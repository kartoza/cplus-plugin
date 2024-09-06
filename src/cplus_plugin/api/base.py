# coding=utf-8
"""
 Plugin tasks related to the scenario history

"""
import concurrent.futures
import copy
import datetime
import json
import os

import requests
from qgis.PyQt import QtCore
from qgis.core import QgsTask

from .request import CplusApiRequest
from ..models.base import Scenario, ScenarioResult, NcsPathway, Activity


class BaseScenarioTask(QgsTask):
    """Base Qgs task for Scenario API Operation."""

    task_finished = QtCore.pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.request = CplusApiRequest()


class BaseFetchScenarioOutput:
    """Base class for fetching scenario output."""

    def __init__(self) -> None:
        """Initialize BaseFetchScenarioOutput class."""
        self.downloaded_output = 0
        self.total_file_output = 0
        self.created_datetime = datetime.datetime.now()

    def is_download_cancelled(self):
        """Check if download is cancelled.

        This method should be overriden by child class.
        :return: True if task has been cancelled
        :rtype: bool
        """
        return False

    def download_file(self, url, local_filename):
        """Download file output.

        :param url: URL to the file output
        :type url: str
        :param local_filename: output filepath
        :type local_filename: str
        """
        parent_dir = os.path.dirname(local_filename)
        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir)
        headers = {"Cache-Control": "no-cache"}
        with requests.get(url, stream=True, headers=headers) as r:
            r.raise_for_status()
            if self.is_download_cancelled():
                return
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                    if self.is_download_cancelled():
                        return
        self.downloaded_output += 1

    def __create_activity(self, activity: dict, download_dict: list):
        """
        Create activity object from activity and downloaded file dictionary.

        :param activity: activity dictionary
        :type activity: dict
        :param download_dict: downloaded file dictionary
        :type download_dict: dict
        """
        ncs_pathways = []
        for pathway in activity["pathways"]:
            if "layer_uuid" in pathway:
                del pathway["layer_uuid"]
            if "carbon_uuids" in pathway:
                del pathway["carbon_uuids"]
            pathway_filename = os.path.basename(pathway["path"])
            if pathway_filename in download_dict:
                pathway["path"] = download_dict[pathway_filename]
                ncs_pathways.append(NcsPathway(**pathway))
        activity["pathways"] = ncs_pathways
        activity_filename = os.path.basename(activity["path"])
        if activity_filename in download_dict:
            activity["path"] = download_dict[activity_filename]
        activity_obj = Activity(**activity)
        activity_obj.pathways = ncs_pathways
        return activity_obj

    def __create_scenario(
        self, original_scenario, scenario_detail, output_list, download_paths
    ):
        """Create scenario object based on output list for generating reports.

        :param original_scenario: Original scenario
        :type original_scenario: Scenario
        :param scenario_detail: Scenario dictionary from API
        :type scenario_detail: dict
        :param output_list: Scenario output list from API
        :type output_list: dict
        :param download_paths: List of downloaded file paths
        :type download_paths: list
        :return: Scenario object
        :rtype: Scenario
        """
        from ..utils import log, todict, CustomJsonEncoder

        log(json.dumps(todict(scenario_detail), cls=CustomJsonEncoder))
        output_fnames = []
        for output in output_list["results"]:
            if "_cleaned" in output["filename"]:
                output_fnames.append(output["filename"])

        weighted_activities = []
        activities = []

        download_dict = {os.path.basename(d): d for d in download_paths}

        for activity in scenario_detail.get("activities", []):
            activities.append(self.__create_activity(activity, download_dict))
        for activity in scenario_detail.get("weighted_activities", []):
            weighted_activities.append(self.__create_activity(activity, download_dict))

        scenario = Scenario(
            uuid=original_scenario.uuid,
            name=original_scenario.name,
            description=original_scenario.description,
            extent=original_scenario.extent,
            activities=activities,
            weighted_activities=weighted_activities,
            priority_layer_groups=scenario_detail.get("priority_layer_groups", []),
            server_uuid=original_scenario.server_uuid,
        )
        return scenario

    def __validate_output_paths(self, download_paths):
        """Validate whether all output paths exist.

        :param download_paths: Output file paths
        :type download_paths: list
        :return: True if all paths exist
        :rtype: bool
        """
        invalid_indexes = []
        for idx, path in enumerate(download_paths):
            if not os.path.exists(path):
                invalid_indexes.append(idx)
        return len(invalid_indexes) == 0, invalid_indexes

    def fetch_scenario_output(
        self, original_scenario, scenario_detail, output_list, scenario_directory
    ):
        """Fetch scenario outputs from API.

        :param original_scenario: Original scenario
        :type original_scenario: Scenario
        :param scenario_detail: scenario detail dictionary
        :type scenario_detail: dict
        :param output_list: Scenario output list from API
        :type output_list: dict
        :param scenario_directory: dictionary that contains outputs from API
        :type scenario_directory: dict
        """
        if not scenario_detail:
            return None, None
        self.total_file_output = len(output_list["results"])
        self.downloaded_output = 0

        urls_to_download = []
        download_paths = []
        final_output = None
        for output in output_list["results"]:
            urls_to_download.append(output["url"])
            if output["is_final_output"]:
                download_path = os.path.join(scenario_directory, output["filename"])
                final_output_path = download_path
                final_output = output["output_meta"]
                final_output["OUTPUT"] = final_output_path
            else:
                download_path = os.path.join(
                    scenario_directory, output["group"], output["filename"]
                )
            download_paths.append(download_path)

        download_paths_copy = copy.deepcopy(download_paths)
        while len(urls_to_download) > 0:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=3 if os.cpu_count() > 3 else 1
            ) as executor:
                executor.map(self.download_file, urls_to_download, download_paths_copy)
            if self.is_download_cancelled():
                return None, None
            is_valid, invalid_indexes = self.__validate_output_paths(download_paths)
            urls_to_download = [urls_to_download[idx] for idx in invalid_indexes]
            download_paths_copy = [download_paths_copy[idx] for idx in invalid_indexes]

        if not self.__validate_output_paths(download_paths):
            return None, None

        scenario = self.__create_scenario(
            original_scenario, scenario_detail, output_list, download_paths
        )

        scenario_result = ScenarioResult(
            scenario=scenario,
            created_date=self.created_datetime,
            scenario_directory=scenario_directory,
            analysis_output=final_output,
        )
        return scenario, scenario_result
