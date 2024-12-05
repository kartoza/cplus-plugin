# -*- coding: utf-8 -*-
"""
    Priority group dialog
"""

import os
import uuid

from qgis.PyQt import (
    QtCore,
    QtGui,
    QtNetwork,
    QtWidgets,
)
from qgis.PyQt.uic import loadUiType

from cplus_core.models.base import PriorityLayer

from ..conf import settings_manager
from ..utils import FileUtils, open_documentation
from ..definitions.defaults import ICON_PATH, PRIORITY_GROUPS, USER_DOCUMENTATION_SITE
from ..definitions.constants import PRIORITY_LAYERS_SEGMENT, USER_DEFINED_ATTRIBUTE

from .items_selection_dialog import ItemsSelectionDialog


DialogUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/priority_group_dialog.ui")
)


class PriorityGroupDialog(QtWidgets.QDialog, DialogUi):
    """Dialog that provide UI for priority group details."""

    def __init__(
        self,
        group=None,
        parent=None,
    ):
        super().__init__(parent)
        self.setupUi(self)
        self.group = group
        self.layers = []
        if self.group is not None:
            self.layers = settings_manager.find_layers_by_group(group.get("name"))

        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(False)

        ok_signals = [
            self.group_name.textChanged,
            self.group_description.textChanged,
        ]

        for signal in ok_signals:
            signal.connect(self.update_ok_buttons)

        icon_pixmap = QtGui.QPixmap(ICON_PATH)
        self.icon_la.setPixmap(icon_pixmap)

        self._user_defined = True

        self.initialize_ui()

    def update_ok_buttons(self):
        """Responsible for changing the state of the
        dialog OK button.
        """
        enabled_state = (
            self.group_name.text() != "" and self.group_description.toPlainText() != ""
        )
        self.button_box.button(QtWidgets.QDialogButtonBox.Ok).setEnabled(enabled_state)

    def initialize_ui(self):
        """Populate UI inputs when loading the dialog"""

        self.btn_help.setIcon(FileUtils.get_icon("mActionHelpContents.svg"))
        self.btn_help.clicked.connect(self.open_help)

        self.select_layers_btn.clicked.connect(self.open_layer_select_dialog)

        if self.group is not None:
            self.group_name.setText(self.group.get("name", ""))
            self.group_description.setText(self.group.get("description", ""))
            self.group_spin_box.setValue(int(self.group.get("value", 0)))

            self._user_defined = self.group.get(USER_DEFINED_ATTRIBUTE, True)

        self.set_selected_items(self.layers)

    def open_layer_select_dialog(self):
        """Opens priority group item selection dialog"""
        model_layers = []
        for layer in self.layers:
            model_layer = PriorityLayer(
                uuid=uuid.UUID(layer.get("uuid")),
                name=layer.get("name"),
                description=layer.get("description"),
                groups=layer.get("groups"),
            )
            model_layers.append(model_layer)

        layer_select_dialog = ItemsSelectionDialog(
            self, self.group, model_layers, item_type=PriorityLayer
        )
        layer_select_dialog.exec_()

    def set_selected_items(self, items, removed_items=[]):
        """Adds this dialog group into the passed layers and removes it from the
        unselected layers passed as remove_items.

        :param items: Selected priority layers
        :type items: list

        :param removed_items: Priority layers should be removed from the group
        :type removed_items: list

        """

        self.layers = items

        if len(items) > 0 and isinstance(items[0], dict):
            items = []
            for layer in self.layers:
                model_layer = PriorityLayer(
                    uuid=uuid.UUID(layer.get("uuid")),
                    name=layer.get("name"),
                    description=layer.get("description"),
                    groups=layer.get("groups"),
                )
                items.append(model_layer)

        layers_names = [item.name for item in items]
        self.selected_layers_le.setText(" , ".join(layers_names))

        if not self.group:
            return

        for item in items:
            layer_item = settings_manager.get_priority_layer(str(item.uuid))
            layer_groups = item.groups
            if self.group not in layer_groups:
                layer_groups.append(self.group)
            layer_item["groups"] = layer_groups

            settings_manager.save_priority_layer(layer_item)

        for item in removed_items:
            layer_groups = []
            for group in item.groups:
                if group.get("uuid") == self.group.get("uuid"):
                    continue
                layer_groups.append(group)

            layer_item = settings_manager.get_priority_layer(str(item.uuid))
            layer_item["groups"] = layer_groups
            settings_manager.save_priority_layer(layer_item)

    def accept(self):
        """Handles logic for adding new priority group and edit existing one"""
        group_id = uuid.uuid4()
        group = {}
        if self.group is not None:
            group_id = self.group.get("uuid")

        group["uuid"] = str(group_id)
        group["name"] = self.group_name.text()
        group["description"] = self.group_description.toPlainText()
        group["value"] = self.group_spin_box.value()

        self.set_selected_items(self.layers)

        # layers_uuid = [str(layer.get('uuid')) for layer in self.layers]
        #
        # all_layers = settings_manager.get_priority_layers()
        #
        # for layer in all_layers:
        #     if layer.get('uuid') in layers_uuid:
        #         group_uuids = [str(group.get('uuid')) for group in layer.get('groups') if group is not None]
        #         if self.group.get('uuid') not in group_uuids:
        #             layer['groups'] = layer.get('groups').append(self.group)
        #             settings_manager.save_priority_layer(layer)
        #     else:
        #         group_uuids = [str(group.get('uuid')) for group in layer.get('groups') if group is not None]
        #         if self.group.get('uuid') in group_uuids:
        #             layer['groups'] = layer.get('groups').remove(self.group)
        #             settings_manager.save_priority_layer(layer)

        group[USER_DEFINED_ATTRIBUTE] = self._user_defined
        settings_manager.save_priority_group(group)

        super().accept()

    def open_help(self):
        """Opens the user documentation for the plugin in a browser"""
        open_documentation(USER_DOCUMENTATION_SITE)
