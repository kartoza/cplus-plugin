# -*- coding: utf-8 -*-
"""Custom CPLUS layout items."""

import typing

from qgis.core import (
    Qgis,
    QgsFillSymbol,
    QgsLayoutItemAbstractMetadata,
    QgsLayoutItemGroup,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemRegistry,
    QgsLayoutItemShape,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLegendRenderer,
    QgsLegendStyle,
    QgsMapLayerLegendUtils,
    QgsProject,
    QgsRasterLayer,
    QgsTextFormat,
    QgsUnitTypes,
)
from qgis.PyQt import QtCore, QtGui

from cplus_core.models.base import ModelComponentType, ScenarioResult
from ...utils import FileUtils, get_report_font, log, tr


CPLUS_MAP_REPEAT_ITEM_TYPE = QgsLayoutItemRegistry.PluginItem + 2350


class CplusMapRepeatItem(QgsLayoutItemShape):
    """Defines an outline area within a layout where map items
    containing NCS pathway or activity will be drawn.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setShapeType(QgsLayoutItemShape.Shape.Rectangle)

        # We shall use a frame so that it can be turned off / on
        # using the item properties UI. The symbol is just a proxy.
        # Symbol properties
        symbol_props = {
            "color": "229,182,54,0",
            "style": "solid",
            "outline_style": "dash",
            "line_color": "132,192,68",
            "outline_width": "0",
            "joinstyle": "miter",
        }
        symbol = QgsFillSymbol.createSimple(symbol_props)
        self.setSymbol(symbol)

        self._model_component_type = kwargs.pop(
            "model_component_type", ModelComponentType.UNKNOWN
        )

    @property
    def model_component_type(self) -> ModelComponentType:
        """Gets the model component type associated with
        this map item i.e. NCS pathway or activity.

        :returns: Type of the model component.
        :rtype: Enum
        """
        return self._model_component_type

    @model_component_type.setter
    def model_component_type(self, component_type: ModelComponentType):
        """Set the model component type associated with
        this map item i.e. NCS pathway or activity.

        :param component_type: Type of the model component.
        :type component_type: Enum
        """
        self._model_component_type = component_type

    def type(self):
        """Return item's unique type identifier."""
        return CPLUS_MAP_REPEAT_ITEM_TYPE

    def visibleName(self) -> str:
        """Override for visible name of the item."""
        return tr("CPLUS Map Repeat Area Item")

    def visiblePluralName(self) -> str:
        """Override for plural name of the items."""
        return tr("CPLUS Map Repeat Area Items")

    def icon(self) -> QtGui.QIcon:
        """Override for custom CPLUS map item."""
        return FileUtils.get_icon("mLayoutItemMap_cplus.svg")

    def writePropertiesToElement(self, el, document, context):
        """Override saving of item properties."""
        status = super().writePropertiesToElement(el, document, context)
        if status:
            el.setAttribute("modelComponentType", self._model_component_type.value)

        return status

    def readPropertiesFromElement(self, element, document, context):
        """Override reading of item properties."""
        status = super().readPropertiesFromElement(element, document, context)
        if status:
            model_component_type = element.attribute("modelComponentType", "")
            self._model_component_type = ModelComponentType.from_string(
                model_component_type
            )

        return status


class CplusMapRepeatItemLayoutItemMetadata(QgsLayoutItemAbstractMetadata):
    """Metadata info of the cplus map repeat item."""

    def __init__(self):
        super().__init__(CPLUS_MAP_REPEAT_ITEM_TYPE, tr("CPLUS Map Repeat Area Item"))

    def createItem(self, layout) -> CplusMapRepeatItem:
        """Factory method that return the cplus map item."""
        return CplusMapRepeatItem(layout)


