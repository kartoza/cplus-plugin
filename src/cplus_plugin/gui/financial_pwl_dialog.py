# -*- coding: utf-8 -*-
"""
Dialog for creating a new financial PWL.
"""

import os
import typing
import uuid

from qgis.core import Qgis, QgsBasicNumericFormat, QgsNumericFormatContext
from qgis.gui import QgsGui, QgsMessageBar

from qgis.PyQt import QtCore, QtGui, QtWidgets

from qgis.PyQt.uic import loadUiType

from ..definitions.defaults import ICON_PATH, USER_DOCUMENTATION_SITE
from .financial_npv_model import FinancialNpvModel
from ..lib.financials import compute_discount_value
from ..utils import FileUtils, open_documentation, tr

WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/financial_pwl_dialog.ui")
)


class FinancialValueItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    Delegate for ensuring only numbers are specified in financial value
    fields.
    """

    def createEditor(
        self,
        parent: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        idx: QtCore.QModelIndex,
    ) -> QtWidgets.QLineEdit:
        """Creates a line edit control whose input value is limited to numbers only.

        :param parent: Parent widget.
        :type parent: QtWidgets.QWidget

        :param option: Options for drawing the widget in the view.
        :type option: QtWidgets.QStyleOptionViewItem

        :param idx: Location of the request in the data model.
        :type idx: QtCore.QModelIndex

        :returns: The editor widget.
        :rtype: QtWidgets.QLineEdit
        """
        line_edit = QtWidgets.QLineEdit(parent)
        line_edit.setFrame(False)
        line_edit.setMaxLength(50)
        validator = QtGui.QDoubleValidator()
        validator.setDecimals(2)
        line_edit.setValidator(validator)

        return line_edit

    def setEditorData(self, widget: QtWidgets.QWidget, idx: QtCore.QModelIndex):
        """Sets the data to be displayed and edited by the editor.

        :param widget: Editor widget.
        :type widget: QtWidgets.QWidget

        :param idx: Location in the data model.
        :type idx: QtCore.QModelIndex
        """
        value = idx.model().data(idx, QtCore.Qt.EditRole)
        if value is None:
            widget.setText("")
        else:
            widget.setText(str(value))

    def displayText(self, value: float, locale: QtCore.QLocale) -> str:
        """Format the value to incorporate thousand comma separator.

        :param value: Value of the display role provided by the model.
        :type value: float

        :param locale: Locale for the value in the display role.
        :type locale: QtCore.QLocale

        :returns: Formatted value of the display role data.
        :rtype: str
        """
        if value is None:
            return ""

        formatter = QgsBasicNumericFormat()
        formatter.setShowThousandsSeparator(True)
        formatter.setNumberDecimalPlaces(2)

        return formatter.formatDouble(float(value), QgsNumericFormatContext())

    def setModelData(
        self,
        widget: QtWidgets.QWidget,
        model: QtCore.QAbstractItemModel,
        idx: QtCore.QModelIndex,
    ):
        """Gets data from the editor widget and stores it in the specified
        model at the item index.

        :param widget: Editor widget.
        :type widget: QtWidgets.QWidget

        :param model: Model to store the editor data in.
        :type model: QtCore.QAbstractItemModel

        :param idx: Location in the data model.
        :type idx: QtCore.QModelIndex
        """
        if not widget.text():
            value = None
        else:
            value = float(widget.text())

        model.setData(idx, value, QtCore.Qt.EditRole)

    def updateEditorGeometry(
        self,
        widget: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        idx: QtCore.QModelIndex,
    ):
        """Updates the geometry of the editor for the item with the given index,
        according to the rectangle specified in the option.

        :param widget: Widget whose geometry will be updated.
        :type widget: QtWidgets.QWidget

        :param option: Option containing the rectangle for
        updating the widget.
        :type option: QtWidgets.QStyleOptionViewItem

        :param idx: Location of the widget in the data model.
        :type idx: QtCore.QModelIndex
        """
        widget.setGeometry(option.rect)


class ValueFormatterItemDelegate(QtWidgets.QStyledItemDelegate):
    """
    Delegate for formatting numeric values using thousand comma separator,
    number of decimal places etc.
    """

    def displayText(self, value: float, locale: QtCore.QLocale) -> str:
        """Format the value to incorporate thousand comma separator.

        :param value: Value of the display role provided by the model.
        :type value: float

        :param locale: Locale for the value in the display role.
        :type locale: QtCore.QLocale

        :returns: Formatted value of the display role data.
        :rtype: str
        """
        if value is None:
            return ""

        formatter = QgsBasicNumericFormat()
        formatter.setShowThousandsSeparator(True)
        formatter.setNumberDecimalPlaces(2)

        return formatter.formatDouble(float(value), QgsNumericFormatContext())


class FinancialPwlDialog(QtWidgets.QDialog, WidgetUi):
    """Dialog for creating a new financial PWL."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        QgsGui.enableAutoGeometryRestore(self)

        # Initialize UI
        help_icon = FileUtils.get_icon("mActionHelpContents_green.svg")
        self.btn_help.setIcon(help_icon)

        # copy_icon = FileUtils.get_icon("mActionHelpContents_green.svg")
        # self.btn_help.setIcon(help_icon)

        ok_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok)
        ok_button.setText(tr("Create"))

        self._npv = 0.0

        icon_pixmap = QtGui.QPixmap(ICON_PATH)
        self.icon_la.setPixmap(icon_pixmap)
        self.btn_help.clicked.connect(self.open_help)

        # Set view model
        self._npv_model = FinancialNpvModel()
        self.tv_revenue_costs.setModel(self._npv_model)
        self._revenue_delegate = FinancialValueItemDelegate()
        self._costs_delegate = FinancialValueItemDelegate()
        self._discounted_value_delegate = ValueFormatterItemDelegate()
        self.tv_revenue_costs.setItemDelegateForColumn(1, self._revenue_delegate)
        self.tv_revenue_costs.setItemDelegateForColumn(2, self._costs_delegate)
        self.tv_revenue_costs.setItemDelegateForColumn(
            3, self._discounted_value_delegate
        )
        self._npv_model.itemChanged.connect(self.on_item_changed)
        self._npv_model.rowsRemoved.connect(self.on_years_removed)

        self.sb_num_years.valueChanged.connect(self.on_number_years_changed)
        self.sb_discount.valueChanged.connect(self.on_discount_rate_changed)

        # Set default values
        self.sb_num_years.setValue(5)

    def open_help(self, activated: bool):
        """Opens the user documentation for the plugin in a browser."""
        open_documentation(USER_DOCUMENTATION_SITE)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        """Use this event to trigger the resizing of the table columns.

        :param event: Contains the geometry information of the dialog.
        :type event: QtGui.QResizeEvent
        """
        table_width = self.tv_revenue_costs.width()
        self.tv_revenue_costs.setColumnWidth(0, table_width * 0.1)
        self.tv_revenue_costs.setColumnWidth(1, table_width * 0.35)
        self.tv_revenue_costs.setColumnWidth(2, table_width * 0.35)
        self.tv_revenue_costs.setColumnWidth(3, table_width * 0.2)

    def on_number_years_changed(self, years: int):
        """Slot raised when the number of years change.

        :param years: The number of years.
        :type years: int
        """
        self._npv_model.set_number_of_years(years)

    def on_item_changed(self, item: QtGui.QStandardItem):
        """Slot raised when the data of an item has changed.

        Use this to compute discounted value as well as the NPV.

        :param item: Item whose value has changed.
        :type item: QtGui.QStandardItem
        """
        # Update discounted value only if revenue or cost
        # have changed.
        column = item.column()
        if column == 1 or column == 2:
            self.update_discounted_value(item.row())

    def update_discounted_value(self, row: int):
        """Updated the discounted value for the given row number.

        :param row: Row number to compute the discounted value.
        :type row: int
        """
        # For computation purposes, any None value will be
        # translated to zero.
        revenue = self._npv_model.data(
            self._npv_model.index(row, 1), QtCore.Qt.EditRole
        )
        if revenue is None:
            revenue = 0.0

        cost = self._npv_model.data(self._npv_model.index(row, 2), QtCore.Qt.EditRole)
        if cost is None:
            cost = 0.0

        discounted_value = compute_discount_value(
            revenue, cost, row + 1, self.sb_discount.value()
        )
        discounted_value_index = self._npv_model.index(row, 3)
        self._npv_model.setData(
            discounted_value_index, discounted_value, QtCore.Qt.EditRole
        )

        self.compute_npv()

    def update_all_discounted_values(self):
        """Updates al discounted values that had already been
        computed using the revised discount rate.
        """
        for row in range(self._npv_model.rowCount()):
            discount_value = self._npv_model.data(
                self._npv_model.index(row, 3), QtCore.Qt.EditRole
            )
            if discount_value is None:
                continue
            self.update_discounted_value(row)

    def on_discount_rate_changed(self, discount_rate: float):
        """Slot raised when discount rate has changed.

        :param discount_rate: New discount rate.
        :type discount_rate: float
        """
        # Recompute discounted values
        self.update_all_discounted_values()

    def compute_npv(self):
        """Computes the NPV based on the total of the discounted value and
        sets it in the corresponding text control.
        """
        npv = 0.0
        for row in range(self._npv_model.rowCount()):
            discount_value = self._npv_model.data(
                self._npv_model.index(row, 3), QtCore.Qt.EditRole
            )
            if discount_value is None:
                continue
            npv += discount_value

        self._npv = npv

        # Format display
        formatter = QgsBasicNumericFormat()
        formatter.setShowThousandsSeparator(True)
        formatter.setNumberDecimalPlaces(2)

        self.txt_npv.setText(formatter.formatDouble(npv, QgsNumericFormatContext()))

    def on_years_removed(self, index: QtCore.QModelIndex, start: int, end: int):
        """Slot raised when the year rows have been removed.

        :param index: Reference item at the given location.
        :type index: QtCore.QModelIndex

        :param start: Start location of the items that have been removed.
        :type start: int

        :param end: End location of the items that have been removed.
        :type end: int
        """
        # Recalculate the NPV
        self.compute_npv()
