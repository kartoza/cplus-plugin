# -*- coding: utf-8 -*-

"""Helper functions for supporting model management."""
import json
from dataclasses import field, fields
import typing
import uuid

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
)

from cplus_core.models.base import (
    BaseModelComponent,
    BaseModelComponentType,
    Activity,
    LayerModelComponent,
    LayerModelComponentType,
    LayerType,
    NcsPathway,
    ScenarioResult,
    SpatialExtent,
)
from ..definitions.constants import (
    ACTIVITY_IDENTIFIER_PROPERTY,
    ABSOLUTE_NPV_ATTRIBUTE,
    CARBON_PATHS_ATTRIBUTE,
    COMPUTED_ATTRIBUTE,
    DISCOUNT_ATTRIBUTE,
    ENABLED_ATTRIBUTE,
    STYLE_ATTRIBUTE,
    NAME_ATTRIBUTE,
    DESCRIPTION_ATTRIBUTE,
    LAYER_TYPE_ATTRIBUTE,
    MANUAL_NPV_ATTRIBUTE,
    MASK_PATHS_SEGMENT,
    NPV_MAPPINGS_ATTRIBUTE,
    MAX_VALUE_ATTRIBUTE,
    MIN_VALUE_ATTRIBUTE,
    NORMALIZED_NPV_ATTRIBUTE,
    PATH_ATTRIBUTE,
    PIXEL_VALUE_ATTRIBUTE,
    PRIORITY_LAYERS_SEGMENT,
    REMOVE_EXISTING_ATTRIBUTE,
    USER_DEFINED_ATTRIBUTE,
    UUID_ATTRIBUTE,
    YEARS_ATTRIBUTE,
    YEARLY_RATES_ATTRIBUTE,
)
from ..definitions.defaults import DEFAULT_CRS_ID, QGIS_GDAL_PROVIDER
from .financial import ActivityNpv, ActivityNpvCollection, NpvParameters

from ..utils import log


def model_component_to_dict(
    model_component: BaseModelComponentType, uuid_to_str=True
) -> dict:
    """Creates a dictionary containing the base attribute
    name-value pairs from a model component object.

    :param model_component: Source model component object whose
    values are to be mapped to the corresponding
    attribute names.
    :type model_component: BaseModelComponent

    :param uuid_to_str: Set True to convert the UUID to a
    string equivalent, else False. Some serialization engines
    such as JSON are unable to handle UUID objects hence the need
    to convert to string.
    :type uuid_to_str: bool

    :returns: Returns a dictionary item containing attribute
    name-value pairs.
    :rtype: dict
    """
    model_uuid = model_component.uuid
    if uuid_to_str:
        model_uuid = str(model_uuid)

    return {
        UUID_ATTRIBUTE: model_uuid,
        NAME_ATTRIBUTE: model_component.name,
        DESCRIPTION_ATTRIBUTE: model_component.description,
    }


def create_model_component(
    source_dict: dict,
    model_cls: typing.Callable[[uuid.UUID, str, str], BaseModelComponentType],
) -> typing.Union[BaseModelComponentType, None]:
    """Factory method for creating and setting attribute values
    for a base model component object.

    :param source_dict: Dictionary containing attribute values.
    :type source_dict: dict

    :param model_cls: Callable class that will be created based on the
    input argument values from the dictionary.
    :type model_cls: BaseModelComponent

    :returns: Base model component object with property values
    derived from the dictionary.
    :rtype: BaseModelComponent
    """
    if not issubclass(model_cls, BaseModelComponent):
        return None

    return model_cls(
        uuid.UUID(source_dict[UUID_ATTRIBUTE]),
        source_dict[NAME_ATTRIBUTE],
        source_dict[DESCRIPTION_ATTRIBUTE],
    )


