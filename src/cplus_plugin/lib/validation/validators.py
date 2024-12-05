# -*- coding: utf-8 -*-
"""
Aggregated and individual rule validators.
"""

from abc import abstractmethod
from pathlib import Path
import traceback
import typing

from qgis.core import QgsRasterLayer, QgsTask, QgsUnitTypes

from ...definitions.constants import NO_DATA_VALUE

from .configs import (
    carbon_resolution_validation_config,
    crs_validation_config,
    no_data_validation_config,
    projected_crs_validation_config,
    raster_validation_config,
    resolution_validation_config,
)
from .feedback import ValidationFeedback
from cplus_core.models.base import LayerModelComponent, ModelComponentType, NcsPathway
from ...models.validation import (
    RuleConfiguration,
    RuleInfo,
    RuleResult,
    RuleType,
    ValidationResult,
)
from ...utils import log, tr
from ...conf import settings_manager


class BaseRuleValidator:
    """Validator for an individual rule.

    This is an abstract class that needs to be subclassed with the
    specific validation implementation by overriding the `validate`
    protected function.
    """

    def __init__(self, configuration: RuleConfiguration, feedback: ValidationFeedback):
        self._config = configuration
        self._feedback = feedback
        self._result: RuleResult = None
        self.model_components: typing.List[LayerModelComponent] = list()

    @property
    def rule_configuration(self) -> RuleConfiguration:
        """Returns the rule configuration use in the validator.

        :returns: Rule configuration used in the validator.
        :rtype: RuleConfiguration
        """
        return self._config

    @property
    def result(self) -> RuleResult:
        """Returns the result of the validation process.

        :returns: Result of the validation process.
        :rtype: RuleResult
        """
        return self._result

    @property
    @abstractmethod
    def rule_type(self) -> RuleType:
        """Returns the type identifier of the rule validator.

        :returns: Type identifier of the rule validator.
        :rtype: RuleType
        """
        raise NotImplementedError

    @property
    def feedback(self) -> ValidationFeedback:
        """Returns the feedback object used in the validator
        for providing feedback on the validation process.

        :returns: Feedback object used in the validator
        for providing feedback on the validation process.
        :rtype: ValidationFeedback
        """
        return self._feedback

    @abstractmethod
    def _validate(self) -> bool:
        """Initiates the validation process.

        Subclasses need to override this method with the specific
        validation implementation and set the 'result' attribute
        value.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        raise NotImplementedError

    def log(self, message: str, info: bool = True):
        """Convenience function that logs the given messages by appending
        the information in the rule configuration.

        :param message: Message to be logged.
        :type message: str

        :param info: False if the message should be logged as a warning
        else True if information.
        :type info: bool
        """
        msg = f"{self._config.rule_name} - {message}"
        log(message=msg, info=info)

    def is_comparative(self) -> bool:
        """Indicate whether the validation check is comparative i.e. relative to
        the datasets or an absolute check. The former requires more than one
        dataset to execute the validation whereas the latter can be executed
        even for one dataset.

        :returns: True if the validator is comparative else False. Default is
        True.
        :rtype: bool
        """
        return True

    def _set_progress(self, progress: float):
        """Set the current progress of the validator.

        The 'validation_progress_changed' signal will be emitted.

        :param progress: Progress of validation as a percentage
        value i.e. between 0.0 and 100.0.
        :type progress: float
        """
        self._feedback.rule_progress = progress

    def run(self) -> bool:
        """Initiates the rule validation process and returns
        a result indicating whether the process succeeded or
        failed.

        A fail result would, for instance, be due to no layers,
        or only one layer, defined for validation.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        if len(self.model_components) == 0:
            msg = tr("No datasets for validation.")
            self.log(msg, False)

            return False

        return self._validate()

    def get_default_layer_metadata(
        self, layer_uuid: str, layer_type: str = "ncs_pathway"
    ) -> typing.Dict:
        """Get default layer metadata

        :param layer_uuid: UUID of the layer
        :type layer_uuid: str

        :param layer_type: Type of the layer e.g. ncs_pathway
        :type layer_type: str

        :return: Layer metadata
        :rtype: typing.Dict
        """
        layers = settings_manager.get_default_layers(layer_type, as_dict=True)
        layer = layers.get(layer_uuid)
        layer_metadata = layer.get("metadata", {})
        return layer_metadata


