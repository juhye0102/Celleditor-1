# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Serval  https://github.com/erpas/serval
                                 A QGIS plugin
 Set Raster Values
                              -------------------
        begin                : 2015-12-30
        git sha              : $Format:%H$
        copyright            : (C) 2015 by Radosław Pasiok
        email                : rpasiok@gmail.com
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
from osgeo import gdal
from osgeo.gdalconst import *
from qgis.gui import *
from qgis.core import *
from qgis.PyQt.QtCore import pyqtSignal
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from PyQt5 import QtGui, uic
from PyQt5.QtWidgets import *

import math
import os.path
import tempfile
import numpy as np
from math import ceil
from array import array
from subprocess import Popen, call

from .utils import *
from .user_communication import UserCommunication


gdal.ErrorReset()
gdal.UseExceptions()
_Fd=""
_Hydro=""
_Layer=""
_Slop=""
_mainLayer={}

class BandSpinBox(QgsDoubleSpinBox):
    """Spinbox class for raster band value"""
    
    user_hit_enter = pyqtSignal()
    
    def __init__(self, parent=None):
        super(BandSpinBox, self).__init__()

    def keyPressEvent(self, event):
#         b = self.property("bandNr")
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if is_number(self.text().replace(',','.')):
                self.setValue(float(self.text().replace(',', '.')))
                self.user_hit_enter.emit()
        else:
            QgsDoubleSpinBox.keyPressEvent(self, event)


class Serval:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.uc = UserCommunication(iface, 'DEM Cell Editor')
        self.menu = u'DEM Cell Editor'
        self.actions = []
        self.toolbar = self.iface.addToolBar(u'DEM Cell Editor')
        self.toolbar.setObjectName(u'DEM Cell Editor')
        self.setup_tools()
        self.mode = 'probe'
        self.bands = {}
        self.px, self.py = [0, 0]
        self.last_point = QgsPoint(0,0)
        self.undos = {}
        self.redos = {}
        self.layerId = {}
        self.b1SBox = BandSpinBox()
        self.sboxes = [self.b1SBox]
        
        self.mapRegistry = QgsProject.instance()
        self.iface.currentLayerChanged.connect(self.set_active_raster)
#         self.mapRegistry.layersAdded.connect(self.set_active_raster)        
        self.mapRegistry.layersAdded.connect(self.add_layer_event)
        self.mapRegistry.layerRemoved.connect(self.remove_layer_event)
        self.canvas.mapToolSet.connect(self.check_active_tool)
        self.b1SBox.user_hit_enter.connect(self.change_cell_value_key)
        
    def setup_tools(self):
        self.probeTool = QgsMapToolEmitPoint(self.canvas)
        self.probeTool.setObjectName('SProbeTool')
        self.probeTool.setCursor(QCursor(QPixmap(os.path.join(os.path.dirname(__file__), 'icons/probe_tool.svg')), hotX=2, hotY=22))
        self.probeTool.canvasClicked.connect(self.point_clicked)


    def initGui(self):
        self.add_action(
            os.path.join(self.plugin_dir,'icons/serval_icon.svg'),
            text=u'Show Toolbar',
            add_to_menu=True,
            add_to_toolbar=False,
            callback=self.show_toolbar,
            parent=self.iface.mainWindow())
        
        self.probe_btn = self.add_action(
            os.path.join(self.plugin_dir,'icons/spord_icon.png'),
            text=u'Probing Mode',
            whats_this=u'Probing Mode',
            add_to_toolbar=True,
            callback=self.activate_probing,
            parent=self.iface.mainWindow())
        self.setup_spin_boxes()

        self.probe_btn2 = self.add_action(
            os.path.join(self.plugin_dir, 'icons/Setting.jpg'),
            text=u'Reload fd,filled dem....',
            whats_this=u'Reload fd,filled dem....',
            add_to_toolbar=True,
            callback=self.Reload,
            parent=self.iface.mainWindow())
        self.set_active_raster()


    
    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=False,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
            
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)
        return action


    def unload(self):
        self.iface.actionPan().trigger()
        
        for action in self.actions:
            self.iface.removePluginMenu(
                u'DEM Cell Editor',
                action)
            self.iface.removeToolBarIcon(action)
