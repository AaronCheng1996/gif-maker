"""
Material Selector Dialog - Dialog for selecting materials to add as layers
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
    QListWidgetItem, QPushButton, QLabel
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QImage
from PIL import Image


class MaterialSelectorDialog(QDialog):
    """Dialog for selecting a material from the material manager"""
    
    def __init__(self, material_manager, parent=None):
        super().__init__(parent)
        
        self.material_manager = material_manager
        self.selected_material_index = None
        
        self.setWindowTitle("Select Material")
        self.resize(400, 500)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        label = QLabel("Select a material to add as a layer:")
        layout.addWidget(label)
        
        # Material list
        self.material_list = QListWidget()
        self.material_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.material_list.setIconSize(QSize(64, 64))
        self.material_list.setViewMode(QListWidget.ViewMode.ListMode)
        self.material_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.material_list)
        
        # Populate list
        for i, (img, name) in enumerate(self.material_manager.get_all_materials()):
            thumbnail = self.create_thumbnail(img, 64, 64)
            icon_pixmap = thumbnail
            
            item = QListWidgetItem(f"[{i}] {name} ({img.width}x{img.height})")
            item.setData(Qt.ItemDataRole.DecorationRole, icon_pixmap)
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setSizeHint(QSize(200, 70))
            self.material_list.addItem(item)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def create_thumbnail(self, pil_image: Image.Image, width: int, height: int) -> QPixmap:
        """Create a thumbnail from PIL image"""
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
    def accept(self):
        """Accept the dialog and store selected material index"""
        selected_items = self.material_list.selectedItems()
        if selected_items:
            self.selected_material_index = selected_items[0].data(Qt.ItemDataRole.UserRole)
        super().accept()
    
    def get_selected_material_index(self):
        """Get the selected material index"""
        return self.selected_material_index

