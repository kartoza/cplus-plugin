# -*- coding: utf-8 -*-
"""
Dialog for creating a new financial PWL.
"""

import os
import typing

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsBasicNumericFormat,
    QgsNumericFormatContext,
)
from qgis.gui import QgsGui, QgsMessageBar

from qgis.PyQt import QtCore, QtGui, QtWidgets

from qgis.PyQt.uic import loadUiType

from ..component_item_model import ActivityItemModel
from ...conf import settings_manager
from ...definitions.defaults import ICON_PATH, USER_DOCUMENTATION_SITE
from cplus_core.models.base import Activity
from ...models.financial import ActivityNpv, ActivityNpvCollection, NpvParameters
from .npv_financial_model import NpvFinancialModel
from ...lib.financials import compute_discount_value
from ...utils import FileUtils, open_documentation, tr


WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/financial_pwl_dialog.ui")
)


DEFAULT_DECIMAL_PLACES = 2


class DisplayValueFormatterItemDelegate(QtWidgets.QStyledItemDelegate):
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
        formatter.setNumberDecimalPlaces(DEFAULT_DECIMAL_PLACES)

        return formatter.formatDouble(float(value), QgsNumericFormatContext())


class FinancialValueItemDelegate(DisplayValueFormatterItemDelegate):
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


