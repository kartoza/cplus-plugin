# -*- coding: utf-8 -*-
"""
    Handles storage and retrieval of the plugin QgsSettings.
"""

import contextlib
import dataclasses
import datetime
import enum
import json
import os.path
import typing
import uuid
from pathlib import Path

from qgis.PyQt import QtCore
from qgis.core import QgsSettings

from .definitions.constants import (
    STYLE_ATTRIBUTE,
    NCS_CARBON_SEGMENT,
    NCS_PATHWAY_SEGMENT,
    NPV_COLLECTION_PROPERTY,
    MASK_PATHS_SEGMENT,
    PATH_ATTRIBUTE,
    PATHWAYS_ATTRIBUTE,
    PIXEL_VALUE_ATTRIBUTE,
    PRIORITY_LAYERS_SEGMENT,
    UUID_ATTRIBUTE,
)
from .definitions.defaults import PRIORITY_LAYERS
from cplus_core.models.base import (
    Activity,
    NcsPathway,
    Scenario,
    ScenarioResult,
    SpatialExtent,
)
from .models.financial import ActivityNpvCollection
from .models.helpers import (
    activity_npv_collection_to_dict,
    create_activity,
    create_activity_npv_collection,
    create_ncs_pathway,
    layer_component_to_dict,
    ncs_pathway_to_dict,
)
from .utils import log, todict, CustomJsonEncoder


@contextlib.contextmanager
def qgis_settings(group_root: str, settings=None):
    """Context manager to help defining groups when creating QgsSettings.

    :param group_root: Name of the root group for the settings
    :type group_root: str

    :param settings: QGIS settings to use
    :type settings: QgsSettings

    :yields: Instance of the created settings
    :ytype: QgsSettings
    """
    if settings is None:
        settings = QgsSettings()
    settings.beginGroup(group_root)
    try:
        yield settings
    finally:
        settings.endGroup()


@dataclasses.dataclass
class ScenarioSettings(Scenario):
    """Plugin Scenario settings."""

    @classmethod
    def from_qgs_settings(cls, identifier: str, settings: QgsSettings):
        """Reads QGIS settings and parses them into a scenario
        settings instance with the respective settings values as properties.

        :param identifier: Scenario identifier
        :type identifier: str

        :param settings: Scenario identifier
        :type settings: QgsSettings

        :returns: Scenario settings object
        :rtype: ScenarioSettings
        """

        activities_list = settings.value("activities", [])
        weighted_activities_list = settings.value("activities", [])
        server_uuid = settings.value("server_uuid", None)

        activities = []

        weighted_activities = []

        try:
            for activity in activities_list:
                setting_activity = json.loads(activity)

                saved_activity = settings_manager.get_activity(
                    setting_activity.get("uuid")
                )
                if saved_activity is None:
                    continue

                for pathways in setting_activity[PATHWAYS_ATTRIBUTE]:
                    for path_uuid, path in pathways.items():
                        pathway = settings_manager.get_ncs_pathway(path_uuid)
                        if pathway:
                            pathway.path = path
                            saved_activity.add_ncs_pathway(pathway)

                saved_activity.path = setting_activity.get("path")
                activities.append(saved_activity)

            for activity in weighted_activities_list:
                setting_activity = json.loads(activity)

                saved_activity = settings_manager.get_activity(
                    setting_activity.get("uuid")
                )
                if saved_activity is None:
                    continue

                for pathways in setting_activity[PATHWAYS_ATTRIBUTE]:
                    for path_uuid, path in pathways.items():
                        pathway = settings_manager.get_ncs_pathway(path_uuid)
                        if pathway:
                            pathway.path = path
                            saved_activity.add_ncs_pathway(pathway)

                saved_activity.path = setting_activity.get("path")
                weighted_activities.append(saved_activity)
        except Exception as e:
            log(f"Problem fetching saved activities, {e}")

        return cls(
            uuid=uuid.UUID(identifier),
            name=settings.value("name", None),
            description=settings.value("description", None),
            extent=[],
            activities=activities,
            weighted_activities=weighted_activities,
            priority_layer_groups=[],
            server_uuid=uuid.UUID(server_uuid) if server_uuid else None,
        )

    @classmethod
    def get_scenario_extent(cls, identifier):
        """Fetches Scenario extent from
         the passed scenario settings.


        :returns: Spatial extent instance extent
        :rtype: SpatialExtent
        """
        spatial_key = (
            f"{settings_manager._get_scenario_settings_base(identifier)}/extent/spatial"
        )

        with qgis_settings(spatial_key) as settings:
            bbox = settings.value("bbox", None)
            bbox = [float(b) for b in bbox]
            spatial_extent = SpatialExtent(bbox=bbox)

        return spatial_extent