#         del self.b1SBox, self.b2SBox
        del self.toolbar


    def show_toolbar(self):
        if self.toolbar:
            self.toolbar.show()      
    
    def check_active_tool(self, tool):
        try:
            if not tool.objectName() in ['SDrawTool']:
                self.probe_btn.setChecked(False)
        except AttributeError:
            pass


    def activate_probing(self):
        self.mode = 'probe'
        self.canvas.setMapTool(self.probeTool)
        self.probe_btn.setChecked(True)


    # 2018 04-10 박: Slop,hydro,fd 새로 작성 
    def Reload(self):
        try:
            msg = 'This function recalculates Filled DEM, FD in DEM.\n'
            msg += 'It also takes time because it is LABELING for all CELLs.\n'
            msg += 'Do you want to do that?'
            result = QMessageBox.question(None, "DEM Cell Editor", msg, QMessageBox.Yes, QMessageBox.No)
            if result == QMessageBox.Yes:
                self.Execute_taudem()
        except Exception as es:
            self.MessageboxShowInfo("error",str(es))

    def setup_spin_boxes(self):
#         sbox=self.b1SBox
        self.b1SBox.setMinimumSize(QSize(60, 25))
        self.b1SBox.setMaximumSize(QSize(60, 25))
        self.b1SBox.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
 
        self.b1SBox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.b1SBox.setKeyboardTracking(False)
        self.b1SBox.setShowClearButton(False)
        self.b1SBox.setExpressionsEnabled(False)
        self.b1SBox.setStyleSheet("")
        self.toolbar.addWidget(self.b1SBox)

#=======2018/06/18 셀 위치(행렬) 보여주는 라벨
        #셀 위치(행렬) 라벨
        self.positionLabel = QLabel("   Xcols, Yrows :    ")
        self.positionLabel.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.toolbar.addWidget(self.positionLabel)
        
        #xcols 값
        #라벨에 이미 값이 들어 있으면 값이 나오지 않음... 
        self.position_xy_Label = QLabel()
        self.position_xy_Label.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.toolbar.addWidget(self.position_xy_Label)
        
