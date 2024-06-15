import json
import math
import os
import time
import typing
import datetime

from qgis.PyQt import QtCore
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import QgsNetworkAccessManager

from ..utils import log, get_layer_type
from ..conf import settings_manager, Settings
from ..trends_earth import auth
from ..trends_earth.constants import API_URL as TRENDS_EARTH_API_URL
from ..definitions.defaults import BASE_API_URL

JOB_COMPLETED_STATUS = "Completed"
JOB_CANCELLED_STATUS = "Cancelled"
JOB_STOPPED_STATUS = "Stopped"
CHUNK_SIZE = 100 * 1024 * 1024


def log_response(response: typing.Union[dict, str], request_name: str) -> None:
    """Log response to QGIS console.
    :param response: Response from CPLUS API
    :type response: dict
    :param request_name: Name of the request
    :type request_name: str
    """

    if not settings_manager.get_value(Settings.DEBUG):
        return
    log(f"****Request - {request_name} *****")
    if isinstance(response, dict):
        log(json.dumps(response))
    else:
        log(response)


def debug_log(message, data: dict = {}):
    if not settings_manager.get_value(Settings.DEBUG):
        return
    log(message)
    if data:
        log(json.dumps(data))


class CplusApiRequestError(Exception):
    """Error class for Cplus API Request.
    :param message: Error message
    :type message: str
    """

    def __init__(self, message):
        """Constructor for CplusApiRequestError"""
        if isinstance(message, dict):
            message = json.dumps(message)
        elif isinstance(message, list):
            message = ", ".join(message)
        log(message, info=False)
        self.message = message
        super().__init__(self.message)


