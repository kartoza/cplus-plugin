# -*- coding: utf-8 -*-
"""
/***************************************************************************
 QgisCplus

 A QGIS plugin that enables usage of the CPLUS framework in land-use planning.
                             -------------------
        begin                : 2021-11-15
        copyright            : (C) 2021 by Kartoza
        email                : info@kartoza.com
        git sha              : $Format:%H$
 ***************************************************************************/
/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""
import os
import sys
import site
from pathlib import Path

LIB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "lib"))
if LIB_DIR not in sys.path:
    sys.path.append(LIB_DIR)


def _add_at_front_of_path(d):
    """add a folder at front of path"""
    sys.path, remainder = sys.path[:1], sys.path[1:]
    site.addsitedir(d)
    sys.path.extend(remainder)


# init ext-libs directory
plugin_dir = os.path.dirname(os.path.realpath(__file__))
# Put ext-libs folder near the front of the path (important on Linux)
_add_at_front_of_path(str(Path(plugin_dir) / "ext-libs"))


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load QgisCplus class
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """

    from .main import QgisCplus

    return QgisCplus(iface)
