# -*- coding: utf-8 -*-
"""
Registers custom report variables for layout design
and handles report generation.
"""

import datetime
import os
from pathlib import Path
from functools import partial
import typing

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsFeedback,
    QgsMasterLayoutInterface,
    QgsProject,
    QgsPrintLayout,
    QgsTask,
)
from qgis.gui import QgsLayoutDesignerInterface
from qgis.utils import iface

from qgis.PyQt import QtCore, QtGui

from ...conf import settings_manager, Settings
from ...definitions.constants import COMPARISON_REPORT_SEGMENT
from ...definitions.defaults import (
    DEFAULT_BASE_COMPARISON_REPORT_NAME,
    SCENARIO_ANALYSIS_TEMPLATE_NAME,
    SCENARIO_COMPARISON_TEMPLATE_NAME,
)
from cplus_core.models.base import Scenario, ScenarioResult
from ...models.report import (
    ReportContext,
    ReportResult,
    ReportSubmitStatus,
    ScenarioComparisonReportContext,
)
from ...utils import clean_filename, FileUtils, log, tr

from .generator import (
    ScenarioAnalysisReportGeneratorTask,
    ScenarioComparisonReportGeneratorTask,
)
from .variables import LayoutVariableRegister


class ReportManager(QtCore.QObject):
    """Registers custom report variables for
    layout design and handles report generation.
    """

    generate_started = QtCore.pyqtSignal(str)
    generate_error = QtCore.pyqtSignal(str)
    generate_completed = QtCore.pyqtSignal(str)

    # Max number of comparison report tasks
    COMPARISON_REPORT_LIMIT = 3

    def __init__(self, parent=None):
        super().__init__(parent)

        self.iface = iface
        self._variable_register = LayoutVariableRegister()
        self.report_name = tr("Scenario Analysis Report")

        # Task id (value) indexed by scenario id (key)
        self._report_tasks = {}

        # Report results (value) indexed by scenario id (key)
        self._report_results = {}

        # Flag for checking number of comparison report tasks
        self._running_comparison_tasks = 0

        self.task_manager = QgsApplication.instance().taskManager()
        self.task_manager.statusChanged.connect(self.on_task_status_changed)

        # Set default zoom when a report is opened
        self.iface.layoutDesignerOpened.connect(self.on_layout_designer_opened)

        self.root_output_dir = ""

    @property
    def variable_register(self) -> LayoutVariableRegister:
        """Get the instance of the variable register used
        for the management of variables.

        :returns: The register for managing variables in
        report layout scope.
        :rtype: LayoutVariableRegister
        """
        return self._variable_register

    def register_variables(self, layout: QgsPrintLayout):
        """Registers custom variables and their corresponding
        initial values in the layout.

        :param layout: Layout object where the custom
        variables will be registered.
        :type layout: QgsPrintLayout
        """
        self._variable_register.register_variables(layout)

    def task_by_id(self, task_id: int) -> typing.Optional[QgsTask]:
        """Gets the task using its identifier.

        :param task_id: Task identifier.
        :type task_id: int

        :returns: The tas corresponding to the given ID or
        None if not found.
        :rtype: QgsTask
        """
        return self.task_manager.task(task_id)

    def scenario_by_task_id(self, task_id: int) -> str:
        """Gets the scenario identifier for the report generation t
        ask with the given ID.

        :param task_id: ID of the task whose corresponding scenario
        is to be retrieved.
        :type task_id: int

        :returns: Scenario identifier whose report is being generated
        by a process with the given task id or an empty string if
        there was no match.
        :rtype: str
        """
        scenario_ids = [
            sid for sid, tid in self._report_tasks.items() if tid == task_id
        ]
        if len(scenario_ids) == 0:
            return ""

        return scenario_ids[0]

    def on_task_status_changed(self, task_id: int, status: QgsTask.TaskStatus):
        """Slot raised when the status of a task has changed.

        This function will emit when the report generation task has started
        or when it has completed successfully or terminated due to an error.

        :param task_id: ID of the task.
        :type task_id: int

        :param status: New task status.
        :type status: QgsTask.TaskStatus
        """
        scenario_id = self.scenario_by_task_id(task_id)

        # Not related to CPLUS scenario analysis report
        if not scenario_id:
            return

        if status == QgsTask.TaskStatus.Running:
            self.generate_started.emit(scenario_id)

        elif status == QgsTask.TaskStatus.Complete:
            # Get result
            task = self.task_manager.task(task_id)
            result = task.result
            if result is not None:
                self._report_results[scenario_id] = result

            # Remove task
            self.remove_report_task(scenario_id)

            self.generate_completed.emit(scenario_id)

    def remove_report_task(self, scenario_id: str) -> bool:
        """Remove report task associated with the given scenario.

        :param scenario_id: Identified of the scenario whose report
        generation process is to be removed.
        :type scenario_id: str

        :returns: True if the task has been successfully removed
        else False if there is no associated task for the given
        scenario.
        :rtype: bool
        """
        if scenario_id not in self._report_tasks:
            return False

        task_id = self._report_tasks[scenario_id]
        task = self.task_manager.task(task_id)
        if task is None:
            return False

        if (
            task.status() != QgsTask.TaskStatus.Complete
            or task.status() != QgsTask.TaskStatus.Terminated
        ):
            task.cancel()

        _ = self._report_tasks.pop(scenario_id)

        return True

    def remove_task_by_result(self, submit_result: ReportSubmitStatus) -> bool:
        """Remove a report task based on the submit result.

        :param submit_result: Submit result information.
        :type submit_result: ReportSubmitStatus

        :returns: True if the task has been successfully removed
        else False if there is no associated task for the given
        submit result.
        :rtype: bool
        """
        for scenario_id, task_id in self._report_tasks.items():
            if int(submit_result.identifier) == task_id:
                self.remove_report_task(scenario_id)
                return True

        task = self.task_by_id(int(submit_result.identifier))
        if task is None:
            return False

        if (
            task.status() != QgsTask.TaskStatus.Complete
            or task.status() != QgsTask.TaskStatus.Terminated
        ):
            submit_result.feedback.cancel()
            task.cancel()
            return True

        return False

    def create_scenario_dir(self, scenario: Scenario) -> str:
        """Creates an output directory (within BASE_DIR) for saving the
        analysis outputs for the given scenario.

        :param scenario: Reference scenario object.
        :type scenario: Scenario

        :returns: The absolute path to the output directory. If
        BASE_DIR does not exist, it will not create the directory and
        will return an empty string. If the current user does not have
        write permissions to the base directory, it will return an
        empty string.
        :rtype: str
        """
        if not self.root_output_dir:
            return ""

        output_path = Path(self.root_output_dir)
        if not output_path.exists():
            try:
                output_path.mkdir()
            except FileNotFoundError:
                msg = (
                    "Missing parent directory when creating "
                    "outputs subdirectory in the base directory."
                )
                log(msg)
                return ""

        scenario_path_str = f"{self.root_output_dir}/{str(scenario.uuid)}"
        scenario_output_path = Path(scenario_path_str)
        if not scenario_output_path.exists():
            try:
                scenario_output_path.mkdir()
            except FileNotFoundError:
                msg = (
                    "Missing parent directory when creating "
                    "scenario subdirectory in the outputs directory."
                )
                log(msg)
                return ""

        return scenario_path_str

    def generate(
        self, scenario_result: ScenarioResult, feedback: QgsFeedback = None
    ) -> ReportSubmitStatus:
        """Initiates the report generation process using information
        resulting from the scenario analysis.

        :param scenario_result: Contains details from the scenario analysis.
        :type scenario_result: ScenarioResult

        :param feedback: Feedback for reporting back to the main application.
        If one is not specified then the manager will create one for the context.
        :type feedback: QgsFeedback

        :returns: True if the report generation process was successfully
        submitted else False if a running process is re-submitted. Object
        also contains feedback object for report updating and cancellation.
        :rtype: ReportSubmitStatus
        """
        if not scenario_result.output_layer_name:
            log(
                "Layer name for output scenario is empty. Cannot generate report_templates."
            )
            return ReportSubmitStatus(False, None, "")

        if feedback is None:
            feedback = QgsFeedback(self)

        ctx = self.create_report_context(scenario_result, feedback)
        if ctx is None:
            log("Could not create report context. Check directory settings.")
            return ReportSubmitStatus(False, None, "")

        scenario_id = str(ctx.scenario.uuid)
        if scenario_id in self._report_tasks:
            return ReportSubmitStatus(False, ctx.feedback, "")

        msg_tr = tr("Generating report for")
        description = f"{msg_tr} {ctx.scenario.name}"
        report_task = ScenarioAnalysisReportGeneratorTask(description, ctx)

        report_task_completed = partial(self.report_task_completed, report_task)

        report_task.taskCompleted.connect(report_task_completed)
        report_task.taskTerminated.connect(report_task_completed)

        task_id = self.task_manager.addTask(report_task)

        self._report_tasks[scenario_id] = task_id

        return ReportSubmitStatus(True, ctx.feedback, str(task_id))

    def report_task_completed(self, task):
        if len(task._result.messages) > 0:
            self.generate_error.emit(",".join(task._result.messages))

    def report_result(self, scenario_id: str) -> typing.Union[ReportResult, None]:
        """Gets the report result for the scenario with the given ID.

        :param scenario_id: Identifier of the scenario whose report is to
        be retrieved.
        :type scenario_id: str

        :returns: Result of the report generation process. Caller needs to
        check if the process was successful or there was an error by checking
        the status of the `success` attribute. For scenarios that had not
        been submitted for report generation, a None object will be
        returned.
        :rtype: ReportResult
        """
        if scenario_id not in self._report_results:
            return None

        return self._report_results[scenario_id]

    @classmethod
    def create_report_context(
        cls, scenario_result: ScenarioResult, feedback: QgsFeedback
    ) -> typing.Optional[ReportContext]:
        """Creates the report context for use in the report
        generator task.

        :param scenario_result: Result of the scenario analysis.
        :type scenario_result: ScenarioResult

        :param feedback: Feedback object for reporting back to the main
        application.
        :type feedback: QgsFeedback

        :returns: A report context object containing the information
        for generating the report else None if it could not be created.
        :rtype: ReportContext
        """
        output_dir = os.path.normpath(scenario_result.scenario_directory)
        if not output_dir or not Path(output_dir).exists():
            log(f"Unable to generate the report. {output_dir} not found.\n")
            return None

        scenario_report_dir = os.path.normpath(f"{output_dir}/reports")
        FileUtils.create_new_dir(scenario_report_dir)

        cleaned_scenario_name = clean_filename(scenario_result.scenario.name)
        project_file_path = os.path.join(
            scenario_report_dir, f"{cleaned_scenario_name}.qgz"
        )
        if os.path.exists(project_file_path):
            counter = 1
            while True:
                project_file_path = os.path.join(
                    scenario_report_dir,
                    f"{scenario_result.scenario.name}_{counter!s}.qgz",
                )
                if not os.path.exists(project_file_path):
                    break
                counter += 1

        # Write project to file for use in the task since QgsProject
        # instances are not thread safe.
        result = cls._save_current_project(project_file_path)
        if not result:
            return None

        # Set base name for the layout and PDF file suffixed with a number
        # depending on the number of runs.
        layout_manager = QgsProject.instance().layoutManager()
        counter = 1
        context_name = ""
        while True:
            layout_name = f"{scenario_result.scenario.name} {counter!s}"
            matching_layout = layout_manager.layoutByName(layout_name)
            if matching_layout is None:
                context_name = layout_name
                break
            counter += 1

        template_path = FileUtils.report_template_path(SCENARIO_ANALYSIS_TEMPLATE_NAME)

        return ReportContext(
            template_path=template_path,
            scenario=scenario_result.scenario,
            name=context_name,
            scenario_output_dir=scenario_report_dir,
            project_file=project_file_path,
            feedback=feedback,
            output_layer_name=scenario_result.output_layer_name,
        )

    @classmethod
    def _save_current_project(cls, project_file_path):
        """Saves the current project."""
        storage_type = QgsProject.instance().filePathStorage()
        QgsProject.instance().setFilePathStorage(Qgis.FilePathType.Absolute)
        result = QgsProject.instance().write(project_file_path)
        QgsProject.instance().setFilePathStorage(storage_type)

        return result

    def open_layout_designer(self, result: ReportResult) -> bool:
        """Opens the analysis report in the layout designer. The
        layout needs to exist in the currently loaded project.

        :param result: Result object from the report generation
        process.
        :type result: ReportResult

        :returns: True if the layout was successfully loaded, else
        False if the result from the generation process was False
        or if the layout does not exist in the current project.
        :rtype: bool
        """
        if not result.success:
            return False

        layout = QgsProject.instance().layoutManager().layoutByName(result.name)
        if layout is None:
            return False

        _ = self.iface.openLayoutDesigner(layout)

        return True

    def generate_comparison_report(
        self,
        scenario_results: typing.List[ScenarioResult],
        feedback: QgsFeedback = None,
    ) -> ReportSubmitStatus:
        """Generates a report comparing the two or more scenarios.

        :param scenario_results: Collection of scenario results to be compared.
        :type scenario_results: list

        :param feedback: Feedback object for reporting back to the main
        application. Default is None.
        :type feedback: QgsFeedback

        :returns: True if the report generation process was successfully
        submitted else False if a running process is re-submitted. Object
        also contains feedback object for report updating and cancellation.
        :rtype: ReportSubmitStatus
        """
        if self._running_comparison_tasks == self.COMPARISON_REPORT_LIMIT:
            log("Reached limit of comparison report processes, try again later.")
            return ReportSubmitStatus(False, None, "")

        if feedback is None:
            feedback = QgsFeedback(self)

        comparison_context = self.create_comparison_report_context(
            scenario_results, feedback
        )
        if comparison_context is None:
            return ReportSubmitStatus(False, None, "")

        description = tr("Generating scenario comparison report")
        task = ScenarioComparisonReportGeneratorTask(description, comparison_context)
        task.statusChanged.connect(self.on_comparison_task_status_changed)
        task_id = self.task_manager.addTask(task)

        return ReportSubmitStatus(True, feedback, str(task_id))

    def on_comparison_task_status_changed(self, status: int):
        """Slot raised when the comparison task status has changed.

        :param status: Task status:
        :type status: int
        """
        if status == QgsTask.TaskStatus.Running:
            self._running_comparison_tasks += 1
        elif status in (QgsTask.TaskStatus.Complete, QgsTask.TaskStatus.Terminated):
            self._running_comparison_tasks -= 1

    @classmethod
    def create_comparison_report_context(
        cls, scenario_results: typing.List[ScenarioResult], feedback: QgsFeedback
    ) -> typing.Optional[ScenarioComparisonReportContext]:
        """Create contextual information for generating the scenario comparison report.

        :param scenario_results: Collection of scenario results to be compared.
        :type scenario_results: list

        :param feedback: Feedback object for reporting back to the main
        application.
        :type feedback: QgsFeedback
        """
        base_dir = settings_manager.get_value(Settings.BASE_DIR)
        if base_dir is None:
            log(f"Base directory is empty, unable to generate comparison report.")
            return None

        FileUtils.create_comparison_reports_dir(base_dir)

        folder_name = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        report_dir = os.path.normpath(
            f"{base_dir}/{COMPARISON_REPORT_SEGMENT}/{folder_name}"
        )
        FileUtils.create_new_dir(report_dir)

        project_file_path = os.path.join(report_dir, f"{COMPARISON_REPORT_SEGMENT}.qgz")
        # Save project file.
        result = cls._save_current_project(project_file_path)
        if not result:
            log(f"Unable to save the project for scenario report generation.")
            return None

        layout_name = f"{DEFAULT_BASE_COMPARISON_REPORT_NAME} {folder_name}"

        template_path = FileUtils.report_template_path(
            SCENARIO_COMPARISON_TEMPLATE_NAME
        )

        return ScenarioComparisonReportContext(
            template_path=template_path,
            name=layout_name,
            project_file=project_file_path,
            feedback=feedback,
            results=scenario_results,
            output_dir=report_dir,
        )

    def on_layout_designer_opened(self, designer: QgsLayoutDesignerInterface):
        """Sets a default zoom level for the report when opened for
        the first time.
        """
        layout_type = designer.masterLayout().layoutType()
        if layout_type == QgsMasterLayoutInterface.PrintLayout:
            layout = designer.layout()
            if self._variable_register.is_analysis_report(layout):
                view = designer.view()
                view.zoomActual()
                view.emitZoomLevelChanged()

    @classmethod
    def view_pdf(cls, result: ReportResult) -> bool:
        """Opens the analysis in the host's default PDF viewer.

        :param result: Result object from the report generation
        process.
        :type result: ReportResult

        :returns: True if the PDF was successfully loaded, else
        False if the result from the generation process was False.
        :rtype: bool
        """
        if not result.success:
            return False

        pdf_url = QtCore.QUrl.fromLocalFile(result.pdf_path)
        if pdf_url.isEmpty():
            return False

        return QtGui.QDesktopServices.openUrl(pdf_url)


report_manager = ReportManager()
