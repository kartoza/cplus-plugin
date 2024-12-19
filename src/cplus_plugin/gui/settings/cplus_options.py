# coding=utf-8

"""Plugin global settings.

Covers the plugin global settings which a user can set and save. The settings
will be saved using QgsSettings. Settings can be accessed via the QGIS options,
a button on the docking widget, and from the toolbar menu.
"""

import os
import typing

import qgis.core
import qgis.gui

from qgis.analysis import QgsAlignRaster

from qgis.gui import QgsFileWidget, QgsOptionsPageWidget
from qgis.gui import QgsOptionsWidgetFactory
from qgis.PyQt import uic, QtWidgets
from qgis.PyQt.QtGui import (
    QIcon,
    QShowEvent,
)
from qgis.utils import iface

from qgis.PyQt.QtWidgets import QFileDialog, QListWidgetItem, QMessageBox, QWidget
from qgis.PyQt import QtCore

from ...api.base import ApiRequestStatus
from ...api.carbon import (
    start_irrecoverable_carbon_download,
    get_downloader_task,
)
from ...conf import (
    settings_manager,
    Settings,
)
from ...models.base import DataSourceType
from ...definitions.constants import CPLUS_OPTIONS_KEY
from ...definitions.defaults import (
    GENERAL_OPTIONS_TITLE,
    ICON_PATH,
    OPTIONS_TITLE,
)
from ...trends_earth.constants import API_URL, TIMEOUT
from ...utils import FileUtils, log, tr
from ...trends_earth import auth, api, download

Ui_DlgSettings, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/cplus_settings.ui")
)
Ui_TrendsEarthDlgSettingsLogin, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/trends_earth_login.ui")
)
Ui_TrendsEarthDlgSettingsEditForgotPassword, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/trends_earth_forgot_password.ui")
)
Ui_TrendsEarthSettingsRegister, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/trends_earth_register.ui")
)
Ui_TrendsEarthSettingsEditUpdate, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "../../ui/trends_earth_edit_update.ui")
)


settings = QtCore.QSettings()


class tr_settings(QtCore.QObject):
    def tr(txt):
        return QtCore.QCoreApplication.translate(self.__class__.__name__, txt)


# Function to indicate if child is a folder within parent
def is_subdir(child, parent):
    parent = os.path.normpath(os.path.realpath(parent))
    child = os.path.normpath(os.path.realpath(child))

    if not os.path.isdir(parent) or not os.path.isdir(child):
        return False
    elif child == parent:
        return True
    head, tail = os.path.split(child)

    if head == parent:
        return True
    elif tail == "":
        return False
    else:
        return is_subdir(head, parent)


def _get_user_email(auth_setup, warn=True):
    """get user email for a particular service from authConfig"""
    authConfig = auth.get_auth_config(auth_setup, warn=warn)
    if not authConfig:
        return None

    email = authConfig.config("username")
    log(email)
    log(authConfig.config("password"))
    if warn and email is None:
        QtWidgets.QMessageBox.critical(
            None,
            tr_settings.tr("Error"),
            tr_settings.tr(
                "Please setup access to {auth_setup.name} before "
                "using this function."
            ),
        )
        return None
    else:
        return email


class DlgSettingsRegister(QtWidgets.QDialog, Ui_TrendsEarthSettingsRegister):
    authConfigInitialised = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.admin_bounds_key = download.get_admin_bounds()
        self.country.addItems(sorted(self.admin_bounds_key.keys()))

        self.buttonBox.accepted.connect(self.register)
        self.buttonBox.rejected.connect(self.close)

        self.trends_earth_api_client = api.APIClient(API_URL, TIMEOUT)

    def register(self):
        if not self.email.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your email address.")
            )

            return
        elif not self.name.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your name.")
            )

            return
        elif not self.organization.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your organization.")
            )

            return
        elif not self.country.currentText():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your country.")
            )

            return

        resp = self.trends_earth_api_client.register(
            self.email.text(),
            self.name.text(),
            self.organization.text(),
            self.country.currentText(),
        )

        if resp:
            self.close()
            if resp.get("status", 200) == 200:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Success"),
                    self.tr(
                        "User registered. Your password "
                        f"has been emailed to {self.email.text()}. "
                        "Enter that password in CPLUS settings "
                        "to finish setting up the plugin."
                    ),
                )
                # add a new auth conf that have to be completed with pwd
                authConfigId = auth.init_auth_config(
                    auth.TE_API_AUTH_SETUP, email=self.email.text()
                )

                if authConfigId:
                    self.authConfigInitialised.emit(authConfigId)
                    return authConfigId
            else:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Registration failed"),
                    self.tr(resp.get("detail", "")),
                )
        else:
            QtWidgets.QMessageBox.information(
                None,
                self.tr("Failed"),
                self.tr(
                    "Failed to register. Please check your internet connection and try again."
                ),
            )
            return None


