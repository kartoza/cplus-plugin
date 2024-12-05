# coding=utf-8
"""
 Plugin tasks related to the scenario history

"""
import datetime
import os
import shutil
from typing import List

from qgis.PyQt import QtCore

from .base import BaseScenarioTask
from .request import CplusApiRequest, CplusApiRequestError
from .scenario_task_api_client import ScenarioAnalysisTaskApiClient
from ..conf import settings_manager
from cplus_core.models.base import Scenario
from cplus_core.analysis import TaskConfig
from ..utils import log


class FetchScenarioHistoryTask(BaseScenarioTask):
    """Task to fetch scenario history from API."""

    def __init__(self, main_widget=None):
        """Task initialization."""
        super().__init__()
        self.result = []
        self.main_widget = main_widget

    def run(self):
        """Execute the task logic.

        :return: True if task runs successfully
        :rtype: bool
        """
        try:
            self.result = self.fetch_scenario_history()
            return True
        except Exception as ex:
            log(f"Error during fetch scenario history: {ex}", info=False)
            return False

    def finished(self, is_success):
        """Handler when task has been executed.

        :param is_success: True if task runs successfully.
        :type is_success: bool
        """
        if is_success:
            self.store_scenario_list(self.result)
        self.task_finished.emit(is_success)
        if self.main_widget:
            self.main_widget.update_scenario_list

    def store_scenario_list(self, result: List[Scenario]):
        """Store scenario history into settings_manager.

        :param result: Scenario history list from API
        :type result: List[Scenario]
        """
        scenarios: List[Scenario] = settings_manager.get_scenarios()
        existing_scenarios = [s for s in scenarios if s.server_uuid is not None]
        for scenario in result:
            exist = [
                s for s in existing_scenarios if s.server_uuid == scenario.server_uuid
            ]
            if len(exist) > 0:
                continue
            settings_manager.save_scenario(scenario)
        for scenario in existing_scenarios:
            exist = [s for s in result if s.server_uuid == scenario.server_uuid]
            if len(exist) > 0:
                continue
            # check if the scenario has been downloaded
            scenario_result = settings_manager.get_scenario_result(scenario.uuid)
            running_online_scenario_uuid = (
                settings_manager.get_running_online_scenario()
            )
            if (
                scenario_result is None
                and str(scenario.uuid) != running_online_scenario_uuid
            ):
                settings_manager.delete_scenario(scenario.uuid)

    def fetch_scenario_history(self):
        """Fetch scenario history list from API.

        :return: latest 10 scenario history.
        :rtype: List[Scenario]
        """
        return self.request.fetch_scenario_history()


class DeleteScenarioTask(BaseScenarioTask):
    """Task to delete Scenario from API."""

    def __init__(self, scenario_server_uuid):
        """Initialize the task.

        :param scenario_server_uuid: scenario server uuid
        :type scenario_server_uuid: str
        """
        super().__init__()
        self.scenario_server_uuid = scenario_server_uuid

    def run(self):
        """Execute the task logic.

        :return: True if task runs successfully
        :rtype: bool
        """
        try:
            self.request.delete_scenario(self.scenario_server_uuid)
            return True
        except Exception as ex:
            log(f"Error during delete scenario: {ex}", info=False)
            return False

    def finished(self, is_success):
        """Handler when task has been executed.

        :param is_success: True if task runs successfully.
        :type is_success: bool
        """
        self.task_finished.emit(is_success)


