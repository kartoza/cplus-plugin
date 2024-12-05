# -*- coding: utf-8 -*-

"""
 Item selection dialog  file
"""

import os
import uuid

from qgis.PyQt import QtCore, QtGui, QtWidgets, QtNetwork

from qgis.PyQt.uic import loadUiType

from cplus_core.models.base import Activity, PriorityLayer

from ..conf import settings_manager


from ..utils import log, tr


DialogUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/items_selection_dialog.ui")
)


class ItemsSelectionDialog(QtWidgets.QDialog, DialogUi):
    """Dialog for handling items selection"""

    def __init__(self, parent, parent_item=None, items=[], item_type=Activity):
        """Constructor"""
        super().__init__()
        self.setupUi(self)
        self.parent = parent
        self.parent_item = parent_item

        self.item_type = item_type
        self.items = items

        select_all_btn = QtWidgets.QPushButton(tr("Select All"))
        select_all_btn.setToolTip(tr("Select the all listed items"))
        select_all_btn.clicked.connect(self.select_all_clicked)
        self.mButtonBox.addButton(select_all_btn, QtWidgets.QDialogButtonBox.ActionRole)

        clear_all_btn = QtWidgets.QPushButton(tr("Clear Selection"))
        clear_all_btn.setToolTip(tr("Clear the current selection"))
        clear_all_btn.clicked.connect(self.clear_all_clicked)
        self.mButtonBox.addButton(clear_all_btn, QtWidgets.QDialogButtonBox.ActionRole)

        toggle_selection_btn = QtWidgets.QPushButton(tr("Toggle Selection"))
        toggle_selection_btn.clicked.connect(self.toggle_selection_clicked)
        self.mButtonBox.addButton(
            toggle_selection_btn, QtWidgets.QDialogButtonBox.ActionRole
        )

        self.mButtonBox.accepted.connect(self.accept)

        self.set_items()

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item_uuid = item.data(QtCore.Qt.UserRole)

            if self.item_type is Activity:
                activity = settings_manager.get_activity(str(item_uuid))

                layer_model_uuids = [item.uuid for item in self.items]
                activity_layer_uuids = [
                    layer.get("uuid")
                    for layer in activity.priority_layers
                    if layer is not None
                ]

                if (
                    self.parent_item is not None
                    and str(self.parent_item.get("uuid")) in activity_layer_uuids
                ) or (activity.uuid in layer_model_uuids):
                    item.setCheckState(QtCore.Qt.Checked)
            else:
                layer = settings_manager.get_priority_layer(str(item_uuid))
                group_uuids = []

                for group in layer.get("groups"):
                    group = settings_manager.find_group_by_name(group.get("name"))

                    if group is not None:
                        group_uuids.append(str(group.get("uuid")))

                if self.parent_item.get("uuid") in group_uuids:
                    item.setCheckState(QtCore.Qt.Checked)

    def set_items(self):
        """Sets the item list in the dialog"""
        if self.item_type is Activity:
            items = settings_manager.get_all_activities()
        else:
            all_layers = settings_manager.get_priority_layers()
            items = []
            for layer in all_layers:
                model_layer = PriorityLayer(
                    uuid=uuid.UUID(layer.get("uuid")),
                    name=layer.get("name"),
                    description=layer.get("description"),
                    groups=layer.get("groups"),
                )
                items.append(model_layer)

        for item in items:
            list_widget_item = QtWidgets.QListWidgetItem(item.name)
            list_widget_item.setFlags(
                list_widget_item.flags() | QtCore.Qt.ItemIsUserCheckable
            )
            list_widget_item.setData(QtCore.Qt.UserRole, item.uuid)
            list_widget_item.setCheckState(QtCore.Qt.Unchecked)
            self.list_widget.addItem(list_widget_item)

    def selected_items(self):
        """Returns the selected items from the dialog"""
        if self.item_type is Activity:
            items = settings_manager.get_all_activities()
        else:
            all_layers = settings_manager.get_priority_layers()
            items = []
            for layer in all_layers:
                model_layer = PriorityLayer(
                    uuid=uuid.UUID(layer.get("uuid")),
                    name=layer.get("name"),
                    description=layer.get("description"),
                    groups=layer.get("groups"),
                )
                items.append(model_layer)

        items_text = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == QtCore.Qt.Checked:
                items_text.append(item.text())

        final_items = []

        for item in items:
            for item_name in items_text:
                if item.name == item_name:
                    final_items.append(item)
                    break

        return final_items

    def unselected_items(self):
        """Returns unselected items from the dialog"""
        if self.item_type is Activity:
            items = settings_manager.get_all_activities()
        else:
            all_layers = settings_manager.get_priority_layers()
            items = []
            for layer in all_layers:
                model_layer = PriorityLayer(
                    uuid=uuid.UUID(layer.get("uuid")),
                    name=layer.get("name"),
                    description=layer.get("description"),
                    groups=layer.get("groups"),
                )
                items.append(model_layer)

        items_text = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.checkState() == QtCore.Qt.Unchecked:
                items_text.append(item.text())
        item_names = ",".join(items_text)
        items = [item for item in items if item.name in item_names]
        return items

    def accept(self):
        """Saves the item selection"""
        self.parent.set_selected_items(self.selected_items(), self.unselected_items())
        super().accept()

    def select_all_clicked(self):
        """Slot for handling selection for all items."""
        for item_index in range(self.list_widget.count()):
            item_item = self.list_widget.item(item_index)
            item_item.setCheckState(QtCore.Qt.Checked)

    def clear_all_clicked(self):
        """Slot for handling clear selection for all items."""
        for item_index in range(self.list_widget.count()):
            item_item = self.list_widget.item(item_index)
            item_item.setCheckState(QtCore.Qt.Unchecked)

    def toggle_selection_clicked(self):
        """Toggles all the current items selection."""
        for item_index in range(self.list_widget.count()):
            item_item = self.list_widget.item(item_index)
            state = item_item.checkState()
            if state == QtCore.Qt.Checked:
                item_item.setCheckState(QtCore.Qt.Unchecked)
            elif state == QtCore.Qt.Unchecked:
                item_item.setCheckState(QtCore.Qt.Checked)
