# -*- coding: utf-8 -*-
"""
Contains item models for view widgets such as NCS pathway or IM views.
"""
import uuid
from abc import abstractmethod
import json
import typing
from uuid import UUID, uuid4

from qgis.core import QgsMapLayer, QgsRasterLayer, QgsVectorLayer

from qgis.PyQt import QtCore, QtGui

from cplus_core.models.base import (
    BaseModelComponent,
    BaseModelComponentType,
    Activity,
    LayerModelComponent,
    LayerType,
    NcsPathway,
)
from ..models.helpers import (
    clone_activity,
    clone_ncs_pathway,
    copy_layer_component_attributes,
    create_ncs_pathway,
    ncs_pathway_to_dict,
)

from ..utils import FileUtils


NCS_PATHWAY_TYPE = QtGui.QStandardItem.UserType + 2
ACTIVITY_TYPE = QtGui.QStandardItem.UserType + 3
LAYER_ITEM_TYPE = QtGui.QStandardItem.UserType + 4

NCS_MIME_TYPE = "application/x-qabstractitemmodeldatalist"


class ModelComponentItem(QtGui.QStandardItem):
    """Base standard item for a BaseModelComponent object."""

    def __init__(self, model_component: BaseModelComponent):
        super().__init__(model_component.name)
        self.setToolTip(model_component.name)

        self._model_component = model_component
        if self._model_component is not None:
            self.update(self._model_component)

    def update(self, model_component: BaseModelComponent):
        """Update the component-related properties of the item."""
        if model_component is None:
            return

        self._model_component = model_component
        self.setText(model_component.name)
        self.setToolTip(model_component.name)

    @property
    def model_component(self) -> BaseModelComponent:
        """Returns an instance of the underlying model component object.

        :returns: Instance of underlying model component object.
        :rtype: BaseModelComponent
        """
        return self._model_component

    @property
    def uuid(self) -> str:
        """Returns the UUID of the item.

        :returns: UUID string of the item.
        :rtype: str
        """
        if self._model_component is None:
            return ""

        return str(self._model_component.uuid)

    @property
    def description(self) -> str:
        """Returns the description of the item.

        :returns: Description of the item.
        :rtype: str
        """
        if self._model_component is None:
            return ""

        return str(self._model_component.description)

    @staticmethod
    @abstractmethod
    def create(model_component: BaseModelComponent) -> "ModelComponentItem":
        """Factory method for creating an instance of a model item.

        This is an abstract method that needs to be implemented by
        subclasses.

        :param model_component: Source model component for creating the
        corresponding item.
        :type model_component: BaseModelComponent

        :returns: Model component item for use in a standard item model.
        :rtype: ModelComponentItem
        """
        pass

    @abstractmethod
    def clone(self) -> "ModelComponentItemType":
        """Creates a deep copied version of the model item.

        :returns: Cloned version of the model item containing all
        the properties as the source.
        :rtype: ModelComponentItem
        """
        pass


ModelComponentItemType = typing.TypeVar(
    "ModelComponentItemType", bound=ModelComponentItem
)


class LayerComponentItem(ModelComponentItem):
    """Base class view item for layer-based component items."""

    def __init__(self, model_component: LayerModelComponent):
        if not isinstance(model_component, LayerModelComponent):
            raise TypeError("'model_component' not of type LayerModelComponent")
        super().__init__(model_component)

    def is_valid(self) -> bool:
        """Checks whether the map layer of the underlying model
        component object is valid.

        :returns: True if the map layer is valid, else False
        if map layer is invalid or of None type.
        :rtype: bool
        """
        if self._model_component is None:
            return False

        return self._model_component.is_valid()

    @property
    def layer(self) -> typing.Union[QgsMapLayer, None]:
        """Returns the map layer from the underlying model
        component object.

        :returns: Map layer corresponding from the underlying
        model component.
        :rtype: QgsMapLayer
        """
        return self._model_component.to_map_layer()

    def set_layer(self, layer: QgsMapLayer) -> bool:
        """Set the map layer for the component item.

        It sets the :py:attr:`~path` attribute of the
        underlying data model.

        :param layer: Map layer for the component item.
        :type layer: QgsMapLayer

        :returns: Returns True if the layer was successfully
        set, else False if the layer is invalid.
        :rtype: bool
        """
        if not layer:
            return False

        if not layer.isValid():
            return False

        path = layer.source()
        self._model_component.path = path
        if isinstance(layer, QgsRasterLayer):
            self._model_component.layer_type = LayerType.RASTER
        elif isinstance(layer, QgsVectorLayer):
            self._model_component.layer_type = LayerType.VECTOR

        return True

    @staticmethod
    @abstractmethod
    def create(model_component: BaseModelComponent) -> "ModelComponentItem":
        """Factory method for creating an instance of a model item.

        This is an abstract method that needs to be implemented by
        subclasses.

        :param model_component: Source model component for creating the
        corresponding item.
        :type model_component: BaseModelComponent

        :returns: Model component item for use in a standard item model.
        :rtype: ModelComponentItem
        """
        pass

    @abstractmethod
    def clone(self) -> "ModelComponentItemType":
        """Creates a deep copied version of the model item.

        :returns: Cloned version of the model item containing all
        the properties as the source.
        :rtype: ModelComponentItem
        """
        pass

    @property
    def user_defined(self) -> bool:
        """Returns whether the model component is user-defined or default
        that is shipped together with the plugin.

        :returns: True if the model component is user-defined else False
        if its a default component.
        :rtype: bool
        """
        return self.model_component.user_defined