def create_layer_component(
    source_dict,
    model_cls: typing.Callable[
        [uuid.UUID, str, str, str, LayerType, bool], LayerModelComponentType
    ],
) -> typing.Union[LayerModelComponent, None]:
    """Factory method for creating a layer model component using
    attribute values defined in a dictionary.

    :param source_dict: Dictionary containing property values.
    :type source_dict: dict

    :param model_cls: Callable class that will be created based on the
    input argument values from the dictionary.
    :type model_cls: LayerModelComponent

    :returns: Layer model component object with property values set
    from the dictionary.
    :rtype: LayerModelComponent
    """
    if UUID_ATTRIBUTE not in source_dict:
        return None

    source_uuid = source_dict[UUID_ATTRIBUTE]
    if isinstance(source_uuid, str):
        source_uuid = uuid.UUID(source_uuid)

    kwargs = {}
    if PATH_ATTRIBUTE in source_dict:
        kwargs[PATH_ATTRIBUTE] = source_dict[PATH_ATTRIBUTE]

    if LAYER_TYPE_ATTRIBUTE in source_dict:
        kwargs[LAYER_TYPE_ATTRIBUTE] = LayerType(int(source_dict[LAYER_TYPE_ATTRIBUTE]))

    if USER_DEFINED_ATTRIBUTE in source_dict:
        kwargs[USER_DEFINED_ATTRIBUTE] = bool(source_dict[USER_DEFINED_ATTRIBUTE])

    return model_cls(
        source_uuid,
        source_dict[NAME_ATTRIBUTE],
        source_dict[DESCRIPTION_ATTRIBUTE],
        **kwargs,
    )


def create_ncs_pathway(source_dict) -> typing.Union[NcsPathway, None]:
    """Factory method for creating an NcsPathway object using
    attribute values defined in a dictionary.

    :param source_dict: Dictionary containing property values.
    :type source_dict: dict

    :returns: NCS pathway object with property values set
    from the dictionary.
    :rtype: NcsPathway
    """
    ncs = create_layer_component(source_dict, NcsPathway)

    # We are checking because of the various iterations of the attributes
    # in the NcsPathway class where some of these attributes might
    # be missing.
    if CARBON_PATHS_ATTRIBUTE in source_dict:
        ncs.carbon_paths = source_dict[CARBON_PATHS_ATTRIBUTE]

    return ncs


def create_activity(source_dict) -> typing.Union[Activity, None]:
    """Factory method for creating an activity using
    attribute values defined in a dictionary.

    :param source_dict: Dictionary containing property values.
    :type source_dict: dict

    :returns: activity with property values set
    from the dictionary.
    :rtype: Activity
    """
    activity = create_layer_component(source_dict, Activity)
    if PRIORITY_LAYERS_SEGMENT in source_dict.keys():
        activity.priority_layers = source_dict[PRIORITY_LAYERS_SEGMENT]

    if MASK_PATHS_SEGMENT in source_dict.keys():
        activity.mask_paths = source_dict[MASK_PATHS_SEGMENT]

    # Set style
    if STYLE_ATTRIBUTE in source_dict.keys():
        activity.layer_styles = source_dict[STYLE_ATTRIBUTE]

    # Set styling pixel value
    if PIXEL_VALUE_ATTRIBUTE in source_dict.keys():
        activity.style_pixel_value = source_dict[PIXEL_VALUE_ATTRIBUTE]

    return activity


def layer_component_to_dict(
    layer_component: LayerModelComponentType, uuid_to_str=True
) -> dict:
    """Creates a dictionary containing attribute
    name-value pairs from a layer model component object.

    :param layer_component: Source layer model component object whose
    values are to be mapped to the corresponding
    attribute names.
    :type layer_component: LayerModelComponent

    :param uuid_to_str: Set True to convert the UUID to a
    string equivalent, else False. Some serialization engines
    such as JSON are unable to handle UUID objects hence the need
    to convert to string.
    :type uuid_to_str: bool

    :returns: Returns a dictionary item containing attribute
    name-value pairs.
    :rtype: dict
    """
    base_attrs = model_component_to_dict(layer_component, uuid_to_str)
    base_attrs[PATH_ATTRIBUTE] = layer_component.path
    try:
        base_attrs[LAYER_TYPE_ATTRIBUTE] = int(layer_component.layer_type)
    except TypeError:
        if base_attrs["path"].endswith(".tif"):
            base_attrs[LAYER_TYPE_ATTRIBUTE] = 0
        elif base_attrs["path"].endswith(".shp"):
            base_attrs[LAYER_TYPE_ATTRIBUTE] = 1
    base_attrs[USER_DEFINED_ATTRIBUTE] = layer_component.user_defined

    return base_attrs