class DlgSettingsLogin(QtWidgets.QDialog, Ui_TrendsEarthDlgSettingsLogin):
    def __init__(self, parent=None, main_widget=None):
        super().__init__(parent)

        self.setupUi(self)

        self.buttonBox.accepted.connect(self.login)
        self.buttonBox.rejected.connect(self.close)

        self.ok = False
        self.trends_earth_api_client = api.APIClient(API_URL, TIMEOUT)
        self.main_widget = main_widget

    def showEvent(self, event):
        super().showEvent(event)

        email = _get_user_email(auth.TE_API_AUTH_SETUP, warn=False)

        if email:
            self.email.setText(email)

    def login(self):
        if not self.email.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your email address.")
            )

            return
        elif not self.password.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your password.")
            )

            return

        if self.trends_earth_api_client.login_test(
            self.email.text(), self.password.text()
        ):
            QtWidgets.QMessageBox.information(
                None,
                self.tr("Success"),
                self.tr(
                    "Logged in to the CPLUS server as "
                    f"{self.email.text()}.<html><p>Welcome to "
                    "CPLUS!</p><p>You only need to login once.<p></html>"
                ),
            )
            auth.init_auth_config(
                auth.TE_API_AUTH_SETUP, self.email.text(), self.password.text()
            )

            settings_manager.delete_online_scenario()
            settings_manager.remove_default_layers()
            self.main_widget.fetch_default_layer_list()
            self.main_widget.fetch_scenario_history_list()
            self.ok = True
            self.close()


class DlgSettingsEditUpdate(QtWidgets.QDialog, Ui_TrendsEarthSettingsEditUpdate):
    def __init__(self, user, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.user = user

        self.admin_bounds_key = download.get_admin_bounds()

        self.email.setText(user["email"])
        self.name.setText(user["name"])
        self.organization.setText(user["institution"])

        # Add countries, and set index to currently chosen country
        self.country.addItems(sorted(self.admin_bounds_key.keys()))
        index = self.country.findText(user["country"])

        if index != -1:
            self.country.setCurrentIndex(index)

        self.buttonBox.accepted.connect(self.update_profile)
        self.buttonBox.rejected.connect(self.close)

        self.ok = False
        self.trends_earth_api_client = api.APIClient(API_URL, TIMEOUT)

    def update_profile(self):
        if not self.email.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your email address.")
            )

            return
        elif not self.name.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your name.")
            )

            return
        elif not self.organization.text():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your organization.")
            )

            return
        elif not self.country.currentText():
            QtWidgets.QMessageBox.critical(
                None, self.tr("Error"), self.tr("Enter your country.")
            )

            return

        resp = self.trends_earth_api_client.update_user(
            self.email.text(),
            self.name.text(),
            self.organization.text(),
            self.country.currentText(),
        )

        if resp:
            if resp.get("status", 200) == 200:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Saved"),
                    self.tr("Updated information for {}.").format(self.email.text()),
                )
                self.close()
                self.ok = True
            else:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Failed"),
                    self.tr(resp.get("detail", "")),
                )
                self.close()
        else:
            QtWidgets.QMessageBox.information(
                None,
                self.tr("Failed"),
                self.tr(
                    "Failed to update user information. Please check your internet connection and try again."
                ),
            )


class DlgSettingsEditForgotPassword(
    QtWidgets.QDialog, Ui_TrendsEarthDlgSettingsEditForgotPassword
):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setupUi(self)

        self.buttonBox.accepted.connect(self.reset_password)
        self.buttonBox.rejected.connect(self.close)

        self.ok = False

        self.trends_earth_api_client = api.APIClient(API_URL, TIMEOUT)

    def showEvent(self, event):
        super().showEvent(event)

        email = _get_user_email(auth.TE_API_AUTH_SETUP, warn=False)

        if email:
            self.email.setText(email)

    def reset_password(self):
        if not self.email.text():
            QtWidgets.QMessageBox.critical(
                None,
                self.tr("Error"),
                self.tr("Enter your email address to reset your password."),
            )

            return

        reply = QtWidgets.QMessageBox.question(
            None,
            self.tr("Reset password?"),
            self.tr(
                "Are you sure you want to reset the password for "
                f"{self.email.text()}? Your new password will be emailed "
                "to you."
            ),
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            resp = self.trends_earth_api_client.recover_pwd(self.email.text())

            if resp:
                if resp.get("status", 200) == 200:
                    self.close()
                    QtWidgets.QMessageBox.information(
                        None,
                        self.tr("Success"),
                        self.tr(
                            f"The password has been reset for {self.email.text()}. "
                            "Check your email for the new password, and then "
                            "return to Trends.Earth to enter it."
                        ),
                    )
                    self.ok = True
                else:
                    self.close()
                    QtWidgets.QMessageBox.information(
                        None,
                        self.tr("Failed"),
                        self.tr(resp.get("detail", "")),
                    )
            else:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Failed"),
                    self.tr(
                        "Failed to reset password. Please check your internet connection and try again."
                    ),
                )


