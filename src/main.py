import sys
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
                              QTableWidgetItem, QComboBox, QStackedWidget)
from PyQt6.QtCore import Qt, QSize, QItemSelectionModel
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image

from .core import MaterialManager, SequenceEditor, GifBuilder, LayeredSequenceEditor, Layer, LayeredFrame, TemplateManager
from .widgets import PreviewWidget, PreviewPageWidget, TimelineWidget, TileEditorWidget, LayerEditorWidget, BatchProcessorWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.material_manager = MaterialManager()
        self.layered_sequence_editor = LayeredSequenceEditor()
        self.gif_builder = GifBuilder()
        
        # Remember last used directories
        self.last_image_dir = ""
        self.last_gif_dir = ""
        self.last_export_dir = ""
        self.last_template_dir = ""
        
        # Template storage: {name: template_dict}
        self.templates = {}
        
        self.init_ui()
        self.setWindowTitle("GIF Maker - Layered Animation Editor")
        self.resize(1600, 950)
    
    def init_ui(self):
        # 創建堆疊 widget 來管理不同的頁面
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # 創建主頁面
        self.main_page = self.create_main_page()
        self.stacked_widget.addWidget(self.main_page)
        
        # 創建預覽頁面
        self.preview_page = PreviewPageWidget()
        self.preview_page.back_requested.connect(self.show_main_page)
        self.stacked_widget.addWidget(self.preview_page)
        
        # 預設顯示主頁面
        self.stacked_widget.setCurrentWidget(self.main_page)
        
        self.create_menu_bar()
    
    def create_main_page(self) -> QWidget:
        """創建主頁面"""
        central_widget = QWidget()
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
        # Adjusted sizes: left panel wider for batch processor, right panel for preview
        splitter.setSizes([400, 700, 400])
        
        main_layout.addWidget(splitter)
        
        return central_widget
    
    def show_main_page(self):
        """顯示主頁面"""
        self.stacked_widget.setCurrentWidget(self.main_page)
    
    def show_preview_page(self):
        """顯示預覽頁面"""
        self.stacked_widget.setCurrentWidget(self.preview_page)
    
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
        
        # Batch Processor tab
        self.batch_processor = BatchProcessorWidget()
        self.batch_processor.batch_complete.connect(self.on_batch_complete)
        
        batch_scroll_area = QScrollArea()
        batch_scroll_area.setWidget(self.batch_processor)
        batch_scroll_area.setWidgetResizable(True)
        tabs.addTab(batch_scroll_area, "Batch Process")
        
        # Update batch processor templates when templates change
        self.batch_processor.set_templates(self.templates)
        
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
        
        layout.addLayout(btn_row1)
        
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
        layout.addLayout(offset_layout)
        
        # Batch layer buttons (compact)
        batch_row1 = QHBoxLayout()
        self.batch_add_same_layer_btn = QPushButton("+ Same Layer")
        self.batch_add_same_layer_btn.clicked.connect(self.batch_add_same_layer)
        self.batch_add_same_layer_btn.setMaximumHeight(25)
        batch_row1.addWidget(self.batch_add_same_layer_btn)
        layout.addLayout(batch_row1)
        
        batch_row2 = QHBoxLayout()
        self.batch_add_matched_layers_btn = QPushButton("+ Matched (1:1)")
        self.batch_add_matched_layers_btn.clicked.connect(self.batch_add_matched_layers)
        self.batch_add_matched_layers_btn.setMaximumHeight(25)
        batch_row2.addWidget(self.batch_add_matched_layers_btn)
        layout.addLayout(batch_row2)
        
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

        self.info_label = QLabel("Frame: 0/0")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_controls.addWidget(self.info_label)
        
        layout.addLayout(preview_controls)
        
        # Preview (centered horizontally)
        preview_container = QHBoxLayout()
        preview_container.addStretch()  # Add stretch before preview
        self.preview = PreviewWidget()
        self.preview.frame_info_changed.connect(self.on_preview_frame_info_changed)
        self.preview.preview_clicked.connect(self.on_preview_clicked)
        self.preview.setMaximumHeight(400)  # Limit max height (accounts for control buttons)
        preview_container.addWidget(self.preview)  # Add preview widget
        preview_container.addStretch()  # Add stretch after preview
        layout.addLayout(preview_container)
        
        # Template management section (more space)
        template_group = QGroupBox("Template Manager")
        template_layout = QVBoxLayout()
        template_layout.setSpacing(3)
        
        # Template list (larger for easier management)
        self.template_list = QListWidget()
        self.template_list.setMinimumHeight(120)  # More visible space
        self.template_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        template_layout.addWidget(self.template_list)
        
        # Template action buttons (2 rows)
        template_row1 = QHBoxLayout()
        self.save_template_btn = QPushButton("💾 Save")
        self.save_template_btn.clicked.connect(self.quick_save_template)
        self.save_template_btn.setToolTip("Save current timeline as template")
        template_row1.addWidget(self.save_template_btn)
        
        self.apply_template_btn = QPushButton("✓ Apply")
        self.apply_template_btn.clicked.connect(self.quick_apply_template)
        self.apply_template_btn.setToolTip("Apply selected template to current materials")
        template_row1.addWidget(self.apply_template_btn)
        template_layout.addLayout(template_row1)
        
        template_row2 = QHBoxLayout()
        self.import_template_btn = QPushButton("📂 Import")
        self.import_template_btn.clicked.connect(self.quick_import_template)
        self.import_template_btn.setToolTip("Import template from file")
        template_row2.addWidget(self.import_template_btn)
        
        self.export_template_btn = QPushButton("💾 Export")
        self.export_template_btn.clicked.connect(self.quick_export_template)
        self.export_template_btn.setToolTip("Export selected template to file")
        template_row2.addWidget(self.export_template_btn)
        
        self.remove_template_btn = QPushButton("🗑 Remove")
        self.remove_template_btn.clicked.connect(self.remove_template)
        self.remove_template_btn.setToolTip("Remove selected template from list")
        template_row2.addWidget(self.remove_template_btn)
        template_layout.addLayout(template_row2)
        
        template_group.setLayout(template_layout)
        layout.addWidget(template_group, stretch=1)  # Allow template section to expand
        
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
        
        # Color palette selection
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Colors:"))
        self.color_palette_combo = QComboBox()
        self.color_palette_combo.addItems(["256", "128", "64", "32", "16"])
        self.color_palette_combo.setCurrentText("256")
        self.color_palette_combo.currentTextChanged.connect(self.on_color_palette_changed)
        color_layout.addWidget(self.color_palette_combo)
        color_layout.addStretch()
        settings_layout.addLayout(color_layout)
        
        
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
        file_menu.addAction("Export Template", self.export_template)
        file_menu.addAction("Import Template", self.import_template)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        
        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About", self.show_about)
    
    def load_image_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            self.last_image_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                # Remember the directory
                self.last_image_dir = str(Path(file_path).parent)
                
                self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                QMessageBox.information(self, "Success", "Image loaded successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load image:\n{str(e)}")
    
    def load_gif_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select GIF",
            self.last_gif_dir,
            "GIF Files (*.gif)"
        )
        
        if file_path:
            try:
                # Remember the directory
                self.last_gif_dir = str(Path(file_path).parent)
                
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
            self.last_image_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_paths:
            try:
                # Remember the directory from the first file
                self.last_image_dir = str(Path(file_paths[0]).parent)
                
                for file_path in file_paths:
                    self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                QMessageBox.information(self, "Success", 
                    f"Loaded {len(file_paths)} images!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load images:\n{str(e)}")
    
    def on_tiles_created(self, tiles):
        """
        Handle tiles created from tile splitter
        tiles: List[Tuple[Image, str]] - (tile_image, source_filename)
        """
        try:
            # Group tiles by source filename to number them per source
            from collections import defaultdict
            tile_counters = defaultdict(int)
            
            for tile_img, source_filename in tiles:
                tile_counters[source_filename] += 1
                tile_number = tile_counters[source_filename]
                # Create name like: "filename_tile_1", "filename_tile_2", etc.
                tile_name = f"{source_filename}_tile_{tile_number}"
                self.material_manager.add_material(tile_img, tile_name)
            
            self.refresh_materials_list()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add tiles:\n{str(e)}")
    
    def on_batch_complete(self, success_count: int, fail_count: int):
        """
        Handle batch processing completion
        
        Args:
            success_count: Number of successfully processed images
            fail_count: Number of failed images
        """
        # Currently just a placeholder - the batch processor widget handles the notification
        # Could add additional actions here if needed (e.g., logging, statistics)
        pass
    
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
            
            # Determine insertion position
            # If timeline has selected frames, insert after the last selected frame
            # Otherwise, append to the end
            timeline_selected_rows = sorted({idx.row() for idx in self.timeline.timeline_table.selectedIndexes()})
            
            if timeline_selected_rows:
                # Insert after the last selected row
                insert_position = timeline_selected_rows[-1] + 1
            else:
                # No selection, append to end
                insert_position = len(self.layered_sequence_editor)
            
            # Create a new LayeredFrame for each selected material
            frames_to_add = []
            for material_idx in selected_rows:
                new_frame = LayeredFrame(
                    duration=duration,
                    name=f"Frame {len(self.layered_sequence_editor) + len(frames_to_add) + 1}"
                )
                layer = Layer(material_index=material_idx, name="Layer 1")
                new_frame.add_layer(layer)
                frames_to_add.append(new_frame)
            
            # Insert frames at the determined position
            for i, frame in enumerate(frames_to_add):
                self.layered_sequence_editor.insert_frame(insert_position + i, frame)
            
            self.refresh_timeline()
            
            # Auto-select the newly added frames
            if len(frames_to_add) > 0:
                self.timeline.timeline_table.clearSelection()
                for i in range(len(frames_to_add)):
                    self.timeline.timeline_table.selectRow(insert_position + i)
        
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
            self.last_export_dir
        )
        
        if not export_dir:
            return
        
        try:
            # Remember the directory
            self.last_export_dir = export_dir
            
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
            self.last_export_dir
        )
        
        if not export_dir:
            return
        
        try:
            # Remember the directory
            self.last_export_dir = export_dir
            
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
            frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) 
                                   for item in selected_items 
                                   if item.data(Qt.ItemDataRole.UserRole) is not None})
            
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
        
        # Construct default path
        default_path = "output.gif"
        if self.last_export_dir:
            default_path = str(Path(self.last_export_dir) / "output.gif")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save GIF",
            default_path,
            "GIF Files (*.gif)"
        )
        
        if file_path:
            try:
                # Remember the directory
                self.last_export_dir = str(Path(file_path).parent)
                
                self.gif_builder.set_output_size(
                    self.width_spinbox.value(),
                    self.height_spinbox.value()
                )
                self.gif_builder.set_loop(self.loop_spinbox.value())
                
                # Set color palette
                color_count = int(self.color_palette_combo.currentText())
                self.gif_builder.set_color_count(color_count)
                
                if self.transparent_bg_checkbox.isChecked():
                    self.gif_builder.set_background_color(0, 0, 0, 0)
                else:
                    self.gif_builder.set_background_color(255, 255, 255, 255)
                
                self.gif_builder.build_from_layered_sequence(
                    self.layered_sequence_editor.get_frames(),
                    self.material_manager,
                    file_path
                )
                
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) 
                                for item in selected_items 
                                if item.data(Qt.ItemDataRole.UserRole) is not None})
        
        if not frame_indices:
            return
        
        # Copy all selected frames as a group and insert after the last selected frame
        # This produces: [1,2,3] -> [1,2,3,1,2,3] instead of [1,1,2,2,3,3]
        insert_position = frame_indices[-1] + 1
        num_duplicated = 0
        
        for frame_idx in frame_indices:
            if frame_idx < len(self.layered_sequence_editor):
                # Get the frame to duplicate
                original_frame = self.layered_sequence_editor.get_frame(frame_idx)
                if original_frame:
                    # Create a copy and insert at the insert position
                    duplicated_frame = original_frame.copy()
                    self.layered_sequence_editor.frames.insert(insert_position, duplicated_frame)
                    insert_position += 1
                    num_duplicated += 1
        
        self.refresh_timeline()
        
        # Auto-select all duplicated frames using selection model
        if num_duplicated > 0:
            selection_model = self.timeline.timeline_table.selectionModel()
            self.timeline.timeline_table.clearSelection()
            
            start_position = frame_indices[-1] + 1
            for i in range(num_duplicated):
                new_row = start_position + i
                for col in range(self.timeline.timeline_table.columnCount()):
                    index = self.timeline.timeline_table.model().index(new_row, col)
                    selection_model.select(index, QItemSelectionModel.SelectionFlag.Select)
    
    def remove_frame(self):
        """Remove selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to remove!")
            return
        
        # Get unique frame indices (selectedIndexes includes all cells, we need unique rows)
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) 
                               for item in selected_items 
                               if item.data(Qt.ItemDataRole.UserRole) is not None}, 
                              reverse=True)
        
        if not frame_indices:
            return
        
        # Remove frames in reverse order to avoid index shifting issues
        for frame_index in frame_indices:
            if 0 <= frame_index < len(self.layered_sequence_editor):
                self.layered_sequence_editor.remove_frame(frame_index)
        
        self.refresh_timeline()
    
    def move_frame_up(self):
        """Move selected frame(s) up (earlier in timeline)"""
        # Get unique selected row indices
        selected_rows = sorted({idx.row() for idx in self.timeline.timeline_table.selectedIndexes()})
        
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one frame to move!")
            return
        
        # Check if first selected frame is already at the top
        if selected_rows[0] == 0:
            return  # Cannot move up
        
        # Move frames up one position (process from top to bottom to avoid conflicts)
        for row in selected_rows:
            self.layered_sequence_editor.move_frame(row, row - 1)
        
        self.refresh_timeline()
        
        # Re-select the moved frames at their new positions using selection model
        selection_model = self.timeline.timeline_table.selectionModel()
        self.timeline.timeline_table.clearSelection()
        
        for row in selected_rows:
            new_row = row - 1
            for col in range(self.timeline.timeline_table.columnCount()):
                index = self.timeline.timeline_table.model().index(new_row, col)
                selection_model.select(index, QItemSelectionModel.SelectionFlag.Select)
    
    def move_frame_down(self):
        """Move selected frame(s) down (later in timeline)"""
        # Get unique selected row indices
        selected_rows = sorted({idx.row() for idx in self.timeline.timeline_table.selectedIndexes()})
        
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one frame to move!")
            return
        
        # Check if last selected frame is already at the bottom
        if selected_rows[-1] >= len(self.layered_sequence_editor) - 1:
            return  # Cannot move down
        
        # Move frames down one position (process from bottom to top to avoid conflicts)
        for row in reversed(selected_rows):
            self.layered_sequence_editor.move_frame(row, row + 1)
        
        self.refresh_timeline()
        
        # Re-select the moved frames at their new positions using selection model
        selection_model = self.timeline.timeline_table.selectionModel()
        self.timeline.timeline_table.clearSelection()
        
        for row in selected_rows:
            new_row = row + 1
            for col in range(self.timeline.timeline_table.columnCount()):
                index = self.timeline.timeline_table.model().index(new_row, col)
                selection_model.select(index, QItemSelectionModel.SelectionFlag.Select)
    
    def apply_batch_offset(self):
        """Apply offset to all layers in selected frames"""
        selected_items = self.timeline.timeline_table.selectedIndexes()
        
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames!")
            return
        
        # Get unique frame indices (selectedIndexes includes all cells, we need unique rows)
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) 
                               for item in selected_items 
                               if item.data(Qt.ItemDataRole.UserRole) is not None})
        
        if not frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        
        offset_x = self.batch_offset_x.value()
        offset_y = self.batch_offset_y.value()
        
        total_layers = 0
        for frame_index in frame_indices:
            if frame_index < len(self.layered_sequence_editor):
                frame = self.layered_sequence_editor.get_frame(frame_index)
                if frame:
                    for layer in frame.layers:
                        layer.x = offset_x
                        layer.y = offset_y
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
    
    def on_preview_frame_info_changed(self, current: int, total: int, duration: int):
        """Handle preview frame info change"""
        if total > 0:
            self.info_label.setText(f"Frame: {current}/{total} | Duration: {duration}ms")
        else:
            self.info_label.setText("Frame: 0/0")
    
    def on_preview_clicked(self):
        """Handle preview image click - switch to preview page"""
        # 將當前的幀資料傳遞給預覽頁面
        if hasattr(self.preview, 'frames') and self.preview.frames:
            self.preview_page.set_frames(self.preview.frames)
            self.show_preview_page()
    
    def on_transparent_bg_changed(self):
        """Handle transparent background checkbox change"""
        # Update preview with new transparency setting
        self.update_preview()
    
    def on_color_palette_changed(self):
        """Handle color palette selection change"""
        color_count = int(self.color_palette_combo.currentText())
        self.gif_builder.set_color_count(color_count)
        # Update preview with new color palette setting
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
            
            # Set color palette for preview
            color_count = int(self.color_palette_combo.currentText())
            self.gif_builder.set_color_count(color_count)
            
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
            
            # Set color palette for preview
            color_count = int(self.color_palette_combo.currentText())
            self.gif_builder.set_color_count(color_count)
            
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
    
    def export_template(self):
        """Export current timeline as a template"""
        if len(self.layered_sequence_editor) == 0:
            QMessageBox.warning(self, "Warning", "No frames to export as template!")
            return
        
        # Construct default path
        default_path = "timeline_template.json"
        if self.last_template_dir:
            default_path = str(Path(self.last_template_dir) / "timeline_template.json")
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            default_path,
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                # Remember the directory
                self.last_template_dir = str(Path(file_path).parent)
                
                # Export template
                color_count = int(self.color_palette_combo.currentText())
                template = TemplateManager.export_template(
                    self.layered_sequence_editor,
                    self.width_spinbox.value(),
                    self.height_spinbox.value(),
                    self.loop_spinbox.value(),
                    self.transparent_bg_checkbox.isChecked(),
                    len(self.material_manager),
                    color_count
                )
                
                # Save to file
                TemplateManager.save_template_to_file(template, file_path)
                
                # Show info
                info = TemplateManager.get_template_info(template)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Template saved successfully!\n\n"
                    f"Frames: {info['frame_count']}\n"
                    f"Materials used: {info['unique_materials_used']}/{info['material_count']}\n"
                    f"Total layers: {info['total_layers']}\n"
                    f"Duration: {info['total_duration_ms']}ms\n"
                    f"Output size: {info['output_size'][0]}x{info['output_size'][1]}\n\n"
                    f"File: {file_path}"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export template:\n{str(e)}")
    
    def import_template(self):
        """Import and apply a template"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Template",
            self.last_template_dir,
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            # Remember the directory
            self.last_template_dir = str(Path(file_path).parent)
            
            # Load template
            template = TemplateManager.load_template_from_file(file_path)
            
            # Get template info
            info = TemplateManager.get_template_info(template)
            
            # Check if we have enough materials
            materials_needed = info['unique_materials_used']
            materials_available = len(self.material_manager)
            
            if materials_available == 0:
                QMessageBox.warning(
                    self,
                    "Warning",
                    f"No materials loaded!\n\n"
                    f"This template requires {materials_needed} materials.\n"
                    f"Please load materials first before importing a template."
                )
                return
            
            # Show template info and ask for confirmation
            reply = QMessageBox.question(
                self,
                "Import Template",
                f"Template Info:\n"
                f"• Frames: {info['frame_count']}\n"
                f"• Materials needed: {materials_needed}\n"
                f"• Total layers: {info['total_layers']}\n"
                f"• Duration: {info['total_duration_ms']}ms\n"
                f"• Output size: {info['output_size'][0]}x{info['output_size'][1]}\n\n"
                f"Available materials: {materials_available}\n\n"
                f"Import Method:\n"
                f"• Use First N: Uses first {materials_needed} materials in order\n"
                f"• Use Selected: Uses selected materials (must select {materials_needed} materials)\n\n"
                f"Choose import method:",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            
            # Determine material mapping
            material_mapping = {}
            
            if reply == QMessageBox.StandardButton.Yes:
                # Use first N materials
                if materials_available < materials_needed:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        f"Not enough materials!\n\n"
                        f"Template needs {materials_needed} materials, but only {materials_available} available.\n"
                        f"Please load more materials first."
                    )
                    return
                
                # Create 1:1 mapping for first N materials
                for i in range(materials_needed):
                    material_mapping[i] = i
                    
            else:  # No = Use Selected
                # Get selected materials
                selected_rows = sorted([item.row() for item in self.materials_list.selectedIndexes()])
                
                if len(selected_rows) != materials_needed:
                    QMessageBox.warning(
                        self,
                        "Warning",
                        f"Please select exactly {materials_needed} materials!\n\n"
                        f"Currently selected: {len(selected_rows)}\n"
                        f"Required: {materials_needed}"
                    )
                    return
                
                # Create mapping from template indices to selected material indices
                for template_idx in range(materials_needed):
                    material_mapping[template_idx] = selected_rows[template_idx]
            
            # Apply template
            new_editor, settings = TemplateManager.apply_template(template, material_mapping)
            
            # Replace current sequence
            self.layered_sequence_editor = new_editor
            
            # Apply settings
            if settings:
                self.width_spinbox.setValue(settings.get('output_width', 400))
                self.height_spinbox.setValue(settings.get('output_height', 400))
                self.loop_spinbox.setValue(settings.get('loop_count', 0))
                self.transparent_bg_checkbox.setChecked(settings.get('transparent_bg', False))
                
                # Apply color palette setting
                color_count = settings.get('color_count', 256)
                self.color_palette_combo.setCurrentText(str(color_count))
                self.gif_builder.set_color_count(color_count)
            
            # Refresh UI
            self.refresh_timeline()
            self.update_preview()
            
            QMessageBox.information(
                self,
                "Success",
                f"Template imported successfully!\n\n"
                f"Created {info['frame_count']} frames with {info['total_layers']} total layers."
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to import template:\n{str(e)}")
    
    def quick_save_template(self):
        """Quick save current timeline as template"""
        if len(self.layered_sequence_editor) == 0:
            QMessageBox.warning(self, "Warning", "No frames to save as template!")
            return
        
        from PyQt6.QtWidgets import QInputDialog
        
        # Ask for template name
        name, ok = QInputDialog.getText(
            self,
            "Save Template",
            "Template name:",
            text=f"Template_{len(self.templates) + 1}"
        )
        
        if ok and name:
            try:
                # Create template
                color_count = int(self.color_palette_combo.currentText())
                template = TemplateManager.export_template(
                    self.layered_sequence_editor,
                    self.width_spinbox.value(),
                    self.height_spinbox.value(),
                    self.loop_spinbox.value(),
                    self.transparent_bg_checkbox.isChecked(),
                    len(self.material_manager),
                    color_count
                )
                
                # Store template
                self.templates[name] = template
                
                # Update list
                self.refresh_template_list()
                
                # Select the newly added template
                items = self.template_list.findItems(name, Qt.MatchFlag.MatchExactly)
                if items:
                    self.template_list.setCurrentItem(items[0])
                
                info = TemplateManager.get_template_info(template)
                QMessageBox.information(
                    self,
                    "Success",
                    f"Template '{name}' saved!\n\n"
                    f"Frames: {info['frame_count']}\n"
                    f"Materials: {info['unique_materials_used']}\n"
                    f"Total layers: {info['total_layers']}"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save template:\n{str(e)}")
    
    def quick_apply_template(self):
        """Quick apply selected template"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to apply!")
            return
        
        template_name = current_item.text().split(" - ")[0]  # Extract name before " - "
        if template_name not in self.templates:
            QMessageBox.warning(self, "Warning", "Template not found!")
            return
        
        template = self.templates[template_name]
        
        try:
            # Get template info
            info = TemplateManager.get_template_info(template)
            materials_needed = info['unique_materials_used']
            materials_available = len(self.material_manager)
            
            if materials_available < materials_needed:
                QMessageBox.warning(
                    self,
                    "Warning",
                    f"Not enough materials!\n\n"
                    f"Template needs: {materials_needed}\n"
                    f"Available: {materials_available}\n\n"
                    f"Please load more materials first."
                )
                return
            
            # Apply template using first N materials
            material_mapping = {i: i for i in range(materials_needed)}
            new_editor, settings = TemplateManager.apply_template(template, material_mapping)
            
            # Replace current sequence
            self.layered_sequence_editor = new_editor
            
            # Apply settings
            if settings:
                self.width_spinbox.setValue(settings.get('output_width', 400))
                self.height_spinbox.setValue(settings.get('output_height', 400))
                self.loop_spinbox.setValue(settings.get('loop_count', 0))
                self.transparent_bg_checkbox.setChecked(settings.get('transparent_bg', False))
                
                # Apply color palette setting
                color_count = settings.get('color_count', 256)
                self.color_palette_combo.setCurrentText(str(color_count))
                self.gif_builder.set_color_count(color_count)
            
            # Refresh UI
            self.refresh_timeline()
            self.update_preview()
            
            QMessageBox.information(
                self,
                "Success",
                f"Template '{template_name}' applied!\n\n"
                f"Created {info['frame_count']} frames."
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to apply template:\n{str(e)}")
    
    def quick_import_template(self):
        """Quick import template from file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Template",
            self.last_template_dir,
            "JSON Files (*.json)"
        )
        
        if not file_path:
            return
        
        try:
            # Remember the directory
            self.last_template_dir = str(Path(file_path).parent)
            
            # Load template
            template = TemplateManager.load_template_from_file(file_path)
            
            # Get template name from filename
            template_name = Path(file_path).stem
            
            # Check if name already exists, add number if needed
            original_name = template_name
            counter = 1
            while template_name in self.templates:
                template_name = f"{original_name}_{counter}"
                counter += 1
            
            # Store template
            self.templates[template_name] = template
            
            # Refresh list
            self.refresh_template_list()
            
            # Select the newly imported template
            items = self.template_list.findItems(template_name, Qt.MatchFlag.MatchContains)
            if items:
                self.template_list.setCurrentItem(items[0])
            
            info = TemplateManager.get_template_info(template)
            QMessageBox.information(
                self,
                "Success",
                f"Template '{template_name}' imported!\n\n"
                f"Frames: {info['frame_count']}\n"
                f"Materials needed: {info['unique_materials_used']}"
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to import template:\n{str(e)}")
    
    def quick_export_template(self):
        """Quick export selected template to file"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to export!")
            return
        
        template_name = current_item.text().split(" - ")[0]
        if template_name not in self.templates:
            QMessageBox.warning(self, "Warning", "Template not found!")
            return
        
        template = self.templates[template_name]
        
        # Construct default path
        default_filename = f"{template_name}.json"
        default_path = default_filename
        if self.last_template_dir:
            default_path = str(Path(self.last_template_dir) / default_filename)
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Template",
            default_path,
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                # Remember the directory
                self.last_template_dir = str(Path(file_path).parent)
                
                # Save to file
                TemplateManager.save_template_to_file(template, file_path)
                
                QMessageBox.information(
                    self,
                    "Success",
                    f"Template '{template_name}' exported!\n\n"
                    f"File: {file_path}"
                )
                
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export template:\n{str(e)}")
    
    def remove_template(self):
        """Remove selected template from list"""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to remove!")
            return
        
        template_name = current_item.text().split(" - ")[0]
        if template_name not in self.templates:
            return
        
        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Remove template '{template_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.templates[template_name]
            self.refresh_template_list()
    
    def refresh_template_list(self):
        """Refresh template list widget"""
        self.template_list.clear()
        
        for name, template in self.templates.items():
            info = TemplateManager.get_template_info(template)
            item_text = f"{name} - {info['frame_count']} frames, {info['unique_materials_used']} mats"
            self.template_list.addItem(item_text)
        
        # Update batch processor templates
        if hasattr(self, 'batch_processor'):
            self.batch_processor.set_templates(self.templates)
    
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
            "<li>Export and import timeline templates</li>"
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