BaseRuleValidatorType = typing.TypeVar("BaseRuleValidatorType", bound=BaseRuleValidator)


class RasterValidator(BaseRuleValidator):
    """Checks if the input datasets are raster layers."""

    def _validate(self) -> bool:
        """Checks whether all input datasets are raster layers.

        If a layer is not valid, it will also be included in the list
        of non-raster datasets.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True
        non_raster_model_components = []

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False
                non_raster_model_components.append(model_component.name)
            else:
                if model_component.is_default_layer():
                    layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    if not layer_metadata.get("is_raster", False):
                        non_raster_model_components.append(model_component.name)
                else:
                    layer = model_component.to_map_layer().clone()
                    if not isinstance(layer, QgsRasterLayer):
                        non_raster_model_components.append(model_component.name)

            progress += progress_increment
            self._set_progress(progress)

        summary = ""
        validate_info = []
        if not status:
            summary = tr("There are invalid non-raster datasets")
            invalid_layer_names = ", ".join(non_raster_model_components)
            validate_info = [(tr("Non-raster datasets"), invalid_layer_names)]
        else:
            summary = tr("All datasets are rasters")

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @property
    def rule_type(self) -> RuleType:
        """Returns the raster type rule validator.

        :returns: Raster type rule validator.
        :rtype: RuleType
        """
        return RuleType.DATA_TYPE

    def is_comparative(self) -> bool:
        """Validator can be used for even one dataset."""
        return False


class CrsValidator(BaseRuleValidator):
    """Checks if the input datasets have the same CRS."""

    def _validate(self) -> bool:
        """Checks whether all input datasets have the same CRS.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True

        # key: CRS name or 'undefined', value: list of model/layer names
        crs_definitions = {}
        undefined_msg = tr("Undefined")
        invalid_msg = tr("Invalid datasets")
        has_undefined = False

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False

                # Add invalid datasets to the validation messages to make it explicit
                if invalid_msg in crs_definitions:
                    layers = crs_definitions.get(invalid_msg)
                    layers.append(model_component.name)
                else:
                    crs_definitions[invalid_msg] = [model_component.name]

            else:
                if model_component.is_default_layer():
                    layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    crs = layer_metadata.get("crs", None)
                else:
                    layer = model_component.to_map_layer().clone()
                    crs = layer.crs()

                if crs is None:
                    # Flag that there is at least one dataset with an undefined CRS
                    if not has_undefined:
                        has_undefined = True

                    if status:
                        status = False

                    if undefined_msg in crs_definitions:
                        layers = crs_definitions.get(undefined_msg)
                        layers.append(model_component.name)
                    else:
                        crs_definitions[undefined_msg] = [model_component.name]
                else:
                    if model_component.is_default_layer():
                        crs_id = crs
                    else:
                        crs_id = crs.authid()
                    if crs_id in crs_definitions:
                        layers = crs_definitions.get(crs_id)
                        layers.append(model_component.name)
                    else:
                        crs_definitions[crs_id] = [model_component.name]

            progress += progress_increment
            self._set_progress(progress)

        if len(crs_definitions) > 1 and status:
            status = False

        summary = ""
        validate_info = []
        if not status:
            summary = tr("Datasets have different CRS definitions")
            for crs_str, layers in crs_definitions.items():
                validate_info.append((crs_str, ", ".join(layers)))
        else:
            summary_tr = tr("All datasets have the same CRS")
            summary = f"{summary_tr} - {list(crs_definitions.keys())[0]}"

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @property
    def rule_type(self) -> RuleType:
        """Returns the CRS rule validator.

        :returns: CRS rule validator.
        :rtype: RuleType
        """
        return RuleType.CRS


