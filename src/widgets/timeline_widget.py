from PyQt6.QtWidgets import (QWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QLabel, QSpinBox, QHeaderView, QMenu)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage, QFont
from PIL import Image
from typing import List, Tuple, Optional, Set


class TimelineWidget(QWidget):
    
    sequence_changed = pyqtSignal()
    frame_selected = pyqtSignal(int)
    apply_duration_requested = pyqtSignal(int, bool)  # (duration, apply_to_all)
    edit_group_requested = pyqtSignal(int)  # group_index
    remove_group_requested = pyqtSignal(int)  # frame_index
    duplicate_group_requested = pyqtSignal(int)  # frame_index
    remove_material_from_group_requested = pyqtSignal(int, object)  # (group_index, material_indices: int or list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.material_manager = None
        self.group_manager = None
        self.is_main_timebase = True
        
        # Track which groups are expanded (group_index -> bool)
        self.expanded_groups: Set[int] = set()
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        title_label = QLabel("Timeline (Frame Sequence)")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)
        
        self.timeline_table = QTableWidget()
        self.timeline_table.setColumnCount(4)
        self.timeline_table.setHorizontalHeaderLabels(["#", "Preview", "Group/Material", "Duration (ms)"])
        
        header = self.timeline_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        
        self.timeline_table.setColumnWidth(0, 50)
        self.timeline_table.setColumnWidth(1, 80)
        self.timeline_table.setColumnWidth(3, 100)
        
        self.timeline_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.timeline_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setIconSize(QSize(64, 64))
        
        # Enable context menu
        self.timeline_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.timeline_table.customContextMenuRequested.connect(self.show_context_menu)
        
        self.timeline_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.timeline_table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        
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
        
        self.setLayout(layout)
    
    def set_material_manager(self, material_manager):
        self.material_manager = material_manager
    
    def set_group_manager(self, group_manager):
        self.group_manager = group_manager
    
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
    
    def toggle_group_expansion(self, group_index: int):
        """Toggle expansion state of a group"""
        if group_index in self.expanded_groups:
            self.expanded_groups.remove(group_index)
        else:
            self.expanded_groups.add(group_index)
        
        # Emit signal to trigger refresh
        self.sequence_changed.emit()
    
    def remove_material_from_group(self, group_index: int, material_indices):
        """Remove material(s) from a group
        
        Args:
            group_index: Index of the group
            material_indices: Single material index (int) or list of material indices (list)
        """
        self.remove_material_from_group_requested.emit(group_index, material_indices)
    
    def on_cell_double_clicked(self, row: int, column: int):
        """Handle double-click on timeline cell"""
        item = self.timeline_table.item(row, 0)
        if not item:
            return
        
        row_type = item.data(Qt.ItemDataRole.UserRole)  # 'group' or 'material'
        
        if row_type == 'group':
            group_index = item.data(Qt.ItemDataRole.UserRole + 1)
            if group_index is not None:
                self.toggle_group_expansion(group_index)
    
    def show_context_menu(self, pos):
        """Show context menu for timeline items"""
        item = self.timeline_table.itemAt(pos)
        if not item:
            return
        
        row = item.row()
        row_item = self.timeline_table.item(row, 0)
        if not row_item:
            return
        
        row_type = row_item.data(Qt.ItemDataRole.UserRole)
        
        if row_type == 'group':
            group_index = row_item.data(Qt.ItemDataRole.UserRole + 1)
            frame_index = row_item.data(Qt.ItemDataRole.UserRole + 2)
            
            menu = QMenu(self)
            
            # Toggle expansion
            if group_index in self.expanded_groups:
                expand_action = menu.addAction("▼ Collapse")
            else:
                expand_action = menu.addAction("▶ Expand")
            expand_action.triggered.connect(lambda: self.toggle_group_expansion(group_index))
            
            menu.addSeparator()
            
            # Edit group
            edit_action = menu.addAction("✏ Edit Group")
            edit_action.triggered.connect(lambda: self.edit_group_requested.emit(group_index))
            
            # Duplicate group
            duplicate_action = menu.addAction("📋 Duplicate Group")
            duplicate_action.triggered.connect(lambda: self.duplicate_group_requested.emit(frame_index))
            
            menu.addSeparator()
            
            # Remove group
            remove_action = menu.addAction("🗑 Remove Group")
            remove_action.triggered.connect(lambda: self.remove_group_requested.emit(frame_index))
            
            menu.exec(self.timeline_table.viewport().mapToGlobal(pos))
        
        elif row_type == 'material':
            # Material child row - show remove from group option
            # Collect all selected material rows from the same group
            selected_materials = []
            group_index = None
            
            selected_rows = self.timeline_table.selectedIndexes()
            selected_row_numbers = set([idx.row() for idx in selected_rows])
            
            for row_num in selected_row_numbers:
                item = self.timeline_table.item(row_num, 0)
                if item:
                    item_type = item.data(Qt.ItemDataRole.UserRole)
                    if item_type == 'material':
                        item_group_index = item.data(Qt.ItemDataRole.UserRole + 1)
                        item_material_index = item.data(Qt.ItemDataRole.UserRole + 2)
                        
                        # Set group_index from first material row
                        if group_index is None:
                            group_index = item_group_index
                        
                        # Only include materials from the same group
                        if item_group_index == group_index:
                            selected_materials.append(item_material_index)
            
            if not selected_materials or group_index is None:
                return
            
            menu = QMenu(self)
            
            # Remove material(s) from group
            if len(selected_materials) == 1:
                remove_action = menu.addAction("🗑 Remove from Group")
            else:
                remove_action = menu.addAction(f"🗑 Remove {len(selected_materials)} Materials from Group")
            
            remove_action.triggered.connect(
                lambda: self.remove_material_from_group(group_index, selected_materials)
            )
            
            menu.exec(self.timeline_table.viewport().mapToGlobal(pos))
    
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
            # Get the actual frame index from the first selected row
            min_row = min(selected_rows)
            item = self.timeline_table.item(min_row, 0)
            if item:
                frame_index = item.data(Qt.ItemDataRole.UserRole + 2)
                if frame_index is not None:
                    self.frame_selected.emit(frame_index)