#=======2018/06/18
        
              
        #소수점 spin 박스 라벨
        spinLabel = QLabel("   Decimal : ")
        spinLabel.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.toolbar.addWidget(spinLabel)

        #cell 값 라벨링 소수점 결정
        self.b2SBox = QSpinBox()

        self.b2SBox.setMinimumSize(QSize(60, 25))
        self.b2SBox.setMaximumSize(QSize(60, 25))
        self.b2SBox.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.b2SBox.setValue(3)
        self.toolbar.addWidget(self.b2SBox)

        #layer
        spinLabel = QLabel("   Layer : ")
        spinLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
        self.toolbar.addWidget(spinLabel)

        self.cmdLayer =QComboBox()
        self.cmdLayer.setMinimumSize(QSize(120, 20))
        self.cmdLayer.addItem("select layer")
        self.toolbar.addWidget(self.cmdLayer)

        #Hydro
        spinLabel = QLabel("   Filled DEM : ")
        spinLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
        self.toolbar.addWidget(spinLabel)

        self.cmdHydro =QComboBox()
        self.cmdHydro.setMinimumSize(QSize(120, 20))
        self.cmdHydro.addItem("select layer")
        self.toolbar.addWidget(self.cmdHydro)


         #FD
        spinLabel = QLabel("   FD : ")
        spinLabel.setAlignment(Qt.AlignLeading | Qt.AlignLeft | Qt.AlignVCenter)
        self.toolbar.addWidget(spinLabel)

        self.cmdFD =QComboBox()
        self.cmdFD.setMinimumSize(QSize(120, 20))
        self.cmdFD.addItem("select layer")
        self.toolbar.addWidget(self.cmdFD)

        #각각의 콤보에 레이어 목록 셋팅
        layers = QgsProject.instance().mapLayers().values()
        SetCommbox(self, layers, self.cmdLayer, "tif")
        SetCommbox(self, layers, self.cmdHydro, "tif")
        SetCommbox(self, layers, self.cmdFD, "tif")

        #콤보박스 선택 이벤트
        self.cmdLayer.currentIndexChanged.connect(lambda:self.Selectcmb(self.cmdLayer,"layer"))
        self.cmdHydro.currentIndexChanged.connect(lambda:self.Selectcmb(self.cmdHydro,"hydro"))
        self.cmdFD.currentIndexChanged.connect(lambda:self.Selectcmb(self.cmdFD,"fd"))

    def Selectcmb(self,commbox,type):
        # 콤보 박스에서 선택된 레이어 경로 받아 오기
        global _Fd,_Hydro,_Layer,_mainLayer
        layername = commbox.currentText()
        if layername == 'select layer':
            return ""
        else:
            layer = None
            for lyr in QgsProject.instance().mapLayers().values():
                if lyr.name() == layername:
                    layer = lyr
            
            dataUri = layer.dataProvider().dataSourceUri()
            if type.upper()=="LAYER":
                if _Layer == dataUri:
                    return
                _Layer = dataUri
                _mainLayer = layer
            elif type.upper()=="HYDRO":
                if _Hydro == dataUri:
                    return
                _Hydro = dataUri
            elif type.upper()=="FD":
                if _Fd == dataUri:
                    return
                _Fd = dataUri

        self.Active_CellValue()


    def Active_CellValue(self):
        if _Fd!="" and _Hydro!="" and _Layer!="" :
            self.run()
    
    def remove_layer_event(self, layerID):
        global _Fd, _Hydro, _Layer, _mainLayer
        try:
            layerName = self.layerId[layerID]
        except KeyError:
            return
        
        textIndex = self.cmdLayer.findText(layerName)

        fd = self.cmdFD.currentText()
        hydro = self.cmdHydro.currentText()
        layer = self.cmdLayer.currentText()
        
        if fd == layerName:
            self.cmdFD.setCurrentIndex(0)
            _Fd = ''
        if hydro == layerName:
            self.cmdHydro.setCurrentIndex(0)
            _Hydro = ''
        if layer == layerName:
            self.cmdLayer.setCurrentIndex(0)
            _Layer = ''
            _mainLayer = {}

        self.cmdFD.removeItem(textIndex)
        self.cmdHydro.removeItem(textIndex)
        self.cmdLayer.removeItem(textIndex)
    
    def add_layer_event(self, layers):
        SetCommbox(self, layers, self.cmdLayer, "tif")
        SetCommbox(self, layers, self.cmdHydro, "tif")
        SetCommbox(self, layers, self.cmdFD, "tif")
            
        self.set_active_raster()

    # 메시지 박스 출력
    def MessageboxShowInfo(self, title, message):
        QMessageBox.information(None, title, message)

    def MessageboxShowError(self, title, message):
        QMessageBox.warning(None, title, message)


    def point_clicked(self, point=None, button=None):
        # check if active layer is raster
        if self.raster is None:
            self.uc.bar_warn("Choose a raster to set a value", dur=3)
            return
        
        # check if coordinates trasformation is required
        canvas_srs = self.iface.mapCanvas().mapSettings().destinationCrs()
        if point is None:
            pos = self.last_point
        elif not canvas_srs == self.raster.crs():
            project = QgsProject.instance()
            srs_transform = QgsCoordinateTransform(canvas_srs, self.raster.crs(), project)
            try:
                pos = srs_transform.transform(point)
            except QgsCsException as err:
                self.uc.bar_warn(
                    "Point coordinates transformation failed! Check the raster projection:\n\n{}".format(repr(err)),
                    dur=5)
                return
        else:
            pos = QgsPointXY(point.x(), point.y())
        
        # keep last clicked point
        self.last_point = pos
        
        # check if the point is within active raster bounds
        if self.rbounds[0] <= pos.x() <= self.rbounds[2]:
            self.px = int((pos.x() - self.rbounds[0]) / self.raster.rasterUnitsPerPixelX())  # - self.gt[0]) / self.gt[1])
        else:
            self.uc.bar_info("Out of x bounds", dur=2)
            return

        if self.rbounds[1] <= pos.y() <= self.rbounds[3]:
            self.py = int((self.rbounds[3] - pos.y()) / self.raster.rasterUnitsPerPixelY()) #  - self.gt[3]) / self.gt[5])
        else:
            self.uc.bar_info("Out of y bounds", dur=2)
            return

        # show x, y
        self.position_xy_Label.setText(str(self.px)+", "+str(self.py))
        # probe current raster value, dict: band_nr -> value
        vals = self.rdp.identify(pos, QgsRaster.IdentifyFormatValue).results()

        # for rasters having more that 3 bands, ignore other than 1-3
        bands_to_ignore = [i for i in vals.keys() if i > 3]
        for band_nr in bands_to_ignore:
            del vals[band_nr]

        # data types for each band
        dtypes = []

        for nr in range(1, min(4, self.band_count + 1)):
            # bands data type
            dtypes.append(self.bands[nr]['qtype'])
            
            # check if nodata is defined
            if self.mode == 'gom' and self.bands[nr]['nodata'] is None:
                msg = 'NODATA value is not defined for one of the raster\'s bands.\n'
                msg += 'Please define it in raster properties dialog!'
                self.uc.show_warn(msg)
                return
            
            # if in probing mode, set band's spinbox value
            if self.mode == 'probe':
                val = vals[nr] if vals[nr]!=None and is_number(vals[nr]) else self.bands[nr]['nodata']
                self.bands[nr]['sbox'].setValue(val)
                self.bands[nr]['sbox'].setFocus()
                self.bands[nr]['sbox'].selectAll()

        if not self.mode == 'probe':

            old_vals = [v if v is not None else self.bands[k]['nodata'] for k, v in sorted(vals.items())]
            if self.mode == 'gom':
                temp_vals = [self.bands[nr]['nodata'] for nr in sorted(vals.keys())]
                new_vals = [int(v) if dtypes[i] < 6 else float(v) for i, v in enumerate(temp_vals)]
            else:
                temp_vals = [self.bands[nr]['sbox'].value() for nr in sorted(vals.keys())]
                new_vals = [int(v) if dtypes[i] < 6 else float(v) for i, v in enumerate(temp_vals)]

            # write the new cell value(s)
            self.change_cell_value(new_vals)

    def set_rgb_from_picker(self, c):
        """Set bands spinboxes values after color change in the color picker"""
        self.bands[1]['sbox'].setValue(c.red())
        self.bands[2]['sbox'].setValue(c.green())
        self.bands[3]['sbox'].setValue(c.blue())


    def change_cell_value(self, vals, x=None, y=None):
        """Save new bands values to data provider"""

        if not self.rdp.isEditable():
            success = self.rdp.setEditable(True)
            if not success:
                self.uc.show_warn('QGIS can\'t modify this type of raster')
                return

        if not x:
            x = self.px
            y = self.py

        for nr in range(1, min(4, self.band_count + 1)):
            rblock = QgsRasterBlock(self.bands[nr]['qtype'], 1, 1)
            rblock.setValue(0, 0, vals[nr - 1])
            success = self.rdp.writeBlock(rblock, nr, x, y)
            if not success:
                self.uc.show_warn('QGIS can\'t modify this type of raster')
                return

        self.rdp.setEditable(False)
        self.raster.triggerRepaint()

        # prepare raster for next actions
        self.prepare_gdal_raster(True)

    def change_cell_value_key(self):
        """Change cell value after user changes band's spinbox value and hits Enter key"""
        if self.last_point:
            pm = self.mode
            self.mode = 'draw'
            self.point_clicked()
            self.mode = pm
        
            self.run_RapidRefresh()
        
    def undo(self):
        if self.undos[self.raster.id()]:
            data = self.undos[self.raster.id()].pop()
            self.redos[self.raster.id()].append(data)
        else:
            return
        self.change_cell_value(data[0], data[2], data[3])
     
     
    def redo(self):
        if self.redos[self.raster.id()]:
            data = self.redos[self.raster.id()].pop()
            self.undos[self.raster.id()].append(data)
        else:
            return
        self.change_cell_value(data[1], data[2], data[3])
     
 
        # check if user defined additional NODATA value
        if self.rdp.userNoDataValues(1):
            note = '\nNote: there is a user defined NODATA value.\nCheck the raster properties (Transparency).'
        else:
            note = ''
        # first band data type
        dt = self.rdp.dataType(1)
         
        # current NODATA value
        if self.rdp.srcHasNoDataValue(1):
            cur_nodata = self.rdp.srcNoDataValue(1)
            if dt < 6:
                cur_nodata = '{0:d}'.format(int(float(cur_nodata)))
        else:
            cur_nodata = ''
         
        label = 'Define/change raster NODATA value.\n\n'
        label += 'Raster data type: {}.{}'.format(dtypes[dt]['name'], note)
        nd, ok = QInputDialog.getText(None, "Define NODATA Value",
            label, QLineEdit.Normal, str(cur_nodata))
        if not ok:
            return
         
        if not is_number(nd):
            self.uc.show_warn('Wrong NODATA value!')
            return
         
        new_nodata = int(nd) if dt < 6 else float(nd)
         
        # set the NODATA value for each band
        res = []
        for nr in range(1, min(4, self.band_count + 1)):
            res.append(self.rdp.setNoDataValue(nr, new_nodata))
            self.rdp.setUseSrcNoDataValue(nr, True)
         
        if False in res:
            self.uc.show_warn('Setting new NODATA value failed!')
        else:
            self.uc.bar_info('Succesful setting new NODATA values!', dur=2)
        self.prepare_gdal_raster()
        self.raster.triggerRepaint()

    def set_active_raster(self):
        """Active layer has change - check if it is a raster layer and prepare it for the plugin"""
        # properly close previous raster data if exist
        try:
            for nr in self.bands.keys():
                self.bands[nr]['data'] = None
                self.bands = None
                self.gdal_raster = None
        except:
            pass
        
        # disable all toolbar actions except Help
        # (for vectors and unsupported rasters)
        for action in self.actions:
            action.setDisabled(True)
        layer = self.iface.activeLayer()
        
        # check if we can work with the raster
        if layer!=None and layer.isValid() and \
                layer.type() == 1 and \
                layer.dataProvider() and \
                (layer.dataProvider().capabilities() & 2) and \
                not layer.crs() is None:
            self.raster = layer
            self.rdp = layer.dataProvider()
            self.band_count = layer.bandCount()
            
            # is data type supported?
            supported = True
            for nr in range(1, min(4, self.band_count + 1)):
                if self.rdp.dataType(nr) == 0 or self.rdp.dataType(nr) > 7:
                    t = dtypes[self.rdp.dataType(nr)]['name']
                    supported = False
                
            if supported:
                # disable all toolbar actions (for vectors and unsupported rasters)
                for action in self.actions:
                    action.setEnabled(True)
                # if raster properties change get them (refeshes view)
                self.raster.rendererChanged.connect(self.prepare_gdal_raster)
                self.prepare_gdal_raster(True)

            # not supported data type
            else:
                msg = 'The raster data type is: {}.'.format(t)
                msg += '\nServal can\'t work with it, sorry!'
                self.uc.show_warn(msg)
                self.raster = None
                # self.mColorButton.setDisabled(True)
                self.prepare_gdal_raster(False)
        
        # it is not a supported raster layer
        else:
            self.raster = None
            # self.mColorButton.setDisabled(True)
            self.prepare_gdal_raster(False)

    def prepare_gdal_raster(self, supported=True):
        """Open raster using GDAL if it is supported"""
        # reset bands' spin boxes