class ProjectedCrsValidator(BaseRuleValidator):
    """Checks if the input datasets have a projected CRS."""

    def _validate(self) -> bool:
        """Checks whether all input datasets have a projected CRS.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True

        # key: Geographic CRS ID or 'undefined', value: list of model/layer names
        geographic_crs_definitions = {}
        undefined_msg = tr("Undefined")
        invalid_msg = tr("Invalid datasets")
        has_undefined = False

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        crs_type_id = ""

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False

                # Add invalid datasets to the validation messages to make it explicit
                if invalid_msg in geographic_crs_definitions:
                    layers = geographic_crs_definitions.get(invalid_msg)
                    layers.append(model_component.name)
                else:
                    geographic_crs_definitions[invalid_msg] = [model_component.name]

            else:
                if model_component.is_default_layer():
                    layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    crs = layer_metadata.get("crs", None)
                else:
                    layer = model_component.to_map_layer().clone()
                    crs = layer.crs()

                if crs is None:
                    # Flag that there is at least one dataset with an undefined CRS
                    if not has_undefined:
                        has_undefined = True

                    if status:
                        status = False

                    if undefined_msg in geographic_crs_definitions:
                        layers = geographic_crs_definitions.get(undefined_msg)
                        layers.append(model_component.name)
                    else:
                        geographic_crs_definitions[undefined_msg] = [
                            model_component.name
                        ]
                else:
                    # Use this to capture the CRS auth ID incase all datasets have
                    # the same CRS type.
                    if not crs_type_id:
                        if model_component.is_default_layer():
                            crs_type_id = crs
                            layer_metadata = self.get_default_layer_metadata(
                                model_component.layer_uuid
                            )
                            is_geographic = layer_metadata["is_geographic"]
                        else:
                            crs_type_id = crs.authid()
                            is_geographic = crs.isGeographic()

                    if is_geographic:
                        if crs_type_id in geographic_crs_definitions:
                            layers = geographic_crs_definitions.get(crs_type_id)
                            layers.append(model_component.name)
                        else:
                            geographic_crs_definitions[crs_type_id] = [
                                model_component.name
                            ]

            progress += progress_increment
            self._set_progress(progress)

        if len(geographic_crs_definitions) > 0 and status:
            status = False

        summary = ""
        validate_info = []
        if not status:
            summary = tr("Some datasets have a geographic CRS")
            for crs_type_str, layers in geographic_crs_definitions.items():
                validate_info.append((crs_type_str, ", ".join(layers)))
        else:
            summary_tr = tr("All datasets have a projected CRS")
            summary = f"{summary_tr} - {crs_type_id}"

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @property
    def rule_type(self) -> RuleType:
        """Returns the projected CRS rule validator.

        :returns: Projected CRS rule validator.
        :rtype: RuleType
        """
        return RuleType.PROJECTED_CRS

    def is_comparative(self) -> bool:
        """Validator can be used for even one dataset."""
        return False


class NoDataValueValidator(BaseRuleValidator):
    """Checks if applicable input datasets have the same no data value."""

    # Default band in raster layer.
    BAND_NUMBER = 0

    def _validate(self) -> bool:
        """Checks whether applicable input datasets have the same no data value.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True

        no_data_definitions = {}
        invalid_msg = tr("Invalid datasets")
        has_undefined = False

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False

                # Add invalid datasets to the validation messages to
                # make it explicit
                if invalid_msg in no_data_definitions:
                    layers = no_data_definitions.get(invalid_msg)
                    layers.append(model_component.name)
                else:
                    no_data_definitions[invalid_msg] = [model_component.name]

            else:
                if model_component.is_default_layer():
                    layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    if not layer_metadata.get("is_raster", False):
                        continue
                else:
                    layer = model_component.to_map_layer().clone()
                    if not isinstance(layer, QgsRasterLayer):
                        continue

                # If band does not have NoData value then exclude from validation
                if model_component.is_default_layer():
                    if "nodata_value" not in layer_metadata:
                        continue
                else:
                    raster_provider = layer.dataProvider()
                    if not raster_provider.sourceHasNoDataValue(self.BAND_NUMBER):
                        continue

                if model_component.is_default_layer():
                    no_data_value = layer_metadata["nodata_value"]
                else:
                    no_data_value = raster_provider.sourceNoDataValue(self.BAND_NUMBER)
                if no_data_value != NO_DATA_VALUE:
                    if no_data_value in no_data_definitions:
                        layers = no_data_definitions.get(no_data_value)
                        layers.append(model_component.name)
                    else:
                        no_data_definitions[no_data_value] = [model_component.name]

            progress += progress_increment
            self._set_progress(progress)

        if len(no_data_definitions) > 1 and status:
            status = False

        summary = ""
        validate_info = []
        if not status:
            summary_tr = tr("Datasets have a NoData value different from")
            summary = f"{summary_tr} {str(NO_DATA_VALUE)}"
            for no_data, layers in no_data_definitions.items():
                validate_info.append((str(no_data), ", ".join(layers)))
        else:
            summary_tr = tr("Datasets have the same NoData value")
            summary = f"{summary_tr} {str(NO_DATA_VALUE)}"

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @property
    def rule_type(self) -> RuleType:
        """Returns the no data value rule validator.

        :returns: No data value rule validator.
        :rtype: RuleType
        """
        return RuleType.NO_DATA_VALUE

    def is_comparative(self) -> bool:
        """Validator can be used for even one dataset."""
        return False


