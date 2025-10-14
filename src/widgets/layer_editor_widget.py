"""
Layer Editor Widget - UI for editing layers in a frame
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QSpinBox, QDoubleSpinBox,
    QGroupBox, QCheckBox, QLineEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from typing import Optional, List

from ..core.layer_system import Layer, LayeredFrame
from .material_selector_dialog import MaterialSelectorDialog


class LayerEditorWidget(QWidget):
    """
    Widget for editing layers in a frame
    Allows adding, removing, reordering layers and adjusting their properties
    """
    
    layers_changed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.current_frame: Optional[LayeredFrame] = None
        self.material_manager = None
        self.selected_layer_index: Optional[int] = None
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Title
        title = QLabel("Layer Editor")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)
        
        # Layer list
        list_label = QLabel("Layers (bottom to top)")
        layout.addWidget(list_label)
        
        self.layer_list = QTableWidget()
        self.layer_list.setColumnCount(3)
        self.layer_list.setHorizontalHeaderLabels(["#", "Preview", "Layer"])
        
        header = self.layer_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        
        self.layer_list.setColumnWidth(0, 30)
        self.layer_list.setColumnWidth(1, 60)
        
        self.layer_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.layer_list.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.layer_list.setIconSize(QSize(48, 48))
        self.layer_list.verticalHeader().setVisible(False)
        
        self.layer_list.itemSelectionChanged.connect(self.on_layer_selected)
        layout.addWidget(self.layer_list)
        
        # Layer controls
        controls_layout = QHBoxLayout()
        
        self.add_layer_btn = QPushButton("Add Layer")
        self.add_layer_btn.clicked.connect(self.add_layer)
        controls_layout.addWidget(self.add_layer_btn)
        
        self.remove_layer_btn = QPushButton("Remove")
        self.remove_layer_btn.clicked.connect(self.remove_layer)
        controls_layout.addWidget(self.remove_layer_btn)
        
        self.move_up_btn = QPushButton("▲")
        self.move_up_btn.clicked.connect(self.move_layer_up)
        self.move_up_btn.setMaximumWidth(40)
        controls_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("▼")
        self.move_down_btn.clicked.connect(self.move_layer_down)
        self.move_down_btn.setMaximumWidth(40)
        controls_layout.addWidget(self.move_down_btn)
        
        layout.addLayout(controls_layout)
        
        # Layer properties group
        props_group = QGroupBox("Layer Properties")
        props_layout = QVBoxLayout()
        
        # Name
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Name:"))
        self.name_input = QLineEdit()
        self.name_input.textChanged.connect(self.on_property_changed)
        name_layout.addWidget(self.name_input)
        props_layout.addLayout(name_layout)
        
        # Position
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        
        pos_layout.addWidget(QLabel("X:"))
        self.x_spinbox = QSpinBox()
        self.x_spinbox.setRange(-4096, 4096)
        self.x_spinbox.valueChanged.connect(self.on_property_changed)
        pos_layout.addWidget(self.x_spinbox)
        
        pos_layout.addWidget(QLabel("Y:"))
        self.y_spinbox = QSpinBox()
        self.y_spinbox.setRange(-4096, 4096)
        self.y_spinbox.valueChanged.connect(self.on_property_changed)
        pos_layout.addWidget(self.y_spinbox)
        
        props_layout.addLayout(pos_layout)
        
        # Crop
        crop_layout = QVBoxLayout()
        crop_enabled_layout = QHBoxLayout()
        self.crop_enabled_checkbox = QCheckBox("Enable Crop")
        self.crop_enabled_checkbox.stateChanged.connect(self.on_crop_enabled_changed)
        crop_enabled_layout.addWidget(self.crop_enabled_checkbox)
        crop_layout.addLayout(crop_enabled_layout)
        
        crop_pos_layout = QHBoxLayout()
        crop_pos_layout.addWidget(QLabel("Crop X:"))
        self.crop_x_spinbox = QSpinBox()
        self.crop_x_spinbox.setRange(0, 4096)
        self.crop_x_spinbox.valueChanged.connect(self.on_property_changed)
        crop_pos_layout.addWidget(self.crop_x_spinbox)
        
        crop_pos_layout.addWidget(QLabel("Y:"))
        self.crop_y_spinbox = QSpinBox()
        self.crop_y_spinbox.setRange(0, 4096)
        self.crop_y_spinbox.valueChanged.connect(self.on_property_changed)
        crop_pos_layout.addWidget(self.crop_y_spinbox)
        crop_layout.addLayout(crop_pos_layout)
        
        crop_size_layout = QHBoxLayout()
        crop_size_layout.addWidget(QLabel("Width:"))
        self.crop_width_spinbox = QSpinBox()
        self.crop_width_spinbox.setRange(1, 4096)
        self.crop_width_spinbox.valueChanged.connect(self.on_property_changed)
        crop_size_layout.addWidget(self.crop_width_spinbox)
        
        crop_size_layout.addWidget(QLabel("Height:"))
        self.crop_height_spinbox = QSpinBox()
        self.crop_height_spinbox.setRange(1, 4096)
        self.crop_height_spinbox.valueChanged.connect(self.on_property_changed)
        crop_size_layout.addWidget(self.crop_height_spinbox)
        crop_layout.addLayout(crop_size_layout)
        
        props_layout.addLayout(crop_layout)
        
        # Scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.01, 10.0)
        self.scale_spinbox.setSingleStep(0.1)
        self.scale_spinbox.setValue(1.0)
        self.scale_spinbox.valueChanged.connect(self.on_property_changed)
        scale_layout.addWidget(self.scale_spinbox)
        props_layout.addLayout(scale_layout)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        self.opacity_spinbox = QDoubleSpinBox()
        self.opacity_spinbox.setRange(0.0, 1.0)
        self.opacity_spinbox.setSingleStep(0.1)
        self.opacity_spinbox.setValue(1.0)
        self.opacity_spinbox.valueChanged.connect(self.on_property_changed)
        opacity_layout.addWidget(self.opacity_spinbox)
        props_layout.addLayout(opacity_layout)
        
        # Visible
        self.visible_checkbox = QCheckBox("Visible")
        self.visible_checkbox.setChecked(True)
        self.visible_checkbox.stateChanged.connect(self.on_property_changed)
        props_layout.addWidget(self.visible_checkbox)
        
        props_group.setLayout(props_layout)
        layout.addWidget(props_group)
        
        self.setLayout(layout)
        
        # Initially disable property controls
        self.set_property_controls_enabled(False)
    
    def set_material_manager(self, material_manager):
        """Set the material manager"""
        self.material_manager = material_manager
    
    def set_frame(self, frame: Optional[LayeredFrame]):
        """Set the frame to edit"""
        self.current_frame = frame
        self.refresh_layer_list()
    
    def get_frame(self) -> Optional[LayeredFrame]:
        """Get the current frame"""
        return self.current_frame
    
    def refresh_layer_list(self):
        """Refresh the layer list display"""
        self.layer_list.setRowCount(0)
        
        if not self.current_frame:
            return
        
        for i, layer in enumerate(self.current_frame.layers):
            self.add_layer_row(i, layer)
    
    def add_layer_row(self, row_index: int, layer: Layer):
        """Add a row to the layer table"""
        self.layer_list.insertRow(row_index)
        
        # Index
        index_item = QTableWidgetItem(str(row_index))
        index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.layer_list.setItem(row_index, 0, index_item)
        
        # Preview
        preview_item = QTableWidgetItem()
        if self.material_manager and layer.material_index < len(self.material_manager):
            material = self.material_manager.get_material(layer.material_index)
            if material:
                img, _ = material
                thumbnail = self.create_thumbnail(img, 48, 48)
                preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.layer_list.setItem(row_index, 1, preview_item)
        
        # Layer info
        visible_text = "✓" if layer.visible else "✗"
        layer_text = f"{visible_text} {layer.name}"
        layer_item = QTableWidgetItem(layer_text)
        layer_item.setFlags(layer_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.layer_list.setItem(row_index, 2, layer_item)
        
        self.layer_list.setRowHeight(row_index, 54)
    
    def create_thumbnail(self, pil_image: Image.Image, width: int, height: int) -> QPixmap:
        """Create a thumbnail from PIL image"""
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
    def add_layer(self):
        """Add a new layer from selected material"""
        if not self.current_frame:
            QMessageBox.warning(self, "Warning", "No frame is being edited!")
            return
        
        if not self.material_manager or len(self.material_manager) == 0:
            QMessageBox.warning(self, "Warning", "No materials available!")
            return
        
        # Show material selector dialog
        dialog = MaterialSelectorDialog(self.material_manager, self)
        if dialog.exec():
            material_index = dialog.get_selected_material_index()
            if material_index is not None:
                new_layer = Layer(material_index=material_index, name=f"Layer {len(self.current_frame) + 1}")
                self.current_frame.add_layer(new_layer)
                self.refresh_layer_list()
                self.layers_changed.emit()
    
    def remove_layer(self):
        """Remove the selected layer"""
        if not self.current_frame or self.selected_layer_index is None:
            return
        
        self.current_frame.remove_layer(self.selected_layer_index)
        self.selected_layer_index = None
        self.refresh_layer_list()
        self.set_property_controls_enabled(False)
        self.layers_changed.emit()
    
    def move_layer_up(self):
        """Move selected layer up (increase z-index)"""
        if not self.current_frame or self.selected_layer_index is None:
            return
        
        if self.selected_layer_index < len(self.current_frame.layers) - 1:
            self.current_frame.move_layer(self.selected_layer_index, self.selected_layer_index + 1)
            self.selected_layer_index += 1
            self.refresh_layer_list()
            self.layer_list.selectRow(self.selected_layer_index)
            self.layers_changed.emit()
    
    def move_layer_down(self):
        """Move selected layer down (decrease z-index)"""
        if not self.current_frame or self.selected_layer_index is None:
            return
        
        if self.selected_layer_index > 0:
            self.current_frame.move_layer(self.selected_layer_index, self.selected_layer_index - 1)
            self.selected_layer_index -= 1
            self.refresh_layer_list()
            self.layer_list.selectRow(self.selected_layer_index)
            self.layers_changed.emit()
    
    def on_layer_selected(self):
        """Handle layer selection"""
        selected_rows = self.layer_list.selectedIndexes()
        
        if not selected_rows:
            self.selected_layer_index = None
            self.set_property_controls_enabled(False)
            return
        
        row = selected_rows[0].row()
        self.selected_layer_index = row
        
        if self.current_frame and 0 <= row < len(self.current_frame.layers):
            layer = self.current_frame.layers[row]
            self.load_layer_properties(layer)
            self.set_property_controls_enabled(True)
    
    def load_layer_properties(self, layer: Layer):
        """Load layer properties into controls"""
        # Block signals to avoid triggering on_property_changed
        self.name_input.blockSignals(True)
        self.x_spinbox.blockSignals(True)
        self.y_spinbox.blockSignals(True)
        self.crop_enabled_checkbox.blockSignals(True)
        self.crop_x_spinbox.blockSignals(True)
        self.crop_y_spinbox.blockSignals(True)
        self.crop_width_spinbox.blockSignals(True)
        self.crop_height_spinbox.blockSignals(True)
        self.scale_spinbox.blockSignals(True)
        self.opacity_spinbox.blockSignals(True)
        self.visible_checkbox.blockSignals(True)
        
        self.name_input.setText(layer.name)
        self.x_spinbox.setValue(layer.x)
        self.y_spinbox.setValue(layer.y)
        
        # Crop
        crop_enabled = layer.crop_width is not None and layer.crop_height is not None
        self.crop_enabled_checkbox.setChecked(crop_enabled)
        self.crop_x_spinbox.setValue(layer.crop_x)
        self.crop_y_spinbox.setValue(layer.crop_y)
        self.crop_width_spinbox.setValue(layer.crop_width or 100)
        self.crop_height_spinbox.setValue(layer.crop_height or 100)
        
        self.crop_x_spinbox.setEnabled(crop_enabled)
        self.crop_y_spinbox.setEnabled(crop_enabled)
        self.crop_width_spinbox.setEnabled(crop_enabled)
        self.crop_height_spinbox.setEnabled(crop_enabled)
        
        self.scale_spinbox.setValue(layer.scale)
        self.opacity_spinbox.setValue(layer.opacity)
        self.visible_checkbox.setChecked(layer.visible)
        
        # Unblock signals
        self.name_input.blockSignals(False)
        self.x_spinbox.blockSignals(False)
        self.y_spinbox.blockSignals(False)
        self.crop_enabled_checkbox.blockSignals(False)
        self.crop_x_spinbox.blockSignals(False)
        self.crop_y_spinbox.blockSignals(False)
        self.crop_width_spinbox.blockSignals(False)
        self.crop_height_spinbox.blockSignals(False)
        self.scale_spinbox.blockSignals(False)
        self.opacity_spinbox.blockSignals(False)
        self.visible_checkbox.blockSignals(False)
    
    def on_crop_enabled_changed(self):
        """Handle crop enabled checkbox change"""
        enabled = self.crop_enabled_checkbox.isChecked()
        self.crop_x_spinbox.setEnabled(enabled)
        self.crop_y_spinbox.setEnabled(enabled)
        self.crop_width_spinbox.setEnabled(enabled)
        self.crop_height_spinbox.setEnabled(enabled)
        self.on_property_changed()
    
    def on_property_changed(self):
        """Handle property change"""
        if not self.current_frame or self.selected_layer_index is None:
            return
        
        layer = self.current_frame.get_layer(self.selected_layer_index)
        if not layer:
            return
        
        layer.name = self.name_input.text()
        layer.x = self.x_spinbox.value()
        layer.y = self.y_spinbox.value()
        
        # Crop
        if self.crop_enabled_checkbox.isChecked():
            layer.crop_x = self.crop_x_spinbox.value()
            layer.crop_y = self.crop_y_spinbox.value()
            layer.crop_width = self.crop_width_spinbox.value()
            layer.crop_height = self.crop_height_spinbox.value()
        else:
            layer.crop_width = None
            layer.crop_height = None
        
        layer.scale = self.scale_spinbox.value()
        layer.opacity = self.opacity_spinbox.value()
        layer.visible = self.visible_checkbox.isChecked()
        
        # Refresh the list to show updated info
        if self.selected_layer_index is not None:
            visible_text = "✓" if layer.visible else "✗"
            layer_text = f"{visible_text} {layer.name}"
            self.layer_list.item(self.selected_layer_index, 2).setText(layer_text)
        
        self.layers_changed.emit()
    
    def set_property_controls_enabled(self, enabled: bool):
        """Enable or disable property controls"""
        self.name_input.setEnabled(enabled)
        self.x_spinbox.setEnabled(enabled)
        self.y_spinbox.setEnabled(enabled)
        self.crop_enabled_checkbox.setEnabled(enabled)
        
        crop_enabled = enabled and self.crop_enabled_checkbox.isChecked()
        self.crop_x_spinbox.setEnabled(crop_enabled)
        self.crop_y_spinbox.setEnabled(crop_enabled)
        self.crop_width_spinbox.setEnabled(crop_enabled)
        self.crop_height_spinbox.setEnabled(crop_enabled)
        
        self.scale_spinbox.setEnabled(enabled)
        self.opacity_spinbox.setEnabled(enabled)
        self.visible_checkbox.setEnabled(enabled)

