# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Integraing_test
                                 A QGIS plugin
 Set multi raster value
                             -------------------
        begin                : 2019-03-21
        copyright            : (C) 2019 by Hermesys
        email                : info@hermesys.co.kr
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

from __future__ import absolute_import

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    from .cell_editor import Intergrated
    return Intergrated(iface)
