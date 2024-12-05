# -*- coding: utf-8 -*-
"""
Functions for providing model test data.
"""
import os
import typing
from uuid import UUID

from qgis.core import QgsRasterLayer

from cplus_plugin.definitions.constants import (
    CARBON_COEFFICIENT_ATTRIBUTE,
    CARBON_PATHS_ATTRIBUTE,
    NAME_ATTRIBUTE,
    DESCRIPTION_ATTRIBUTE,
    LAYER_TYPE_ATTRIBUTE,
    PATH_ATTRIBUTE,
    PRIORITY_LAYERS_SEGMENT,
    USER_DEFINED_ATTRIBUTE,
    UUID_ATTRIBUTE,
)
from cplus_plugin.definitions.defaults import PILOT_AREA_EXTENT
from cplus_core.models.base import (
    Activity,
    LayerType,
    NcsPathway,
    Scenario,
    ScenarioResult,
    SpatialExtent,
)
from cplus_plugin.models.financial import (
    ActivityNpv,
    ActivityNpvCollection,
    NpvParameters,
)


VALID_NCS_UUID_STR = "b5338edf-f3cc-4040-867d-be9651a28b63"
INVALID_NCS_UUID_STR = "4c6b31a1-3ff3-43b2-bfe2-45519a975955"
ACTIVITY_UUID_STR = "01e3a612-118d-4d94-9a5a-09c4b9168288"
ACTIVITY_2_UUID_STR = "1fbfb272-0b8d-409e-8cf6-db9f1f63fce2"
ACTIVITY_3_UUID_STR = "7b5c2ae0-aeea-4006-a3f8-42ee7cd81bcf"
TEST_RASTER_PATH = os.path.join(os.path.dirname(__file__), "tenbytenraster.tif")
SCENARIO_UUID_STR = "6cf5b355-f605-4de5-98b1-64936d473f82"

NCS_UUID_STR_1 = "51f561d1-32eb-4104-9408-d5b66ce6b651"
NCS_UUID_STR_2 = "424e076e-61b7-4116-a5a9-d2a7b4c2574e"
NCS_UUID_STR_3 = "5c42b644-3d21-4081-9206-28e872efca73"


def get_valid_ncs_pathway() -> NcsPathway:
    """Creates a valid NCS pathway object."""
    return NcsPathway(
        UUID(VALID_NCS_UUID_STR),
        "Valid NCS Pathway",
        "Description for valid NCS",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
        carbon_paths=[],
    )


def get_invalid_ncs_pathway() -> NcsPathway:
    """Creates an invalid NCS pathway object i.e. path not set."""
    return NcsPathway(
        UUID(INVALID_NCS_UUID_STR),
        "Invalid NCS Pathway",
        "Description for invalid NCS",
        "",
    )


def get_ncs_pathway_with_valid_carbon() -> NcsPathway:
    """Creates a valid NCS pathway object with a valid carbon layer."""
    return NcsPathway(
        UUID(VALID_NCS_UUID_STR),
        "Valid NCS Pathway",
        "Description for valid NCS",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
        carbon_paths=[TEST_RASTER_PATH],
    )


def get_ncs_pathway_with_invalid_carbon() -> NcsPathway:
    """Creates an NCS pathway object with an invalid carbon layer."""
    return NcsPathway(
        UUID(VALID_NCS_UUID_STR),
        "Invalid NCS Pathway",
        "Description for invalid NCS",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
        carbon_paths=["tenbytenraster"],
    )


def get_ncs_pathways(use_projected=False) -> typing.List[NcsPathway]:
    """Returns a list of NCS pathways with some containing carbon layers.

    :param use_projected: True to return projected NCS layers else the
    geographic ones.
    :type use_projected: bool

    :returns: List of NCS pathways.
    :rtype: list
    """
    pathway_layer_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "pathways", "layers"
    )

    carbon_directory = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "carbon", "layers"
    )

    carbon_layer_path = os.path.join(carbon_directory, "carbon_layer_1.tif")

    filenames = []

    for i in range(1, 4):
        base_name = "test_pathway"
        if use_projected:
            base_name = f"{base_name}_projected"

        filenames.append(f"{base_name}_{i!s}.tif")

    pathway_layer_path1 = os.path.join(pathway_layer_directory, filenames[0])
    pathway_layer_path2 = os.path.join(pathway_layer_directory, filenames[1])
    pathway_layer_path3 = os.path.join(pathway_layer_directory, filenames[2])

    ncs_pathway1 = NcsPathway(
        UUID(NCS_UUID_STR_1),
        "NCS One",
        "Description for NCS one",
        pathway_layer_path1,
        LayerType.RASTER,
        True,
        carbon_paths=[carbon_layer_path],
    )

    ncs_pathway2 = NcsPathway(
        UUID(NCS_UUID_STR_2),
        "NCS Two",
        "Description for NCS two",
        pathway_layer_path2,
        LayerType.RASTER,
        True,
    )

    ncs_pathway3 = NcsPathway(
        UUID(NCS_UUID_STR_2),
        "NCS Three",
        "Description for NCS three",
        pathway_layer_path3,
        LayerType.RASTER,
        True,
        carbon_paths=[carbon_layer_path],
    )

    return [ncs_pathway1, ncs_pathway2, ncs_pathway3]