class FetchScenarioOutputTask(ScenarioAnalysisTaskApiClient):
    """Fetch scenario output from API."""

    task_finished = QtCore.pyqtSignal()

    def __init__(
        self,
        task_config: TaskConfig,
        extent_box,
    ):
        super(FetchScenarioOutputTask, self).__init__(task_config, extent_box)
        self.request = CplusApiRequest()
        self.status_pooling = None
        self.logs = []
        self.total_file_output = 0
        self.downloaded_output = 0
        self.scenario_status = None
        self.scenario_api_uuid = task_config.scenario.uuid
        self.scenario = task_config.scenario

        self.scenario_directory = None
        self.processing_cancelled = False
        self.scenario_result = None
        self.output_list = None
        self.created_datetime = None

    def _get_scenario_directory(self, created_datetime: datetime.datetime) -> str:
        """Generate scenario directory for current task.

        :return: Path to scenario directory
        :rtype: str
        """
        base_dir = self.task_config.base_dir
        return os.path.join(
            f"{base_dir}",
            "scenario_" f'{created_datetime.strftime("%Y_%m_%d_%H_%M_%S")}',
        )

    def run(self):
        """Execute the task logic.

        :return: True if task runs successfully
        :rtype: bool
        """
        try:
            self.status_pooling = self.request.fetch_scenario_status(
                self.scenario_api_uuid
            )
            self.status_pooling.on_response_fetched = self._update_scenario_status
            status_response = self.status_pooling.results()
            self._update_scenario_status(status_response)
            self.new_scenario_detail = self.fetch_scenario_detail()
            self.created_datetime = datetime.datetime.strptime(
                self.new_scenario_detail["submitted_on"], "%Y-%m-%dT%H:%M:%SZ"
            )
            self.scenario_directory = self._get_scenario_directory(
                self.created_datetime
            )
            if os.path.exists(self.scenario_directory):
                for file in os.listdir(self.scenario_directory):
                    if file != "processing.log":
                        path = os.path.join(self.scenario_directory, file)
                        if os.path.isdir(path):
                            shutil.rmtree(os.path.join(self.scenario_directory, file))
                        else:
                            os.remove(path)
            if self.processing_cancelled:
                # Will not proceed if processing has been cancelled by the user
                return False
            self._retrieve_scenario_outputs(self.scenario_api_uuid)
            return True
        except Exception as ex:
            log(f"Error during fetch scenario output list: {ex}", info=False)
            return False

    def finished(self, is_success):
        """Handler when task has been executed.

        :param is_success: True if task runs successfully.
        :type is_success: bool
        """
        if is_success:
            settings_manager.save_scenario(self.scenario)
            if self.scenario_result:
                settings_manager.save_scenario_result(
                    self.scenario_result, str(self.scenario.uuid)
                )
        elif not self.processing_cancelled:
            log("Failed download scenario outputs!", info=False)
        self.task_finished.emit()

    def fetch_scenario_detail(self):
        """Fetch scenario detail from API.

        :return: scenario detail dictionary
        :rtype: dict
        """
        return self.request.fetch_scenario_detail(self.scenario.server_uuid)


class FetchOnlineTaskStatusTask(FetchScenarioHistoryTask):
    """Task to fetch online scenario status from API."""

    task_finished = QtCore.pyqtSignal(str)

    def __init__(self, main_widget):
        super().__init__()
        self.main_widget = main_widget
        self.exception = None
        self.request = CplusApiRequest()
        self.task_status = None

    def fetch_running_scenario(self):
        """Fetch running scenario list from API.

        :return: latest 10 scenario that is running.
        :rtype: List[Scenario]
        """
        return self.request.fetch_scenario_history(status="Running")

    def run(self):
        """Run fetch status using API."""
        running_online_scenario_uuid = settings_manager.get_running_online_scenario()
        online_task = settings_manager.get_scenario(running_online_scenario_uuid)
        if not online_task:
            online_tasks = self.fetch_running_scenario()
            if len(online_tasks) > 0:
                online_task = online_tasks[0]
            else:
                online_task = None

        if online_task:
            try:
                status_response = self.request.fetch_scenario_detail(
                    online_task.server_uuid
                )
                self.task_status = status_response["status"]
            except CplusApiRequestError:
                self.task_status = "Error"

        return True

    def finished(self, result):
        """This method is automatically called when self.run returns."""
        self.task_finished.emit(self.task_status)

    def cancel(self):
        """Cancel ongoing task."""
        super().cancel()
