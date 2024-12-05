# -*- coding: utf-8 -*-

""" Data models for report production."""

import dataclasses
import typing
from uuid import UUID

from qgis.core import QgsFeedback, QgsRectangle

from cplus_core.models.base import Scenario, ScenarioResult


@dataclasses.dataclass
class BaseReportContext:
    """Common context information for generating a scenario report."""

    template_path: str
    name: str
    project_file: str
    feedback: QgsFeedback


@dataclasses.dataclass
class ReportContext(BaseReportContext):
    """Context information for generating a scenario analysis report."""

    scenario: Scenario
    scenario_output_dir: str
    output_layer_name: str


@dataclasses.dataclass
class ReportSubmitStatus:
    """Result of report submission process."""

    status: bool
    feedback: QgsFeedback
    identifier: str


@dataclasses.dataclass
class ReportResult:
    """Detailed result information from a report generation
    run.
    """

    success: bool
    scenario_id: UUID
    output_dir: str
    # Error messages
    messages: typing.Tuple[str] = dataclasses.field(default_factory=tuple)
    # Layout name
    name: str = ""
    base_file_name: str = ""

    @property
    def pdf_path(self) -> str:
        """Returns the absolute path to the PDF file if the process
        completed successfully.

         Caller needs to verify if the file actually exists in the
         given location.

         :returns: Absolute path to the PDF file if the process
        completed successfully else an empty string.
        :rtype: str
        """
        if not self.output_dir or not self.base_file_name:
            return ""

        return f"{self.output_dir}/{self.base_file_name}.pdf"


@dataclasses.dataclass
class ScenarioComparisonReportContext(BaseReportContext):
    """Contextual information related to the generation of scenario
    comparison report.
    """

    results: typing.List[ScenarioResult]
    output_dir: str


@dataclasses.dataclass
class ScenarioAreaInfo:
    """Contains information on the result of calculating a
    scenario's area.
    """

    name: str
    identifier: UUID
    area: dict = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class RepeatAreaDimension:
    """Contains information for rendering repeat model items
    such as scenarios or activities in a CPlus repeat item.
    """

    rows: int
    columns: int
    width: float
    height: float
