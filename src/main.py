import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
                              QTableWidgetItem, QComboBox, QStackedWidget, QColorDialog, QDialog, QInputDialog)
from PyQt6.QtCore import Qt, QSize, QItemSelectionModel, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage, QFont

from PIL import Image
from collections import Counter

from .core import MaterialManager, GifBuilder, TemplateManager, GroupManager, CompositionGroup, FrameEntry, SubGroupEntry
from .widgets import AppTheme, PreviewWidget, PreviewPageWidget, TileEditorWidget, BatchProcessorWidget, GifOptimizerWidget, GroupEditorDialog, GroupSelectorDialog, GroupCompositionWidget


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
        
        # Auto-save configuration (temporarily disabled for multi-timeline phase)
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
        self.setWindowTitle("GIF Maker - Layer Timeline GIF Editor")
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
        # Templates temporarily disabled in multi-timeline phase
        # file_menu.addAction("Export Template", self.export_template)
        # file_menu.addAction("Import Template", self.import_template)
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
    
    def add_selected_to_timebase(self):
        """Add selected materials as frame entries to the current group (group-led model)."""
        mat_indices = self._get_selected_material_indices()
        if not mat_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "No group selected. Select a group in the composition panel.")
            return
        group = self.group_manager.get_group(self.current_group_id)
        if not group:
            return
        try:
            for mat_idx in mat_indices:
                group.entries.append(FrameEntry(material_index=mat_idx, x=0, y=0))
            self.group_manager.update_group(self.current_group_id, group)
            if mat_indices and len(self.material_manager) > 0:
                first = self.material_manager.get_material(mat_indices[0])
                if first:
                    img, _ = first
                    self.width_spinbox.setValue(img.width)
                    self.height_spinbox.setValue(img.height)
            self.refresh_timeline()
            self.update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add materials:\n{str(e)}")

    def add_selected_to_current_timeline(self):
        """Add selected materials to the current group (same as Add to Timebase in group-led model)."""
        self.add_selected_to_timebase()

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
    
    def create_group_from_selected(self):
        """Create a CompositionGroup from selected materials (name + frame entries)."""
        material_indices = self._get_selected_material_indices()
        if not material_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material to create a group!")
            return
        name, ok = QInputDialog.getText(self, "New Group", "Group name:", text=f"Group_{len(material_indices)}")
        if not ok:
            return
        comp_group = CompositionGroup(
            name=name or f"Group_{len(material_indices)}",
            entries=[FrameEntry(material_index=m, x=0, y=0) for m in material_indices],
            default_duration_ms=100,
        )
        self.group_manager.add_group(comp_group)
        self.refresh_groups_list()
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            self.group_composition_widget.refresh_groups_list()
        QMessageBox.information(self, "Success", f"Group '{comp_group.name}' created with {len(comp_group.entries)} frame(s).")
    
    def refresh_groups_list(self):
        """Refresh the groups list display (CompositionGroup model)."""
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            self.group_composition_widget.refresh_groups_list()
        if not hasattr(self, 'groups_list') or self.groups_list is None:
            return
        self.groups_list.clear()
        for idx, group in enumerate(self.group_manager.get_all_groups()):
            text = f"[{idx}] {group.name} ({len(group.entries)} entries)"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.groups_list.addItem(item)
    
    def remove_selected_group(self):
        """Remove selected groups (CompositionGroup model)."""
        if not hasattr(self, 'groups_list') or self.groups_list is None:
            QMessageBox.information(self, "Info", "Use the Composition panel to manage groups.")
            return
        selected_items = self.groups_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select at least one group to remove!")
            return
        indices = []
        for item in selected_items:
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx is not None:
                indices.append(idx)
        for idx in sorted(indices, reverse=True):
            self.group_manager.remove_group(idx)
        self.refresh_groups_list()
        QMessageBox.information(self, "Success", f"Removed {len(indices)} group(s).")
    
    def view_group_details(self):
        """View details of selected group (CompositionGroup model)."""
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            gid = self.group_composition_widget.get_current_group_id()
        else:
            gid = self.current_group_id
        if gid is None:
            QMessageBox.warning(self, "Warning", "Please select a group to view!")
            return
        group = self.group_manager.get_group(gid)
        if group is None:
            return
        details = f"Group: {group.name}\nEntries: {len(group.entries)}\nDefault duration: {group.default_duration_ms} ms"
        QMessageBox.information(self, f"Group - {group.name}", details)
    
    def add_selected_groups_to_current_layer(self):
        """Add selected groups as SubGroupEntry to the current group (group-led model)."""
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "Select a group in the Composition panel first.")
            return
        selected_items = getattr(self.group_composition_widget, 'groups_list', None)
        if selected_items is None:
            selected_items = getattr(self, 'groups_list', None)
        if selected_items is None:
            QMessageBox.information(self, "Info", "Select groups in the Composition panel, then use Add Sub-group.")
            return
        selected_items = selected_items.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select at least one group in the list!")
            return
        from .core.composition_group import SubGroupEntry
        group_indices = []
        for item in selected_items:
            idx = item.data(Qt.ItemDataRole.UserRole)
            if idx is not None and idx != self.current_group_id:
                group_indices.append(idx)
        if not group_indices:
            QMessageBox.warning(self, "Warning", "Select other groups (not the current one) to add as sub-groups.")
            return
        group = self.group_manager.get_group(self.current_group_id)
        if not group:
            return
        for gid in group_indices:
            group.entries.append(SubGroupEntry(group_id=gid, loop_count=1))
        self.group_manager.update_group(self.current_group_id, group)
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Added {len(group_indices)} sub-group(s) to current group.")
    
    # ===== New Group Addition Methods =====
    
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
    
    def edit_group_in_timeline(self, group_index: int):
        """Edit a group from the timeline"""
        group = self.group_manager.get_group(group_index)
        if group is None:
            QMessageBox.warning(self, "Warning", "Group not found!")
            return
        
        # Show group editor dialog with existing group
        dialog = GroupEditorDialog(self, existing_group=group)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        
        updated_group = dialog.get_group()
        if updated_group:
            self.group_manager.update_group(group_index, updated_group)
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(self, "Success", f"Group '{updated_group.name}' updated.")
    
    def remove_group_from_timeline(self, frame_index: int):
        """Remove a group from the timeline at specified frame index"""
        current_index = self.timeline_tabs.currentIndex()
        if current_index < 0:
            return
        
        track = self.layer_editor.get_layer_track(current_index)
        if track is None or frame_index >= len(track.frames):
            return
        
        frame = track.frames[frame_index]
        if frame.group_index is None:
            QMessageBox.warning(self, "Warning", "No group at this position!")
            return
        
        # Clear the group reference
        frame.material_index = None
        frame.group_index = None
        frame.x = 0
        frame.y = 0
        
        self.refresh_timeline()
        self.update_preview()
    
    def duplicate_group_in_timeline(self, frame_index: int):
        """Duplicate a group in the timeline"""
        current_index = self.timeline_tabs.currentIndex()
        if current_index < 0:
            return
        
        track = self.layer_editor.get_layer_track(current_index)
        if track is None or frame_index >= len(track.frames):
            return
        
        frame = track.frames[frame_index]
        if frame.group_index is None:
            QMessageBox.warning(self, "Warning", "No group at this position!")
            return
        
        # Get the group and create a copy
        group = self.group_manager.get_group(frame.group_index)
        if group is None:
            return
        
        # Create a copy with a new name
        new_group = group.copy()
        new_group.name = f"{group.name} (Copy)"
        new_group_idx = self.group_manager.add_group(new_group)
        
        # Find next empty slot
        frame_count = self.layer_editor.get_frame_count()
        next_slot = None
        for i in range(frame_index + 1, frame_count):
            if i >= len(track.frames) or (track.frames[i].material_index is None and track.frames[i].group_index is None):
                next_slot = i
                break
        
        if next_slot is None:
            # Extend timebase
            duration = 100
            main_idx = self.layer_editor.main_track_index
            main_tab = self.timeline_tabs.widget(main_idx) if 0 <= main_idx < self.timeline_tabs.count() else None
            if hasattr(main_tab, 'timeline_widget') and main_tab.timeline_widget.is_main_timebase:
                duration = main_tab.timeline_widget.duration_spinbox.value()
            self.layer_editor.add_timebase_frames(1, duration)
            frame_count = self.layer_editor.get_frame_count()
            next_slot = frame_count - 1
        
        self.layer_editor.ensure_track_length(current_index, frame_count)
        
        # Add duplicated group
        track.frames[next_slot].material_index = None
        track.frames[next_slot].group_index = new_group_idx
        track.frames[next_slot].x = frame.x
        track.frames[next_slot].y = frame.y
        
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Duplicated group '{group.name}'.")
    
    def remove_material_from_group(self, group_index: int, material_indices):
        """Remove material(s) from a group
        
        Args:
            group_index: Index of the group
            material_indices: Single material index (int) or list of material indices (list)
        """
        group = self.group_manager.get_group(group_index)
        if group is None:
            QMessageBox.warning(self, "Warning", "Group not found!")
            return
        
        # Convert single index to list for uniform processing
        if isinstance(material_indices, int):
            material_indices = [material_indices]
        
        # Validate all materials are in the group
        invalid_materials = [idx for idx in material_indices if idx not in group.material_indices]
        if invalid_materials:
            QMessageBox.warning(
                self, 
                "Warning", 
                f"Some materials not found in group: {invalid_materials}"
            )
            return
        
        # Confirm deletion
        if len(material_indices) == 1:
            message = f"Remove material #{material_indices[0]} from group '{group.name}'?"
        else:
            message = f"Remove {len(material_indices)} materials from group '{group.name}'?\n\nMaterials: {material_indices}"
        
        reply = QMessageBox.question(
            self,
            "Confirm",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Remove all selected materials from the group
        for mat_idx in material_indices:
            group.material_indices.remove(mat_idx)
        
        # If group becomes empty, warn the user
        if len(group.material_indices) == 0:
            QMessageBox.warning(
                self,
                "Empty Group",
                f"Group '{group.name}' is now empty. Consider removing it from the timeline."
            )
        
        self.refresh_timeline()
        self.update_preview()
    
    # ===== End New Group Methods =====
    
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
    
    def on_sequence_changed(self):
        """Handle current tab timeline reorder."""
        # Read current table order and reorder multi-editor timebase and frames accordingly
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        # Build mapping from visual rows to frame indices
        # Note: With new group UI, only count actual frame rows (not child material rows)
        new_order = []
        for row in range(tw.timeline_table.rowCount()):
            item = tw.timeline_table.item(row, 0)
            if not item:
                continue
            
            row_type = item.data(Qt.ItemDataRole.UserRole)  # 'group', 'material', or 'frame'
            frame_index = item.data(Qt.ItemDataRole.UserRole + 2)  # The actual frame index
            
            # Only include actual frames (groups and old-style frames), not child material rows
            if row_type in ('group', 'frame') and frame_index is not None:
                new_order.append(frame_index)
        
        # If we are on main timeline tab, reorder timebase
        if current_index == self.layer_editor.main_track_index:
            # Reorder durations and all layer_tracks according to new_order
            if len(new_order) == len(self.layer_editor.durations_ms):
                # Apply permutation
                self.layer_editor.durations_ms = [self.layer_editor.durations_ms[i] for i in new_order]
                for t in self.layer_editor.layer_tracks:
                    t.frames = [t.frames[i] for i in new_order]
        else:
            # For non-main layer_tracks, only reorder that timeline's frames to match new order
            tl = self.layer_editor.get_layer_track(current_index)
            if tl and len(new_order) == len(tl.frames):
                tl.frames = [tl.frames[i] for i in new_order]
        self.refresh_timeline()
        self.update_preview()
    
    def _get_frame_indices_from_selection(self, timeline_widget):
        """Helper method to extract frame indices from timeline table selection.
        
        With the new group UI, UserRole stores the row type ('group', 'material', 'frame')
        and UserRole+2 stores the actual frame index. This method correctly extracts
        frame indices, ignoring child material rows.
        """
        frame_indices = set()
        selected_items = timeline_widget.timeline_table.selectedIndexes()
        
        for item_index in selected_items:
            row = item_index.row()
            item = timeline_widget.timeline_table.item(row, 0)
            if not item:
                continue
            
            row_type = item.data(Qt.ItemDataRole.UserRole)
            frame_index = item.data(Qt.ItemDataRole.UserRole + 2)
            
            # Only include actual frames (groups and old-style frames), not child material rows
            if row_type in ('group', 'frame') and frame_index is not None:
                frame_indices.add(frame_index)
        
        return sorted(frame_indices)
    
    def on_apply_duration(self, duration: int, apply_to_all: bool):
        """Handle duration change requests from timeline"""
        # Only the main timeline tab can change durations
        current_index = self.timeline_tabs.currentIndex()
        if current_index != self.layer_editor.main_track_index:
            return
        if apply_to_all:
            self.layer_editor.set_timebase_all_durations(duration)
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(self, "Success", f"Applied duration {duration}ms to all {self.layer_editor.get_frame_count()} frames.")
        else:
            tab = self.timeline_tabs.widget(current_index)
            if not hasattr(tab, 'timeline_widget'):
                return
            tw = tab.timeline_widget
            selected_items = tw.timeline_table.selectedIndexes()
            if not selected_items:
                QMessageBox.warning(self, "Warning", "Please select one or more frames!")
                return
            frame_indices = self._get_frame_indices_from_selection(tw)
            for frame_index in frame_indices:
                self.layer_editor.set_timebase_duration(frame_index, duration)
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(self, "Success", f"Applied duration {duration}ms to {len(frame_indices)} selected frames.")
    
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
    
    def on_timeline_selection_changed(self):
        # Update preview in single-frame mode to follow selection (use first selected)
        if not self.preview_all_checkbox.isChecked():
            current_index = self.timeline_tabs.currentIndex()
            tab = self.timeline_tabs.widget(current_index)
            if hasattr(tab, 'timeline_widget'):
                tw = tab.timeline_widget
                selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
                if selected_rows:
                    # Sync spinbox for visibility (1-based)
                    self.preview_frame_spinbox.blockSignals(True)
                    self.preview_frame_spinbox.setValue(selected_rows[0] + 1)
                    self.preview_frame_spinbox.blockSignals(False)
                self.update_single_frame_preview()
    
    def duplicate_frame(self):
        """Duplicate selected frames. Only available on the main timeline.

        After duplication, auto-select the newly created frames (as a block
        inserted right after the last originally selected row, preserving order).
        """
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_items = tw.timeline_table.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to duplicate!")
            return
        frame_indices = self._get_frame_indices_from_selection(tw)
        if not frame_indices:
            return
        if current_index == self.layer_editor.main_track_index:
            # Insert duplicates as a contiguous block after the last selected row (affects timebase and all layer_tracks)
            insert_pos = frame_indices[-1]
            original_durs = list(self.layer_editor.durations_ms)
            dup_durs = [original_durs[i] for i in frame_indices]
            self.layer_editor.durations_ms = (
                original_durs[: insert_pos + 1] + dup_durs + original_durs[insert_pos + 1 :]
            )
            for t in self.layer_editor.layer_tracks:
                orig_frames = list(t.frames)
                from .core import TimelineFrame as _TLF
                dup_frames = [
                    _TLF(
                        material_index=orig_frames[i].material_index if i < len(orig_frames) else None,
                        x=orig_frames[i].x if i < len(orig_frames) else 0,
                        y=orig_frames[i].y if i < len(orig_frames) else 0,
                    )
                    for i in frame_indices
                ]
                t.frames = orig_frames[: insert_pos + 1] + dup_frames + orig_frames[insert_pos + 1 :]
            new_rows = list(range(insert_pos + 1, insert_pos + 1 + len(frame_indices)))
        else:
            # Duplicate only within the current timeline, keep timebase length unchanged
            tl = self.layer_editor.get_layer_track(current_index)
            if not tl:
                return
            n = self.layer_editor.get_frame_count()
            insert_pos = frame_indices[-1]
            from .core import TimelineFrame as _TLF
            dup_frames = [
                _TLF(
                    material_index=tl.frames[i].material_index if i < len(tl.frames) else None,
                    x=tl.frames[i].x if i < len(tl.frames) else 0,
                    y=tl.frames[i].y if i < len(tl.frames) else 0,
                )
                for i in frame_indices
            ]
            tl.frames = tl.frames[: insert_pos + 1] + dup_frames + tl.frames[insert_pos + 1 :]
            # Truncate to match timebase length
            if len(tl.frames) > n:
                tl.frames = tl.frames[:n]
            new_rows = list(range(insert_pos + 1, min(insert_pos + 1 + len(frame_indices), n)))

        # Refresh and select new duplicated block
        self.refresh_timeline()
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw2 = tab.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in new_rows:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.update_preview()
    
    def remove_frame(self):
        """Remove selected frames. Only available on the main timeline."""
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_items = tw.timeline_table.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a frame to remove!")
            return
        frame_indices = sorted(self._get_frame_indices_from_selection(tw), reverse=True)
        if not frame_indices:
            return
        if current_index == self.layer_editor.main_track_index:
            self.layer_editor.remove_timebase_frames(frame_indices)
        else:
            # Remove within current timeline and append empty frames to keep length
            tl = self.layer_editor.get_layer_track(current_index)
            if not tl:
                return
            count = len(frame_indices)
            for idx in frame_indices:
                if 0 <= idx < len(tl.frames):
                    tl.frames.pop(idx)
            from .core import TimelineFrame as _TLF
            tl.frames.extend([_TLF() for _ in range(count)])
        self.refresh_timeline()
        self.update_preview()
    
    def move_frame_up(self):
        """Move selected frame(s) up. Only available on the main timeline."""
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one frame to move!")
            return
        if selected_rows[0] == 0:
            return
        if current_index == self.layer_editor.main_track_index:
            # Move timebase and all layer_tracks
            n = self.layer_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(1, n):
                if order[i] in selected_set and order[i - 1] not in selected_set:
                    order[i - 1], order[i] = order[i], order[i - 1]
            self.layer_editor.durations_ms = [self.layer_editor.durations_ms[i] for i in order]
            for t in self.layer_editor.layer_tracks:
                t.frames = [t.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        else:
            # Move only current timeline rows
            tl = self.layer_editor.get_layer_track(current_index)
            if not tl:
                return
            n = self.layer_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(1, n):
                if order[i] in selected_set and order[i - 1] not in selected_set:
                    order[i - 1], order[i] = order[i], order[i - 1]
            tl.frames = [tl.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        self.refresh_timeline()
        # Reselect moved rows
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw2 = tab.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in new_positions:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    
    def move_frame_down(self):
        """Move selected frame(s) down. Only available on the main timeline."""
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one frame to move!")
            return
        if selected_rows[-1] >= self.layer_editor.get_frame_count() - 1:
            return
        if current_index == self.layer_editor.main_track_index:
            n = self.layer_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(n - 2, -1, -1):
                if order[i] in selected_set and order[i + 1] not in selected_set:
                    order[i], order[i + 1] = order[i + 1], order[i]
            self.layer_editor.durations_ms = [self.layer_editor.durations_ms[i] for i in order]
            for t in self.layer_editor.layer_tracks:
                t.frames = [t.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        else:
            tl = self.layer_editor.get_layer_track(current_index)
            if not tl:
                return
            n = self.layer_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(n - 2, -1, -1):
                if order[i] in selected_set and order[i + 1] not in selected_set:
                    order[i], order[i + 1] = order[i + 1], order[i]
            tl.frames = [tl.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        self.refresh_timeline()
        # Reselect moved rows
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw2 = tab.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in new_positions:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
    
    def apply_batch_offset(self):
        """Apply offset to selected frames in the current timeline."""
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_items = tw.timeline_table.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames!")
            return
        frame_indices = self._get_frame_indices_from_selection(tw)
        if not frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        offset_x = self.batch_offset_x.value()
        offset_y = self.batch_offset_y.value()
        tl = self.layer_editor.get_layer_track(current_index)
        changed = 0
        if tl:
            for fi in frame_indices:
                self.layer_editor.ensure_track_length(current_index, fi + 1)
                tl.frames[fi].x = offset_x
                tl.frames[fi].y = offset_y
                changed += 1
        self.batch_offset_x.setValue(0)
        self.batch_offset_y.setValue(0)
        self.refresh_timeline()
        self.update_preview()
        QMessageBox.information(self, "Success", f"Applied offset (X: {offset_x}, Y: {offset_y}) to {changed} frames.")
    
    def batch_add_same_layer(self):
        pass
    
    def batch_add_matched_layers(self):
        pass
    
    def get_frame_material_size(self, frame) -> Optional[Tuple[int, int]]:
        """
        Get the size of material(s) referenced by a frame.
        
        Args:
            frame: LayerFrame object
        
        Returns:
            (width, height) tuple, or None if no valid material found
        """
        # Handle material_index
        if frame.material_index is not None:
            material = self.material_manager.get_material(frame.material_index)
            if material:
                img, _ = material
                return img.size
        
        # Handle group_index
        if frame.group_index is not None:
            group = self.group_manager.get_group(frame.group_index)
            if group and group.material_indices:
                max_w, max_h = 0, 0
                for mat_idx in group.material_indices:
                    material = self.material_manager.get_material(mat_idx)
                    if material:
                        img, _ = material
                        w, h = img.size
                        max_w = max(max_w, w)
                        max_h = max(max_h, h)
                if max_w > 0 and max_h > 0:
                    return (max_w, max_h)
        
        return None
    
    def get_all_materials_max_size(self) -> Tuple[int, int]:
        """
        Calculate maximum size of all materials in all layer tracks.
        
        Returns:
            (max_width, max_height) tuple, or (0, 0) if no materials found
        """
        max_width = 0
        max_height = 0
        
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                size = self.get_frame_material_size(frame)
                if size:
                    w, h = size
                    max_width = max(max_width, w)
                    max_height = max(max_height, h)
        
        return (max_width, max_height)
    
    def _apply_alignment_to_independent_groups(self, alignment_func, output_width=0, output_height=0):
        """
        Apply alignment function to groups with independent_offsets=True.
        Instead of expanding groups, modifies material_offsets within each group.
        
        Args:
            alignment_func: Function(material_size, output_size, current_offset) -> new_offset
            output_width: Output canvas width (for horizontal alignment)
            output_height: Output canvas height (for vertical alignment)
        
        Returns:
            Number of independent groups processed
        """
        processed_count = 0
        
        # Find all independent groups
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        # Apply alignment to each material in the group
                        for mat_list_idx, material_idx in enumerate(group.material_indices):
                            material = self.material_manager.get_material(material_idx)
                            if not material:
                                continue
                            
                            img, _ = material
                            mat_width, mat_height = img.size
                            
                            # Calculate new offset using alignment function
                            current_x, current_y = group.get_material_offset(mat_list_idx)
                            new_x, new_y = alignment_func(
                                (mat_width, mat_height),
                                (output_width, output_height),
                                (current_x, current_y)
                            )
                            
                            # Update group's internal offset
                            group.set_material_offset(mat_list_idx, new_x, new_y)
                        
                        processed_count += 1
        
        return processed_count
    
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
        """Align all materials to the left (x = 0)."""
        # Define alignment function
        def align_left(mat_size, output_size, current_offset):
            return (0, current_offset[1])  # x=0, keep y unchanged
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(align_left, 0, 0)
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                if frame.material_index is not None or frame.group_index is not None:
                    frame.x = 0
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Aligned {total} frame(s) to the left")
    
    def align_all_center_horizontal(self):
        """Center all materials horizontally."""
        output_width = self.width_spinbox.value()
        
        # Define alignment function
        def center_horizontal(mat_size, output_size, current_offset):
            mat_width, _ = mat_size
            out_width, _ = output_size
            new_x = (out_width - mat_width) // 2
            return (new_x, current_offset[1])  # Keep y unchanged
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(
            center_horizontal, output_width, 0
        )
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                size = self.get_frame_material_size(frame)
                if size:
                    mat_width, _ = size
                    frame.x = (output_width - mat_width) // 2
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Centered {total} frame(s) horizontally")
    
    def align_all_right(self):
        """Align all materials to the right."""
        output_width = self.width_spinbox.value()
        
        # Define alignment function
        def align_right(mat_size, output_size, current_offset):
            mat_width, _ = mat_size
            out_width, _ = output_size
            new_x = out_width - mat_width
            return (new_x, current_offset[1])  # Keep y unchanged
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(
            align_right, output_width, 0
        )
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                size = self.get_frame_material_size(frame)
                if size:
                    mat_width, _ = size
                    frame.x = output_width - mat_width
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Aligned {total} frame(s) to the right")
    
    def align_all_top(self):
        """Align all materials to the top (y = 0)."""
        # Define alignment function
        def align_top(mat_size, output_size, current_offset):
            return (current_offset[0], 0)  # Keep x, y=0
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(align_top, 0, 0)
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                if frame.material_index is not None or frame.group_index is not None:
                    frame.y = 0
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Aligned {total} frame(s) to the top")
    
    def align_all_middle_vertical(self):
        """Center all materials vertically."""
        output_height = self.height_spinbox.value()
        
        # Define alignment function
        def center_vertical(mat_size, output_size, current_offset):
            _, mat_height = mat_size
            _, out_height = output_size
            new_y = (out_height - mat_height) // 2
            return (current_offset[0], new_y)  # Keep x unchanged
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(
            center_vertical, 0, output_height
        )
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                size = self.get_frame_material_size(frame)
                if size:
                    _, mat_height = size
                    frame.y = (output_height - mat_height) // 2
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Centered {total} frame(s) vertically")
    
    def align_all_bottom(self):
        """Align all materials to the bottom."""
        output_height = self.height_spinbox.value()
        
        # Define alignment function
        def align_bottom(mat_size, output_size, current_offset):
            _, mat_height = mat_size
            _, out_height = output_size
            new_y = out_height - mat_height
            return (current_offset[0], new_y)  # Keep x unchanged
        
        # Apply to independent groups
        independent_count = self._apply_alignment_to_independent_groups(
            align_bottom, 0, output_height
        )
        
        # Apply to regular frames (non-independent-group)
        changed_count = 0
        for track in self.layer_editor.layer_tracks:
            for frame in track.frames:
                # Skip independent groups (already handled)
                if frame.group_index is not None:
                    group = self.group_manager.get_group(frame.group_index)
                    if group and group.independent_offsets:
                        continue  # Already processed
                
                # Handle regular materials and unified groups
                size = self.get_frame_material_size(frame)
                if size:
                    _, mat_height = size
                    frame.y = output_height - mat_height
                    changed_count += 1
        
        if changed_count == 0 and independent_count == 0:
            QMessageBox.warning(self, "Warning", "No materials found in timeline!")
            return
        
        self.refresh_timeline()
        self.update_preview()
        total = changed_count + independent_count
        QMessageBox.information(self, "Success", f"Aligned {total} frame(s) to the bottom")
    
    def refresh_timeline(self):
        """Refresh group composition widget (group-led model)."""
        if hasattr(self, 'group_composition_widget') and self.group_composition_widget is not None:
            self.group_composition_widget.refresh_groups_list()
            self.group_composition_widget.refresh_entries_list()
        return

    def _add_group_row(self, tw, table_row, frame_index, frame, group, is_expanded):
        """Add a group row to timeline table"""
        tw.timeline_table.insertRow(table_row)
        
        # Column 0: Expand/collapse icon + frame number
        expand_icon = "▼" if is_expanded else "▶"
        index_text = f"{expand_icon} {frame_index + 1}"
        index_item = QTableWidgetItem(index_text)
        index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        index_item.setData(Qt.ItemDataRole.UserRole, 'group')  # Mark as group row
        index_item.setData(Qt.ItemDataRole.UserRole + 1, frame.group_index)  # Store group index
        index_item.setData(Qt.ItemDataRole.UserRole + 2, frame_index)  # Store frame index
        font = QFont()
        font.setBold(True)
        index_item.setFont(font)
        tw.timeline_table.setItem(table_row, 0, index_item)
        
        # Column 1: Preview (first material thumbnail)
        preview_item = QTableWidgetItem()
        if len(group.material_indices) > 0:
            first_mat_idx = group.material_indices[0]
            if first_mat_idx < len(self.material_manager):
                material = self.material_manager.get_material(first_mat_idx)
                if material:
                    img, _ = material
                    thumbnail = self.create_thumbnail(img, 64, 64)
                    preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 1, preview_item)
        
        # Column 2: Group info
        total_frames = group.get_total_frames()
        mode_icon = "🔓" if group.independent_offsets else "🔒"
        text = f"[G{frame.group_index}] {group.name} ({len(group.material_indices)}×{group.loop_count}={total_frames}f) {mode_icon} | Pos({frame.x}, {frame.y})"
        frame_item = QTableWidgetItem(text)
        frame_item.setFlags(frame_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        font = QFont()
        font.setBold(True)
        frame_item.setFont(font)
        tw.timeline_table.setItem(table_row, 2, frame_item)
        
        # Column 3: Total duration
        total_duration = group.get_total_duration()
        duration_item = QTableWidgetItem(f"{total_duration}ms")
        duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 3, duration_item)
        
        tw.timeline_table.setRowHeight(table_row, 70)
    
    def _add_material_child_row(self, tw, table_row, frame_index, mat_idx, sequence_idx, group, group_index):
        """Add a child material row under expanded group"""
        tw.timeline_table.insertRow(table_row)
        
        # Column 0: Indented sequence number
        index_item = QTableWidgetItem(f"   └ {sequence_idx + 1}")
        index_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        index_item.setData(Qt.ItemDataRole.UserRole, 'material')  # Mark as material child row
        index_item.setData(Qt.ItemDataRole.UserRole + 1, group_index)  # Store group index
        index_item.setData(Qt.ItemDataRole.UserRole + 2, mat_idx)  # Store material index (changed from frame_index)
        tw.timeline_table.setItem(table_row, 0, index_item)
        
        # Column 1: Material preview
        preview_item = QTableWidgetItem()
        if mat_idx < len(self.material_manager):
            material = self.material_manager.get_material(mat_idx)
            if material:
                img, _ = material
                thumbnail = self.create_thumbnail(img, 48, 48)
                preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 1, preview_item)
        
        # Column 2: Material info
        if mat_idx < len(self.material_manager):
            material = self.material_manager.get_material(mat_idx)
            if material:
                _, mat_name = material
                text = f"   [{mat_idx}] {mat_name}"
                text_color = Qt.GlobalColor.gray
            else:
                text = f"   ⚠ [{mat_idx}] Material Not Loaded"
                text_color = Qt.GlobalColor.darkYellow
        else:
            text = f"   ⚠ [{mat_idx}] Material Missing (out of range)"
            text_color = Qt.GlobalColor.red
        
        frame_item = QTableWidgetItem(text)
        frame_item.setFlags(frame_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        frame_item.setForeground(text_color)
        tw.timeline_table.setItem(table_row, 2, frame_item)
        
        # Column 3: Frame duration
        duration_item = QTableWidgetItem(f"{group.frame_duration}ms")
        duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        duration_item.setForeground(Qt.GlobalColor.gray)
        tw.timeline_table.setItem(table_row, 3, duration_item)
        
        tw.timeline_table.setRowHeight(table_row, 50)
    
    def _add_timeline_row(self, tw, table_row, frame_index, mat_idx, group_idx, frame, is_child):
        """Add a regular timeline row (for backward compatibility with old material_index)"""
        tw.timeline_table.insertRow(table_row)
        
        # Column 0: Frame index
        index_item = QTableWidgetItem(str(frame_index + 1))
        index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        index_item.setData(Qt.ItemDataRole.UserRole, 'frame')  # Mark as regular frame
        index_item.setData(Qt.ItemDataRole.UserRole + 2, frame_index)  # Store frame index
        tw.timeline_table.setItem(table_row, 0, index_item)
        
        # Column 1: Preview
        preview_item = QTableWidgetItem()
        if mat_idx is not None and mat_idx < len(self.material_manager):
            material = self.material_manager.get_material(mat_idx)
            if material:
                img, _ = material
                thumbnail = self.create_thumbnail(img, 64, 64)
                preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
        preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 1, preview_item)
        
        # Column 2: Info
        text = "Empty"
        if frame:
            if mat_idx is not None and mat_idx < len(self.material_manager):
                material = self.material_manager.get_material(mat_idx)
                if material:
                    _, mat_name = material
                    text = f"[{mat_idx}] {mat_name} | Pos({frame.x}, {frame.y})"
            else:
                text = f"Empty | Pos({frame.x}, {frame.y})"
        frame_item = QTableWidgetItem(text)
        frame_item.setFlags(frame_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 2, frame_item)
        
        # Column 3: Duration
        dur = 0
        if 0 <= frame_index < len(self.layer_editor.durations_ms):
            dur = self.layer_editor.durations_ms[frame_index]
        duration_item = QTableWidgetItem(str(dur))
        duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        tw.timeline_table.setItem(table_row, 3, duration_item)
        
        tw.timeline_table.setRowHeight(table_row, 70)

    def on_timeline_tab_changed(self, index: int):
        self.refresh_timeline()
        self.update_preview()

    def on_apply_timeline_offset(self):
        idx = self.timeline_tabs.currentIndex()
        tl = self.layer_editor.get_layer_track(idx)
        if tl is None:
            return
        tl.offset_x = self.timeline_offset_x.value()
        tl.offset_y = self.timeline_offset_y.value()
        # Live preview to help fine-tune
        self.update_preview()
    
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

    def on_set_main_track(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0:
            return
        self.layer_editor.set_main_track(idx)
        self.refresh_timeline()
        self.update_preview()

    def on_add_layer_track(self):
        name = f"Timeline {len(self.layer_editor.layer_tracks) + 1}"
        new_idx = self.layer_editor.add_layer_track(name)
        # Ensure new timeline matches current timebase length
        self.layer_editor.ensure_track_length(new_idx, self.layer_editor.get_frame_count())
        self.refresh_timeline()
        self.timeline_tabs.setCurrentIndex(new_idx)

    def on_remove_timeline(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0:
            return
        if idx == self.layer_editor.main_track_index:
            QMessageBox.warning(self, "Warning", "Cannot remove the main layer track.")
            return
        self.layer_editor.remove_layer_track(idx)
        self.refresh_timeline()
        self.update_preview()

    def on_move_timeline_down(self):
        idx = self.timeline_tabs.currentIndex()
        if idx <= 0:
            return
        self.layer_editor.move_layer_track(idx, idx - 1)
        self.refresh_timeline()
        self.timeline_tabs.setCurrentIndex(idx - 1)

    def on_move_timeline_up(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0 or idx >= self.timeline_tabs.count() - 1:
            return
        self.layer_editor.move_layer_track(idx, idx + 1)
        self.refresh_timeline()
        self.timeline_tabs.setCurrentIndex(idx + 1)

    def on_assign_selected_material(self):
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select a material from the Materials list.")
            return
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_items = tw.timeline_table.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames in the current timeline.")
            return
        frame_indices = self._get_frame_indices_from_selection(tw)
        if not frame_indices:
            return
        mat_idx = selected_rows[0]
        tl = self.layer_editor.get_layer_track(current_index)
        if not tl:
            return
        # Ensure timeline has enough frames
        self.layer_editor.ensure_track_length(current_index, max(frame_indices) + 1)
        for fi in frame_indices:
            tl.frames[fi].material_index = mat_idx
        # Reselect frames after assignment
        self.refresh_timeline()
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw2 = tab.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in frame_indices:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.update_preview()

    def on_assign_selected_materials_matched(self):
        # Get selected materials (ordered)
        selected_material_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_material_rows.append(mat_idx if mat_idx is not None else index.row())
        selected_material_rows = sorted(selected_material_rows)
        if not selected_material_rows:
            QMessageBox.warning(self, "Warning", "Please select materials from the Materials list.")
            return
        # Get selected frames in current timeline (ordered)
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_items = tw.timeline_table.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select one or more frames in the current timeline.")
            return
        frame_indices = self._get_frame_indices_from_selection(tw)
        if not frame_indices:
            return
        if len(frame_indices) != len(selected_material_rows):
            QMessageBox.warning(self, "Warning", f"Selected frames ({len(frame_indices)}) must match selected materials ({len(selected_material_rows)}).")
            return
        tl = self.layer_editor.get_layer_track(current_index)
        if not tl:
            return
        # Ensure length and assign one-to-one
        self.layer_editor.ensure_track_length(current_index, max(frame_indices) + 1)
        for fi, mat_idx in zip(frame_indices, selected_material_rows):
            tl.frames[fi].material_index = mat_idx
        # Refresh and restore selection
        self.refresh_timeline()
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw2 = tab.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in frame_indices:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.update_preview()
    
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
    
    def export_template(self):
        """Export current composition as a template to file."""
        if len(self.group_manager.groups) == 0:
            QMessageBox.warning(self, "Warning", "No groups to export as template!")
            return
        default_path = "composition_template.json"
        if self.last_template_dir:
            default_path = str(Path(self.last_template_dir) / "composition_template.json")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Template", default_path, "JSON Files (*.json)"
        )
        if file_path:
            try:
                self.last_template_dir = str(Path(file_path).parent)
                color_count = int(self.color_palette_combo.currentText())
                template = TemplateManager.export_composition_template(
                    self.group_manager,
                    self.transparent_bg_checkbox.isChecked(),
                    color_count,
                )
                TemplateManager.save_template_to_file(template, file_path)
                info = TemplateManager.get_template_info(template)
                QMessageBox.information(
                    self, "Success",
                    f"Template saved successfully!\n\n"
                    f"Groups: {info['group_count']}\n"
                    f"Materials needed: {info['materials_needed']}\n"
                    f"File: {file_path}",
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export template:\n{str(e)}")
    
    def import_template(self):
        """Import and apply a composition template from file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Template", self.last_template_dir, "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            template = TemplateManager.load_template_from_file(file_path)
            info = TemplateManager.get_template_info(template)
            materials_needed = info["materials_needed"]
            materials_available = len(self.material_manager)
            reply = QMessageBox.question(
                self, "Import Template",
                f"Template Info:\n"
                f"• Groups: {info['group_count']}\n"
                f"• Materials needed: {materials_needed}\n\n"
                f"Available materials: {materials_available}\n\n"
                f"Apply this template? (replaces current composition)",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            new_gm, settings = TemplateManager.import_composition_template(template)
            self.group_manager = new_gm
            if settings:
                self.transparent_bg_checkbox.setChecked(settings.get("transparent_bg", False))
                color_count = settings.get("color_count", 256)
                self.color_palette_combo.setCurrentText(str(color_count))
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            self.update_preview()
            QMessageBox.information(
                self, "Success",
                f"Template imported successfully!\nGroups: {info['group_count']}",
            )
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to import template:\n{str(e)}")
    
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

    def reverse_selected_frames(self):
        """Reverse the order of selected frames in the current timeline.
        
        If current tab is the main timebase, reverse the selected positions across
        durations and all layer_tracks to preserve alignment.
        Otherwise, reverse only the current timeline's frames at those positions.
        """
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget
        selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
        if len(selected_rows) < 2:
            QMessageBox.warning(self, "Warning", "Select at least two frames to reverse.")
            return

        # Build reversed mapping within the same positions
        target_rows = list(reversed(selected_rows))

        if current_index == self.layer_editor.main_track_index:
            # Reverse durations at selected positions
            original_durs = list(self.layer_editor.durations_ms)
            new_durs = list(original_durs)
            for dst, src in zip(selected_rows, target_rows):
                if 0 <= dst < len(new_durs) and 0 <= src < len(original_durs):
                    new_durs[dst] = original_durs[src]
            self.layer_editor.durations_ms = new_durs
            # Reverse each timeline's frames at those positions
            for t in self.layer_editor.layer_tracks:
                orig_frames = list(t.frames)
                new_frames = list(orig_frames)
                for dst, src in zip(selected_rows, target_rows):
                    if 0 <= dst < len(new_frames) and 0 <= src < len(orig_frames):
                        new_frames[dst] = orig_frames[src]
                t.frames = new_frames
        else:
            tl = self.layer_editor.get_layer_track(current_index)
            if not tl:
                return
            orig_frames = list(tl.frames)
            new_frames = list(orig_frames)
            for dst, src in zip(selected_rows, target_rows):
                if 0 <= dst < len(new_frames) and 0 <= src < len(orig_frames):
                    new_frames[dst] = orig_frames[src]
            tl.frames = new_frames

        # Refresh and keep the same positions selected
        self.refresh_timeline()
        tab2 = self.timeline_tabs.widget(current_index)
        if hasattr(tab2, 'timeline_widget'):
            tw2 = tab2.timeline_widget
            sel_model = tw2.timeline_table.selectionModel()
            tw2.timeline_table.clearSelection()
            for r in selected_rows:
                if 0 <= r < tw2.timeline_table.rowCount():
                    index = tw2.timeline_table.model().index(r, 0)
                    sel_model.select(index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.update_preview()
    
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
            "<p>A powerful GIF animation editor with material management and timeline editing.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Load images and GIFs as materials</li>"
            "<li>Split images into tiles</li>"
            "<li>Drag-and-drop timeline editing</li>"
            "<li>Real-time preview</li>"
            "<li>Customizable frame duration and sequence</li>"
            "<li>Export and import timeline templates</li>"
            "<li>Auto-save protection</li>"
            "</ul>"
            "<p>Version 1.0</p>"
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
        """Analyze colors in the first frame of the main timeline and populate chroma key dropdown"""
        try:
            # Get main timeline
            main_idx = self.layer_editor.main_track_index
            main_timeline = self.layer_editor.get_layer_track(main_idx)
            
            if not main_timeline or len(main_timeline.frames) == 0:
                QMessageBox.warning(self, "Warning", "No frames in main timeline to analyze!")
                return
            
            # Get first frame's material
            first_frame = main_timeline.frames[0]
            if first_frame.material_index is None:
                QMessageBox.warning(self, "Warning", "First frame has no material assigned!")
                return
            
            material = self.material_manager.get_material(first_frame.material_index)
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

