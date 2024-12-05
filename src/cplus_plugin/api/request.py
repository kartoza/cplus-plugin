import datetime
import io
import json
import math
import os
import time
import typing
import uuid

from qgis import processing
from qgis.PyQt import QtCore
from qgis.PyQt.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import (
    QgsNetworkAccessManager,
    QgsNetworkReplyContent,
    QgsProcessingFeedback,
)

from cplus_core.models.base import Scenario, SpatialExtent, Activity
from ..conf import settings_manager, Settings
from ..definitions.defaults import BASE_API_URL
from ..trends_earth import auth
from ..trends_earth.constants import API_URL as TRENDS_EARTH_API_URL
from ..utils import log, get_layer_type, CustomJsonEncoder

JOB_COMPLETED_STATUS = "Completed"
JOB_CANCELLED_STATUS = "Cancelled"
JOB_RUNNING_STATUS = "Running"
JOB_STOPPED_STATUS = "Stopped"
CHUNK_SIZE = 100 * 1024 * 1024


def debug_log(message: str, data: dict = {}):
    """Log message when DEBUG is enabled.

    :param message: message
    :type message: str

    :param data: payload, defaults to {}
    :type data: dict, optional
    """
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
        """Create Cplus API Pooling for fetching status.

        :param context: context object for making the API request
        :type context: BaseApiClient

        :param url: URL for pooling the status
        :type url: str

        :param headers: header dictionary, defaults to {}
        :type headers: dict, optional

        :param method: API method, defaults to "GET"
        :type method: str, optional

        :param data: payload for POST method, defaults to None
        :type data: dict, optional

        :param max_limit: maximum retries when pooling, defaults to None
        :type max_limit: int, optional

        :param interval: interval for pooling, defaults to None
        :type interval: int, optional

        :param on_response_fetched: callback when response is fetched, defaults to None
        :type on_response_fetched: any, optional
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

    def __call_api(self) -> typing.Tuple[dict, int]:
        """Trigger the api call to fetch the status.

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        if self.method == "GET":
            return self.context.get(self.url)
        return self.context.post(self.url, self.data)

    def results(self) -> dict:
        """Fetch the results from API every X seconds and stop when status is in the final status list.

        :raises CplusApiRequestError: raisess when max limit is reached or server returns non 200 status code.

        :return: response dictionary
        :rtype: dict
        """
        if self.cancelled:
            return {"status": JOB_CANCELLED_STATUS}
        if self.limit != -1 and self.current_repeat >= self.limit:
            raise CplusApiRequestError("Request Timeout when fetching status!")
        self.current_repeat += 1
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
        except Exception as ex:
            log(f"Error when fetching results {ex}", info=False)
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
        """Cplus API URL to get layer detail.

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer detail
        :rtype: str
        """
        return f"{self.base_url}/layer/{layer_uuid}/"

    def layer_check(self) -> str:
        """Cplus API URL for checking layer validity.

        :return: Cplus API URL for layer check
        :rtype: str
        """
        return f"{self.base_url}/layer/check/?id_type=layer_uuid"

    def layer_upload_start(self) -> str:
        """Cplus API URL for starting layer upload.


        :return: Cplus API URL for layer upload start
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/start/"

    def layer_upload_finish(self, layer_uuid) -> str:
        """Cplus API URL for finishing layer upload.

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer upload finish
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/{layer_uuid}/finish/"

    def layer_upload_abort(self, layer_uuid) -> str:
        """Cplus API URL for aborting layer upload.

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Cplus API URL for layer upload abort
        :rtype: str
        """
        return f"{self.base_url}/layer/upload/{layer_uuid}/abort/"

    def layer_default_list(self):
        return f"{self.base_url}/layer/default/"

    def scenario_submit(self, plugin_version=None) -> str:
        """Cplus API URL for submitting scenario JSON.

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
        """Cplus API URL for executing scenario.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario execution
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/execute/"

    def scenario_status(self, scenario_uuid) -> str:
        """Cplus API URL for getting scenario status.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario status
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/status/"

    def scenario_cancel(self, scenario_uuid) -> str:
        """Cplus API URL for cancelling scenario execution.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for cancelling scenario execution
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/cancel/"

    def scenario_history_list(self, page=1, page_size=10, filters={}):
        params = f"page={page}&page_size={page_size}"
        for key, filter in filters.items():
            params = params + f"&{key}={filter}"
        return f"{self.base_url}/scenario/history/?{params}"

    def scenario_detail(self, scenario_uuid) -> str:
        """Cplus API URL for getting scenario detail.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for getting scenario detail
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/detail/"

    def scenario_delete(self, scenario_uuid):
        """Cplus API URL for deleting a scenario.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for deleting a scenario
        :rtype: str
        """
        return f"{self.base_url}/scenario/{scenario_uuid}/detail/"

    def scenario_output_list(self, scenario_uuid) -> str:
        """Cplus API URL for listing scenario output.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: Cplus API URL for scenario output list
        :rtype: str
        """
        return (
            f"{self.base_url}/scenario_output/{scenario_uuid}/"
            "list/?page=1&page_size=100"
        )


class CplusApiRequest:
    """Class to send request to Cplus API."""

    page_size = 50

    def __init__(self) -> None:
        super().__init__()
        self.urls = CplusApiUrl()
        self.trends_urls = TrendsApiUrl()
        self._api_token = None
        self.token_exp = None

    def _get_raw_header_value(self, value: str) -> QtCore.QByteArray:
        """Get byte array of header name or value.

        :param value: header name/value
        :type value: str

        :return: bytes array of string value
        :rtype: QtCore.QByteArray
        """
        return QtCore.QByteArray(bytes(value, encoding="utf-8"))

    def _generate_request(self, url: str, headers: dict = {}) -> QNetworkRequest:
        """Generate request from url and set headers in the request.

        :param url: URL in request
        :type url: str

        :param headers: header dictionary, defaults to {}
        :type headers: dict, optional

        :return: request object
        :rtype: QNetworkRequest
        """
        request = QNetworkRequest(QtCore.QUrl(url))
        self._set_headers(request, headers)
        return request

    def _set_headers(self, request: QNetworkRequest, headers: dict = {}):
        """Set headers into a request object.

        :param request: request object
        :type request: QNetworkRequest

        :param headers: header dictionary, defaults to {}
        :type headers: dict, optional
        """
        for key, value in headers.items():
            request.setRawHeader(
                self._get_raw_header_value(key),
                self._get_raw_header_value(value),
            )

    def _read_json_response(
        self, reply: typing.Union[QNetworkReply, QgsNetworkReplyContent]
    ) -> dict:
        """Parse json response from reply object.

        :param reply: reply object
        :type reply: QNetworkReply

        :return: dictionary of the response, empty if failed to parse
        :rtype: dict
        """
        response = {}
        try:
            if isinstance(reply, QNetworkReply):
                ret = reply.readAll().data().decode("utf-8")
                response = json.loads(ret)
            elif isinstance(reply, QgsNetworkReplyContent):
                ret = reply.content()
                response = json.load(io.BytesIO(ret))
            else:
                err_msg = "Unknown object type: {}.".format(str(reply))
                debug_log(err_msg)
        except Exception as ex:
            log(f"Error parsing API response {ex}")
        debug_log(f"Response: {response}")
        return response

    def _handle_response(
        self, url: str, reply: typing.Union[QNetworkReply, QgsNetworkReplyContent]
    ) -> typing.Tuple[dict, int]:
        """Handle response from a request.

        :param url: URL from the request
        :type url: str

        :param reply: reply object
        :type reply: QNetworkReply

        :raises CplusApiRequestError: raises when there is Network Error

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        json_response = {}
        http_status = None
        # Check for network errors
        if reply.error() == QNetworkReply.NoError:
            # Check the HTTP status code
            http_status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
            if http_status is not None and 200 <= http_status < 300:
                if http_status == 204:
                    json_response = {}
                else:
                    json_response = self._read_json_response(reply)
            else:
                log(f"HTTP Error: {http_status} from request {url}")
                json_response = self._read_json_response(reply)
            if isinstance(reply, QNetworkReply):
                reply.deleteLater()
        else:
            # log the error string
            log(f"Network Error: {reply.errorString()} from request {url}")
            if isinstance(reply, QNetworkReply):
                reply.deleteLater()
            raise CplusApiRequestError(f"Network error: {reply.errorString()}")
        http_status = http_status if http_status is not None else 500
        debug_log(f"Status-Code: {http_status}")
        return json_response, http_status

    def _make_request(self, reply: QNetworkReply):
        """Make request in the event loop.

        :param reply: reply object
        :type reply: QNetworkReply
        """
        debug_log(f"URL: {reply.request().url()}")
        # Create an event loop
        event_loop = QtCore.QEventLoop()
        # Connect the reply's finished signal to the event loop's quit slot
        reply.finished.connect(event_loop.quit)
        # Start the event loop, waiting for the request to complete
        event_loop.exec_()

    def _get_request_payload(self, data: typing.Union[dict, list]) -> QtCore.QByteArray:
        """Get byte array of json request payload.

        :param data: request payload
        :type data: typing.Union[dict, list]

        :return: byte array object
        :rtype: QtCore.QByteArray
        """
        return QtCore.QByteArray(
            json.dumps(data, cls=CustomJsonEncoder).encode("utf-8")
        )

    def get(self, url: str, headers: dict = {}) -> typing.Tuple[dict, int]:
        """Trigger a GET request.

        :param url: Cplus API URL
        :type url: str

        :param headers: header dictionary, defaults to {}
        :type headers: dict

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        nam = QgsNetworkAccessManager.instance()
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        reply = nam.blockingGet(request, forceRefresh=True)
        return self._handle_response(url, reply)

    def post(
        self, url: str, data: typing.Union[dict, list], headers: dict = {}
    ) -> typing.Tuple[dict, int]:
        """Trigger a POST request.

        :param url: Cplus API URL
        :type url: str

        :param data: API payload
        :type data: typing.Union[dict, list]

        :param headers: header dictionary, defaults to {}
        :type headers: dict

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        nam = QgsNetworkAccessManager.instance()
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        json_data = self._get_request_payload(data)
        reply = nam.blockingPost(request, json_data)
        return self._handle_response(url, reply)

    def put(
        self, url: str, data: typing.Union[dict, list], headers: dict = {}
    ) -> typing.Tuple[dict, int]:
        """Trigger a PUT request.

        :param url: Cplus API URL
        :type url: str

        :param data: API payload
        :type data: typing.Union[dict, list]

        :param headers: header dictionary, defaults to {}
        :type headers: dict

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        nam = QgsNetworkAccessManager.instance()
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        json_data = self._get_request_payload(data)
        reply = nam.put(request, json_data)
        self._make_request(reply)
        return self._handle_response(url, reply)

    def delete(self, url: str, headers: dict = {}) -> typing.Tuple[dict, int]:
        """Trigger a DELETE request.

        :param url: Cplus API URL
        :type url: str

        :param headers: header dictionary, defaults to {}
        :type headers: dict

        :return: tuple of response dictionary and HTTP status code
        :rtype: typing.Tuple[dict, int]
        """
        nam = QgsNetworkAccessManager.instance()
        headers = headers or self._default_headers()
        request = self._generate_request(url, headers)
        reply = nam.deleteResource(request)
        self._make_request(reply)
        return self._handle_response(url, reply)

    def _on_download_error(self, filename: str, error):
        """Callback when there is an error in download file.

        :param filename: filename of the downloaded file
        :type filename: str

        :param error: exception
        :type error: any

        :raises CplusApiRequestError: error
        """
        log(f"Error while downloading file to {filename}: {error}")
        raise CplusApiRequestError(f"Unable to start download of {filename}, {error}")

    def _on_download_finished(self, filename: str):
        """Callback when download file is finished.

        :param filename: filename of the downloaded file
        :type filename: str
        """
        log(f"Finished downloading file to {filename}")

    def download_file(self, url: str, file_path: str, on_download_progress):
        """Download a file from url and save into output file in file_path.

        :param url: Download URL
        :type url: str

        :param file_path: Path to the output file
        :type file_path: str

        :param on_download_progress: callback for download progress signal
        :type on_download_progress: any
        """

        feedback = QgsProcessingFeedback()
        params = {"URL": url, "OUTPUT": file_path}
        feedback.progressChanged.connect(on_download_progress)

        processing.run("qgis:filedownloader", params, feedback=feedback)

    def _do_upload_file_part(
        self, url: str, chunk: typing.Union[bytes, bytearray], file_part_number: int
    ) -> dict:
        """Trigger a PUT request to upload a chunk file to the url.

        :param url: Upload URL
        :type url: str

        :param chunk: File chunk to be uploaded
        :type chunk: bytes or bytearray

        :param file_part_number: File part number
        :type file_part_number: int

        :raises Exception: raises when there is Network Error
        :return: Dictionary of part_number and etag

        :rtype: dict
        """
        nam = QgsNetworkAccessManager.instance()
        request = QNetworkRequest(QtCore.QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/octet-stream")
        request.setHeader(QNetworkRequest.ContentLengthHeader, len(chunk))
        if url.startswith("http://"):
            # add header for minio host in local env
            request.setRawHeader(
                self._get_raw_header_value("Host"),
                self._get_raw_header_value("minio:9000"),
            )
        reply = nam.put(request, chunk)
        self._make_request(reply)
        response = {}
        if reply.error() == QNetworkReply.NoError:
            etag = reply.rawHeader(b"ETag")
            response = {
                "part_number": file_part_number,
                "etag": etag.data().decode("utf-8"),
            }
            debug_log("Upload chunk finished:", response)
            reply.deleteLater()
        else:
            reply.deleteLater()
            raise Exception(f"Network Error: {reply.errorString()}")
        return response

    def upload_file_part(
        self,
        url: str,
        chunk: typing.Union[bytes, bytearray],
        file_part_number: int,
        max_retries=5,
    ) -> dict:
        """Do upload of a file part using exponential backoff.

        :param url: Upload URL
        :type url: str

        :param chunk: File chunk to be uploaded
        :type chunk: typing.Union[bytes, bytearray]

        :param file_part_number: File part number
        :type file_part_number: int

        :param max_retries: Maximum retries in exponential backoff, defaults to 5
        :type max_retries: int, optional

        :return: Dictionary of part_number and etag
        :rtype: dict
        """
        retries = 0
        while retries < max_retries:
            try:
                return self._do_upload_file_part(url, chunk, file_part_number)
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
        return None

    def _default_headers(self) -> dict:
        """Get default headers for Cplus API requests.

        :return: header dictionary
        :rtype: dict
        """
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def _is_valid_token(self) -> bool:
        """Check if api token exists and valid before its expiry.

        :return: True if valid token
        :rtype: bool
        """
        return (
            self._api_token is not None
            and self.token_exp > datetime.datetime.now() + datetime.timedelta(hours=1)
        )

    @property
    def api_token(self) -> str:
        """Property to return an api token from Trends Earth Authentication.

        :raises CplusApiRequestError: Raises when authentication is failed
        :return: API Token
        :rtype: str
        """
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
        """Request for getting layer detail.

        :param layer_uuid: Layer UUID
        :type layer_uuid: str

        :return: Layer detail
        :rtype: dict
        """
        result, _ = self.get(self.urls.layer_detail(layer_uuid))
        return result

    def check_layer(self, payload) -> dict:
        """Request for checking layer validity.

        :param payload: List of Layer UUID
        :type payload: list

        :return: dict consisting of which Layer UUIDs are available,
            unavailable, or invalid
        :rtype: dict
        """
        result, _ = self.post(self.urls.layer_check(), payload)
        return result

    def start_upload_layer(self, file_path: str, component_type: str) -> dict:
        """Request for starting layer upload.

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
        """Request for finishing layer upload.

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
        """Aborting layer upload.

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

    def submit_scenario_detail(self, scenario_detail: dict) -> str:
        """Submitting scenario JSON to Cplus API.

        :param scenario_detail: Scenario detail
        :type scenario_detail: dict

        :raises CplusApiRequestError: If the failed to submit scenario

        :return: Scenario UUID
        :rtype: str
        """
        result, status_code = self.post(self.urls.scenario_submit(), scenario_detail)
        if status_code != 201:
            raise CplusApiRequestError(result.get("detail", ""))
        return result["uuid"]

    def execute_scenario(self, scenario_uuid: str) -> bool:
        """Executing scenario in Cplus API.

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
        """Fetching scenario status.

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str

        :return: CplusApiPooling object
        :rtype: CplusApiPooling
        """
        url = self.urls.scenario_status(scenario_uuid)
        return CplusApiPooling(self, url)

    def cancel_scenario(self, scenario_uuid: str) -> bool:
        """Cancel scenario execution.

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
        """List scenario output.

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
        """Fetch scenario detail.

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

    def fetch_default_layer_list(self) -> dict:
        """Fetch available default layers from Server.

        :raises CplusApiRequestError: when response code is non-2xx
        :return: Layer List
        :rtype: dict
        """
        result, status_code = self.get(self.urls.layer_default_list())
        if status_code != 200:
            raise CplusApiRequestError(result.get("detail", ""))
        data = {}
        for layer in result:
            component_type = layer.get("component_type", "")
            out_layer = {
                "type": component_type,
                "layer_uuid": layer.get("uuid"),
                "name": layer.get("filename"),
                "size": layer.get("size"),
                "layer_type": layer.get("layer_type"),
                "metadata": layer.get("metadata", {}),
            }
            if component_type in data:
                data[component_type].append(out_layer)
            else:
                data[component_type] = [out_layer]
        return data

    def build_scenario_from_scenario_json(self, scenario_json):
        """Build scenario object from scenario JSON.

        :param scenario_json: scenario json dict
        :type scenario_json: dict

        :return: Scenario object
        :rtype: Scenario
        """
        detail = scenario_json["detail"]
        extent = []
        if "extent_project" in detail:
            extent = detail.get("extent_project", [])
        else:
            extent = detail.get("extent", [])

        scenario = Scenario(
            uuid=uuid.uuid4(),
            name=detail.get("scenario_name", ""),
            description=detail.get("scenario_desc", ""),
            extent=SpatialExtent(bbox=extent),
            server_uuid=uuid.UUID(scenario_json["uuid"]),
            activities=[
                Activity.from_dict(activity) for activity in detail["activities"]
            ],
            weighted_activities=[],
            priority_layer_groups=detail["priority_layer_groups"],
        )
        return scenario

    def fetch_scenario_history(self, page=1, page_size=10, status="Completed"):
        """Fetch scenario history from server.

        :param page: page number, defaults to 1
        :type page: int, optional

        :param page_size: page size to fetch, defaults to 10
        :type page_size: int, optional

        :raises CplusApiRequestError: Raises when server return non-2xx code

        :return: List of Scenario object
        :rtype: List[Scenario]
        """
        filters = {"status": status}
        result, status_code = self.get(
            self.urls.scenario_history_list(page, page_size, filters)
        )
        if status_code != 200:
            raise CplusApiRequestError(result.get("detail", ""))
        scenario_results = []
        for item in result["results"]:
            detail = item["detail"]
            extent = []
            if "extent_project" in detail:
                extent = detail.get("extent_project", [])
            else:
                extent = detail.get("extent", [])
            scenario_results.append(
                Scenario(
                    uuid=uuid.uuid4(),
                    name=detail.get("scenario_name", ""),
                    description=detail.get("scenario_desc", ""),
                    extent=SpatialExtent(bbox=extent),
                    server_uuid=uuid.UUID(item["uuid"]),
                    activities=[
                        Activity.from_dict(activity)
                        for activity in detail["activities"]
                    ],
                    weighted_activities=[],
                    priority_layer_groups=detail["priority_layer_groups"],
                )
            )
        return scenario_results

    def delete_scenario(self, scenario_uuid):
        """Delete scenario history from server.

        :param scenario_uuid: Server's scenario UUID
        :type scenario_uuid: str

        :raises CplusApiRequestError: Raises when server return non-204 code

        :return: No content
        :rtype: dictionary
        """
        result, status_code = self.delete(self.urls.scenario_delete(scenario_uuid))
        if status_code != 204:
            raise CplusApiRequestError(result.get("detail", ""))
        return result