class CplusSettings(Ui_DlgSettings, QgsOptionsPageWidget):
    message_bar: qgis.gui.QgsMessageBar

    """CPLUS plugin settings class.

    Class which manages the CPLUS settings. Initializes the UI, which can be accessed
    from the menu drop-down or the QGIS settings.
    """

    def __init__(self, parent=None, main_widget=None) -> None:
        """QGIS CPLUS Plugin Settings dialog."""
        QgsOptionsPageWidget.__init__(self, parent)
        self.main_widget = main_widget

        self.setupUi(self)
        self.message_bar = qgis.gui.QgsMessageBar(self)
        self.layout().insertWidget(0, self.message_bar)

        self.settings = qgis.core.QgsSettings()
        settings_manager.settings_updated[str, object].connect(self.on_settings_changed)

        # Connections
        self.folder_data.fileChanged.connect(self.base_dir_exists)

        self.map_layer_file_widget.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.map_layer_box.layerChanged.connect(self.map_layer_changed)

        self.mask_layer_widget.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.mask_layer_box.layerChanged.connect(self.mask_layer_changed)

        self.resample_method_box.addItem(
            tr("Nearest Neighbour"), QgsAlignRaster.ResampleAlg.RA_NearestNeighbour
        )
        self.resample_method_box.addItem(
            tr("Bilinear (2x2 Kernel)"), QgsAlignRaster.ResampleAlg.RA_Bilinear
        )
        self.resample_method_box.addItem(
            tr("Cubic (4x4 Kernel)"), QgsAlignRaster.ResampleAlg.RA_Cubic
        )
        self.resample_method_box.addItem(
            tr("Cubic B-Spline (4x4 Kernel)"), QgsAlignRaster.ResampleAlg.RA_CubicSpline
        )
        self.resample_method_box.addItem(
            tr("Lanczos (6x6 Kernel)"), QgsAlignRaster.ResampleAlg.RA_Lanczos
        )
        self.resample_method_box.addItem(
            tr("Average"), QgsAlignRaster.ResampleAlg.RA_Average
        )
        self.resample_method_box.addItem(tr("Mode"), QgsAlignRaster.ResampleAlg.RA_Mode)
        self.resample_method_box.addItem(
            tr("Maximum"), QgsAlignRaster.ResampleAlg.RA_Max
        )
        self.resample_method_box.addItem(
            tr("Minimum"), QgsAlignRaster.ResampleAlg.RA_Min
        )
        self.resample_method_box.addItem(
            tr("Median"), QgsAlignRaster.ResampleAlg.RA_Median
        )
        self.resample_method_box.addItem(
            tr("First Quartile (Q1)"), QgsAlignRaster.ResampleAlg.RA_Q1
        )
        self.resample_method_box.addItem(
            tr("Third Quartile (Q3)"), QgsAlignRaster.ResampleAlg.RA_Q3
        )

        # Mask layers
        add_icon = FileUtils.get_icon("symbologyAdd.svg")
        self.btn_add_mask.setIcon(add_icon)
        self.btn_add_mask.clicked.connect(self._on_add_mask_layer)

        remove_icon = FileUtils.get_icon("symbologyRemove.svg")
        self.btn_delete_mask.setIcon(remove_icon)
        self.btn_delete_mask.setEnabled(False)
        self.btn_delete_mask.clicked.connect(self._on_remove_mask_layer)

        edit_icon = FileUtils.get_icon("mActionToggleEditing.svg")
        self.btn_edit_mask.setIcon(edit_icon)
        self.btn_edit_mask.setEnabled(False)
        self.btn_edit_mask.clicked.connect(self._on_edit_mask_layer)

        # Trends.Earth settings
        self.dlg_settings_register = DlgSettingsRegister()
        self.dlg_settings_login = DlgSettingsLogin(main_widget=self.main_widget)

        self.pushButton_register.clicked.connect(self.register)
        self.pushButton_login.clicked.connect(self.login)
        self.pushButton_update_profile.clicked.connect(self.update_profile)
        self.pushButton_forgot_pwd.clicked.connect(self.forgot_pwd)
        self.pushButton_delete_user.clicked.connect(self.delete)

        # Irrecoverable carbon
        self.gb_ic_reference_layer.toggled.connect(
            self._on_irrecoverable_group_box_toggled
        )

        self._irrecoverable_group = QtWidgets.QButtonGroup(self)
        self._irrecoverable_group.addButton(self.rb_local, DataSourceType.LOCAL.value)
        self._irrecoverable_group.addButton(self.rb_online, DataSourceType.ONLINE.value)
        self._irrecoverable_group.idToggled.connect(
            self._on_irrecoverable_button_group_toggled
        )

        tif_file_filter = tr("GeoTIFF (*.tif *.tiff *.TIF *.TIFF)")

        self.fw_irrecoverable_carbon.setDialogTitle(
            tr("Select Irrecoverable Carbon Dataset")
        )
        self.fw_irrecoverable_carbon.setRelativeStorage(
            QgsFileWidget.RelativeStorage.Absolute
        )
        self.fw_irrecoverable_carbon.setStorageMode(QgsFileWidget.StorageMode.GetFile)
        self.fw_irrecoverable_carbon.setFilter(tif_file_filter)

        self.cbo_irrecoverable_carbon.layerChanged.connect(
            self._on_irrecoverable_carbon_layer_changed
        )

        self.fw_save_online_file.setDialogTitle(
            tr("Specify Save Location of Irrecoverable Carbon Dataset")
        )
        self.fw_save_online_file.setRelativeStorage(
            QgsFileWidget.RelativeStorage.Absolute
        )
        self.fw_save_online_file.setStorageMode(QgsFileWidget.StorageMode.SaveFile)
        self.fw_save_online_file.setFilter(tif_file_filter)

        # self.lbl_url_tip.setPixmap(FileUtils.get_pixmap("info_green.svg"))
        # self.lbl_url_tip.setScaledContents(True)

        self.btn_ic_download.setIcon(FileUtils.get_icon("downloading_svg.svg"))
        self.btn_ic_download.clicked.connect(self.on_download_irrecoverable_carbon)

        # Use the task to get real time updates on the download progress
        self._irrecoverable_carbon_downloader = None
        self._configure_irrecoverable_carbon_downloader_updates()

        # Load gui default value from settings
        auth_id = settings.value("cplusplugin/auth")
        if auth_id is not None:
            self.authcfg_acs.setConfigId(auth_id)
        else:
            log("Authentication configuration id was not found")

        # load gui default value from settings
        # self.reloadAuthConfigurations()

        self.trends_earth_api_client = api.APIClient(API_URL, TIMEOUT)

    def apply(self) -> None:
        """This is called on OK click in the QGIS options panel."""

        self.save_settings()

    def map_layer_changed(self, layer):
        """Sets the file path of the selected layer in file path input

        :param layer: Qgis map layer
        :type layer: QgsMapLayer
        """
        if layer is not None:
            self.map_layer_file_widget.setFilePath(layer.source())

    def mask_layer_changed(self, layer):
        """Sets the file path of the selected mask layer in file path input

        :param layer: Qgis map layer
        :type layer: QgsMapLayer
        """
        if layer is not None:
            self.mask_layer_widget.setFilePath(layer.source())

    def on_settings_changed(self, name: str, value: typing.Any):
        """Slot raised when settings has been changed.

        :param name: Name of the setting that has changed.
        :type name: str

        :param value: New value for the given settings name.
        :type value: Any
        """
        # Create NCS pathway subdirectory if base directory has changed.
        if name == Settings.BASE_DIR.value:
            if not value:
                return

            # Create data directories if they do not exist.
            FileUtils.create_ncs_pathways_dir(value)
            FileUtils.create_ncs_carbon_dir(value)
            FileUtils.create_pwls_dir(value)

    def base_dir_exists(self) -> bool:
        """Checks if the provided base directory exists.
        A warning messages is presented if the directory does not exist.

        :returns: Whether the base directory exists
        :rtype: bool
        """

        # Clears the error messages when doing next check
        self.message_bar.clearWidgets()

        folder_found = False
        base_dir_path = self.folder_data.filePath()
        if not os.path.exists(base_dir_path):
            # File not found
            self.message_bar.pushWarning(
                "CPLUS - Base directory not found: ", base_dir_path
            )
        else:
            folder_found = True

        return folder_found

    def save_settings(self) -> None:
        """Saves the settings.
        Also does error checking for settings (e.g if the custom logo exists).
        Will present the user with an error message if an issue is found.
        """
        # Advanced settings
        base_dir_path = self.folder_data.filePath()
        settings_manager.set_value(Settings.BASE_DIR, base_dir_path)

        # Carbon layers coefficient saving
        coefficient = self.carbon_coefficient_box.value()
        settings_manager.set_value(Settings.CARBON_COEFFICIENT, coefficient)

        # Pathway suitability index
        pathway_suitability_index = self.suitability_index_box.value()
        settings_manager.set_value(
            Settings.PATHWAY_SUITABILITY_INDEX, pathway_suitability_index
        )

        # Snapping settings saving
        settings_manager.set_value(
            Settings.SNAPPING_ENABLED, self.snapping_group_box.isChecked()
        )
        snap_layer_path = self.map_layer_file_widget.filePath()
        settings_manager.set_value(Settings.SNAP_LAYER, snap_layer_path)

        settings_manager.set_value(
            Settings.RESCALE_VALUES, self.rescale_values.isChecked()
        )
        settings_manager.set_value(
            Settings.RESAMPLING_METHOD, self.resample_method_box.currentIndex()
        )

        # Saving sieve function settings

        settings_manager.set_value(
            Settings.SIEVE_ENABLED, self.sieve_group_box.isChecked()
        )
        mask_layer_path = self.mask_layer_widget.filePath()
        settings_manager.set_value(Settings.SIEVE_MASK_PATH, mask_layer_path)

        settings_manager.set_value(
            Settings.SIEVE_THRESHOLD, self.pixel_size_box.value()
        )

        # Mask layers settings
        mask_paths = ""
        for row in range(0, self.lst_mask_layers.count()):
            item = self.lst_mask_layers.item(row)
            item_path = item.data(QtCore.Qt.DisplayRole)
            mask_paths += f"{item_path},"

        settings_manager.set_value(Settings.MASK_LAYERS_PATHS, mask_paths)

        # Checks if the provided base directory exists
        if not os.path.exists(base_dir_path):
            iface.messageBar().pushCritical(
                "CPLUS - Base directory not found: ", base_dir_path
            )

        # Irrecoverable carbon
        settings_manager.set_value(
            Settings.IRRECOVERABLE_CARBON_LOCAL_SOURCE,
            self.fw_irrecoverable_carbon.filePath(),
        )
        settings_manager.set_value(
            Settings.IRRECOVERABLE_CARBON_ONLINE_SOURCE, self.txt_ic_url.text()
        )
        settings_manager.set_value(
            Settings.IRRECOVERABLE_CARBON_ONLINE_LOCAL_PATH,
            self.fw_save_online_file.filePath(),
        )

        if self.rb_local.isChecked():
            settings_manager.set_value(
                Settings.IRRECOVERABLE_CARBON_SOURCE_TYPE, DataSourceType.LOCAL.value
            )
        elif self.rb_online.isChecked():
            settings_manager.set_value(
                Settings.IRRECOVERABLE_CARBON_SOURCE_TYPE, DataSourceType.ONLINE.value
            )

        settings_manager.set_value(
            Settings.IRRECOVERABLE_CARBON_ENABLED,
            self.gb_ic_reference_layer.isChecked(),
        )

    def load_settings(self) -> None:
        """Loads the settings and displays it in the options UI"""
        # Advanced settings
        base_dir = settings_manager.get_value(Settings.BASE_DIR, default="")
        self.folder_data.setFilePath(base_dir)
        self.base_dir_exists()

        # Carbon layers coefficient
        coefficient = settings_manager.get_value(
            Settings.CARBON_COEFFICIENT, default=0.0
        )
        self.carbon_coefficient_box.setValue(float(coefficient))

        # Pathway suitability index
        pathway_suitability_index = settings_manager.get_value(
            Settings.PATHWAY_SUITABILITY_INDEX, default=0
        )
        self.suitability_index_box.setValue(float(pathway_suitability_index))

        # Snapping settings
        self.snapping_group_box.setChecked(
            settings_manager.get_value(
                Settings.SNAPPING_ENABLED, default=False, setting_type=bool
            )
        )
        snap_layer_path = settings_manager.get_value(Settings.SNAP_LAYER, default="")
        self.map_layer_file_widget.setFilePath(snap_layer_path)

        self.rescale_values.setChecked(
            settings_manager.get_value(
                Settings.RESCALE_VALUES, default=False, setting_type=bool
            )
        )
        self.resample_method_box.setCurrentIndex(
            int(settings_manager.get_value(Settings.RESAMPLING_METHOD, default=0))
        )

        # Sieve settings
        self.sieve_group_box.setChecked(
            settings_manager.get_value(
                Settings.SIEVE_ENABLED, default=False, setting_type=bool
            )
        )
        mask_layer_path = settings_manager.get_value(
            Settings.SIEVE_MASK_PATH, default=""
        )
        self.mask_layer_widget.setFilePath(mask_layer_path)

        self.pixel_size_box.setValue(
            float(settings_manager.get_value(Settings.SIEVE_THRESHOLD, default=10.0))
        )

        # Mask layers settings
        mask_paths = settings_manager.get_value(
            Settings.MASK_LAYERS_PATHS, default=None
        )
        mask_paths_list = mask_paths.split(",") if mask_paths else []

        for mask_path in mask_paths_list:
            if mask_path == "":
                continue
            item = QListWidgetItem()
            item.setData(QtCore.Qt.DisplayRole, mask_path)
            self.lst_mask_layers.addItem(item)

        if len(mask_paths_list) > 0:
            self.mask_layers_changed()

        # Irrecoverable carbon
        irrecoverable_carbon_enabled = settings_manager.get_value(
            Settings.IRRECOVERABLE_CARBON_ENABLED, default=False
        )
        if irrecoverable_carbon_enabled:
            self.gb_ic_reference_layer.setChecked(True)
        else:
            self.gb_ic_reference_layer.setChecked(False)

        # Local path
        self.fw_irrecoverable_carbon.setFilePath(
            settings_manager.get_value(
                Settings.IRRECOVERABLE_CARBON_LOCAL_SOURCE, default=""
            )
        )

        # Online config
        self.txt_ic_url.setText(
            settings_manager.get_value(
                Settings.IRRECOVERABLE_CARBON_ONLINE_SOURCE, default=""
            )
        )
        self.fw_save_online_file.setFilePath(
            settings_manager.get_value(
                Settings.IRRECOVERABLE_CARBON_ONLINE_LOCAL_PATH, default=""
            )
        )

        source_type_int = settings_manager.get_value(
            Settings.IRRECOVERABLE_CARBON_SOURCE_TYPE,
            default=DataSourceType.ONLINE.value,
            setting_type=int,
        )
        if source_type_int == DataSourceType.LOCAL.value:
            self.rb_local.setChecked(True)
            self.sw_irrecoverable_carbon.setCurrentIndex(0)
        elif source_type_int == DataSourceType.ONLINE.value:
            self.rb_online.setChecked(True)
            self.sw_irrecoverable_carbon.setCurrentIndex(1)

        self.validate_current_irrecoverable_data_source()

        self.reload_irrecoverable_carbon_download_status()

    def reload_irrecoverable_carbon_download_status(self):
        """Fetch the latest download status of the irrecoverable carbon
        dataset from the online source if applicable.
        """
        status = settings_manager.get_value(
            Settings.IRRECOVERABLE_CARBON_ONLINE_DOWNLOAD_STATUS, None, int
        )
        if status is None:
            return

        # Set notification icon
        path = ""
        status_type = ApiRequestStatus.from_int(status)
        if status_type == ApiRequestStatus.COMPLETED:
            path = FileUtils.get_icon_path("mIconSuccess.svg")
        elif status_type == ApiRequestStatus.ERROR:
            path = FileUtils.get_icon_path("mIconWarning.svg")
        elif status_type == ApiRequestStatus.NOT_STARTED:
            path = FileUtils.get_icon_path("mIndicatorTemporal.svg")
        elif status_type == ApiRequestStatus.IN_PROGRESS:
            path = FileUtils.get_icon_path("progress-indicator.svg")
        elif status_type == ApiRequestStatus.CANCELED:
            path = FileUtils.get_icon_path("mTaskCancel.svg")

        self.lbl_download_status_tip.svg_path = path

        # Set notification description
        description = settings_manager.get_value(
            Settings.IRRECOVERABLE_CARBON_ONLINE_STATUS_DESCRIPTION, "", str
        )
        self.lbl_ic_download_status.setText(description)

    def _configure_irrecoverable_carbon_downloader_updates(self):
        """Get current downloader and connect the signals of the
        task in order to update the UI.
        """
        # Use the task to get real time updates on the download progress
        self._irrecoverable_carbon_downloader = get_downloader_task()

        if self._irrecoverable_carbon_downloader is None:
            return

        self._irrecoverable_carbon_downloader.started.connect(
            self.reload_irrecoverable_carbon_download_status
        )
        self._irrecoverable_carbon_downloader.canceled.connect(
            self.reload_irrecoverable_carbon_download_status
        )
        self._irrecoverable_carbon_downloader.completed.connect(
            self.reload_irrecoverable_carbon_download_status
        )
        self._irrecoverable_carbon_downloader.error_occurred.connect(
            self.reload_irrecoverable_carbon_download_status
        )

    def validate_irrecoverable_carbon_url(self) -> bool:
        """Checks if the irrecoverable data URL is valid.

        :returns: True if the link is valid else False if the
        URL is empty, points to a local file or if not
        well-formed.
        :rtype: bool
        """
        dataset_url = self.txt_ic_url.text()
        if not dataset_url:
            self.message_bar.pushWarning(
                tr("CPLUS - Irrecoverable carbon dataset"), tr("URL not defined")
            )
            return False

        url_checker = QtCore.QUrl(dataset_url, QtCore.QUrl.StrictMode)
        if url_checker.isLocalFile():
            self.message_bar.pushWarning(
                tr("CPLUS - Irrecoverable carbon dataset"),
                tr("Invalid URL referencing a local file"),
            )
            return False
        else:
            if not url_checker.isValid():
                self.message_bar.pushWarning(
                    tr("CPLUS - Irrecoverable carbon dataset"),
                    tr("URL is invalid."),
                )
                return False

        return True

    def on_download_irrecoverable_carbon(self):
        """Slot raised to check download link and initiate download
        process of the irrecoverable carbon data.

        The function will check and save the currently defined local
        save as path for the reference dataset as this will be required
        and fetched by the background download process.

        """
        valid_url = self.validate_irrecoverable_carbon_url()
        if not valid_url:
            tr_title = tr("CPLUS - Online irrecoverable carbon dataset")
            tr_msg = tr("URL for downloading irrecoverable carbon data is invalid.")
            self.message_bar.pushWarning(tr_title, tr_msg)

            return

        if not self.fw_save_online_file.filePath():
            tr_title = tr("CPLUS - Online irrecoverable carbon dataset")
            tr_msg = tr(
                "File path for saving downloaded irrecoverable "
                "carbon dataset not defined"
            )
            self.message_bar.pushWarning(tr_title, tr_msg)

            return

        # Check if the local path has been saved in settings or varies from
        # what already is saved in settings
        download_save_path = self.fw_save_online_file.filePath()
        if (
            settings_manager.get_value(
                Settings.IRRECOVERABLE_CARBON_ONLINE_LOCAL_PATH,
                default="",
                setting_type=str,
            )
            != download_save_path
        ):
            settings_manager.set_value(
                Settings.IRRECOVERABLE_CARBON_ONLINE_LOCAL_PATH, download_save_path
            )

        # (Re)initiate download
        start_irrecoverable_carbon_download()

        # Get downloader for UI updates
        self._configure_irrecoverable_carbon_downloader_updates()

    def validate_current_irrecoverable_data_source(self):
        """Checks if the currently selected irrecoverable data source
        is valid.
        """
        self.message_bar.clearWidgets()

        if self.rb_local.isChecked():
            local_path = self.fw_irrecoverable_carbon.filePath()
            if not os.path.exists(local_path):
                tr_msg = tr("CPLUS - Local irrecoverable carbon dataset not found")
                self.message_bar.pushWarning(tr_msg, local_path)
        elif self.rb_online.isChecked():
            _ = self.validate_irrecoverable_carbon_url()
            if not self.fw_save_online_file.filePath():
                tr_msg = tr("CPLUS - Online irrecoverable carbon dataset")
                self.message_bar.pushWarning(
                    tr_msg, tr("File path for saving dataset not defined")
                )

    def showEvent(self, event: QShowEvent) -> None:
        """Show event being called. This will display the plugin settings.
        The stored/saved settings will be loaded.

        :param event: Event that has been triggered
        :type event: QShowEvent
        """

        super().showEvent(event)
        self.load_settings()

    def closeEvent(self, event: QShowEvent) -> None:
        """When closing the setings.

        :param event: Event that has been triggered
        :type event: QShowEvent
        """

        super().closeEvent(event)

    def _on_irrecoverable_button_group_toggled(self, button_id: int, toggled: bool):
        """Slot raised when a button in the irrecoverable
        button group has been toggled.

        :param button_id: Button identifier.
        :type button_id: int

        :param toggled: True if the button is checked else False
        if unchecked.
        :type toggled: bool
        """
        if button_id == DataSourceType.LOCAL.value and toggled:
            self.sw_irrecoverable_carbon.setCurrentIndex(0)
        elif button_id == DataSourceType.ONLINE.value and toggled:
            self.sw_irrecoverable_carbon.setCurrentIndex(1)

    def _on_irrecoverable_group_box_toggled(self, toggled: bool):
        """Slot raised when the irrecoverable group box has
        been toggled.

        :param toggled: True if the button is checked else
        False if unchecked.
        :type toggled: bool
        """
        settings_manager.set_value(Settings.IRRECOVERABLE_CARBON_ENABLED, toggled)

    def _on_irrecoverable_carbon_layer_changed(self, layer: qgis.core.QgsMapLayer):
        """Sets the file path of the currently selected irrecoverable
        layer in the corresponding file input widget.

        :param layer: Currently selected layer.
        :type layer: QgsMapLayer
        """
        if layer is not None:
            self.fw_irrecoverable_carbon.setFilePath(layer.source())

    def _on_add_mask_layer(self, activated: bool):
        """Slot raised to add a mask layer."""
        data_dir = settings_manager.get_value(Settings.LAST_MASK_DIR, default=None)

        if not data_dir:
            data_dir = os.path.expanduser("~")

        mask_path = self._show_mask_path_selector(data_dir)
        if not mask_path:
            return

        item = QListWidgetItem()
        item.setData(QtCore.Qt.DisplayRole, mask_path)

        if self.lst_mask_layers.findItems(mask_path, QtCore.Qt.MatchExactly):
            error_tr = tr("The selected mask layer already exists.")
            self.message_bar.pushMessage(error_tr, qgis.core.Qgis.MessageLevel.Warning)
            return

        self.lst_mask_layers.addItem(item)
        settings_manager.set_value(Settings.LAST_MASK_DIR, os.path.dirname(mask_path))

        self.mask_layers_changed()

    def _on_edit_mask_layer(self, activated: bool):
        """Slot raised to edit a mask layer."""

        item = self.lst_mask_layers.currentItem()
        if not item:
            error_tr = tr("Select a mask layer first.")
            self.message_bar.pushMessage(error_tr, qgis.core.Qgis.MessageLevel.Warning)
            return
        mask_path = self._show_mask_path_selector(item.data(QtCore.Qt.DisplayRole))
        if not mask_path:
            return

        if self.lst_mask_layers.findItems(mask_path, QtCore.Qt.MatchExactly):
            error_tr = tr("The selected mask layer already exists.")
            self.message_bar.pushMessage(error_tr, qgis.core.Qgis.MessageLevel.Warning)
            return

        item.setData(QtCore.Qt.DisplayRole, mask_path)

    def _on_remove_mask_layer(self, activated: bool):
        """Slot raised to remove one or more selected mask layers."""
        item = self.lst_mask_layers.currentItem()
        if not item:
            error_tr = tr("Select the target mask layer first, before removing it.")
            self.message_bar.pushMessage(error_tr, qgis.core.Qgis.MessageLevel.Warning)
            return

        reply = QMessageBox.warning(
            self,
            tr("QGIS CPLUS PLUGIN | Settings"),
            tr('Remove the mask layer from "{}"?').format(
                item.data(QtCore.Qt.DisplayRole)
            ),
            QMessageBox.Yes,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            item_row = self.lst_mask_layers.row(item)
            self.lst_mask_layers.takeItem(item_row)

            self.mask_layers_changed()

    def _show_mask_path_selector(self, layer_dir: str) -> str:
        """Show file selector dialog for selecting a mask layer."""
        filter_tr = tr("All files")

        layer_path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr("Select Mask Layer"),
            layer_dir,
            f"{filter_tr} (*.*)",
            options=QFileDialog.DontResolveSymlinks,
        )
        if not layer_path:
            return ""

        return layer_path

    def mask_layers_changed(self):
        contains_items = self.lst_mask_layers.count() > 0

        self.btn_edit_mask.setEnabled(contains_items)
        self.btn_delete_mask.setEnabled(contains_items)

    def register(self):
        self.dlg_settings_register.exec_()

    def login(self):
        self.dlg_settings_login.exec_()

    def forgot_pwd(self):
        dlg_settings_edit_forgot_password = DlgSettingsEditForgotPassword()
        dlg_settings_edit_forgot_password.exec_()

    def update_profile(self):
        user = self.trends_earth_api_client.get_user()

        if not user:
            return
        dlg_settings_edit_update = DlgSettingsEditUpdate(user)
        dlg_settings_edit_update.exec_()

    def delete(self):
        email = _get_user_email(auth.TE_API_AUTH_SETUP)

        if not email:
            return

        reply = QtWidgets.QMessageBox.question(
            None,
            self.tr("Delete user?"),
            self.tr(
                "Are you sure you want to delete the user {}? All of your tasks will "
                "be lost and you will no longer be able to process data online "
                "using Trends.Earth.".format(email)
            ),
            QtWidgets.QMessageBox.Yes,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            resp = self.trends_earth_api_client.delete_user(email)

            if resp:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Success"),
                    self.tr(f"Trends.Earth user {email} deleted."),
                )
                # remove currently used config (as set in QSettings) and
                # trigger GUI
                auth.remove_current_auth_config(auth.TE_API_AUTH_SETUP)
            else:
                QtWidgets.QMessageBox.information(
                    None,
                    self.tr("Failed"),
                    self.tr("Failed to delete user."),
                )

    def reloadAuthConfigurations(self):
        authConfigId = settings.value(
            f"{settings_manager.BASE_GROUP_NAME}/{auth.TE_API_AUTH_SETUP.key}", None
        )
        if not authConfigId:
            self.message_bar.pushCritical(
                "Trends.Earth", self.tr("Please register in order to use Trends.Earth")
            )
            return
        configs = qgis.core.QgsApplication.authManager().availableAuthMethodConfigs()
        if authConfigId not in configs.keys():
            QtCore.QSettings().setValue(
                f"{settings_manager.BASE_GROUP_NAME}/{auth.TE_API_AUTH_SETUP.key}", None
            )