class BasicScenarioDetailsItem(QgsLayoutItemGroup):
    """Contains elements showing the basic details of a scenario such as a
    title, description, map and legend.
    """

    def __init__(self, *args, **kwargs):
        self._result: ScenarioResult = kwargs.pop("scenario_result", None)
        self._project = kwargs.pop("project", None)
        super().__init__(*args, **kwargs)

        self._add_scenario_layout_items()

        self._update_scenario_details()

    def _add_scenario_layout_items(self):
        """Add layout items for showing the scenario details.

        The position and size values for the map and legend are
        just placeholder values and will be adjusted when the
        parent item has been resized.
        """
        reference_point = self.pagePositionWithUnits()
        reference_point_x = reference_point.x()
        reference_point_y = reference_point.y()

        normalized_scenario_name = self._result.scenario.name.lower().replace(" ", "_")

        title_color = QtGui.QColor(QtCore.Qt.white)
        label_margin = 1.2

        # Scenario name
        self._title_label = QgsLayoutItemLabel(self.layout())
        self.layout().addLayoutItem(self._title_label)
        self._title_label.attemptMove(reference_point, True, False, self.page())
        self._title_label.attemptResize(QgsLayoutSize(200, 10, self.layout().units()))
        self._title_label.setBackgroundColor(QtGui.QColor(3, 109, 0))
        self._title_label.setBackgroundEnabled(True)
        self._title_label.setId(f"label_title_{normalized_scenario_name}")
        self._title_label.setHAlign(QtCore.Qt.AlignHCenter)
        self._title_label.setMargin(label_margin)
        self.set_label_font(self._title_label, 15, color=title_color)
        self.addItem(self._title_label)

        # Scenario description
        self._description_label = QgsLayoutItemLabel(self.layout())
        self.layout().addLayoutItem(self._description_label)
        description_ref_point = QgsLayoutPoint(
            reference_point_x, reference_point_y + 10, self.layout().units()
        )
        self._description_label.attemptMove(
            description_ref_point, True, False, self.page()
        )
        self._description_label.attemptResize(
            QgsLayoutSize(200, 10, self.layout().units())
        )
        self._description_label.setMargin(label_margin)
        self._description_label.setId(f"label_description_{normalized_scenario_name}")
        self.set_label_font(self._description_label, 11)
        self.addItem(self._description_label)

        # Map for scenario HPA layer
        self._scenario_map = QgsLayoutItemMap(self.layout())
        self.layout().addLayoutItem(self._scenario_map)
        map_ref_point = QgsLayoutPoint(
            reference_point_x, reference_point_y + 20, self.layout().units()
        )
        self._scenario_map.attemptMove(map_ref_point, True, False, self.page())
        self._scenario_map.attemptResize(QgsLayoutSize(200, 90, self.layout().units()))
        self.setId(f"group_{normalized_scenario_name}")
        self._scenario_map.setId(f"map_{normalized_scenario_name}")
        self.addItem(self._scenario_map)

        # Map legend
        self._legend = QgsLayoutItemLegend(self.layout())
        self._legend.setLinkedMap(self._scenario_map)
        self.layout().addLayoutItem(self._legend)
        legend_ref_point = QgsLayoutPoint(
            reference_point_x, reference_point_y + 110, self.layout().units()
        )
        self._legend.attemptMove(legend_ref_point, True, False, self.page())
        self._legend.attemptResize(QgsLayoutSize(200, 35, self.layout().units()))
        self._legend.setId(f"legend_{normalized_scenario_name}")
        self._legend.setColumnCount(2)
        self._legend.setSplitLayer(True)
        self._legend.setBackgroundColor(QtGui.QColor(178, 223, 138))
        self._legend.setBackgroundEnabled(True)
        self._legend.setColumnSpace(0.5)
        self._legend.setBoxSpace(1.2)
        self.addItem(self._legend)

    def _update_scenario_details(self):
        """Updates the layout items with the scenario information."""
        if self._result is None:
            return

        self._title_label.setText(self._result.scenario.name)
        self._description_label.setText(self._result.scenario.description)

        scenario_layer = self._get_scenario_layer_in_project()
        if scenario_layer is not None:
            self._scenario_map.setLayers([scenario_layer])
            ext = scenario_layer.extent()
            self._scenario_map.setExtent(ext)
            self._scenario_map.attemptResize(
                QgsLayoutSize(200, 90, self.layout().units())
            )

        self._update_map_legend()

    def attemptResize(self, *args, **kwargs):
        """Override to set the correct position of the legend item."""
        super().attemptResize(*args, **kwargs)

        group_height = self.sizeWithUnits().height()
        group_width = self.sizeWithUnits().width()

        reference_point = self.pagePositionWithUnits()
        reference_point_x = reference_point.x()
        reference_point_y = reference_point.y()

        # Set position of the legend
        legend_height = self._legend.sizeWithUnits().height() / 2
        new_reference_y = reference_point_y + (group_height - legend_height)
        legend_ref_point = QgsLayoutPoint(
            reference_point_x, new_reference_y, self.layout().units()
        )
        self._legend.attemptMove(legend_ref_point, True, False, self.page())
        self._legend.attemptResize(
            QgsLayoutSize(group_width, legend_height, self.layout().units())
        )

        # Set height for the map
        map_height = group_height - (
            legend_height
            + self._title_label.sizeWithUnits().height()
            + self._description_label.sizeWithUnits().height()
        )
        self._scenario_map.attemptResize(
            QgsLayoutSize(
                self._scenario_map.sizeWithUnits().width(),
                map_height,
                self.layout().units(),
            )
        )

    def _get_scenario_layer_in_project(self) -> typing.Optional[QgsRasterLayer]:
        """Gets the scenario layer from the project.

        :returns: Raster layer corresponding to the scenario HPA.
        :rtype: QgsRasterLayer
        """
        if self._project is None:
            return None

        layer_root = self._project.layerTreeRoot()
        matching_tree_layers = [
            tl
            for tl in layer_root.findLayers()
            if tl.layer().name() == self._result.output_layer_name
        ]

        if len(matching_tree_layers) == 0:
            return None

        scenario_tree_layer = matching_tree_layers[0]
        return scenario_tree_layer.layer()

    def _update_map_legend(self):
        """Ensure that the legend only contains symbol categories of activities
        in the scenario layer.
        """
        self._legend.setAutoUpdateModel(False)
        self._legend.setResizeToContents(False)
        model = self._legend.model()
        activity_names = [
            activity.name.lower()
            for activity in self._result.scenario.weighted_activities
        ]

        # Hiding the first root group child title
        root_group = model.rootGroup()
        root_children = root_group.children() if root_group is not None else []

        for child in root_children:
            QgsLegendRenderer.setNodeLegendStyle(child, QgsLegendStyle.Hidden)

        for tree_layer in model.rootGroup().findLayers():
            if tree_layer.name() == self._result.output_layer_name:
                # We need to refresh the tree layer for the nodes to be loaded
                model.refreshLayerLegend(tree_layer)
                scenario_child_nodes = model.layerLegendNodes(tree_layer)
                activity_node_indices = []
                for i, child_node in enumerate(scenario_child_nodes):
                    node_name = str(child_node.data(QtCore.Qt.DisplayRole))
                    # Only show nodes for activity nodes used for the scenario
                    if node_name.lower() in activity_names:
                        activity_node_indices.append(i)

                QgsMapLayerLegendUtils.setLegendNodeOrder(
                    tree_layer, activity_node_indices
                )

                # Remove the tree layer band title
                QgsLegendRenderer.setNodeLegendStyle(tree_layer, QgsLegendStyle.Hidden)

                model.refreshLayerLegend(tree_layer)
            else:
                # Remove all other non-scenario layers
                node_index = model.node2index(tree_layer)
                if not node_index.isValid():
                    continue
                model.removeRow(node_index.row(), node_index.parent())

        # Set item font
        item_font_size = 7.5
        font = get_report_font(item_font_size)
        version = Qgis.versionInt()
        if version < 33000:
            self._legend.setStyleFont(QgsLegendStyle.SymbolLabel, font)
        else:
            style = self._legend.style(QgsLegendStyle.SymbolLabel)
            text_format = style.textFormat()
            text_format.setFont(font)
            text_format.setSize(item_font_size)
            style.setTextFormat(text_format)
            self._legend.setStyle(QgsLegendStyle.SymbolLabel, style)

        # Refresh legend
        self._legend.adjustBoxSize()
        self._legend.invalidateCache()
        self._legend.update()

    @classmethod
    def set_label_font(
        cls,
        label: QgsLayoutItemLabel,
        size: float,
        bold: bool = False,
        italic: bool = False,
        color: QtGui.QColor = None,
    ):
        """Set font properties of the given layout label item.

        :param label: Label item whose font properties will
        be updated.
        :type label: QgsLayoutItemLabel

        :param size: Point size of the font.
        :type size: int

        :param bold: True if font is to be bold, else
        False (default).
        :type bold: bool

        :param italic: True if font is to be in italics, else
        False (default).
        :type italic: bool

        :param color: Color for the text or None for the default color.
        :type color: QtGui.QColor
        """
        font = get_report_font(size, bold, italic)
        version = Qgis.versionInt()

        # Text format size unit
        if version < 33000:
            unit_type = QgsUnitTypes.RenderUnit.RenderPoints
        else:
            unit_type = Qgis.RenderUnit.Points

        # Label font setting option
        if version < 32400:
            label.setFont(font)
            if color is not None:
                label.setFontColor(color)
        else:
            txt_format = QgsTextFormat()
            txt_format.setFont(font)
            txt_format.setSize(size)
            txt_format.setSizeUnit(unit_type)

            if color is not None:
                txt_format.setColor(color)

            label.setTextFormat(txt_format)

        label.refresh()