def ncs_pathway_to_dict(ncs_pathway: NcsPathway, uuid_to_str=True) -> dict:
    """Creates a dictionary containing attribute
    name-value pairs from an NCS pathway object.

    This function has been retained for legacy support.

    :param ncs_pathway: Source NCS pathway object whose
    values are to be mapped to the corresponding
    attribute names.
    :type ncs_pathway: NcsPathway

    :param uuid_to_str: Set True to convert the UUID to a
    string equivalent, else False. Some serialization engines
    such as JSON are unable to handle UUID objects hence the need
    to convert to string.
    :type uuid_to_str: bool

    :returns: Returns a dictionary item containing attribute
    name-value pairs.
    :rtype: dict
    """
    base_ncs_dict = layer_component_to_dict(ncs_pathway, uuid_to_str)
    base_ncs_dict[CARBON_PATHS_ATTRIBUTE] = ncs_pathway.carbon_paths

    return base_ncs_dict


def clone_layer_component(
    layer_component: LayerModelComponent,
    model_cls: typing.Callable[[uuid.UUID, str, str], LayerModelComponentType],
) -> typing.Union[LayerModelComponent, None]:
    """Clones a layer-based model component.

    :param layer_component: Layer-based model component to clone.
    :type layer_component: LayerModelComponent

    :param model_cls: Callable class that will be created based on the
    input argument values from the dictionary.
    :type model_cls: LayerModelComponent

    :returns: A new instance of the cloned model component. It
    will return None if the input is not a layer-based model
    component.
    :rtype: LayerModelComponent
    """
    if not isinstance(layer_component, LayerModelComponent):
        return None

    cloned_component = model_cls(
        layer_component.uuid, layer_component.name, layer_component.description
    )

    for f in fields(layer_component):
        attr_val = getattr(layer_component, f.name)
        setattr(cloned_component, f.name, attr_val)

    return cloned_component


def clone_ncs_pathway(ncs: NcsPathway) -> NcsPathway:
    """Creates a deep copy of the given NCS pathway.

    :param ncs: NCS pathway to clone.
    :type ncs: NcsPathway

    :returns: A deep copy of the original NCS pathway object.
    :rtype: NcsPathway
    """
    return clone_layer_component(ncs, NcsPathway)


def clone_activity(
    activity: Activity,
) -> Activity:
    """Creates a deep copy of the given activity.

    :param activity: activity to clone.
    :type activity: Activity

    :returns: A deep copy of the original activity object.
    :rtype: Activity
    """
    activity = clone_layer_component(activity, Activity)
    if activity is None:
        return None

    pathways = activity.pathways
    cloned_pathways = []
    for p in pathways:
        cloned_ncs = clone_ncs_pathway(p)
        if cloned_ncs is not None:
            cloned_pathways.append(cloned_ncs)

    activity.pathways = cloned_pathways

    return activity


def copy_layer_component_attributes(
    target: LayerModelComponent, source: LayerModelComponent
) -> LayerModelComponent:
    """Copies the attribute values of source to target. The uuid
    attribute value is not copied as well as the layer attribute.
    However, for the latter, the path is copied.

    :param target: Target object whose attribute values will be updated.
    :type target: LayerModelComponent

    :param source: Source object whose attribute values will be copied to
    the target.
    :type source: LayerModelComponent

    :returns: Target object containing the updated attribute values apart
    for the uuid whose value will not change.
    :rtype: LayerModelComponent
    """
    if not isinstance(target, LayerModelComponent) or not isinstance(
        source, LayerModelComponent
    ):
        raise TypeError(
            "Source or target objects are not of type 'LayerModelComponent'"
        )

    for f in fields(source):
        # Exclude uuid
        if f.name == UUID_ATTRIBUTE:
            continue
        attr_val = getattr(source, f.name)
        setattr(target, f.name, attr_val)

    # Force layer to be set/updated
    target.update_layer_type()

    return target


def extent_to_qgs_rectangle(
    spatial_extent: SpatialExtent,
) -> typing.Union[QgsRectangle, None]:
    """Returns a QgsRectangle object from the SpatialExtent object.

    If the SpatialExtent is invalid (i.e. less than four items) then it
    will return None.

    :param spatial_extent: Spatial extent data model that defines the
    scenario bounds.
    :type spatial_extent: SpatialExtent

    :returns: QGIS rectangle defining the bounds for the scenario.
    :rtype: QgsRectangle
    """
    if len(spatial_extent.bbox) < 4:
        return None

    return QgsRectangle(
        spatial_extent.bbox[0],
        spatial_extent.bbox[2],
        spatial_extent.bbox[1],
        spatial_extent.bbox[3],
    )


