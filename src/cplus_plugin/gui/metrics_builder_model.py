# -*- coding: utf-8 -*-
"""
MVC models for the metrics builder.
"""
from enum import IntEnum
import typing

from qgis.PyQt import QtCore, QtGui

from ..definitions.constants import ACTIVITY_NAME

from ..models.base import Activity
from ..models.report import ActivityColumnMetric, MetricColumn, MetricType

from ..utils import FileUtils, log, tr


METRIC_COLUMN_LIST_ITEM_TYPE = QtGui.QStandardItem.UserType + 6
ACTIVITY_NAME_TABLE_ITEM_TYPE = QtGui.QStandardItem.UserType + 7
ACTIVITY_COLUMN_METRIC_TABLE_ITEM_TYPE = QtGui.QStandardItem.UserType + 8

COLUMN_METRIC_STR = "<Column metric>"
CUSTOM_METRIC_STR = "<Custom metric>"


class MetricColumnListItem(QtGui.QStandardItem):
    """Represents a single carbon layer path."""

    def __init__(self, name_column: typing.Union[str, MetricColumn]):
        super().__init__()

        self._column = None
        if isinstance(name_column, str):
            self._column = MetricColumn(name_column, name_column, "")
        else:
            self._column = name_column

        self.name = self._column.name

        column_icon = FileUtils.get_icon("table_column.svg")
        self.setIcon(column_icon)

    @property
    def name(self) -> str:
        """Gets the name of the column.

        :returns: The name of the column.
        :rtype: str
        """
        return self._column.name

    @name.setter
    def name(self, name: str):
        """Update the column name.

        :param name: Name of the column.
        :type name: str
        """
        self._column.name = name
        self.setText(name)
        self.setToolTip(name)

    @property
    def header(self) -> str:
        """Gets the column header.

        :returns: The column header.
        :rtype: str
        """
        return self._column.header

    @header.setter
    def header(self, header: str):
        """Update the column header.

        :param header: Header of the column.
        :type header: str
        """
        self._column.header = header

    @property
    def alignment(self) -> QtCore.Qt.AlignmentFlag:
        """Gest the alignment of the column text.

        :returns: The alignment of the column text.
        :rtype: QtCore.Qt.AlignmentFlag
        """
        return self._column.alignment

    @alignment.setter
    def alignment(self, alignment: QtCore.Qt.AlignmentFlag):
        """Update the column alignment.

        :param alignment: Alignment of the column text.
        :type alignment: QtCore.Qt.AlignmentFlag
        """
        self._column.alignment = alignment

    @property
    def expression(self) -> str:
        """Gets the column-wide expression used by activity
        metrics.

        :returns: The column-wide expression used by the activity
        metrics.
        :rtype: str
        """
        return self._column.expression

    @expression.setter
    def expression(self, expression: str):
        """Set the column-wide expression to be used by the activity
        metrics.

        :param expression: Column-wide expression to be used for
        activity metrics.
        :type expression: str
        """
        self._column.expression = expression

    @property
    def auto_calculated(self):
        """Indicates whether the column value is auto-calculated.

        :returns: True if the column value is auto-calculated else
        False.
        :rtype: bool
        """
        return self._column.auto_calculated

    @auto_calculated.setter
    def auto_calculated(self, auto_calculated: bool):
        """Set whether the column value is auto-calculated.

        :param auto_calculated: True if the column value is
        auto-calculated else False.
        :type auto_calculated: bool
        """
        self._column.auto_calculated = auto_calculated

    @property
    def is_valid(self) -> bool:
        """Returns the validity status of the item.

        The name and header label should be defined.

        :returns: True if valid, else False.
        :rtype: bool
        """
        if not self._column.name or not self._column.header:
            return False

        return True

    @property
    def model(self) -> MetricColumn:
        """Gets the underlying data model used in the item.

        :returns: The underlying data model used in the item.
        :rtype: MetricColumn
        """
        return self._column

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the item.
        :rtype: int
        """
        return METRIC_COLUMN_LIST_ITEM_TYPE


class VerticalMoveDirection(IntEnum):
    """Move an item up or down."""

    UP = 0
    DOWN = 1


class HorizontalMoveDirection(IntEnum):
    """Move an item left or right."""

    LEFT = 0
    RIGHT = 1


class MetricColumnListModel(QtGui.QStandardItemModel):
    """View model for list-based metric column objects."""

    column_added = QtCore.pyqtSignal(MetricColumnListItem)
    column_removed = QtCore.pyqtSignal(int)
    column_moved = QtCore.pyqtSignal(MetricColumnListItem, VerticalMoveDirection)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(1)

    @property
    def column_items(self) -> typing.List[MetricColumnListItem]:
        """Gets all the column items in the model.

        :returns: All the column items in the model.
        :rtype: typing.List[MetricColumnListItem]
        """
        return [self.item(r) for r in range(self.rowCount())]

    def add_new_column(self, name_column: typing.Union[str, MetricColumn]) -> bool:
        """Adds a new column to the model.

        :param name_column: Name of the column or metric column
        data model.
        :type name_column:

        :returns: True if the column was successfully added
        due to an already existing column with a similar name,
        else False.
        :rtype: bool
        """
        column_item = MetricColumnListItem(name_column)
        item = self.add_column(column_item)
        if item is None:
            return False

        return True

    def add_column(
        self, column_item: MetricColumnListItem
    ) -> typing.Optional[MetricColumnListItem]:
        """Adds a column item to the model.

        :param column_item: Column item to be added to the model.
        :type column_item: MetricColumnListItem

        :returns: The item successfully added to the model else
        None if the item could not be successfully added due to
        an already existing name in the model.
        :rtype: MetricColumnListItem or None
        """
        existing_column = self.column_exists(column_item.name)
        if existing_column:
            return None

        self.appendRow(column_item)

        self.column_added.emit(column_item)

        return column_item

    def column_exists(self, name: str) -> bool:
        """Checks if a column with the given name exists.

        :param name: Name of the column.
        :type name: str

        :returns: True if the column name exists, else False.
        :rtype: bool
        """
        item = self.item_from_name(name)

        if item is None:
            return False

        return True

    def item_from_name(self, name: str) -> typing.Optional[MetricColumnListItem]:
        """Gets the model item from the column name.

        It performs a case-insensitive search of
        the first matching model item.

        :param name: Name of the column.
        :type name:str

        :returns: The first matching model item if
        found else None.
        :rtype: MetricColumnListItem
        """
        items = self.findItems(name, QtCore.Qt.MatchFixedString)

        if len(items) > 0:
            return items[0]

        return None

    def remove_column(self, name: str) -> bool:
        """Removes the column matching the given name.

        :param name: Name of the column to be removed.
        :type name: str

        :returns: True if the column was successfully
        removed else False if there is no column matching
        the given name.
        :rtype: bool
        """
        item = self.item_from_name(name)

        if item is None:
            return False

        status = self.removeRows(item.row(), 1)

        if status:
            self.column_removed.emit(item)

        return status

    def move_column_up(self, row: int) -> int:
        """Moves the column item in the given row one level up.

        :param row: Column item in the given row to be moved up.
        :type row: int

        :returns: New position of the column item or -1 if the column
        item was not moved up.
        :rtype: int
        """
        return self.move_column(row, VerticalMoveDirection.UP)

    def move_column_down(self, row: int) -> int:
        """Moves the column item in the given row one level down.

        :param row: Column item in the given row to be moved down.
        :type row: int

        :returns: New position of the column item or -1 if the column
        item was not moved down.
        :rtype: int
        """
        return self.move_column(row, VerticalMoveDirection.DOWN)

    def move_column(self, row: int, direction: VerticalMoveDirection) -> int:
        """Moves the column item in the given row one by a level
        up or down as defined in the direction.

        :param row: Position of the column item to be moved.
        :type row: int

        :param direction: Direction to move the column item.
        :type direction: VerticalMoveDirection

        :returns: New position of the column item or -1 if the column
        item was not moved.
        :rtype: int
        """
        if direction == VerticalMoveDirection.UP and row < 1:
            return -1
        elif direction == VerticalMoveDirection.DOWN and row >= self.rowCount() - 1:
            return -1

        items = self.takeRow(row)
        if items is None or len(items) == 0:
            return -1

        if direction == VerticalMoveDirection.UP:
            new_position = row - 1
        elif direction == VerticalMoveDirection.DOWN:
            new_position = row + 1

        self.insertRow(new_position, items[0])

        self.column_moved.emit(items[0], direction)

        return new_position


class ActivityNameTableItem(QtGui.QStandardItem):
    """Represents an activity name in the metrics table."""

    def __init__(self, activity: Activity):
        super().__init__()

        self._activity = activity

        self.setEditable(False)
        self.setText(activity.name)
        self.setTextAlignment(QtCore.Qt.AlignCenter)

        background = self.background()
        background.setColor(QtCore.Qt.lightGray)
        background.setStyle(QtCore.Qt.SolidPattern)
        self.setBackground(background)

    @property
    def activity(self) -> Activity:
        """Gets the activity model in the item.

        :returns: The activity model in the item.
        :rtype: Activity
        """
        return self._activity

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the item.
        :rtype: int
        """
        return ACTIVITY_NAME_TABLE_ITEM_TYPE


