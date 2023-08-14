# -*- coding: utf-8 -*-

"""
 The plugin main window class.
"""

import os
import uuid

import datetime

from functools import partial

from pathlib import Path

from qgis.PyQt import (
    QtCore,
    QtGui,
    QtWidgets,
    QtNetwork,
)

from qgis.PyQt.uic import loadUiType

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsProject,
    QgsProcessing,
    QgsProcessingAlgRunnerTask,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsRasterLayer,
    QgsRectangle,
    QgsTask,
    QgsWkbTypes,
    QgsLayerTreeLayer,
)

from qgis.gui import (
    QgsMessageBar,
    QgsRubberBand,
)

from qgis.utils import iface

from .component_item_model import ImplementationModelItem
from .implementation_model_widget import ImplementationModelContainerWidget
from .priority_group_widget import PriorityGroupWidget

from ..models.base import Scenario, ScenarioResult, ScenarioState, SpatialExtent

from ..conf import settings_manager, Settings

from ..lib.reports.manager import report_manager

from ..resources import *

from ..utils import (
    clean_filename,
    open_documentation,
    tr,
    log,
    FileUtils,
)

from ..definitions.defaults import (
    ADD_LAYER_ICON_PATH,
    PILOT_AREA_EXTENT,
    OPTIONS_TITLE,
    ICON_PATH,
    QGIS_GDAL_PROVIDER,
    REMOVE_LAYER_ICON_PATH,
    SCENARIO_OUTPUT_FILE_NAME,
    SCENARIO_OUTPUT_LAYER_NAME,
    USER_DOCUMENTATION_SITE,
    LAYER_STYLES,
    LAYER_STYLES_WEIGHTED,
)
from ..definitions.constants import (
    NCS_CARBON_SEGMENT,
    PRIORITY_LAYERS_SEGMENT,
    IM_GROUP_LAYER_NAME,
    IM_WEIGHTED_GROUP_NAME,
    NCS_PATHWAYS_GROUP_LAYER_NAME,
)

from .progress_dialog import ProgressDialog

WidgetUi, _ = loadUiType(
    os.path.join(os.path.dirname(__file__), "../ui/qgis_cplus_main_dockwidget.ui")
)