class Settings(enum.Enum):
    """Plugin settings names"""

    DOWNLOAD_FOLDER = "download_folder"
    REFRESH_FREQUENCY = "refresh/period"
    REFRESH_FREQUENCY_UNIT = "refresh/unit"
    REFRESH_LAST_UPDATE = "refresh/last_update"
    REFRESH_STATE = "refresh/state"

    # Report settings
    REPORT_ORGANIZATION = "report/organization"
    REPORT_CONTACT_EMAIL = "report/email"
    REPORT_WEBSITE = "report/website"
    REPORT_CUSTOM_LOGO = "report/custom_logo"
    REPORT_CPLUS_LOGO = "report/cplus_logo"
    REPORT_CI_LOGO = "report/ci_logo"
    REPORT_LOGO_DIR = "report/logo_dir"
    REPORT_FOOTER = "report/footer"
    REPORT_DISCLAIMER = "report/disclaimer"
    REPORT_LICENSE = "report/license"
    REPORT_STAKEHOLDERS = "report/stakeholders"
    REPORT_CULTURE_POLICIES = "report/culture_policies"
    REPORT_CULTURE_CONSIDERATIONS = "report/culture_considerations"

    # Last selected data directory
    LAST_DATA_DIR = "last_data_dir"
    LAST_MASK_DIR = "last_mask_dir"

    # Advanced settings
    BASE_DIR = "advanced/base_dir"

    # Scenario basic details
    SCENARIO_NAME = "scenario_name"
    SCENARIO_DESCRIPTION = "scenario_description"
    SCENARIO_EXTENT = "scenario_extent"

    # Coefficient for carbon layers
    CARBON_COEFFICIENT = "carbon_coefficient"

    # Pathway suitability index value
    PATHWAY_SUITABILITY_INDEX = "pathway_suitability_index"

    # Snapping values
    SNAPPING_ENABLED = "snapping_enabled"
    SNAP_LAYER = "snap_layer"
    ALLOW_RESAMPLING = "snap_resampling"
    RESCALE_VALUES = "snap_rescale"
    RESAMPLING_METHOD = "snap_method"
    SNAP_PIXEL_VALUE = "snap_pixel_value"

    # Sieve function parameters
    SIEVE_ENABLED = "sieve_enabled"
    SIEVE_THRESHOLD = "sieve_threshold"
    SIEVE_MASK_PATH = "mask_path"

    # Mask layer
    MASK_LAYERS_PATHS = "mask_layers_paths"

    # Outputs options
    NCS_WITH_CARBON = "ncs_with_carbon"
    LANDUSE_PROJECT = "landuse_project"
    LANDUSE_NORMALIZED = "landuse_normalized"
    LANDUSE_WEIGHTED = "landuse_weighted"
    HIGHEST_POSITION = "highest_position"

    # Processing option
    PROCESSING_TYPE = "processing_type"

    # DEBUG
    DEBUG = "debug"
    BASE_API_URL = "base_api_url"

    ACTIVE_ONLINE_TASK = "active_online_task"


