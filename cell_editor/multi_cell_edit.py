# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Serval
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
import re
import os
import shutil
import codecs
import tempfile
from subprocess import call

from qgis.gui import QgsDoubleSpinBox
from qgis.core import QgsProject, QgsMapLayer, QgsRasterLayer, QgsApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import QAction, QAbstractSpinBox, QLineEdit, QComboBox, QLabel, QFileDialog, QApplication

from .utils import *
from .user_communication import UserCommunication


class BandSpinBox(QgsDoubleSpinBox):
    userHitEnter = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super(BandSpinBox, self).__init__()
        self.parent = parent
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if is_number(self.text().replace(',','.')):
                self.setValue(float(self.text().replace(',','.')))
                self.userHitEnter.emit(True)
            else:
                self.parent.uc.bar_warn('Enter a number!')
        else:
            QgsDoubleSpinBox.keyPressEvent(self, event)

class LineEdit(QLineEdit):
    userHitEnter = pyqtSignal(bool)
    
    def __init__(self, parent=None):
        super(LineEdit, self).__init__()
        self.parent = parent

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            txt = self.text()
            oper = ["+", "-", "*", "/"]
            
            if (txt[:1] in oper) and (is_number(re.sub(r'[+-/*]', '', txt))):
                self.userHitEnter.emit(False)
            else:
                self.parent.uc.bar_warn('Invalid formula!')
        else:
            QLineEdit.keyPressEvent(self, event)
            
#--- Init                     
class MultiCellEdit:  
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        self.plugin_dir = os.path.dirname(__file__)
        self.uc = UserCommunication(iface, 'Multi cell edit')
        self.menu = u'Multi cell edit'
        self.qgis_project = QgsProject.instance()
        self.actions = []
        self.toolbar = self.iface.addToolBar(u'Multi cell edit')
        self.toolbar.setObjectName(u'Multi cell edit')
