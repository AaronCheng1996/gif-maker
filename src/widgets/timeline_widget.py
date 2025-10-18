from PyQt6.QtWidgets import (QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QSpinBox, QHeaderView)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from typing import List, Tuple, Optional


class TimelineWidget(QWidget):
    
    sequence_changed = pyqtSignal()
    frame_selected = pyqtSignal(int)
    apply_duration_requested = pyqtSignal(int, bool)  # (duration, apply_to_all)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.material_manager = None
        self.is_main_timebase = True
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("Timeline (Frame Sequence)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        self.timeline_table = QTableWidget()
        self.timeline_table.setColumnCount(4)
        self.timeline_table.setHorizontalHeaderLabels(["#", "Preview", "Material", "Duration (ms)"])
        
        header = self.timeline_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        
        self.timeline_table.setColumnWidth(0, 40)
        self.timeline_table.setColumnWidth(1, 80)
        self.timeline_table.setColumnWidth(3, 100)
        
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.timeline_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        # Disable drag-drop for now - use Move Up/Down buttons instead
        # self.timeline_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        # self.timeline_table.setDragDropOverwriteMode(False)
        
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setIconSize(QSize(64, 64))
        
        self.timeline_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.timeline_table.model().rowsMoved.connect(self.on_rows_moved)
        
        layout.addWidget(self.timeline_table)
        
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Frame Duration (ms):"))
        
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(10)
        self.duration_spinbox.setMaximum(10000)
        self.duration_spinbox.setValue(100)
        self.duration_spinbox.setSingleStep(10)
        duration_layout.addWidget(self.duration_spinbox)
        
        self.apply_duration_button = QPushButton("Apply to Selected")
        self.apply_duration_button.clicked.connect(self.apply_duration_to_selected)
        duration_layout.addWidget(self.apply_duration_button)
        
        self.apply_all_duration_button = QPushButton("Apply to All")
        self.apply_all_duration_button.clicked.connect(self.apply_duration_to_all)
        duration_layout.addWidget(self.apply_all_duration_button)
        
        layout.addLayout(duration_layout)
        
        control_layout = QHBoxLayout()
        
        self.setLayout(layout)
    
    def set_material_manager(self, material_manager):
        self.material_manager = material_manager
    
    def set_is_main_timebase(self, is_main: bool):
        """Enable/disable duration editing controls depending on whether this is the main timeline."""
        self.is_main_timebase = is_main
        enabled = bool(is_main)
        self.duration_spinbox.setEnabled(enabled)
        self.apply_duration_button.setEnabled(enabled)
        self.apply_all_duration_button.setEnabled(enabled)
    
    def create_thumbnail(self, pil_image, width, height):
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
    def apply_duration_to_selected(self):
        """Request applying duration to selected frames"""
        if not self.is_main_timebase:
            return
        duration = self.duration_spinbox.value()
        self.apply_duration_requested.emit(duration, False)
    
    def apply_duration_to_all(self):
        """Request applying duration to all frames"""
        if not self.is_main_timebase:
            return
        duration = self.duration_spinbox.value()
        self.apply_duration_requested.emit(duration, True)
    
    def on_selection_changed(self):
        selected_rows = set([index.row() for index in self.timeline_table.selectedIndexes()])
        if selected_rows:
            self.frame_selected.emit(min(selected_rows))
    
    def on_rows_moved(self, parent, start, end, destination, row):
        """Handle row reordering - Timeline doesn't manage frames anymore, just notify"""
        # Emit signal to tell main.py that the user reordered rows
        # main.py will handle updating layered_sequence_editor based on current table order
        self.sequence_changed.emit()