class SettingsManager(QtCore.QObject):
    """Manages saving/loading settings for the plugin in QgsSettings."""

    BASE_GROUP_NAME: str = "cplus_plugin"
    SCENARIO_GROUP_NAME: str = "scenarios"
    SCENARIO_RESULTS_GROUP_NAME: str = "scenarios_results"
    PRIORITY_GROUP_NAME: str = "priority_groups"
    PRIORITY_LAYERS_GROUP_NAME: str = "priority_layers"
    NCS_PATHWAY_BASE: str = "ncs_pathways"
    LAYER_MAPPING_BASE: str = "layer_mapping"
    SERVER_DEFAULT_LAYERS: str = "default_layers"
    ONLINE_TASK_BASE: str = "online_task"

    ACTIVITY_BASE: str = "activities"

    settings = QgsSettings()

    scenarios_settings_updated = QtCore.pyqtSignal()
    priority_layers_changed = QtCore.pyqtSignal()
    settings_updated = QtCore.pyqtSignal([str, object], [Settings, object])

    def set_value(self, name: str, value):
        """Adds a new setting key and value on the plugin specific settings.

        :param name: Name of setting key
        :type name: str

        :param value: Value of the setting
        :type value: Any
        """
        self.settings.setValue(f"{self.BASE_GROUP_NAME}/{name}", value)
        if isinstance(name, Settings):
            name = name.value

        self.settings_updated.emit(name, value)

    def get_value(self, name: str, default=None, setting_type=None):
        """Gets value of the setting with the passed name.

        :param name: Name of setting key
        :type name: str

        :param default: Default value returned when the setting key does not exist
        :type default: Any

        :param setting_type: Type of the store setting
        :type setting_type: Any

        :returns: Value of the setting
        :rtype: Any
        """
        if setting_type:
            return self.settings.value(
                f"{self.BASE_GROUP_NAME}/{name}", default, setting_type
            )
        return self.settings.value(f"{self.BASE_GROUP_NAME}/{name}", default)

    def find_settings(self, name):
        """Returns the plugin setting keys from the
         plugin root group that matches the passed name

        :param name: Setting name to search for
        :type name: str

        :returns result: List of the matching settings names
        :rtype result: list
        """

        result = []
        with qgis_settings(f"{self.BASE_GROUP_NAME}") as settings:
            for settings_name in settings.childKeys():
                if name in settings_name:
                    result.append(settings_name)
        return result

    def remove(self, name):
        """Remove the setting with the specified name.

        :param name: Name of the setting key
        :type name: str
        """
        self.settings.remove(f"{self.BASE_GROUP_NAME}/{name}")

    def delete_settings(self):
        """Deletes the all the plugin settings."""
        self.settings.remove(f"{self.BASE_GROUP_NAME}")

    def _get_scenario_settings_base(self, identifier):
        """Gets the scenario settings base url.

        :param identifier: Scenario settings identifier
        :type identifier: uuid.UUID

        :returns: Scenario settings base group
        :rtype: str
        """
        return (
            f"{self.BASE_GROUP_NAME}/"
            f"{self.SCENARIO_GROUP_NAME}/"
            f"{str(identifier)}"
        )

    def _get_scenario_results_settings_base(self, identifier):
        """Gets the scenario results settings base url.

        :param identifier: Scenario identifier
        :type identifier: uuid.UUID

        :returns: Scenario settings base group
        :rtype: str
        """
        return (
            f"{self.BASE_GROUP_NAME}/"
            f"{self.SCENARIO_RESULTS_GROUP_NAME}/"
            f"{str(identifier)}"
        )

    def save_scenario(self, scenario_settings):
        """Save the passed scenario settings into the plugin settings

        :param scenario_settings: Scenario settings
        :type scenario_settings: ScenarioSettings
        """
        settings_key = self._get_scenario_settings_base(scenario_settings.uuid)
        self.save_scenario_extent(settings_key, scenario_settings.extent)

        activities = []
        weighted_activities = []

        for activity in scenario_settings.activities:
            if isinstance(activity, Activity):
                priority_layers = activity.priority_layers
                layer_styles = activity.layer_styles
                style_pixel_value = activity.style_pixel_value

                ncs_pathways = []
                for ncs in activity.pathways:
                    ncs_pathways.append({str(ncs.uuid): ncs.path})

                activity = layer_component_to_dict(activity)
                activity[PRIORITY_LAYERS_SEGMENT] = priority_layers
                activity[PATHWAYS_ATTRIBUTE] = ncs_pathways
                activity[STYLE_ATTRIBUTE] = layer_styles
                activity[PIXEL_VALUE_ATTRIBUTE] = style_pixel_value

                activities.append(json.dumps(activity))

        for activity in scenario_settings.weighted_activities:
            if isinstance(activity, Activity):
                priority_layers = activity.priority_layers
                layer_styles = activity.layer_styles
                style_pixel_value = activity.style_pixel_value

                ncs_pathways = []
                for ncs in activity.pathways:
                    ncs_pathways.append({str(ncs.uuid): ncs.path})

                activity = layer_component_to_dict(activity)
                activity[PRIORITY_LAYERS_SEGMENT] = priority_layers
                activity[PATHWAYS_ATTRIBUTE] = ncs_pathways
                activity[STYLE_ATTRIBUTE] = layer_styles
                activity[PIXEL_VALUE_ATTRIBUTE] = style_pixel_value

                weighted_activities.append(json.dumps(activity))

        with qgis_settings(settings_key) as settings:
            settings.setValue("uuid", str(scenario_settings.uuid))
            settings.setValue("name", scenario_settings.name)
            settings.setValue("description", scenario_settings.description)
            settings.setValue("activities", activities)
            settings.setValue("weighted_activities", weighted_activities)
            settings.setValue(
                "server_uuid",
                str(scenario_settings.server_uuid)
                if scenario_settings.server_uuid
                else None,
            )

    def save_scenario_extent(self, key, extent):
        """Saves the scenario extent into plugin settings
        using the provided settings group key.

        :param key: QgsSettings group key
        :type key: str

        :param extent: Scenario extent
        :type extent: SpatialExtent

        Args:
            extent (SpatialExtent): Scenario extent
            key (str): QgsSettings group key
        """
        spatial_extent = extent.bbox

        spatial_key = f"{key}/extent/spatial/"
        with qgis_settings(spatial_key) as settings:
            settings.setValue("bbox", spatial_extent)

    # def get_scenario(self, identifier):
    #     """Retrieves the scenario that matches the passed identifier.
    #
    #     :param identifier: Scenario identifier
    #     :type identifier: str
    #
    #     :returns: Scenario settings instance
    #     :rtype: ScenarioSettings
    #     """
    #
    #     settings_key = self._get_scenario_settings_base(identifier)
    #     with qgis_settings(settings_key) as settings:
    #         scenario_settings = ScenarioSettings.from_qgs_settings(
    #             str(identifier), settings
    #         )
    #     return scenario_settings

    def get_scenario(self, scenario_id):
        """Retrieves the first scenario that matched the passed scenario id.

        :param scenario_id: Scenario id
        :type scenario_id: str

        :returns: Scenario settings instance
        :rtype: ScenarioSettings
        """

        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_GROUP_NAME}"
        ) as settings:
            for scenario_uuid in settings.childGroups():
                scenario_settings_key = self._get_scenario_settings_base(scenario_uuid)
                with qgis_settings(scenario_settings_key) as scenario_settings:
                    if scenario_uuid == scenario_id:
                        scenario = ScenarioSettings.from_qgs_settings(
                            scenario_uuid, scenario_settings
                        )

                        scenario.extent = scenario.get_scenario_extent(scenario_uuid)
                        return scenario
        return None

    def get_scenarios(self):
        """Gets all the available scenarios settings in the plugin.

        :returns: List of the scenario settings instances
        :rtype: list
        """
        result = []
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_GROUP_NAME}"
        ) as settings:
            for scenario_uuid in settings.childGroups():
                scenario_settings_key = self._get_scenario_settings_base(scenario_uuid)
                with qgis_settings(scenario_settings_key) as scenario_settings:
                    scenario = ScenarioSettings.from_qgs_settings(
                        scenario_uuid, scenario_settings
                    )
                    scenario.extent = scenario.get_scenario_extent(scenario_uuid)
                    result.append(scenario)
        return result

    def delete_scenario(self, scenario_id):
        """Delete the scenario with the passed scenarion id.

        :param scenario_id: Scenario identifier
        :type scenario_id: str
        """

        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_GROUP_NAME}"
        ) as settings:
            for scenario_identifier in settings.childGroups():
                if str(scenario_identifier) == str(scenario_id):
                    settings.remove(scenario_identifier)

    def delete_online_scenario(self):
        """Delete online scenario from QGIS settings"""

        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_GROUP_NAME}"
        ) as settings:
            for scenario_identifier in settings.childGroups():
                scenario = settings_manager.get_scenario(scenario_identifier)
                if scenario.server_uuid:
                    settings_manager.delete_scenario_result(scenario_identifier)
                    settings_manager.delete_scenario(scenario_identifier)

    def delete_all_scenarios(self):
        """Deletes all the plugin scenarios settings."""
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_GROUP_NAME}"
        ) as settings:
            for scenario_name in settings.childGroups():
                settings.remove(scenario_name)

    def save_scenario_result(self, scenario_result, scenario_id):
        """Save the scenario results plugin settings

        :param scenario_settings: Scenario settings
        :type scenario_settings: ScenarioSettings
        """
        settings_key = self._get_scenario_results_settings_base(scenario_id)

        analysis_output = json.dumps(scenario_result.analysis_output)

        with qgis_settings(settings_key) as settings:
            settings.setValue("scenario_id", scenario_id)
            settings.setValue(
                "created_date",
                scenario_result.created_date.strftime("%Y_%m_%d_%H_%M_%S"),
            )
            settings.setValue("analysis_output", analysis_output)
            settings.setValue("output_layer_name", scenario_result.output_layer_name)
            settings.setValue("scenario_directory", scenario_result.scenario_directory)

    def get_scenario_result(self, scenario_id):
        """Retrieves the scenario result that matched the passed scenario id.

        :param scenario_id: Scenario id
        :type scenario_id: str

        :returns: Scenario result
        :rtype: ScenarioSettings
        """

        scenario_settings_key = self._get_scenario_results_settings_base(scenario_id)
        with qgis_settings(scenario_settings_key) as scenario_settings:
            created_date = scenario_settings.value("created_date")
            analysis_output = scenario_settings.value("analysis_output")
            output_layer_name = scenario_settings.value("output_layer_name")
            scenario_directory = scenario_settings.value("scenario_directory")
            if analysis_output is None:
                return None
            try:
                created_date = datetime.datetime.strptime(
                    created_date, "%Y_%m_%d_%H_%M_%S"
                )
                analysis_output = json.loads(analysis_output)
            except Exception as e:
                log(f"Problem fetching scenario result, {e}")
                return None

            return ScenarioResult(
                scenario=None,
                created_date=created_date,
                analysis_output=analysis_output,
                output_layer_name=output_layer_name,
                scenario_directory=scenario_directory,
            )
        return None

    def get_scenarios_results(self):
        """Gets all the saved scenarios results.

        :returns: List of the scenario results
        :rtype: list
        """
        result = []
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/{self.SCENARIO_RESULTS_GROUP_NAME}"
        ) as settings:
            for uuid in settings.childGroups():
                scenario_settings_key = self._get_scenario_results_settings_base(uuid)
                with qgis_settings(scenario_settings_key) as scenario_settings:
                    created_date = scenario_settings.value("created_date")
                    analysis_output = scenario_settings.value("analysis_output")
                    output_layer_name = scenario_settings.value("output_layer_name")
                    scenario_directory = scenario_settings.value("scenario_directory")

                    try:
                        created_date = datetime.datetime.strptime(
                            created_date, "%Y_%m_%d_%H_%M_%S"
                        )
                        analysis_output = json.loads(analysis_output)
                    except Exception as e:
                        log(f"Problem fetching scenario result, {e}")
                        return None

                    result.append(
                        ScenarioResult(
                            scenario=None,
                            created_date=created_date,
                            analysis_output=analysis_output,
                            output_layer_name=output_layer_name,
                            scenario_directory=scenario_directory,
                        )
                    )
        return result

    def delete_scenario_result(self, scenario_id):
        """Delete the scenario result that contains the scenario id.

        :param scenario_id: Scenario identifier
        :type scenario_id: str
        """

        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.SCENARIO_RESULTS_GROUP_NAME}"
        ) as settings:
            for scenario_identifier in settings.childGroups():
                if str(scenario_identifier) == str(scenario_id):
                    settings.remove(scenario_identifier)

    def delete_all_scenarios_results(self):
        """Deletes all the plugin scenarios results settings."""
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/{self.SCENARIO_GROUP_NAME}/"
            f"{self.SCENARIO_RESULTS_GROUP_NAME}"
        ) as settings:
            for scenario_result in settings.childGroups():
                settings.remove(scenario_result)

    def _get_priority_layers_settings_base(self, identifier) -> str:
        """Gets the priority layers settings base url.

        :param identifier: Priority layers settings identifier
        :type identifier: uuid.UUID

        :returns: Priority layers settings base group
        :rtype: str
        """
        return (
            f"{self.BASE_GROUP_NAME}/"
            f"{self.PRIORITY_LAYERS_GROUP_NAME}/"
            f"{str(identifier)}"
        )

    def get_priority_layer(self, identifier) -> typing.Dict:
        """Retrieves the priority layer that matches the passed identifier.

        :param identifier: Priority layers identifier
        :type identifier: uuid.UUID

        :returns: Priority layer dict
        :rtype: dict
        """
        priority_layer = None

        settings_key = self._get_priority_layers_settings_base(identifier)
        with qgis_settings(settings_key) as settings:
            groups_key = f"{settings_key}/groups"
            groups = []

            if len(settings.childKeys()) <= 0:
                return priority_layer

            with qgis_settings(groups_key) as groups_settings:
                for name in groups_settings.childGroups():
                    group_settings_key = f"{groups_key}/{name}"
                    with qgis_settings(group_settings_key) as group_settings:
                        stored_group = {}
                        stored_group["uuid"] = group_settings.value("uuid")
                        stored_group["name"] = group_settings.value("name")
                        stored_group["value"] = group_settings.value("value")
                        groups.append(stored_group)

            priority_layer = {"uuid": str(identifier)}
            priority_layer["name"] = settings.value("name")
            priority_layer["description"] = settings.value("description")
            priority_layer["path"] = settings.value("path")
            priority_layer["selected"] = settings.value("selected", type=bool)
            priority_layer["user_defined"] = settings.value(
                "user_defined", defaultValue=True, type=bool
            )
            priority_layer["type"] = settings.value("type", defaultValue=0, type=int)
            priority_layer["groups"] = groups
        return priority_layer

    def get_priority_layers(self) -> typing.List:
        """Gets all the available priority layers in the plugin.

        :returns: Priority layers list
        :rtype: list
        """
        priority_layer_list = []
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}"
        ) as settings:
            for uuid in settings.childGroups():
                priority_layer_settings = self._get_priority_layers_settings_base(uuid)
                with qgis_settings(priority_layer_settings) as priority_settings:
                    groups_key = f"{priority_layer_settings}/groups"
                    groups = []

                    with qgis_settings(groups_key) as groups_settings:
                        for name in groups_settings.childGroups():
                            group_settings_key = f"{groups_key}/{name}"
                            with qgis_settings(group_settings_key) as group_settings:
                                stored_group = {}
                                stored_group["uuid"] = group_settings.value("uuid")
                                stored_group["name"] = group_settings.value("name")
                                stored_group["value"] = group_settings.value("value")
                                groups.append(stored_group)
                    layer = {
                        "uuid": uuid,
                        "name": priority_settings.value("name"),
                        "description": priority_settings.value("description"),
                        "path": priority_settings.value("path"),
                        "selected": priority_settings.value("selected", type=bool),
                        "user_defined": priority_settings.value(
                            "user_defined", defaultValue=True, type=bool
                        ),
                        "type": priority_settings.value(
                            "type", defaultValue=0, type=int
                        ),
                        "groups": groups,
                    }
                    priority_layer_list.append(layer)
        return priority_layer_list

    def find_layer_by_name(self, name) -> typing.Dict:
        """Finds a priority layer setting inside
        the plugin QgsSettings by name.

        :param name: Priority layers identifier
        :type name: str

        :returns: Priority layers dict
        :rtype: dict
        """
        found_id = None
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}"
        ) as settings:
            for layer_id in settings.childGroups():
                layer_settings_key = self._get_priority_layers_settings_base(layer_id)
                with qgis_settings(layer_settings_key) as layer_settings:
                    layer_name = layer_settings.value("name")
                    if layer_name == name:
                        found_id = uuid.UUID(layer_id)
                        break

        return self.get_priority_layer(found_id) if found_id is not None else None

    def find_layers_by_group(self, group) -> typing.List:
        """Finds priority layers inside the plugin QgsSettings
         that contain the passed group.

        :param group: Priority group name
        :type group: str

        :returns: Priority layers list
        :rtype: list
        """
        layers = []
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}"
        ) as settings:
            for layer_id in settings.childGroups():
                priority_layer_settings = self._get_priority_layers_settings_base(
                    layer_id
                )
                with qgis_settings(priority_layer_settings) as priority_settings:
                    groups_key = f"{priority_layer_settings}/groups"

                    with qgis_settings(groups_key) as groups_settings:
                        for name in groups_settings.childGroups():
                            group_settings_key = f"{groups_key}/{name}"
                            with qgis_settings(group_settings_key) as group_settings:
                                if group == group_settings.value("name"):
                                    layers.append(self.get_priority_layer(layer_id))
        return layers

    def save_priority_layer(self, priority_layer):
        """Save the priority layer into the plugin settings.
        Updates the layer with new priority groups.

        Note: Emits priority_layers_changed signal

        :param priority_layer: Priority layer
        :type priority_layer: dict
        """
        settings_key = self._get_priority_layers_settings_base(priority_layer["uuid"])

        with qgis_settings(settings_key) as settings:
            groups = priority_layer.get("groups", [])
            settings.setValue("name", priority_layer["name"])
            settings.setValue("description", priority_layer["description"])
            settings.setValue("path", priority_layer["path"])
            settings.setValue("selected", priority_layer.get("selected", False))
            settings.setValue("user_defined", priority_layer.get("user_defined", True))
            settings.setValue("type", priority_layer.get("type", 0))
            groups_key = f"{settings_key}/groups"
            with qgis_settings(groups_key) as groups_settings:
                for group_id in groups_settings.childGroups():
                    groups_settings.remove(group_id)
            for group in groups:
                group_key = f"{groups_key}/{group['name']}"
                with qgis_settings(group_key) as group_settings:
                    group_settings.setValue("uuid", str(group.get("uuid")))
                    group_settings.setValue("name", group["name"])
                    group_settings.setValue("value", group["value"])

        self.priority_layers_changed.emit()

    def set_current_priority_layer(self, identifier):
        """Set current priority layer

        :param identifier: Priority layer identifier
        :type identifier: str
        """
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}/"
        ) as settings:
            for priority_layer in settings.childGroups():
                settings_key = self._get_priority_layers_settings_base(identifier)
                with qgis_settings(settings_key) as layer_settings:
                    layer_settings.setValue(
                        "selected", str(priority_layer) == str(identifier)
                    )

    def delete_priority_layers(self):
        """Deletes all the plugin priority weighting layers settings."""
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}"
        ) as settings:
            for priority_layer in settings.childGroups():
                settings.remove(priority_layer)

    def delete_priority_layer(self, identifier):
        """Removes priority layer that match the passed identifier

        :param identifier: Priority layer identifier
        :type identifier: str
        """
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_LAYERS_GROUP_NAME}/"
        ) as settings:
            for priority_layer in settings.childGroups():
                if str(priority_layer) == str(identifier):
                    settings.remove(priority_layer)

    def _get_priority_groups_settings_base(self, identifier) -> str:
        """Gets the priority group settings base url.

        :param identifier: Priority group settings identifier
        :type identifier: str

        :returns: Priority groups settings base group
        :rtype: str

        """
        return (
            f"{self.BASE_GROUP_NAME}/"
            f"{self.PRIORITY_GROUP_NAME}/"
            f"{str(identifier)}"
        )

    def find_group_by_name(self, name) -> typing.Dict:
        """Finds a priority group setting inside the plugin QgsSettings by name.

        :param name: Name of the group
        :type name: str

        :returns: Priority group
        :rtype: typing.Dict
        """

        found_id = None

        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_GROUP_NAME}"
        ) as settings:
            for group_id in settings.childGroups():
                group_settings_key = self._get_priority_groups_settings_base(group_id)
                with qgis_settings(group_settings_key) as group_settings_key:
                    group_name = group_settings_key.value("name")
                    if group_name == name:
                        found_id = uuid.UUID(group_id)
                        break

        return self.get_priority_group(found_id)

    def get_priority_group(self, identifier) -> typing.Dict:
        """Retrieves the priority group that matches the passed identifier.

        :param identifier: Priority group identifier
        :type identifier: str

        :returns: Priority group
        :rtype: typing.Dict
        """

        if identifier is None:
            return None

        settings_key = self._get_priority_groups_settings_base(identifier)
        with qgis_settings(settings_key) as settings:
            priority_group = {"uuid": identifier}
            priority_group["name"] = settings.value("name")
            priority_group["value"] = settings.value("value")
            priority_group["description"] = settings.value("description")
        return priority_group

    def get_priority_groups(self) -> typing.List[typing.Dict]:
        """Gets all the available priority groups in the plugin.

        :returns: List of the priority groups instances
        :rtype: list
        """
        priority_groups = []
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_GROUP_NAME}"
        ) as settings:
            for uuid in settings.childGroups():
                priority_layer_settings = self._get_priority_groups_settings_base(uuid)
                with qgis_settings(priority_layer_settings) as priority_settings:
                    group = {
                        "uuid": uuid,
                        "name": priority_settings.value("name"),
                        "value": priority_settings.value("value"),
                        "description": priority_settings.value("description"),
                    }
                    priority_groups.append(group)
        return priority_groups

    def save_priority_group(self, priority_group):
        """Save the priority group into the plugin settings

        :param priority_group: Priority group
        :type priority_group: str
        """

        settings_key = self._get_priority_groups_settings_base(priority_group["uuid"])

        with qgis_settings(settings_key) as settings:
            settings.setValue("name", priority_group["name"])
            settings.setValue("value", priority_group["value"])
            settings.setValue("description", priority_group.get("description"))

    def delete_priority_group(self, identifier):
        """Removes priority group that match the passed identifier

        :param identifier: Priority group identifier
        :type identifier: str
        """
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_GROUP_NAME}/"
        ) as settings:
            for priority_group in settings.childGroups():
                if str(priority_group) == str(identifier):
                    settings.remove(priority_group)

    def delete_priority_groups(self):
        """Deletes all the plugin priority groups settings."""
        with qgis_settings(
            f"{self.BASE_GROUP_NAME}/" f"{self.PRIORITY_GROUP_NAME}"
        ) as settings:
            for priority_group in settings.childGroups():
                settings.remove(priority_group)

    def _get_layer_mappings_settings_base(self) -> str:
        """Returns the path for Layer Mapping settings.

        :return: Base path to Layer Mapping group.
        :rtype: str
        """
        return f"{self.BASE_GROUP_NAME}/{self.LAYER_MAPPING_BASE}"

    def get_all_layer_mapping(self) -> typing.Dict:
        """Return all layer mapping.

        :return: All layer mapping
        :rtype: dict
        """
        layer_mapping = {}

        layer_mapping_root = self._get_layer_mappings_settings_base()
        with qgis_settings(layer_mapping_root) as settings:
            keys = settings.childKeys()
            for k in keys:
                layer_raw = settings.value(k, dict())
                if len(layer_raw) > 0:
                    try:
                        layer = json.loads(layer_raw)
                        layer_mapping[k] = layer
                    except json.JSONDecodeError:
                        log("Layer Mapping JSON is invalid")
        return layer_mapping

    def get_layer_mapping(self, identifier: str) -> typing.Dict:
        """Retrieves the layer mapping that matches the passed identifier.

        :param identifier: Layer mapping identifier
        :type identifier: str path

        :return: Layer mapping
        :rtype: typing.Dict
        """

        layer_mapping = {}

        layer_mapping_root = self._get_layer_mappings_settings_base()

        with qgis_settings(layer_mapping_root) as settings:
            layer = settings.value(identifier, dict())
            if len(layer) > 0:
                try:
                    layer_mapping = json.loads(layer)
                except json.JSONDecodeError:
                    log("Layer Mapping JSON is invalid")
        return layer_mapping

    def save_layer_mapping(self, input_layer: dict, identifier: str = None):
        """Save the layer mapping into the plugin settings

        :param input_layer: Layer mapping
        :type input_layer: dict
        :param identifier: file identifier using path
        :type identifier: str
        """

        if not identifier:
            identifier = input_layer["path"].replace(os.sep, "--")
        settings_key = self._get_layer_mappings_settings_base()

        with qgis_settings(settings_key) as settings:
            settings.setValue(identifier, json.dumps(input_layer))

    def remove_layer_mapping(self, identifier: str):
        """Remove layer mapping from settings."""
        self.remove(f"{self.LAYER_MAPPING_BASE}/{identifier}")

    def _get_default_layers_settings_base(self) -> str:
        """Returns the path for Default Layers settings.

        :returns: Base path to Default Layers group.
        :rtype: str
        """
        return f"{self.BASE_GROUP_NAME}/{self.SERVER_DEFAULT_LAYERS}"

    def get_default_layers(self, layer_type: str, as_dict=False) -> typing.List[dict]:
        """Returns list of default layers by type.

        :param layer_type: ncs_pathway, priority_layer, or ncs_carbon
        :type layer_type: str
        :return: List of dictionary of ncs pathway
        :rtype: typing.List[dict]
        """
        layers = []
        default_layers_root = self._get_default_layers_settings_base()
        with qgis_settings(default_layers_root) as settings:
            layers_str = settings.value(layer_type, "")
            if layers_str:
                try:
                    layers = json.loads(layers_str)
                except json.JSONDecodeError:
                    log("Layers JSON is invalid")
        if as_dict:
            if layer_type == "ncs_carbon":
                layers = {
                    f"{layer['layer_uuid']}/{layer['name']}": layer for layer in layers
                }
            else:
                layers = {layer["layer_uuid"]: layer for layer in layers}
        return layers

    def save_default_layers(self, type: str, layers: typing.List):
        """Save default layers by type

        :param type: ncs_pathway, priority_layer, or ncs_carbon
        :type type: str
        :param layers: layer list
        :type layers: typing.List
        """
        default_layers_root = self._get_default_layers_settings_base()

        with qgis_settings(default_layers_root) as settings:
            settings.setValue(type, json.dumps(layers))

    def remove_default_layers(self):
        """Remove default layers from settings."""
        default_layers_root = self._get_default_layers_settings_base()
        self.remove(default_layers_root)

    def _get_ncs_pathway_settings_base(self) -> str:
        """Returns the path for NCS pathway settings.

        :returns: Base path to NCS pathway group.
        :rtype: str
        """
        return f"{self.BASE_GROUP_NAME}/" f"{NCS_PATHWAY_SEGMENT}"

    def save_ncs_pathway(self, ncs_pathway: typing.Union[NcsPathway, dict]):
        """Saves an NCS pathway object serialized to a json string
        indexed by the UUID.

        :param ncs_pathway: NCS pathway object or attribute values
        in a dictionary which are then serialized to a JSON string.
        :type ncs_pathway: NcsPathway, dict
        """
        if isinstance(ncs_pathway, NcsPathway):
            ncs_pathway = ncs_pathway_to_dict(ncs_pathway)

        ncs_str = json.dumps(ncs_pathway)

        ncs_uuid = ncs_pathway[UUID_ATTRIBUTE]
        ncs_root = self._get_ncs_pathway_settings_base()

        with qgis_settings(ncs_root) as settings:
            settings.setValue(ncs_uuid, ncs_str)

    def get_ncs_pathway(self, ncs_uuid: str) -> typing.Union[NcsPathway, None]:
        """Gets an NCS pathway object matching the given unique identified.

        :param ncs_uuid: Unique identifier for the NCS pathway object.
        :type ncs_uuid: str

        :returns: Returns the NCS pathway object matching the given
        identifier else None if not found.
        :rtype: NcsPathway
        """
        ncs_pathway = None

        ncs_dict = self.get_ncs_pathway_dict(ncs_uuid)
        if len(ncs_dict) == 0:
            return None

        ncs_pathway = create_ncs_pathway(ncs_dict)

        return ncs_pathway

    def get_ncs_pathway_dict(self, ncs_uuid: str) -> dict:
        """Gets an NCS pathway attribute values as a dictionary.

        :param ncs_uuid: Unique identifier for the NCS pathway object.
        :type ncs_uuid: str

        :returns: Returns the NCS pathway attribute values matching the given
        identifier else an empty dictionary if not found.
        :rtype: dict
        """
        ncs_pathway_dict = {}

        ncs_root = self._get_ncs_pathway_settings_base()

        with qgis_settings(ncs_root) as settings:
            ncs_model = settings.value(ncs_uuid, dict())
            if len(ncs_model) > 0:
                try:
                    ncs_pathway_dict = json.loads(ncs_model)
                except json.JSONDecodeError:
                    log("NCS pathway JSON is invalid")

        return ncs_pathway_dict

    def get_all_ncs_pathways(self) -> typing.List[NcsPathway]:
        """Get all the NCS pathway objects stored in settings.

        :returns: Returns all the NCS pathway objects.
        :rtype: list
        """
        ncs_pathways = []

        ncs_root = self._get_ncs_pathway_settings_base()

        with qgis_settings(ncs_root) as settings:
            keys = settings.childKeys()
            for k in keys:
                ncs_pathway = self.get_ncs_pathway(k)
                if ncs_pathway is not None:
                    ncs_pathways.append(ncs_pathway)

        return sorted(ncs_pathways, key=lambda ncs: ncs.name)

    def update_ncs_pathways(self):
        """Updates the path attribute of all NCS pathway settings
        based on the BASE_DIR settings to reflect the absolute path
        of each NCS pathway layer.
        If BASE_DIR is empty then the NCS pathway settings will not
        be updated.
        """
        ncs_pathways = self.get_all_ncs_pathways()
        for ncs in ncs_pathways:
            self.update_ncs_pathway(ncs)

    def update_ncs_pathway(self, ncs_pathway: NcsPathway):
        """Updates the attributes of the NCS pathway object
        in settings. On the path, the BASE_DIR in settings
        is used to reflect the absolute path of each NCS
        pathway layer. If BASE_DIR is empty then the NCS
        pathway setting will not be updated, this only applies
        for default pathways.

        :param ncs_pathway: NCS pathway object to be updated.
        :type ncs_pathway: NcsPathway
        """
        base_dir = self.get_value(Settings.BASE_DIR)
        if not base_dir:
            return

        # Pathway location for default pathway
        if not ncs_pathway.user_defined:
            p = Path(ncs_pathway.path)
            # Only update if path does not exist otherwise
            # fallback to check under base directory.
            if not p.exists():
                abs_path = f"{base_dir}/{NCS_PATHWAY_SEGMENT}/" f"{p.name}"
                abs_path = str(os.path.normpath(abs_path))
                ncs_pathway.path = abs_path

            # Carbon location
            abs_carbon_paths = []
            for cb_path in ncs_pathway.carbon_paths:
                cp = Path(cb_path)
                # Similarly, if the given carbon path does not exist then try
                # to use the default one in the ncs_carbon directory.
                if not cp.exists():
                    abs_carbon_path = f"{base_dir}/{NCS_CARBON_SEGMENT}/" f"{cp.name}"
                    abs_carbon_path = str(os.path.normpath(abs_carbon_path))
                    abs_carbon_paths.append(abs_carbon_path)
                else:
                    abs_carbon_paths.append(cb_path)

            ncs_pathway.carbon_paths = abs_carbon_paths

        # Remove then re-insert
        self.remove_ncs_pathway(str(ncs_pathway.uuid))
        self.save_ncs_pathway(ncs_pathway)

    def remove_ncs_pathway(self, ncs_uuid: str):
        """Removes an NCS pathway settings entry using the UUID.

        :param ncs_uuid: Unique identifier of the NCS pathway entry
        to removed.
        :type ncs_uuid: str
        """
        if self.get_ncs_pathway(ncs_uuid) is not None:
            self.remove(f"{self.NCS_PATHWAY_BASE}/{ncs_uuid}")

    def _get_activity_settings_base(self) -> str:
        """Returns the path for activity settings.

        :returns: Base path to activity group.
        :rtype: str
        """
        return f"{self.BASE_GROUP_NAME}/" f"{self.ACTIVITY_BASE}"

    def save_activity(self, activity: typing.Union[Activity, dict]):
        """Saves an activity object serialized to a json string
        indexed by the UUID.

        :param activity: Activity object or attribute
        values in a dictionary which are then serialized to a JSON string.
        :type activity: Activity, dict
        """
        if isinstance(activity, Activity):
            priority_layers = activity.priority_layers
            layer_styles = activity.layer_styles
            style_pixel_value = activity.style_pixel_value
            mask_paths = activity.mask_paths

            ncs_pathways = []
            for ncs in activity.pathways:
                ncs_pathways.append(str(ncs.uuid))

            activity = layer_component_to_dict(activity)
            activity[PRIORITY_LAYERS_SEGMENT] = priority_layers
            activity[MASK_PATHS_SEGMENT] = mask_paths
            activity[PATHWAYS_ATTRIBUTE] = ncs_pathways
            activity[STYLE_ATTRIBUTE] = layer_styles
            activity[PIXEL_VALUE_ATTRIBUTE] = style_pixel_value

        if isinstance(activity, dict):
            priority_layers = []
            if activity.get("pwls_ids") is not None:
                for layer_id in activity.get("pwls_ids", []):
                    layer = self.get_priority_layer(layer_id)
                    priority_layers.append(layer)
                if len(priority_layers) > 0:
                    activity[PRIORITY_LAYERS_SEGMENT] = priority_layers

        activity_str = json.dumps(todict(activity), cls=CustomJsonEncoder)

        activity_uuid = activity[UUID_ATTRIBUTE]
        activity_root = self._get_activity_settings_base()

        with qgis_settings(activity_root) as settings:
            settings.setValue(activity_uuid, activity_str)

    def get_activity(self, activity_uuid: str) -> typing.Union[Activity, None]:
        """Gets an activity object matching the given unique
        identifier.

        :param activity_uuid: Unique identifier of the
        activity object.
        :type activity_uuid: str

        :returns: Returns the activity object matching the given
        identifier else None if not found.
        :rtype: Activity
        """
        activity = None

        activity_root = self._get_activity_settings_base()

        with qgis_settings(activity_root) as settings:
            activity = settings.value(activity_uuid, None)
            ncs_uuids = []
            if activity is not None:
                activity_dict = {}
                try:
                    activity_dict = json.loads(activity)
                except json.JSONDecodeError:
                    log("Activity JSON is invalid.")

                if PATHWAYS_ATTRIBUTE in activity_dict:
                    ncs_uuids = activity_dict[PATHWAYS_ATTRIBUTE]

                activity = create_activity(activity_dict)
                if activity is not None:
                    for ncs_uuid in ncs_uuids:
                        ncs = self.get_ncs_pathway(ncs_uuid)
                        if ncs is not None:
                            activity.add_ncs_pathway(ncs)

        return activity

    def find_activity_by_name(self, name) -> typing.Dict:
        """Finds an activity setting inside
        the plugin QgsSettings that equals or matches the name.

        :param name: Activity name.
        :type name: str

        :returns: Activity object.
        :rtype: Activity
        """
        for activity in self.get_all_activities():
            model_name = activity.name
            trimmed_name = model_name.replace(" ", "_")
            if model_name == name or model_name in name or trimmed_name in name:
                return activity

        return None

    def get_all_activities(self) -> typing.List[Activity]:
        """Get all the activity objects stored in settings.

        :returns: Returns all the activity objects.
        :rtype: list
        """
        activities = []

        activity_root = self._get_activity_settings_base()

        with qgis_settings(activity_root) as settings:
            keys = settings.childKeys()
            for k in keys:
                activity = self.get_activity(k)
                if activity is not None:
                    activities.append(activity)

        return sorted(activities, key=lambda activity: activity.name)

    def update_activity(self, activity: Activity):
        """Updates the attributes of the activity object
        in settings. On the path, the BASE_DIR in settings
        is used to reflect the absolute path of each NCS
        pathway layer. If BASE_DIR is empty then the NCS
        pathway setting will not be updated.

        :param activity: Activity object to be updated.
        :type activity: Activity
        """
        base_dir = self.get_value(Settings.BASE_DIR)

        if base_dir:
            # PWLs path update
            for layer in activity.priority_layers:
                if layer in PRIORITY_LAYERS and base_dir not in layer.get(
                    PATH_ATTRIBUTE
                ):
                    abs_pwl_path = (
                        f"{base_dir}/{PRIORITY_LAYERS_SEGMENT}/"
                        f"{layer.get(PATH_ATTRIBUTE)}"
                    )
                    abs_pwl_path = str(os.path.normpath(abs_pwl_path))
                    layer[PATH_ATTRIBUTE] = abs_pwl_path

        # Remove then re-insert
        self.remove_activity(str(activity.uuid))
        self.save_activity(activity)

    def update_activities(self):
        """Updates the attributes of the existing activities."""
        activities = self.get_all_activities()

        for activity in activities:
            self.update_activity(activity)

    def remove_activity(self, activity_uuid: str):
        """Removes an activity settings entry using the UUID.

        :param activity_uuid: Unique identifier of the activity
        to be removed.
        :type activity_uuid: str
        """
        if self.get_activity(activity_uuid) is not None:
            self.remove(f"{self.ACTIVITY_BASE}/{activity_uuid}")

    def get_npv_collection(self) -> typing.Optional[ActivityNpvCollection]:
        """Gets the collection of NPV mappings of activities.

        :returns: The collection of activity NPV mappings or None
        if not defined.
        :rtype: ActivityNpvCollection
        """
        npv_collection_str = self.get_value(NPV_COLLECTION_PROPERTY, None)
        if not npv_collection_str:
            return None

        npv_collection_dict = {}
        try:
            npv_collection_dict = json.loads(npv_collection_str)
        except json.JSONDecodeError:
            log("ActivityNPVCollection JSON is invalid.")

        return create_activity_npv_collection(
            npv_collection_dict, self.get_all_activities()
        )

    def save_npv_collection(self, npv_collection: ActivityNpvCollection):
        """Saves the activity NPV collection in the settings as a serialized
        JSON string.

        :param npv_collection: Activity NPV collection serialized to a JSON string.
        :type npv_collection: ActivityNpvCollection
        """
        npv_collection_dict = activity_npv_collection_to_dict(npv_collection)
        npv_collection_str = json.dumps(npv_collection_dict)
        self.set_value(NPV_COLLECTION_PROPERTY, npv_collection_str)

    def save_online_scenario(self, scenario_uuid):
        """Save the passed scenario settings into the plugin settings as online tasl

        :param scenario_uuid: Scenario UUID
        :type scenario_uuid: str
        """
        settings_manager.set_value(self.ONLINE_TASK_BASE, scenario_uuid)

    def _get_online_tasks_settings_base(self) -> str:
        """Returns the path for Online Task settings.

        :returns: Base path to Online Task group.
        :rtype: str
        """
        return f"{self.BASE_GROUP_NAME}"

    def get_running_online_scenario(self) -> typing.Dict:
        """Retrieves running online scenario UUID.

        :returns: Scenario settings instance
        :rtype: ScenarioSettings
        """

        scenario_settings_key = self._get_online_tasks_settings_base()
        with qgis_settings(scenario_settings_key) as settings:
            return settings.value(self.ONLINE_TASK_BASE)

    def delete_online_task(self):
        """Delete the online task with the passed scenarion id.

        :param scenario_id: Scenario identifier
        :type scenario_id: str
        """
        log("delete online task")
        with qgis_settings(self.BASE_GROUP_NAME) as settings:
            a = settings.value(self.ONLINE_TASK_BASE)
            log(a)
            settings.remove(self.ONLINE_TASK_BASE)


settings_manager = SettingsManager()
