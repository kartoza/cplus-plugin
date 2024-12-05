# -*- coding: utf-8 -*-
"""
Manager for data validation processes.
"""

import typing

from qgis.core import (
    QgsApplication,
    QgsTask,
)

from qgis.PyQt import QtCore, sip

from cplus_core.models.base import ModelComponentType, NcsPathway
from ...models.helpers import clone_ncs_pathway
from ...models.validation import SubmitResult, ValidationResult
from .validators import NcsDataValidator


class ValidationManager(QtCore.QObject):
    """Manages the validation process including starting, cancelling
    or getting the status of running validation tasks.
    """

    validation_started = QtCore.pyqtSignal(str)
    validation_error = QtCore.pyqtSignal(str)
    validation_completed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data validator (value) indexed by task id (key)
        self._validation_tasks = {}

        # Validation results (value) indexed by task id (key)
        self._validation_results = {}

        self.task_manager = QgsApplication.instance().taskManager()
        self.task_manager.statusChanged.connect(self.on_validation_status_changed)

    def validate_ncs_pathways(
        self, pathways: typing.List[NcsPathway], cancel_running=True
    ) -> SubmitResult:
        """Validates a set of NcsPathway datasets and returns the status
        of the submission.

        :param pathways: A list of NcsPathway objects to be validated. At least one
        NcsPathway is required for the validation process to be executed.
        :type pathways: list

        :param cancel_running: True if any running validation processes are to be cancelled
        else False if multiple concurrent validation processes are to be executed.
        :type cancel_running: bool

        :returns: Result object containing the task id and status of the submission.
        :rtype: SubmitResult
        """
        if len(pathways) == 0:
            return SubmitResult("", False, None)

        if cancel_running:
            self.cancel_ncs_validation()

        # Clone the pathways
        cloned_pathways = list(map(clone_ncs_pathway, pathways))

        ncs_validator = NcsDataValidator()
        ncs_validator.model_components = cloned_pathways
        task_id = self.task_manager.addTask(ncs_validator)

        if task_id == 0:
            return SubmitResult("", False, None)

        self._validation_tasks[str(task_id)] = ncs_validator

        return SubmitResult(str(task_id), True, ncs_validator.feedback)

    def cancel_ncs_validation(self):
        """Cancel all validation processes of NCS pathway datasets."""
        for task_id in list(self._validation_tasks):
            ncs_validator = self._validation_tasks[task_id]
            # In some OSs, the underlying C++ task object is de-referenced
            # unexpectedly hence the need to check if it exists.
            if sip.isdeleted(ncs_validator):
                continue

            status = ncs_validator.status()
            if (
                status == QgsTask.TaskStatus.Running
                or status == QgsTask.TaskStatus.Queued
                or status == QgsTask.TaskStatus.OnHold
            ):
                ncs_validator.cancel()
                del self._validation_tasks[task_id]

    def on_validation_status_changed(self, task_id: int, status: QgsTask.TaskStatus):
        """Slot raised when the status of a validation task has changed.

        This function will emit when the validation task has started, when it
        has completed successfully or terminated due to an error.

        :param task_id: ID of the task.
        :type task_id: int

        :param status: New task status.
        :type status: QgsTask.TaskStatus
        """
        if status == QgsTask.TaskStatus.Running:
            self.validation_started.emit(str(task_id))

        elif status == QgsTask.TaskStatus.Complete:
            if str(task_id) not in self._validation_tasks:
                return

            # Get result
            validator = self.task_manager.task(task_id)
            result = validator.result
            if result is not None:
                self._validation_results[str(task_id)] = result

            # Remove task
            if str(task_id) in self._validation_tasks:
                del self._validation_tasks[str(task_id)]

            self.validation_completed.emit(str(task_id))

    def is_validation_complete(self, result: SubmitResult) -> bool:
        """Checks whether the validation process, based on the given
        submission result, is complete.

        :param result: Result of the request for validation.
        :type result: SubmitResult

        :returns: True if the validation process is complete, else
        False if it is still in progress or has failed.
        :rtype: bool
        """
        if not result.success:
            return False

        if result.identifier in self._validation_results:
            return True

        return False

    def validation_result(
        self, result: SubmitResult
    ) -> typing.Union[None, ValidationResult]:
        """Gets the validation result based on the given submission result.

        :param result: Result of the request for validation.
        :type result: SubmitResult

        :returns: Validation result if the process was complete else None
        if the submission or actual validation process failed.
        :rtype: ValidationResult
        """
        if not result.success:
            return None

        if result.identifier not in self._validation_results:
            return None

        return self._validation_results[result.identifier]

    def cancel(self, result: SubmitResult) -> bool:
        """Cancels a validation process matching the result of the submission.

        :param result: Result of the validation submission.
        :type result: SubmitResult

        :returns: True if the validation task was successfully cancelled
        else False if the submit results status was not successful or if
        the validation task was not found.
        :rtype: bool
        """
        if not result.success:
            return False

        if result.identifier not in self._validation_tasks:
            return False

        validator = self._validation_tasks[result.identifier]
        validator.cancel()

        del self._validation_tasks[result.identifier]

        return True

    def results_by_component_type(
        self, component_type: ModelComponentType
    ) -> typing.List[ValidationResult]:
        """Gets the validation results based on the model component
        type of the validator.

        :param component_type: Model component type e.g. NCS pathway.
        :type component_type: ModelComponentType

        :returns: A list containing the validation results for the given
        model component type or an empty list if no results are found.
        :rtype: list
        """
        if component_type == ModelComponentType.UNKNOWN:
            return []

        return [
            result
            for result in self._validation_results.values()
            if result.component_type == component_type
        ]

    def ncs_results(self) -> typing.List[ValidationResult]:
        """Gets the validation results for NCS pathways.

        :returns: A list containing the validation results for NCS
        pathways or an empty list if no results are found.
        :rtype: list
        """
        return self.results_by_component_type(ModelComponentType.NCS_PATHWAY)

    def last_ncs_result(self) -> typing.Union[ValidationResult, None]:
        """Gets the result of the last successful validation of NCS pathways.

        :returns: Result of the last successful NCS pathway validation.
        :rtype: ValidationResult
        """
        ncs_results = self.ncs_results()
        if len(ncs_results) == 0:
            return None

        return ncs_results[len(ncs_results) - 1]


validation_manager = ValidationManager()
