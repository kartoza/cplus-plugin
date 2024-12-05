# -*- coding: utf-8 -*-
"""
Dialog for creating or editing an NCS pathway entry.
"""

import os
import typing
import uuid

from qgis.core import Qgis, QgsRasterLayer
from qgis.gui import QgsGui, QgsMessageBar

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.uic import loadUiType

from .carbon_item_model import CarbonLayerItem, CarbonLayerModel
from ..conf import Settings, settings_manager
from ..definitions.defaults import ICON_PATH, USER_DOCUMENTATION_SITE
from cplus_core.models.base import LayerType, NcsPathway
from ..utils import FileUtils, open_documentation, tr

WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/ncs_pathway_editor_dialog.ui")
)


class NcsPathwayEditorDialog(QtWidgets.QDialog, WidgetUi):
    """Dialog for creating or editing an NCS pathway entry."""

    def __init__(self, parent=None, ncs_pathway=None, excluded_names=None):
        super().__init__(parent)
        self.setupUi(self)

        QgsGui.enableAutoGeometryRestore(self)

        self._message_bar = QgsMessageBar()
        self.vl_notification.addWidget(self._message_bar)

        self._carbon_model = CarbonLayerModel(self)
        self.lst_carbon_layers.setModel(self._carbon_model)
        self.lst_carbon_layers.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        self.txt_description.textChanged.connect(self.description_changed)

        self.buttonBox.accepted.connect(self._on_accepted)
        self.btn_add_layer.clicked.connect(self._on_select_file)

        icon_pixmap = QtGui.QPixmap(ICON_PATH)
        self.icon_la.setPixmap(icon_pixmap)

        help_icon = FileUtils.get_icon("mActionHelpContents_green.svg")
        self.btn_help.setIcon(help_icon)
        self.btn_help.clicked.connect(self.open_help)

        add_icon = FileUtils.get_icon("symbologyAdd.svg")
        self.btn_add_carbon.setIcon(add_icon)
        self.btn_add_carbon.clicked.connect(self._on_add_carbon_layer)

        remove_icon = FileUtils.get_icon("symbologyRemove.svg")
        self.btn_delete_carbon.setIcon(remove_icon)
        self.btn_delete_carbon.setEnabled(False)
        self.btn_delete_carbon.clicked.connect(self._on_remove_carbon_layer)

        edit_icon = FileUtils.get_icon("mActionToggleEditing.svg")
        self.btn_edit_carbon.setIcon(edit_icon)
        self.btn_edit_carbon.setEnabled(False)
        self.btn_edit_carbon.clicked.connect(self._on_edit_carbon_layer)

        pathways = settings_manager.get_default_layers("ncs_pathway")
        self.cbo_default_layer.addItem("")
        self.cbo_default_layer.addItems([p["name"] for p in pathways])
        self.cbo_default_layer.setCurrentIndex(0)
        self.cbo_default_layer.currentIndexChanged.connect(
            self._on_default_layer_selection_changed
        )

        add_default_icon = FileUtils.get_icon("mActionAddDefaultCarbonLayer.svg")
        self.btn_add_default_carbon.setIcon(add_default_icon)
        self.btn_add_default_carbon.setMenu(QtWidgets.QMenu(self))
        items = settings_manager.get_default_layers("ncs_carbon")
        for item in items:
            action = QtWidgets.QAction(item["name"], self)
            action.triggered.connect(
                lambda checked, item=item: self._on_default_carbon_layer_selected(item)
            )
            self.btn_add_default_carbon.menu().addAction(action)

        self._excluded_names = excluded_names
        if excluded_names is None:
            self._excluded_names = []

        self._edit_mode = False
        self._layer = None
        self._ncs_pathway = ncs_pathway
        if self._ncs_pathway is not None:
            self._edit_mode = True
            self._layer = self._ncs_pathway.to_map_layer()
            self._update_controls()

    @property
    def ncs_pathway(self) -> NcsPathway:
        """Returns a reference to the NcsPathway object.

        :returns: Reference to the NcsPathway object.
        :rtype: NcsPathway
        """
        return self._ncs_pathway

    @property
    def edit_mode(self) -> bool:
        """Returns the state of the editor.

        :returns: True if the editor is editing an existing NcsPathway
        object, else False if its creating a new object.
        :rtype: bool
        """
        return self._edit_mode

    @property
    def layer(self) -> QgsRasterLayer:
        """Returns the raster layer specified by the user,
        either existing layers in the map canvas or from the
        selected file.

        :returns: The raster layer specified by the user or
        None if not set.
        :rtype: QgsRasterLayer
        """
        return self._layer

    def description_changed(self):
        """Slot to handle description text changes, it currently
        limits the number of characters to only be 300 characters
        per description
        """

        description = self.txt_description.toPlainText()
        if len(description) > 300:
            self.txt_description.setPlainText(description[:300])

    def _update_controls(self):
        """Update controls with data from the NcsPathway object."""
        if self._ncs_pathway is None:
            return

        self.txt_name.setText(self._ncs_pathway.name)
        self.txt_description.setPlainText(self._ncs_pathway.description)

        if self._layer:
            layer_path = self._layer.source()
            self._add_layer_path(layer_path)
        if self._ncs_pathway.layer_uuid:
            pathways = settings_manager.get_default_layers("ncs_pathway")
            for i, layer in enumerate(pathways):
                if layer["layer_uuid"] == self._ncs_pathway.layer_uuid:
                    self.cbo_default_layer.setCurrentIndex(i + 1)
                    break

        for carbon_path in self._ncs_pathway.carbon_paths:
            self._carbon_model.add_carbon_layer(carbon_path)

    def _add_layer_path(self, layer_path: str):
        """Select or add layer path to the map layer combobox."""
        matching_index = -1
        num_layers = self.cbo_layer.count()
        for index in range(num_layers):
            layer = self.cbo_layer.layer(index)
            if layer is None:
                continue
            if os.path.normpath(layer.source()) == os.path.normpath(layer_path):
                matching_index = index
                break

        if matching_index == -1:
            self.cbo_layer.setAdditionalItems([layer_path])
            # Set added path as current item
            self.cbo_layer.setCurrentIndex(num_layers)
        else:
            self.cbo_layer.setCurrentIndex(matching_index)

    def _show_warning_message(self, message):
        """Shows a warning message in the message bar."""
        self._message_bar.pushMessage(message, Qgis.MessageLevel.Warning)

    def validate(self) -> bool:
        """Validates if name and layer have been specified.

        :returns: True if user input (i.e. name and layer) have been set.
        :rtype: True
        """
        status = True

        self._message_bar.clearWidgets()

        name = self.txt_name.text()
        if not name:
            msg = tr("NCS pathway name cannot be empty.")
            self._show_warning_message(msg)
            status = False

        if name.lower() in self._excluded_names:
            msg = tr("name has already been used.")
            self._show_warning_message(f"'{name}' {msg}")
            status = False

        if not self.txt_description.toPlainText():
            msg = tr("Description cannot be empty.")
            self._show_warning_message(msg)
            status = False

        layer = self._get_selected_map_layer()
        default_layer = self._get_selected_default_layer()
        if layer is None and default_layer is None:
            msg = tr("Map layer not specified.")
            self._show_warning_message(msg)
            status = False

        if layer and not layer.isValid():
            msg = tr("Map layer is not valid.")
            self._show_warning_message(msg)
            status = False

        return status

    def _create_update_ncs_pathway(self):
        """Create or update NcsPathway from user input."""
        layer = self._get_selected_map_layer()
        if layer:
            self._layer = layer

        if self._ncs_pathway is None:
            self._ncs_pathway = NcsPathway(
                uuid.uuid4(),
                self.txt_name.text(),
                self.txt_description.toPlainText(),
                user_defined=True,
            )
        else:
            # Update mode
            self._ncs_pathway.name = self.txt_name.text()
            self._ncs_pathway.description = self.txt_description.toPlainText()

        self._ncs_pathway.layer_type = LayerType.RASTER
        default_layer = self._get_selected_default_layer()

        if default_layer:
            self._ncs_pathway.path = "cplus://" + default_layer.get("layer_uuid")
        else:
            self._ncs_pathway.path = self._layer.source()
        self._ncs_pathway.carbon_paths = self._carbon_model.carbon_paths()

    def _get_selected_map_layer(self) -> QgsRasterLayer:
        """Returns the currently selected map layer or None if there is
        no item in the combobox.
        """
        layer = self.cbo_layer.currentLayer()

        if layer is None:
            layer_paths = self.cbo_layer.additionalItems()
            current_path = self.cbo_layer.currentText()
            if current_path in layer_paths:
                layer_name = os.path.basename(current_path)
                layer = QgsRasterLayer(current_path, layer_name)

        return layer

    def _get_selected_default_layer(self) -> dict:
        """Returns selected default layer.

        :return: layer dictionary
        :rtype: dict
        """
        layer_name = self.cbo_default_layer.currentText()
        if layer_name == "":
            return {}
        pathways = settings_manager.get_default_layers("ncs_pathway")
        layer = [p for p in pathways if p["name"] == layer_name]
        return layer[0] if layer else {}

    def selected_carbon_items(self) -> typing.List[CarbonLayerItem]:
        """Returns the selected carbon items in the list view.

        :returns: A collection of the selected carbon items.
        :rtype: list
        """
        selection_model = self.lst_carbon_layers.selectionModel()
        idxs = selection_model.selectedRows()

        return [self._carbon_model.item(idx.row()) for idx in idxs]

    def _on_selection_changed(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        """Slot raised when the selection in the carbon list changes."""
        self._update_ui_on_selection_changed()

    def _update_ui_on_selection_changed(self):
        """Update UI properties on selection changed."""
        self.btn_edit_carbon.setEnabled(True)
        self.btn_delete_carbon.setEnabled(True)

        # Disable edit and remove buttons if more than
        # one item has been selected.
        selected_items = self.selected_carbon_items()
        if len(selected_items) == 0:
            self.btn_delete_carbon.setEnabled(False)
            self.btn_edit_carbon.setEnabled(False)
        elif len(selected_items) > 1:
            self.btn_edit_carbon.setEnabled(False)

    def _on_add_carbon_layer(self, activated: bool):
        """Slot raised to add a carbon layer."""
        self._message_bar.clearWidgets()

        data_dir = settings_manager.get_value(Settings.LAST_DATA_DIR, "")
        if not data_dir and self._layer:
            data_path = self._layer.source()
            if os.path.exists(data_path):
                data_dir = os.path.dirname(data_path)

        if not data_dir:
            data_dir = "/home"

        carbon_paths = self._show_carbon_path_selector(data_dir, select_multiple=True)
        if len(carbon_paths) == 0:
            return

        existing_layers = []
        for carbon_path in carbon_paths:
            if self._carbon_model.contains_layer_path(carbon_path):
                existing_layers.append(carbon_path)
                continue

            self._carbon_model.add_carbon_layer(carbon_path)

        if len(existing_layers) > 0:
            self._message_bar.clearWidgets()
            for layer in existing_layers:
                error_tr = tr("Carbon layer already exists")
                self._show_warning_message(f"{error_tr}: {layer}")

    def _on_edit_carbon_layer(self, activated: bool):
        """Slot raised to edit a carbon layer."""
        carbon_items = self.selected_carbon_items()
        if len(carbon_items) == 0:
            return

        carbon_item = carbon_items[0]
        carbon_paths = self._show_carbon_path_selector(carbon_item.layer_path)
        if len(carbon_paths) == 0:
            return

        if self._carbon_model.contains_layer_path(carbon_paths[0]):
            error_tr = tr("Selected carbon layer already exists.")
            self._show_warning_message(f"{error_tr}")
            return

        carbon_item.update(carbon_paths[0])

    def _on_remove_carbon_layer(self, activated: bool):
        """Slot raised to remove one or more selected carbon layers."""
        carbon_items = self.selected_carbon_items()
        if len(carbon_items) == 0:
            return

        for ci in carbon_items:
            index = self._carbon_model.indexFromItem(ci)
            if not index.isValid():
                continue
            self._carbon_model.removeRows(index.row(), 1)

    def _show_carbon_path_selector(
        self, layer_dir: str, select_multiple: bool = False
    ) -> typing.List[str]:
        """Show file selector dialog for selecting a carbon layer."""
        filter_tr = tr("All files")

        if select_multiple:
            open_file_func = QtWidgets.QFileDialog.getOpenFileNames
            title = self.tr("Select Carbon Layers")
        else:
            open_file_func = QtWidgets.QFileDialog.getOpenFileName
            title = self.tr("Select Carbon Layer")

        layer_paths, _ = open_file_func(
            self,
            title,
            layer_dir,
            f"{filter_tr} (*.*)",
            options=QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        if not layer_paths or len(layer_paths) == 0:
            return []

        if not select_multiple:
            return [layer_paths]

        return layer_paths

    def open_help(self, activated: bool):
        """Opens the user documentation for the plugin in a browser."""
        open_documentation(USER_DOCUMENTATION_SITE)

    def _on_accepted(self):
        """Validates user input before closing."""
        if not self.validate():
            return

        self._create_update_ncs_pathway()
        self.accept()

    def _on_select_file(self, activated: bool):
        """Slot raised to upload a raster layer."""
        data_dir = settings_manager.get_value(Settings.LAST_DATA_DIR, "")
        if not data_dir and self._layer:
            data_path = self._layer.source()
            if os.path.exists(data_path):
                data_dir = os.path.dirname(data_path)

        if not data_dir:
            data_dir = "/home"

        filter_tr = tr("All files")

        layer_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select NCS Pathway Layer"),
            data_dir,
            f"{filter_tr} (*.*)",
            options=QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        if not layer_path:
            return

        existing_paths = self.cbo_layer.additionalItems()
        if layer_path in existing_paths:
            return

        self.cbo_layer.setAdditionalItems([])

        self._add_layer_path(layer_path)
        settings_manager.set_value(Settings.LAST_DATA_DIR, os.path.dirname(layer_path))

    def _on_default_layer_selection_changed(self):
        """Event raised when default layer selection is changed."""
        layer = self._get_selected_default_layer()
        metadata = layer.get("metadata", {})
        self.txt_name.setText(metadata.get("name", layer.get("name", "")))
        self.txt_description.setPlainText(metadata.get("description", ""))
        # remove selection from cbo_layer
        self.cbo_layer.setAdditionalItems([])

    def _on_default_carbon_layer_selected(self, item):
        """Event raised when default carbon layer is selected."""
        layer_name = item["name"]
        layer_path = "cplus://" + item["layer_uuid"] + "/" + layer_name
        self._carbon_model.add_carbon_layer(layer_path)