class ResolutionValidator(BaseRuleValidator):
    """Checks if datasets have the same spatial resolution."""

    DECIMAL_PLACES = 6

    def _validate(self) -> bool:
        """Checks whether input datasets have the same
        spatial resolution.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True

        spatial_resolution_definitions = {}
        invalid_msg = tr("Invalid datasets")

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False

                # Add invalid datasets to the validation messages to
                # make it explicit
                if invalid_msg in spatial_resolution_definitions:
                    layers = spatial_resolution_definitions.get(invalid_msg)
                    layers.append(model_component.name)
                else:
                    spatial_resolution_definitions[invalid_msg] = [model_component.name]

            else:
                if model_component.is_default_layer():
                    layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    if not layer_metadata.get("is_raster", False):
                        continue
                else:
                    layer = model_component.to_map_layer().clone()
                    if not isinstance(layer, QgsRasterLayer):
                        continue

                if model_component.is_default_layer():
                    resolution_definition = (
                        round(layer_metadata["resolution"][0], self.DECIMAL_PLACES),
                        round(layer_metadata["resolution"][1], self.DECIMAL_PLACES),
                        layer_metadata["unit"],
                    )
                else:
                    resolution_definition = self.create_resolution_definition(layer)
                if resolution_definition in spatial_resolution_definitions:
                    layers = spatial_resolution_definitions.get(resolution_definition)
                    layers.append(model_component.name)
                else:
                    spatial_resolution_definitions[resolution_definition] = [
                        model_component.name
                    ]

            progress += progress_increment
            self._set_progress(progress)

        if len(spatial_resolution_definitions) > 1 and status:
            status = False

        summary = ""
        validate_info = []
        if not status:
            summary = tr("Datasets have different spatial resolutions")
            for res_definition, layers in spatial_resolution_definitions.items():
                validate_info.append(
                    (
                        self.resolution_definition_to_str(res_definition),
                        ", ".join(layers),
                    )
                )
        else:
            summary_tr = tr("Datasets have the same spatial resolution")
            summary = f"{summary_tr} {self.resolution_definition_to_str(list(spatial_resolution_definitions.keys())[0])}"

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @classmethod
    def create_resolution_definition(cls, layer: QgsRasterLayer):
        """Creates a resolution definition tuple from a layer.

        :param layer: Input layer.
        :type layer: QgsRasterLayer

        :returns: Tuple containing x and y resolutions as well
        as the units.
        :rtype: tuple
        """
        crs = layer.crs()
        if crs is None:
            crs_unit_str = tr("unknown")
        else:
            crs_unit_str = QgsUnitTypes.toAbbreviatedString(crs.mapUnits())

        # Tuple containing x, y (truncated to given decimal places) and units
        resolution_definition = (
            round(layer.rasterUnitsPerPixelX(), cls.DECIMAL_PLACES),
            round(layer.rasterUnitsPerPixelY(), cls.DECIMAL_PLACES),
            crs_unit_str,
        )
        return resolution_definition

    @classmethod
    def resolution_definition_to_str(cls, resolution_definition: tuple) -> str:
        """Formats the resolution definition to a friendly-display string.

        :param resolution_definition: Tuple containing x and y resolutions as
        well as the units.
        :type resolution_definition: tuple

        :returns: Friendly display string.
        :rtype: str
        """
        if len(resolution_definition) < 3:
            return ""

        unit_str = (
            tr("unknown units")
            if not resolution_definition[2]
            else resolution_definition[2]
        )

        return f"X: {resolution_definition[0]!s} {unit_str}, Y: {resolution_definition[1]!s} {unit_str}"

    @property
    def rule_type(self) -> RuleType:
        """Returns the no data value rule validator.

        :returns: No data value rule validator.
        :rtype: RuleType
        """
        return RuleType.NO_DATA_VALUE


class CarbonLayerResolutionValidator(ResolutionValidator):
    """Checks if the resolution of the carbon layers matches
    that of the corresponding NCS pathways.
    """

    def _validate(self) -> bool:
        """Checks if the resolution of the carbon layers matches
        that of the corresponding NCS pathways.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        status = True

        carbon_resolution_definitions = {}
        invalid_msg = tr("Invalid datasets")
        invalid_carbon_msg = tr("Invalid carbon layer")

        progress = 0.0
        progress_increment = 100.0 / len(self.model_components)
        self._set_progress(progress)

        for model_component in self.model_components:
            if self.feedback.isCanceled():
                return False

            is_valid = model_component.is_valid()
            if not is_valid:
                if status:
                    status = False

                # Add invalid datasets to the validation messages to
                # make it explicit
                if invalid_msg in carbon_resolution_definitions:
                    layers = carbon_resolution_definitions.get(invalid_msg)
                    layers.append(model_component.name)
                else:
                    carbon_resolution_definitions[invalid_msg] = [model_component.name]

            else:
                if model_component.is_default_layer():
                    ncs_layer_metadata = self.get_default_layer_metadata(
                        model_component.layer_uuid
                    )
                    if not ncs_layer_metadata.get("is_raster", False):
                        continue
                else:
                    ncs_layer = model_component.to_map_layer().clone()
                    if not isinstance(ncs_layer, QgsRasterLayer):
                        continue

                # Check if the model component is an NcsPathway
                if not isinstance(model_component, NcsPathway):
                    continue

                if model_component.is_default_layer():
                    ncs_resolution_definition = (
                        round(ncs_layer_metadata["resolution"][0], self.DECIMAL_PLACES),
                        round(ncs_layer_metadata["resolution"][1], self.DECIMAL_PLACES),
                        ncs_layer_metadata["unit"],
                    )
                else:
                    ncs_resolution_definition = self.create_resolution_definition(
                        ncs_layer
                    )

                # Loop through the spatial resolution of each carbon path
                for carbon_path in model_component.carbon_paths:
                    if carbon_path.startswith("cplus://"):
                        layer_uuid = carbon_path.replace("cplus://", "")
                        carbon_layer_metadata = self.get_default_layer_metadata(
                            layer_uuid, "ncs_carbon"
                        )
                    else:
                        layer = QgsRasterLayer(carbon_path)
                        if not layer.isValid():
                            if model_component.name in carbon_resolution_definitions:
                                carbon_definitions = carbon_resolution_definitions.get(
                                    model_component.name
                                )
                                carbon_definitions.append(invalid_carbon_msg)
                            else:
                                carbon_resolution_definitions[model_component.name] = [
                                    invalid_carbon_msg
                                ]
                            continue

                    if carbon_path.startswith("cplus://"):
                        carbon_resolution_definition = (
                            round(
                                carbon_layer_metadata["resolution"][0],
                                self.DECIMAL_PLACES,
                            ),
                            round(
                                carbon_layer_metadata["resolution"][1],
                                self.DECIMAL_PLACES,
                            ),
                            carbon_layer_metadata["unit"],
                        )
                    else:
                        carbon_layer = layer.clone()
                        carbon_resolution_definition = (
                            self.create_resolution_definition(carbon_layer)
                        )

                    if carbon_path.startswith("cplus://"):
                        layer_name = carbon_layer_metadata["name"]
                    else:
                        # We will use the file name to represent the layer name
                        layer_name = Path(carbon_layer.source()).stem

                    if ncs_resolution_definition != carbon_resolution_definition:
                        if model_component.name in carbon_resolution_definitions:
                            carbon_definitions = carbon_resolution_definitions.get(
                                model_component.name
                            )
                            carbon_definitions.append(layer_name)
                        else:
                            carbon_resolution_definitions[model_component.name] = [
                                layer_name
                            ]

            progress += progress_increment
            self._set_progress(progress)

        if len(carbon_resolution_definitions) > 0 and status:
            status = False

        summary = ""
        validate_info = []
        if not status:
            summary = tr(
                "NCS pathways and corresponding carbon layers have different spatial resolutions"
            )
            for ncs_name, carbon_layers in carbon_resolution_definitions.items():
                validate_info.append(
                    (
                        ncs_name,
                        ", ".join(carbon_layers),
                    )
                )
        else:
            summary = tr(
                "NCS pathways and corresponding carbon layers have the same spatial resolution"
            )

        self._result = RuleResult(
            self._config, self._config.recommendation, summary, validate_info
        )

        self._set_progress(100.0)

        return status

    @property
    def rule_type(self) -> RuleType:
        """Returns the no data value rule validator.

        :returns: No data value rule validator.
        :rtype: RuleType
        """
        return RuleType.CARBON_RESOLUTION

    def is_comparative(self) -> bool:
        """Validator can be used for even one dataset."""
        return False