class NcsPathwayItem(LayerComponentItem):
    """Standard item for an NCS pathway object."""

    def __init__(self, ncs: NcsPathway):
        super().__init__(ncs)
        self._ncs_pathway = ncs
        self._parent = None

    @property
    def ncs_pathway(self) -> NcsPathway:
        """Returns an instance of the underlying NcsPathway object.

        :returns: The underlying NcsPathway model object.
        :rtype: NcsPathway
        """
        return self._ncs_pathway

    @property
    def parent(self) -> "ActivityItem":
        """Returns the parent activity item if specified.

        :returns: Returns the parent item if set when this item is
        mapped to an ActivityItem.
        :rtype: ActivityItem
        """
        return self._parent

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the standard item.
        :rtype: int
        """
        return NCS_PATHWAY_TYPE

    @staticmethod
    def create(ncs: NcsPathway) -> "NcsPathwayItem":
        """Creates an instance of the NcsPathwayItem from the model object.

        :returns: An instance of the NcsPathway item to be used in a standard
        model.
        :rtype: NcsPathwayItem
        """
        return NcsPathwayItem(ncs)

    def clone(self) -> "NcsPathwayItem":
        """Creates a cloned version of this item."""
        ncs = clone_ncs_pathway(self.ncs_pathway)

        return NcsPathwayItem(ncs)

    def json_data(self) -> str:
        """Creates a mapping of NCS pathway property names
        and their corresponding values.

        :returns: JSON representation of property name-value
        pairs for an NCS pathway object.
        :rtype: str
        """
        ncs_attrs = ncs_pathway_to_dict(self._ncs_pathway)

        return json.dumps(ncs_attrs)

    def is_carbon_valid(self) -> bool:
        """Returns the validity of the carbon layers in the
        underlying NCSPathway model object.

        :returns: True if the carbon layers are valid, else
        False.
        :rtype: bool
        """
        return self.ncs_pathway.is_carbon_valid()

    def setEnabled(self, enabled: bool):
        """Override for default implementation that also
        enables or disables selection of the item.
        """
        self.setSelectable(enabled)
        super().setEnabled(enabled)


class ActivityItem(LayerComponentItem):
    """Standard item for an activity object."""

    def __init__(self, activity: Activity, bold_text: bool = True):
        super().__init__(activity)
        self._activity = activity

        self.set_bold_font(bold_text)

        self._ncs_items = []

        # Remap pathway uuids so that there are no duplicate
        # pathways under each activity.
        self._uuid_remap = {}

    def set_bold_font(self, bold: bool):
        """Set the text to bold or normal.

        :param bold: True to set the text font to be
        bold, else False to normal.
        :type bold: bool
        """
        font = self.font()
        font.setBold(bold)
        self.setFont(font)

    @property
    def activity(self) -> Activity:
        """Returns an instance of the underlying activity object.

        :returns: The underlying activity object.
        :rtype: Activity
        """
        return self._activity

    @property
    def ncs_items(self) -> typing.List[NcsPathwayItem]:
        """Returns a collection of NcsPathwayItem in this activity
        object.

        :returns: Collection of NcsPathwayItem objects in this
        activity object.
        :rtype: list
        """
        return self._ncs_items

    @property
    def ncs_pathways(self) -> typing.List[NcsPathway]:
        """Returns a collection of NcsPathway objects.

        :returns: Collection of NcsPathway objects linked to the
        underlying activity object.
        :rtype: list
        """
        return [ncs_item.ncs_pathway for ncs_item in self.ncs_items]

    def ncs_item_from_original_pathway(
        self, ncs_pathway: typing.Union[NcsPathway, str]
    ) -> typing.Union[NcsPathwayItem, None]:
        """Retrieves the NCS item corresponding to the original NCS
        pathway i.e. before it is added to this activity item.

        :param ncs_pathway: Original NCS pathway data model or
        unique identifier of the NCS pathway.
        :type ncs_pathway: NcsPathway, str

        :returns: The matching NCS pathway item in this activity
         item, else None if there is no matching item.
        """
        if isinstance(ncs_pathway, NcsPathway):
            ncs_uuid = str(ncs_pathway.uuid)
        else:
            ncs_uuid = ncs_pathway

        if ncs_uuid not in self._uuid_remap:
            return None

        new_uuid = self._uuid_remap[ncs_uuid]

        return self.ncs_item_by_uuid(new_uuid)

    @property
    def original_ncs_pathways(self) -> typing.List[NcsPathway]:
        """Returns a collection of NcsPathway objects but with
        their original UUIDs.

        These are used for persisting the NCsPathway objects
        related to the underlying activity object.

        :returns: Collection of NcsPathway objects with their
        original UUIDs linked to the underlying activity object.
        :rtype: list
        """
        ncs_pathways = []
        for ncs_item in self.ncs_items:
            ncs = ncs_item.ncs_pathway
            keys = [
                old_uuid
                for old_uuid, new_uuid in self._uuid_remap.items()
                if new_uuid == ncs_item.uuid
            ]
            if len(keys) == 0:
                continue

            cloned_ncs = clone_ncs_pathway(ncs)

            original_uuid = UUID(keys[0])
            cloned_ncs.uuid = original_uuid
            ncs_pathways.append(cloned_ncs)

        return ncs_pathways

    @property
    def layer_item(self) -> QtGui.QStandardItem:
        """Returns the view item for the layer.

        :returns: Returns the view item for the map layer
        else None if no layer has been specified for the
        model.
        :rtype: QtGui.QStandardItem
        """
        return self._layer_item

    def clear_layer(self):
        """Clears the layer reference in the model component."""
        self._activity.clear_layer()

    def ncs_item_by_uuid(self, ncs_uuid: str) -> typing.Union[NcsPathwayItem, None]:
        """Returns an NcsPathway item matching the given UUID.

        :param ncs_uuid: UUID of the NcsPathway item to retrieve.
        :type ncs_uuid: str

        :returns: NcsPathwayItem matching the given UUID, else None
        if not found.
        :rtype: NcsPathwayItem
        """
        ncs_items = [n for n in self._ncs_items if n.uuid == ncs_uuid]

        if len(ncs_items) == 0:
            return None

        return ncs_items[0]

    def contains_ncs_item(self, item_uuid: str) -> bool:
        """Checks whether this item contains an NcsPathway item with
        the given UUID.

        :param item_uuid: UUID of the NcsPathway item to search for.
        :type item_uuid: str

        :returns: True if there is an NcsPathwayItem matching the
        given UUID, else False.
        :rtype: bool
        """
        if self.ncs_item_by_uuid(item_uuid) is None:
            return False

        return True

    def add_ncs_pathway_item(self, ncs_item: NcsPathwayItem) -> bool:
        """Adds an NCS pathway item to this activity item.

        If the item already contains a layer, then the add operation
        will not be successful.

        :param ncs_item: NCS pathway item to the collection.
        :type ncs_item: NcsPathwayItem

        :returns: True if the NCS pathway item was successfully added, else
        False if there underlying NCS pathway object was invalid, there
        is an existing item with the same UUID or if the layer property
        had already been set.
        """
        if self.layer:
            return False

        old_uuid = ncs_item.uuid
        new_uuid = uuid4()
        ncs_item.ncs_pathway.uuid = new_uuid

        if old_uuid in self._uuid_remap:
            return False

        if self.contains_ncs_item(ncs_item.uuid):
            return False

        if not ncs_item.is_valid():
            return False

        if self._activity.contains_pathway(ncs_item.uuid):
            return False

        if not self._activity.add_ncs_pathway(ncs_item.ncs_pathway):
            return False

        self._ncs_items.append(ncs_item)
        ncs_item._parent = self

        self._uuid_remap[old_uuid] = str(new_uuid)

        return True

    def remove_ncs_pathway_item(self, item_uuid: str) -> bool:
        """Removes the NcsPathwayItem matching the given UUID.

        :param item_uuid: The UUID of the NcsPathwayItem to remove.
        :type item_uuid: str

        :returns: True if the item was successfully removed, else
        False.
        :rtype: bool
        """
        if not self.contains_ncs_item(item_uuid):
            return False

        idxs = [i for i, n in enumerate(self._ncs_items) if n.uuid == item_uuid]
        if len(idxs) == 0:
            return False

        item = self._ncs_items.pop(idxs[0])
        item._parent = None
        del item

        self._activity.remove_ncs_pathway(item_uuid)

        old_uuids = [k for k, v in self._uuid_remap.items() if v == item_uuid]
        if len(old_uuids) > 0:
            del self._uuid_remap[old_uuids[0]]

        return True

    def bottom_ncs_item_index(self) -> typing.Union[QtCore.QModelIndex, None]:
        """Returns the model index of the bottom-most NcsPathwayItem
        under this activity item.

        :returns: Model index of the bottom-most NcsPathwayItem.
        :rtype: QModelIndex
        """
        if len(self._ncs_items) == 0:
            return None

        bottom_ncs_item = max(self._ncs_items, key=lambda n: n.index().row())

        return bottom_ncs_item.index()

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the standard item.
        :rtype: int
        """
        return ACTIVITY_TYPE

    @staticmethod
    def create(activity: Activity) -> "ActivityItem":
        """Creates an instance of the activity item from
        the model object.

        :returns: An instance of the activity item to
        be used in a standard model.
        :rtype: Activity
        """
        return ActivityItem(activity)

    def clone(self) -> "ActivityItem":
        """Creates a cloned version of this item.

        The cloned IM will contain pathways with the
        original UUID. The UUID of the activity object will not change.
        """
        activity = clone_activity(
            self.activity,
        )

        # Use NCS pathways with original UUIDs
        activity.pathways = self.original_ncs_pathways

        return ActivityItem(activity)

    def enable_default_pathways(self, state: bool):
        """Enable or disable default NCS pathway items.

        :param state: True to enable default NCS pathways else False
        to disable them.
        :type state: bool
        """
        for ncs_item in self._ncs_items:
            if ncs_item.user_defined:
                continue

            if ncs_item.isEnabled() != state:
                ncs_item.setEnabled(state)

    def _enable_layer_item(self, state: bool):
        """Enable/disable layer item if it exists."""
        item_index = self.index()
        if not item_index.isValid():
            return

        model = self.model()
        if model is None:
            return

        layer_item_row = item_index.row() + 1
        layer_item = model.item(layer_item_row, 0)
        if layer_item is None:
            return

        if not isinstance(layer_item, LayerItem):
            return

        layer_item.setEnabled(state)

    def setEnabled(self, enabled: bool):
        """Override for default implementation that
        also enables or disables NCS pathway items.
        """
        self.enable_default_pathways(enabled)
        self._enable_layer_item(enabled)
        self.setSelectable(enabled)
        super().setEnabled(enabled)