#         for i, sbox in enumerate(self.sboxes):
        self.sboxes[0].setProperty('bandNr', 1)
        self.sboxes[0].setDisabled(True)
            
        if not supported:
            return

        extent = self.raster.extent()
        self.rbounds = extent.toRectF().getCoords()

        self.bands = {}
        for nr in range(1, min(4, self.band_count + 1)):
            self.bands[nr] = {}
            self.bands[nr]['sbox'] = self.sboxes[0]

            # NODATA
            if self.rdp.sourceHasNoDataValue(nr): # source nodata value?
                self.bands[nr]['nodata'] = self.rdp.sourceNoDataValue(nr)
                # use the src nodata
                self.rdp.setUseSourceNoDataValue(nr, True)
            # no nodata defined in the raster source
            else:
                # check if user defined any nodata values
                if self.rdp.userNoDataValues(nr):
                    # get min nodata value from the first user nodata range
                    nd_ranges = self.rdp.userNoDataValues(nr)
                    self.bands[nr]['nodata'] = nd_ranges[0].min()
                else:
                    # leave nodata undefined
                    self.bands[nr]['nodata'] = None

            # enable band's spin box
            self.bands[nr]['sbox'].setEnabled(True)
            # get bands data type
            dt = self.bands[nr]['qtype'] = self.rdp.dataType(nr)
            # set spin boxes properties
            self.bands[nr]['sbox'].setMinimum(dtypes[dt]['min'])
            self.bands[nr]['sbox'].setMaximum(dtypes[dt]['max'])
            self.bands[nr]['sbox'].setDecimals(dtypes[dt]['dig'])
                

    def show_website(self):
        QDesktopServices.openUrl(QUrl('https://github.com/erpas/serval/wiki'))


    def first_use(self):
        meta = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'metadata.txt')
        ver = read_ini_par(meta, 'general', 'version')
        s = QSettings()
        first = s.value('DEM Cell Editor/version', '0')
        if first == '0':
            return
        elif not first == ver:
            self.uc.show_warn('Please, restart QGIS before using the Serval plugin!')
            s.setValue('DEM Cell Editor/version', ver)

