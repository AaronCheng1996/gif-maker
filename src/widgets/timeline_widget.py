from PyQt6.QtWidgets import (QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QSpinBox, QHeaderView)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage
from PIL import Image
from typing import List, Tuple, Optional


class TimelineWidget(QWidget):
    
    sequence_changed = pyqtSignal()
    frame_selected = pyqtSignal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.frames: List[Tuple[int, int]] = []
        self.material_manager = None
        
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
        self.timeline_table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.timeline_table.setDragDropOverwriteMode(False)
        
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
        
        self.duplicate_button = QPushButton("Duplicate")
        self.duplicate_button.clicked.connect(self.duplicate_selected_frame)
        control_layout.addWidget(self.duplicate_button)
        
        self.remove_button = QPushButton("Remove")
        self.remove_button.clicked.connect(self.remove_selected_frame)
        control_layout.addWidget(self.remove_button)
        
        self.clear_button = QPushButton("Clear All")
        self.clear_button.clicked.connect(self.clear_timeline)
        control_layout.addWidget(self.clear_button)
        
        layout.addLayout(control_layout)
        
        self.info_label = QLabel("Total Frames: 0 | Total Duration: 0ms")
        layout.addWidget(self.info_label)
        
        self.setLayout(layout)
    
    def set_material_manager(self, material_manager):
        self.material_manager = material_manager
    
    def create_thumbnail(self, pil_image, width, height):
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
    def add_frame(self, material_index: int, duration: int = 100):
        self.frames.append((material_index, duration))
        self.add_table_row(len(self.frames) - 1, material_index, duration)
        self.update_info()
        self.sequence_changed.emit()
    
    def add_table_row(self, row_index: int, material_index: int, duration: int):
        self.timeline_table.insertRow(row_index)
        
        index_item = QTableWidgetItem(str(row_index + 1))
        index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.timeline_table.setItem(row_index, 0, index_item)
        
        preview_item = QTableWidgetItem()
        if self.material_manager and material_index < len(self.material_manager):
            material = self.material_manager.get_material(material_index)
            if material:
                img, name = material
                thumbnail = self.create_thumbnail(img, 64, 64)
                preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.timeline_table.setItem(row_index, 1, preview_item)
        
        material_item = QTableWidgetItem(f"Material #{material_index}")
        material_item.setFlags(material_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.timeline_table.setItem(row_index, 2, material_item)
        
        duration_item = QTableWidgetItem(str(duration))
        duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.timeline_table.setItem(row_index, 3, duration_item)
        
        self.timeline_table.setRowHeight(row_index, 70)
    
    def insert_frame(self, position: int, material_index: int, duration: int = 100):
        self.frames.insert(position, (material_index, duration))
        self.refresh_display()
        self.sequence_changed.emit()
    
    def remove_frame(self, position: int):
        if 0 <= position < len(self.frames):
            del self.frames[position]
            self.refresh_display()
            self.sequence_changed.emit()
    
    def remove_selected_frame(self):
        selected_rows = sorted(set([index.row() for index in self.timeline_table.selectedIndexes()]), reverse=True)
        if selected_rows:
            for row in selected_rows:
                if 0 <= row < len(self.frames):
                    del self.frames[row]
            self.refresh_display()
            self.sequence_changed.emit()
    
    def duplicate_selected_frame(self):
        selected_rows = sorted(set([index.row() for index in self.timeline_table.selectedIndexes()]))
        if selected_rows:
            frames_to_duplicate = [(self.frames[row][0], self.frames[row][1]) for row in selected_rows if row < len(self.frames)]
            
            insert_position = selected_rows[-1] + 1
            for material_idx, duration in frames_to_duplicate:
                self.frames.insert(insert_position, (material_idx, duration))
                insert_position += 1
            
            self.refresh_display()
            self.sequence_changed.emit()
    
    def clear_timeline(self):
        self.frames.clear()
        self.timeline_table.setRowCount(0)
        self.update_info()
        self.sequence_changed.emit()
    
    def set_sequence(self, pattern: List[int], duration: int = 100):
        self.clear_timeline()
        for material_idx in pattern:
            self.add_frame(material_idx, duration)
    
    def get_sequence(self) -> List[Tuple[int, int]]:
        return self.frames.copy()
    
    def apply_duration_to_selected(self):
        selected_rows = sorted(set([index.row() for index in self.timeline_table.selectedIndexes()]))
        if selected_rows:
            new_duration = self.duration_spinbox.value()
            for row in selected_rows:
                if 0 <= row < len(self.frames):
                    material_idx, _ = self.frames[row]
                    self.frames[row] = (material_idx, new_duration)
            
            self.refresh_display()
            self.sequence_changed.emit()
    
    def apply_duration_to_all(self):
        new_duration = self.duration_spinbox.value()
        self.frames = [(mat_idx, new_duration) for mat_idx, _ in self.frames]
        
        self.refresh_display()
        self.sequence_changed.emit()
    
    def refresh_display(self):
        self.timeline_table.setRowCount(0)
        
        for i, (material_idx, duration) in enumerate(self.frames):
            self.add_table_row(i, material_idx, duration)
        
        self.update_info()
    
    def update_info(self):
        total_frames = len(self.frames)
        total_duration = sum(duration for _, duration in self.frames)
        self.info_label.setText(f"Total Frames: {total_frames} | Total Duration: {total_duration}ms")
    
    def on_selection_changed(self):
        selected_rows = set([index.row() for index in self.timeline_table.selectedIndexes()])
        if selected_rows:
            self.frame_selected.emit(min(selected_rows))
    
    def on_rows_moved(self, parent, start, end, destination, row):
        new_frames = []
        for i in range(self.timeline_table.rowCount()):
            material_item = self.timeline_table.item(i, 2)
            duration_item = self.timeline_table.item(i, 3)
            
            if material_item and duration_item:
                try:
                    material_text = material_item.text()
                    material_idx = int(material_text.split("#")[1])
                    duration = int(duration_item.text())
                    new_frames.append((material_idx, duration))
                except:
                    pass
        
        if len(new_frames) == len(self.frames):
            self.frames = new_frames
            self.refresh_display()
            self.sequence_changed.emit()
