"""
Group Selector Dialog - Dialog for selecting an existing group from timeline to add materials
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, 
    QListWidgetItem, QPushButton, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt
from typing import Optional

from .theme import AppTheme as _T


class GroupSelectorDialog(QDialog):
    """Dialog for selecting an existing group from the current timeline"""
    
    def __init__(self, layer_editor, group_manager, current_track_index, parent=None):
        super().__init__(parent)
        
        self.layer_editor = layer_editor
        self.group_manager = group_manager
        self.current_track_index = current_track_index
        self.selected_group_index = None
        self.selected_frame_index = None
        
        self.setWindowTitle("Select Group")
        self.resize(500, 400)
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        label = QLabel("Select a group from the current timeline to add materials:")
        label.setWordWrap(True)
        layout.addWidget(label)
        
        # Group list
        self.group_list = QListWidget()
        self.group_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.group_list.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.group_list)
        
        # Populate list with groups from current timeline
        self.populate_groups()
        
        # Info label
        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {_T.TEXT_HINT}; font-style: italic;")
        layout.addWidget(self.info_label)
        
        if self.group_list.count() == 0:
            self.info_label.setText("No groups found in current timeline. Please add materials as a new group first.")
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setEnabled(self.group_list.count() > 0)
        button_layout.addWidget(self.ok_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def populate_groups(self):
        """Populate list with groups from current timeline track"""
        track = self.layer_editor.get_layer_track(self.current_track_index)
        if not track:
            return
        
        # Find all unique groups in this track
        seen_groups = set()
        for frame_idx, frame in enumerate(track.frames):
            if frame.group_index is not None and frame.group_index not in seen_groups:
                seen_groups.add(frame.group_index)
                group = self.group_manager.get_group(frame.group_index)
                if group:
                    text = (f"[G{frame.group_index}] {group.name} "
                           f"({len(group.entries)} entries) at frame #{frame_idx + 1}")
                    
                    item = QListWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole, frame.group_index)
                    item.setData(Qt.ItemDataRole.UserRole + 1, frame_idx)
                    self.group_list.addItem(item)
    
    def accept(self):
        """Accept the dialog and store selected group index"""
        selected_items = self.group_list.selectedItems()
        if selected_items:
            self.selected_group_index = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self.selected_frame_index = selected_items[0].data(Qt.ItemDataRole.UserRole + 1)
            super().accept()
        elif self.group_list.count() == 0:
            QMessageBox.warning(self, "No Groups", "No groups available in current timeline.")
        else:
            QMessageBox.warning(self, "No Selection", "Please select a group.")
    
    def get_selected_group_index(self) -> Optional[int]:
        """Get the selected group index"""
        return self.selected_group_index
    
    def get_selected_frame_index(self) -> Optional[int]:
        """Get the frame index where the selected group is located"""
        return self.selected_frame_index