# 라벨링 실행 함수
    def run(self):
        #QgsMessageLog.logMessage("START","Cell Value",QgsMessageLog.INFO)
        
        #dem = layer
        #mapCanvas에 올라와 있는 레이어 모두 refresh(cell 값 변경된 것을 적용하기 위함)
        #self.iface.mapCanvas.refreshAllLayers()
        try:
            #이전 vector layer 삭제
            #기존.. map canvas에 올라온 레이어만 취급하는 코드 사용 중이었으나..
            #layer pannel에 올라온 모든 레이어를 취급하는 코드로 변경.
            for item in QgsProject.instance().mapLayers().values():
                if issubclass(type(item), QgsVectorLayer) ==True:
                    #vector layer 중 라벨을 띄우는 레이어만 지워야 함.
                    #라벨 레이어의 값은 지정되어 있으므로 그 이름을 가진 레이어만 지우도록 조건문
                    if (item.name() == "CellValue"):
                        QgsProject.instance().removeMapLayer( item.id() )

            QgsProject.instance().addMapLayer(self.get_cellvalue())
            self.iface.setActiveLayer(_mainLayer)
        except Exception as ex:
            QgsMessageLog.logMessage(str(ex),"Cell Value",Qgis.Info)

        QgsMessageLog.logMessage("FINISH","Cell Value",Qgis.Info)

		