def extent_to_project_crs_extent(
    spatial_extent: SpatialExtent, project: QgsProject = None
) -> typing.Union[QgsRectangle, None]:
    """Transforms SpatialExtent model to an QGIS extent based
    on the CRS of the given project.

    :param spatial_extent: Spatial extent data model that defines the
    scenario bounds.
    :type spatial_extent: SpatialExtent

    :param project: Project whose CRS will be used to determine
    the values of the output extent.
    :type project: QgsProject

    :returns: Output extent in the project's CRS. If the input extent
    is invalid, this function will return None.
    :rtype: QgsRectangle
    """
    input_rect = extent_to_qgs_rectangle(spatial_extent)
    if input_rect is None:
        return None

    default_crs = QgsCoordinateReferenceSystem.fromEpsgId(DEFAULT_CRS_ID)
    if not default_crs.isValid():
        return None

    if project is None:
        project = QgsProject.instance()

    target_crs = project.crs()
    if default_crs == target_crs:
        # No need for transformation
        return input_rect

    try:
        coordinate_xform = QgsCoordinateTransform(default_crs, project.crs(), project)
        return coordinate_xform.transformBoundingBox(input_rect)
    except Exception as e:
        log(f"{e}, using the default input extent.")

    return input_rect


def activity_npv_to_dict(activity_npv: ActivityNpv) -> dict:
    """Converts an ActivityNpv object to a dictionary representation.

    :returns: A dictionary containing attribute name-value pairs.
    :rtype: dict
    """
    return {
        YEARS_ATTRIBUTE: activity_npv.params.years,
        DISCOUNT_ATTRIBUTE: activity_npv.params.discount,
        ABSOLUTE_NPV_ATTRIBUTE: activity_npv.params.absolute_npv,
        NORMALIZED_NPV_ATTRIBUTE: activity_npv.params.normalized_npv,
        YEARLY_RATES_ATTRIBUTE: activity_npv.params.yearly_rates,
        MANUAL_NPV_ATTRIBUTE: activity_npv.params.manual_npv,
        ENABLED_ATTRIBUTE: activity_npv.enabled,
        ACTIVITY_IDENTIFIER_PROPERTY: activity_npv.activity_id,
    }


def create_activity_npv(activity_npv_dict: dict) -> typing.Optional[ActivityNpv]:
    """Creates an ActivityNpv object from the equivalent dictionary
    representation.

    Please note that the `activity` attribute of the `ActivityNpv` object will be
    `None` hence, will have to be set manually by extracting the corresponding `Activity`
    from the activity UUID.

    :param activity_npv_dict: Dictionary containing information for deserializing
    to the ActivityNpv object.
    :type activity_npv_dict: dict

    :returns: ActivityNpv deserialized from the dictionary representation.
    :rtype: ActivityNpv
    """
    args = []
    if YEARS_ATTRIBUTE in activity_npv_dict:
        args.append(activity_npv_dict[YEARS_ATTRIBUTE])

    if DISCOUNT_ATTRIBUTE in activity_npv_dict:
        args.append(activity_npv_dict[DISCOUNT_ATTRIBUTE])

    if len(args) < 2:
        return None

    kwargs = {}

    if ABSOLUTE_NPV_ATTRIBUTE in activity_npv_dict:
        kwargs[ABSOLUTE_NPV_ATTRIBUTE] = activity_npv_dict[ABSOLUTE_NPV_ATTRIBUTE]

    if NORMALIZED_NPV_ATTRIBUTE in activity_npv_dict:
        kwargs[NORMALIZED_NPV_ATTRIBUTE] = activity_npv_dict[NORMALIZED_NPV_ATTRIBUTE]

    if MANUAL_NPV_ATTRIBUTE in activity_npv_dict:
        kwargs[MANUAL_NPV_ATTRIBUTE] = activity_npv_dict[MANUAL_NPV_ATTRIBUTE]

    npv_params = NpvParameters(*args, **kwargs)

    if YEARLY_RATES_ATTRIBUTE in activity_npv_dict:
        yearly_rates = activity_npv_dict[YEARLY_RATES_ATTRIBUTE]
        npv_params.yearly_rates = yearly_rates

    npv_enabled = False
    if ENABLED_ATTRIBUTE in activity_npv_dict:
        npv_enabled = activity_npv_dict[ENABLED_ATTRIBUTE]

    return ActivityNpv(npv_params, npv_enabled, None)