class BaseApiClient:
    """Base class for API client."""

    def __init__(self) -> None:
        self.nam = QgsNetworkAccessManager.instance()

    def _default_headers(self):
        return {"Content-Type": "application/json"}

    def _generate_request(self, url: str, headers: dict = {}):
        request = QNetworkRequest(QtCore.QUrl(url))
        self._set_headers(request, headers)
        return request

    def _set_headers(self, request: QNetworkRequest, headers: dict = {}):
        for key, value in headers:
            request.setRawHeader(
                QtCore.QByteArray(bytes(key, "utf-8")),
                QtCore.QByteArray(bytes(value, encoding="utf-8")),
            )

    def _read_json_response(self, reply: QNetworkReply):
        response = {}
        try:
            ret = reply.readAll().data().decode("utf-8")
            debug_log(f"Response: {ret}")
            response = json.load(ret)
        except Exception as ex:
            log(f"Error parsing API response {ex}")
        return response

    def _handle_response(self, url: str, reply: QNetworkReply):
        json_response = {}
        http_status = None
        # Check for network errors
        if reply.error() == QNetworkReply.NoError:
            # Check the HTTP status code
            http_status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if http_status is not None and 200 <= http_status < 300:
                json_response = self._read_json_response(reply)
            else:
                log(f"HTTP Error: {http_status} from request {url}")
                json_response = self._read_json_response(reply)
            reply.deleteLater()
        else:
            # log the error string
            log(f"Network Error: {reply.errorString()} from request {url}")
            reply.deleteLater()
            raise CplusApiRequestError(f"Network error: {reply.errorString()}")
        http_status = http_status if http_status is not None else 500
        debug_log(f"Status-Code: {http_status}")
        return json_response, http_status

    def _make_request(self, reply: QNetworkReply):
        debug_log(f"URL: {reply.request().url()}")
        # Create an event loop
        event_loop = QtCore.QEventLoop()
        # Connect the reply's finished signal to the event loop's quit slot
        reply.finished.connect(event_loop.quit)
        # Start the event loop, waiting for the request to complete
        event_loop.exec_()

    def _get_request_payload(self, data: typing.Union[dict, list]):
        return QtCore.QByteArray(json.dumps(data).encode("utf-8"))

    def get(self, url, headers: dict = {}):
        """GET requests.

        :param url: Cplus API URL
        :type url: str

        :return: Response from Cplus API
        :rtype: requests.Response
        """
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        reply = self.nam.get(request)
        self._make_request(reply)
        return self._handle_response(url, reply)

    def post(self, url: str, data: typing.Union[dict, list], headers: dict = {}):
        """POST requests.

        :param url: Cplus API URL
        :type url: typing.Union[dict, list]
        :param data: Cplus API payload
        :type data: dict

        :return: Response from Cplus API
        :rtype: requests.Response
        """
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        json_data = self._get_request_payload(data)
        reply = self.nam.post(request, json_data)
        self._make_request(reply)
        return self._handle_response(url, reply)

    def put(self, url: str, data: typing.Union[dict, list], headers: dict = {}):
        """PUT requests.

        :param url: Cplus API URL
        :type url: typing.Union[dict, list]
        :param data: Cplus API payload
        :type data: dict

        :return: Response from Cplus API
        :rtype: requests.Response
        """
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        json_data = self._get_request_payload(data)
        reply = self.nam.put(request, json_data)
        self._make_request(reply)
        return self._handle_response(url, reply)

    def download_file(self, url, file_path):
        pass

    def _do_upload_file_part(self, url, chunk, file_part_number):
        request = QNetworkRequest(QtCore.QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/octet-stream")
        request.setHeader(QNetworkRequest.ContentLengthHeader, len(chunk))
        reply = self.nam.put(request, chunk)
        self._make_request(reply)
        response = {}
        if reply.error() == QNetworkReply.NoError:
            etag = reply.rawHeader(b"ETag")
            response = {
                "part_number": file_part_number,
                "etag": etag.data().decode("utf-8"),
            }
            debug_log("Upload chunk finished:", response)
        else:
            raise Exception(f"Network Error: {reply.errorString()}")
        reply.deleteLater()
        return response

    def upload_file_part(self, url, chunk, file_part_number, max_retries=5):
        retries = 0
        while retries < max_retries:
            try:
                self._do_upload_file_part(url, chunk, file_part_number)
            except Exception as e:
                log(f"Request failed: {e}")
                retries += 1
                if retries < max_retries:
                    # Calculate the exponential backoff delay
                    delay = 2**retries
                    log(f"Retrying in {delay} seconds...")
                    time.sleep(delay)
                else:
                    log("Max retries exceeded.")
                    raise


class CplusApiPooling:
    """Fetch/Post url with pooling."""

    DEFAULT_LIMIT = 3600  # Check result maximum 3600 times
    DEFAULT_INTERVAL = 1  # Interval of check results
    FINAL_STATUS_LIST = [JOB_COMPLETED_STATUS, JOB_CANCELLED_STATUS, JOB_STOPPED_STATUS]

    def __init__(
        self,
        context,
        url,
        headers={},
        method="GET",
        data=None,
        max_limit=None,
        interval=None,
        on_response_fetched=None,
    ):
        """Create Cplus API Pooling for Fetching Status.

        :param context: _description_
        :type context: _type_
        :param url: _description_
        :type url: _type_
        :param headers: _description_, defaults to {}
        :type headers: dict, optional
        :param method: _description_, defaults to "GET"
        :type method: str, optional
        :param data: _description_, defaults to None
        :type data: _type_, optional
        :param max_limit: _description_, defaults to None
        :type max_limit: _type_, optional
        :param interval: _description_, defaults to None
        :type interval: _type_, optional
        :param on_response_fetched: _description_, defaults to None
        :type on_response_fetched: _type_, optional
        """
        self.context = context
        self.url = url
        self.headers = headers
        self.current_repeat = 0
        self.method = method
        self.data = data
        self.limit = max_limit or self.DEFAULT_LIMIT
        self.interval = interval or self.DEFAULT_INTERVAL
        self.on_response_fetched = on_response_fetched
        self.cancelled = False

    def __call_api(self):
        if self.method == "GET":
            return self.context.get(self.url)
        return self.context.post(self.url, self.data)

    def results(self):
        """Return results of data."""
        if self.cancelled:
            return {"status": JOB_CANCELLED_STATUS}
        self.current_repeat += 1
        if self.limit != -1 and self.current_repeat >= self.limit:
            raise CplusApiRequestError("Request Timeout when fetching status!")
        try:
            response, status_code = self.__call_api()
            if status_code != 200:
                error_detail = response.get("detail", "Unknown Error!")
                raise CplusApiRequestError(f"{status_code} - {error_detail}")
            if self.on_response_fetched:
                self.on_response_fetched(response)
            if response["status"] in self.FINAL_STATUS_LIST:
                return response
            else:
                time.sleep(self.interval)
                return self.results()
        except Exception:
            time.sleep(self.interval)
            return self.results()


class TrendsApiUrl:
    """Trends API Urls."""

    def __init__(self) -> None:
        self.base_url = TRENDS_EARTH_API_URL

    @property
    def auth(self):
        return f"{self.base_url}/auth"


class CplusApiUrl:
    """Class for Cplus API Urls."""

    def __init__(self):
        self.base_url = self.get_base_api_url()

    def get_base_api_url(self) -> str:
        """Returns the base API URL.

        :return: Base API URL
        :rtype: str
        """

        debug = settings_manager.get_value(Settings.DEBUG, False, bool)
        if debug:
            return settings_manager.get_value(Settings.BASE_API_URL)
        else:
            return BASE_API_URL

    def layer_detail(self, layer_uuid) -> str:
        """Cplus API URL to get layer detail

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer detail
        :rtype: str
        """
        return f"{self.base_url}/layer/{layer_uuid}/"

    def layer_check(self) -> str:
        """Cplus API URL for checking layer validity


        :return: Cplus API URL for layer check
        :rtype: str
        """
        return f"{self.base_url}/layer/check/?id_type=layer_uuid"

    def layer_upload_start(self) -> str:
        """Cplus API URL for starting layer upload


        :return: Cplus API URL for layer upload start
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/start/"

    def layer_upload_finish(self, layer_uuid) -> str:
        """Cplus API URL for finishing layer upload

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer upload finish
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/{layer_uuid}/finish/"

    def layer_upload_abort(self, layer_uuid) -> str:
        """Cplus API URL for aborting layer upload

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer upload abort
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/{layer_uuid}/abort/"

    def scenario_submit(self, plugin_version=None) -> str:
        """Cplus API URL for submitting scenario JSON

        :param plugin_version: Version of the Cplus Plugin
        :type plugin_version: str

        :return: Cplus API URL for scenario submission
        :rtype: str
        """
        url = f"{self.base_url}/scenario/submit/"
        if plugin_version:
            url += f"?plugin_version={plugin_version}"
        return url

    def scenario_execute(self, scenario_uuid) -> str:
        """Cplus API URL for executing scenario

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario execution
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/execute/"

    def scenario_status(self, scenario_uuid) -> str:
        """Cplus API URL for getting scenario status

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario status
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/status/"

    def scenario_cancel(self, scenario_uuid) -> str:
        """Cplus API URL for cancelling scenario execution

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for cancelling scenario execution
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/cancel/"

    def scenario_detail(self, scenario_uuid) -> str:
        """Cplus API URL for getting scenario detal

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for getting scenario detail
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/detail/"

    def scenario_output_list(self, scenario_uuid) -> str:
        """Cplus API URL for listing scenario output

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario output list
        :rtype: str
        """
        return (
            f"{self.base_url}/scenario_output/{scenario_uuid}/"
            "list/?page=1&page_size=100"
        )


class CplusApiRequest(BaseApiClient):
    """Class to send request to Cplus API."""

    page_size = 50

    def __init__(self) -> None:
        super().__init__()
        self.urls = CplusApiUrl()
        self.trends_urls = TrendsApiUrl()
        self._api_token = None
        self.token_exp = None

    def _default_headers(self):
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _is_valid_token(self):
        return (
            self._api_token is not None
            and self.token_exp > datetime.datetime.now() + datetime.timedelta(hours=1)
        )

    @property
    def api_token(self):
        if self._is_valid_token():
            return self._api_token
        # fetch token from Trends Earth API
        auth_config = auth.get_auth_config(auth.TE_API_AUTH_SETUP, warn=None)
        if (
            not auth_config
            or not auth_config.config("username")
            or not auth_config.config("password")
        ):
            log("API unable to login - setup auth configuration before using")
            return
        payload = {
            "email": auth_config.config("username"),
            "password": auth_config.config("password"),
        }
        response, status_code = self.post(
            self.trends_urls.auth, payload, {"Content-Type": "application/json"}
        )
        if status_code != 200:
            detail = response.get("description", "Unknwon Error!")
            raise CplusApiRequestError(
                "Error authenticating to Trends Earth API: " f"{status_code} - {detail}"
            )
        access_token = response.get("access_token", None)
        if access_token is None:
            raise CplusApiRequestError(
                "Error authenticating to Trends Earth API: " "missing access_token!"
            )
        self._api_token = access_token
        self.token_exp = datetime.datetime.now() + datetime.timedelta(days=1)
        return access_token

    def get_layer_detail(self, layer_uuid) -> dict:
        """Request for getting layer detail

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Layer detail
        :rtype: dict
        """
        result, _ = self.get(self.urls.layer_detail(layer_uuid))
        return result

    def check_layer(self, payload) -> dict:
        """Request for checking layer validity

        :param payload: List of Layer UUID
        :type payload: list

        :return: dict consisting of which Layer UUIDs are available,
            unavailable, or invalid
        :rtype: dict
        """
        log(self.urls.layer_check())
        log(json.dumps(payload))
        result, _ = self.post(self.urls.layer_check(), payload)
        return result

    def start_upload_layer(self, file_path: str, component_type: str) -> dict:
        """Request for starting layer upload

        :param file_path: Path of the file to be uploaded
        :type file_path: str
        :param component_type: Layer component type, e.g. "ncs_pathway"
        :type component_type: str
        :raises CplusApiRequestError: If the request is failing

        :return: Dictionary of the layer to be uploaded
        :rtype: dict
        """
        file_size = os.stat(file_path).st_size
        payload = {
            "layer_type": get_layer_type(file_path),
            "component_type": component_type,
            "privacy_type": "private",
            "name": os.path.basename(file_path),
            "size": file_size,
            "number_of_parts": math.ceil(file_size / CHUNK_SIZE),
        }
        result, status_code = self.post(self.urls.layer_upload_start(), payload)
        if status_code != 201:
            raise CplusApiRequestError(result.get("detail", ""))
        return result

    def finish_upload_layer(
        self,
        layer_uuid: str,
        upload_id: typing.Union[str, None],
        items: typing.Union[typing.List[dict], None],
    ) -> dict:
        """Request for finishing layer upload

        :param layer_uuid: UUID of the uploaded layer
        :type layer_uuid: str
        :param upload_id: Upload ID of the multipart upload, optional,
            defaults to None
        :type upload_id: str
        :param items: List of uploaded items for multipart upload, optional,
            defaults to None
        :type items: typing.Union[typing.List[dict], None]

        :return: Dictionary containing the UUID, name, size of the upload file
        :rtype: dict
        """
        payload = {}
        if upload_id:
            payload["multipart_upload_id"] = upload_id
        if items:
            payload["items"] = items
        result, _ = self.post(self.urls.layer_upload_finish(layer_uuid), payload)
        return result

    def abort_upload_layer(self, layer_uuid: str, upload_id: str) -> bool:
        """Aborting layer upload

        :param layer_uuid: UUID of a Layer that is currently being uploaded
        :type layer_uuid: str
        :param upload_id: Multipart Upload ID
        :type upload_id: str
        :raises CplusApiRequestError: If the abort is failed

        :return: True if upload is successfully aborted
        :rtype: bool
        """
        payload = {"multipart_upload_id": upload_id, "items": []}
        result, status_code = self.post(
            self.urls.layer_upload_abort(layer_uuid), payload
        )
        if status_code != 204:
            raise CplusApiRequestError(result.get("detail", ""))
        return True

    def submit_scenario_detail(self, scenario_detail: dict) -> bool:
        """Submitting scenario JSON to Cplus API

        :param scenario_detail: Scenario detail
        :type scenario_detail: dict
        :raises CplusApiRequestError: If the failed to submit scenario

        :return: Scenario UUID
        :rtype: bool
        """
        log_response(scenario_detail, "scenario_detail")
        result, status_code = self.post(self.urls.scenario_submit(), scenario_detail)
        if status_code != 201:
            raise CplusApiRequestError(result.get("detail", ""))
        return result["uuid"]

    def execute_scenario(self, scenario_uuid: str) -> bool:
        """Executing scenario in Cplus API

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str
        :raises CplusApiRequestError: If the failed to execute scenario

        :return: True if the scenario was successfully executed
        :rtype: bool
        """
        result, status_code = self.get(self.urls.scenario_execute(scenario_uuid))
        if status_code != 201:
            raise CplusApiRequestError(result.get("detail", ""))
        return True

    def fetch_scenario_status(self, scenario_uuid) -> CplusApiPooling:
        """Fetching scenario status

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: CplusApiPooling object
        :rtype: CplusApiPooling
        """
        url = self.urls.scenario_status(scenario_uuid)
        return CplusApiPooling(self, url, self.urls.headers)

    def cancel_scenario(self, scenario_uuid: str) -> bool:
        """Cancel scenario execution

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str
        :raises CplusApiRequestError: If the failed to cancel scenario

        :return: True if the scenario was successfully cancelled
        :rtype: bool
        """
        result, status_code = self.get(self.urls.scenario_cancel(scenario_uuid))
        if status_code != 200:
            raise CplusApiRequestError(result.get("detail", ""))
        return True

    def fetch_scenario_output_list(self, scenario_uuid) -> typing.List[dict]:
        """List scenario output

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str
        :raises CplusApiRequestError: If the failed to list scenario output

        :return: List of scenario output:
        :rtype: typing.List[dict]
        """
        result, status_code = self.get(self.urls.scenario_output_list(scenario_uuid))
        if status_code != 200:
            raise CplusApiRequestError(result.get("detail", ""))
        return result

    def fetch_scenario_detail(self, scenario_uuid: str) -> dict:
        """Fetch scenario detail

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str
        :raises CplusApiRequestError: If the failed to list scenario output

        :return: Scenario detail
        :rtype: dict
        """
        result, status_code = self.get(self.urls.scenario_detail(scenario_uuid))
        if status_code != 200:
            raise CplusApiRequestError(result.get("detail", ""))
        return result
