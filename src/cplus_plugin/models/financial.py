# -*- coding: utf-8 -*-

""" Data models for the financial elements of the tool."""

import dataclasses
from enum import IntEnum
import typing

from .base import Activity


@dataclasses.dataclass
class NpvParameters:
    """Parameters for computing an activity's NPV."""

    years: int
    discount: float
    absolute_npv: float = 0.0
    normalized_npv: float = 0.0
    # Each tuple contains 3 elements i.e. revenue, costs and discount rates
    yearly_rates: typing.List[tuple] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ActivityNpv:
    """Mapping of the NPV parameters to the corresponding Activity model."""

    params: NpvParameters
    enabled: bool
    activity: typing.Optional[Activity]

    @property
    def activity_id(self) -> str:
        """Gets the identifier of the activity model.

        :returns: The unique identifier of the activity model else an
        empty string if no activity has been set.
        """
        if not self.activity:
            return ""

        return str(self.activity.uuid)


@dataclasses.dataclass
class ActivityNpvCollection:
    """Collection for all ActivityNpvMapping configurations that have been
    specified by the user.
    """

    minimum_value: float
    maximum_value: float
    use_computed: bool = True
    remove_existing: bool = False
    mappings: typing.List[ActivityNpv] = dataclasses.field(default_factory=list)

    def activity_npv(self, activity_identifier: str) -> typing.Optional[ActivityNpv]:
        """Gets the mapping of an activity's NPV mapping if defined.

        :param activity_identifier: Unique identifier of an activity whose
        NPV mapping is to be retrieved.
        :type activity_identifier: str

        :returns: The activity's NPV mapping else None if not found.
        :rtype: ActivityNpv
        """
        matching_mapping = [
            activity_npv
            for activity_npv in self.mappings
            if activity_npv.activity_id == activity_identifier
        ]

        return None if len(matching_mapping) == 0 else matching_mapping[0]

    def update_computed_normalization_range(self) -> bool:
        """Update the minimum and maximum normalization values
        based on the absolute values of the existing ActivityNpv
        objects.

        :returns: True if the min/max values were updated else False if
        there are no mappings or valid absolute NPV values defined.
        """
        if len(self.mappings) == 0:
            return False

        valid_npv_values = [
            activity_npv.params.absolute_npv
            for activity_npv in self.mappings
            if activity_npv.params.absolute_npv
        ]
        if len(valid_npv_values) == 0:
            return False

        self.minimum_value = min(valid_npv_values)
        self.maximum_value = max(valid_npv_values)

        return True

    def normalize_npvs(self) -> bool:
        """Normalize the NPV values of the activities using the specified
        normalization range.

        If the absolute NPV values are less than or greater than the
        normalization range, then they will be truncated to 0.0 and 1.0
        respectively. To avoid such a situation from occurring, it is recommended
        to make sure that the ranges are synchronized using the latest absolute
        NPV values.

        :returns: True if the NPVs were successfully normalized else False due
        to various reasons such as if the minimum value is greater than the
        maximum value or if the min/max values are the same.
        """
        if self.minimum_value > self.maximum_value:
            return False

        norm_range = float(self.maximum_value - self.minimum_value)

        if norm_range == 0.0:
            return False

        for activity_npv in self.mappings:
            absolute_npv = activity_npv.params.absolute_npv
            if not absolute_npv:
                continue

            if absolute_npv <= self.minimum_value:
                normalized_npv = 0.0
            elif absolute_npv >= self.maximum_value:
                normalized_npv = 1.0
            else:
                normalized_npv = (absolute_npv - self.minimum_value) / norm_range

            activity_npv.params.normalized_npv = normalized_npv

        return True