class CplusOptionsFactory(QgsOptionsWidgetFactory):
    """Options factory initializes the CPLUS settings.

    Class which creates the widget required for the CPLUS settings.
    QgsOptionsWidgetFactory is used to accomplish this.
    """

    def __init__(self, main_widget=None) -> None:
        """QGIS CPLUS Plugin Settings factory."""
        super().__init__()

        # Check version for API compatibility for managing items in
        # options tree view.
        version = qgis.core.Qgis.versionInt()
        if version < 33200:
            self.setTitle(GENERAL_OPTIONS_TITLE)
        else:
            self.setTitle(OPTIONS_TITLE)
            self.setKey(CPLUS_OPTIONS_KEY)
        self.main_widget = main_widget

    def icon(self) -> QIcon:
        """Returns the icon which will be used for the CPLUS options tab.

        :returns: An icon object which contains the provided custom icon
        :rtype: QIcon
        """

        return QIcon(ICON_PATH)

    def path(self) -> typing.List[str]:
        """
        Returns the path to place the widget page at.

        This instructs the registry to place the log options tab under the
        main CPLUS settings.

        :returns: Path name of the main CPLUS settings.
        :rtype: list
        """
        version = qgis.core.Qgis.versionInt()
        if version < 33200:
            return [OPTIONS_TITLE]

        return list()

    def createWidget(self, parent: QWidget) -> CplusSettings:
        """Creates a widget for CPLUS settings.

        :param parent: Parent widget
        :type parent: QWidget

        :returns: Widget to be used in the QGIS options
        :rtype: CplusSettings
        """

        return CplusSettings(parent, main_widget=self.main_widget)
