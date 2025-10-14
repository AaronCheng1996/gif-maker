import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image

from .core import MaterialManager, SequenceEditor, GifBuilder, LayeredSequenceEditor, Layer, LayeredFrame
from .widgets import PreviewWidget, TimelineWidget, TileEditorWidget, LayerEditorWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.material_manager = MaterialManager()
        self.sequence_editor = SequenceEditor()
        self.layered_sequence_editor = LayeredSequenceEditor()
        self.gif_builder = GifBuilder()
        
        # Mode: 'simple' or 'layered'
        self.editing_mode = 'simple'
        
        self.init_ui()
        self.setWindowTitle("GIF Maker - Animation Editor")
        self.resize(1600, 900)
    
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
        splitter.setSizes([400, 500, 500])
        
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
        
        # Mode switcher
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Editing Mode:"))
        
        self.simple_mode_btn = QPushButton("Simple Mode")
        self.simple_mode_btn.setCheckable(True)
        self.simple_mode_btn.setChecked(True)
        self.simple_mode_btn.clicked.connect(lambda: self.switch_mode('simple'))
        mode_layout.addWidget(self.simple_mode_btn)
        
        self.layered_mode_btn = QPushButton("Layered Mode")
        self.layered_mode_btn.setCheckable(True)
        self.layered_mode_btn.clicked.connect(lambda: self.switch_mode('layered'))
        mode_layout.addWidget(self.layered_mode_btn)
        
        mode_layout.addStretch()
        layout.addLayout(mode_layout)
        
        # Timeline
        self.timeline = TimelineWidget()
        self.timeline.set_material_manager(self.material_manager)
        self.timeline.sequence_changed.connect(self.on_sequence_changed)
        layout.addWidget(self.timeline)
        
        # Layer editor (initially hidden)
        self.layer_editor = LayerEditorWidget()
        self.layer_editor.set_material_manager(self.material_manager)
        self.layer_editor.layers_changed.connect(self.on_layers_changed)
        self.layer_editor.setVisible(False)
        layout.addWidget(self.layer_editor)
        
        # Frame controls for layered mode
        self.layered_frame_controls = QGroupBox("Frame Controls")
        layered_controls_layout = QVBoxLayout()
        
        btn_layout = QHBoxLayout()
        self.add_layered_frame_btn = QPushButton("Add Frame")
        self.add_layered_frame_btn.clicked.connect(self.add_layered_frame)
        btn_layout.addWidget(self.add_layered_frame_btn)
        
        self.edit_frame_layers_btn = QPushButton("Edit Frame Layers")
        self.edit_frame_layers_btn.clicked.connect(self.edit_frame_layers)
        btn_layout.addWidget(self.edit_frame_layers_btn)
        
        self.remove_layered_frame_btn = QPushButton("Remove Frame")
        self.remove_layered_frame_btn.clicked.connect(self.remove_layered_frame)
        btn_layout.addWidget(self.remove_layered_frame_btn)
        
        layered_controls_layout.addLayout(btn_layout)
        self.layered_frame_controls.setLayout(layered_controls_layout)
        self.layered_frame_controls.setVisible(False)
        layout.addWidget(self.layered_frame_controls)
        
        # Sequence operations (for simple mode)
        self.sequence_group = QGroupBox("Sequence Operations")
        sequence_layout = QVBoxLayout()
        
        repeat_layout = QHBoxLayout()
        repeat_layout.addWidget(QLabel("Repeat Selected:"))
        self.repeat_spinbox = QSpinBox()
        self.repeat_spinbox.setMinimum(2)
        self.repeat_spinbox.setMaximum(100)
        self.repeat_spinbox.setValue(2)
        repeat_layout.addWidget(self.repeat_spinbox)
        
        self.repeat_btn = QPushButton("Apply")
        self.repeat_btn.clicked.connect(self.repeat_sequence)
        repeat_layout.addWidget(self.repeat_btn)
        sequence_layout.addLayout(repeat_layout)
        
        self.reverse_btn = QPushButton("Reverse Selected")
        self.reverse_btn.clicked.connect(self.reverse_sequence)
        sequence_layout.addWidget(self.reverse_btn)
        
        self.sequence_group.setLayout(sequence_layout)
        layout.addWidget(self.sequence_group)
        
        panel.setLayout(layout)
        return panel
    
    def create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        
        self.preview = PreviewWidget()
        layout.addWidget(self.preview)
        
        settings_group = QGroupBox("GIF Settings")
        settings_layout = QVBoxLayout()
        
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Output Size:"))
        
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setMinimum(1)
        self.width_spinbox.setMaximum(4096)
        self.width_spinbox.setValue(400)
        self.width_spinbox.setSuffix(" px")
        size_layout.addWidget(self.width_spinbox)
        
        size_layout.addWidget(QLabel("x"))
        
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setMinimum(1)
        self.height_spinbox.setMaximum(4096)
        self.height_spinbox.setValue(400)
        self.height_spinbox.setSuffix(" px")
        size_layout.addWidget(self.height_spinbox)
        
        settings_layout.addLayout(size_layout)
        
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel("Loop:"))
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setMinimum(0)
        self.loop_spinbox.setMaximum(1000)
        self.loop_spinbox.setValue(0)
        self.loop_spinbox.setSpecialValueText("Infinite")
        loop_layout.addWidget(self.loop_spinbox)
        settings_layout.addLayout(loop_layout)
        
        self.transparent_bg_checkbox = QCheckBox("Transparent Background")
        self.transparent_bg_checkbox.setChecked(False)
        settings_layout.addWidget(self.transparent_bg_checkbox)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        actions_layout = QVBoxLayout()
        
        self.update_preview_btn = QPushButton("🔄 Update Preview")
        self.update_preview_btn.clicked.connect(self.update_preview)
        self.update_preview_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        actions_layout.addWidget(self.update_preview_btn)
        
        self.export_gif_btn = QPushButton("💾 Export GIF")
        self.export_gif_btn.clicked.connect(self.export_gif)
        self.export_gif_btn.setStyleSheet("font-weight: bold; padding: 10px; background-color: #4CAF50; color: white;")
        actions_layout.addWidget(self.export_gif_btn)
        
        layout.addLayout(actions_layout)
        
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
        selected_rows = [item.row() for item in self.materials_list.selectedIndexes()]
        if selected_rows:
            duration = self.timeline.duration_spinbox.value()
            
            # Auto-set output size based on first material if timeline is empty
            if len(self.timeline.frames) == 0 and selected_rows:
                first_material_row = selected_rows[0]
                if first_material_row < len(self.material_manager):
                    material = self.material_manager.get_material(first_material_row)
                    if material:
                        img, name = material
                        self.width_spinbox.setValue(img.width)
                        self.height_spinbox.setValue(img.height)
            
            for row in selected_rows:
                self.timeline.add_frame(row, duration)
        else:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
    
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
        self.update_preview()
    
    def repeat_sequence(self):
        selected_rows = sorted({index.row() for index in self.timeline.timeline_table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select frames to repeat!")
            return
        
        times = self.repeat_spinbox.value()
        selected_frames = [(self.timeline.frames[row][0], self.timeline.frames[row][1]) for row in selected_rows]
        
        insert_position = selected_rows[-1] + 1
        for _ in range(times - 1):
            for material_idx, duration in selected_frames:
                self.timeline.frames.insert(insert_position, (material_idx, duration))
                insert_position += 1
        
        self.timeline.refresh_display()
    
    def reverse_sequence(self):
        selected_rows = sorted({index.row() for index in self.timeline.timeline_table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select frames to reverse!")
            return
        
        selected_frames = [self.timeline.frames[row] for row in selected_rows]
        selected_frames.reverse()
        
        for i, row in enumerate(selected_rows):
            self.timeline.frames[row] = selected_frames[i]
        
        self.timeline.refresh_display()
    
    def update_preview(self):
        if self.editing_mode == 'simple':
            if len(self.timeline.frames) == 0:
                QMessageBox.warning(self, "Warning", "Timeline is empty!")
                return
            
            try:
                self.sequence_editor.clear()
                for material_idx, duration in self.timeline.frames:
                    self.sequence_editor.add_frame(material_idx, duration)
                
                self.gif_builder.set_output_size(
                    self.width_spinbox.value(),
                    self.height_spinbox.value()
                )
                self.gif_builder.set_loop(self.loop_spinbox.value())
                
                if self.transparent_bg_checkbox.isChecked():
                    self.gif_builder.set_background_color(0, 0, 0, 0)
                else:
                    self.gif_builder.set_background_color(255, 255, 255, 255)
                
                frames = self.gif_builder.get_preview_frames(
                    self.material_manager,
                    self.sequence_editor
                )
                
                self.preview.set_frames(frames)
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to update preview:\n{str(e)}")
        
        else:  # layered mode
            self.update_layered_preview()
    
    def export_gif(self):
        if self.editing_mode == 'simple':
            if len(self.timeline.frames) == 0:
                QMessageBox.warning(self, "Warning", "Timeline is empty!")
                return
        else:  # layered mode
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
                
                if self.editing_mode == 'simple':
                    self.sequence_editor.clear()
                    for material_idx, duration in self.timeline.frames:
                        self.sequence_editor.add_frame(material_idx, duration)
                    
                    self.gif_builder.build_from_sequence(
                        self.material_manager,
                        self.sequence_editor,
                        file_path
                    )
                else:  # layered mode
                    self.gif_builder.build_from_layered_sequence(
                        self.layered_sequence_editor.get_frames(),
                        self.material_manager,
                        file_path
                    )
                
                QMessageBox.information(self, "Success", 
                    f"GIF saved successfully!\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export GIF:\n{str(e)}")
    
    def switch_mode(self, mode: str):
        """Switch between simple and layered editing modes"""
        if mode == self.editing_mode:
            return
        
        self.editing_mode = mode
        
        if mode == 'simple':
            self.simple_mode_btn.setChecked(True)
            self.layered_mode_btn.setChecked(False)
            self.timeline.setVisible(True)
            self.layer_editor.setVisible(False)
            self.layered_frame_controls.setVisible(False)
            self.sequence_group.setVisible(True)
        else:  # layered
            self.simple_mode_btn.setChecked(False)
            self.layered_mode_btn.setChecked(True)
            self.timeline.setVisible(False)
            self.layer_editor.setVisible(True)
            self.layered_frame_controls.setVisible(True)
            self.sequence_group.setVisible(False)
    
    def add_layered_frame(self):
        """Add a new empty layered frame"""
        if not self.material_manager or len(self.material_manager) == 0:
            QMessageBox.warning(self, "Warning", "No materials available!")
            return
        
        # Create a frame with a single layer from the first material
        new_frame = LayeredFrame(duration=100, name=f"Frame {len(self.layered_sequence_editor) + 1}")
        layer = Layer(material_index=0, name="Layer 1")
        new_frame.add_layer(layer)
        
        self.layered_sequence_editor.add_frame(new_frame)
        self.refresh_layered_timeline()
        QMessageBox.information(self, "Success", "New frame added!")
    
    def edit_frame_layers(self):
        """Edit layers of the selected frame"""
        selected_rows = [item.row() for item in self.timeline.timeline_table.selectedIndexes()]
        
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select a frame to edit!")
            return
        
        frame_idx = selected_rows[0]
        if frame_idx >= len(self.layered_sequence_editor):
            QMessageBox.warning(self, "Warning", "Invalid frame selection!")
            return
        
        frame = self.layered_sequence_editor.get_frame(frame_idx)
        self.layer_editor.set_frame(frame)
        QMessageBox.information(self, "Info", f"Editing layers for Frame {frame_idx + 1}")
    
    def remove_layered_frame(self):
        """Remove selected layered frame"""
        selected_rows = sorted({item.row() for item in self.timeline.timeline_table.selectedIndexes()}, reverse=True)
        
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select a frame to remove!")
            return
        
        for row in selected_rows:
            if 0 <= row < len(self.layered_sequence_editor):
                self.layered_sequence_editor.remove_frame(row)
        
        self.refresh_layered_timeline()
    
    def refresh_layered_timeline(self):
        """Refresh timeline to show layered frames"""
        self.timeline.clear_timeline()
        
        for i, frame in enumerate(self.layered_sequence_editor.get_frames()):
            # For now, use the first layer's material for preview
            if len(frame.layers) > 0:
                first_layer = frame.layers[0]
                self.timeline.add_frame(first_layer.material_index, frame.duration)
    
    def on_layers_changed(self):
        """Handle layer changes"""
        self.update_layered_preview()
    
    def update_layered_preview(self):
        """Update preview for layered mode"""
        if len(self.layered_sequence_editor) == 0:
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
            QMessageBox.critical(self, "Error", f"Failed to update preview:\n{str(e)}")
    
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