def activity_npv_collection_to_dict(activity_collection: ActivityNpvCollection) -> dict:
    """Converts the activity NPV collection object to the
    dictionary representation.

    :returns: A dictionary containing the attribute name-value pairs
    of an activity NPV collection object
    :rtype: dict
    """
    npv_collection_dict = {
        MIN_VALUE_ATTRIBUTE: activity_collection.minimum_value,
        MAX_VALUE_ATTRIBUTE: activity_collection.maximum_value,
        COMPUTED_ATTRIBUTE: activity_collection.use_computed,
        REMOVE_EXISTING_ATTRIBUTE: activity_collection.remove_existing,
    }

    mapping_dict = list(map(activity_npv_to_dict, activity_collection.mappings))
    npv_collection_dict[NPV_MAPPINGS_ATTRIBUTE] = mapping_dict

    return npv_collection_dict


def create_activity_npv_collection(
    activity_collection_dict: dict, reference_activities: typing.List[Activity] = None
) -> typing.Optional[ActivityNpvCollection]:
    """Creates an activity NPV collection object from the corresponding
    dictionary representation.

    :param activity_collection_dict: Dictionary representation containing
    information of an activity NPV collection object.
    :type activity_collection_dict: dict

    :param reference_activities: Optional list of activities that will be
    used to lookup  when deserializing the ActivityNpv objects.
    :type reference_activities: list

    :returns: Activity NPV collection object from the dictionary representation
    or None if the source dictionary is invalid.
    :rtype: ActivityNpvCollection
    """
    if len(activity_collection_dict) == 0:
        return None

    ref_activities_by_uuid = {
        str(activity.uuid): activity for activity in reference_activities
    }

    args = []

    # Minimum value
    if MIN_VALUE_ATTRIBUTE in activity_collection_dict:
        args.append(activity_collection_dict[MIN_VALUE_ATTRIBUTE])

    # Maximum value
    if MAX_VALUE_ATTRIBUTE in activity_collection_dict:
        args.append(activity_collection_dict[MAX_VALUE_ATTRIBUTE])

    if len(args) < 2:
        return None

    activity_npv_collection = ActivityNpvCollection(*args)

    # Use computed
    if COMPUTED_ATTRIBUTE in activity_collection_dict:
        use_computed = activity_collection_dict[COMPUTED_ATTRIBUTE]
        activity_npv_collection.use_computed = use_computed

    # Remove existing
    if REMOVE_EXISTING_ATTRIBUTE in activity_collection_dict:
        remove_existing = activity_collection_dict[REMOVE_EXISTING_ATTRIBUTE]
        activity_npv_collection.remove_existing = remove_existing

    if NPV_MAPPINGS_ATTRIBUTE in activity_collection_dict:
        mappings_dict = activity_collection_dict[NPV_MAPPINGS_ATTRIBUTE]
        npv_mappings = []
        for md in mappings_dict:
            activity_npv = create_activity_npv(md)
            if activity_npv is None:
                continue

            # Get the corresponding activity from the unique identifier
            if ACTIVITY_IDENTIFIER_PROPERTY in md:
                activity_id = md[ACTIVITY_IDENTIFIER_PROPERTY]
                if activity_id in ref_activities_by_uuid:
                    ref_activity = ref_activities_by_uuid[activity_id]
                    activity_npv.activity = ref_activity
                    npv_mappings.append(activity_npv)

        activity_npv_collection.mappings = npv_mappings

    return activity_npv_collection


def layer_from_scenario_result(
    result: ScenarioResult,
) -> typing.Optional[QgsRasterLayer]:
    """Gets the scenario output layer from the results of the
    analysis.

    :returns: Raster layer corresponding to the output scenario
    path or None if the file does not exist or if the raster layer
    is invalid.
    :rtype: QgsRasterLayer
    """
    layer_file = result.analysis_output.get("OUTPUT")

    layer = QgsRasterLayer(layer_file, result.scenario.name, QGIS_GDAL_PROVIDER)
    if not layer.isValid():
        return None

    return layer
