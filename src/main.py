import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
                              QTableWidgetItem)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image

from .core import MaterialManager, SequenceEditor, GifBuilder, LayeredSequenceEditor, Layer, LayeredFrame
from .widgets import PreviewWidget, TimelineWidget, TileEditorWidget, LayerEditorWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.material_manager = MaterialManager()
        self.layered_sequence_editor = LayeredSequenceEditor()
        self.gif_builder = GifBuilder()
        
        self.init_ui()
        self.setWindowTitle("GIF Maker - Layered Animation Editor")
        self.resize(1600, 950)
    
    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        left_panel = self.create_left_panel()
        
        middle_panel = self.create_middle_panel()
        
        right_panel = self.create_right_panel()
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(middle_panel)
        splitter.addWidget(right_panel)
        # Give more space to middle panel (timeline & layers)
        splitter.setSizes([300, 700, 400])
        
        main_layout.addWidget(splitter)
        
        self.create_menu_bar()
    
    def create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        
        title = QLabel("Materials & Tools")
        title.setStyleSheet("font-weight: bold; font-size: 16px;")
        layout.addWidget(title)
        
        tabs = QTabWidget()
        
        materials_tab = self.create_materials_tab()
        tabs.addTab(materials_tab, "Materials")
        
        self.tile_editor = TileEditorWidget()
        self.tile_editor.tiles_created.connect(self.on_tiles_created)
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.tile_editor)
        scroll_area.setWidgetResizable(True)
        tabs.addTab(scroll_area, "Tile Splitter")
        
        layout.addWidget(tabs)
        
        panel.setLayout(layout)
        return panel
    
    def create_materials_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        load_group = QGroupBox("Load Materials")
        load_layout = QVBoxLayout()
        
        self.load_image_btn = QPushButton("Load Image")
        self.load_image_btn.clicked.connect(self.load_image_material)
        load_layout.addWidget(self.load_image_btn)
        
        self.load_gif_btn = QPushButton("Load GIF (Extract Frames)")
        self.load_gif_btn.clicked.connect(self.load_gif_material)
        load_layout.addWidget(self.load_gif_btn)
        
        self.load_multiple_btn = QPushButton("Load Multiple Images")
        self.load_multiple_btn.clicked.connect(self.load_multiple_materials)
        load_layout.addWidget(self.load_multiple_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        list_label = QLabel("Material Library")
        list_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(list_label)
        
        self.materials_list = QListWidget()
        self.materials_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.materials_list.setIconSize(QSize(64, 64))
        self.materials_list.setViewMode(QListWidget.ViewMode.ListMode)
        layout.addWidget(self.materials_list)
        
        material_actions = QHBoxLayout()
        
        self.add_to_timeline_btn = QPushButton("Add to Timeline")
        self.add_to_timeline_btn.clicked.connect(self.add_selected_to_timeline)
        material_actions.addWidget(self.add_to_timeline_btn)
        
        self.remove_material_btn = QPushButton("Remove")
        self.remove_material_btn.clicked.connect(self.remove_selected_material)
        material_actions.addWidget(self.remove_material_btn)
        
        layout.addLayout(material_actions)
        
        self.clear_materials_btn = QPushButton("Clear All Materials")
        self.clear_materials_btn.clicked.connect(self.clear_materials)
        layout.addWidget(self.clear_materials_btn)
        
        # Export materials section
        export_group = QGroupBox("Export Materials")
        export_layout = QVBoxLayout()
        
        self.export_selected_btn = QPushButton("Export Selected Images")
        self.export_selected_btn.clicked.connect(self.export_selected_materials)
        export_layout.addWidget(self.export_selected_btn)
        
        self.export_all_btn = QPushButton("Export All Images")
        self.export_all_btn.clicked.connect(self.export_all_materials)
        export_layout.addWidget(self.export_all_btn)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_middle_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        
        # Timeline
        self.timeline = TimelineWidget()
        self.timeline.set_material_manager(self.material_manager)
        self.timeline.sequence_changed.connect(self.on_sequence_changed)
        self.timeline.timeline_table.itemSelectionChanged.connect(self.on_timeline_selection_changed)
        self.timeline.apply_duration_requested.connect(self.on_apply_duration)
        layout.addWidget(self.timeline, stretch=2)
        
        # Frame controls (compact)
        frame_controls = QGroupBox("Frame Tools")
        frame_controls_layout = QVBoxLayout()
        frame_controls_layout.setSpacing(3)
        
        # Row 1: Basic operations (more compact buttons)
        btn_row1 = QHBoxLayout()
        self.duplicate_frame_btn = QPushButton("Copy")
        self.duplicate_frame_btn.clicked.connect(self.duplicate_frame)
        self.duplicate_frame_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.duplicate_frame_btn)
        
        self.remove_frame_btn = QPushButton("Del")
        self.remove_frame_btn.clicked.connect(self.remove_frame)
        self.remove_frame_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.remove_frame_btn)
        
        self.move_frame_up_btn = QPushButton("▲")
        self.move_frame_up_btn.clicked.connect(self.move_frame_up)
        self.move_frame_up_btn.setMaximumWidth(30)
        self.move_frame_up_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.move_frame_up_btn)
        
        self.move_frame_down_btn = QPushButton("▼")
        self.move_frame_down_btn.clicked.connect(self.move_frame_down)
        self.move_frame_down_btn.setMaximumWidth(30)
        self.move_frame_down_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.move_frame_down_btn)
        
        self.refresh_timeline_btn = QPushButton("🔄")
        self.refresh_timeline_btn.clicked.connect(self.refresh_timeline)
        self.refresh_timeline_btn.setMaximumWidth(30)
        self.refresh_timeline_btn.setMaximumHeight(25)
        self.refresh_timeline_btn.setToolTip("Refresh Timeline")
        btn_row1.addWidget(self.refresh_timeline_btn)
        
        frame_controls_layout.addLayout(btn_row1)
        
        # Batch offset (single row)
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("Offset:"))
        self.batch_offset_x = QSpinBox()
        self.batch_offset_x.setMinimum(-10000)
        self.batch_offset_x.setMaximum(10000)
        self.batch_offset_x.setValue(0)
        self.batch_offset_x.setMaximumWidth(60)
        offset_layout.addWidget(self.batch_offset_x)
        self.batch_offset_y = QSpinBox()
        self.batch_offset_y.setMinimum(-10000)
        self.batch_offset_y.setMaximum(10000)
        self.batch_offset_y.setValue(0)
        self.batch_offset_y.setMaximumWidth(60)
        offset_layout.addWidget(self.batch_offset_y)
        self.apply_batch_offset_btn = QPushButton("Apply")
        self.apply_batch_offset_btn.clicked.connect(self.apply_batch_offset)
        self.apply_batch_offset_btn.setMaximumHeight(25)
        offset_layout.addWidget(self.apply_batch_offset_btn)
        offset_layout.addStretch()
        frame_controls_layout.addLayout(offset_layout)
        
        # Batch layer buttons (compact)
        batch_row1 = QHBoxLayout()
        self.batch_add_same_layer_btn = QPushButton("+ Same Layer")
        self.batch_add_same_layer_btn.clicked.connect(self.batch_add_same_layer)
        self.batch_add_same_layer_btn.setMaximumHeight(25)
        batch_row1.addWidget(self.batch_add_same_layer_btn)
        frame_controls_layout.addLayout(batch_row1)
        
        batch_row2 = QHBoxLayout()
        self.batch_add_matched_layers_btn = QPushButton("+ Matched (1:1)")
        self.batch_add_matched_layers_btn.clicked.connect(self.batch_add_matched_layers)
        self.batch_add_matched_layers_btn.setMaximumHeight(25)
        batch_row2.addWidget(self.batch_add_matched_layers_btn)
        frame_controls_layout.addLayout(batch_row2)
        
        frame_controls.setLayout(frame_controls_layout)
        layout.addWidget(frame_controls, stretch=0)
        
        # Layer editor
        self.layer_editor = LayerEditorWidget()
        self.layer_editor.set_material_manager(self.material_manager)
        self.layer_editor.layers_changed.connect(self.on_layers_changed)
        layout.addWidget(self.layer_editor, stretch=2)
        
        panel.setLayout(layout)
        return panel
    
    def create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        # Preview controls
        preview_controls = QHBoxLayout()
        preview_controls.addWidget(QLabel("Preview Frame:"))
        
        self.preview_frame_spinbox = QSpinBox()
        self.preview_frame_spinbox.setMinimum(1)
        self.preview_frame_spinbox.setMaximum(1)
        self.preview_frame_spinbox.setValue(1)
        self.preview_frame_spinbox.setMaximumWidth(60)
        self.preview_frame_spinbox.valueChanged.connect(self.update_single_frame_preview)
        preview_controls.addWidget(self.preview_frame_spinbox)
        
        self.preview_all_checkbox = QCheckBox("Preview All (Animation)")
        self.preview_all_checkbox.setChecked(True)
        self.preview_all_checkbox.stateChanged.connect(self.on_preview_mode_changed)
        preview_controls.addWidget(self.preview_all_checkbox)
        preview_controls.addStretch()
        
        layout.addLayout(preview_controls)
        
        # Preview at top (with more space)
        self.preview = PreviewWidget()
        layout.addWidget(self.preview, stretch=3)
        
        # Compact settings section
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(3)
        
        # Size (more compact)
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setMinimum(1)
        self.width_spinbox.setMaximum(4096)
        self.width_spinbox.setValue(400)
        size_layout.addWidget(self.width_spinbox)
        size_layout.addWidget(QLabel("×"))
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(1)
        self.height_spinbox.setMaximum(4096)
        self.height_spinbox.setValue(400)
        size_layout.addWidget(self.height_spinbox)
        size_layout.addStretch()
        settings_layout.addLayout(size_layout)
        
        # Loop (compact)
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("Loop:"))
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setMinimum(0)
        self.loop_spinbox.setMaximum(1000)
        self.loop_spinbox.setValue(0)
        self.loop_spinbox.setSpecialValueText("∞")
        loop_layout.addWidget(self.loop_spinbox)
        loop_layout.addStretch()
        settings_layout.addLayout(loop_layout)
        
        # Transparent BG
        self.transparent_bg_checkbox = QCheckBox("Transparent BG")
        self.transparent_bg_checkbox.stateChanged.connect(self.on_transparent_bg_changed)
        settings_layout.addWidget(self.transparent_bg_checkbox)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group, stretch=0)
        
        # Action buttons (compact)
        self.update_preview_btn = QPushButton("🔄 Preview")
        self.update_preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(self.update_preview_btn)
        
        self.export_gif_btn = QPushButton("💾 Export GIF")
        self.export_gif_btn.clicked.connect(self.export_gif)
        self.export_gif_btn.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white;")
        layout.addWidget(self.export_gif_btn)
        
        panel.setLayout(layout)
        return panel
    
    def create_menu_bar(self):
        menubar = self.menuBar()
        
        file_menu = menubar.addMenu("File")
        
        file_menu.addAction("Load Image", self.load_image_material)
        file_menu.addAction("Load GIF", self.load_gif_material)
        file_menu.addSeparator()
        file_menu.addAction("Export GIF", self.export_gif)
        file_menu.addAction("Export Selected Materials", self.export_selected_materials)
        file_menu.addAction("Export All Materials", self.export_all_materials)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self.show_about)
    
    def load_image_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                QMessageBox.information(self, "Success", "Image loaded successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
    
    def load_gif_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GIF",
            "",
            "GIF Files (*.gif)"
        )
        
        if file_path:
            try:
                self.material_manager.load_from_gif(file_path)
                self.refresh_materials_list()
                QMessageBox.information(self, "Success", 
                    f"GIF loaded and extracted into {len(self.material_manager)} frames!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load GIF:\n{str(e)}")
    
    def load_multiple_materials(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Images",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_paths:
            try:
                for file_path in file_paths:
                    self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                QMessageBox.information(self, "Success", 
                    f"Loaded {len(file_paths)} images!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load images:\n{str(e)}")
    
    def on_tiles_created(self, tiles):
        try:
            name_prefix = "Tile"
            self.material_manager.add_materials_from_list(tiles, name_prefix)
            self.refresh_materials_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add tiles:\n{str(e)}")
    
    def refresh_materials_list(self):
        self.materials_list.clear()
        
        for i, (img, name) in enumerate(self.material_manager.get_all_materials()):
            thumbnail = self.create_thumbnail(img, 64, 64)
            icon = QIcon(thumbnail)
            
            item = QListWidgetItem(icon, f"[{i}] {name} ({img.width}x{img.height})")
            item.setSizeHint(QSize(200, 70))
            self.materials_list.addItem(item)
    
    def create_thumbnail(self, pil_image, width, height):
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)
    
    def add_selected_to_timeline(self):
        """Add selected materials as new frames"""
        selected_rows = [item.row() for item in self.materials_list.selectedIndexes()]
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        
        try:
            duration = self.timeline.duration_spinbox.value()
            
            # Auto-set output size based on first material if timeline is empty
            if len(self.layered_sequence_editor) == 0 and selected_rows:
                first_material_row = selected_rows[0]
                if first_material_row < len(self.material_manager):
                    material = self.material_manager.get_material(first_material_row)
                    if material:
                        img, name = material
                        self.width_spinbox.setValue(img.width)
                        self.height_spinbox.setValue(img.height)
            
            # Create a new LayeredFrame for each selected material
            for material_idx in selected_rows:
                new_frame = LayeredFrame(
                    duration=duration,
                    name=f"Frame {len(self.layered_sequence_editor) + 1}"
                )
                layer = Layer(material_index=material_idx, name="Layer 1")
                new_frame.add_layer(layer)
                self.layered_sequence_editor.add_frame(new_frame)
            
            self.refresh_timeline()
            
            # Auto-select the last added frame
            if len(self.layered_sequence_editor) > 0:
                last_idx = len(self.layered_sequence_editor) - 1
                self.timeline.timeline_table.selectRow(last_idx)
        
        except Exception as e:
            print(f"ERROR in add_selected_to_timeline: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to add materials to timeline:\n{str(e)}")
    
    def remove_selected_material(self):
        selected_rows = sorted([item.row() for item in self.materials_list.selectedIndexes()], reverse=True)
        if selected_rows:
            for row in selected_rows:
                self.material_manager.remove_material(row)
            self.refresh_materials_list()
        else:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
    
    def clear_materials(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "Are you sure you want to clear all materials?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.material_manager.clear()
            self.refresh_materials_list()
    
    def export_selected_materials(self):
        selected_rows = [item.row() for item in self.materials_list.selectedIndexes()]
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one material to export!")
            return
        
        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            ""
        )
        
        if not export_dir:
            return
        
        try:
            exported_count = 0
            used_names = set()  # Track used filenames to avoid duplicates
            
            for row in selected_rows:
                if row < len(self.material_manager):
                    material = self.material_manager.get_material(row)
                    if material:
                        img, name = material
                        # Clean filename (remove invalid characters)
                        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                        if not safe_name:
                            safe_name = f"material_{row}"
                        
                        # Ensure unique filename
                        base_name = safe_name
                        counter = 1
                        final_name = base_name
                        
                        while f"{final_name}.png" in used_names:
                            final_name = f"{base_name}_{counter}"
                            counter += 1
                        
                        used_names.add(f"{final_name}.png")
                        
                        # Export as PNG
                        export_path = f"{export_dir}/{final_name}.png"
                        img.save(export_path, "PNG")
                        exported_count += 1
            
            QMessageBox.information(self, "Success", 
                f"Successfully exported {exported_count} images to:\n{export_dir}")
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export images:\n{str(e)}")
    
    def export_all_materials(self):
        if len(self.material_manager) == 0:
            QMessageBox.warning(self, "Warning", "No materials to export!")
            return
        
        # Ask for export directory
        export_dir = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            ""
        )
        
        if not export_dir:
            return
        
        try:
            exported_count = 0
            used_names = set()  # Track used filenames to avoid duplicates
            
            for i in range(len(self.material_manager)):
                material = self.material_manager.get_material(i)
                if material:
                    img, name = material
                    # Clean filename (remove invalid characters)
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    if not safe_name:
                        safe_name = f"material_{i}"
                    
                    # Ensure unique filename
                    base_name = safe_name
                    counter = 1
                    final_name = base_name
                    
                    while f"{final_name}.png" in used_names:
                        final_name = f"{base_name}_{counter}"
                        counter += 1
                    
                    used_names.add(f"{final_name}.png")
                    
                    # Export as PNG
                    export_path = f"{export_dir}/{final_name}.png"
                    img.save(export_path, "PNG")
                    exported_count += 1
            
            QMessageBox.information(self, "Success", 
                f"Successfully exported {exported_count} images to:\n{export_dir}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export images:\n{str(e)}")
    
    def on_sequence_changed(self):
        """Handle timeline changes (including drag-reorder)"""
        # Timeline rows may have been reordered by dragging
        # We need to reorder layered_sequence_editor to match
        # But for now, just update preview
        # TODO: Handle drag reordering properly
        self.update_preview()
    
    def on_apply_duration(self, duration: int, apply_to_all: bool):
        """Handle duration change requests from timeline"""
        if apply_to_all:
            # Apply to all frames
            for frame in self.layered_sequence_editor.get_frames():
                frame.duration = duration
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(
                self, 
                "Success", 
                f"Applied duration {duration}ms to all {len(self.layered_sequence_editor)} frames."
            )
        else:
            # Apply to selected frames
            selected_items = self.timeline.timeline_table.selectedIndexes()
            
            if not selected_items:
                QMessageBox.warning(self, "Warning", "Please select one or more frames!")
                return
            
            # Get unique frame indices
            frame_indices = sorted(set([item.data(Qt.ItemDataRole.UserRole) 
                                        for item in selected_items 
                                        if item.data(Qt.ItemDataRole.UserRole) is not None]))
            
            if not frame_indices:
                return
            
            for frame_index in frame_indices:
                if frame_index < len(self.layered_sequence_editor):
                    frame = self.layered_sequence_editor.get_frame(frame_index)
                    if frame:
                        frame.duration = duration
            
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(
                self, 
                "Success", 
                f"Applied duration {duration}ms to {len(frame_indices)} selected frames."
            )
    
    def export_gif(self):
        """Export GIF from layered frames"""
        if len(self.layered_sequence_editor) == 0:
            QMessageBox.warning(self, "Warning", "No frames to export!")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save GIF",
            "output.gif",
            "GIF Files (*.gif)"
        )
        
        if file_path:
            try:
                self.gif_builder.set_output_size(
                    self.width_spinbox.value(),
                    self.height_spinbox.value()
                )
                self.gif_builder.set_loop(self.loop_spinbox.value())
                
                if self.transparent_bg_checkbox.isChecked():
                    self.gif_builder.set_background_color(0, 0, 0, 0)
                else:
                    self.gif_builder.set_background_color(255, 255, 255, 255)
                
                self.gif_builder.build_from_layered_sequence(
                    self.layered_sequence_editor.get_frames(),
                    self.material_manager,
                    file_path
                )
                
                QMessageBox.information(self, "Success", 
                    f"GIF saved successfully!\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export GIF:\n{str(e)}")
    
    def on_timeline_selection_changed(self):
        """Handle timeline selection change - auto-edit the selected frame"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            # No selection, clear layer editor
            self.layer_editor.set_frame(None)
            return
        
        # Get actual frame index from the first selected item
        frame_idx = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if frame_idx is not None and frame_idx < len(self.layered_sequence_editor):
            frame = self.layered_sequence_editor.get_frame(frame_idx)
            self.layer_editor.set_frame(frame)
    
    def duplicate_frame(self):
        """Duplicate the selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to duplicate!")
            return
        
        # Get unique frame indices (selectedIndexes includes all cells, we need unique rows)
        frame_indices = sorted(set([item.data(Qt.ItemDataRole.UserRole) 
                                    for item in selected_items 
                                    if item.data(Qt.ItemDataRole.UserRole) is not None]))
        
        if not frame_indices:
            return
        
        # Copy all selected frames as a group and insert after the last selected frame
        # This produces: [1,2,3] -> [1,2,3,1,2,3] instead of [1,1,2,2,3,3]
        insert_position = frame_indices[-1] + 1
        
        for frame_idx in frame_indices:
            if frame_idx < len(self.layered_sequence_editor):
                # Get the frame to duplicate
                original_frame = self.layered_sequence_editor.get_frame(frame_idx)
                if original_frame:
                    # Create a copy and insert at the insert position
                    duplicated_frame = original_frame.copy()
                    self.layered_sequence_editor.frames.insert(insert_position, duplicated_frame)
                    insert_position += 1
        
        self.refresh_timeline()
        
        # Auto-select the first duplicated frame
        if frame_indices:
            new_idx = frame_indices[-1] + 1
            for row in range(self.timeline.timeline_table.rowCount()):
                item = self.timeline.timeline_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == new_idx:
                    self.timeline.timeline_table.selectRow(row)
                    break
    
    def remove_frame(self):
        """Remove selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to remove!")
            return
        
        # Get unique frame indices (selectedIndexes includes all cells, we need unique rows)
        frame_indices = sorted(set([item.data(Qt.ItemDataRole.UserRole) 
                                    for item in selected_items 
                                    if item.data(Qt.ItemDataRole.UserRole) is not None]), 
                              reverse=True)
        
        if not frame_indices:
            return
        
        # Remove frames in reverse order to avoid index shifting issues
        for frame_index in frame_indices:
            if 0 <= frame_index < len(self.layered_sequence_editor):
                self.layered_sequence_editor.remove_frame(frame_index)
        
        self.refresh_timeline()
    
    def move_frame_up(self):
        """Move selected frame up (earlier in timeline)"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to move!")
            return
        
        if len(selected_items) > 1:
            QMessageBox.warning(self, "Warning", "Please select only one frame to move!")
            return
        
        # Get actual frame index
        frame_index = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if frame_index is None:
            return
        
        if frame_index > 0:
            self.layered_sequence_editor.move_frame(frame_index, frame_index - 1)
            self.refresh_timeline()
            # Select the moved frame (find the new table row)
            for row in range(self.timeline.timeline_table.rowCount()):
                item = self.timeline.timeline_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == frame_index - 1:
                    self.timeline.timeline_table.selectRow(row)
                    break
    
    def move_frame_down(self):
        """Move selected frame down (later in timeline)"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to move!")
            return
        
        if len(selected_items) > 1:
            QMessageBox.warning(self, "Warning", "Please select only one frame to move!")
            return
        
        # Get actual frame index
        frame_index = selected_items[0].data(Qt.ItemDataRole.UserRole)
        if frame_index is None:
            return
        
        if frame_index < len(self.layered_sequence_editor) - 1:
            self.layered_sequence_editor.move_frame(frame_index, frame_index + 1)
            self.refresh_timeline()
            # Select the moved frame (find the new table row)
            for row in range(self.timeline.timeline_table.rowCount()):
                item = self.timeline.timeline_table.item(row, 0)
                if item and item.data(Qt.ItemDataRole.UserRole) == frame_index + 1:
                    self.timeline.timeline_table.selectRow(row)
                    break
    
    def apply_batch_offset(self):
        """Apply offset to all layers in selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames!")
            return
        
        # Get unique frame indices (selectedIndexes includes all cells, we need unique rows)
        frame_indices = sorted(set([item.data(Qt.ItemDataRole.UserRole) 
                                    for item in selected_items 
                                    if item.data(Qt.ItemDataRole.UserRole) is not None]))
        
        if not frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        
        offset_x = self.batch_offset_x.value()
        offset_y = self.batch_offset_y.value()
        
        if offset_x == 0 and offset_y == 0:
            QMessageBox.information(self, "Info", "Offset is 0, no changes needed.")
            return
        
        total_layers = 0
        for frame_index in frame_indices:
            if frame_index < len(self.layered_sequence_editor):
                frame = self.layered_sequence_editor.get_frame(frame_index)
                if frame:
                    for layer in frame.layers:
                        layer.x += offset_x
                        layer.y += offset_y
                        total_layers += 1
        
        # Reset offset values to prevent accidental re-application
        self.batch_offset_x.setValue(0)
        self.batch_offset_y.setValue(0)
        
        self.update_preview()
        
        # If currently editing one of the modified frames, refresh the layer editor
        if self.layer_editor.current_frame:
            for frame_index in frame_indices:
                if frame_index < len(self.layered_sequence_editor):
                    if self.layered_sequence_editor.get_frame(frame_index) == self.layer_editor.current_frame:
                        self.layer_editor.refresh_layer_list()
                        break
        
        QMessageBox.information(
            self, 
            "Success", 
            f"Applied offset (X: {offset_x}, Y: {offset_y}) to {total_layers} layers in {len(frame_indices)} frames."
        )
    
    def batch_add_same_layer(self):
        """Add the same layer to all selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames!")
            return
        
        # Get actual frame indices
        frame_indices = []
        for item in selected_items:
            frame_index = item.data(Qt.ItemDataRole.UserRole)
            if frame_index is not None:
                frame_indices.append(frame_index)
        
        if not frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        
        if not self.material_manager or len(self.material_manager) == 0:
            QMessageBox.warning(self, "Warning", "No materials available!")
            return
        
        # Show material selector dialog
        from .widgets.material_selector_dialog import MaterialSelectorDialog
        dialog = MaterialSelectorDialog(self.material_manager, self)
        
        if not dialog.exec():
            return
        
        material_index = dialog.get_selected_material_index()
        if material_index is None:
            return
        
        # Ask for layer properties
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox, QPushButton, QDialogButtonBox
        
        props_dialog = QDialog(self)
        props_dialog.setWindowTitle("Layer Properties")
        props_layout = QVBoxLayout()
        
        # X position
        x_layout = QHBoxLayout()
        x_layout.addWidget(QLabel("X Position:"))
        x_spinbox = QSpinBox()
        x_spinbox.setMinimum(-10000)
        x_spinbox.setMaximum(10000)
        x_spinbox.setValue(0)
        x_layout.addWidget(x_spinbox)
        props_layout.addLayout(x_layout)
        
        # Y position
        y_layout = QHBoxLayout()
        y_layout.addWidget(QLabel("Y Position:"))
        y_spinbox = QSpinBox()
        y_spinbox.setMinimum(-10000)
        y_spinbox.setMaximum(10000)
        y_spinbox.setValue(0)
        y_layout.addWidget(y_spinbox)
        props_layout.addLayout(y_layout)
        
        # Scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        scale_spinbox = QDoubleSpinBox()
        scale_spinbox.setMinimum(0.01)
        scale_spinbox.setMaximum(10.0)
        scale_spinbox.setValue(1.0)
        scale_spinbox.setSingleStep(0.1)
        scale_layout.addWidget(scale_spinbox)
        props_layout.addLayout(scale_layout)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        opacity_spinbox = QDoubleSpinBox()
        opacity_spinbox.setMinimum(0.0)
        opacity_spinbox.setMaximum(1.0)
        opacity_spinbox.setValue(1.0)
        opacity_spinbox.setSingleStep(0.1)
        opacity_layout.addWidget(opacity_spinbox)
        props_layout.addLayout(opacity_layout)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(props_dialog.accept)
        button_box.rejected.connect(props_dialog.reject)
        props_layout.addWidget(button_box)
        
        props_dialog.setLayout(props_layout)
        
        if not props_dialog.exec():
            return
        
        # Get properties
        x = x_spinbox.value()
        y = y_spinbox.value()
        scale = scale_spinbox.value()
        opacity = opacity_spinbox.value()
        
        # Add layer to all selected frames
        for frame_index in frame_indices:
            if frame_index < len(self.layered_sequence_editor):
                frame = self.layered_sequence_editor.get_frame(frame_index)
                if frame:
                    new_layer = Layer(
                        material_index=material_index,
                        x=x,
                        y=y,
                        scale=scale,
                        opacity=opacity,
                        name=f"Layer {len(frame.layers) + 1}"
                    )
                    frame.add_layer(new_layer)
        
        self.refresh_timeline()
        self.update_preview()
        
        # Refresh layer editor if currently editing one of the modified frames
        if self.layer_editor.current_frame:
            for frame_index in frame_indices:
                if frame_index < len(self.layered_sequence_editor):
                    if self.layered_sequence_editor.get_frame(frame_index) == self.layer_editor.current_frame:
                        self.layer_editor.refresh_layer_list()
                        break
        
        QMessageBox.information(
            self,
            "Success",
            f"Added layer (Material #{material_index}) to {len(frame_indices)} frames."
        )
    
    def batch_add_matched_layers(self):
        """Add matched layers 1:1 - N frames + N materials"""
        # Get selected frames
        selected_frame_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_frame_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames in Timeline!")
            return
        
        # Get actual frame indices
        selected_frame_indices = []
        for item in selected_frame_items:
            frame_index = item.data(Qt.ItemDataRole.UserRole)
            if frame_index is not None:
                selected_frame_indices.append(frame_index)
        
        if not selected_frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        
        # Get selected materials
        selected_material_rows = sorted([item.row() for item in self.materials_list.selectedIndexes()])
        
        if not selected_material_rows:
            QMessageBox.warning(self, "Warning", "Please select one or more materials in Materials list!")
            return
        
        # Check if counts match
        if len(selected_frame_indices) != len(selected_material_rows):
            QMessageBox.warning(
                self,
                "Warning",
                f"Number of selected frames ({len(selected_frame_indices)}) must match "
                f"number of selected materials ({len(selected_material_rows)})!"
            )
            return
        
        # Ask for layer properties
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QDoubleSpinBox, QDialogButtonBox
        
        props_dialog = QDialog(self)
        props_dialog.setWindowTitle("Layer Properties (Applied to All)")
        props_layout = QVBoxLayout()
        
        props_layout.addWidget(QLabel(f"Adding {len(selected_frame_indices)} materials to {len(selected_frame_indices)} frames (1:1 matched)"))
        
        # X position
        x_layout = QHBoxLayout()
        x_layout.addWidget(QLabel("X Position:"))
        x_spinbox = QSpinBox()
        x_spinbox.setMinimum(-10000)
        x_spinbox.setMaximum(10000)
        x_spinbox.setValue(0)
        x_layout.addWidget(x_spinbox)
        props_layout.addLayout(x_layout)
        
        # Y position
        y_layout = QHBoxLayout()
        y_layout.addWidget(QLabel("Y Position:"))
        y_spinbox = QSpinBox()
        y_spinbox.setMinimum(-10000)
        y_spinbox.setMaximum(10000)
        y_spinbox.setValue(0)
        y_layout.addWidget(y_spinbox)
        props_layout.addLayout(y_layout)
        
        # Scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        scale_spinbox = QDoubleSpinBox()
        scale_spinbox.setMinimum(0.01)
        scale_spinbox.setMaximum(10.0)
        scale_spinbox.setValue(1.0)
        scale_spinbox.setSingleStep(0.1)
        scale_layout.addWidget(scale_spinbox)
        props_layout.addLayout(scale_layout)
        
        # Opacity
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("Opacity:"))
        opacity_spinbox = QDoubleSpinBox()
        opacity_spinbox.setMinimum(0.0)
        opacity_spinbox.setMaximum(1.0)
        opacity_spinbox.setValue(1.0)
        opacity_spinbox.setSingleStep(0.1)
        opacity_layout.addWidget(opacity_spinbox)
        props_layout.addLayout(opacity_layout)
        
        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(props_dialog.accept)
        button_box.rejected.connect(props_dialog.reject)
        props_layout.addWidget(button_box)
        
        props_dialog.setLayout(props_layout)
        
        if not props_dialog.exec():
            return
        
        # Get properties
        x = x_spinbox.value()
        y = y_spinbox.value()
        scale = scale_spinbox.value()
        opacity = opacity_spinbox.value()
        
        # Add matched layers
        for frame_index, material_idx in zip(selected_frame_indices, selected_material_rows):
            if frame_index < len(self.layered_sequence_editor):
                frame = self.layered_sequence_editor.get_frame(frame_index)
                if frame:
                    new_layer = Layer(
                        material_index=material_idx,
                        x=x,
                        y=y,
                        scale=scale,
                        opacity=opacity,
                        name=f"Layer {len(frame.layers) + 1}"
                    )
                    frame.add_layer(new_layer)
        
        self.refresh_timeline()
        self.update_preview()
        
        # Refresh layer editor if currently editing one of the modified frames
        if self.layer_editor.current_frame:
            for frame_index in selected_frame_indices:
                if frame_index < len(self.layered_sequence_editor):
                    if self.layered_sequence_editor.get_frame(frame_index) == self.layer_editor.current_frame:
                        self.layer_editor.refresh_layer_list()
                        break
        
        QMessageBox.information(
            self,
            "Success",
            f"Added {len(selected_frame_indices)} matched layers (1:1) with properties:\n"
            f"X: {x}, Y: {y}, Scale: {scale}, Opacity: {opacity}"
        )
    
    def refresh_timeline(self):
        """Refresh timeline to show frames"""
        # Block signals during refresh to prevent triggering update_preview multiple times
        self.timeline.timeline_table.blockSignals(True)
        
        # Clear table
        self.timeline.timeline_table.setRowCount(0)
        
        # Show all frames, including empty ones
        for i, frame in enumerate(self.layered_sequence_editor.get_frames()):
            # Add row to table
            self.timeline.timeline_table.insertRow(i)
            
            # Column 0: Index (show actual frame index + 1)
            index_item = QTableWidgetItem(str(i + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store the actual frame index in the item's data
            index_item.setData(Qt.ItemDataRole.UserRole, i)
            self.timeline.timeline_table.setItem(i, 0, index_item)
            
            # Column 1: Preview
            preview_item = QTableWidgetItem()
            if len(frame.layers) > 0:
                first_layer = frame.layers[0]
                if first_layer.material_index < len(self.material_manager):
                    material = self.material_manager.get_material(first_layer.material_index)
                    if material:
                        img, name = material
                        thumbnail = self.create_thumbnail(img, 64, 64)
                        preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store the actual frame index in the item's data
            preview_item.setData(Qt.ItemDataRole.UserRole, i)
            self.timeline.timeline_table.setItem(i, 1, preview_item)
            
            # Column 2: Frame info (Material + Layers count + Offset)
            if len(frame.layers) > 0:
                first_layer = frame.layers[0]
                offset_text = f"({first_layer.x}, {first_layer.y})"
                frame_text = f"Mat#{first_layer.material_index} | {len(frame.layers)}L | Pos{offset_text}"
            else:
                frame_text = f"Empty | 0L"
            frame_item = QTableWidgetItem(frame_text)
            frame_item.setFlags(frame_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store the actual frame index in the item's data
            frame_item.setData(Qt.ItemDataRole.UserRole, i)
            self.timeline.timeline_table.setItem(i, 2, frame_item)
            
            # Column 3: Duration
            duration_item = QTableWidgetItem(str(frame.duration))
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            # Store the actual frame index in the item's data
            duration_item.setData(Qt.ItemDataRole.UserRole, i)
            self.timeline.timeline_table.setItem(i, 3, duration_item)
            
            self.timeline.timeline_table.setRowHeight(i, 70)
        
        self.timeline.timeline_table.blockSignals(False)
    
    def on_layers_changed(self):
        """Handle layer changes - only update preview, don't refresh timeline to avoid losing focus"""
        self.update_preview()
    
    def on_transparent_bg_changed(self):
        """Handle transparent background checkbox change"""
        # Update preview to show/hide checkerboard
        self.preview.set_checkerboard(self.transparent_bg_checkbox.isChecked())
        self.update_preview()
    
    def on_preview_mode_changed(self):
        """Handle preview mode change"""
        if self.preview_all_checkbox.isChecked():
            # Preview all frames (animation)
            self.preview_frame_spinbox.setEnabled(False)
            self.update_preview()
        else:
            # Preview single frame
            self.preview_frame_spinbox.setEnabled(True)
            self.update_single_frame_preview()
    
    def update_single_frame_preview(self):
        """Update preview for a single selected frame"""
        if len(self.layered_sequence_editor) == 0:
            return
        
        frame_idx = self.preview_frame_spinbox.value() - 1  # Convert to 0-based index
        if frame_idx >= len(self.layered_sequence_editor):
            return
        
        try:
            self.gif_builder.set_output_size(
                self.width_spinbox.value(),
                self.height_spinbox.value()
            )
            
            if self.transparent_bg_checkbox.isChecked():
                self.gif_builder.set_background_color(0, 0, 0, 0)
            else:
                self.gif_builder.set_background_color(255, 255, 255, 255)
            
            # Get the single frame
            frame = self.layered_sequence_editor.get_frame(frame_idx)
            if frame:
                frames = self.gif_builder.get_layered_preview_frames(
                    [frame],
                    self.material_manager
                )
                self.preview.set_frames(frames)
            
        except Exception as e:
            print(f"ERROR in update_single_frame_preview: {e}")
            import traceback
            traceback.print_exc()
    
    def update_preview(self):
        """Update preview"""
        if len(self.layered_sequence_editor) == 0:
            return
        
        # Update preview frame spinbox range
        total_frames = len(self.layered_sequence_editor)
        self.preview_frame_spinbox.setMaximum(max(1, total_frames))
        
        # If single frame mode, update single frame
        if not self.preview_all_checkbox.isChecked():
            self.update_single_frame_preview()
            return
        
        try:
            self.gif_builder.set_output_size(
                self.width_spinbox.value(),
                self.height_spinbox.value()
            )
            self.gif_builder.set_loop(self.loop_spinbox.value())
            
            if self.transparent_bg_checkbox.isChecked():
                self.gif_builder.set_background_color(0, 0, 0, 0)
            else:
                self.gif_builder.set_background_color(255, 255, 255, 255)
            
            frames = self.gif_builder.get_layered_preview_frames(
                self.layered_sequence_editor.get_frames(),
                self.material_manager
            )
            
            self.preview.set_frames(frames)
            
        except Exception as e:
            # Just print to console, don't show error dialog on every property change
            print(f"ERROR in update_preview: {e}")
            import traceback
            traceback.print_exc()
    
    def show_about(self):
        QMessageBox.about(
            self,
            "About GIF Maker",
            "<h2>GIF Maker</h2>"
            "<p>A powerful GIF animation editor with material management and timeline editing.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Load images and GIFs as materials</li>"
            "<li>Split images into tiles</li>"
            "<li>Drag-and-drop timeline editing</li>"
            "<li>Real-time preview</li>"
            "<li>Customizable frame duration and sequence</li>"
            "</ul>"
            "<p>Version 1.0</p>"
        )


def main():
    app = QApplication(sys.argv)
    
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

