# -*- coding: utf-8 -*-
"""
/***************************************************************************
 MMTools
                                 A QGIS plugin
        Print composer, mask and markers creation
                              -------------------
        begin                : 2016-08-09
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Lutra
        email                : info@lutraconsulting.co.kr
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import configparser
import re
import os.path
import tempfile

dtypes = {
    0: {'name': 'UnknownDataType'}, 
    1: {'name': 'Byte', 'atype': 'B',
        'min': 0, 'max': 255, 'dig': 0},
    2: {'name': 'UInt16', 'atype': 'H',
        'min': 0, 'max': 65535, 'dig': 0},
    3: {'name': 'Int16', 'atype': 'h',
        'min': -32768, 'max': 32767, 'dig': 0},
    4: {'name': 'UInt32', 'atype': 'I',
        'min': 0, 'max': 4294967295, 'dig': 0},
    5: {'name': 'Int32', 'atype': 'i',
        'min': -2147483648, 'max': 2147483647, 'dig': 0},
    6: {'name': 'Float32', 'atype': 'f',
        'min': -3.4e38, 'max': 3.4e38, 'dig': 5}, 
    7: {'name': 'Float64', 'atype': 'd',
        'min': -1.7e308, 'max': 1.7e308, 'dig': 12}, 
    8: {'name': 'CInt16'}, 
    9: {'name': 'CInt32'}, 
    10: {'name': 'CFloat32'}, 
    11: {'name': 'CFloat64'}, 
    12: {'name': 'ARGB32'}, 
    13: {'name': 'ARGB32_Premultiplied'}
}


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def icon_path(icon_filename):
    plugin_dir = os.path.dirname(__file__)
    return os.path.join(plugin_dir, 'icons', icon_filename)    

def read_ini_par(file, section, parameter):
    # Get the email address from the configuration file file
    parser = configparser.ConfigParser()
    parser.read(file)
    return parser.get(section, parameter)

def is_korean(path):
    strs = re.sub('[^가-힣]', '', path.decode('utf-8').encode('utf-8'))
    if len(strs)>0:
        return True
    else :
        return False

# 콤보박스 리스트 셋팅 type은( tif, shp , "" 일땐 모두다)
def SetCommbox(self, layers, commbox, type):
    cmdCount = commbox.count()

    if type.upper() == "TIF" or  type.upper() == "ASC" :
        for i, layer in enumerate(layers):
            layertype = layer.type()
            if layertype == layer.RasterLayer:
                layerName = layer.name()
        
                commbox.addItem(layerName)
                commbox.setItemData(cmdCount+i, layerName, 3)
                self.layerId[layer.id()] = layerName
                
# 각각의 기능별로 arg를 생성하고 반환 하는 기능
def GetTaudemArg(self, inputfile, ouputfile, taudemcommand, facoption, optionvalue):
    option = optionvalue
    tauPath  = "C:\\Program Files\\TauDEM\\TauDEM5Exe\\"
    input = inputfile.replace('\\', '\\\\')
    output = ouputfile.replace('\\', '\\\\')
    output_Temp = tempfile.mkdtemp() + r"\1.tif"
    arg = ""
    if taudemcommand == "SK":
        tauPath = tauPath + "PitRemove.exe"
        arg = '"' + tauPath + '"' + ' -z ' + '"' + input + '"' + ' -fel ' + '"' + output + '"'
    elif taudemcommand == "FD":
        tauPath = tauPath + "D8FlowDir.exe"
        arg = '"' + tauPath + '"' + ' -fel ' + '"' + input + '"' + ' -p ' + '"' + output + '"' + ' -sd8 ' + '"' + output_Temp + '"'
    elif taudemcommand == "FA":
        tauPath = tauPath + "AreaD8.exe"
        if str(facoption) == "True":
            arg = '"' + tauPath + '"' + ' -p ' + '"' + input + '"' + ' -ad8 ' + '"' + output + '"'
        else:
            arg = '"' + tauPath + '"' + ' -p ' + '"' + input + '"' + ' -ad8 ' + '"' + output + '"' + ' -nc '
    elif taudemcommand == "SG":
        tauPath = tauPath + "D8FlowDir.exe"
        arg = '"' + tauPath + '"' + ' -fel ' + '"' + input + '"' + ' -p ' + '"' + output_Temp + '"' + ' -sd8 ' + '"' + output + '"'
    elif taudemcommand == "ST":
        tauPath = tauPath + "Threshold.exe"
        arg ='"' + tauPath + '"' + ' -ssa '  + '"' + input + '"' + ' -src ' + '"' + output + '"' + ' -thresh ' +  option
    return arg