class DataValidator(QgsTask):
    """Abstract runner for checking a set of datasets against specific
    validation rules.

    Rule validators need to be added manually in the sub-class
    implementation and set the model component type of the result.
    """

    NAME = "Default Data Validator"
    MODEL_COMPONENT_TYPE = ModelComponentType.UNKNOWN

    def __init__(self, model_components=None):
        super().__init__(tr(self.NAME))

        self.model_components = []
        if model_components is not None:
            self.model_components = model_components

        self._result: ValidationResult = None
        self._rule_validators = []
        self._applicable_rule_validators = []
        self._feedback = ValidationFeedback()
        self._feedback.rule_progress_changed.connect(self._on_rule_progress_changed)
        self._feedback.rule_validation_completed.connect(
            self._on_rule_validation_completed
        )

        # Used to calculate the overall progress
        self._rule_reference_progress = 0

    @property
    def feedback(self) -> ValidationFeedback:
        """Returns the feedback object used in the validator
        for providing feedback on the validation process.

        :returns: Feedback object used in the validator
        for providing feedback on the validation process.
        :rtype: ValidationFeedback
        """
        return self._feedback

    def _validate(self) -> bool:
        """Initiates the validation process based on the specified
        rule validators.

        :returns: True if the validation process succeeded
        or False if it failed ro cancelled.
        :rtype: bool
        """
        status = True

        # Set validators to use based on the number of layers
        if len(self.model_components) == 1:
            self._applicable_rule_validators = [
                validator
                for validator in self._rule_validators
                if not validator.is_comparative()
            ]
        else:
            self._applicable_rule_validators = self._rule_validators

        if len(self._applicable_rule_validators) == 0:
            msg = tr("No rule validators available for the given model components.")
            self.log(msg, False)
            return False

        for i, rule_validator in enumerate(self._applicable_rule_validators):
            if self.isCanceled():
                status = False
                break

            rule_validator.model_components = self.model_components
            rule_info = RuleInfo(
                rule_validator.rule_type, rule_validator.rule_configuration.rule_name
            )
            self.feedback.current_rule = rule_info
            rule_validator.run()

        return status

    def _on_rule_progress_changed(self, rule_type: RuleType, rule_progress: float):
        """Slot raised when the rule validation progress changes.

        This calculates the overall progress of the validation process.

        :param rule_type: Rule type currently being executed.
        :type rule_type: RuleType

        :param rule_progress: Progress of the rule validation.
        :type rule_progress: float
        """
        if len(self._rule_validators) == 0:
            return

        progress_increment = rule_progress / len(self._rule_validators)
        total_progress = self._rule_reference_progress + progress_increment
        self._feedback.setProgress(total_progress)
        self.setProgress(total_progress)

    def _on_rule_validation_completed(self, rule_info: RuleInfo):
        """Slot raised when rule validation has completed.

        param rule_info: Rule whose execution has ended.
        :type rule_info: RuleInfo
        """
        self._rule_reference_progress += 100 / len(self._rule_validators)

    def log(self, message: str, info: bool = True):
        """Convenience function that logs the given messages by appending
        the information for the validator.

        :param message: Message to be logged.
        :type message: str

        :param info: False if the message should be logged as a warning
        else True if information.
        :type info: bool
        """
        msg = f"{self.NAME} - {message}"
        log(message=msg, info=info)

    @property
    def result(self) -> ValidationResult:
        """Returns the result of the validation process.

        :returns: Result of the validation process.
        :rtype: ValidationResult
        """
        return self._result

    def cancel(self):
        """Cancel the validation process."""
        self.log(tr("Validation process has been cancelled."))

        self._feedback.cancel()

        super().cancel()

    def run(self) -> bool:
        """Initiates the validation process based on the
        specified validators and returns a result indicating
        whether the process succeeded or failed.

        :returns: True if the validation process succeeded
        or False if it failed.
        :rtype: bool
        """
        if len(self._rule_validators) == 0:
            msg = tr("No rule validators specified.")
            self.log(msg, False)

            return False

        if len(self.model_components) == 0:
            msg = tr("At least one dataset is required for the validation process.")
            self.log(msg, False)

            return False

        status = True

        try:
            status = self._validate()
        except Exception as ex:
            exc_info = "".join(traceback.TracebackException.from_exception(ex).format())
            self.log(exc_info, False)
            status = False

        return status

    @staticmethod
    def rule_validators() -> typing.Dict[RuleType, typing.Type[BaseRuleValidator]]:
        """Returns all the rule validator classes, any new validator
        type needs to be added here.

        The validator classes are indexed by their corresponding rule
        type enum.

        :returns: Collection containing rule validator classes indexed
        by their corresponding rule types.
        :rtype: dict
        """
        return {
            RuleType.DATA_TYPE: RasterValidator,
            RuleType.CRS: CrsValidator,
            RuleType.NO_DATA_VALUE: NoDataValueValidator,
            RuleType.RESOLUTION: ResolutionValidator,
            RuleType.CARBON_RESOLUTION: CarbonLayerResolutionValidator,
            RuleType.PROJECTED_CRS: ProjectedCrsValidator,
        }

    @staticmethod
    def validator_cls_by_type(rule_type: RuleType) -> typing.Type[BaseRuleValidator]:
        """Gets the rule validator class based on the corresponding rule type.

        :param rule_type: The type of the validator rule.
        :type rule_type: RuleType

        :returns: The rule validator class corresponding to the
        given rule type.
        :rtype: BaseRuleValidator
        """
        return DataValidator.rule_validators()[rule_type]

    @staticmethod
    def create_rule_validator(
        rule_type: RuleType, config: RuleConfiguration, feedback: ValidationFeedback
    ) -> BaseRuleValidator:
        """Factory method for creating a rule validator object.

        :param rule_type: The type of the validator rule.
        :type rule_type: RuleType

        :param config: The context information for configuring
        the rule validator.
        :type rule_type: RuleConfiguration

        :param feedback: Feedback object for reporting progress.
        :type feedback: ValidationFeedback

        :returns: An instance of the specific rule validator.
        :rtype: BaseRuleValidator
        """
        validator_cls = DataValidator.validator_cls_by_type(rule_type)

        return validator_cls(config, feedback)

    def add_rule_validator(self, rule_validator: BaseRuleValidator):
        """Add a rule validator for validating the input model components.

        :param rule_validator: Validator for checking the input model
        components based on the specific validation rule.
        :type rule_validator: BaseRuleValidator
        """
        self._rule_validators.append(rule_validator)

    def finished(self, result: bool):
        """Depending on the outcome of the validation process,
        `validation_completed` signal will be emitted only if the
        validation was successful. The `result` attribute will also contain the
        validation result object. If an error occurred during the validation
        process, the validation result object will be None.

        :param result: True if the validation process was successful, else False.
        :type result: bool
        """
        if result:
            rule_results = [
                rule_validator.result
                for rule_validator in self._applicable_rule_validators
            ]
            self._result = ValidationResult(rule_results, self.MODEL_COMPONENT_TYPE)
            self._feedback.validation_completed.emit(self._result)
            self.log("Validation complete.")


