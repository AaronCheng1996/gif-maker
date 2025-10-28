import sys
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                              QHBoxLayout, QPushButton, QFileDialog, QMessageBox,
                              QListWidget, QListWidgetItem, QSplitter, QLabel,
                              QGroupBox, QSpinBox, QTabWidget, QScrollArea, QCheckBox,
                              QTableWidgetItem, QComboBox, QStackedWidget, QColorDialog)
from PyQt6.QtCore import Qt, QSize, QItemSelectionModel, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image
from collections import Counter

from .core import MaterialManager, GifBuilder, TemplateManager, MultiTimelineEditor, Timeline, TimelineFrame
from .widgets import PreviewWidget, PreviewPageWidget, TimelineWidget, TileEditorWidget, BatchProcessorWidget, GifOptimizerWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.material_manager = MaterialManager()
        self.multi_editor = MultiTimelineEditor()
        self.gif_builder = GifBuilder()
        
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
        self.setWindowTitle("GIF Maker - Multi-Timeline GIF Editor")
        self.resize(1600, 950)
        # Default preview background color
        self.preview_bg_color = "#e8e8e8"
        
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
        
        list_label = QLabel("Material Library")
        list_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(list_label)
        
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
        
        self.add_to_timebase_btn = QPushButton("Add to Timebase")
        self.add_to_timebase_btn.setToolTip("Append frames to main timeline using selected materials")
        self.add_to_timebase_btn.clicked.connect(self.add_selected_to_timebase)
        material_actions.addWidget(self.add_to_timebase_btn)
        
        self.add_to_current_timeline_btn = QPushButton("Add to Current Timeline")
        self.add_to_current_timeline_btn.setToolTip("Assign selected materials into current timeline (appends; extends timebase if needed)")
        self.add_to_current_timeline_btn.clicked.connect(self.add_selected_to_current_timeline)
        material_actions.addWidget(self.add_to_current_timeline_btn)
        
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

        # Controls to add/remove/reorder timelines
        timeline_controls = QHBoxLayout()
        self.add_timeline_btn = QPushButton("+ Timeline")
        self.add_timeline_btn.setMaximumHeight(25)
        self.add_timeline_btn.clicked.connect(self.on_add_timeline)
        timeline_controls.addWidget(self.add_timeline_btn)

        self.remove_timeline_btn = QPushButton("🗑 Remove Timeline")
        self.remove_timeline_btn.setMaximumHeight(25)
        self.remove_timeline_btn.clicked.connect(self.on_remove_timeline)
        timeline_controls.addWidget(self.remove_timeline_btn)

        self.move_timeline_up_btn = QPushButton("▲ Move Up")
        self.move_timeline_up_btn.setMaximumHeight(25)
        self.move_timeline_up_btn.clicked.connect(self.on_move_timeline_up)
        timeline_controls.addWidget(self.move_timeline_up_btn)

        self.move_timeline_down_btn = QPushButton("▼ Move Down")
        self.move_timeline_down_btn.setMaximumHeight(25)
        self.move_timeline_down_btn.clicked.connect(self.on_move_timeline_down)
        timeline_controls.addWidget(self.move_timeline_down_btn)

        self.set_main_btn = QPushButton("★ Set Main")
        self.set_main_btn.setMaximumHeight(25)
        self.set_main_btn.setToolTip("Set selected tab as main timeline (timebase)")
        self.set_main_btn.clicked.connect(self.on_set_main_timeline)
        timeline_controls.addWidget(self.set_main_btn)

        timeline_controls.addStretch()
        layout.addLayout(timeline_controls)
        
        # Multi timeline tabs
        tabs_row = QHBoxLayout()
        self.timeline_tabs = QTabWidget()
        self.timeline_tabs.currentChanged.connect(self.on_timeline_tab_changed)
        layout.addWidget(self.timeline_tabs, stretch=2)
        
        # Row 1: Offset (left) and controls (right)
        btn_row1 = QHBoxLayout()
        # Offset group on left
        btn_row1.addWidget(QLabel("Offset:"))
        self.batch_offset_x = QSpinBox()
        self.batch_offset_x.setMinimum(-10000)
        self.batch_offset_x.setMaximum(10000)
        self.batch_offset_x.setValue(0)
        self.batch_offset_x.setMaximumWidth(60)
        btn_row1.addWidget(self.batch_offset_x)
        self.batch_offset_y = QSpinBox()
        self.batch_offset_y.setMinimum(-10000)
        self.batch_offset_y.setMaximum(10000)
        self.batch_offset_y.setValue(0)
        self.batch_offset_y.setMaximumWidth(60)
        btn_row1.addWidget(self.batch_offset_y)
        self.apply_batch_offset_btn = QPushButton("Apply")
        self.apply_batch_offset_btn.clicked.connect(self.apply_batch_offset)
        self.apply_batch_offset_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.apply_batch_offset_btn)
        
        btn_row1.addStretch()
        
        # Controls on the right
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

        # Reverse selected frames
        self.reverse_frames_btn = QPushButton("⇄")
        self.reverse_frames_btn.setToolTip("Reverse order of selected frames")
        self.reverse_frames_btn.setMaximumWidth(30)
        self.reverse_frames_btn.setMaximumHeight(25)
        self.reverse_frames_btn.clicked.connect(self.reverse_selected_frames)
        btn_row1.addWidget(self.reverse_frames_btn)
        
        # Copy/Delete as icons on the far right
        self.duplicate_frame_btn = QPushButton("📄")
        self.duplicate_frame_btn.setToolTip("Copy (duplicate) selected frames")
        self.duplicate_frame_btn.clicked.connect(self.duplicate_frame)
        self.duplicate_frame_btn.setMaximumWidth(30)
        self.duplicate_frame_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.duplicate_frame_btn)
        
        self.remove_frame_btn = QPushButton("🗑")
        self.remove_frame_btn.setToolTip("Delete selected frames")
        self.remove_frame_btn.clicked.connect(self.remove_frame)
        self.remove_frame_btn.setMaximumWidth(30)
        self.remove_frame_btn.setMaximumHeight(25)
        btn_row1.addWidget(self.remove_frame_btn)
        
        self.refresh_timeline_btn = QPushButton("🔄")
        self.refresh_timeline_btn.clicked.connect(self.refresh_timeline)
        self.refresh_timeline_btn.setMaximumWidth(30)
        self.refresh_timeline_btn.setMaximumHeight(25)
        self.refresh_timeline_btn.setToolTip("Refresh Timeline")
        btn_row1.addWidget(self.refresh_timeline_btn)
        
        layout.addLayout(btn_row1)
        
        # Controls for assigning material to current timeline frame
        assign_row = QHBoxLayout()
        self.assign_selected_material_btn = QPushButton("Assign Selected Material")
        self.assign_selected_material_btn.setMaximumHeight(25)
        self.assign_selected_material_btn.clicked.connect(self.on_assign_selected_material)
        assign_row.addWidget(self.assign_selected_material_btn)
        self.assign_matched_materials_btn = QPushButton("Assign Selected (1:1)")
        self.assign_matched_materials_btn.setMaximumHeight(25)
        self.assign_matched_materials_btn.setToolTip("Assign selected materials to selected frames one-by-one in order")
        self.assign_matched_materials_btn.clicked.connect(self.on_assign_selected_materials_matched)
        assign_row.addWidget(self.assign_matched_materials_btn)
        # Per-timeline global offset controls
        assign_row.addWidget(QLabel("Timeline Offset:"))
        self.timeline_offset_x = QSpinBox()
        self.timeline_offset_x.setMinimum(-10000)
        self.timeline_offset_x.setMaximum(10000)
        self.timeline_offset_x.setValue(0)
        self.timeline_offset_x.setMaximumWidth(60)
        assign_row.addWidget(self.timeline_offset_x)
        self.timeline_offset_y = QSpinBox()
        self.timeline_offset_y.setMinimum(-10000)
        self.timeline_offset_y.setMaximum(10000)
        self.timeline_offset_y.setValue(0)
        self.timeline_offset_y.setMaximumWidth(60)
        assign_row.addWidget(self.timeline_offset_y)
        self.apply_timeline_offset_btn = QPushButton("Apply")
        self.apply_timeline_offset_btn.setMaximumHeight(25)
        self.apply_timeline_offset_btn.clicked.connect(self.on_apply_timeline_offset)
        assign_row.addWidget(self.apply_timeline_offset_btn)
        layout.addLayout(assign_row)
        
        panel.setLayout(layout)
        # Populate initial tabs/tables
        self.refresh_timeline()
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

        for i in indices:
            mat = self.material_manager.get_material(i)
            if not mat:
                continue
            img, name = mat
            thumbnail = self.create_thumbnail(img, 64, 64)
            icon = QIcon(thumbnail)
            item = QListWidgetItem(icon, f"[{i}] {name} ({img.width}x{img.height})")
            item.setData(Qt.ItemDataRole.UserRole, i)
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
    
    def add_selected_to_timebase(self):
        """Append selected materials as new frames to the main timebase and all timelines."""
        selected_rows = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            selected_rows.append(mat_idx if mat_idx is not None else index.row())
        if not selected_rows:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return
        
        try:
            # Create a main timeline if none exists
            if not self.multi_editor.timelines:
                self.multi_editor.add_timeline("Main")
                self.multi_editor.set_main_timeline(0)
            
            # Auto-set output size based on first material if empty
            if self.multi_editor.get_frame_count() == 0 and selected_rows:
                first_material_row = selected_rows[0]
                if first_material_row < len(self.material_manager):
                    material = self.material_manager.get_material(first_material_row)
                    if material:
                        img, name = material
                        self.width_spinbox.setValue(img.width)
                        self.height_spinbox.setValue(img.height)
            
            # Append timebase frames
            duration = 100
            if self.timeline_tabs.count() > 0:
                # If main tab exists and has a widget, read its spinbox if available
                current_widget = self.timeline_tabs.currentWidget()
                if hasattr(current_widget, 'timeline_widget') and current_widget.timeline_widget.is_main_timebase:
                    duration = current_widget.timeline_widget.duration_spinbox.value()
            self.multi_editor.add_timebase_frames(len(selected_rows), duration)

            # If only one timeline exists, set its frames' materials in order
            # For new timelines added later, frames are already created (empty materials)
            main_idx = self.multi_editor.main_timeline_index
            main_tl = self.multi_editor.get_timeline(main_idx)
            if main_tl is not None:
                # Assign materials to the newly appended frames at the end
                start = len(main_tl.frames) - len(selected_rows)
                for i, material_idx in enumerate(selected_rows):
                    pos = start + i
                    if 0 <= pos < len(main_tl.frames):
                        main_tl.frames[pos].material_index = material_idx
                        main_tl.frames[pos].x = 0
                        main_tl.frames[pos].y = 0
            
            self.refresh_timeline()
        
        except Exception as e:
            print(f"ERROR in add_selected_to_timeline: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to add materials to timebase:\n{str(e)}")

    def add_selected_to_current_timeline(self):
        """Assign selected materials into the current timeline sequentially.

        If the current tab is the main timebase, reuse Add to Timebase.
        If more slots are needed, extends the timebase for all timelines.
        """
        mat_indices = []
        for index in self.materials_list.selectedIndexes():
            item = self.materials_list.item(index.row())
            mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            mat_indices.append(mat_idx if mat_idx is not None else index.row())
        if not mat_indices:
            QMessageBox.warning(self, "Warning", "Please select at least one material!")
            return

        # Ensure at least one timeline exists
        if not self.multi_editor.timelines:
            self.multi_editor.add_timeline("Main")
            self.multi_editor.set_main_timeline(0)

        current_index = self.timeline_tabs.currentIndex()
        if current_index < 0:
            current_index = 0

        if current_index == self.multi_editor.main_timeline_index:
            # Append to timebase directly
            self.add_selected_to_timebase()
            return

        tl = self.multi_editor.get_timeline(current_index)
        if tl is None:
            return

        frame_count = self.multi_editor.get_frame_count()
        # Find first empty slot to place materials
        start = None
        for i in range(frame_count):
            if i >= len(tl.frames) or tl.frames[i].material_index is None:
                start = i
                break
        if start is None:
            start = frame_count

        needed = (start + len(mat_indices)) - frame_count
        if needed > 0:
            duration = 100
            # Use main timebase default duration if available
            main_idx = self.multi_editor.main_timeline_index
            main_tab = self.timeline_tabs.widget(main_idx) if 0 <= main_idx < self.timeline_tabs.count() else None
            if hasattr(main_tab, 'timeline_widget') and main_tab.timeline_widget.is_main_timebase:
                duration = main_tab.timeline_widget.duration_spinbox.value()
            self.multi_editor.add_timebase_frames(needed, duration)
            frame_count = self.multi_editor.get_frame_count()

        self.multi_editor.ensure_timeline_length(current_index, frame_count)
        for offset, mat_idx in enumerate(mat_indices):
            pos = start + offset
            if 0 <= pos < len(tl.frames):
                tl.frames[pos].material_index = mat_idx
                tl.frames[pos].x = 0
                tl.frames[pos].y = 0

        self.refresh_timeline()
        self.update_preview()
    
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
        new_order = []
        for row in range(tw.timeline_table.rowCount()):
            item = tw.timeline_table.item(row, 0)
            idx = item.data(Qt.ItemDataRole.UserRole) if item else None
            if idx is not None:
                new_order.append(idx)
        # If we are on main timeline tab, reorder timebase
        if current_index == self.multi_editor.main_timeline_index:
            # Reorder durations and all timelines according to new_order
            if len(new_order) == len(self.multi_editor.durations_ms):
                # Apply permutation
                self.multi_editor.durations_ms = [self.multi_editor.durations_ms[i] for i in new_order]
                for t in self.multi_editor.timelines:
                    t.frames = [t.frames[i] for i in new_order]
        else:
            # For non-main timelines, only reorder that timeline's frames to match new order
            tl = self.multi_editor.get_timeline(current_index)
            if tl and len(new_order) == len(tl.frames):
                tl.frames = [tl.frames[i] for i in new_order]
        self.refresh_timeline()
        self.update_preview()
    
    def on_apply_duration(self, duration: int, apply_to_all: bool):
        """Handle duration change requests from timeline"""
        # Only the main timeline tab can change durations
        current_index = self.timeline_tabs.currentIndex()
        if current_index != self.multi_editor.main_timeline_index:
            return
        if apply_to_all:
            self.multi_editor.set_timebase_all_durations(duration)
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(self, "Success", f"Applied duration {duration}ms to all {self.multi_editor.get_frame_count()} frames.")
        else:
            tab = self.timeline_tabs.widget(current_index)
            if not hasattr(tab, 'timeline_widget'):
                return
            tw = tab.timeline_widget
            selected_items = tw.timeline_table.selectedIndexes()
            if not selected_items:
                QMessageBox.warning(self, "Warning", "Please select one or more frames!")
                return
            frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None})
            for frame_index in frame_indices:
                self.multi_editor.set_timebase_duration(frame_index, duration)
            self.refresh_timeline()
            self.update_preview()
            QMessageBox.information(self, "Success", f"Applied duration {duration}ms to {len(frame_indices)} selected frames.")
    
    def export_gif(self):
        """Export GIF from multi timelines"""
        if self.multi_editor.get_frame_count() == 0:
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
                
                self.gif_builder.build_from_multitimeline(
                    self.multi_editor,
                    self.material_manager,
                    file_path,
                )
                
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None})
        if not frame_indices:
            return
        if current_index == self.multi_editor.main_timeline_index:
            # Insert duplicates as a contiguous block after the last selected row (affects timebase and all timelines)
            insert_pos = frame_indices[-1]
            original_durs = list(self.multi_editor.durations_ms)
            dup_durs = [original_durs[i] for i in frame_indices]
            self.multi_editor.durations_ms = (
                original_durs[: insert_pos + 1] + dup_durs + original_durs[insert_pos + 1 :]
            )
            for t in self.multi_editor.timelines:
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
            tl = self.multi_editor.get_timeline(current_index)
            if not tl:
                return
            n = self.multi_editor.get_frame_count()
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None}, reverse=True)
        if not frame_indices:
            return
        if current_index == self.multi_editor.main_timeline_index:
            self.multi_editor.remove_timebase_frames(frame_indices)
        else:
            # Remove within current timeline and append empty frames to keep length
            tl = self.multi_editor.get_timeline(current_index)
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
        if current_index == self.multi_editor.main_timeline_index:
            # Move timebase and all timelines
            n = self.multi_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(1, n):
                if order[i] in selected_set and order[i - 1] not in selected_set:
                    order[i - 1], order[i] = order[i], order[i - 1]
            self.multi_editor.durations_ms = [self.multi_editor.durations_ms[i] for i in order]
            for t in self.multi_editor.timelines:
                t.frames = [t.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        else:
            # Move only current timeline rows
            tl = self.multi_editor.get_timeline(current_index)
            if not tl:
                return
            n = self.multi_editor.get_frame_count()
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
        if selected_rows[-1] >= self.multi_editor.get_frame_count() - 1:
            return
        if current_index == self.multi_editor.main_timeline_index:
            n = self.multi_editor.get_frame_count()
            selected_set = set(selected_rows)
            order = list(range(n))
            for i in range(n - 2, -1, -1):
                if order[i] in selected_set and order[i + 1] not in selected_set:
                    order[i], order[i + 1] = order[i + 1], order[i]
            self.multi_editor.durations_ms = [self.multi_editor.durations_ms[i] for i in order]
            for t in self.multi_editor.timelines:
                t.frames = [t.frames[i] for i in order]
            inv = {order[i]: i for i in range(n)}
            new_positions = [inv[i] for i in selected_rows]
        else:
            tl = self.multi_editor.get_timeline(current_index)
            if not tl:
                return
            n = self.multi_editor.get_frame_count()
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None})
        if not frame_indices:
            QMessageBox.warning(self, "Warning", "No valid frames selected!")
            return
        offset_x = self.batch_offset_x.value()
        offset_y = self.batch_offset_y.value()
        tl = self.multi_editor.get_timeline(current_index)
        changed = 0
        if tl:
            for fi in frame_indices:
                self.multi_editor.ensure_timeline_length(current_index, fi + 1)
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
    
    def refresh_timeline(self):
        """Refresh timeline tabs and the current tab's table content."""
        # Ensure at least one timeline exists
        if not self.multi_editor.timelines:
            self.multi_editor.add_timeline("Main")
            self.multi_editor.set_main_timeline(0)

        # Ensure tab count matches timelines
        while self.timeline_tabs.count() > len(self.multi_editor.timelines):
            self.timeline_tabs.removeTab(self.timeline_tabs.count() - 1)
        while self.timeline_tabs.count() < len(self.multi_editor.timelines):
            idx = self.timeline_tabs.count()
            tab = QWidget()
            v = QVBoxLayout()
            timeline_widget = TimelineWidget()
            timeline_widget.set_material_manager(self.material_manager)
            # Mark main
            timeline_widget.set_is_main_timebase(idx == self.multi_editor.main_timeline_index)
            # Connect signals
            timeline_widget.sequence_changed.connect(self.on_sequence_changed)
            timeline_widget.timeline_table.itemSelectionChanged.connect(self.on_timeline_selection_changed)
            timeline_widget.apply_duration_requested.connect(self.on_apply_duration)
            # Store on tab for later access
            tab.timeline_widget = timeline_widget
            v.addWidget(timeline_widget)
            tab.setLayout(v)
            # Set initial tab name with asterisk if it's the main timeline
            timeline_name = self.multi_editor.timelines[idx].name
            if idx == self.multi_editor.main_timeline_index and not timeline_name.startswith('*'):
                timeline_name = f"★ {timeline_name}"
            self.timeline_tabs.addTab(tab, timeline_name)

        # Update which tab is main and update tab names with asterisk
        for i in range(self.timeline_tabs.count()):
            tab = self.timeline_tabs.widget(i)
            if hasattr(tab, 'timeline_widget'):
                tab.timeline_widget.set_is_main_timebase(i == self.multi_editor.main_timeline_index)
            
            # Update tab name with asterisk for main timeline
            timeline_name = self.multi_editor.timelines[i].name
            if i == self.multi_editor.main_timeline_index:
                # Add asterisk to main timeline name
                if not timeline_name.startswith('★ '):
                    timeline_name = f"★ {timeline_name}"
            else:
                # Remove asterisk from non-main timeline names
                if timeline_name.startswith('★ '):
                    timeline_name = timeline_name[2:]
            
            self.timeline_tabs.setTabText(i, timeline_name)

        # Populate current tab table
        current_index = self.timeline_tabs.currentIndex()
        if current_index < 0:
            current_index = 0
            self.timeline_tabs.setCurrentIndex(0)
        tab = self.timeline_tabs.widget(current_index)
        if not hasattr(tab, 'timeline_widget'):
            return
        tw = tab.timeline_widget

        # Block signals while filling
        tw.timeline_table.blockSignals(True)
        tw.timeline_table.setRowCount(0)

        frame_count = self.multi_editor.get_frame_count()
        tl = self.multi_editor.get_timeline(current_index)
        for i in range(frame_count):
            tw.timeline_table.insertRow(i)

            # Column 0 index
            index_item = QTableWidgetItem(str(i + 1))
            index_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            index_item.setFlags(index_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            index_item.setData(Qt.ItemDataRole.UserRole, i)
            tw.timeline_table.setItem(i, 0, index_item)
            
            # Column 1 preview
            preview_item = QTableWidgetItem()
            mat_idx = None
            if tl and i < len(tl.frames):
                mat_idx = tl.frames[i].material_index
            if mat_idx is not None and mat_idx < len(self.material_manager):
                material = self.material_manager.get_material(mat_idx)
                if material:
                    img, name = material
                    thumbnail = self.create_thumbnail(img, 64, 64)
                    preview_item.setData(Qt.ItemDataRole.DecorationRole, thumbnail)
            preview_item.setFlags(preview_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            preview_item.setData(Qt.ItemDataRole.UserRole, i)
            tw.timeline_table.setItem(i, 1, preview_item)

            # Column 2 info (material name + offset)
            text = "Empty"
            if tl and i < len(tl.frames):
                fr = tl.frames[i]
                if fr.material_index is not None and fr.material_index < len(self.material_manager):
                    mat = self.material_manager.get_material(fr.material_index)
                    if mat:
                        _, mat_name = mat
                        text = f"[{fr.material_index}] {mat_name} | Pos({fr.x}, {fr.y})"
                else:
                    text = f"Empty | Pos({fr.x}, {fr.y})"
            frame_item = QTableWidgetItem(text)
            frame_item.setFlags(frame_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            frame_item.setData(Qt.ItemDataRole.UserRole, i)
            tw.timeline_table.setItem(i, 2, frame_item)

            # Column 3 duration (from main timebase)
            dur = 0
            if 0 <= i < len(self.multi_editor.durations_ms):
                dur = self.multi_editor.durations_ms[i]
            duration_item = QTableWidgetItem(str(dur))
            duration_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            duration_item.setFlags(duration_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            duration_item.setData(Qt.ItemDataRole.UserRole, i)
            tw.timeline_table.setItem(i, 3, duration_item)

            tw.timeline_table.setRowHeight(i, 70)

        # Sync duration spinbox to default
        if hasattr(tw, 'duration_spinbox') and tw.is_main_timebase:
            if self.multi_editor.durations_ms:
                tw.duration_spinbox.setValue(self.multi_editor.durations_ms[0])

        tw.timeline_table.blockSignals(False)

        # Sync timeline-offset spinboxes with current tab timeline
        tl = self.multi_editor.get_timeline(current_index)
        if tl is not None:
            self.timeline_offset_x.blockSignals(True)
            self.timeline_offset_y.blockSignals(True)
            self.timeline_offset_x.setValue(tl.offset_x)
            self.timeline_offset_y.setValue(tl.offset_y)
            self.timeline_offset_x.blockSignals(False)
            self.timeline_offset_y.blockSignals(False)

    def on_timeline_tab_changed(self, index: int):
        self.refresh_timeline()
        self.update_preview()

    def on_apply_timeline_offset(self):
        idx = self.timeline_tabs.currentIndex()
        tl = self.multi_editor.get_timeline(idx)
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

    def on_set_main_timeline(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0:
            return
        self.multi_editor.set_main_timeline(idx)
        self.refresh_timeline()
        self.update_preview()

    def on_add_timeline(self):
        name = f"Timeline {len(self.multi_editor.timelines) + 1}"
        new_idx = self.multi_editor.add_timeline(name)
        # Ensure new timeline matches current timebase length
        self.multi_editor.ensure_timeline_length(new_idx, self.multi_editor.get_frame_count())
        self.refresh_timeline()
        self.timeline_tabs.setCurrentIndex(new_idx)

    def on_remove_timeline(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0:
            return
        if idx == self.multi_editor.main_timeline_index:
            QMessageBox.warning(self, "Warning", "Cannot remove the main timeline.")
            return
        self.multi_editor.remove_timeline(idx)
        self.refresh_timeline()
        self.update_preview()

    def on_move_timeline_down(self):
        idx = self.timeline_tabs.currentIndex()
        if idx <= 0:
            return
        self.multi_editor.move_timeline(idx, idx - 1)
        self.refresh_timeline()
        self.timeline_tabs.setCurrentIndex(idx - 1)

    def on_move_timeline_up(self):
        idx = self.timeline_tabs.currentIndex()
        if idx < 0 or idx >= self.timeline_tabs.count() - 1:
            return
        self.multi_editor.move_timeline(idx, idx + 1)
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None})
        if not frame_indices:
            return
        mat_idx = selected_rows[0]
        tl = self.multi_editor.get_timeline(current_index)
        if not tl:
            return
        # Ensure timeline has enough frames
        self.multi_editor.ensure_timeline_length(current_index, max(frame_indices) + 1)
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
        frame_indices = sorted({item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole) is not None})
        if not frame_indices:
            return
        if len(frame_indices) != len(selected_material_rows):
            QMessageBox.warning(self, "Warning", f"Selected frames ({len(frame_indices)}) must match selected materials ({len(selected_material_rows)}).")
            return
        tl = self.multi_editor.get_timeline(current_index)
        if not tl:
            return
        # Ensure length and assign one-to-one
        self.multi_editor.ensure_timeline_length(current_index, max(frame_indices) + 1)
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
        """Handle preview mode change"""
        if self.preview_all_checkbox.isChecked():
            # Preview all frames (animation)
            self.preview_frame_spinbox.setEnabled(False)
            self.update_preview()
        else:
            # Preview single frame
            self.preview_frame_spinbox.setEnabled(True)
            self.preview_frame_spinbox.setMaximum(max(1, self.multi_editor.get_frame_count()))
            # If there's a selection, sync to it
            current_index = self.timeline_tabs.currentIndex()
            tab = self.timeline_tabs.widget(current_index)
            if hasattr(tab, 'timeline_widget'):
                tw = tab.timeline_widget
                selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
                if selected_rows:
                    self.preview_frame_spinbox.blockSignals(True)
                    self.preview_frame_spinbox.setValue(selected_rows[0] + 1)
                    self.preview_frame_spinbox.blockSignals(False)
            self.update_single_frame_preview()
    
    def update_single_frame_preview(self):
        """Update preview for a single selected frame"""
        if self.multi_editor.get_frame_count() == 0:
            return
        # Prefer current timeline selection if any; otherwise use spinbox
        frame_idx = None
        current_index = self.timeline_tabs.currentIndex()
        tab = self.timeline_tabs.widget(current_index)
        if hasattr(tab, 'timeline_widget'):
            tw = tab.timeline_widget
            selected_rows = sorted({idx.row() for idx in tw.timeline_table.selectedIndexes()})
            if selected_rows:
                frame_idx = selected_rows[0]
        if frame_idx is None:
            frame_idx = self.preview_frame_spinbox.value() - 1
        if frame_idx >= self.multi_editor.get_frame_count():
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
            
            # Compose single frame
            img = self.gif_builder._compose_from_multi_timeline_frame(self.multi_editor, self.material_manager, frame_idx)
            dur = self.multi_editor.durations_ms[frame_idx] if 0 <= frame_idx < len(self.multi_editor.durations_ms) else 100
            self.preview.set_frames([(img, dur)])
            
        except Exception as e:
            print(f"ERROR in update_single_frame_preview: {e}")
            import traceback
            traceback.print_exc()
    
    def update_preview(self):
        """Update preview"""
        if self.multi_editor.get_frame_count() == 0:
            return
        
        # Update preview frame spinbox range
        total_frames = self.multi_editor.get_frame_count()
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
            
            frames = self.gif_builder.get_multitimeline_preview_frames(
                self.multi_editor,
                self.material_manager,
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
                selected_rows = []
                for index in self.materials_list.selectedIndexes():
                    item = self.materials_list.item(index.row())
                    mat_idx = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
                    selected_rows.append(mat_idx if mat_idx is not None else index.row())
                selected_rows = sorted(selected_rows)
                
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
        """Save current multi-timeline state into in-memory template list."""
        if self.multi_editor.get_frame_count() == 0:
            QMessageBox.warning(self, "Warning", "No frames to save as template!")
            return
        try:
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_multi_template(
                self.multi_editor,
                self.width_spinbox.value(),
                self.height_spinbox.value(),
                self.loop_spinbox.value(),
                self.transparent_bg_checkbox.isChecked(),
                color_count
            )
            # Generate a simple name
            timestamp = datetime.now().strftime("%H:%M:%S")
            name = f"Template {len(self.templates) + 1} ({timestamp})"
            self.templates[name] = template
            self.refresh_template_list()
            info = TemplateManager.get_template_info(template)
            QMessageBox.information(
                self,
                "Saved",
                f"Saved template in memory.\nTimelines: {info.get('timeline_count', 0)}\nFrames: {info.get('frame_count', 0)}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save template: {str(e)}")
    
    def quick_apply_template(self):
        """Apply selected in-memory template to current editor."""
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
            # Apply depending on format
            if template.get("format") == "multi_timeline" or ("timelines" in template and "timebase" in template):
                new_editor, settings = TemplateManager.apply_multi_template(template)
                self.multi_editor = new_editor
                # Apply settings
                if settings:
                    self.width_spinbox.setValue(settings.get('output_width', self.width_spinbox.value()))
                    self.height_spinbox.setValue(settings.get('output_height', self.height_spinbox.value()))
                    self.loop_spinbox.setValue(settings.get('loop_count', self.loop_spinbox.value()))
                    self.transparent_bg_checkbox.setChecked(settings.get('transparent_bg', self.transparent_bg_checkbox.isChecked()))
                    color_count = settings.get('color_count', int(self.color_palette_combo.currentText()))
                    self.color_palette_combo.setCurrentText(str(color_count))
                self.refresh_timeline()
                self.update_preview()
            else:
                QMessageBox.warning(self, "Unsupported", "Selected template format is not multi-timeline.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply template: {str(e)}")
    
    def quick_import_template(self):
        """Import a template JSON from disk into in-memory templates."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Template",
            self.last_template_dir,
            "JSON Files (*.json)"
        )
        if not file_path:
            return
        try:
            self.last_template_dir = str(Path(file_path).parent)
            template = TemplateManager.load_template_from_file(file_path)
            info = TemplateManager.get_template_info(template)
            if info.get('format') != 'multi_timeline':
                QMessageBox.warning(self, "Warning", "Only multi-timeline templates are supported.")
                return
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
        durations and all timelines to preserve alignment.
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

        if current_index == self.multi_editor.main_timeline_index:
            # Reverse durations at selected positions
            original_durs = list(self.multi_editor.durations_ms)
            new_durs = list(original_durs)
            for dst, src in zip(selected_rows, target_rows):
                if 0 <= dst < len(new_durs) and 0 <= src < len(original_durs):
                    new_durs[dst] = original_durs[src]
            self.multi_editor.durations_ms = new_durs
            # Reverse each timeline's frames at those positions
            for t in self.multi_editor.timelines:
                orig_frames = list(t.frames)
                new_frames = list(orig_frames)
                for dst, src in zip(selected_rows, target_rows):
                    if 0 <= dst < len(new_frames) and 0 <= src < len(orig_frames):
                        new_frames[dst] = orig_frames[src]
                t.frames = new_frames
        else:
            tl = self.multi_editor.get_timeline(current_index)
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
        # Populate list with name and brief info
        for name, tpl in self.templates.items():
            try:
                info = TemplateManager.get_template_info(tpl)
                if info.get('format') == 'multi_timeline':
                    subtitle = f"{info.get('timeline_count', 0)} TL, {info.get('frame_count', 0)} F"
                else:
                    subtitle = f"{info.get('frame_count', 0)} F"
            except Exception:
                subtitle = "invalid"
            item = QListWidgetItem(f"{name} - {subtitle}")
            self.template_list.addItem(item)
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
            "<li>Auto-save protection</li>"
            "</ul>"
            "<p>Version 1.0</p>"
        )
    
    def auto_save_template(self):
        """Automatically save current work as a multi-timeline template."""
        if not self.auto_save_enabled:
            return
        # Only save if there's actual content
        if self.multi_editor.get_frame_count() == 0:
            return
        try:
            # Create content hash to avoid duplicate saves
            content_hash = self._get_content_hash()
            if content_hash == self.last_auto_save_content_hash:
                return  # No changes since last save
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            frame_count = self.multi_editor.get_frame_count()
            material_count = len(self.material_manager)
            file_path = self.auto_save_file
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_multi_template(
                self.multi_editor,
                self.width_spinbox.value(),
                self.height_spinbox.value(),
                self.loop_spinbox.value(),
                self.transparent_bg_checkbox.isChecked(),
                color_count
            )
            template["auto_save_metadata"] = {
                "timestamp": timestamp,
                "frame_count": frame_count,
                "material_count": material_count,
                "content_hash": content_hash
            }
            TemplateManager.save_template_to_file(template, str(file_path))
            self.last_auto_save_content_hash = content_hash
            print(f"Auto-saved: {file_path.name}")
        except Exception as e:
            print(f"Auto-save failed: {e}")
    
    def _get_content_hash(self):
        """Generate hash of current multi-timeline content for change detection"""
        import hashlib
        parts = []
        # Timebase
        parts.append("durations:" + ",".join(str(d) for d in self.multi_editor.durations_ms))
        # Timelines
        for t in self.multi_editor.timelines:
            parts.append(f"tl:{t.name}:{t.offset_x}:{t.offset_y}")
            for fr in t.frames:
                mi = "n" if fr.material_index is None else str(fr.material_index)
                parts.append(f"f:{mi}:{fr.x}:{fr.y}")
        # Settings
        parts.append(f"settings:{self.width_spinbox.value()}:{self.height_spinbox.value()}:{self.loop_spinbox.value()}:{self.transparent_bg_checkbox.isChecked()}:{self.color_palette_combo.currentText()}")
        return hashlib.md5("|".join(parts).encode()).hexdigest()
    
    
    def closeEvent(self, event):
        """Handle application closing - perform emergency auto-save"""
        if self.auto_save_enabled and self.multi_editor.get_frame_count() > 0:
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
        """Restore from the latest auto-save"""
        try:
            # Check if auto-save file exists
            if not self.auto_save_file.exists():
                QMessageBox.information(self, "No Auto-Save", "No auto-save file found.")
                return
            
            # Load template
            template = TemplateManager.load_template_from_file(str(self.auto_save_file))
            info = TemplateManager.get_template_info(template)
            if info.get('format') == 'multi_timeline':
                new_editor, settings = TemplateManager.apply_multi_template(template)
                self.multi_editor = new_editor
                if settings:
                    self.width_spinbox.setValue(settings.get("output_width", self.width_spinbox.value()))
                    self.height_spinbox.setValue(settings.get("output_height", self.height_spinbox.value()))
                    self.loop_spinbox.setValue(settings.get("loop_count", self.loop_spinbox.value()))
                    self.transparent_bg_checkbox.setChecked(settings.get("transparent_bg", self.transparent_bg_checkbox.isChecked()))
                    color_count = settings.get("color_count", int(self.color_palette_combo.currentText()))
                    color_text = str(color_count)
                    if color_text in [self.color_palette_combo.itemText(i) for i in range(self.color_palette_combo.count())]:
                        self.color_palette_combo.setCurrentText(color_text)
                # Refresh UI
                self.refresh_timeline()
            
            # Get metadata
            metadata = template.get("auto_save_metadata", {})
            timestamp = metadata.get("timestamp", "unknown")
            
            QMessageBox.information(
                self,
                "Auto-Save Restored",
                f"Restored from auto-save:\n{self.auto_save_file.name}\n\n"
                f"Saved: {timestamp}\n"
                f"Frames: {metadata.get('frame_count', info.get('frame_count', 0))}\n"
                f"Materials: {metadata.get('material_count', 0)}"
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
            main_idx = self.multi_editor.main_timeline_index
            main_timeline = self.multi_editor.get_timeline(main_idx)
            
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
    
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

