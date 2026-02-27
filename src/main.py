import sys
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
                              QComboBox, QStackedWidget, QColorDialog, QInputDialog)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image
from collections import Counter

from .core import MaterialManager, GifBuilder, TemplateManager, GroupManager, CompositionGroup, FrameEntry, SubGroupEntry
from .widgets import AppTheme, PreviewWidget, PreviewPageWidget, TileEditorWidget, BatchProcessorWidget, GifOptimizerWidget, GroupCompositionWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.material_manager = MaterialManager()
        self.group_manager = GroupManager()
        self.gif_builder = GifBuilder()
        self.current_group_id: Optional[int] = None
        # Ensure root group exists for group-led composition
        if len(self.group_manager.groups) == 0:
            root = CompositionGroup(name="Root")
            self.group_manager.add_group(root)
        self.current_group_id = self.group_manager.get_root_group_id()
        
        # Remember last used directories
        self.last_image_dir = ""
        self.last_gif_dir = ""
        self.last_export_dir = ""
        self.last_template_dir = ""
        
        # Template storage: {name: template_dict}
        self.templates = {}
        
        self.auto_save_enabled = False
        self.auto_save_interval = 5 * 60 * 1000  # 5 minutes in milliseconds
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save_template)
        
        # Auto-save directory
        self.auto_save_dir = Path.home() / ".gif_maker" / "auto_save"
        self.auto_save_dir.mkdir(parents=True, exist_ok=True)
        
        # Fixed auto-save filename (always overwrite the same file)
        self.auto_save_file = self.auto_save_dir / "auto_save_latest.json"
        
        # Track last auto-save time to avoid duplicate saves
        self.last_auto_save_content_hash = None
        
        self.init_ui()
        self.setWindowTitle("GIF Maker")
        self.resize(1600, 950)
        # Default preview background color (neutral dark for dark theme)
        self.preview_bg_color = "#2a2e3c"
        
        # Chroma key state
        self.chroma_key_colors = []  # List of (color_rgb, percentage, display_name) tuples
        self.chroma_key_colors_all = []  # All analyzed colors
        self.chroma_key_display_count = 10  # Number of colors to display at once
    
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
        # Apply default preview background to both preview areas
        if hasattr(self, 'preview'):
            try:
                self.preview.set_background_color(self.preview_bg_color)
            except Exception:
                pass
        try:
            self.preview_page.set_background_color(self.preview_bg_color)
        except Exception:
            pass
    
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
        splitter.setSizes([400, 800, 400])
        
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
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
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

        # GIF Optimizer tab (Lossy)
        self.gif_optimizer = GifOptimizerWidget()
        optimizer_scroll_area = QScrollArea()
        optimizer_scroll_area.setWidget(self.gif_optimizer)
        optimizer_scroll_area.setWidgetResizable(True)
        tabs.addTab(optimizer_scroll_area, "GIF Optimizer")
        
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
        
        lib_header_row = QHBoxLayout()
        list_label = QLabel("Material Library")
        list_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        lib_header_row.addWidget(list_label)
        lib_header_row.addStretch()
        self.material_view_btn = QPushButton("⊞ Grid")
        self.material_view_btn.setFixedSize(58, 22)
        self.material_view_btn.setToolTip("Switch between list and grid (icon) view")
        self.material_view_btn.setCheckable(True)
        self.material_view_btn.clicked.connect(self._toggle_material_view)
        lib_header_row.addWidget(self.material_view_btn)
        layout.addLayout(lib_header_row)

        self._material_icon_mode = False  # False = list, True = icon/grid

        # Sorting controls for materials
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("Sort:"))
        self.material_sort_combo = QComboBox()
        self.material_sort_combo.addItems([
            "Default",
            "Name (A→Z)",
            "Name (Z→A)",
            "Width (Large→Small)",
            "Height (Large→Small)",
        ])
        self.material_sort_combo.currentIndexChanged.connect(self.refresh_materials_list)
        sort_row.addWidget(self.material_sort_combo)
        sort_row.addStretch()
        layout.addLayout(sort_row)
        
        self.materials_list = QListWidget()
        self.materials_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.materials_list.setIconSize(QSize(64, 64))
        self.materials_list.setViewMode(QListWidget.ViewMode.ListMode)
        layout.addWidget(self.materials_list)
        
        material_actions = QHBoxLayout()

        self.remove_material_btn = QPushButton("Remove Selected")
        self.remove_material_btn.clicked.connect(self.remove_selected_material)
        material_actions.addWidget(self.remove_material_btn)

        self.clear_materials_btn2 = QPushButton("Clear All")
        self.clear_materials_btn2.clicked.connect(self.clear_materials)
        material_actions.addWidget(self.clear_materials_btn2)

        layout.addLayout(material_actions)

        # Group addition buttons
        group_add_layout = QVBoxLayout()
        group_add_layout.setSpacing(4)

        self.add_to_existing_group_btn = QPushButton("➕ Add to Selected Group")
        self.add_to_existing_group_btn.setToolTip("Add selected materials to the currently selected group")
        self.add_to_existing_group_btn.clicked.connect(self.add_materials_to_existing_group)
        group_add_layout.addWidget(self.add_to_existing_group_btn)

        self.add_as_single_group_btn = QPushButton("📦 Add as New Group (Merge)")
        self.add_as_single_group_btn.setToolTip("Combine selected materials into a single new group and add to timeline")
        self.add_as_single_group_btn.clicked.connect(self.add_materials_as_single_group)
        group_add_layout.addWidget(self.add_as_single_group_btn)

        self.add_each_as_group_btn = QPushButton("📦📦 Add Each as Group")
        self.add_each_as_group_btn.setToolTip("Create a separate group for each selected material and add to timeline")
        self.add_each_as_group_btn.clicked.connect(self.add_materials_as_separate_groups)
        group_add_layout.addWidget(self.add_each_as_group_btn)

        layout.addLayout(group_add_layout)
        
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
        title = QLabel("Composition (Groups)")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
        layout.addWidget(title)
        self.group_composition_widget = GroupCompositionWidget()
        self.group_composition_widget.set_group_manager(self.group_manager)
        self.group_composition_widget.set_material_manager(self.material_manager)
        self.group_composition_widget.set_get_selected_material_indices(self._get_selected_material_indices)
        self.group_composition_widget.current_group_changed.connect(self._on_current_group_changed)
        self.group_composition_widget.entries_changed.connect(self._on_group_entries_changed)
        layout.addWidget(self.group_composition_widget, stretch=1)
        panel.setLayout(layout)
        return panel

    def _get_selected_material_indices(self) -> List[int]:
        """Return list of selected material indices from the materials list (for Add Frame)."""
        indices = []
        for item in self.materials_list.selectedItems():
            row = self.materials_list.row(item)
            if 0 <= row < len(self.material_manager):
                indices.append(row)
        return sorted(indices)

    def _on_current_group_changed(self, group_id: int):
        self.current_group_id = group_id
        self.update_preview()

    def _on_group_entries_changed(self):
        self.update_preview()
    
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
        self.preview_frame_spinbox.valueChanged.connect(self.update_preview)
        preview_controls.addWidget(self.preview_frame_spinbox)
        
        self.preview_all_checkbox = QCheckBox("Preview All (Animation)")
        self.preview_all_checkbox.setChecked(True)
        self.preview_all_checkbox.stateChanged.connect(self.on_preview_mode_changed)
        preview_controls.addWidget(self.preview_all_checkbox)
        preview_controls.addStretch()

        # Preview background color (preview-only)
        self.preview_bg_btn = QPushButton("Preview BG")
        self.preview_bg_btn.setToolTip("Set preview background color (does not affect export)")
        self.preview_bg_btn.clicked.connect(self.on_choose_preview_bg)
        preview_controls.addWidget(self.preview_bg_btn)

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
        
        # Chroma key (green screen) selection
        chroma_layout = QHBoxLayout()
        chroma_layout.addWidget(QLabel("Chroma Key:"))
        self.chroma_key_combo = QComboBox()
        self.chroma_key_combo.addItem("None (Disabled)")
        self.chroma_key_combo.setToolTip("Select a color to make transparent (green screen effect)")
        self.chroma_key_combo.currentIndexChanged.connect(self.on_chroma_key_changed)
        self.chroma_key_combo.setMinimumWidth(150)
        chroma_layout.addWidget(self.chroma_key_combo)
        
        self.analyze_colors_btn = QPushButton("🔍")
        self.analyze_colors_btn.setMaximumWidth(30)
        self.analyze_colors_btn.setToolTip("Analyze colors from first frame")
        self.analyze_colors_btn.clicked.connect(self.analyze_first_frame_colors)
        chroma_layout.addWidget(self.analyze_colors_btn)
        
        self.show_more_colors_btn = QPushButton("+10")
        self.show_more_colors_btn.setMaximumWidth(40)
        self.show_more_colors_btn.setToolTip("Show 10 more color options")
        self.show_more_colors_btn.clicked.connect(self.show_more_colors)
        self.show_more_colors_btn.setEnabled(False)
        chroma_layout.addWidget(self.show_more_colors_btn)
        
        chroma_layout.addStretch()
        settings_layout.addLayout(chroma_layout)
        
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group, stretch=0)
        
        # Auto Layout section
        auto_layout_group = QGroupBox("Auto Layout")
        auto_layout_layout = QVBoxLayout()
        auto_layout_layout.setSpacing(3)
        
        # Auto fit size button
        self.auto_fit_size_btn = QPushButton("🔧 Auto Fit Size")
        self.auto_fit_size_btn.clicked.connect(self.auto_fit_output_size)
        self.auto_fit_size_btn.setToolTip("Automatically adjust output size to fit all materials")
        auto_layout_layout.addWidget(self.auto_fit_size_btn)
        
        # Horizontal alignment buttons
        h_align_label = QLabel("Horizontal:")
        h_align_label.setStyleSheet("font-size: 10px; color: #9ba8c0;")
        auto_layout_layout.addWidget(h_align_label)
        
        h_align_layout = QHBoxLayout()
        self.align_left_btn = QPushButton("⬅ Left")
        self.align_left_btn.clicked.connect(self.align_all_left)
        self.align_left_btn.setToolTip("Align all materials to the left")
        h_align_layout.addWidget(self.align_left_btn)
        
        self.align_center_h_btn = QPushButton("↔ Center")
        self.align_center_h_btn.clicked.connect(self.align_all_center_horizontal)
        self.align_center_h_btn.setToolTip("Center all materials horizontally")
        h_align_layout.addWidget(self.align_center_h_btn)
        
        self.align_right_btn = QPushButton("➡ Right")
        self.align_right_btn.clicked.connect(self.align_all_right)
        self.align_right_btn.setToolTip("Align all materials to the right")
        h_align_layout.addWidget(self.align_right_btn)
        
        auto_layout_layout.addLayout(h_align_layout)
        
        # Vertical alignment buttons
        v_align_label = QLabel("Vertical:")
        v_align_label.setStyleSheet("font-size: 10px; color: #9ba8c0;")
        auto_layout_layout.addWidget(v_align_label)
        
        v_align_layout = QHBoxLayout()
        self.align_top_btn = QPushButton("⬆ Top")
        self.align_top_btn.clicked.connect(self.align_all_top)
        self.align_top_btn.setToolTip("Align all materials to the top")
        v_align_layout.addWidget(self.align_top_btn)
        
        self.align_middle_btn = QPushButton("↕ Middle")
        self.align_middle_btn.clicked.connect(self.align_all_middle_vertical)
        self.align_middle_btn.setToolTip("Center all materials vertically")
        v_align_layout.addWidget(self.align_middle_btn)
        
        self.align_bottom_btn = QPushButton("⬇ Bottom")
        self.align_bottom_btn.clicked.connect(self.align_all_bottom)
        self.align_bottom_btn.setToolTip("Align all materials to the bottom")
        v_align_layout.addWidget(self.align_bottom_btn)
        
        auto_layout_layout.addLayout(v_align_layout)
        
        auto_layout_group.setLayout(auto_layout_layout)
        layout.addWidget(auto_layout_group, stretch=0)
        
        # Action buttons (compact)
        self.update_preview_btn = QPushButton("🔄 Preview")
        self.update_preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(self.update_preview_btn)
        
        self.export_gif_btn = QPushButton("💾 Export GIF")
        self.export_gif_btn.clicked.connect(self.export_gif)
        self.export_gif_btn.setStyleSheet(
            "font-weight: bold; font-size: 13px; background-color: #2d6a3f; "
            "color: #d4f5db; border: 1px solid #3d8a52; border-radius: 4px; padding: 5px 14px;"
        )
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
        
        # Auto-save menu items
        auto_save_menu = file_menu.addMenu("Auto-Save")
        auto_save_menu.addAction("Restore Auto-Save", self.restore_auto_save)
        auto_save_menu.addAction("Toggle Auto-Save", self.toggle_auto_save)
        
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
    
    def _toggle_material_view(self, checked: bool):
        self._material_icon_mode = checked
        self.material_view_btn.setText("☰ List" if checked else "⊞ Grid")
        self.refresh_materials_list()

    def refresh_materials_list(self):
        self.materials_list.clear()

        # Determine sort order
        indices = list(range(len(self.material_manager)))
        sort_mode = getattr(self, 'material_sort_combo', None).currentText() if hasattr(self, 'material_sort_combo') else "Default"

        def get_name(idx):
            m = self.material_manager.get_material(idx)
            return m[1] if m else ""

        def get_size(idx):
            m = self.material_manager.get_material(idx)
            if not m:
                return (0, 0)
            img = m[0]
            return (img.width, img.height)

        if sort_mode == "Name (A→Z)":
            indices.sort(key=lambda i: get_name(i).lower())
        elif sort_mode == "Name (Z→A)":
            indices.sort(key=lambda i: get_name(i).lower(), reverse=True)
        elif sort_mode == "Width (Large→Small)":
            indices.sort(key=lambda i: get_size(i)[0], reverse=True)
        elif sort_mode == "Height (Large→Small)":
            indices.sort(key=lambda i: get_size(i)[1], reverse=True)
        # else Default keeps original order

        icon_mode = getattr(self, '_material_icon_mode', False)
        if icon_mode:
            self.materials_list.setViewMode(QListWidget.ViewMode.IconMode)
            self.materials_list.setIconSize(QSize(80, 80))
            self.materials_list.setGridSize(QSize(100, 110))
            self.materials_list.setResizeMode(QListWidget.ResizeMode.Adjust)
            self.materials_list.setWordWrap(True)
            self.materials_list.setSpacing(4)
        else:
            self.materials_list.setViewMode(QListWidget.ViewMode.ListMode)
            self.materials_list.setIconSize(QSize(64, 64))
            self.materials_list.setGridSize(QSize())
            self.materials_list.setSpacing(0)

        for i in indices:
            mat = self.material_manager.get_material(i)
            if not mat:
                continue
            img, name = mat
            if icon_mode:
                thumbnail = self.create_thumbnail(img, 80, 80)
                icon = QIcon(thumbnail)
                short_name = name if len(name) <= 12 else name[:11] + "…"
                item = QListWidgetItem(icon, short_name)
                item.setToolTip(f"[{i}] {name}\n{img.width}×{img.height}")
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                item.setSizeHint(QSize(96, 106))
            else:
                thumbnail = self.create_thumbnail(img, 64, 64)
                icon = QIcon(thumbnail)
                item = QListWidgetItem(icon, f"[{i}] {name} ({img.width}x{img.height})")
                item.setSizeHint(QSize(200, 70))
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.materials_list.addItem(item)
    
    def create_thumbnail(self, pil_image, width, height):
        img_copy = pil_image.copy()
        img_copy.thumbnail((width, height), Image.Resampling.LANCZOS)
        
        if img_copy.mode != 'RGBA':
            img_copy = img_copy.convert('RGBA')
        
        data = img_copy.tobytes('raw', 'RGBA')
        qimage = QImage(data, img_copy.width, img_copy.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimage)

    def remove_selected_material(self):
        # Map selected view rows to underlying material indices
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
        selected_rows = sorted(selected_rows, reverse=True)
        if selected_rows:
            for row in selected_rows:
                self.material_manager.remove_material(row)
            self.refresh_materials_list()
        else:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
    
    def add_materials_to_existing_group(self):
        """Add selected materials as FrameEntry to an existing group (group-led model)."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        groups = self.group_manager.get_all_groups()
        if not groups:
            QMessageBox.information(self, "Info", "Create a group first (e.g. Add as New Group).")
            return
        names = [g.name for g in groups]
        item, ok = QInputDialog.getItem(self, "Add to Group", "Select group to add materials to:", names, 0, False)
        if not ok:
            return
        idx = names.index(item)
        group = self.group_manager.get_group(idx)
        if not group:
            return
        original = len(group.entries)
        for m in material_indices:
            group.entries.append(FrameEntry(material_index=m, x=0, y=0))
        self.group_manager.update_group(idx, group)
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Added {len(material_indices)} frame(s) to group '{group.name}' (now {len(group.entries)} entries).")
    
    def add_materials_as_single_group(self):
        """Create a new CompositionGroup from selected materials and add as SubGroupEntry to current group."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        name, ok = QInputDialog.getText(self, "New Group", "Group name:", text=f"Group_{len(material_indices)}")
        if not ok:
            return
        comp_group = CompositionGroup(
            name=name or f"Group_{len(material_indices)}",
            entries=[FrameEntry(material_index=m, x=0, y=0) for m in material_indices],
            default_duration_ms=100,
        )
        group_idx = self.group_manager.add_group(comp_group)
        if self.current_group_id is not None:
            current = self.group_manager.get_group(self.current_group_id)
            if current:
                current.entries.append(SubGroupEntry(group_id=group_idx, loop_count=1))
                self.group_manager.update_group(self.current_group_id, current)
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Created group '{comp_group.name}' and added to current group.")
    
    def add_materials_as_separate_groups(self):
        """Create one CompositionGroup per selected material and add each as SubGroupEntry to current group."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "Select a group in the Composition panel first.")
            return
        current = self.group_manager.get_group(self.current_group_id)
        if not current:
            return
        for mat_idx in material_indices:
            mat_name = f"Material_{mat_idx}"
            mat = self.material_manager.get_material(mat_idx)
            if mat:
                _, mat_name = mat
            comp_group = CompositionGroup(
                name=mat_name,
                entries=[FrameEntry(material_index=mat_idx, x=0, y=0)],
                default_duration_ms=100,
            )
            group_idx = self.group_manager.add_group(comp_group)
            current.entries.append(SubGroupEntry(group_id=group_idx, loop_count=1))
        self.group_manager.update_group(self.current_group_id, current)
        self.refresh_timeline()
        self.update_preview()
        
        QMessageBox.information(
            self,
            "Success",
            f"Created {len(material_indices)} group(s) (one per material) and added to timeline."
        )
    
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
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
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
    
    def export_gif(self):
        """Export GIF from the currently selected group."""
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "No group selected to export!")
            return
        if self.group_manager.get_group(self.current_group_id) is None:
            QMessageBox.warning(self, "Warning", "Selected group not found!")
            return

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
                self.last_export_dir = str(Path(file_path).parent)
                self.gif_builder.set_output_size(
                    self.width_spinbox.value(),
                    self.height_spinbox.value()
                )
                self.gif_builder.set_loop(self.loop_spinbox.value())
                color_count = int(self.color_palette_combo.currentText())
                self.gif_builder.set_color_count(color_count)
                if self.transparent_bg_checkbox.isChecked():
                    self.gif_builder.set_background_color(0, 0, 0, 0)
                else:
                    self.gif_builder.set_background_color(255, 255, 255, 255)
                self.gif_builder.build_gif_from_group(
                    self.current_group_id,
                    self.group_manager,
                    self.material_manager,
                    file_path,
                )
                QMessageBox.information(self, "Success", "GIF exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export GIF:\n{str(e)}")
    
    def _get_current_group(self) -> Optional["CompositionGroup"]:
        """Return the currently selected CompositionGroup, or None."""
        if self.current_group_id is None:
            return None
        return self.group_manager.get_group(self.current_group_id)

    def _align_current_group_entries(self, apply_fn) -> int:
        """Apply apply_fn(entry, mat_size) to every FrameEntry in the current group.
        Returns the number of entries modified."""
        group = self._get_current_group()
        if group is None:
            return 0
        count = 0
        for entry in group.entries:
            if isinstance(entry, FrameEntry):
                mat = self.material_manager.get_material(entry.material_index)
                if mat:
                    apply_fn(entry, mat[0].size)
                    count += 1
        return count

    def get_all_materials_max_size(self) -> Tuple[int, int]:
        """Return max (width, height) of all FrameEntry materials in the current group."""
        group = self._get_current_group()
        if group is None:
            return (0, 0)
        max_w = max_h = 0
        for entry in group.entries:
            if isinstance(entry, FrameEntry):
                mat = self.material_manager.get_material(entry.material_index)
                if mat:
                    w, h = mat[0].size
                    max_w = max(max_w, w)
                    max_h = max(max_h, h)
        return (max_w, max_h)
    
    def auto_fit_output_size(self):
        """Automatically adjust output size to fit all materials."""
        max_width, max_height = self.get_all_materials_max_size()
        
        if max_width == 0 or max_height == 0:
            QMessageBox.warning(
                self,
                "Warning",
                "No materials found in timeline!\nPlease add materials to frames first."
            )
            return
        
        # Set the spinbox values
        self.width_spinbox.setValue(max_width)
        self.height_spinbox.setValue(max_height)
        
        # Update preview
        self.update_preview()
        
        QMessageBox.information(
            self,
            "Success",
            f"Output size adjusted to {max_width} × {max_height}"
        )
    
    def align_all_left(self):
        """Align all frame entries in the current group to x = 0."""
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'x', 0))
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Aligned {count} frame(s) to the left")
    
    def align_all_center_horizontal(self):
        """Center all frame entries in the current group horizontally."""
        out_w = self.width_spinbox.value()
        def _fn(e, sz):
            e.x = (out_w - sz[0]) // 2
        count = self._align_current_group_entries(_fn)
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Centered {count} frame(s) horizontally")
    
    def align_all_right(self):
        """Align all frame entries in the current group to the right."""
        out_w = self.width_spinbox.value()
        def _fn(e, sz):
            e.x = out_w - sz[0]
        count = self._align_current_group_entries(_fn)
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Aligned {count} frame(s) to the right")
    
    def align_all_top(self):
        """Align all frame entries in the current group to y = 0."""
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'y', 0))
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Aligned {count} frame(s) to the top")
    
    def align_all_middle_vertical(self):
        """Center all frame entries in the current group vertically."""
        out_h = self.height_spinbox.value()
        def _fn(e, sz):
            e.y = (out_h - sz[1]) // 2
        count = self._align_current_group_entries(_fn)
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Centered {count} frame(s) vertically")
    
    def align_all_bottom(self):
        """Align all frame entries in the current group to the bottom."""
        out_h = self.height_spinbox.value()
        def _fn(e, sz):
            e.y = out_h - sz[1]
        count = self._align_current_group_entries(_fn)
        if count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in the selected group!")
            return
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Aligned {count} frame(s) to the bottom")
    
    def refresh_timeline(self):
        """Refresh group composition widget (group-led model)."""
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            self.group_composition_widget.refresh_groups_list()
            self.group_composition_widget.refresh_entries_list()
        return
    
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
            # Keep preview page background consistent
            try:
                self.preview_page.set_background_color(self.preview_bg_color)
            except Exception:
                pass
            self.show_preview_page()

    def on_choose_preview_bg(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.preview_bg_color = color.name()
            try:
                self.preview.set_background_color(color)
            except Exception:
                pass
            try:
                self.preview_page.set_background_color(color)
            except Exception:
                pass
    
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
        """Handle preview mode change (group-led: single frame vs full animation)."""
        if self.preview_all_checkbox.isChecked():
            self.preview_frame_spinbox.setEnabled(False)
        else:
            self.preview_frame_spinbox.setEnabled(True)
        self.update_preview()

    def update_single_frame_preview(self):
        """Update preview for a single frame (delegates to update_preview; group-led model)."""
        self.update_preview()
    
    def update_preview(self):
        """Update preview from the currently selected group."""
        if self.current_group_id is None:
            return
        if self.group_manager.get_group(self.current_group_id) is None:
            return
        try:
            self.gif_builder.set_output_size(
                self.width_spinbox.value(),
                self.height_spinbox.value()
            )
            self.gif_builder.set_loop(self.loop_spinbox.value())
            color_count = int(self.color_palette_combo.currentText())
            self.gif_builder.set_color_count(color_count)
            if self.transparent_bg_checkbox.isChecked():
                self.gif_builder.set_background_color(0, 0, 0, 0)
            else:
                self.gif_builder.set_background_color(255, 255, 255, 255)
            frames = self.gif_builder.get_preview_frames_for_group(
                self.current_group_id,
                self.group_manager,
                self.material_manager,
            )
            self.preview_frame_spinbox.setMaximum(max(1, len(frames)))
            if not self.preview_all_checkbox.isChecked():
                idx = self.preview_frame_spinbox.value() - 1
                if 0 <= idx < len(frames):
                    self.preview.set_frames([frames[idx]])
                else:
                    self.preview.set_frames(frames[:1] if frames else [])
                return
            self.preview.set_frames(frames)
        except Exception as e:
            print(f"ERROR in update_preview: {e}")
            import traceback
            traceback.print_exc()
    
    def quick_save_template(self):
        """Save current group composition to in-memory template list."""
        if len(self.group_manager.groups) == 0:
            QMessageBox.warning(self, "Warning", "No groups to save as template!")
            return
        try:
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_composition_template(
                self.group_manager,
                self.transparent_bg_checkbox.isChecked(),
                color_count,
            )
            timestamp = datetime.now().strftime("%H:%M:%S")
            name = f"Template {len(self.templates) + 1} ({timestamp})"
            self.templates[name] = template
            self.refresh_template_list()
            info = TemplateManager.get_template_info(template)
            QMessageBox.information(
                self, "Saved",
                f"Saved template '{name}'.\n"
                f"Groups: {info['group_count']}  |  "
                f"Materials needed: {info['materials_needed']}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save template: {str(e)}")
    
    def quick_apply_template(self):
        """Apply selected in-memory template to current composition."""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to apply!")
            return
        template_name = current_item.text().split(" - ")[0]
        template = self.templates.get(template_name)
        if not template:
            QMessageBox.warning(self, "Warning", "Selected template not found!")
            return
        try:
            new_gm, settings = TemplateManager.import_composition_template(template)
            self.group_manager = new_gm
            if settings:
                self.transparent_bg_checkbox.setChecked(
                    settings.get("transparent_bg", self.transparent_bg_checkbox.isChecked())
                )
                color_count = settings.get("color_count", int(self.color_palette_combo.currentText()))
                self.color_palette_combo.setCurrentText(str(color_count))
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            self.update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply template: {str(e)}")
    
    def quick_import_template(self):
        """Import a composition template JSON from disk into in-memory templates."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Template", self.last_template_dir, "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            template = TemplateManager.load_template_from_file(file_path)
            TemplateManager.validate_template(template)
            name = Path(file_path).stem
            suffix = 1
            unique_name = name
            while unique_name in self.templates:
                suffix += 1
                unique_name = f"{name} ({suffix})"
            self.templates[unique_name] = template
            self.refresh_template_list()
            QMessageBox.information(self, "Imported", f"Imported template '{unique_name}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import template: {str(e)}")
    
    def quick_export_template(self):
        """Export selected in-memory template to a JSON file."""
        current_item = self.template_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a template to export!")
            return
        template_name = current_item.text().split(" - ")[0]
        template = self.templates.get(template_name)
        if not template:
            QMessageBox.warning(self, "Warning", "Selected template not found!")
            return
        default_path = str(Path(self.last_template_dir or ".") / f"{template_name}.json")
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Template",
            default_path,
            "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            TemplateManager.save_template_to_file(template, file_path)
            QMessageBox.information(self, "Success", f"Exported template to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export template: {str(e)}")
    
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
        """Refresh template list widget with current in-memory templates."""
        self.template_list.clear()
        for name, tpl in self.templates.items():
            try:
                info = TemplateManager.get_template_info(tpl)
                subtitle = (
                    f"{info.get('group_count', 0)} groups, "
                    f"{info.get('materials_needed', 0)} tiles"
                )
            except Exception:
                subtitle = "invalid"
            item = QListWidgetItem(f"{name} - {subtitle}")
            self.template_list.addItem(item)
        if hasattr(self, "batch_processor"):
            self.batch_processor.set_templates(self.templates)
    
    def show_about(self):
        QMessageBox.about(
            self,
            "About GIF Maker",
            "<h2>GIF Maker</h2>"
            "<p>A GIF animation editor for game developers and animators.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Load images and GIFs as materials</li>"
            "<li>Split sprite sheets into tiles</li>"
            "<li>Group-led composition with nested groups and layer blocks</li>"
            "<li>Real-time animated preview</li>"
            "<li>Chroma key (green screen) support</li>"
            "<li>Template save / apply / import / export</li>"
            "<li>Batch processing and GIF optimizer</li>"
            "</ul>"
        )
    
    def auto_save_template(self):
        """Automatically save current composition as a template."""
        if not self.auto_save_enabled:
            return
        if len(self.group_manager.groups) == 0:
            return
        try:
            content_hash = self._get_content_hash()
            if content_hash == self.last_auto_save_content_hash:
                return
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_composition_template(
                self.group_manager,
                self.transparent_bg_checkbox.isChecked(),
                color_count,
            )
            template["auto_save_metadata"] = {
                "timestamp": timestamp,
                "group_count": len(self.group_manager.groups),
                "material_count": len(self.material_manager),
                "content_hash": content_hash,
            }
            TemplateManager.save_template_to_file(template, str(self.auto_save_file))
            self.last_auto_save_content_hash = content_hash
            print(f"Auto-saved: {self.auto_save_file.name}")
        except Exception as e:
            print(f"Auto-save failed: {e}")
    
    def _get_content_hash(self):
        """Hash current group composition for change detection."""
        import hashlib
        try:
            template = TemplateManager.export_composition_template(self.group_manager)
            import json as _json
            content = _json.dumps(template, sort_keys=True)
        except Exception:
            content = str(id(self.group_manager))
        return hashlib.md5(content.encode()).hexdigest()
    
    
    def closeEvent(self, event):
        """Handle application closing - perform emergency auto-save"""
        if self.auto_save_enabled and len(self.group_manager.groups) > 0:
            try:
                # Force emergency save
                self.auto_save_template()
                print("Emergency auto-save completed before closing")
            except Exception as e:
                print(f"Emergency auto-save failed: {e}")
        
        # Stop auto-save timer
        if hasattr(self, 'auto_save_timer'):
            self.auto_save_timer.stop()
        
        # Call parent closeEvent
        super().closeEvent(event)
    
    def restore_auto_save(self):
        """Restore composition from the latest auto-save."""
        try:
            if not self.auto_save_file.exists():
                QMessageBox.information(self, "No Auto-Save", "No auto-save file found.")
                return
            template = TemplateManager.load_template_from_file(str(self.auto_save_file))
            new_gm, settings = TemplateManager.import_composition_template(template)
            self.group_manager = new_gm
            if settings:
                self.transparent_bg_checkbox.setChecked(
                    settings.get("transparent_bg", self.transparent_bg_checkbox.isChecked())
                )
                color_count = settings.get("color_count", int(self.color_palette_combo.currentText()))
                color_text = str(color_count)
                if color_text in [self.color_palette_combo.itemText(i) for i in range(self.color_palette_combo.count())]:
                    self.color_palette_combo.setCurrentText(color_text)
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            self.update_preview()
            metadata = template.get("auto_save_metadata", {})
            QMessageBox.information(
                self, "Auto-Save Restored",
                f"Restored from: {self.auto_save_file.name}\n\n"
                f"Saved: {metadata.get('timestamp', 'unknown')}\n"
                f"Groups: {metadata.get('group_count', len(self.group_manager.groups))}\n"
                f"Materials: {metadata.get('material_count', 0)}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Restore Failed", f"Failed to restore auto-save:\n{str(e)}")
    
    def toggle_auto_save(self):
        """Toggle auto-save on/off"""
        self.auto_save_enabled = not self.auto_save_enabled
        
        if self.auto_save_enabled:
            self.auto_save_timer.start(self.auto_save_interval)
            QMessageBox.information(self, "Auto-Save", "Auto-save enabled")
        else:
            self.auto_save_timer.stop()
            QMessageBox.information(self, "Auto-Save", "Auto-save disabled")
    
    def create_color_icon(self, r: int, g: int, b: int, size: int = 16) -> QIcon:
        """Create a color preview icon"""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        from PyQt6.QtGui import QPainter, QColor
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, size, size, QColor(r, g, b))
        painter.end()
        
        return QIcon(pixmap)
    
    def analyze_first_frame_colors(self):
        """Analyze colors in the first frame of the current group and populate chroma key dropdown"""
        try:
            group = self._get_current_group()
            if group is None:
                QMessageBox.warning(self, "Warning", "No group selected!")
                return

            first_entry = next((e for e in group.entries if isinstance(e, FrameEntry)), None)
            if first_entry is None:
                QMessageBox.warning(self, "Warning", "No frames in the selected group to analyze!")
                return

            material = self.material_manager.get_material(first_entry.material_index)
            if not material:
                QMessageBox.warning(self, "Warning", "First frame material not found!")
                return
            
            img, _ = material
            
            # Convert to RGB for color analysis
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Sample colors (downsample for performance on large images)
            max_size = 200
            if img.width > max_size or img.height > max_size:
                # Create a thumbnail for analysis
                img_small = img.copy()
                img_small.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                img = img_small
            
            # Get all pixels
            pixels = list(img.getdata())
            total_pixels = len(pixels)
            
            # Count colors
            color_counts = Counter(pixels)
            
            # Get top colors (store all for "show more" functionality)
            top_colors = color_counts.most_common(100)  # Store up to 100
            
            # Store all colors with their percentages
            self.chroma_key_colors_all = []
            for color, count in top_colors:
                percentage = (count / total_pixels) * 100
                r, g, b = color
                # Create display name with color and percentage
                display_name = f"RGB({r},{g},{b}) - {percentage:.1f}%"
                self.chroma_key_colors_all.append((color, percentage, display_name))
            
            # Reset display count and update combo box
            self.chroma_key_display_count = 10
            self.update_chroma_key_combo()
            
            # Enable/disable show more button
            self.show_more_colors_btn.setEnabled(len(self.chroma_key_colors_all) > self.chroma_key_display_count)
            
            QMessageBox.information(
                self, 
                "Analysis Complete", 
                f"Analyzed {len(top_colors)} most common colors from first frame.\n"
                f"Showing top {min(10, len(top_colors))} colors.\n"
                f"Click '+10' to see more options."
            )
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to analyze colors:\n{str(e)}")
    
    def update_chroma_key_combo(self):
        """Update chroma key combo box with current display count"""
        # Store current selection
        current_index = self.chroma_key_combo.currentIndex()
        
        self.chroma_key_combo.blockSignals(True)
        self.chroma_key_combo.clear()
        self.chroma_key_combo.addItem("None (Disabled)")
        
        # Add colors up to display count
        display_colors = self.chroma_key_colors_all[:self.chroma_key_display_count]
        for color_rgb, _, display_name in display_colors:
            r, g, b = color_rgb
            icon = self.create_color_icon(r, g, b)
            self.chroma_key_combo.addItem(icon, display_name)
        
        # Restore selection if valid
        if current_index < self.chroma_key_combo.count():
            self.chroma_key_combo.setCurrentIndex(current_index)
        else:
            self.chroma_key_combo.setCurrentIndex(0)
        
        self.chroma_key_combo.blockSignals(False)
    
    def show_more_colors(self):
        """Show 10 more color options"""
        if self.chroma_key_display_count < len(self.chroma_key_colors_all):
            self.chroma_key_display_count += 10
            self.update_chroma_key_combo()
            
            # Disable button if we've shown all colors
            if self.chroma_key_display_count >= len(self.chroma_key_colors_all):
                self.show_more_colors_btn.setEnabled(False)
    
    def on_chroma_key_changed(self):
        """Handle chroma key color selection change"""
        try:
            index = self.chroma_key_combo.currentIndex()
            
            if index == 0:
                # "None" selected - disable chroma key
                self.gif_builder.clear_chroma_key()
            else:
                # Color selected - apply chroma key
                color_index = index - 1  # Account for "None" option
                display_colors = self.chroma_key_colors_all[:self.chroma_key_display_count]
                if 0 <= color_index < len(display_colors):
                    color_rgb, _, _ = display_colors[color_index]
                    r, g, b = color_rgb
                    self.gif_builder.set_chroma_key(r, g, b, threshold=30)
            
            # Update preview to show effect
            self.update_preview()
            
        except Exception as e:
            print(f"Error applying chroma key: {e}")
            import traceback
            traceback.print_exc()


def main():
    app = QApplication(sys.argv)
    AppTheme.apply(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