class NcsDataValidator(DataValidator):
    """Validates both NCS pathway and carbon layer datasets. The resolution
    check for carbon layers is tagged as a warning rather than an error.
    """

    MODEL_COMPONENT_TYPE = ModelComponentType.NCS_PATHWAY
    NAME = "NCS Data Validator"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model_components = kwargs.pop("ncs_pathways", list)
        self._initialize_rule_validators()

    def _initialize_rule_validators(self):
        """Add rule validators."""
        # Raster data type validator
        self._raster_type_validator = DataValidator.create_rule_validator(
            RuleType.DATA_TYPE, raster_validation_config, self.feedback
        )
        self.add_rule_validator(self._raster_type_validator)

        # Same CRS validator
        self._crs_validator = DataValidator.create_rule_validator(
            RuleType.CRS, crs_validation_config, self.feedback
        )
        self.add_rule_validator(self._crs_validator)

        # Projected CRS validator
        self._projected_crs_validator = DataValidator.create_rule_validator(
            RuleType.PROJECTED_CRS, projected_crs_validation_config, self.feedback
        )
        self.add_rule_validator(self._projected_crs_validator)

        # NoData value validator
        self._no_data_validator = DataValidator.create_rule_validator(
            RuleType.NO_DATA_VALUE, no_data_validation_config, self.feedback
        )
        self.add_rule_validator(self._no_data_validator)

        # Spatial resolution
        self._spatial_resolution_validator = DataValidator.create_rule_validator(
            RuleType.RESOLUTION, resolution_validation_config, self.feedback
        )
        self.add_rule_validator(self._spatial_resolution_validator)

        # Carbon resolution
        self._carbon_resolution_validator = DataValidator.create_rule_validator(
            RuleType.CARBON_RESOLUTION,
            carbon_resolution_validation_config,
            self.feedback,
        )
        self.add_rule_validator(self._carbon_resolution_validator)
