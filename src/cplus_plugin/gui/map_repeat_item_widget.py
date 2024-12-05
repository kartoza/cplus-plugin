# -*- coding: utf-8 -*-
"""
Widget for the custom CPLUS layout map item.
"""

import os
import typing

from qgis.core import QgsLayoutItem, QgsLayoutMeasurement
from qgis.gui import (
    QgsLayoutItemAbstractGuiMetadata,
    QgsLayoutItemBaseWidget,
    QgsLayoutItemPropertiesWidget,
)

from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.uic import loadUiType

from ..conf import settings_manager
from ..lib.reports.layout_items import CplusMapRepeatItem, CPLUS_MAP_REPEAT_ITEM_TYPE
from cplus_core.models.base import ModelComponentType
from ..utils import FileUtils, tr


WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/map_layout_item_widget.ui")
)


CPLUS_ITEM_NAME = tr("CPLUS Map Repeat Area")


class CplusMapRepeatItemWidget(QgsLayoutItemBaseWidget, WidgetUi):
    """Widget for configuring the CPLUS layout map repeat item."""

    def __init__(self, parent, layout_object: CplusMapRepeatItem):
        super().__init__(parent, layout_object)
        self.setupUi(self)

        self._map_item = layout_object

        # Common item properties widget
        self._prop_widget = QgsLayoutItemPropertiesWidget(self, layout_object)
        self.layout.addWidget(self._prop_widget, 2, 0, 1, 2)

        self.cbo_map_type.addItem(
            self.tr("Activity"),
            ModelComponentType.ACTIVITY.value,
        )


class CplusMapLayoutItemGuiMetadata(QgsLayoutItemAbstractGuiMetadata):
    """GUI metadata for a CPLUS map layout item."""

    def __init__(self):
        super().__init__(CPLUS_MAP_REPEAT_ITEM_TYPE, CPLUS_ITEM_NAME)

    def createItemWidget(self, item) -> QtWidgets.QWidget:
        """Factory override for the item widget."""
        return CplusMapRepeatItemWidget(None, item)

    def createItem(self, layout) -> QgsLayoutItem:
        """Factory override that returns the map item."""
        return CplusMapRepeatItem(layout)

    def visibleName(self) -> str:
        """Override for user-visible name identifying the item."""
        return CPLUS_ITEM_NAME

    def creationIcon(self) -> QtGui.QIcon:
        """Factory override for item icon."""
        return FileUtils.get_icon("mLayoutItemMap_cplus_add.svg")

    def newItemAddedToLayout(self, map_repeat_item: CplusMapRepeatItem):
        """Define action that is called when the CplusMapItem
        is added to a layout through the GUI.

        :param map_repeat_item: Map repeat item to be added to the layout.
        :type map_repeat_item: CplusMapRepeatItem
        """
        items = map_repeat_item.layout().items()
        counter = 1
        for item in items:
            if isinstance(item, CplusMapRepeatItem):
                counter += 1

        # Set frame properties
        map_repeat_item.setFrameEnabled(True)
        map_repeat_item.setFrameJoinStyle(QtCore.Qt.MiterJoin)
        map_repeat_item.setFrameStrokeColor(QtGui.QColor(132, 192, 68))
        map_repeat_item.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))

        map_repeat_item.setId(f"{CPLUS_ITEM_NAME} {counter!s}")
