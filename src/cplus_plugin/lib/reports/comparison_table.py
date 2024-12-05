# -*- coding: utf-8 -*-
"""Scenario comparison table information."""

from numbers import Number
import typing

from qgis.core import (
    QgsBasicNumericFormat,
    QgsFeedback,
    QgsLayoutTableColumn,
    QgsProcessingMultiStepFeedback,
    QgsProcessingFeedback,
    QgsTableCell,
)
from qgis.PyQt import QtCore, QtGui

from cplus_core.models.base import ScenarioResult
from ...models.helpers import layer_from_scenario_result
from ...models.report import ScenarioAreaInfo
from ...utils import calculate_raster_value_area, log, tr


class ScenarioComparisonTableInfo(QtCore.QObject):
    """Get area information for the scenarios in the corresponding
    ScenarioResult objects and uses this information to generate
    QgsLayoutTableColumn and QgsTableCell objects for use in a
    scenario comparison table.
    """

    NOT_AVAILABLE_STR = "-"
    AREA_DECIMAL_PLACES = 2

    area_calculated = QtCore.pyqtSignal(ScenarioAreaInfo)

    def __init__(self, results: typing.List[ScenarioResult], parent=None):
        super().__init__(parent)

        self._scenario_results = results
        self._activity_header_info = []
        self._scenario_activity_name_pixel = {}
        self._contents = []
        self._area_calculated = False
        self._area_feedback = QgsProcessingFeedback()
        self._multistep_area_feedback = QgsProcessingMultiStepFeedback(
            len(results), self._area_feedback
        )

        # Extract the header information and populate mapping of activity
        # pixel value with the corresponding name
        for result in self._scenario_results:
            name_pixel_mapping = {}
            for pixel_value, activity in enumerate(
                result.scenario.weighted_activities, 1
            ):
                activity_info = (str(activity.uuid), activity.name)
                name_pixel_mapping[pixel_value] = activity.name
                if activity_info in self._activity_header_info:
                    continue
                self._activity_header_info.append(activity_info)

            self._scenario_activity_name_pixel[
                result.scenario.uuid
            ] = name_pixel_mapping

    @property
    def feedback(self) -> QgsProcessingFeedback:
        """Returns a feedback object for updating or canceling the
        process of area calculation.

        :returns: Feedback for updating or canceling the process.
        :rtype: QgsProcessingFeedback
        """
        return self._area_feedback

    @property
    def columns(self) -> typing.List[QgsLayoutTableColumn]:
        """Headers for the scenario comparison table.

        The columns start with one titled 'Scenario' which will contain
        the scenario name in the rows.

        :returns: Table headers based on the activities in the scenarios.
        :rtype: list
        """
        columns = []

        scenario_name_column = QgsLayoutTableColumn(tr("Scenario"))
        columns.append(scenario_name_column)

        for activity_header in self._activity_header_info:
            activity_column = QgsLayoutTableColumn(activity_header[1])
            columns.append(activity_column)

        return columns

    def contents(self) -> typing.List[typing.List[QgsTableCell]]:
        """Calculates the area of scenario layers and creates the
        corresponding table rows for use in a QgsLayoutTable
        derivative.

        The `area_calculated` signal is emitted once for every scenario
        area calculated or acquired using alternative mechanisms.

        This function is idempotent and will only return the
        results from the first call. Subsequent calls will return
        the same result.

        :returns: A nested list containing area information for
        each scenario.
        :rtype: list
        """
        if self._area_calculated:
            return self._contents

        result_data = []

        current_step = 0
        self._multistep_area_feedback.setCurrentStep(current_step)

        for result in self._scenario_results:
            if self._area_feedback.isCanceled():
                return self._contents

            layer = layer_from_scenario_result(result)
            if layer is None:
                msg = (
                    f"Unable to calculate area for scenario comparison a"
                    f"s layer for {result.scenario.name} could not "
                    f"be created."
                )
                log(msg)

                current_step += 1
                self._multistep_area_feedback.setCurrentStep(current_step)
                continue

            area_info = calculate_raster_value_area(
                layer, feedback=self._multistep_area_feedback
            )
            int_area_info = {
                int(pixel_value): area for pixel_value, area in area_info.items()
            }
            scenario_area_info = ScenarioAreaInfo(
                result.scenario.name, result.scenario.uuid, int_area_info
            )

            # Remap activity pixel value with the name for the calculated area
            activity_pixel_name_info = self._scenario_activity_name_pixel[
                result.scenario.uuid
            ]
            activity_name_area_info = {
                activity_pixel_name_info[pixel_value]: area
                for pixel_value, area in int_area_info.items()
            }

            self.area_calculated.emit(scenario_area_info)

            if len(int_area_info) == 0:
                msg = "No activity areas from the calculation"
                log(msg)

            row_data = []
            row_data.append(QgsTableCell(result.scenario.name))
            for header_info in self._activity_header_info:
                activity_name = header_info[1]
                if activity_name in activity_name_area_info:
                    activity_area = activity_name_area_info[activity_name]
                else:
                    activity_area = self.NOT_AVAILABLE_STR

                area_cell = QgsTableCell(activity_area)
                area_cell.setHorizontalAlignment(QtCore.Qt.AlignHCenter)
                if isinstance(activity_area, Number):
                    number_format = QgsBasicNumericFormat()
                    number_format.setThousandsSeparator(",")
                    number_format.setShowTrailingZeros(True)
                    number_format.setNumberDecimalPlaces(self.AREA_DECIMAL_PLACES)
                    area_cell.setNumericFormat(number_format)

                row_data.append(area_cell)

            result_data.append(row_data)

            current_step += 1
            self._multistep_area_feedback.setCurrentStep(current_step)

        self._contents = result_data
        self._area_calculated = True

        return self._contents
