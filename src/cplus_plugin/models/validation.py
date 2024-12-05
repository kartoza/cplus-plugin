# -*- coding: utf-8 -*-

""" Data models for validation of input datasets for generating scenarios."""

import dataclasses
from enum import IntEnum
import typing

from cplus_core.models.base import ModelComponentType


class RuleType(IntEnum):
    """Types of validation that will be performed on the data."""

    CRS = 0
    DATA_TYPE = 1
    NO_DATA_VALUE = 2
    RESOLUTION = 3
    CARBON_RESOLUTION = 4
    PROJECTED_CRS = 5


class ValidationCategory(IntEnum):
    """Classification type of the validation."""

    ERROR = 0
    WARNING = 1


@dataclasses.dataclass
class RuleConfiguration:
    """Context information for configuring a data validator."""

    category: ValidationCategory
    description: str
    rule_name: str
    recommendation: str = ""


@dataclasses.dataclass
class SubmitResult:
    """Contains information on the status of submitting a set of
    layers for validation.
    """

    identifier: str
    success: bool
    feedback: "ValidationFeedback" = None


@dataclasses.dataclass
class RuleInfo:
    """Contains summary information on the rule type and corresponding
    friendly rule name (which is synced with the one in the
    RuleConfiguration object).
    """

    type: RuleType
    name: str


@dataclasses.dataclass
class RuleResult:
    """Contains information on the result of validating a single rule."""

    config: "RuleConfiguration"
    recommendation: str
    summary: str
    validate_info: typing.List[tuple] = dataclasses.field(default_factory=list)

    @property
    def success(self) -> bool:
        """Whether the result contains any warnings or errors depending
        on the rule configuration.

         :returns: True if there are no errors or warnings depending on the
         rule configuration, else False.
        :rtype: bool
        """
        return True if len(self.validate_info) == 0 else False

    @property
    def category(self) -> ValidationCategory:
        """Returns the validation category of the specified rule.

        :returns: Validation category of the specified rule.
        :rtype: ValidationCategory
        """
        return self.config.category


@dataclasses.dataclass
class ValidationResult:
    """Contains information on the result of validating multiple rules i.e.
    an aggregation of RuleResult objects.
    """

    rule_results: typing.List[RuleResult] = dataclasses.field(default_factory=list)
    component_type: ModelComponentType = ModelComponentType.UNKNOWN

    @property
    def errors(self) -> typing.List[RuleResult]:
        """Returns RuleResult objects that are of ERROR category and
        contain one or more error messages.

        :returns: RuleResult objects that are of ERROR category and
        contain one or mor error messages.
        :rtype: list
        """
        return [
            result
            for result in self.rule_results
            if not result.success and result.category == ValidationCategory.ERROR
        ]

    @property
    def warnings(self) -> typing.List[RuleResult]:
        """Returns RuleResult objects that are of WARNING category and
        contain one or more error messages.

        :returns: RuleResult objects that are of WARNING category and
        contain one or mor error messages.
        :rtype: list
        """
        return [
            result
            for result in self.rule_results
            if not result.success and result.category == ValidationCategory.WARNING
        ]

    @property
    def success(self) -> bool:
        """Whether the result contains any warnings or errors based on
        the individual rule results.

         :returns: True if there are no errors or warnings for any of the
         RuleResult objects, else False.
        :rtype: bool
        """
        return True if len(self.warnings) == 0 and len(self.errors) == 0 else False

    def __len__(self) -> int:
        """Gets the number of rule results in the object.

        :returns: The number of rule results in the object.
        :rtype: int
        """
        return len(self.rule_results)

    def __iter__(self):
        """Returns an iterable object containing the individual rule results."""
        return iter(self.rule_results)