class ActivityColumnMetricItem(QtGui.QStandardItem):
    """Represents an activity's metric information for a
    specific column.
    """

    def __init__(self, activity_column_metric: ActivityColumnMetric):
        super().__init__()

        self._activity_column_metric = activity_column_metric

        if activity_column_metric.metric_column.auto_calculated:
            self.setEditable(False)
        else:
            self.setEditable(True)

        self._update_display_text()
        self.setTextAlignment(
            self._activity_column_metric.metric_column.alignment
            | QtCore.Qt.AlignVCenter
        )

        # self.setData(self._activity_column_metric.metric_type, QtCore.Qt.EditRole)

        self._update_tool_tip()

    @staticmethod
    def metric_type_to_str(metric_type: MetricType) -> str:
        """Returns the corresponding string representation for
        the given metric type.

        :param metric_type: Type of metric or expression.
        :type metric_type: MetricType

        :returns: The corresponding string representation of
        the given metric type.
        :rtype: str
        """
        if metric_type == MetricType.COLUMN:
            return tr(COLUMN_METRIC_STR)
        elif metric_type == MetricType.CUSTOM:
            return tr(CUSTOM_METRIC_STR)
        else:
            return tr("<Not set>")

    @property
    def column_metric(self) -> ActivityColumnMetric:
        """Gets the underlying activity column metric data model.

        :returns: The underlying activity column metric data model.
        :rtype: ActivityColumnMetric
        """
        return self._activity_column_metric

    @property
    def metric_type(self) -> MetricType:
        """Gets the metric type of the underlying data model.

        :returns: The metric type of the underlying data model.
        :rtype: MetricType
        """
        return self._activity_column_metric.metric_type

    def update_metric_type(self, metric_type: MetricType, expression: str = ""):
        """Updates the metric type of the underlying metric model.

        :param metric_type: Metric type to be used by the model.
        :type metric_type: MetricType

        :param expression: Expression for the given metric type.
        Default is an empty string.
        :type expression: str
        """
        if self._activity_column_metric.metric_type == metric_type:
            return

        self._activity_column_metric.metric_type = metric_type
        self._activity_column_metric.expression = expression

        self._update_display_text()
        self._update_tool_tip()

    def update_metric_model(self, model: MetricColumn):
        """Updates the underlying metric model.

        :param model: Metric column containing updated properties.
        :type model: MetricColumn
        """
        if (
            self._activity_column_metric.metric_type == MetricType.NOT_SET
            and model.expression
        ):
            self._activity_column_metric.metric_type = MetricType.COLUMN
            self._activity_column_metric.expression = model.expression
        elif (
            self._activity_column_metric.metric_type == MetricType.COLUMN
            and not model.expression
        ):
            self._activity_column_metric.metric_type = MetricType.NOT_SET
            self._activity_column_metric.expression = ""

        self._activity_column_metric.metric_column = model

        self._update_display_text()
        self._update_tool_tip()

    def _update_tool_tip(self):
        """Updates the tooltip to show the expression."""
        if self._activity_column_metric.metric_type == MetricType.NOT_SET:
            self.setToolTip("")
        else:
            self.setToolTip(self._activity_column_metric.expression)

    def _update_display_text(self):
        """Updates the display text of the item.

        This should be called when there are any
        changes in the activity column metric model.
        """
        self.setText(
            ActivityColumnMetricItem.metric_type_to_str(
                self._activity_column_metric.metric_type
            )
        )

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the item.
        :rtype: int
        """
        return ACTIVITY_COLUMN_METRIC_TABLE_ITEM_TYPE


class ActivityMetricTableModel(QtGui.QStandardItemModel):
    """View model for activity metrics in a table."""

    def __init__(self, parent=None, columns: typing.List[MetricColumn] = None):
        super().__init__(parent)

        self.setColumnCount(1)
        # Add default activity name header
        self.setHorizontalHeaderLabels([tr(ACTIVITY_NAME)])

        self._metric_columns = []
        if columns is not None:
            self._metric_columns = columns

    @property
    def metric_columns(self) -> typing.List[MetricColumn]:
        """Gets the metric columns used in the model to
        define the headers.

        :returns: Metric columns used in the model.
        :rtype: typing.List[MetricColumn]
        """
        return list(self._metric_columns)

    def append_column(self, column: MetricColumn):
        """Adds a column to the model based on the information
        in the metric column.

        :param column: Metric column containing information
        for defining the new column.
        :type column: MetricColumn
        """
        column_items = []

        # Update rows based on the selected activities
        for activity in self.activities:
            activity_column_metric = ActivityColumnMetric(
                activity,
                column,
                MetricType.COLUMN if column.expression else MetricType.NOT_SET,
                column.expression if column.expression else "",
            )
            item = ActivityColumnMetricItem(activity_column_metric)
            column_items.append(item)

        self.appendColumn(column_items)
        self.setHeaderData(
            self.columnCount() - 1,
            QtCore.Qt.Horizontal,
            column.header,
            QtCore.Qt.DisplayRole,
        )

        self._metric_columns.append(column)

    def remove_column(self, index: int) -> bool:
        """Remove the column at the specified index.

        The index will be normalized to reflect the first
        metric column since index zero is reserved for the
        activity name column which is fixed.

        :param index: Index of the column to be removed.
        :type index: int

        :returns: True if the column was successfully
        removed else False.
        :rtype: bool
        """
        if index == -1:
            return False

        model_index = index + 1
        status = self.removeColumns(model_index, 1)

        del self._metric_columns[index]

        return status

    def update_column_properties(self, index: int, column: MetricColumn):
        """Updates the properties of an underlying metric column
        in the model.

        :param index: Index of the column to the updated.
        :type index: int

        :param column: Updated column metric object.
        :type column: MetricColumn
        """
        model_index = index + 1
        if model_index == 0 or model_index >= self.columnCount():
            return False

        # Update header
        self.setHeaderData(
            model_index, QtCore.Qt.Horizontal, column.header, QtCore.Qt.DisplayRole
        )
        self._metric_columns[index] = column

        # Update corresponding column metric items in the given column
        for r in range(self.rowCount()):
            column_metric_item = self.item(r, model_index)
            if column_metric_item is None:
                continue

            column_metric_item.update_metric_model(column)

    def append_activity(self, activity: Activity) -> bool:
        """Adds an activity row in the activity metrics table.

        :param activity: Activity to be added.
        :type activity: Activity

        :returns: True if the activity was successfully added
        else False.
        :rtype: bool
        """
        # Check if there is a similar activity
        matching_activities = [
            act for act in self.activities if act.uuid == activity.uuid
        ]
        if len(matching_activities) > 0:
            return False

        row_items = []

        activity_item = ActivityNameTableItem(activity)
        row_items.append(activity_item)

        # Set corresponding activity column metric items
        for mc in self._metric_columns:
            activity_column_metric = ActivityColumnMetric(
                activity,
                mc,
                MetricType.COLUMN if mc.expression else MetricType.NOT_SET,
                mc.expression if mc.expression else "",
            )
            row_items.append(ActivityColumnMetricItem(activity_column_metric))

        self.appendRow(row_items)

        return True

    @property
    def activities(self) -> typing.List[Activity]:
        """Gets all the activities in the model.

        :returns: All activities in the model.
        :rtype: typing.List[Activity]
        """
        return [self.item(r, 0).activity for r in range(self.rowCount())]

    def move_column(
        self, current_index: int, direction: HorizontalMoveDirection
    ) -> int:
        """Move the column in the specified index left or right depending on the
        move direction.

        :param current_index: Index of the column to be moved.
        :type current_index: int

        :param direction: Direction to move the column, either left or right.
        :type direction: HorizontalMoveDirection

        :returns: New position of the column or -1 if the column
        item was not moved.
        :rtype: int
        """
        # The activity name column will always be on the extreme left (LTR)
        if current_index <= 1 and direction == HorizontalMoveDirection.LEFT:
            return -1

        if (
            current_index >= self.columnCount() - 1
            and direction == HorizontalMoveDirection.RIGHT
        ):
            return -1

        if direction == HorizontalMoveDirection.LEFT:
            new_index = current_index - 1
        else:
            new_index = current_index + 1

        # Move header and items
        header_item = self.takeHorizontalHeaderItem(current_index)
        column_items = self.takeColumn(current_index)
        self.insertColumn(new_index, column_items)
        self.setHorizontalHeaderItem(new_index, header_item)

        return new_index

    def move_column_left(self, current_index: int) -> int:
        """Convenience method for moving a column to the left.

        :param current_index: Index of the column to be moved.
        :type current_index: int

        :returns: New position of the column or -1 if the column
        item was not moved.
        :rtype: int
        """
        return self.move_column(current_index, HorizontalMoveDirection.LEFT)

    def move_column_right(self, current_index: int) -> int:
        """Convenience method for moving a column to the right.

        :param current_index: Index of the column to be moved.
        :type current_index: int

        :returns: New position of the column or -1 if the column
        item was not moved.
        :rtype: int
        """
        return self.move_column(current_index, HorizontalMoveDirection.RIGHT)