class LayerItem(QtGui.QStandardItem):
    """Contains a custom identifier for an item used to define a
    layer for an activity.
    """

    def type(self) -> int:
        """Returns the type of the standard item.

        :returns: Type identifier of the standard item.
        :rtype: int
        """
        return LAYER_ITEM_TYPE


class ComponentItemModel(QtGui.QStandardItemModel):
    """View model for ModelComponent objects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(1)

        self._uuid_row_idx = {}

    def add_component_item(
        self, component_item: ModelComponentItem, position=-1
    ) -> bool:
        """Adds a model component item to the view model.

        :param component_item: Model component item to be added to the view
        model.
        :type component_item: ModelComponentItem

        :param position: Reference row to insert the item.
        :type position: int

        :returns: True if the component item was successfully added, else
        False if there is an existing component item with the same UUID.
        :rtype: bool
        """
        idx = position
        if position == -1:
            idx = self.rowCount()

        if self.contains_item(str(component_item.uuid)):
            return False

        self.insertRow(idx, component_item)

        self._re_index_rows()

        return True

    def contains_item(self, item_uuid: str) -> bool:
        """Checks if the model contains an item with the given UUID.

        :param item_uuid: UUID of the model item.
        :type item_uuid: str

        :returns: True if there is an existing item else False.
        :rtype: bool
        """
        return True if self.component_item_by_uuid(item_uuid) is not None else False

    def component_item_by_uuid(
        self, uuid_str: str
    ) -> typing.Union[ModelComponentItemType, None]:
        """Retrieves a ModelComponentItem based on a matching UUID.

        :param uuid_str: UUID of the model item.
        :type uuid_str: str

        :returns: Component item matching the given UUID or None if not found.
        :rtype: ModelComponentItem
        """
        if uuid_str not in self._uuid_row_idx:
            return None

        row = self._uuid_row_idx[uuid_str]

        return self.item(row)

    def index_by_uuid(self, uuid_str) -> QtCore.QModelIndex:
        """Get the QModelIndex object for the component item matching the
        given UUID identifier.

        :param uuid_str: UUID of the model item.
        :type uuid_str: str

        :returns: QModelIndex for the component item matching the given
        UUID or an invalid QModelIndex if not found.
        :rtype: QtCore.QModelIndex
        """
        if uuid_str not in self._uuid_row_idx:
            return QtCore.QModelIndex()

        row = self._uuid_row_idx[uuid_str]

        return self.index(row, 0)

    def update_item(self, item: ModelComponentItemType) -> bool:
        """Update an existing ModelComponentItem if it exists in the model.

        :param item: An updated instance of the ModelComponentItem.
        :type item: ModelComponentItem

        :returns: True if the item was successfully updated, else False
        if there was no matching item found in the model.
        :rtype: bool
        """
        if not self.contains_item(item.uuid):
            return False

        item.update(item.model_component)

        return True

    def model_components(self) -> typing.List[BaseModelComponentType]:
        """Returns a collection of model component objects in the model.

        :returns: A collection of all model component objects.
        :rtype: list
        """
        return [item.model_component for item in self.model_component_items()]

    def model_component_items(self) -> typing.List[ModelComponentItem]:
        """Returns model component items in the model.

        :returns: Model component items in the model.
        :rtype: list
        """
        rows = self.rowCount()

        items = []
        for r in range(rows):
            item = self.item(r)
            items.append(item)

        return items

    def _re_index_rows(self):
        """Remap UUIDs with corresponding row numbers.

        Not the most ideal but should suffice for a small number of
        rows in the model.
        """
        rows = self.rowCount()
        for r in range(rows):
            item = self.item(r)
            if not isinstance(item, ModelComponentItem):
                continue

            self._uuid_row_idx[item.uuid] = r

    def remove_component_item(self, uuid_str: str) -> bool:
        """Removes a ModelComponentItem based on a matching UUID.

        :param uuid_str: UUID of the model item to be removed.
        :type uuid_str: str

        :returns: True if the component item was successfully removed, else
        False if there was not matching UUID.
        :rtype: bool
        """
        if not self.contains_item(uuid_str):
            return False

        if uuid_str not in self._uuid_row_idx:
            return False

        self.removeRows(self._uuid_row_idx[uuid_str], 1)
        del self._uuid_row_idx[uuid_str]

        self._re_index_rows()

        return True

    def enable_default_items(self, state: bool):
        """Enable or disable items for default model components.

        :param state: True to enable or False to disable.
        :type state: bool
        """
        for item in self.model_component_items():
            if not isinstance(item, LayerComponentItem):
                continue

            if not item.user_defined:
                item.setEnabled(state)

    def disabled_items(self) -> typing.List[LayerComponentItem]:
        """Gets the list of disabled items in the model.

        :returns: Disabled items in the model.
        :rtype: list
        """
        return [item for item in self.model_component_items() if not item.isEnabled()]


ComponentItemModelType = typing.TypeVar(
    "ComponentItemModelType", bound=ComponentItemModel
)


class NcsPathwayItemModel(ComponentItemModel):
    """View model for NCS pathways."""

    def add_ncs_pathway(self, ncs: NcsPathway) -> bool:
        """Add an NCS pathway object to the model.

        :param ncs: NCS pathway object to the added to the view.
        :type ncs: NcsPathway

        :returns: True if the NCS pathway object was added successfully,
        else False if the NcsPathway object is invalid.
        :rtype: bool
        """
        ncs_item = NcsPathwayItem.create(ncs)
        self._update_display(ncs_item)

        status = self.add_component_item(ncs_item)

        self.sort(0)
        self._re_index_rows()

        return status

    def update_ncs_pathway(self, ncs: NcsPathway) -> bool:
        """Updates the NCS pathway item in the model.

        :param ncs: NcsPathway whose corresponding item is to be updated.
        :type ncs: NcsPathway

        :returns: Returns True if the operation was successful else False
        if the matching item was not found in the model.
        """
        item = self.component_item_by_uuid(str(ncs.uuid))
        if item is None:
            return False

        status = self.update_item(item)
        if not status:
            return False

        self._update_display(item)

        self.sort(0)
        self._re_index_rows()

        return True

    def _update_display(self, item: NcsPathwayItem):
        """Update icon based on whether an item is valid or invalid."""
        ncs = item.ncs_pathway

        if ncs.is_valid():
            item.setIcon(QtGui.QIcon())
        else:
            error_icon = FileUtils.get_icon("mIndicatorLayerError.svg")
            item.setIcon(error_icon)

            if not ncs.is_carbon_valid():
                item.setToolTip(self.tr("Invalid carbon layer data source"))
            else:
                item.setToolTip(self.tr("Invalid NCS pathway data source"))

    def pathways(self, valid_only: bool = False) -> typing.List[NcsPathway]:
        """Returns NCS pathway objects in the model.

        :param valid_only: Whether to only return NCS pathway objects
        that are valid.
        :type valid_only: bool

        :returns: All NCS pathway objects in the model (default), else only
        those NCS pathway objects that are valid if valid_only is True.
        :rtype: list
        """
        ncs_pathways = self.model_components()

        if valid_only:
            return [p for p in ncs_pathways if p.is_valid()]

        return ncs_pathways

    def remove_ncs_pathway(self, ncs_uuid: str) -> bool:
        """Remove an NCS pathway item from the model.

        param uuid: UUID of the NCS pathway item to be removed.
        :type ncs_uuid: str

        :returns: True if the NCS pathway item as successfully
        removed, else False if there was not matching UUID.
        :rtype: bool
        """
        return self.remove_component_item(ncs_uuid)

    def supportedDropActions(self) -> QtCore.Qt.DropActions:
        """Configure the model to only support copying items in a
        drag-and-drop operation.

        :returns: Supported drag-and-drop action for NCS pathway
        items.
        :rtype: QtCore.Qt.DropActions
        """
        return QtCore.Qt.CopyAction

    def mimeTypes(self) -> typing.List[str]:
        """Returns supported MIME types that can be used to
        describe a list of model indexes for NCS pathway items.

        :returns: MIME type for NCS pathway items which is JSON
        string but MIME type is the default datalist type for Qt
        since it does not allow custom types.
        :rtype: list
        """
        return [NCS_MIME_TYPE]

    def mimeData(self, indexes: typing.List[QtCore.QModelIndex]) -> QtCore.QMimeData:
        """Serializes the NCS items corresponding to the specified indexes.

        :param indexes: NCS items stored in the specified indexes.
        :type indexes: list

        :returns: Mime object containing serialized NCS items.
        :rtype: QtCore.QMimeData
        """
        mime_data = QtCore.QMimeData()
        item_data = QtCore.QByteArray()
        data_stream = QtCore.QDataStream(item_data, QtCore.QIODevice.WriteOnly)

        for idx in indexes:
            if not idx.isValid():
                continue

            ncs_item = self.itemFromIndex(idx)
            if ncs_item is None:
                continue

            # Do not add disabled items (e.g. disabled default NCS pathway items)
            if not ncs_item.isEnabled():
                continue

            ncs_data = QtCore.QByteArray()
            ncs_data.append(ncs_item.json_data())
            data_stream << ncs_data

        mime_data.setData(NCS_MIME_TYPE, item_data)

        return mime_data


class ActivityItemModel(ComponentItemModel):
    """View model for activity."""

    # Signal raised when the pathways have been updated (added or removed)
    activity_pathways_updated = QtCore.pyqtSignal(ActivityItem)

    def __init__(self, *args, **kwargs):
        self._load_pathways = kwargs.pop("load_pathways", True)
        super().__init__(*args, **kwargs)

    def add_activity(self, activity: Activity, layer: QgsMapLayer = None) -> bool:
        """Add an activity object to the model.

        :param activity: Activity object to be
        added to the view.
        :type activity: Activity

        :param layer: Map layer for the activity.
        :type layer: QgsMapLayer

        :returns: True if an activity object was added
        successfully, else False.
        :rtype: bool
        """
        # Check if we can retrieve the layer from the path
        if layer is None:
            if activity.path:
                layer = activity.to_map_layer()

        activity_item = ActivityItem.create(activity)
        if not self._load_pathways:
            activity_item.set_bold_font(False)

        result = self.add_component_item(activity_item)

        # No need to load any additional information if not showing pathways
        if not self._load_pathways:
            return result

        if layer:
            status = self.set_model_layer(activity_item, layer)
            if not status:
                result = False
        else:
            # Add NCS pathways. If there are underlying NCS pathway objects then
            # clone them, remove then re-insert so that the underlying NCS pathways can
            # have the unique UUID in the activity item.
            if result:
                cloned_activity = clone_activity(activity)
                cloned_ncs_pathways = cloned_activity.pathways

                # Remove pathways in the IM
                activity.pathways = []

                # Now add the NCSs afresh
                for ncs in cloned_ncs_pathways:
                    ncs_item = NcsPathwayItem.create(ncs)
                    self.add_ncs_pathway(ncs_item, activity_item)

        return result

    def remove_layer(self, activity_item: ActivityItem):
        """Removes the layer reference from the underlying
        activity.

        :param activity_item: activity
        item whose layer is to be removed.
        :type activity_item: ActivityItem
        """
        if activity_item.layer is None:
            return

        if not self.contains_item(activity_item.uuid):
            return

        # Remove item in model
        item_idx = self.index_by_uuid(activity_item.uuid)
        layer_row = item_idx.row() + 1
        self.removeRows(layer_row, 1)
        self._re_index_rows()

        # Remove underlying layer reference
        activity_item.clear_layer()

    def set_model_layer(
        self,
        activity_item: ActivityItem,
        layer: QgsMapLayer,
        display_name: str = "",
    ) -> bool:
        """Set the layer for the given activity item.

        :param activity_item: activity item
        whose layer is to be specified.
        :type activity_item: ActivityItem

        :param layer: Map layer to be set for the activity.
        :type layer: QgsMapLayer

        :param display_name: Display name for the layer node. If not
        specified then the name from the map layer is used.
        :type display_name: str

        :returns: True if the layer was successfully set for the
        activity, else False if the layer is invalid, if
        there are already existing NCS pathways in the activity
         or if the item is not in the model.
        :rtype: bool
        """
        if len(activity_item.ncs_items) > 0:
            return False

        if not self.contains_item(activity_item.uuid):
            return False

        if not activity_item.set_layer(layer):
            return False

        if not display_name:
            display_name = layer.name()

        icon = FileUtils.get_icon("mIconRaster.svg")
        item = LayerItem(icon, display_name)
        item.setToolTip(layer.source())
        item.setData(activity_item)

        item_idx = self.index_by_uuid(activity_item.uuid)
        layer_row = item_idx.row() + 1
        self.insertRow(layer_row, item)
        self._re_index_rows()

        return True

    def add_ncs_pathway(
        self, ncs_item: NcsPathwayItem, target_activity_item: ActivityItem
    ) -> bool:
        """Adds an NCS pathway item to the activity.

        :param ncs_item: NCS pathway item to the collection.
        :type ncs_item: NcsPathwayItem

        :param target_activity_item: Target activity for the NCS item.
        :type target_activity_item: ActivityItem

        :returns: True if the NCS pathway item was successfully added, else
        False if there underlying NCS pathway object was invalid, there
        is an existing item with the same UUID or if there is already
        a map layer defined for the activity.
        """
        idx = target_activity_item.index()
        if not idx.isValid():
            return False

        if not isinstance(target_activity_item, LayerComponentItem):
            return False

        # Do not add if the activity item has been disabled
        # (e.g. disabled default activities)
        if not target_activity_item.isEnabled():
            return False

        # If there is an existing layer then return
        if target_activity_item.layer:
            return False

        clone_ncs_item = ncs_item.clone()
        status = target_activity_item.add_ncs_pathway_item(clone_ncs_item)
        if not status:
            return False

        bottom_idx = target_activity_item.bottom_ncs_item_index()
        reference_row = max(bottom_idx.row(), idx.row())
        self.add_component_item(clone_ncs_item, reference_row + 1)

        self.activity_pathways_updated.emit(target_activity_item)

        return True

    def remove_ncs_pathway_item(self, ncs_uuid: str, parent: ActivityItem) -> bool:
        """Remove an NCS pathway item from the activity.

        param uuid: UUID of the NCS pathway item to be removed.
        :type ncs_uuid: str

        :param parent: Reference activity item that
        is the parent to the NCS pathway item.
        :type parent: ActivityItem

        :returns: True if the NCS pathway item has been
        successfully removed, else False if there was
        no matching UUID.
        :rtype: bool
        """
        status = parent.remove_ncs_pathway_item(ncs_uuid)
        if not status:
            return False

        self.activity_pathways_updated.emit(parent)

        return self.remove_component_item(ncs_uuid)

    def update_activity(self, activity: Activity, layer: QgsMapLayer = None) -> bool:
        """Updates the activity item using the given activity.

        :param activity: Activity object whose
        corresponding item is to be updated.
        :type activity: Activity

        :param layer: Map layer to be updated for the
        activity if specified.
        :type layer: QgsMapLayer

        :returns: Returns True if the operation was successful else False
        if the matching item was not found in the activity.
        """
        item = self.component_item_by_uuid(str(activity.uuid))
        if item is None:
            return False

        status = self.update_item(item)
        if not status:
            return False

        # Update layer information
        self.remove_layer(item)
        if layer:
            layer_status = self.set_model_layer(item, layer)
            if not layer_status:
                return False

        return True

    def activities(self) -> typing.List[Activity]:
        """Returns activity objects in the view model.

        :returns: Activity objects in the view model.
        :rtype: list
        """
        return [model_item.activity for model_item in self.activity_items()]

    def activity_items(self) -> typing.List[ActivityItem]:
        """Returns all activity item objects in the model.

        :returns: Activity items in the model.
        :rtype: list
        """
        component_items = self.model_component_items()

        return [ci for ci in component_items if ci.type() == ACTIVITY_TYPE]

    def update_ncs_pathway_items(self, ncs_pathway: NcsPathway) -> bool:
        """Update NCS pathway items matching the given NCS pathway model.

        If the NCS pathway model is not valid then the NCS pathway items
        in the activity item will not be updated.

        :param ncs_pathway: Original NCS pathway object whose corresponding
        models are to be updated.
        :type ncs_pathway: NcsPathway

        :returns: True if matching NCS pathway items have been updated,
        else False.
        :rtype: bool
        """
        if not ncs_pathway.is_valid():
            return False

        for activity_item in self.activity_items():
            ncs_item_for_original = activity_item.ncs_item_from_original_pathway(
                ncs_pathway
            )
            if ncs_item_for_original is None:
                continue

            item_pathway = ncs_item_for_original.ncs_pathway
            # Copy attribute values excluding the UUID
            copy_layer_component_attributes(item_pathway, ncs_pathway)
            ncs_item_for_original.update(item_pathway)

        return True

    def remove_ncs_pathway_items(self, ncs_pathway_uuid: str):
        """Delete NCS pathway items matching the given NCS pathway model.

        If the NCS pathway model is not valid then the NCS pathway items
        in the activity item will not be deleted.

        :param ncs_pathway_uuid: Unique identifier of the NCS pathway object
        whose corresponding models are to be removed in the activities.
        :type ncs_pathway_uuid: str
        """
        for im_item in self.activity_items():
            ncs_item_for_original = im_item.ncs_item_from_original_pathway(
                ncs_pathway_uuid
            )
            if ncs_item_for_original is None:
                continue

            status = self.remove_ncs_pathway_item(ncs_item_for_original.uuid, im_item)

    def remove_activity(self, uuid_str: str) -> bool:
        """Remove an activity item from the view model.

        param uuid: UUID of the activity item to
        be removed.
        :type uuid_str: str

        :returns: True if the activity item was successfully
        removed, else False if there was not matching UUID.
        :rtype: bool
        """
        activity_item = self.component_item_by_uuid(uuid_str)
        if activity_item is None:
            return False

        if len(activity_item.ncs_items) > 0:
            ncs_items = activity_item.ncs_items
            for item in ncs_items:
                self.remove_component_item(item.uuid)
        else:
            # Layer item
            self.remove_layer(activity_item)

        return self.remove_component_item(uuid_str)

    def flags(self, index):
        flags = super().flags(index)

        return QtCore.Qt.ItemIsDropEnabled | flags

    def dropMimeData(
        self,
        data: QtCore.QMimeData,
        action: QtCore.Qt.DropAction,
        row: int,
        column: int,
        parent: QtCore.QModelIndex,
    ) -> bool:
        """Implements behaviour for handling data supplied by drag
        and drop operation.

        :param data: Object containing data from the drag operation.
        :type data: QtCore.QMimeData

        :param action: Type of the drag and drop operation.
        :type action: QtCore.Qt.DropAction

        :param row: Row location of dropped data.
        :type row: int

        :param column: Column location of dropped data.
        :type column: int

        :param parent: Index location for target item where the
        operation ended.
        :type parent: QtCore.QModelIndex

        :returns: True if the data and action can be handled by the
        model, else False.
        :rtype: bool
        """
        if action == QtCore.Qt.IgnoreAction:
            return True

        if not data.hasFormat(NCS_MIME_TYPE):
            return False

        encoded_data = data.data(NCS_MIME_TYPE)
        data_stream = QtCore.QDataStream(encoded_data, QtCore.QIODevice.ReadOnly)

        ncs_items = []

        while not data_stream.atEnd():
            byte_data = QtCore.QByteArray()
            data_stream >> byte_data

            item_data = json.loads(byte_data.data())
            ncs_pathway = create_ncs_pathway(item_data)

            ncs_item = NcsPathwayItem(ncs_pathway)
            ncs_items.append(ncs_item)

        # Get reference to activity item
        if parent.isValid():
            activity_item = self.itemFromIndex(parent)
        else:
            row_count = self.rowCount()
            activity_item = self.item(row_count - 1)

        if activity_item is None or isinstance(activity_item, LayerItem):
            return False

        if activity_item.type() == NCS_PATHWAY_TYPE:
            target_activity_item = activity_item.parent
        else:
            target_activity_item = activity_item

        # Add NCS items to the activity.
        status = True
        for item in ncs_items:
            status = self.add_ncs_pathway(item, target_activity_item)

        return status