def get_activity() -> Activity:
    """Creates a test activity object."""
    return Activity(
        UUID(ACTIVITY_UUID_STR),
        "Test Activity",
        "Description for test activity",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
    )


def get_test_layer() -> QgsRasterLayer:
    """Returns the test raster layer."""
    return QgsRasterLayer(TEST_RASTER_PATH, "Test Layer")


def get_test_scenario() -> Scenario:
    """Returns the test Scenario object."""
    extent_list = PILOT_AREA_EXTENT["coordinates"]
    sp_extent = SpatialExtent(
        bbox=[extent_list[3], extent_list[2], extent_list[1], extent_list[0]]
    )
    return Scenario(
        UUID(SCENARIO_UUID_STR),
        "Test Scenario",
        "Test scenario description",
        sp_extent,
        [get_activity()],
        [get_activity()],
        [
            [
                {
                    "name": "Biodiversity",
                    "value": 50,
                    "description": "Test biodiversity group",
                }
            ]
        ],
    )


def get_test_scenario_result() -> ScenarioResult:
    """Returns a test scenario result object."""
    return ScenarioResult(get_test_scenario(), output_layer_name="Test Scenario Layer")


def get_activity_npvs() -> typing.List[ActivityNpv]:
    """Returns a collection of activity NPV mappings."""
    npv_params_1 = NpvParameters(3, 2.0)
    npv_params_1.absolute_npv = 40410.23
    npv_params_1.yearly_rates = [
        (25000.0, 18000.0, 7000.0),
        (28000.0, 15000.0, 12745.1),
        (35000.0, 13500.0, 20665.13),
    ]
    activity_npv_1 = ActivityNpv(npv_params_1, True, get_activity())

    npv_params_2 = NpvParameters(2, 4.0)
    npv_params_2.absolute_npv = 102307.69
    npv_params_2.yearly_rates = [
        (100000.0, 65000.0, 35000.0),
        (120000.0, 50000.0, 67307.69),
    ]
    activity_2 = Activity(
        UUID(ACTIVITY_2_UUID_STR),
        "Test Activity 2",
        "Description for test activity 2",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
    )
    activity_npv_2 = ActivityNpv(npv_params_2, True, activity_2)

    npv_params_3 = NpvParameters(3, 7.0)
    npv_params_3.absolute_npv = 38767.05
    npv_params_3.yearly_rates = [
        (64000.0, 58000.0, 6000.0),
        (67500.0, 53000.0, 13551.4),
        (70000.0, 48000.0, 19215.65),
    ]
    activity_3 = Activity(
        UUID(ACTIVITY_3_UUID_STR),
        "Test Activity 3",
        "Description for test activity 3",
        TEST_RASTER_PATH,
        LayerType.RASTER,
        True,
    )
    activity_npv_3 = ActivityNpv(npv_params_3, True, activity_3)

    return [activity_npv_1, activity_npv_2, activity_npv_3]


def get_activity_npv_collection() -> ActivityNpvCollection:
    """Returns an activity NPV collection for testing."""
    npv_collection = ActivityNpvCollection(0.0, 0.0)

    mappings = get_activity_npvs()
    npv_collection.mappings = mappings

    return npv_collection


NCS_PATHWAY_DICT = {
    UUID_ATTRIBUTE: UUID(VALID_NCS_UUID_STR),
    NAME_ATTRIBUTE: "Valid NCS Pathway",
    DESCRIPTION_ATTRIBUTE: "Description for valid NCS",
    PATH_ATTRIBUTE: TEST_RASTER_PATH,
    LAYER_TYPE_ATTRIBUTE: 0,
    USER_DEFINED_ATTRIBUTE: True,
    CARBON_PATHS_ATTRIBUTE: [],
}
