# -*- coding: utf-8 -*-
"""
Container widget for configuring the implementation widget.
"""

import os
import typing

from qgis.core import Qgis
from qgis.gui import QgsMessageBar

from qgis.PyQt import QtCore, QtWidgets

from qgis.PyQt.uic import loadUiType

from ..conf import Settings, settings_manager
from .component_item_model import ActivityItem, ModelComponentItemType
from .model_component_widget import (
    ActivityComponentWidget,
    NcsComponentWidget,
)
from cplus_core.models.base import Activity, NcsPathway

from ..utils import FileUtils


WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/activity_container_widget.ui")
)


class ActivityContainerWidget(QtWidgets.QWidget, WidgetUi):
    """Widget for configuring an activity."""

    ncs_reloaded = QtCore.pyqtSignal()

    def __init__(
        self, parent: QtWidgets.QWidget = None, message_bar: QgsMessageBar = None
    ):
        super().__init__(parent)
        self.setupUi(self)

        self._message_bar = message_bar

        self._items_loaded = False

        self.btn_add_one.setIcon(FileUtils.get_icon("cplus_right_arrow.svg"))
        self.btn_add_one.setToolTip(self.tr("Add selected NCS pathway"))
        self.btn_add_one.clicked.connect(self._on_add_ncs_pathway)

        self.btn_add_all.setIcon(FileUtils.get_icon("cplus_double_right_arrows.svg"))
        self.btn_add_all.setToolTip(self.tr("Add all NCS pathways"))
        self.btn_add_all.clicked.connect(self._on_add_all_ncs_pathways)

        # NCS pathway view
        self.ncs_pathway_view = NcsComponentWidget()
        self.ncs_pathway_view.title = self.tr("NCS Pathways")
        self.ncs_layout.addWidget(self.ncs_pathway_view)

        # activity view
        self.activity_view = ActivityComponentWidget()
        self.activity_layout.addWidget(self.activity_view)
        self.activity_view.title = self.tr("Activities")

        settings_manager.settings_updated[str, object].connect(self.on_settings_changed)
        self.ncs_pathway_view.ncs_pathway_updated.connect(self.on_ncs_pathway_updated)
        self.ncs_pathway_view.ncs_pathway_removed.connect(self.on_ncs_pathway_removed)
        self.ncs_pathway_view.items_reloaded.connect(self._on_ncs_pathways_reloaded)

        self.load()

    def load(self):
        """Load NCS pathways and activities to the views.

        This function is idempotent as items will only be loaded once
        on initial call.
        """
        if not self._items_loaded:
            self.ncs_pathway_view.load()
            self.activity_view.load()
            self._items_loaded = True

    def ncs_pathways(self) -> typing.List[NcsPathway]:
        """Gets the NCS pathway objects in the NCS Pathways view.

        :returns: NCS pathway objects, both default and user-defined.
        :rtype: list
        """
        return self.ncs_pathway_view.pathways()

    def activities(self) -> typing.List[Activity]:
        """Returns the user-defined activities in the
        activity view.

        :returns: User-defined activities for the current scenario.
        :rtype: list
        """
        return self.activity_view.activities()

    def _on_add_ncs_pathway(self):
        """Slot raised to add NCS pathway item to an activity."""
        selected_ncs_items = self.ncs_pathway_view.selected_items()
        if len(selected_ncs_items) == 0:
            return

        ncs_item = selected_ncs_items[0]
        self.activity_view.add_ncs_pathway_items([ncs_item])

    def _on_add_all_ncs_pathways(self):
        """Slot raised to add all NCS pathway item to an
        activity view.
        """
        all_ncs_items = self.ncs_pathway_view.ncs_items()
        if len(all_ncs_items) == 0:
            return

        self.activity_view.add_ncs_pathway_items(all_ncs_items)

    def _on_ncs_pathways_reloaded(self):
        """Slot raised when NCS pathways have been reloaded."""
        self.ncs_reloaded.emit()

    def on_ncs_pathway_updated(self, ncs_pathway: NcsPathway):
        """Slot raised when an NCS pathway has been updated."""
        self.activity_view.update_ncs_pathway_items(ncs_pathway)

    def on_ncs_pathway_removed(self, ncs_pathway_uuid: str):
        """Slot raised when an NCS pathway has been removed.

        :param ncs_pathway_uuid: Unique identified of the removed NCS pathway item.
        :type ncs_pathway_uuid: str
        """
        self.activity_view.remove_ncs_pathway_items(ncs_pathway_uuid)

    def show_message(self, message, level=Qgis.Warning):
        """Shows message if message bar has been specified.

        :param message: Text to display in the message bar.
        :type message: str

        :param level: Message level type
        :type level: Qgis.MessageLevel
        """
        if self._message_bar is None:
            return

        self._message_bar.clearWidgets()
        self._message_bar.pushMessage(message, level=level)

    def on_settings_changed(self, name: str, value: typing.Any):
        """Slot raised when settings has been changed.

        :param name: Name of the setting that has changed.
        :type name: str

        :param value: New value for the given settings name.
        :type value: Any
        """
        # Update the NCS pathway and carbon layer paths when
        # BASE_DIR has been updated.
        if name == Settings.BASE_DIR.value:
            self.ncs_pathway_view.load()

    def is_ncs_valid(self) -> bool:
        """Checks whether the NCS pathways are valid against a given set of validation rules.

        :returns: True if the NCS pathways are valid else False.
        :rtype: bool
        """
        return self.ncs_pathway_view.is_valid()

    def is_activity_valid(self) -> bool:
        """Check if the user input is valid.

        This checks if there is one activity defined with at
        least one NCS pathway under it.

        :returns: True if the activity configuration is
        valid, else False at least until there is one implementation
        model defined with at least one NCS pathway under it.
        :rtype: bool
        """
        activities = self.activities()
        if len(activities) == 0:
            return False

        status = False
        for activity in activities:
            if len(activity.pathways) > 0 or activity.to_map_layer() is not None:
                status = True
                break

        return status

    def selected_items(self) -> typing.List[ModelComponentItemType]:
        """Returns the selected model component item types which could be
        NCS pathway or activity items.

        If an item is disabled then it will be excluded from the
        selection.

        These are cloned objects so as not to interfere with the
        underlying data models when used for scenario analysis. Otherwise,
        one can also use the data models from the MVC item model.

        :returns: Selected model component items.
        :rtype: list
        """
        ref_items = self.activity_view.selected_items()
        cloned_items = []
        for ref_item in ref_items:
            if not ref_item.isEnabled():
                continue

            clone_item = ref_item.clone()
            cloned_items.append(clone_item)

        return cloned_items

    def selected_activity_items(self) -> typing.List[ActivityItem]:
        """Returns the currently selected instances of activity items.

        If an item is disabled then it will be excluded from the selection.

        :returns: Currently selected instances of ActivityItem or
        an empty list if there is no selection of activity items.
        :rtype: list
        """
        return [
            item for item in self.selected_items() if isinstance(item, ActivityItem)
        ]
