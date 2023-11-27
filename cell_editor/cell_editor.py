import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QCheckBox

from .multi_cell_edit import MultiCellEdit
from .serval import Serval

class Intergrated:  
        
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.toolbar = self.iface.addToolBar(u'CellEditor')
        self.toolbar.setObjectName(u'CellEditor')
        self.plugin_dir = os.path.dirname(__file__)
        self.menu = u'CellEditor'
        
        self.multiCell = MultiCellEdit(iface)
        self.cellEdit = Serval(iface)
        
    def initGui(self):
        self.add_action(
            'Multi cell value.png',  # icon
            text=u'Show CellEditor tool bar',                  # 아이콘 text
            add_to_menu=True,                                       # 메뉴 추가 여부
            add_to_toolbar=False,                                   # 툴바 추가 여부
            callback=self.show_toolbar,                             # connection
            parent=self.iface.mainWindow())                         # 부모 객체
        
        self.chk_multiCell = QCheckBox()
        self.chk_cellEdit = QCheckBox()
        
        self.chk_multiCell.setText("Multi cell edit")
        self.chk_cellEdit.setText("Cell value edit")
        
        cellAction = self.toolbar.addWidget(self.chk_cellEdit)
        multiCellAction = self.toolbar.addWidget(self.chk_multiCell)
        self.actions += [cellAction, multiCellAction]
        
        self.multiCell.initGui()
        self.multiTool = self.multiCell.toolbar
        self.checked("Multi cell")
        
        self.cellEdit.initGui()
        self.cellTool = self.cellEdit.toolbar
        self.chk_cellEdit.setChecked(False)
        self.checked("Cell value")

        self.chk_multiCell.stateChanged.connect(lambda: self.checked("Multi cell"))
        self.chk_cellEdit.stateChanged.connect(lambda: self.checked("Cell value"))
    
    def checked(self, target):
        if target=="Multi cell":
            checkState = self.chk_multiCell.isChecked()
            targetTool = self.multiTool
        else:
            checkState = self.chk_cellEdit.isChecked()
            targetTool = self.cellTool
        
        targetTool.setVisible(checkState)
        
    
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
        self.chk_multiCell.setChecked(False)
        self.multiCell.unload()
        self.cellEdit.unload()
            
        for action in self.actions:
            self.iface.removePluginMenu(
                u'CellEditor',
                action)
            self.iface.removeToolBarIcon(action)
    
        del self.toolbar
            
        
    def show_toolbar(self):
        if self.toolbar:
            self.toolbar.show()