#         self.toolbar.setParent(parentTool)
        
        global SHP_LAYER
        SHP_LAYER = 'Multi_cellEdit_shpLayer'
        self.saveLayer = None   # 기존 저장 값이 있을 때 다시 로드하지 않고 갱신만 하도록 하기 위함.
        self.layers = {}        # ComboBox에 적혀진 이름과 LayerPenal에 있는 레이어 이름을 매칭 시키기 위함.
        self.layerId = {}       # Layer Remove할 떄 주어지는 ID 값과 레이어 이름을 매칭 시키기 위함.
        self.currentLayer = ''  # ComboBox 선택 인덱스 값이 레이어 삭제로 인해 변경 되었을 때 이벤트 발생을 막기 위함.
        tempPath = tempfile.mkdtemp(dir = os.path.dirname(__file__)+'/temp')+"/"
        self.qgisPath = QgsApplication.instance().applicationDirPath()+"/.."
        self.pathList = {
            "TEMP_PATH" : tempPath,
            "STYLE_FILE" : self.plugin_dir+'/style/vectorLayer_polygon_style.qml',
            "SAGA_CMD" : self.qgisPath+'/apps/saga-ltr/saga_cmd.exe',
            "OSGEO_BAT" : self.qgisPath+'/OSGeo4W.bat',
            "BAT_FILE" : tempPath+'createShape.bat',
            "SGRD_FILE" : tempPath+'temp.sgrd',
            "SHP_FILE" : tempPath+'Multi_cell_value.shp',
            "LOG_FILE" : self.plugin_dir+'/temp/temp_log.txt',
            "SAVE_PATH" : ''
        }
        
        self.cmb_layer = QComboBox()
        self.spb_batch = BandSpinBox(self)
        self.txt_inDecrease = LineEdit(self)

        self.iface.currentLayerChanged.connect(self.currentLayerChangeEvent)
        self.qgis_project.layerRemoved.connect(self.layerRemovedEvent)
        self.qgis_project.layersAdded.connect(self.layerAddedEvent)
        

    def initGui(self):
        self.add_action(
            'Multi cell value.png',  # icon
            text=u'Show Multi cell edit Tool bar',                  # 아이콘 text
            add_to_menu=True,                                       # 메뉴 추가 여부
            add_to_toolbar=False,                                   # 툴바 추가 여부
            callback=self.show_toolbar,                             # connection
            parent=self.iface.mainWindow())                         # 부모 객체
        
        textLabel = QLabel("   ")
        self.cmb_layer.setMinimumSize(QSize(120, 20))
        self.cmb_layer.addItem("select layer") 
        self.toolbar.addWidget(textLabel)
        self.cmb_layerAction = self.toolbar.addWidget(self.cmb_layer)
        
        self.btn_batch = self.add_action(
            'Batch.jpg',
            text=u'Apply constant value',
            whats_this=u'Apply constant value',
            add_to_toolbar=True,
            callback=(lambda: self.selectButtonType(False)),
            parent=self.iface.mainWindow())

        self.btn_increase = self.add_action(
            'In.Decrease.jpg',
            text=u'Applying increment / decrement values',
            whats_this=u'Applying increment / decrement values',
            add_to_toolbar=True,
            callback=(lambda: self.selectButtonType(True)),
            parent=self.iface.mainWindow())

        self.setup_gui()

        self.btn_save = self.add_action(
            'Save.png',
            text=u'Save',
            whats_this=u'Save',
            add_to_toolbar=True,
            callback=(lambda: self.resultSave("Save")),
            parent=self.iface.mainWindow())
 
        self.btn_saveAs = self.add_action(
            'Save as.png',
            text=u'Save as',
            whats_this=u'Save as',
            add_to_toolbar=True,
            callback=(lambda: self.resultSave("Save as")),
            parent=self.iface.mainWindow())
 
        self.btn_Refresh = self.add_action(
            'Refresh.png',
            text=u'Refresh',
            whats_this=u'Refresh',
            add_to_toolbar=True,
            callback=self.refreshEvent,
            parent=self.iface.mainWindow())
        
        self.currentLayerChangeEvent(self.iface.activeLayer())
        self.layerAddedEvent(self.qgis_project.mapLayers().values())
        
        self.spb_batch.userHitEnter.connect(self.changeValueAction)
        self.txt_inDecrease.userHitEnter.connect(self.changeValueAction)
        self.cmb_layer.currentIndexChanged['QString'].connect(self.selectLayerConvert)
        
    def setup_gui(self): 
        self.spb_batch.setMinimumSize(QSize(60, 25))
        self.spb_batch.setMaximumSize(QSize(60, 25))
        self.spb_batch.setDecimals(4)
        self.spb_batch.setMaximum(999999.00000)
        self.spb_batch.setMinimum(-999999.00000)
        self.spb_batch.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
        self.spb_batch.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.spb_batch.setKeyboardTracking(False)
        self.spb_batch.setShowClearButton(False)
        self.spb_batch.setExpressionsEnabled(False)
        self.spb_batch.setStyleSheet("")
         
        self.txt_inDecrease.setMinimumSize(QSize(60, 25))
        self.txt_inDecrease.setMaximumSize(QSize(60, 25))
        self.txt_inDecrease.setAlignment(Qt.AlignLeading|Qt.AlignLeft|Qt.AlignVCenter)
                 
        self.spb_batchAction = self.toolbar.addWidget(self.spb_batch)
        self.txt_inDecreaseAction = self.toolbar.addWidget(self.txt_inDecrease)
    
    def add_action(
        self,
        icon_name,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=False,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
            
        icon = QIcon(icon_path(icon_name))
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
        try:
            # sgrd, shape 파일이 저장된 temp 폴더 삭제
            self.getTempLog()  
            if self.isShapeLayer():
                self.qgis_project.removeMapLayer(self.layers[SHP_LAYER])
            shutil.rmtree(self.pathList["TEMP_PATH"])
        except Exception as e:
            # 파일이 사용 중이여서 삭제가 되지 않을 시 해당 폴더 이름을 기록하여 후에 다시 삭제 
            self.tempLog()
            
        for action in self.actions:
            self.iface.removePluginMenu(
                u'Multi cell edit',
                action)
            self.iface.removeToolBarIcon(action)
    
        self.layers = self.layerId = {}
        del self.toolbar
        
        try:
            # 연결이 자동으로 끊어지지 않아 임의적으로 명시하여 연결을 끊어줌.
            self.iface.currentLayerChanged.disconnect(self.currentLayerChangeEvent)
            self.qgis_project.layersAdded.disconnect(self.layerAddedEvent)
            self.qgis_project.layerRemoved.disconnect(self.layerRemovedEvent)
        except Exception:
            pass
        
    def show_toolbar(self):
        if self.toolbar:
            self.toolbar.show()

        
#--- Temp log   
    def tempLog(self):
        file = open(self.pathList["LOG_FILE"], 'w')
        file.write(self.pathList["TEMP_PATH"])
        file.close()
        
    def getTempLog(self):
        file = open(self.pathList["LOG_FILE"], 'r')
        read = file.readline()
        file.close()
        
        try:
            if read!=[] and os.path.isdir(read):
                shutil.rmtree(read)
        except Exception as e:
            self.uc.log_warn(str(e))


#--- Enable event
    def selectButtonType(self, type):
        self.spb_batch.setDisabled(type)
        self.txt_inDecrease.setDisabled(not type)

        self.iface.actionSelectRectangle().trigger()
        
    def currentLayerChangeEvent(self, mapLayer):
        raster = QgsMapLayer.RasterLayer
        selected = self.cmb_layer.currentIndex()
        
        type = mapLayer.type() if mapLayer!=None else raster
        typeFlag = True if type==raster else False
        saveFlag = True if selected==0 else False
        
        self.btn_batch.setDisabled(typeFlag)
        self.btn_increase.setDisabled(typeFlag)
        self.spb_batch.setDisabled(typeFlag)
        self.txt_inDecrease.setDisabled(True)
        self.btn_save.setDisabled(saveFlag)
        self.btn_saveAs.setDisabled(saveFlag)

#--- Layer event     
    def layerAddedEvent(self, layerList):
        keyList = self.layers.keys()
        itemCount = self.cmb_layer.count()
        
        try:
            # 추가된 레이어 개수만큼
            for c, layer in enumerate(layerList):
                # 레스터 레이어일 경우에만    
                if layer.type() == QgsMapLayer.RasterLayer:
                    layerId = layer.id()
                    layerName = layer.name()
                    
                    # 레스터 레이어의 이름을 dictionary 키 값으로 사용중이여서 중복이름 배제
                    if layerName in self.layers.keys():
                        overlap = len([key for key in keyList if layerName+"@" in key])    
                        layerName = layerName+"@"+str(overlap+1)
                        layer.setName(layerName)
                        
                    self.cmb_layer.addItem(layerName)
                    self.cmb_layer.setItemData(itemCount+c, layerName, Qt.ToolTipRole)
                    self.layers[layerName] = layer
                    self.layerId[layerId] = layerName
        except Exception as e:
            self.uc.bar_warn(str(e))
        
    def layerRemovedEvent(self, layerId):
        try:
            layerName = self.layerId[layerId]
            cmdItemCount = self.cmb_layer.findText(layerName)
            
            if layerName == self.cmb_layer.currentText():
                self.cmb_layer.setCurrentIndex(0)
            
            self.cmb_layer.removeItem(cmdItemCount)
            del self.layers[layerName]
            del self.layerId[layerId]

        except KeyError:
            pass
        except Exception as e:
            self.uc.bar_warn(str(e))
    

#--- Action            
    def selectLayerConvert(self, currentLayer):
        try:
            currentFlag = (currentLayer=='select layer')
            
            if not currentFlag and self.currentLayer!=currentLayer:
                self.pathList['SAVE_PATH'] = ''
                layerPath = self.layers[currentLayer].dataProvider().dataSourceUri()
                
                # encoding을 지정해 주지 않으면 .bat 파일을 실행 할 때 한글이 깨져보임.
                file = codecs.open(self.pathList['BAT_FILE'], "w", encoding="CP949")
                file.write(f'PATH="{self.qgisPath}/apps/qgis/bin;{self.qgisPath}/bin;"\r\n')
                file.write('"{}" io_gdal 0 -TRANSFORM 1 -RESAMPLING 0 -GRIDS "{}" -FILES "{}"\r\n'
                           .format(self.pathList["SAGA_CMD"], self.pathList["SGRD_FILE"], layerPath))
                file.write('"{}" shapes_grid "Grid Values to Points" -GRIDS "{}" -NODATA true -TYPE 1 -SHAPES "{}"'
                           .format(self.pathList["SAGA_CMD"], self.pathList["SGRD_FILE"], self.pathList["SHP_FILE"]))
                file.close()
              
                ret = call(self.pathList["BAT_FILE"])
                
                if self.isShapeLayer():
                    self.qgis_project.removeMapLayer(self.layers[SHP_LAYER])
               
                if ret==0:
                    layerList = self.canvas.layers()
                    if layerList!=[]:
                        self.iface.setActiveLayer(layerList[0])
                    self.layers[SHP_LAYER] = self.iface.addVectorLayer(self.pathList["SHP_FILE"], '', "ogr")
                    self.layers[SHP_LAYER].loadNamedStyle(self.pathList["STYLE_FILE"])
                    self.layers[SHP_LAYER].setName(currentLayer)
                    self.layerId[self.layers[SHP_LAYER].id()] = SHP_LAYER
                    self.uc.bar_info("Completed shape layer creation.")
                    
                self.currentLayer = currentLayer
            
            self.btn_save.setDisabled(currentFlag)
            self.btn_saveAs.setDisabled(currentFlag)
                
        except Exception as e:
            self.uc.bar_warn(str(e))
    
    def changeValueAction(self, type):
        flag = []
        flagAppend = flag.append
        layer = self.layers[SHP_LAYER]
        features = layer.selectedFeatures()
        changeAttr = layer.dataProvider().changeAttributeValues
        fieldName = 'temp'

        value = self.spb_batch.value()
        oper = self.txt_inDecrease.text()
        
        # 선택한 셀 만큼
        for feature in features:            
            if type: # 일괄 적용
                result = value
            else: # 증감 적용
                fieldContent = str(feature[fieldName])
                result = eval(fieldContent+oper)
            
            flagAppend(changeAttr({feature.id() : {3: float(result)}}))
            
        if False not in flag:
            layer.commitChanges()
            layer.triggerRepaint()
        else:
            self.uc.bar_warn("Failed to convert value.")
 
    def resultSave(self, type):
        try:
            if self.pathList['SAVE_PATH']=='' or type=="Save as":
                path = QFileDialog.getSaveFileName(None, "Save result files", 'C://', "Tif (*.tif )")[0]
                
                if path=='':
                    return
                    
                self.saveLayer = None
                self.pathList['SAVE_PATH'] = path
            
            fileName = os.path.split(self.pathList['SAVE_PATH'])[1][:-4]
            file = open(self.pathList['SGRD_FILE'], "r")
            sgrdList = file.readlines()
            
            valueList = ['CELLCOUNT_X', 'CELLCOUNT_Y', 'CELLSIZE', 'NODATA_VALUE', 'POSITION_XMIN', 'POSITION_YMIN']
            X, Y, cellSize, noValue, positionX, positionY = self.fileFilter(valueList, sgrdList)
            
            minX = str(float(positionX)-(float(cellSize)/2))
            minY = str(float(positionY)-(float(cellSize)/2))
            maxX = str(float(minX)+(float(cellSize)*float(X)))
            maxY = str(float(minY)+(float(cellSize)*float(Y)))
            
            file.close()
    
            # -co DECIMAL_PRECISION=4 소수점 자리 조정 | ts X Y : tr 대신 사용가능
            convertTIF = ('"{}" gdal_rasterize -a "temp" -tr {} {} -te {} {} {} {} -a_nodata {} "{}" "{}"'
                          .format(self.pathList['OSGEO_BAT'], cellSize, cellSize, 
                                  minX, minY, maxX, maxY, noValue, self.pathList['SHP_FILE'], self.pathList['SAVE_PATH']))
            

            ret = call(convertTIF)
            
            if ret==0 and self.isShapeLayer():
                self.uc.bar_info("Saving completed.")
                
                if self.saveLayer!=None:
                    self.saveLayer.dataProvider().setEditable(True)
                    self.saveLayer.dataProvider().setEditable(False)
                    self.saveLayer.triggerRepaint()

                else:
                    layerList = self.canvas.layers()
                    if len(layerList)>1:
                        self.iface.setActiveLayer(layerList[1])
                    self.saveLayer = self.iface.addRasterLayer(self.pathList['SAVE_PATH'], fileName, "gdal")
                    self.iface.setActiveLayer(self.layers[SHP_LAYER])
                
                    lastCount = self.cmb_layer.count()-1
                    self.currentLayer = self.saveLayer.name()
                    self.cmb_layer.setCurrentIndex(lastCount)
                    self.layers[SHP_LAYER].setName(self.currentLayer)
                
        except Exception as e:
            self.uc.bar_warn(str(e))

    def refreshEvent(self):
        self.currentLayer = ''
        currentLayer = self.cmb_layer.currentText()
         
        self.selectLayerConvert(currentLayer)
     
    
#--- Other           
    def fileFilter(self, txtList, sgrdList):
        value = []
        for txt in txtList:
            value.append(list(filter(lambda x: txt in x, sgrdList))[0].split('=')[1].replace("\n","").strip())
            
        return value
    
    def isShapeLayer(self):
        return SHP_LAYER in self.layers.keys()