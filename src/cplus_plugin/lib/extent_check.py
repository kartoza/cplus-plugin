# -*- coding: utf-8 -*-
"""
Checks if a given extent is within the pilot area of interest.
"""

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
    QgsRectangle,
)

from ..definitions.defaults import DEFAULT_CRS_ID, PILOT_AREA_EXTENT


def extent_within_pilot(
    new_extent: QgsRectangle, source_crs: QgsCoordinateReferenceSystem = None
) -> bool:
    """Checks if the extent is within the pilot area.

    :param new_extent: Extent to check if within the pilot area.
    :type new_extent: QgsRectangle

    :param source_crs: Source coordinate reference system, if not specified then
    it will default to the project reference system. It reproject to WGS84
    which is what is used for the pilot extent.
    :type source_crs: QgsCoordinateReferenceSystem

    :returns: True if the current map canvas extent is within the
    pilot area, else False.
    :rtype: bool
    """
    if source_crs is None:
        source_crs = QgsProject.instance().crs()

    extent_list = PILOT_AREA_EXTENT["coordinates"]
    pilot_extent = QgsRectangle(
        extent_list[0], extent_list[2], extent_list[1], extent_list[3]
    )

    default_crs = QgsCoordinateReferenceSystem.fromEpsgId(DEFAULT_CRS_ID)
    if default_crs != source_crs:
        coordinate_xform = QgsCoordinateTransform(
            source_crs, default_crs, QgsProject.instance()
        )
        new_extent = coordinate_xform.transformBoundingBox(new_extent)

    return pilot_extent.contains(new_extent)


def extent_within_wgs84(extent: QgsRectangle) -> bool:
    """Checks if the given extents are within the bounds of WGS84.

    :returns: True if the bounds (which should be in WGS84) are within
    the bounds of WGS84, else False.
    :rtype: bool
    """
    crs = QgsCoordinateReferenceSystem("EPSG:4326")
    wgs_bounds = crs.bounds()

    return wgs_bounds.contains(extent)