class QgisCplusMain(QtWidgets.QDockWidget, WidgetUi):
    """Main plugin UI"""

    analysis_finished = QtCore.pyqtSignal(ScenarioResult)

    def __init__(
        self,
        iface,
        parent=None,
    ):
        super().__init__(parent)
        self.setupUi(self)
        self.iface = iface
        self.progress_dialog = None
        self.task = None
        self.processing_cancelled = False

        # Insert widget for step 2
        self.implementation_model_widget = ImplementationModelContainerWidget(self)
        self.tab_widget.insertTab(
            1, self.implementation_model_widget, self.tr("Step 2")
        )
        self.tab_widget.currentChanged.connect(self.on_tab_step_changed)

        self.prepare_input()

        # Step 3, priority weighting layers initialization
        self.priority_groups_widgets = {}

        self.initialize_priority_layers()

        self.position_feedback = QgsProcessingFeedback()
        self.processing_context = QgsProcessingContext()

        self.scenario_result = None

        self.analysis_finished.connect(self.post_analysis)

        # Report manager
        self.rpm = report_manager
        self.rpm.generate_started.connect(self.on_report_running)
        self.rpm.generate_completed.connect(self.on_report_finished)

    def prepare_input(self):
        """Initializes plugin input widgets"""
        self.prepare_extent_box()
        self.grid_layout = QtWidgets.QGridLayout()
        self.message_bar = QgsMessageBar()
        self.prepare_message_bar()

        self.progress_dialog = None
        self.scenario_directory = None

        self.help_btn.clicked.connect(self.open_help)
        self.pilot_area_btn.clicked.connect(self.zoom_pilot_area)
        self.run_scenario_btn.clicked.connect(self.run_analysis)
        self.options_btn.clicked.connect(self.open_settings)

        self.restore_scenario()

        self.scenario_name.textChanged.connect(self.save_scenario)
        self.scenario_description.textChanged.connect(self.save_scenario)
        self.extent_box.extentChanged.connect(self.save_scenario)

        icon_pixmap = QtGui.QPixmap(ICON_PATH)
        self.icon_la.setPixmap(icon_pixmap)

        add_layer_icon = QtGui.QIcon(ADD_LAYER_ICON_PATH)
        self.layer_add_btn.setIcon(add_layer_icon)

        remove_layer_icon = QtGui.QIcon(REMOVE_LAYER_ICON_PATH)
        self.layer_remove_btn.setIcon(remove_layer_icon)

        self.layer_add_btn.clicked.connect(self.add_priority_layer_group)
        self.layer_remove_btn.clicked.connect(self.remove_priority_layer_group)

        reload_icon = FileUtils.get_icon("mActionReload.svg")
        self.btn_reload_pwl.setIcon(reload_icon)
        self.btn_reload_pwl.setToolTip(
            self.tr("Refresh and assign priority" " layers to implementation models")
        )
        update_pwl_layers = partial(self.update_pwl_layers, True)
        self.btn_reload_pwl.clicked.connect(update_pwl_layers)
        self.update_pwl_layers()

        # Scenario analysis variables

        self.analysis_scenario_name = None
        self.analysis_scenario_description = None
        self.analysis_extent = None
        self.analysis_implementation_models = None
        self.analysis_priority_layers_groups = None

    def update_pwl_layers(self, notify=False):
        """Updates the priority layers path available in the store implementation models"""
        settings_manager.update_implementation_models()
        if notify:
            self.show_message(
                tr(
                    "Updated all the implemenation models"
                    " with their respective priority layers"
                ),
                Qgis.Info,
            )
        log(
            tr(
                "Updated all the implemenation models"
                " with their respective priority layers"
            )
        )

    def save_scenario(self):
        """Save current scenario details into settings"""
        scenario_name = self.scenario_name.text()
        scenario_description = self.scenario_description.text()
        extent = self.extent_box.outputExtent()

        extent_box = [
            extent.xMinimum(),
            extent.xMaximum(),
            extent.yMinimum(),
            extent.yMaximum(),
        ]

        settings_manager.set_value(Settings.SCENARIO_NAME, scenario_name)
        settings_manager.set_value(Settings.SCENARIO_DESCRIPTION, scenario_description)
        settings_manager.set_value(Settings.SCENARIO_EXTENT, extent_box)

    def restore_scenario(self):
        """Update the first tab input with the last scenario details"""
        scenario_name = settings_manager.get_value(Settings.SCENARIO_NAME)
        scenario_description = settings_manager.get_value(Settings.SCENARIO_DESCRIPTION)
        extent = settings_manager.get_value(Settings.SCENARIO_EXTENT)

        self.scenario_name.setText(scenario_name) if scenario_name is not None else None
        self.scenario_description.setText(
            scenario_description
        ) if scenario_description is not None else None

        if extent is not None:
            extent_rectangle = QgsRectangle(
                float(extent[0]), float(extent[3]), float(extent[1]), float(extent[2])
            )
            self.extent_box.setOutputExtentFromUser(
                extent_rectangle,
                QgsCoordinateReferenceSystem("EPSG:4326"),
            )

    def initialize_priority_layers(self):
        """Prepares the priority weighted layers UI with the defaults.

        Gets the store priority layers from plugin settings and populates
        them into the QListWidget as QListWidgetItems then fetches the
        priority groups and adds them to the QTreeWidget as QTreeWidgetItems
        with their corresponding priority layers as their child items.
        """
        self.priority_layers_list.clear()

        for layer in settings_manager.get_priority_layers():
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.DisplayRole, layer.get("name"))
            item.setData(QtCore.Qt.UserRole, layer.get("uuid"))

            self.priority_layers_list.addItem(item)

        list_items = []
        items_only = []
        stored_priority_groups = settings_manager.get_priority_groups()
        self.priority_groups_list.clear()

        for group in stored_priority_groups:
            group_widget = PriorityGroupWidget(
                group,
            )
            group_widget.input_value_changed.connect(self.group_value_changed)
            group_widget.slider_value_changed.connect(self.group_value_changed)

            self.priority_groups_widgets[group["name"]] = group_widget

            pw_layers = settings_manager.find_layers_by_group(group["name"])

            item = QtWidgets.QTreeWidgetItem()
            item.setSizeHint(0, group_widget.sizeHint())
            item.setExpanded(True)

            # Add priority layers into the group as a child items.

            item.setExpanded(True) if len(pw_layers) > 0 else None

            for layer in pw_layers:
                if item.parent() is None:
                    layer_item = QtWidgets.QTreeWidgetItem(item)
                    layer_item.setText(0, layer.get("name"))

            list_items.append((item, group_widget))
            items_only.append(item)

        self.priority_groups_list.addTopLevelItems(items_only)
        for item in list_items:
            self.priority_groups_list.setItemWidget(item[0], 0, item[1])

    def group_value_changed(self, group_name, group_value):
        """Slot to handle priority group widget changes.

        :param group_name: Group name
        :type group_name: str

        :param group_value: Group value
        :type group_value: int
        """

        group = settings_manager.find_group_by_name(group_name)
        group["value"] = group_value
        settings_manager.save_priority_group(group)

        for index in range(self.priority_groups_list.topLevelItemCount()):
            item = self.priority_groups_list.topLevelItem(index)

            for child_index in range(item.childCount()):
                child = item.child(child_index)
                layer = settings_manager.find_layer_by_name(child.text(0))
                new_groups = []
                for group in layer.get("groups"):
                    if group.get("name") == group_name:
                        group["value"] = group_value
                    new_groups.append(group)
                layer["groups"] = new_groups
                settings_manager.save_priority_layer(layer)

    def update_priority_layers(self):
        """Updates the priority weighting layers list in the UI."""
        self.priority_layers_list.clear()
        for layer in settings_manager.get_priority_layers():
            item = QtWidgets.QListWidgetItem()
            item.setData(QtCore.Qt.DisplayRole, layer.get("name"))
            item.setData(QtCore.Qt.UserRole, layer.get("uuid"))

            self.priority_layers_list.addItem(item)
            for index in range(self.priority_groups_list.topLevelItemCount()):
                group = self.priority_groups_list.topLevelItem(index)
                if group.text(0) in layer.get("groups"):
                    self.add_priority_layer_group(group, item)
                else:
                    group_children = group.takeChildren()
                    children = []
                    for child in group_children:
                        if child.text(0) == layer.get("name"):
                            continue
                        children.append(child)
                    group.addChildren(children)

    def add_priority_layer_group(self, target_group=None, priority_layer=None):
        """Adds priority layer from the weighting layers into a priority group
           If no target_group or priority_layer is passed then the current selected
           group or priority layer from their respective list will be used.

           Checks if priority layer is already in the target group and if so no
           addition is done.

           After addition is done the respective priority layer plugin settings
           are updated to store the new information.

        :param target_group: Priority group where layer will be added to
        :type target_group: dict

        :param priority_layer: Priority weighting layer to be added
        :type priority_layer: dict
        """
        selected_priority_layer = (
            priority_layer or self.priority_layers_list.currentItem()
        )
        selected_group = target_group or self.priority_groups_list.currentItem()

        if (
            selected_group is not None and selected_group.parent() is None
        ) and selected_priority_layer is not None:
            children = selected_group.takeChildren()
            item_found = False
            text = selected_priority_layer.data(QtCore.Qt.DisplayRole)
            for child in children:
                if child.text(0) == text:
                    item_found = True
                    break
            selected_group.addChildren(children)

            if not item_found:
                selected_group.setExpanded(True)
                item = QtWidgets.QTreeWidgetItem(selected_group)
                item.setText(0, text)
                group_widget = self.priority_groups_list.itemWidget(selected_group, 0)
                layer_id = selected_priority_layer.data(QtCore.Qt.UserRole)

                priority_layer = settings_manager.get_priority_layer(layer_id)
                target_group_name = (
                    group_widget.group.get("name") if group_widget.group else None
                )

                groups = priority_layer.get("groups")
                new_groups = []
                group_found = False

                for group in groups:
                    if target_group_name == group["name"]:
                        group_found = True
                        new_group = settings_manager.find_group_by_name(
                            target_group_name
                        )
                    else:
                        new_group = group
                    new_groups.append(new_group)
                if not group_found:
                    searched_group = settings_manager.find_group_by_name(
                        target_group_name
                    )
                    new_groups.append(searched_group)

                priority_layer["groups"] = new_groups
                settings_manager.save_priority_layer(priority_layer)

    def remove_priority_layer_group(self, target_group=None, priority_layer=None):
        """Remove priority layer from a priority group.
           If no target_group or priority_layer is passed then the current selected
           group or priority layer from their respective list will be used.

           Checks if priority layer is already in the target group and if no,
           the removal is not performed.

        :param target_group: Priority group where layer will be removed from
        :type target_group: dict

        :param priority_layer: Priority weighting layer to be removed
        :type priority_layer: dict
        """
        selected_group = self.priority_groups_list.currentItem()
        parent_item = selected_group.parent() if selected_group is not None else None

        if parent_item:
            priority_layer = settings_manager.find_layer_by_name(selected_group.text(0))
            group_widget = self.priority_groups_list.itemWidget(parent_item, 0)

            groups = priority_layer.get("groups")
            new_groups = []
            for group in groups:
                if group.get("name") == group_widget.group.get("name"):
                    continue
                new_groups.append(group)
            priority_layer["groups"] = new_groups
            settings_manager.save_priority_layer(priority_layer)

            parent_item.removeChild(selected_group)

    def open_help(self):
        """Opens the user documentation for the plugin in a browser"""
        open_documentation(USER_DOCUMENTATION_SITE)

    def prepare_message_bar(self):
        """Initializes the widget message bar settings"""
        self.message_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed
        )
        self.grid_layout.addWidget(
            self.message_bar, 0, 0, 1, 1, alignment=QtCore.Qt.AlignTop
        )
        self.dock_widget_contents.layout().insertLayout(0, self.grid_layout)

    def run_analysis(self):
        """Runs the plugin analysis"""

        extent_list = PILOT_AREA_EXTENT["coordinates"]
        default_extent = QgsRectangle(
            extent_list[3], extent_list[0], extent_list[1], extent_list[2]
        )
        passed_extent = self.extent_box.outputExtent()
        contains = default_extent == passed_extent or default_extent.contains(
            passed_extent
        )
        self.analysis_scenario_name = self.scenario_name.text()
        self.analysis_scenario_description = self.scenario_description.text()

        self.position_feedback = QgsProcessingFeedback()
        self.processing_context = QgsProcessingContext()

        self.analysis_priority_layers_groups = [
            layer.get("groups")
            for layer in settings_manager.get_priority_layers()
            if layer.get("groups") is not [] or layer.get("groups") is not None
        ]

        self.analysis_implementation_models = [
            item.implementation_model
            for item in self.implementation_model_widget.selected_im_items()
        ]

        base_dir = settings_manager.get_value(Settings.BASE_DIR)

        if self.analysis_scenario_name == "" or self.analysis_scenario_name is None:
            self.show_message(
                tr(f"Scenario name cannot be blank."),
                level=Qgis.Critical,
            )
            return
        if (
            self.analysis_scenario_description == ""
            or self.analysis_scenario_description is None
        ):
            self.show_message(
                tr(f"Scenario description cannot be blank."),
                level=Qgis.Critical,
            )
            return
        if (
            self.analysis_implementation_models == []
            or self.analysis_implementation_models is None
        ):
            self.show_message(
                tr("Select at least one implementation models from step two."),
                level=Qgis.Critical,
            )
            return
        if not any(self.analysis_priority_layers_groups):
            self.show_message(
                tr(
                    f"At least one priority weight layer should be added "
                    f"into one of the priority groups from step three."
                ),
                level=Qgis.Critical,
            )
            return

        if not contains:
            self.show_message(
                tr(f"Selected area of interest is outside the pilot area."),
                level=Qgis.Info,
            )
            return

        if base_dir is None:
            self.show_message(
                tr(
                    f"Plugin base data directory is not set! "
                    f"Go to plugin settings in order to set it."
                ),
                level=Qgis.Critial,
            )
            return
        self.analysis_extent = SpatialExtent(
            bbox=[extent_list[3], extent_list[2], extent_list[1], extent_list[0]]
        )

        try:
            self.scenario_directory = (
                f"{base_dir}/"
                f'scenario_{datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}'
            )

            FileUtils.create_new_dir(self.scenario_directory)

            # Creates and opens the progress dialog for the analysis
            self.progress_dialog = ProgressDialog(
                "Raster calculation",
                "implementation models",
                0,
                100,
                main_widget=self,
            )
            self.progress_dialog.run_dialog()
            self.progress_dialog.scenario_name = ""
            self.progress_dialog.change_status_message(
                tr("Raster calculation"), tr("models")
            )

        except Exception as err:
            self.show_message(
                tr(
                    "An error occurred when opening the progress dialog, "
                    "check logs for more information"
                ),
                level=Qgis.Info,
            )
            log(
                tr(
                    "An error occurred when opening the progress dialog for "
                    'scenario analysis, error message "{}"'.format(err)
                )
            )

        self.run_pathways_analysis(
            self.analysis_implementation_models,
            self.analysis_priority_layers_groups,
            self.analysis_extent,
        )

    def run_scenario_analysis(self):
        """Performs the scenario analysis. This covers the pilot study area,
        and checks whether the AOI is outside the pilot study area.
        """

        extent_list = PILOT_AREA_EXTENT["coordinates"]
        default_extent = QgsRectangle(
            extent_list[3], extent_list[0], extent_list[1], extent_list[2]
        )
        passed_extent = self.extent_box.outputExtent()
        contains = default_extent == passed_extent or default_extent.contains(
            passed_extent
        )

        scenario = Scenario(
            uuid=uuid.uuid4(),
            name=self.analysis_scenario_name,
            description=self.analysis_scenario_description,
            extent=self.analysis_extent,
            models=self.analysis_implementation_models,
            priority_layer_groups=self.analysis_priority_layers_groups,
        )

        self.scenario_result = ScenarioResult(
            scenario=scenario,
        )

        if contains:
            try:
                layers = {}

                self.progress_dialog.progress_bar.setMinimum(0)
                self.progress_dialog.progress_bar.setMaximum(100)
                self.progress_dialog.progress_bar.setValue(0)
                self.progress_dialog.analysis_finished_message = tr("Analysis finished")
                self.progress_dialog.scenario_name = tr(f"<b>{scenario.name}</b>")
                self.progress_dialog.scenario_id = str(scenario.uuid)
                self.progress_dialog.change_status_message(
                    tr("Calculating the highest position")
                )

                self.position_feedback.progressChanged.connect(self.update_progress_bar)

                for model in self.analysis_implementation_models:
                    if model.layer:
                        raster_layer = model.layer
                        if isinstance(model.layer, str):
                            raster_layer = QgsRasterLayer(model.layer, model.name)
                        layers[model.name] = (
                            raster_layer if raster_layer is not None else None
                        )
                    else:
                        for pathway in model.pathways:
                            layers[model.name] = QgsRasterLayer(pathway.path)

                source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                dest_crs = (
                    list(layers.values())[0].crs() if len(layers) > 0 else source_crs
                )
                transform = QgsCoordinateTransform(
                    source_crs, dest_crs, QgsProject.instance()
                )
                transformed_extent = transform.transformBoundingBox(passed_extent)

                extent_string = (
                    f"{transformed_extent.xMinimum()},{transformed_extent.xMaximum()},"
                    f"{transformed_extent.yMinimum()},{transformed_extent.yMaximum()}"
                    f" [{dest_crs.authid()}]"
                )

                output_file = (
                    f"{self.scenario_directory}/"
                    f"{SCENARIO_OUTPUT_FILE_NAME}_{str(scenario.uuid)[:4]}.tif"
                )

                # Preparing the input rasters for the highest position
                # analysis in a correct order

                models_names = [
                    model.name for model in self.analysis_implementation_models
                ]
                all_models_names = [
                    model.name
                    for model in self.implementation_model_widget.implementation_models()
                ]
                sources = []

                absolute_path = (
                    f"{FileUtils.plugin_dir()}/app_data/layers/null_raster.tif"
                )
                null_raster_file = os.path.normpath(absolute_path)

                for model_name in all_models_names:
                    if model_name in models_names:
                        sources.append(layers[model_name].source())
                    else:
                        sources.append(null_raster_file)

                log(f"Layers sources {[Path(source).stem for source in sources]}")

                alg_params = {
                    "IGNORE_NODATA": True,
                    "INPUT_RASTERS": sources,
                    "EXTENT": extent_string,
                    "OUTPUT_NODATA_VALUE": -9999,
                    "REFERENCE_LAYER": list(layers.values())[0]
                    if len(layers) >= 1
                    else None,
                    "OUTPUT": output_file,
                }

                log(f"Used parameters for highest position analysis: {alg_params}")

                alg = QgsApplication.processingRegistry().algorithmById(
                    "native:highestpositioninrasterstack"
                )

                self.processing_cancelled = False
                self.task = QgsProcessingAlgRunnerTask(
                    alg,
                    alg_params,
                    self.processing_context,
                    feedback=self.position_feedback,
                )
                self.task.executed.connect(self.scenario_results)
                QgsApplication.taskManager().addTask(self.task)

            except Exception as err:
                self.show_message(
                    tr(
                        "An error occurred when running analysis task, "
                        "check logs for more information"
                    ),
                    level=Qgis.Info,
                )
                log(
                    tr(
                        "An error occurred when running task for "
                        'scenario analysis, error message "{}"'.format(str(err))
                    )
                )

        else:
            self.show_message(
                tr("Selected area of interest is outside the pilot area."),
                level=Qgis.Critical,
            )

            default_ext = (
                f"{default_extent.xMinimum()}, {default_extent.xMaximum()},"
                f"{default_extent.yMinimum()}, {default_extent.yMaximum()}"
            )
            log(
                f"Outside the pilot area, passed extent "
                f"{self.analysis_extent}, default extent{default_ext}"
            )
            return

    def transfrom_extent(self, extent, source_crs, dest_crs):
        """Transforms the passed extent into the destionation crs

         :param extent: Target extent
        :type extent: SpatialExtent

        :param source_crs: Source CRS of the passed extent
        :type source_crs: QgsCoordinateReferenceSystem

        :param dest_crs: Destination CRS
        :type dest_crs: QgsCoordinateReferenceSystem
        """

        box = QgsRectangle(
            float(extent.bbox[0]),
            float(extent.bbox[1]),
            float(extent.bbox[2]),
            float(extent.bbox[3]),
        )
        transform = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())
        transformed_extent = transform.transformBoundingBox(box)

        return tranformed_extent

    def main_task(self):
        """Serves as a QgsTask function for the main task that contains
        smaller sub-tasks running the actual processing calculations.
        """

        log("Running from main task.")

    def run_pathways_analysis(self, models, priority_layers_groups, extent):
        """Runs the required model pathways analysis on the passed implementation models

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param priority_layers_groups: Used priority layers groups and their values
        :type priority_layers_groups: dict

        :param extent: selected extent from user
        :type extent: SpatialExtent
        """
        model_count = 0

        models_function = partial(
            self.run_models_analysis, models, priority_layers_groups, extent
        )
        main_task = QgsTask.fromFunction(
            "Main task for running pathways combination with carbon layers",
            self.main_task,
            on_finished=models_function,
        )

        main_task.taskCompleted.connect(models_function)

        previous_sub_tasks = []

        self.progress_dialog.analysis_finished_message = tr("Calculating carbon layers")
        self.progress_dialog.scenario_name = tr(f"models pathways")

        for model in models:
            if not model.pathways:
                if model.layer is not None:
                    source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                    transformed_extent = self.transform_extent(
                        extent, source_crs, layer.crs()
                    )

                    extent_string = (
                        f"{transformed_extent.xMinimum()},{transformed_extent.xMaximum()},"
                        f"{transformed_extent.yMinimum()},{transformed_extent.yMaximum()}"
                        f" [{layer.crs().authid()}]"
                    )
                    self.run_models_analysis(
                        models, priority_layers_groups, extent_string
                    )
                else:
                    return False

            new_ims_directory = f"{self.scenario_directory}/pathways_carbon_layers"
            carbon_coefficient = float(
                settings_manager.get_value(Settings.CARBON_COEFFICIENT, default=0.0)
            )
            base_dir = settings_manager.get_value(Settings.BASE_DIR)

            FileUtils.create_new_dir(new_ims_directory)
            file_name = clean_filename(model.name.replace(" ", "_"))

            output_file = f"{new_ims_directory}/{file_name}_{str(uuid.uuid4())[:4]}.tif"
            pathway_count = 0

            for pathway in model.pathways:
                basenames = []
                layers = []
                path_basename = Path(pathway.path).stem
                layers.append(pathway.path)
                basenames.append(f'"{path_basename}@1"')
                for carbon_path in pathway.carbon_paths:
                    if base_dir not in carbon_path:
                        carbon_path = f"{base_dir}/{NCS_CARBON_SEGMENT}/{carbon_path}"
                    carbon_full_path = Path(carbon_path)
                    if not carbon_full_path.exists():
                        continue
                    layers.append(carbon_path)
                    if carbon_coefficient > 0:
                        basenames.append(
                            f'({carbon_coefficient} * "{carbon_full_path.stem}@1")'
                        )
                expression = " + ".join(basenames)

                source_crs = QgsCoordinateReferenceSystem("EPSG:4326")
                dest_crs = QgsRasterLayer(layers[0]).crs()

                transformed_extent = self.transform_extent(extent, source_crs, dest_crs)

                extent_string = (
                    f"{transformed_extent.xMinimum()},{transformed_extent.xMaximum()},"
                    f"{transformed_extent.yMinimum()},{transformed_extent.yMaximum()}"
                    f" [{dest_crs.authid()}]"
                )
                analysis_done = partial(
                    self.pathways_analysis_done,
                    model_count,
                    models,
                    extent_string,
                    priority_layers_groups,
                    pathway,
                    (pathway_count == len(model.pathways) - 1),
                )

                if carbon_coefficient <= 0:
                    self.run_models_analysis(
                        models, priority_layers_groups, extent_string
                    )
                    return

                # Actual processing calculation
                alg_params = {
                    "CELLSIZE": 0,
                    "CRS": None,
                    "EXPRESSION": expression,
                    "EXTENT": extent_string,
                    "LAYERS": layers,
                    "OUTPUT": output_file,
                }

                log(
                    f"Used parameters for combining pathways"
                    f" and carbon layers generation: {alg_params}"
                )

                alg = QgsApplication.processingRegistry().algorithmById(
                    "qgis:rastercalculator"
                )

                self.processing_cancelled = False

                self.task = QgsProcessingAlgRunnerTask(
                    alg, alg_params, self.processing_context, self.position_feedback
                )
                self.position_feedback.progressChanged.connect(self.update_progress_bar)

                main_task.addSubTask(
                    self.task, previous_sub_tasks, QgsTask.ParentDependsOnSubTask
                )
                previous_sub_tasks.append(self.task)
                self.task.executed.connect(analysis_done)

                pathway_count = pathway_count + 1

            model_count = model_count + 1
        QgsApplication.taskManager().addTask(main_task)

    def pathways_analysis_done(
        self,
        model_index,
        models,
        extent,
        priority_layers_groups,
        pathway,
        last_pathway,
        success,
        output,
    ):
        """Slot that handles post calculations for the models pathways and
         carbon layers

        :param model_index: List index of the target model
        :type model_index: int

        :param pathway: Target pathway
        :type pathway: NCSPathway

        :param models: List of the selected implementation models
        :type models: typing.List[ImplementationModel]

        :param priority_layers_groups: Used priority layers groups and their values
        :type priority_layers_groups: dict

        :param last_pathway: Whether the pathway is the last from the models pathway list
        :type last_pathway: bool

        :param success: Whether the scenario analysis was successful
        :type success: bool

        :param output: Analysis output results
        :type output: dict
        """
        if output is not None and output.get("OUTPUT") is not None:
            pathway.path = output.get("OUTPUT")

        if (model_index == len(models) - 1) and last_pathway:
            self.run_models_analysis(models, priority_layers_groups, extent)

    def run_models_analysis(self, models, priority_layers_groups, extent):
        """Runs the required model analysis on the passed implementation models

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param priority_layers_groups: Used priority layers groups and their values
        :type priority_layers_groups: dict

        :param extent: selected extent from user
        :type extent: SpatialExtent
        """
        model_count = 0

        priority_function = partial(
            self.run_priority_analysis, models, priority_layers_groups, extent
        )
        main_task = QgsTask.fromFunction(
            "Running main functions", self.main_task, on_finished=priority_function
        )

        previous_sub_tasks = []

        self.progress_dialog.analysis_finished_message = tr("Processing calculations")
        self.progress_dialog.scenario_name = tr("implementation models")

        for model in models:
            new_ims_directory = f"{self.scenario_directory}/implementation_models"
            FileUtils.create_new_dir(new_ims_directory)
            file_name = clean_filename(model.name.replace(" ", "_"))

            basenames = []
            layers = []
            if not model.pathways:
                if model.layer is not None:
                    shutil.copy(str(model.layer.source()), new_ims_directory)
                    if model_count == len(models) - 1:
                        self.run_normalization_analysis(
                            models, priority_layers_groups, extent
                        )
            else:
                continue
            output_file = f"{new_ims_directory}/{file_name}_{str(uuid.uuid4())[:4]}.tif"

            for pathway in model.pathways:
                path_basename = Path(pathway.path).stem
                layers.append(pathway.path)
                basenames.append(f'"{path_basename}@1"')

            expression = " + ".join(basenames)

            analysis_done = partial(
                self.model_analysis_done,
                model_count,
                model,
                models,
                extent,
                priority_layers_groups,
            )

            # Actual processing calculation
            alg_params = {
                "CELLSIZE": 0,
                "CRS": None,
                "EXPRESSION": expression,
                "EXTENT": extent,
                "LAYERS": layers,
                "OUTPUT": output_file,
            }

            log(f"Used parameters for implementation models generation: {alg_params}")

            alg = QgsApplication.processingRegistry().algorithmById(
                "qgis:rastercalculator"
            )

            self.processing_cancelled = False

            self.task = QgsProcessingAlgRunnerTask(
                alg, alg_params, self.processing_context, self.position_feedback
            )

            self.position_feedback.progressChanged.connect(self.update_progress_bar)

            main_task.addSubTask(
                self.task, previous_sub_tasks, QgsTask.ParentDependsOnSubTask
            )
            previous_sub_tasks.append(self.task)
            self.task.executed.connect(analysis_done)

            model_count = model_count + 1

        QgsApplication.taskManager().addTask(main_task)

    def model_analysis_done(
        self,
        model_index,
        model,
        models,
        extent,
        priority_layers_groups,
        success,
        output,
    ):
        """Slot that handles post calculations for the models layers

        :param model_index: List index of the target model
        :type model_index: int

        :param model: Target implementation models
        :type model: ImplementationModel

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param priority_layers_groups: Used priority layers groups and their values
        :type priority_layers_groups: dict

        :param success: Whether the scenario analysis was successful
        :type success: bool

        :param output: Analysis output results
        :type output: dict
        """
        if output is not None and output.get("OUTPUT") is not None:
            model.layer = QgsRasterLayer(output.get("OUTPUT"), model.name)

        if model_index == len(models) - 1:
            self.run_normalization_analysis(models, priority_layers_groups, extent)

    def run_normalization_analysis(self, models, priority_layers_groups, extent):
        """Runs the normalization on the analysis models layers,
        adjusting band statistical values measured on different scale
        to a 0-1 scale or 0-2 scale.

        If carbon layers were used prior to the models analysis the 0-2 scale will
        be used instead of the default 0-1 scale.

        :param model: List of the analyzed implementation models
        :type model: typing.List[ImplementationModel]

        :param priority_layers_groups: Used priority layers groups and their values
        :type priority_layers_groups: dict

        :param extent: selected extent from user
        :type extent: str
        """
        model_count = 0

        priority_function = partial(
            self.run_priority_analysis, models, priority_layers_groups, extent
        )
        main_task = QgsTask.fromFunction(
            "Running normalization", self.main_task, on_finished=priority_function
        )

        previous_sub_tasks = []

        self.progress_dialog.analysis_finished_message = tr("Normalization")
        self.progress_dialog.scenario_name = tr("implementation models")

        for model in models:
            if not model.layer:
                log(f"There is no raster layer for the model {model.name}")
                continue

            basenames = []
            layers = []
            new_ims_directory = f"{self.scenario_directory}/normalized_ims"
            FileUtils.create_new_dir(new_ims_directory)
            file_name = clean_filename(model.name.replace(" ", "_"))

            output_file = f"{new_ims_directory}/{file_name}_{str(uuid.uuid4())[:4]}.tif"

            provider = model.layer.dataProvider()
            band_statistics = provider.bandStatistics(1)

            min_value = band_statistics.minimumValue
            max_value = band_statistics.maximumValue

            layer_source = model.layer.source()
            layer_name = Path(layer_source).stem

            layers.append(layer_source)

            carbon_coefficient = float(
                settings_manager.get_value(Settings.CARBON_COEFFICIENT, default=0.0)
            )

            if carbon_coefficient <= 0:
                expression = (
                    f'("{layer_name}@1" - {min_value}) /'
                    f" ({max_value} - {min_value})"
                )
            else:
                expression = (
                    f' 2 * ("{layer_name}@1" - {min_value}) /'
                    f" ({max_value} - {min_value})"
                )

            analysis_done = partial(
                self.normalization_analysis_done,
                model_count,
                model,
                models,
                extent,
                priority_layers_groups,
            )

            # Actual processing calculation
            alg_params = {
                "CELLSIZE": 0,
                "CRS": None,
                "EXPRESSION": expression,
                "EXTENT": extent,
                "LAYERS": layers,
                "OUTPUT": output_file,
            }

            log(f"Used parameters for normalization of the models: {alg_params}")

            alg = QgsApplication.processingRegistry().algorithmById(
                "qgis:rastercalculator"
            )

            self.processing_cancelled = False

            self.task = QgsProcessingAlgRunnerTask(
                alg, alg_params, self.processing_context, self.position_feedback
            )

            self.position_feedback.progressChanged.connect(self.update_progress_bar)

            main_task.addSubTask(
                self.task, previous_sub_tasks, QgsTask.ParentDependsOnSubTask
            )
            previous_sub_tasks.append(self.task)
            self.task.executed.connect(analysis_done)

            model_count = model_count + 1

        QgsApplication.taskManager().addTask(main_task)

    def normalization_analysis_done(
        self,
        model_index,
        model,
        models,
        extent,
        priority_layers_groups,
        success,
        output,
    ):
        """Slot that handles post calculations for the models layers

        :param model_index: List index of the target model
        :type model_index: int

        :param model: Target implementation models
        :type model: ImplementationModel

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param success: Whether the scenario analysis was successful
        :type success: bool

        :param output: Analysis output results
        :type output: dict
        """
        if output is not None and output.get("OUTPUT") is not None:
            model.layer = QgsRasterLayer(output.get("OUTPUT"), model.name)

        if model_index == len(models) - 1:
            self.run_priority_analysis(models, priority_layers_groups, extent)

    def run_priority_analysis(self, models, priority_layers_groups, extent):
        """Runs the required model analysis on the passed implementation models

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param extent: selected extent from user
        :type extent: SpatialExtent
        """
        model_count = 0

        main_task = QgsTask.fromFunction(
            "Running main task for priority layers weighting",
            self.main_task,
            on_finished=self.run_scenario_analysis,
        )

        main_task.taskCompleted.connect(self.run_scenario_analysis)

        previous_sub_tasks = []

        self.progress_dialog.analysis_finished_message = tr(f"Weighting")

        self.progress_dialog.scenario_name = tr(f"implementation models")

        for model in models:
            if model.layer is None:
                return False

            basenames = []
            layers = []
            analysis_done = partial(
                self.priority_layers_analysis_done, model_count, model, models
            )
            layers.append(model.layer.source())
            basenames.append(f'"{Path(model.layer.source()).stem}@1"')

            if model.pwls_paths is None or model.pwls_paths is []:
                continue

            settings_model = settings_manager.get_implementation_model(str(model.uuid))
            base_dir = settings_manager.get_value(Settings.BASE_DIR)

            for pwl in settings_model.pwls_paths:
                if base_dir not in pwl:
                    pwl = f"{base_dir}/{PRIORITY_LAYERS_SEGMENT}/{pwl}"
                pwl_path = Path(pwl)
                if not pwl_path.exists():
                    continue

                path_basename = pwl_path.stem
                layers.append(pwl)
                for layer in settings_manager.get_priority_layers():
                    if layer.get("name") == path_basename:
                        for group in layer.get("groups"):
                            value = group.get("value")
                            coefficient = float(value) / 100
                            if coefficient > 0:
                                basenames.append(f'({coefficient}*"{path_basename}@1")')

            if basenames is []:
                return

            new_ims_directory = f"{self.scenario_directory}/weighted_ims"

            FileUtils.create_new_dir(new_ims_directory)

            file_name = clean_filename(model.name.replace(" ", "_"))
            output_file = f"{new_ims_directory}/{file_name}_{str(uuid.uuid4())[:4]}.tif"
            expression = " + ".join(basenames)

            # Actual processing calculation
            alg_params = {
                "CELLSIZE": 0,
                "CRS": None,
                "EXPRESSION": expression,
                "EXTENT": extent,
                "LAYERS": layers,
                "OUTPUT": output_file,
            }

            log(f" Used parameters for calculating weighting models {alg_params}")

            alg = QgsApplication.processingRegistry().algorithmById(
                "qgis:rastercalculator"
            )

            self.processing_cancelled = False

            self.task = QgsProcessingAlgRunnerTask(
                alg, alg_params, self.processing_context, self.position_feedback
            )

            self.position_feedback.progressChanged.connect(self.update_progress_bar)

            main_task.addSubTask(
                self.task, previous_sub_tasks, QgsTask.ParentDependsOnSubTask
            )
            previous_sub_tasks.append(self.task)

            self.task.executed.connect(analysis_done)

            model_count = model_count + 1

        QgsApplication.taskManager().addTask(main_task)

    def priority_layers_analysis_done(
        self, model_index, model, models, success, output
    ):
        """Slot that handles post calculations for the models priority layers

        :param model_index: List index of the target model
        :type model_index: int

        :param model: Target implementation models
        :type model: ImplementationModel

        :param model: List of the selected implementation models
        :type model: typing.List[ImplementationModel]

        :param success: Whether the scenario analysis was successful
        :type success: bool

        :param output: Analysis output results
        :type output: dict
        """
        if output is not None and output.get("OUTPUT") is not None:
            model.layer = QgsRasterLayer(output.get("OUTPUT"), model.name)

        if model_index == len(models) - 1:
            self.run_scenario_analysis()

    def cancel_processing_task(self):
        """Cancels the current processing task."""
        self.processing_cancelled = True

        try:
            if self.task:
                self.task.cancel()
        except Exception as e:
            log(f"Problem cancelling task, {e}")

    def scenario_results(self, success, output):
        """Called when the task ends. Sets the progress bar to 100 if it finished.

        :param success: Whether the scenario analysis was successful
        :type success: bool

        :param output: Analysis output results
        :type output: dict
        """
        if output is not None:
            self.update_progress_bar(100)
            self.scenario_result.analysis_output = output
            self.scenario_result.state = ScenarioState.FINISHED
            self.analysis_finished.emit(self.scenario_result)

        else:
            self.progress_dialog.change_status_message(
                "No valid output from the processing results."
            )
            log(f"No valid output from the processing results.")

    def move_layer_to_group(self, layer, group) -> None:
        """Moves a layer open in QGIS to another group.

        :param layer: Raster layer to move
        :type layer: QgsRasterLayer

        :param group: Group to which the raster should be moved
        :type group: QgsLayerTreeGroup
        """
        if layer:
            instance_root = QgsProject.instance().layerTreeRoot()
            layer = instance_root.findLayer(layer.id())
            layer_clone = layer.clone()
            parent = layer.parent()
            group.insertChildNode(0, layer_clone)  # Add to top of group
            parent.removeChildNode(layer)

    def post_analysis(self, scenario_result):
        """Handles analysis outputs from the final analysis results.
        Adds the resulting scenario raster to the canvas with styling.
        Adds each of the implementation models to the canvas with styling.
        Adds each IMs pathways to the canvas.

        :param scenario_result: ScenarioResult of output results
        :type scenario_result: ScenarioResult
        """

        # If the processing were stopped, no file will be added
        if not self.processing_cancelled:
            raster = scenario_result.analysis_output["OUTPUT"]
            im_weighted_dir = os.path.dirname(raster) + "/weighted_ims/"
            list_weighted_ims = os.listdir(im_weighted_dir)

            scenario_name = scenario_result.scenario.name
            qgis_instance = QgsProject.instance()
            instance_root = qgis_instance.layerTreeRoot()

            # Groups
            scenario_group = instance_root.insertGroup(0, scenario_name)
            im_group = scenario_group.addGroup(tr(IM_GROUP_LAYER_NAME))
            im_weighted_group = scenario_group.addGroup(tr(IM_WEIGHTED_GROUP_NAME))
            pathways_group = scenario_group.addGroup(tr(NCS_PATHWAYS_GROUP_LAYER_NAME))

            # Group settings
            im_group.setExpanded(False)
            im_weighted_group.setExpanded(False)
            pathways_group.setExpanded(False)
            pathways_group.setItemVisibilityCheckedRecursive(False)

            # Add scenario result layer to the canvas with styling
            layer_file = scenario_result.analysis_output.get("OUTPUT")
            layer_name = (
                f"{SCENARIO_OUTPUT_LAYER_NAME}_"
                f'{datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")}'
            )
            layer = QgsRasterLayer(layer_file, layer_name, QGIS_GDAL_PROVIDER)
            layer.loadNamedStyle(LAYER_STYLES["scenario_result"])
            scenario_layer = qgis_instance.addMapLayer(layer)

            """A workaround to add a layer to a group.
            Adding it using group.insertChildNode or group.addLayer causes issues,
             but adding to the root is fine.
            This approach adds it to the root, and then moves it to the group.
            """
            self.move_layer_to_group(scenario_layer, scenario_group)

            coefficient = settings_manager.get_value(
                Settings.CARBON_COEFFICIENT, default=0.0
            )

            # Add implementation models and pathways
            list_models = scenario_result.scenario.models
            im_index = 0
            for im in list_models:
                im_name = im.name
                im_layer = im.layer
                list_pathways = im.pathways

                # Add IM layer with styling, if available
                if im_layer:
                    if float(coefficient) > 0:
                        # Style with range 0 to 2
                        style_to_use = LAYER_STYLES["carbon"][im_name]
                    else:
                        # Style with range 0 to 1
                        style_to_use = LAYER_STYLES["normal"][im_name]

                    im_layer.loadNamedStyle(style_to_use)
                    added_im_layer = qgis_instance.addMapLayer(im_layer)
                    self.move_layer_to_group(added_im_layer, im_group)

                # Add IM pathways
                if len(list_pathways) > 0:
                    # im_pathway_group = pathways_group.addGroup(im_name)
                    im_pathway_group = pathways_group.insertGroup(im_index, im_name)
                    im_pathway_group.setExpanded(False)

                    pw_index = 0
                    for pathway in list_pathways:
                        try:
                            # pathway_name = pathway.name
                            pathway_layer = pathway.layer

                            added_pw_layer = qgis_instance.addMapLayer(pathway_layer)
                            self.move_layer_to_group(added_pw_layer, im_pathway_group)

                            pw_index = pw_index + 1
                        except Exception as err:
                            self.show_message(
                                tr(
                                    "An error occurred loading a pathway, "
                                    "check logs for more information"
                                ),
                                level=Qgis.Info,
                            )
                            log(
                                tr(
                                    "An error occurred loading a pathway, "
                                    'scenario analysis, error message "{}"'.format(err)
                                )
                            )

                im_index = im_index + 1

            for weighted_im in list_weighted_ims:
                if not weighted_im.endswith(".tif"):
                    continue

                weighted_im_name = weighted_im[: len(weighted_im) - 9]
                if float(coefficient) > 0:
                    # Style with range 0 to 2
                    style_to_use = LAYER_STYLES_WEIGHTED["carbon"][weighted_im_name]
                else:
                    # Style with range 0 to 1
                    style_to_use = LAYER_STYLES_WEIGHTED["normal"][weighted_im_name]

                im_weighted_layer = QgsRasterLayer(
                    im_weighted_dir + weighted_im, weighted_im_name, QGIS_GDAL_PROVIDER
                )
                im_weighted_layer.loadNamedStyle(style_to_use)
                added_im_weighted_layer = qgis_instance.addMapLayer(im_weighted_layer)
                self.move_layer_to_group(added_im_weighted_layer, im_weighted_group)

            # Initiate report generation
            self.run_report()

        else:
            # Reinitializes variables if processing were cancelled by the user
            # Not doing this breaks the processing if a user tries to run
            # the processing after cancelling or if the processing fails
            self.position_feedback = QgsProcessingFeedback()
            self.processing_context = QgsProcessingContext()

    def update_progress_bar(self, value):
        """Sets the value of the progress bar

        :param value: Value to be set on the progress bar
        :type value: float
        """
        if self.progress_dialog and not self.processing_cancelled:
            try:
                self.progress_dialog.update_progress_bar(int(value))
            except RuntimeError:
                log(tr("Error setting value to a progress bar"), notify=False)

    def update_message_bar(self, message):
        """Changes the message in the message bar item.

        :param message: Message to be updated
        :type message: str
        """
        message_bar_item = self.message_bar.createMessage(message)
        self.message_bar.pushWidget(message_bar_item, Qgis.Info)

    def show_message(self, message, level=Qgis.Warning):
        """Shows message on the main widget message bar.

        :param message: Text message
        :type message: str

        :param level: Message level type
        :type level: Qgis.MessageLevel
        """
        self.message_bar.clearWidgets()
        self.message_bar.pushMessage(message, level=level)

    def zoom_pilot_area(self):
        """Zoom the current main map canvas to the pilot area extent."""
        map_canvas = iface.mapCanvas()
        extent_list = PILOT_AREA_EXTENT["coordinates"]
        default_extent = QgsRectangle(
            extent_list[3], extent_list[2], extent_list[1], extent_list[0]
        )
        zoom_extent = QgsRectangle(
            extent_list[3] - 0.5, extent_list[2], extent_list[1] + 0.5, extent_list[0]
        )

        aoi = QgsRubberBand(iface.mapCanvas(), QgsWkbTypes.PolygonGeometry)

        aoi.setFillColor(QtGui.QColor(0, 0, 0, 0))
        aoi.setStrokeColor(QtGui.QColor(88, 128, 8))
        aoi.setWidth(3)
        aoi.setLineStyle(QtCore.Qt.DashLine)

        geom = QgsGeometry.fromRect(default_extent)
        aoi.setToGeometry(geom, QgsCoordinateReferenceSystem("EPSG:4326"))

        map_canvas.setExtent(zoom_extent)

    def prepare_extent_box(self):
        """Configure the spatial extent box with the initial settings."""

        self.extent_box.setOutputCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        map_canvas = iface.mapCanvas()
        self.extent_box.setCurrentExtent(
            map_canvas.mapSettings().destinationCrs().bounds(),
            map_canvas.mapSettings().destinationCrs(),
        )
        self.extent_box.setOutputExtentFromCurrent()
        self.extent_box.setMapCanvas(map_canvas)

        extent_list = PILOT_AREA_EXTENT["coordinates"]
        default_extent = QgsRectangle(
            extent_list[3], extent_list[2], extent_list[1], extent_list[0]
        )

        self.extent_box.setOutputExtentFromUser(
            default_extent,
            QgsCoordinateReferenceSystem("EPSG:4326"),
        )

    def on_tab_step_changed(self, index: int):
        """Slot raised when the current tab changes.

        :param index: Zero-based index position of new current tab
        :type index: int
        """
        if index == 1:
            self.implementation_model_widget.load()
        elif index == 2:
            # Validate NCS pathway - implementation model mapping
            valid = self.implementation_model_widget.is_valid()
            if not valid:
                msg = self.tr(
                    "Define one or more NCS pathways for at least one implementation model."
                )
                self.show_message(msg)
                self.tab_widget.setCurrentIndex(1)

            else:
                self.message_bar.clearWidgets()

    def open_settings(self):
        """Options the CPLUS settings in the QGIS options dialog."""
        self.iface.showOptionsDialog(currentPage=OPTIONS_TITLE)

    def run_report(self):
        """Run report generation. This should be called after the
        analysis is complete.
        """
        if self.scenario_result is None:
            log(
                "Cannot run report generation, scenario result is " "not defined",
                info=False,
            )
            return

        submit_result = self.rpm.generate(self.scenario_result)
        if not submit_result.status:
            msg = self.tr("Unable to submit report request for scenario")
            self.show_message(f"{msg} {self.scenario_result.scenario.name}.")

    def on_report_running(self, scenario_id: str):
        """Slot raised when report task has started."""
        if not self.report_job_is_for_current_scenario(scenario_id):
            return

        self.progress_dialog.change_status_message(
            tr("Generating report"), tr("scenario")
        )

    def on_report_finished(self, scenario_id: str):
        """Slot raised when report task has finished."""
        if not self.report_job_is_for_current_scenario(scenario_id):
            return

        self.progress_dialog.set_report_complete()
        self.progress_dialog.change_status_message(
            tr("Report generation complete"), tr("scenario")
        )

    def report_job_is_for_current_scenario(self, scenario_id: str) -> bool:
        """Checks if the given scenario identifier is for the current
        scenario result.

        This is to ensure that signals raised by the report manager refer
        to the current scenario result object and not for old jobs.

        :param scenario_id: Scenario identifier usually from a signal
        raised by the report manager.
        :type scenario_id: str

        :returns: True if the scenario identifier matches the current
        scenario object in the results, else False.
        :rtype: bool
        """
        if self.scenario_result is None:
            return False

        current_scenario = self.scenario_result.scenario
        if current_scenario is None:
            return False

        if str(current_scenario.uuid) == scenario_id:
            return True

        return False
