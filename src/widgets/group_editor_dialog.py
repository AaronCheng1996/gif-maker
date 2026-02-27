"""
Group Editor Dialog - Dialog for creating and editing MaterialGroups
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QGroupBox, QFormLayout, QCheckBox
)
from PyQt6.QtCore import Qt
from typing import List, Optional

from ..core.material_group import MaterialGroup
from .theme import AppTheme as _T


class GroupEditorDialog(QDialog):
    """
    Dialog for creating or editing a MaterialGroup
    
    Allows user to set:
    - Group name
    - Frame duration (ms)
    - Loop count
    Displays preview information about total frames and duration
    """
    
    def __init__(self, parent=None, material_indices: List[int] = None, existing_group: MaterialGroup = None):
        super().__init__(parent)
        
        self.material_indices = material_indices or []
        self.existing_group = existing_group
        self.result_group: Optional[MaterialGroup] = None
        
        self.setWindowTitle("Create Material Group" if existing_group is None else "Edit Material Group")
        self.setMinimumWidth(400)
        
        self.init_ui()
        
        # Load existing group data if editing
        if existing_group:
            self.load_group_data(existing_group)
    
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Info section
        info_label = QLabel(f"Creating a group from {len(self.material_indices)} material(s)")
        info_label.setStyleSheet(f"font-weight: bold; color: {_T.TEXT};")
        layout.addWidget(info_label)
        
        # Form section
        form_group = QGroupBox("Group Settings")
        form_layout = QFormLayout()
        
        # Name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter group name...")
        self.name_input.setText(f"Group_{len(self.material_indices)}")
        form_layout.addRow("Name:", self.name_input)
        
        # Frame duration
        self.duration_spinbox = QSpinBox()
        self.duration_spinbox.setMinimum(10)
        self.duration_spinbox.setMaximum(10000)
        self.duration_spinbox.setValue(100)
        self.duration_spinbox.setSuffix(" ms")
        self.duration_spinbox.valueChanged.connect(self.update_preview)
        form_layout.addRow("Frame Duration:", self.duration_spinbox)
        
        # Loop count
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setMinimum(1)
        self.loop_spinbox.setMaximum(100)
        self.loop_spinbox.setValue(1)
        self.loop_spinbox.valueChanged.connect(self.update_preview)
        form_layout.addRow("Loop Count:", self.loop_spinbox)
        
        # Independent offsets mode
        self.independent_mode_checkbox = QCheckBox("Independent Offsets (每個素材可獨立調整)")
        self.independent_mode_checkbox.setToolTip(
            "啟用後，使用對齊功能時每個素材會獨立調整位置\n"
            "停用時（預設），整個 group 作為一個整體移動"
        )
        form_layout.addRow("", self.independent_mode_checkbox)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Preview section
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            f"padding: 10px; background-color: {_T.CARD}; border: 1px solid {_T.BORDER}; "
            f"border-radius: 4px; color: {_T.TEXT_DIM};"
        )
        preview_layout.addWidget(self.preview_label)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        # Update initial preview
        self.update_preview()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.ok_button = QPushButton("OK")
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setDefault(True)
        button_layout.addWidget(self.ok_button)
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_group_data(self, group: MaterialGroup):
        """Load data from an existing group for editing"""
        self.name_input.setText(group.name)
        self.duration_spinbox.setValue(group.frame_duration)
        self.loop_spinbox.setValue(group.loop_count)
        self.independent_mode_checkbox.setChecked(group.independent_offsets)
        self.material_indices = group.material_indices.copy()
        self.update_preview()
    
    def update_preview(self):
        """Update the preview display with calculated values"""
        materials_count = len(self.material_indices)
        duration = self.duration_spinbox.value()
        loops = self.loop_spinbox.value()
        
        total_frames = materials_count * loops
        total_duration = total_frames * duration
        
        preview_text = (
            f"<b>Materials:</b> {materials_count}<br>"
            f"<b>Loop Count:</b> {loops}<br>"
            f"<b>Total Frames:</b> {total_frames}<br>"
            f"<b>Total Duration:</b> {total_duration} ms ({total_duration/1000:.2f}s)"
        )
        
        self.preview_label.setText(preview_text)
    
    def accept(self):
        """Create the result group and close dialog"""
        name = self.name_input.text().strip()
        if not name:
            name = f"Group_{len(self.material_indices)}"
        
        self.result_group = MaterialGroup(
            material_indices=self.material_indices.copy(),
            frame_duration=self.duration_spinbox.value(),
            loop_count=self.loop_spinbox.value(),
            name=name,
            independent_offsets=self.independent_mode_checkbox.isChecked()
        )
        
        super().accept()
    
    def get_group(self) -> Optional[MaterialGroup]:
        """Get the created/edited group (None if dialog was cancelled)"""
        return self.result_group