class NpvPwlManagerDialog(QtWidgets.QDialog, WidgetUi):
    """Dialog for managing NPV priority weighting layers for activities."""

    DEFAULT_YEARS = 5
    DEFAULT_DISCOUNT_RATE = 0.0
    NUM_DECIMAL_PLACES = DEFAULT_DECIMAL_PLACES
    MINIMUM_NPV_VALUE = 0.0
    MAXIMUM_NPV_VALUE = 1000000000.000000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setupUi(self)

        QgsGui.enableAutoGeometryRestore(self)

        self._message_bar = QgsMessageBar()
        self.vl_notification.addWidget(self._message_bar)

        self.sb_npv.setMaximum(self.MAXIMUM_NPV_VALUE)
        self.sb_npv.setMinimum(self.MINIMUM_NPV_VALUE)
        self.sb_npv.setDecimals(self.NUM_DECIMAL_PLACES)
        self.sb_npv.setReadOnly(True)

        # Initialize UI
        help_icon = FileUtils.get_icon("mActionHelpContents_green.svg")
        self.btn_help.setIcon(help_icon)

        copy_icon = FileUtils.get_icon("mActionEditCopy.svg")
        self.tb_copy_npv.setIcon(copy_icon)
        self.tb_copy_npv.clicked.connect(self.copy_npv)

        ok_button = self.buttonBox.button(QtWidgets.QDialogButtonBox.Ok)
        ok_button.setText(tr("Update"))
        # Prevent button from being triggered when Enter is pressed
        # and use dummy interceptor below
        ok_button.setAutoDefault(False)
        ok_button.setDefault(False)
        ok_button.clicked.connect(self._on_accepted)

        # Workaround for intercepting Enter triggers thus preventing the
        # dialog from being accepted. Not ideal but Qt issue
        self._enter_interceptor_btn.setAutoDefault(True)
        self._enter_interceptor_btn.setDefault(True)
        self._enter_interceptor_btn.setVisible(False)

        self._npv = None

        # Current selected activity identifier
        self._current_activity_identifier: str = None

        icon_pixmap = QtGui.QPixmap(ICON_PATH)
        self.icon_la.setPixmap(icon_pixmap)
        self.btn_help.clicked.connect(self.open_help)

        # Load activities
        self._activity_model = ActivityItemModel(load_pathways=False)
        self.lst_activities.setModel(self._activity_model)
        for activity in settings_manager.get_all_activities():
            self._activity_model.add_activity(activity, None)

        self.lst_activities.selectionModel().selectionChanged.connect(
            self.on_activity_selection_changed
        )

        # Set view model
        self._npv_model = NpvFinancialModel()
        self.tv_revenue_costs.setModel(self._npv_model)
        self._revenue_delegate = FinancialValueItemDelegate()
        self._costs_delegate = FinancialValueItemDelegate()
        self._discounted_value_delegate = DisplayValueFormatterItemDelegate()
        self.tv_revenue_costs.setItemDelegateForColumn(1, self._revenue_delegate)
        self.tv_revenue_costs.setItemDelegateForColumn(2, self._costs_delegate)
        self.tv_revenue_costs.setItemDelegateForColumn(
            3, self._discounted_value_delegate
        )
        self._npv_model.itemChanged.connect(self.on_npv_computation_item_changed)
        self._npv_model.rowsRemoved.connect(self.on_years_removed)
        self.tv_revenue_costs.installEventFilter(self)

        self.sb_num_years.valueChanged.connect(self.on_number_years_changed)
        self.sb_discount.valueChanged.connect(self.on_discount_rate_changed)
        self.sb_npv.valueChanged.connect(self.on_total_npv_value_changed)

        # Set default values
        self.reset_npv_values()

        self.cb_computed_npv.toggled.connect(self.on_use_computed_npvs_toggled)

        self._npv_collection = settings_manager.get_npv_collection()
        if self._npv_collection is None:
            self._npv_collection = ActivityNpvCollection(0.0, 0.0)

        self.sb_min_normalize.setValue(self._npv_collection.minimum_value)
        self.sb_max_normalize.setValue(self._npv_collection.maximum_value)
        self.cb_computed_npv.setChecked(self._npv_collection.use_computed)
        self.cb_remove_disabled.setChecked(self._npv_collection.remove_existing)

        # Select first activity
        if self._activity_model.rowCount() > 0:
            activity_idx = self._activity_model.index(0, 0)
            if activity_idx.isValid():
                self.lst_activities.selectionModel().select(
                    activity_idx, QtCore.QItemSelectionModel.ClearAndSelect
                )

        self.gp_npv_pwl.toggled.connect(self._on_activity_npv_groupbox_toggled)
        self.cb_manual_npv.toggled.connect(self._on_manual_npv_toggled)

    def open_help(self, activated: bool):
        """Opens the user documentation for the plugin in a browser."""
        open_documentation(USER_DOCUMENTATION_SITE)

    @property
    def npv_collection(self) -> ActivityNpvCollection:
        """Gets the Activity NPV collection as defined by the user.

        :returns: The Activity NPV collection containing the NPV
        parameters for activities.
        :rtype: ActivityNpvCollection
        """
        return self._npv_collection

    def eventFilter(self, observed_object: QtCore.QObject, event: QtCore.QEvent):
        """Captures events sent to specific widgets.

        :param observed_object: Object receiving the event.
        :type observed_object: QtCore.QObject

        :param event: The specific event being received by the observed object.
        :type event: QtCore.QEvent
        """
        # Resize table columns based on the size of the table view.
        if observed_object == self.tv_revenue_costs:
            if event.type() == QtCore.QEvent.Resize:
                self.resize_column_widths()

        return super().eventFilter(observed_object, event)

    def resize_column_widths(self):
        """Resize column widths of the NPV revenue and cost table based
        on its current width.
        """
        table_width = self.tv_revenue_costs.width()
        self.tv_revenue_costs.setColumnWidth(0, int(table_width * 0.09))
        self.tv_revenue_costs.setColumnWidth(1, int(table_width * 0.33))
        self.tv_revenue_costs.setColumnWidth(2, int(table_width * 0.33))
        self.tv_revenue_costs.setColumnWidth(3, int(table_width * 0.24))

    def on_number_years_changed(self, years: int):
        """Slot raised when the number of years change.

        :param years: The number of years.
        :type years: int
        """
        self._npv_model.set_number_of_years(years)
        self._update_current_activity_npv()

    def on_npv_computation_item_changed(self, item: QtGui.QStandardItem):
        """Slot raised when the data of an item has changed.

        Use this to compute discounted value as well as the NPV.

        :param item: Item whose value has changed.
        :type item: QtGui.QStandardItem
        """
        self._message_bar.clearWidgets()

        # Update discounted value only if revenue or cost
        # have changed.
        column = item.column()
        if column == 1 or column == 2:
            self.update_discounted_value(item.row())
            self._update_current_activity_npv()

    def on_total_npv_value_changed(self, value: float):
        """Slot raised when the total NPV has changed either through
        automatic computation or manual input.

        :param value: NPV value.
        :type value: float
        """
        if (
            not self._current_activity_identifier is None
            and self.cb_manual_npv.isChecked()
        ):
            activity_npv = self._get_current_activity_npv()
            if activity_npv is not None:
                activity_npv.params.absolute_npv = self.sb_npv.value()

                # Update NPV normalization range
                if self.cb_computed_npv.isChecked():
                    self._compute_min_max_range()

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

        cost = self._npv_model.data(self._npv_model.index(row, 2), QtCore.Qt.EditRole)

        # No need to compute if both revenue and cost have not been defined
        if revenue is None and cost is None:
            return

        if revenue is None:
            revenue = 0.0

        if cost is None:
            cost = 0.0

        discounted_value = compute_discount_value(
            revenue, cost, row + 1, self.sb_discount.value()
        )
        rounded_discounted_value = round(discounted_value, self.NUM_DECIMAL_PLACES)
        discounted_value_index = self._npv_model.index(row, 3)
        self._npv_model.setData(
            discounted_value_index, rounded_discounted_value, QtCore.Qt.EditRole
        )

        if not self.cb_manual_npv.isChecked():
            self.compute_npv()

    def update_all_discounted_values(self):
        """Updates all discounted values that had already been
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
        self._update_current_activity_npv()

    def compute_npv(self):
        """Computes the NPV based on the total of the discounted value and
        sets it in the corresponding text control.
        """
        npv = 0.0
        self._npv = None
        for row in range(self._npv_model.rowCount()):
            discount_value = self._npv_model.data(
                self._npv_model.index(row, 3), QtCore.Qt.EditRole
            )
            if discount_value is None:
                continue
            npv += discount_value

        self._npv = npv

        self.sb_npv.setValue(npv)

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

    def copy_npv(self):
        """Copy NPV to the clipboard."""
        QgsApplication.instance().clipboard().setText(str(self.sb_npv.value()))

    def is_valid(self) -> bool:
        """Verifies if the input data is valid.

        :returns: True if the user input is invalid, else False.
        :rtype: bool
        """
        status = True

        self._message_bar.clearWidgets()

        if self.sb_min_normalize.value() > self.sb_max_normalize.value():
            msg = tr(
                "Minimum normalization value cannot be greater than the maximum normalization value."
            )
            self._show_warning_message(msg)
            status = False

        missing_msg_tr = tr("Missing values in Year")
        for activity_mapping in self._npv_collection.mappings:
            # Only validate enabled activity mappings
            if not activity_mapping.enabled:
                continue

            activity_name = activity_mapping.activity.name

            if activity_mapping.params.manual_npv:
                if activity_mapping.params.absolute_npv is None:
                    missing_value_tr = tr("Manual NPV is missing")
                    msg = f"{activity_name}: {missing_value_tr}."
                    self._show_warning_message(msg)

            else:
                # First check if size of yearly rates matches the numbers of years
                if activity_mapping.params.years != len(
                    activity_mapping.params.yearly_rates
                ):
                    msg = tr("Size of yearly rates and number of years do not match.")
                    self._show_warning_message(f"{activity_name}: {msg}")
                    if status:
                        status = False
                    continue

                missing_value_rows = []
                for i, rates_info in enumerate(activity_mapping.params.yearly_rates):
                    if len(rates_info) < 3 or None in rates_info:
                        missing_value_rows.append(str(i + 1))

                if len(missing_value_rows) > 0:
                    msg = f"{activity_name}: {missing_msg_tr} {', '.join(missing_value_rows)}."
                    self._show_warning_message(msg)
                    if status:
                        status = False

        return status

    def _show_warning_message(self, message: str):
        """Shows a warning message in the message bar.

        :param message: Message to show in the message bar.
        :type message: str
        """
        self._message_bar.pushMessage(message, Qgis.MessageLevel.Warning)

    def on_use_computed_npvs_toggled(self, checked: bool):
        """Slot raised when the checkbox for using computed min/max NPVs is toggled.

        :param checked: True to use computed NPVs else False for the
        user to manually define the min/max values.
        :type checked: bool
        """
        if checked:
            self.sb_min_normalize.setEnabled(False)
            self.sb_max_normalize.setEnabled(False)
            self._compute_min_max_range()
        else:
            self.sb_min_normalize.setEnabled(True)
            self.sb_max_normalize.setEnabled(True)

    def _compute_min_max_range(self):
        """Computes the minimum and maximum NPV normalization range and sets
        the values in the corresponding UI controls.
        Otherwise, shows an error if the normalization range could not be
        computed.
        """
        if self._npv_collection.update_computed_normalization_range():
            self.sb_min_normalize.setValue(self._npv_collection.minimum_value)
            self.sb_max_normalize.setValue(self._npv_collection.maximum_value)
        else:
            self._show_warning_message(
                tr("Min/max normalization values could not be computed.")
            )

    def _update_base_npv_collection(self):
        """Update the NPV collection general values based on the UI values."""
        self._npv_collection.minimum_value = self.sb_min_normalize.value()
        self._npv_collection.maximum_value = self.sb_max_normalize.value()
        self._npv_collection.use_computed = self.cb_computed_npv.isChecked()
        self._npv_collection.remove_existing = self.cb_remove_disabled.isChecked()

    def _on_accepted(self):
        """Validates user input before closing."""
        if len(self._npv_collection.mappings) == 0:
            msg = tr(
                "There are no NPV PWLs to create or update. Click Cancel to close the dialog."
            )
            self._show_warning_message(msg)
            return

        self._update_base_npv_collection()

        if not self.is_valid():
            return

        # Normalize NPVs
        status = self._npv_collection.normalize_npvs()
        if not status:
            msg = tr("Unable to normalize NPVs. Check the normalization ranges.")
            self._show_warning_message(msg)
            return

        # Save NPV collection to settings
        settings_manager.save_npv_collection(self._npv_collection)

        self.accept()

    def reset_npv_values(self):
        """Resets the values for computing the NPV."""
        # Set default values
        # We are resetting to zero to remove all previous user-defined values
        self._npv_model.set_number_of_years(0)
        self._npv_model.set_number_of_years(self.DEFAULT_YEARS)
        self.sb_num_years.setValue(self.DEFAULT_YEARS)
        self.sb_discount.setValue(self.DEFAULT_DISCOUNT_RATE)
        self.cb_manual_npv.setChecked(False)
        self.sb_npv.setValue(0.0)
        self.gp_npv_pwl.setChecked(False)

    def on_activity_selection_changed(
        self, selected: QtCore.QItemSelection, deselected: QtCore.QItemSelection
    ):
        """Slot raised when the selection of activities changes.

        :param selected: Selected items.
        :type selected: QtCore.QItemSelection

        :param deselected: Deselected items.
        :type deselected: QtCore.QItemSelection
        """
        self._current_activity_identifier = None
        self.reset_npv_values()

        selected_indexes = selected.indexes()
        if len(selected_indexes) == 0:
            return

        if not selected_indexes[0].isValid():
            return

        activity_item = self._activity_model.itemFromIndex(selected_indexes[0])
        activity_npv = self._npv_collection.activity_npv(activity_item.uuid)
        if activity_npv is None:
            return

        self.load_activity_npv(activity_npv)

    def _get_current_activity_npv(self) -> typing.Optional[ActivityNpv]:
        """Gets the current activity NPV model.

        :returns: The current activity NPV model or None if the current
        identifier is not set or if no model was found in the collection.
        :rtype: ActivityNpv
        """
        if self._current_activity_identifier is None:
            return None

        return self._npv_collection.activity_npv(self._current_activity_identifier)

    def load_activity_npv(self, activity_npv: ActivityNpv):
        """Loads NPV parameters for an activity.

        :param activity_npv: Object containing the NPV parameters for an activity.
        :type activity_npv: ActivityNpv
        """
        self._current_activity_identifier = activity_npv.activity_id
        npv_params = activity_npv.params

        saved_total_npv = npv_params.absolute_npv

        self.gp_npv_pwl.setChecked(activity_npv.enabled)

        self.sb_num_years.blockSignals(True)
        self.sb_num_years.setValue(npv_params.years)
        self.sb_num_years.blockSignals(False)

        self.sb_discount.blockSignals(True)
        self.sb_discount.setValue(npv_params.discount)
        self.sb_discount.blockSignals(False)

        self.cb_manual_npv.setChecked(npv_params.manual_npv)
        if npv_params.manual_npv:
            self._on_manual_npv_toggled(True)

        self._npv_model.set_number_of_years(npv_params.years)

        # Update total NPV if auto-computed or manually defined
        for i, year_info in enumerate(npv_params.yearly_rates):
            if len(year_info) < 3:
                continue

            revenue_index = self._npv_model.index(i, 1)
            self._npv_model.setData(revenue_index, year_info[0], QtCore.Qt.EditRole)
            cost_index = self._npv_model.index(i, 2)
            self._npv_model.setData(cost_index, year_info[1], QtCore.Qt.EditRole)

        self.update_all_discounted_values()

        if npv_params.manual_npv:
            self.sb_npv.setValue(saved_total_npv)

    def _update_current_activity_npv(self):
        """Update NPV parameters changes made in the UI to the underlying
        activity NPV.
        """
        if self._current_activity_identifier is None:
            return

        activity_npv = self._npv_collection.activity_npv(
            self._current_activity_identifier
        )

        activity_npv.params.manual_npv = self.cb_manual_npv.isChecked()
        activity_npv.enabled = self.gp_npv_pwl.isChecked()

        if not activity_npv.params.manual_npv:
            activity_npv.params.years = self.sb_num_years.value()
            activity_npv.params.discount = self.sb_discount.value()

            yearly_rates = []
            for row in range(self._npv_model.rowCount()):
                revenue_value = self._npv_model.data(
                    self._npv_model.index(row, 1), QtCore.Qt.EditRole
                )
                cost_value = self._npv_model.data(
                    self._npv_model.index(row, 2), QtCore.Qt.EditRole
                )
                discount_value = self._npv_model.data(
                    self._npv_model.index(row, 3), QtCore.Qt.EditRole
                )
                yearly_rates.append((revenue_value, cost_value, discount_value))

            activity_npv.params.yearly_rates = yearly_rates

        if not self.cb_manual_npv.isChecked() and self._npv is not None:
            activity_npv.params.absolute_npv = self._npv
        else:
            activity_npv.params.absolute_npv = self.sb_npv.value()

        # Update NPV normalization range
        if self.cb_computed_npv.isChecked():
            self._compute_min_max_range()

    def selected_activity(self) -> typing.Optional[Activity]:
        """Gets the current selected activity.

        :returns: Current selected activity or None if there is
        no selection.
        :rtype: Activity
        """
        selected_indexes = self.lst_activities.selectedIndexes()
        if len(selected_indexes) == 0:
            return None

        if not selected_indexes[0].isValid():
            return

        activity_item = self._activity_model.itemFromIndex(selected_indexes[0])

        return activity_item.activity

    def _on_activity_npv_groupbox_toggled(self, checked: bool):
        """Slot raised when the NPV PWL groupbox has been enabled or disabled.

        :param checked: True if the groupbox is enabled else False.
        :type checked: bool
        """
        if checked and self._current_activity_identifier is None:
            selected_activity = self.selected_activity()
            if selected_activity is not None:
                npv_params = NpvParameters(
                    self.DEFAULT_YEARS, self.DEFAULT_DISCOUNT_RATE
                )
                activity_npv = ActivityNpv(npv_params, True, selected_activity)
                self._npv_collection.mappings.append(activity_npv)
                self._current_activity_identifier = str(selected_activity.uuid)

        elif self._current_activity_identifier is not None:
            if not checked:
                self._update_current_activity_npv()
            else:
                activity_npv = self._get_current_activity_npv()
                if activity_npv is not None:
                    activity_npv.enabled = self.gp_npv_pwl.isChecked()

                # Update NPV normalization range
                if self.cb_computed_npv.isChecked():
                    self._compute_min_max_range()

    def _on_manual_npv_toggled(self, checked: bool):
        """Slot raised to enable/disable manual NPV value.

        :param checked: True if the manual NPV is enabled else False.
        :type checked: bool
        """
        if checked:
            self.sb_npv.setReadOnly(False)
            self.sb_npv.setFocus()
            self.enable_npv_parameters_widgets(False)

            activity_npv = self._get_current_activity_npv()
            if activity_npv is not None:
                activity_npv.params.manual_npv = self.cb_manual_npv.isChecked()

        else:
            self.sb_npv.setReadOnly(True)
            self.enable_npv_parameters_widgets(True)
            self.compute_npv()

    def enable_npv_parameters_widgets(self, enable: bool):
        """Enable or disable the UI widgets for specifying NPV parameters.

        :param enable: True to enable the widgets, else False to disable.
        :type enable: bool
        """
        self.sb_num_years.setEnabled(enable)
        self.sb_discount.setEnabled(enable)
        self.tv_revenue_costs.setEnabled(enable)