# 라벨링 실행 함수  run() 에서 복사함 2018.4.15 ice
    def run_RapidRefresh(self):
        try:
            for item in QgsProject.instance().mapLayers().values():
                if issubclass(type(item), QgsVectorLayer) ==True:
                    if (item.name() == "CellValue"):
                        QgsProject.instance().removeMapLayer( item.id() )

            QgsProject.instance().addMapLayer(self.get_cellvalue_RapidRefresh())
            self.iface.setActiveLayer(_mainLayer)
        except Exception as ex:
            QgsMessageLog.logMessage(str(ex),"Cell Value RapidRefresh",Qgis.Info)

        QgsMessageLog.logMessage("FINISH","Cell Value RapidRefresh",Qgis.Info)		
		
    # cell value 라벨링 함수 분리(by.ice)code -> 조 일부 변경
    # dem, hydro, fd, slope 값 라벨링 함수.
    #def  get_cellvalue(self,dem,hydro,slope,Fdr):
    def  get_cellvalue(self):

        strTempFolder=tempfile.mkdtemp()
        
        #임시 파일 생성(dem, hydro, slope, fdr)
        asc_file_dem = strTempFolder + r"\1.asc"
        asc_file_hydro = strTempFolder + r"\2.asc"
        asc_file_fdr = strTempFolder + r"\4.asc"

        #tif 파일 asc로 변경하는 함수
        self.Convert_TIFF_To_ASCii(_Layer,asc_file_dem)
        self.Convert_TIFF_To_ASCii(_Hydro,asc_file_hydro)
        #self.Convert_TIFF_To_ASCii(_Slop,asc_file_slope)
        self.Convert_TIFF_To_ASCii(_Fd,asc_file_fdr)

        #asc 파일 읽기(dem, hydro, slope, fdr)
        ascii_grid_dem = np.loadtxt(asc_file_dem, skiprows=6)	#skip 6 . caution!
        ascii_grid_hydro = np.loadtxt(asc_file_hydro, skiprows=6)	#skip 6 . caution! 
        ascii_grid_fdr = np.loadtxt(asc_file_fdr, skiprows=6)	#skip 6 . caution!  

        xmin, ymin, xmax, ymax = _mainLayer.extent().toRectF().getCoords()
        crs = _mainLayer.crs().toWkt()
        point_layer = QgsVectorLayer('Point?crs=' + crs, 'CellValue', 'memory')
        point_provider = point_layer.dataProvider()
        
        resV = point_provider.addAttributes( [ QgsField("DEM",QVariant.String) ] )#dem table
        resH = point_provider.addAttributes( [ QgsField("HYDRO",QVariant.String) ] )#hydro table
        resFD = point_provider.addAttributes( [ QgsField("FD",QVariant.String) ] )#fdr table
        
        gridWidth = _mainLayer.rasterUnitsPerPixelX()
        gridHeight = _mainLayer.rasterUnitsPerPixelY()

        rows = ceil((ymax - ymin) / gridHeight)
        cols = ceil((xmax - xmin) / gridWidth)

        point_layer.startEditing()  # if omitted , setAttributes has no effect.

        
        #스타일 파일 경로
        strStylePath = os.path.dirname(os.path.realpath(__file__)) +"/templete/CellValue_Style_Template_cho_v4.qml"
        #strStylePath="C:\GRM\CellValue_Style_Template_cho.qml"     #We Will change the path to relative path
        point_layer.loadNamedStyle(strStylePath)

        for i in range(int(cols)):
            #print i,
            for j in range(int(rows)):
                #if j>690 and j<620 and i>210 and i<230 : 
                if 2>1 : 
                    ptCellCenter = QgsPointXY(xmin+ i *gridWidth+gridWidth/2.0,ymin + j*gridHeight+gridHeight/2.0)

                    feat = QgsFeature()
                    feat.setGeometry(QgsGeometry().fromPointXY(ptCellCenter))

                    value1=ascii_grid_dem[rows-j-1,i] #dem
                    value2=ascii_grid_hydro[rows-j-1,i] #hydro
                    value4=ascii_grid_fdr[rows-j-1,i] #fdr

                    #fdr value 변환.. 화살표 라벨
                    value4new =self.Flow_Direction(value4)
                    
                    value1= format(value1,".{0}f".format(str(self.b2SBox.text()))) #dem, 값 소수점 자리
                    value2= format(value2,".{0}f".format(str(self.b2SBox.text()))) #hydro, 소수점자리 결정 포맷은 self.b2SBox

                    feat.setAttributes([value1,value2,value4new])
                    point_provider.addFeatures([feat])

        point_layer.commitChanges()
        point_layer.updateExtents()
        point_layer.triggerRepaint()
        QgsMessageLog.logMessage("2","Cell Value",Qgis.Info)

        return point_layer

    # get_cellvalue()를 복사해서 수정함. 2018.4.15 by ice
    def  get_cellvalue_RapidRefresh(self):
        try:
            print (self.px, self.py, " get_cellvalue_RapidRefresh")
    
            strTempFolder=tempfile.mkdtemp()
            
            #임시 파일 생성(dem, hydro, slope, fdr)
            asc_file_dem = strTempFolder + r"\1.asc"
    
            #tif 파일 asc로 변경하는 함수
            self.Convert_TIFF_To_ASCii(_Layer,asc_file_dem)
                   
            #asc 파일 읽기(dem, hydro, slope, fdr)
            ascii_grid_dem = np.loadtxt(asc_file_dem, skiprows=6)	#skip 6 . caution!
            
            xmin, ymin, xmax, ymax = _mainLayer.extent().toRectF().getCoords()
            crs = _mainLayer.crs().toWkt()
            point_layer = QgsVectorLayer('Point?crs=' + crs, 'CellValue', 'memory')
            point_provider = point_layer.dataProvider()
            
            resV = point_provider.addAttributes( [ QgsField("DEM",QVariant.String) ] )#dem table
            resFD = point_provider.addAttributes( [ QgsField("FD",QVariant.String) ] )#fdr table
            
            gridWidth = _mainLayer.rasterUnitsPerPixelX()
            gridHeight = _mainLayer.rasterUnitsPerPixelY()
    
            rows = ceil((ymax - ymin) / gridHeight)
            cols = ceil((xmax - xmin) / gridWidth)
    
            point_layer.startEditing()  # if omitted , setAttributes has no effect.
    
            
            #스타일 파일 경로
            strStylePath = os.path.dirname(os.path.realpath(__file__)) +"/templete/CellValue_RapidStyle_Template_ice_v1.qml"
            point_layer.loadNamedStyle(strStylePath)
    
            myFormatString=str(self.b2SBox.text())  # for speed up . 2018.4.15
            
            #print cols,rows  #QGIS meta data의  cols, rows 와 일치함
            for i in range(int(cols)):
                for j in range(int(rows)):
                    # use 8 , 15x15
                    if math.fabs(self.px-i)<8 and  math.fabs(self.py-(rows-j-1))<8 : 
                        ptCellCenter = QgsPointXY(xmin+ i *gridWidth+gridWidth/2.0, ymin + j*gridHeight+gridHeight/2.0)
    
                        feat = QgsFeature()
                        feat.setGeometry(QgsGeometry().fromPointXY(ptCellCenter))
    
                        value1=ascii_grid_dem[rows-j-1,i] #dem
                        value1= format(value1,".{0}f".format(myFormatString)) #dem, 값 소수점 자리
                        
                        FD_Code=0
                        FD_Code=self.Flow_DirectionTauCode(ascii_grid_dem,rows,j,i)
    
                        #fdr value 변환.. 화살표 라벨
                        if FD_Code==0 : 
                            value4new="?"
                        else:
                            value4new =self.Flow_Direction(FD_Code)
                        
                        feat.setAttributes([value1,value4new])
                        point_provider.addFeatures([feat])
    
            point_layer.commitChanges()
            point_layer.updateExtents()
            point_layer.triggerRepaint()
            QgsMessageLog.logMessage("2","get_cellvalue_RapidRefresh()",Qgis.Info)
    
            return point_layer
        except Exception as e:
            print(e)
		
		
    #TIFF 래스터 -> ASC 래스터 포맷 변경(by.ice)code
    def Convert_TIFF_To_ASCii(self,inputfile,OutFile):
            gdal_translate = QgsApplication.instance().applicationDirPath()+r'/../bin/gdal_translate.exe'
            #2018.3.25 ice : / r is very importtant . .. https://stackoverflow.com/questions/36397342/python-adds-special-characters-to-path-string
            if not os.path.exists(gdal_translate) :
                 print ("GDAL path Error!",gdal_translate)
                 return
            arg = '"{0}" -of AAIGrid -co FORCE_CELLSIZE=TRUE "{1}" "{2}"'.format(gdal_translate, inputfile, OutFile)
            CREATE_NO_WINDOW = 0x08000000
            result = call(arg, creationflags=CREATE_NO_WINDOW)
            if result == 0 :
                print ("asc ok :" + OutFile)

    # flow drirection 값 변환.. 화살표 라벨
    def Flow_Direction(self, value):
        fdr=value
        MyDirections = {3: chr(8593), 2:chr(8599), 1: chr(8594), 8:chr(8600) , 7: chr(8595), 6: chr(8601), 5: chr(8592), 4: chr(8598)}
        direction = MyDirections.get(int(fdr))
        return direction

    # flow drirection TauDEM FD Code값 변환
    def Flow_DirectionTauCode(self, DEMArray,rows,j,i):
        # using keyboard number pad . 키보드 숫자 판 방향을 임시 사용함. 직관적이어서.

        try:
            dem7=DEMArray[rows-j-1-1,i-1]
            dem8=DEMArray[rows-j-1-1,i]
            dem9=DEMArray[rows-j-1-1,i+1]
            dem4=DEMArray[rows-j-1,i-1]
            dem5=DEMArray[rows-j-1,i]
            dem6=DEMArray[rows-j-1,i+1]
            dem1=DEMArray[rows-j-1+1,i-1]
            dem2=DEMArray[rows-j-1+1,i]
            dem3=DEMArray[rows-j-1+1,i+1]
        except:
            return 0

        #print dem7,dem8,dem9
        #print dem4,dem5,dem6
        #print dem1,dem2,dem3

        diag=math.sqrt(2)		
        
        maxDIFF=0
        FDCode=0
        if (dem5-dem7)/diag>0:
            FDCode=7;maxDIFF=(dem5-dem7)/diag
        if (dem5-dem8)>maxDIFF:
            FDCode=8;maxDIFF=dem5-dem8
        if (dem5-dem9)/diag>maxDIFF:
            FDCode=9;maxDIFF=(dem5-dem9)/diag
        if (dem5-dem4)>maxDIFF:
            FDCode=4;maxDIFF=(dem5-dem4)
        if (dem5-dem6)>maxDIFF:
            FDCode=6;maxDIFF=(dem5-dem6)
        if (dem5-dem1)/diag>maxDIFF:
            FDCode=1;maxDIFF=(dem5-dem1)/diag
        if (dem5-dem2)>maxDIFF:
            FDCode=2;maxDIFF=(dem5-dem2)
        if (dem5-dem3)/diag>maxDIFF:
            FDCode=3;maxDIFF=(dem5-dem3)/diag

        FDCodeTau=0
        if FDCode==7: FDCodeTau=4
        if FDCode==8: FDCodeTau=3
        if FDCode==9: FDCodeTau=2
        if FDCode==4: FDCodeTau=5
        if FDCode==6: FDCodeTau=1
        if FDCode==1: FDCodeTau=6
        if FDCode==2: FDCodeTau=7
        if FDCode==3: FDCodeTau=8
        
        #print FDCode,FDCodeTau
        return FDCodeTau

    # 각각의 기능별로 arg를 생성하고 반환 하는 기능
    def Execute_taudem(self):
        # Fill sink 시작
        arg = GetTaudemArg(self,_Layer, _Hydro, "SK", False, 0)
        ReultFill = self.ExecuteArg(arg, _Hydro)
        if (ReultFill):
            # FD 시작
            arg = GetTaudemArg(self,_Hydro, _Fd, "FD", False, 0)
            FillResult = self.ExecuteArg(arg, _Fd)
            if (FillResult):
                # Slope 시작
                arg = GetTaudemArg(self,_Hydro, _Slop, "SG", False, 0)
                SlopResult = self.ExecuteArg(arg, _Slop)
                if (SlopResult):
                    self.run()

    def ExecuteArg(self, arg, outpath):
        returnValue = self.Execute(arg)
        if returnValue == 0:
            # self.Addlayer_OutputFile(outpath)
            return True
        else:
            self.MessageboxShowError("Batch Processor", " There was an error creating the file. ")
            return False

    def Execute(self, arg):
        CREATE_NO_WINDOW = 0x08000000
        value = call(arg, creationflags=CREATE_NO_WINDOW)
        return value

    def call(*popenargs, **kwargs):
       return Popen(*popenargs, **kwargs).wait()
   
