# -*- coding: utf-8 -*-
"""
Composite list view-based widgets for displaying activity
and NCS pathway items.
"""
import os
import typing

from qgis.PyQt import QtCore, QtWidgets
from qgis.PyQt.uic import loadUiType

from qgis.core import QgsApplication, QgsMapLayer

from .component_item_model import (
    ActivityItem,
    ActivityItemModel,
    ACTIVITY_TYPE,
    ComponentItemModel,
    ComponentItemModelType,
    LAYER_ITEM_TYPE,
    ModelComponentItem,
    ModelComponentItemType,
    NcsPathwayItem,
    NcsPathwayItemModel,
    NCS_PATHWAY_TYPE,
)
from ..conf import settings_manager
from .activity_editor_dialog import ActivityEditorDialog
from ..lib.validation.manager import validation_manager
from .model_description_editor import ModelDescriptionEditorDialog
from .ncs_pathway_editor_dialog import NcsPathwayEditorDialog
from .pixel_value_editor_dialog import PixelValueEditorDialog
from cplus_core.models.base import Activity, NcsPathway
from .validation.inspector_dialog import ValidationInspectorDialog
from .validation.progress_dialog import ValidationProgressDialog
from ..utils import FileUtils, log


WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/model_component_widget.ui")
)


class ModelComponentWidget(QtWidgets.QWidget, WidgetUi):
    """Widget for displaying and managing model items in a list view."""

    items_reloaded = QtCore.pyqtSignal()

    def __init__(self, parent=None, item_model=None):
        super().__init__(parent)
        self.setupUi(self)

        self._item_model = item_model
        if self._item_model is not None:
            self.item_model = self._item_model

        self.lst_model_items.doubleClicked.connect(self._on_double_click_item)

        add_icon = FileUtils.get_icon("symbologyAdd.svg")
        self.btn_add.setIcon(add_icon)
        self.btn_add.clicked.connect(self._on_add_item)

        remove_icon = FileUtils.get_icon("symbologyRemove.svg")
        self.btn_remove.setIcon(remove_icon)
        self.btn_remove.setEnabled(False)
        self.btn_remove.clicked.connect(self._on_remove_item)

        edit_icon = FileUtils.get_icon("mActionToggleEditing.svg")
        self.btn_edit.setIcon(edit_icon)
        self.btn_edit.setEnabled(False)
        self.btn_edit.clicked.connect(self._on_edit_item)

        reload_icon = FileUtils.get_icon("mActionReload.svg")
        self.btn_reload.setIcon(reload_icon)
        self.btn_reload.setToolTip(self.tr("Refresh view"))
        self.btn_reload.clicked.connect(self._on_reload)

        self.btn_edit_description.setIcon(edit_icon)
        self.btn_edit_description.setToolTip(self.tr("Edit description"))
        self.btn_edit_description.setEnabled(False)
        self.btn_edit_description.clicked.connect(self._on_update_description)

    @property
    def item_model(self) -> ComponentItemModelType:
        """Returns the component item model for managing items the list view.

        :returns: Component item model for managing items the list view.
        :rtype: ComponentItemModel
        """
        return self._item_model

    @item_model.setter
    def item_model(self, model: ComponentItemModelType):
        """Sets the component item model for managing items in the list view.

        :param model: The component item model for managing items.
        :type model: ComponentItemModel
        """
        if self._item_model is None:
            self._item_model = model
            self.lst_model_items.setModel(self._item_model)
            self.lst_model_items.selectionModel().selectionChanged.connect(
                self._on_selection_changed
            )

    @property
    def selection_model(self) -> QtCore.QItemSelectionModel:
        """Gets the item's view selection model.

        :returns: The item's view selection model.
        :rtype: QtCore.QItemSelectionModel
        """
        return self.lst_model_items.selectionModel()

    @property
    def title(self) -> str:
        """Returns the title of the view.

        :returns: Title of the view.
        :rtype: str
        """
        return self.lbl_title.text()

    @title.setter
    def title(self, text: str):
        """Sets the text tobe displayed in the title label of the view.

        :param text: Title of the view.
        :type text: str
        """
        self.lbl_title.setText(f"<b>{text}</b>")

    def load(self):
        """Subclass to determine how to initialize the items."""
        pass

    def _on_add_item(self):
        """Slot raised when add item button has been clicked.

        Default implementation does nothing. To be implemented by
        subclasses.
        """
        pass

    def _on_edit_item(self):
        """Slot raised when edit item button has been clicked.

        Default implementation does nothing. To be implemented by
        subclasses.
        """
        pass

    def _on_remove_item(self):
        """Slot raised when remove item button has been clicked.

        Default implementation does nothing. To be implemented by
        subclasses.
        """
        pass

    def _on_update_description(self):
        """Slot raised to edit the currently selected item."""
        sel_items = self.selected_items()
        if len(sel_items) == 0:
            return

        reference_item = sel_items[0]
        description_editor = ModelDescriptionEditorDialog(
            self, reference_item.description
        )
        title_tr = self.tr("Description Editor")
        description_editor.setWindowTitle(
            f"{reference_item.model_component.name} {title_tr}"
        )
        if description_editor.exec_() == QtWidgets.QDialog.Accepted:
            updated_description = description_editor.description
            reference_item.model_component.description = updated_description
            self.txt_item_description.setText(updated_description)
            self._save_item(reference_item)

    def _save_item(self, item: ComponentItemModelType):
        """Persist the changes in the underlying model for the given item.

        To be implemented by child classes as default implementation does
        nothing.
        """
        pass

    def set_description(self, description: str):
        """Updates the text for the selected item.

        :param description: Description for the selected item.
        :type description: str
        """
        self.txt_item_description.setText(description)
        self.txt_item_description.setToolTip(description)

    def clear_description(self):
        """Clears the content in the description text box."""
        self.txt_item_description.clear()
        self.txt_item_description.setToolTip("")

    def _on_selection_changed(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        """Slot raised when selection in the list view has changed.

        :param selected: Current item selection.
        :type selected: QtCore.QItemSelection

        :param deselected: Previously selected items that have been
        deselected.
        :type deselected: QtCore.QItemSelection
        """
        self._update_ui_on_selection_changed()

    def _on_double_click_item(self, index: QtCore.QModelIndex):
        """Slot raised when an item has been double-clicked.

        :param index: Index of the clicked item.
        :type index: QtCore.QModelIndex
        """
        if self._item_model is None:
            return

        item = self._item_model.itemFromIndex(index)
        if item is None:
            return

        if not item.isEnabled():
            return

        self._handle_double_click(item)

    def _handle_double_click(self, item: ModelComponentItemType):
        """Handle double-clicking of an item.

        To be implemented by sub-classes.

        :param item: Model component item that has received the
        double click event.
        :type item: ModelComponentItem
        """
        pass

    def _update_ui_on_selection_changed(self):
        """Update UI properties on selection changed."""
        self.btn_remove.setEnabled(True)
        self.btn_edit.setEnabled(True)
        self.btn_edit_description.setEnabled(True)

        # Remove description and disable edit and remove buttons if
        # more than one item has been selected.
        selected_items = self.selected_items()
        if len(selected_items) == 0 or len(selected_items) > 1:
            self.clear_description()
            self.btn_remove.setEnabled(False)
            self.btn_edit.setEnabled(False)
            self.btn_edit_description.setEnabled(False)
            return

        if not isinstance(selected_items[0], ModelComponentItem):
            return

        self.set_description(selected_items[0].description)

    def selected_items(self) -> typing.List[ModelComponentItemType]:
        """Returns the selected items in the list view.

        :returns: A collection of the selected model component items. Returns
        an empty list if the item model has not been set.
        :rtype: list
        """
        if self._item_model is None:
            return []

        selection_model = self.lst_model_items.selectionModel()
        idxs = selection_model.selectedRows()

        return [self._item_model.item(idx.row()) for idx in idxs]

    def clear(self):
        """Remove all items in the view. To be implemented
        by subclasses."""
        pass

    def _on_reload(self):
        """Slot raised when the reload button has been clicked.
        Default implementation is to call the load the items
        afresh.
        """
        self.load()
        self.items_reloaded.emit()

    def model_names(self) -> typing.List[str]:
        """Gets the names of the components in the item model.

        :returns: Returns the model names in lower case or an empty
        list if the item model has not been set.
        :rtype: list
        """
        if self._item_model is None:
            return []

        model_components = self._item_model.model_components()

        return [mc.name.lower() for mc in model_components]

    def enable_default_items(self, state: bool):
        """Enable or disable default model component items in the view.

        :param state: True to enable or False to disable default model
        component items.
        :type state: bool
        """
        self._item_model.enable_default_items(state)

        # If false, deselect default items
        if not state:
            selection_model = self.lst_model_items.selectionModel()
            selected_idxs = selection_model.selectedRows()
            for sel_idx in selected_idxs:
                item = self._item_model.item(sel_idx.row(), 0)
                # If not enabled then deselect
                if not item.isEnabled():
                    selection_model.select(sel_idx, QtCore.QItemSelectionModel.Deselect)

    def add_action_widget(self, widget: QtWidgets.QWidget):
        """Adds an auxiliary widget below the list view from the left-hand side.

        :param widget: Widget to be added to the collection of controls
        below the list view.
        :type widget: QtWidgets.QWidget
        """
        self.widget_container.addWidget(widget)


class NcsComponentWidget(ModelComponentWidget):
    """Widget for displaying and managing NCS pathways."""

    ncs_pathway_updated = QtCore.pyqtSignal(NcsPathway)
    ncs_pathway_removed = QtCore.pyqtSignal(str)
    items_reloaded = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Add option for deleting disabled items
        self.btn_remove.clicked.disconnect(self._on_remove_item)
        self._delete_menu = QtWidgets.QMenu()

        self._remove_default_action = self._delete_menu.addAction(
            FileUtils.get_icon("symbologyRemove.svg"), "Remove Selected"
        )
        self._remove_default_action.setEnabled(False)
        self._remove_default_action.triggered.connect(self._on_remove_item)

        self._remove_disabled_action = self._delete_menu.addAction(
            FileUtils.get_icon("repositoryDisabled.svg"), "Remove Disabled"
        )
        self._remove_disabled_action.setEnabled(False)
        self._remove_disabled_action.triggered.connect(self._on_remove_disabled)

        self.btn_remove.setMenu(self._delete_menu)
        self.btn_remove.setDefaultAction(self._remove_default_action)
        self.btn_remove.setPopupMode(QtWidgets.QToolButton.MenuButtonPopup)
        self.btn_remove.triggered.connect(self.on_delete_triggered)

        self.item_model = NcsPathwayItemModel(parent)
        self.item_model.itemChanged.connect(self.on_item_changed)

        self.lst_model_items.setDragEnabled(True)
        self.lst_model_items.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.lst_model_items.setAcceptDrops(False)

        self._validation_manager = validation_manager
        self._validation_submit_result = None

        self.btn_validate_pathways = None

        self.add_auxiliary_widgets()

    def on_delete_triggered(self, action: QtWidgets.QAction):
        """Slot raised to select the default delete action.

        :param action: Action that has been triggered.
        :type action: QtWidgets.QAction
        """
        self.btn_remove.setDefaultAction(action)

    def _on_remove_disabled(self):
        """Slot raised to remove disabled items."""
        disabled_items = self.item_model.disabled_items()
        self._remove_ncs_items(disabled_items)

    def _remove_ncs_items(self, ncs_items: typing.List[NcsPathwayItem]):
        """Remove the specified NCS pathway items.

        :param ncs_items: The NCS pathway items to be removed.
        :type ncs_items: list
        """
        if len(ncs_items) == 0:
            return

        ncs_models = []
        for item in ncs_items:
            ncs_models.append(item.ncs_pathway)

        if len(ncs_models) == 1:
            msg = self.tr(
                f"Do you want to remove '{ncs_models[0].name}'? The corresponding "
                f"NCS pathways used in the activities will "
                f"also be removed.\nClick Yes to proceed or No to cancel."
            )
        else:
            msg = self.tr(
                f"Do you want to remove the NCS pathways? The corresponding "
                f"NCS pathways used in the activities will "
                f"also be removed.\nClick Yes to proceed or No to cancel."
            )

        if (
            QtWidgets.QMessageBox.question(
                self,
                self.tr("Remove NCS Pathways"),
                msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            == QtWidgets.QMessageBox.Yes
        ):
            for ncs in ncs_models:
                self.item_model.remove_ncs_pathway(str(ncs.uuid))
                self.ncs_pathway_removed.emit(str(ncs.uuid))
                settings_manager.remove_ncs_pathway(str(ncs.uuid))

            self.clear_description()
            self.validate_pathways()

    def on_item_changed(self, item: NcsPathwayItem):
        """Slot raised when the data of an NCS pathway item changes.

        :param item: NCS pathway item whose data has changed.
        :type item: NcsPathwayItem
        """
        # Check if there are items disabled and enable or disable
        # the option for deleting disabled items.
        self._on_item_and_selection_changed()

    def _on_item_and_selection_changed(self):
        """Handles the enabling or disabling of NCS pathway delete controls
        based on the item selection as well as disabled items.
        """
        self._remove_default_action.setEnabled(False)
        self.btn_remove.setDefaultAction(self._remove_default_action)

        self.btn_edit.setEnabled(False)

        disabled_items = self.item_model.disabled_items()
        selected_items = self.selected_items()

        if len(selected_items) == 0 and len(disabled_items) == 0:
            return

        elif len(disabled_items) == 0 and len(selected_items) > 0:
            if len(selected_items) == 1:
                self.btn_edit.setEnabled(True)

            self.btn_remove.setEnabled(True)
            self._remove_default_action.setEnabled(True)
            self._remove_disabled_action.setEnabled(False)
            self.btn_remove.setDefaultAction(self._remove_default_action)

        elif len(disabled_items) > 0:
            self.btn_remove.setEnabled(True)
            self._remove_disabled_action.setEnabled(True)
            self._remove_default_action.setEnabled(False)
            self.btn_remove.setDefaultAction(self._remove_disabled_action)

    def add_ncs_pathway(self, ncs_pathway: NcsPathway) -> bool:
        """Adds an NCS pathway object to the view.

        :param ncs_pathway: NCS pathway object to be added to the view.
        :type ncs_pathway: NcsPathway

        :returns: Returns True if the NcsPathway was successfully added,
        else False.
        :rtype: bool
        """
        return self.item_model.add_ncs_pathway(ncs_pathway)

    def add_auxiliary_widgets(self):
        """Adds additional action widgets for managing NCS pathways."""
        self.btn_validate_pathways = QtWidgets.QToolButton(self)
        style_icon = FileUtils.get_icon("mIconRasterValidate.svg")
        self.btn_validate_pathways.setIcon(style_icon)
        self.btn_validate_pathways.setToolTip(self.tr("Show validation inspector"))
        self.btn_validate_pathways.clicked.connect(self.on_load_validation_inspector)
        self.add_action_widget(self.btn_validate_pathways)

    def clear(self):
        """Removes all NCS pathway items in the view."""
        items = self.ncs_items()
        for item in items:
            self.item_model.remove_ncs_pathway(item.uuid)

    def pathways(self, valid_only=False) -> typing.List[NcsPathway]:
        """Returns a collection of NcsPathway objects in the list view.

        :param valid_only: True to only return those NcsPathway objects that
        are valid, default is False.
        :type valid_only: bool

        :returns: Collection of NcsPathway objects in the list view.
        :rtype: list
        """
        return self.item_model.pathways(valid_only)

    def is_valid(self) -> bool:
        """Returns whether the NCS pathways are valid based on the validation against
        a given set of rules defined for an NCSValidator.

        The validation process is automatically triggered through the
        validation manager object.

        :returns: True if the NCS pathways are valid, else False. If the validation
        result has warnings and no errors, the overall results will be True. However,
        if there are errors, it will return False.
        :rtype: bool
        """
        if self._validation_submit_result is None:
            return False

        if not self._validation_submit_result.success:
            return False

        if self._validation_manager.is_validation_complete(
            self._validation_submit_result
        ):
            validation_result = self._validation_manager.validation_result(
                self._validation_submit_result
            )
            if validation_result.success:
                return True

            if validation_result.warnings and not validation_result.errors:
                return True

        return False

    def ncs_items(self) -> typing.List[NcsPathwayItem]:
        """Returns a collection of all NcsPathwayItem objects in the
        list view.

        :returns: Collection of NcsPathwayItem objects in the list view.
        :rtype: list
        """
        return self.item_model.model_component_items()

    def on_load_validation_inspector(self):
        """Slot raised to show the validation inspector dialog.

        If the validation process is not yet completed, a
        progress dialog will be shown.
        """
        if self._validation_submit_result is None:
            QtWidgets.QMessageBox.critical(
                self,
                self.tr("Load Validation Inspector"),
                self.tr(
                    "Unable to show the validation inspector window.\nNo request for validation has been submitted."
                ),
            )
            log(message="Unable to load validation inspector", info=False)
            return

        if self._validation_manager.is_validation_complete(
            self._validation_submit_result
        ):
            validation_result = self._validation_manager.validation_result(
                self._validation_submit_result
            )
            if validation_result is None:
                return

            self.inspector_dialog = ValidationInspectorDialog(result=validation_result)
            self.inspector_dialog.setModal(False)
            self.inspector_dialog.show()

        else:
            # Show progress dialog
            progress_dialog = ValidationProgressDialog(
                self._validation_submit_result, self
            )
            progress_dialog.exec_()

    def validate_pathways(self):
        """Validates NCS pathway model components against a given set of
        rules using the ValidationManager.
        """
        self._validation_submit_result = None

        ncs_pathways = self.pathways()
        # No need for validating if there are no NCS pathways.
        if len(ncs_pathways) == 0:
            log(
                message="At least one NCS pathway is required for the validation process to be initiated.",
                info=False,
            )
            return

        self._validation_submit_result = validation_manager.validate_ncs_pathways(
            ncs_pathways
        )
        if not self._validation_submit_result.success:
            QtWidgets.QMessageBox.critical(
                self,
                self.tr("Validate NCS Pathways"),
                self.tr("Unable to submit NCS pathways for validation"),
            )
            log(message="Unable to submit NCS pathways for validation", info=False)
            return

    def _on_add_item(self):
        """Show NCS pathway editor."""
        ncs_editor = NcsPathwayEditorDialog(self, excluded_names=self.model_names())
        if ncs_editor.exec_() == QtWidgets.QDialog.Accepted:
            ncs_pathway = ncs_editor.ncs_pathway
            result = self.item_model.add_ncs_pathway(ncs_pathway)
            if result:
                settings_manager.save_ncs_pathway(ncs_pathway)
                self.validate_pathways()

    def _on_edit_item(self):
        """Edit selected NCS pathway object."""
        selected_items = self.selected_items()
        if len(selected_items) == 0 or len(selected_items) > 1:
            return

        item = selected_items[0]
        self._edit_ncs_pathway_item(item)

    def _handle_double_click(self, item: NcsPathwayItem):
        """Show editor dialog.

        :param item: NCS pathway item receiving the event.
        :type item: NcsPathwayItem
        """
        self._edit_ncs_pathway_item(item)

    def _edit_ncs_pathway_item(self, item: NcsPathwayItem):
        """Shows dialog for editing an item."""
        # If editing, remove the current name of the model component
        excluded_names = self.model_names()
        excluded_names.remove(item.model_component.name.lower())
        ncs_editor = NcsPathwayEditorDialog(
            self, item.ncs_pathway, excluded_names=excluded_names
        )
        if ncs_editor.exec_() == QtWidgets.QDialog.Accepted:
            ncs_pathway = ncs_editor.ncs_pathway
            result = self.item_model.update_ncs_pathway(ncs_pathway)
            if result:
                self._save_item(item)
                self.ncs_pathway_updated.emit(ncs_pathway)
                self.validate_pathways()
            self._update_ui_on_selection_changed()

    def _save_item(self, item: NcsPathwayItem):
        """Update the NCS pathway in settings."""
        cloned_ncs_item = item.clone()
        cloned_ncs = cloned_ncs_item.ncs_pathway
        settings_manager.update_ncs_pathway(cloned_ncs)

    def _on_remove_item(self):
        """Delete NcsPathway object."""
        selected_items = self.selected_items()
        self._remove_ncs_items(selected_items)

    def load(self):
        """Load items from settings."""
        self.clear()

        settings_manager.update_ncs_pathways()
        ncs_pathways = settings_manager.get_all_ncs_pathways()

        if len(ncs_pathways) > 0:
            progress_dialog = QtWidgets.QProgressDialog(self)
            progress_dialog.setWindowTitle(self.tr("Load NCS Pathways"))
            progress_dialog.setMinimum(0)
            progress_dialog.setMaximum(len(ncs_pathways))
            progress_dialog.setLabelText(self.tr("Updating NCS pathways..."))
            for i, ncs in enumerate(ncs_pathways, start=1):
                progress_dialog.setValue(i)
                if progress_dialog.wasCanceled():
                    break
                self.add_ncs_pathway(ncs)

            self.validate_pathways()

    def _update_ui_on_selection_changed(self):
        """Enable button for deleting pathways even when multiple
        pathways have been selected.
        """
        super()._update_ui_on_selection_changed()
        self._on_item_and_selection_changed()


class ActivityComponentWidget(ModelComponentWidget):
    """Widget for displaying and managing activities."""

    items_reloaded = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.item_model = ActivityItemModel(parent)
        self.item_model.activity_pathways_updated.connect(self.on_pathways_updated)

        self.lst_model_items.setAcceptDrops(True)
        self.lst_model_items.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.lst_model_items.setDropIndicatorShown(True)

        self.btn_reload.setVisible(False)

        self.btn_pixel_editor = None

        self.add_auxiliary_widgets()

    def activities(self) -> typing.List[Activity]:
        """Returns a collection of activity objects in the
        list view.

        :returns: Collection of activity objects in the
        list view.
        :rtype: list
        """
        return self.item_model.activities()

    def add_auxiliary_widgets(self):
        """Adds additional action widgets for managing activities."""
        self.btn_pixel_editor = QtWidgets.QToolButton(self)
        style_icon = FileUtils.get_icon("rendererCategorizedSymbol.svg")
        self.btn_pixel_editor.setIcon(style_icon)
        self.btn_pixel_editor.setToolTip(
            self.tr("Show dialog for ordering pixel values for styling.")
        )
        self.btn_pixel_editor.clicked.connect(self.on_show_pixel_value_editor)
        self.add_action_widget(self.btn_pixel_editor)

    def on_show_pixel_value_editor(self):
        """Slot raised to show editor dialog for managing activity pixel
        values for styling.
        """
        pixel_dialog = PixelValueEditorDialog(self)
        if pixel_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # Update pixel values
            pixel_values = pixel_dialog.item_mapping
            for val, activity_id in pixel_values.items():
                activity = settings_manager.get_activity(activity_id)
                if not activity:
                    continue
                activity.style_pixel_value = val
                settings_manager.update_activity(activity)

            self.load()

    def model_names(self) -> typing.List[str]:
        """Gets the names of the activities in the item model.

        :returns: Returns the names of activities in lower
        case or an empty list if the item model has not been set.
        :rtype: list
        """
        if self._item_model is None:
            return []

        model_components = self._item_model.activities()

        return [mc.name.lower() for mc in model_components]

    def on_pathways_updated(self, activity_item: ActivityItem):
        """Slot raised when the pathways of an ActivityItem
        have been added or removed. Persist this information in settings.
        """
        self._save_item(activity_item)

    def model_items(self) -> typing.List[ActivityItem]:
        """Returns a collection of all ActivityItem objects
        in the list view.

        :returns: Collection of ActivityItem objects in
        the list view.
        :rtype: list
        """
        return self.item_model.activity_items()

    def clear(self):
        """Removes all activity items in the view."""
        items = self.model_items()
        for item in items:
            self.item_model.remove_activity(item.uuid)

    def load(self):
        """Load activities from settings."""
        self.clear()

        for activity in settings_manager.get_all_activities():
            self.add_activity(activity)

    def _on_add_item(self):
        """Show activity editor."""
        editor = ActivityEditorDialog(self, excluded_names=self.model_names())
        if editor.exec_() == QtWidgets.QDialog.Accepted:
            activity = editor.activity
            layer = editor.layer
            num_models = len(settings_manager.get_all_activities())
            activity.style_pixel_value = num_models + 1
            result = self.item_model.add_activity(activity, layer)
            if result:
                settings_manager.save_activity(activity)

    def _on_edit_item(self):
        """Edit selected activity object."""
        selected_items = self.selected_items()
        if len(selected_items) == 0 or len(selected_items) > 1:
            return

        item = selected_items[0]
        self._edit_activity_item(item)

    def _handle_double_click(self, item: ModelComponentItemType):
        """Show dialog for editing activity.

        :param item: Model component item that has received the event.
        :type item: ModelComponentItem
        """
        # Only handle if it is an activity object
        if isinstance(item, ActivityItem):
            self._edit_activity_item(item)

    def _edit_activity_item(self, item: ActivityItem):
        """Load dialog for editing activity."""
        # If editing, remove the current name of the model component
        excluded_names = self.model_names()
        excluded_names.remove(item.model_component.name.lower())
        editor = ActivityEditorDialog(
            self, item.activity, excluded_names=excluded_names
        )
        if editor.exec_() == QtWidgets.QDialog.Accepted:
            activity = editor.activity
            layer = editor.layer
            result = self.item_model.update_activity(activity, layer)
            if result:
                self._save_item(item)
            self._update_ui_on_selection_changed()

    def _save_item(self, item: ActivityItem):
        """Update the underlying IM in the item in settings."""
        cloned_activity_item = item.clone()
        cloned_activity = cloned_activity_item.activity
        settings_manager.update_activity(cloned_activity)

    def _on_remove_item(self):
        """Delete activity object."""
        selected_items = self.selected_items()
        if len(selected_items) == 0 or len(selected_items) > 1:
            return

        item = selected_items[0]
        model_component = None
        if isinstance(item, ModelComponentItem):
            is_model_component_item = True
            model_component = item.model_component
        else:
            is_model_component_item = False

        additional_note = ""

        if is_model_component_item:
            if item.type() == ACTIVITY_TYPE:
                additional_note = self.tr("and its children")

            msg = self.tr(
                f"Do you want to remove '{model_component.name}' {additional_note}?"
                f"\nClick Yes to proceed or No to cancel."
            )
        else:
            msg = self.tr(
                "Do you want to remove the layer for the activity?"
                "\nClick Yes to proceed or No to cancel"
            )

        if (
            QtWidgets.QMessageBox.question(
                self,
                self.tr("Remove Activity Item"),
                msg,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            == QtWidgets.QMessageBox.Yes
        ):
            if is_model_component_item:
                # NCS pathway item
                if item.type() == NCS_PATHWAY_TYPE:
                    parent = item.parent
                    self.item_model.remove_ncs_pathway_item(item.uuid, parent)
                else:
                    # Activity item
                    activity_uuid = str(model_component.uuid)
                    result = self.item_model.remove_activity(activity_uuid)
                    if result:
                        ref_pixel_value = model_component.style_pixel_value
                        settings_manager.remove_activity(activity_uuid)

                        # Reassign pixel values
                        self.reassign_pixel_values(ref_pixel_value)
            else:
                activity_item = item.data()
                if activity_item:
                    self.item_model.remove_layer(activity_item)
                    self._save_item(activity_item)

            self.clear_description()

    def reassign_pixel_values(self, start_position: int):
        """Reassign the styling pixel values for activities
        from the given start position.

        It is important to call this function when the maximum pixel
        value does not match the number of activities such
        as when one or more activities have been deleted.

        :param start_position: Position to start reassigning the pixel
        values.
        :type start_position: int
        """
        sorted_activities = sorted(
            settings_manager.get_all_activities(),
            key=lambda activity: activity.style_pixel_value,
        )
        remap_activities = sorted_activities[start_position - 1 :]
        for val, activity in enumerate(remap_activities, start=start_position):
            activity.style_pixel_value = val
            settings_manager.update_activity(activity)

        self.load()

    def add_ncs_pathway_items(self, ncs_items: typing.List[NcsPathwayItem]) -> bool:
        """Adds an NCS pathway item to the collection.

        One, and only one, target activity item needs
        to have been selected.

        :param ncs_items: NCS pathway items to be added to the
        activity.
        :type ncs_items: list

        :returns: True if the item was successfully added, else False.
        :rtype: bool
        """
        selected_activities = self.selected_items()
        if len(selected_activities) == 0 or len(selected_activities) > 1:
            return False

        sel_activity = selected_activities[0]
        item_type = sel_activity.type()

        # Use the parent to add the NCS item
        if item_type == NCS_PATHWAY_TYPE:
            if sel_activity.parent is None:
                return False

            sel_activity = sel_activity.parent

        elif item_type == LAYER_ITEM_TYPE:
            return False

        status = True
        for ncs_item in ncs_items:
            status = self.item_model.add_ncs_pathway(ncs_item, sel_activity)

        return status

    def add_activity(self, activity: Activity, layer: QgsMapLayer = None):
        """Adds an activity object to the view with the option of
        specifying the layer.

        :param activity: activity object
        to be added to the view.
        :type activity: Activity

        :param layer: Optional map layer to be added to the activity.
        :type layer: QgsMapLayer

        :returns: True if the activity was successfully added, else
        False.
        :rtype: bool
        """
        return self.item_model.add_activity(activity, layer)

    def _update_ui_on_selection_changed(self):
        """Check type of item selected and update UI
        controls accordingly.
        """
        super()._update_ui_on_selection_changed()

        selected_items = self.selected_items()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        self.btn_edit.setEnabled(False)
        self.btn_edit_description.setEnabled(False)
        if item.type() == ACTIVITY_TYPE:
            self.btn_edit.setEnabled(True)
            self.btn_edit_description.setEnabled(True)

    def update_ncs_pathway_items(self, ncs_pathway: NcsPathway) -> bool:
        """Update NCS pathway items used for activities that are linked to the
        given NCS pathway.

        :param ncs_pathway: NCS pathway whose attribute values will be updated
        for the related pathways used in the activities.
        :type ncs_pathway: NcsPathway

        :returns: True if NCS pathway items were updated, else False.
        :rtype: bool
        """
        return self.item_model.update_ncs_pathway_items(ncs_pathway)

    def remove_ncs_pathway_items(self, ncs_pathway_uuid: str):
        """Delete NCS pathway items used for activities that are linked to the
        given NCS pathway.

        :param ncs_pathway_uuid: NCS pathway whose corresponding items will be
        deleted in the activity items that contain it.
        :type ncs_pathway_uuid: str
        """
        self.item_model.remove_ncs_pathway_items(ncs_pathway_uuid)
