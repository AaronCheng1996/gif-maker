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
                              QComboBox, QStackedWidget, QColorDialog, QInputDialog,
                              QStatusBar, QMenu)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QPixmap, QImage, QAction, QKeySequence

from PIL import Image
from collections import Counter

from .core import MaterialManager, GifBuilder, TemplateManager, GroupManager, CompositionGroup, FrameEntry, SubGroupEntry
from .widgets import (AppTheme, PreviewWidget, PreviewPageWidget,
                      TileSplitterPage, BatchProcessorWidget, GifOptimizerWidget,
                      GroupCompositionWidget, VideoToGifWidget, ClipToGifWidget,
                      SettingsDialog)
from .i18n import tr, set_language
from . import settings as AppSettings


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

        # Recent files (max 8 entries)
        self.recent_files: List[str] = []

        # Undo / Redo — snapshot-based with debounce
        self._undo_stack: List[dict] = []
        self._redo_stack: List[dict] = []
        self._undo_in_progress = False          # guard against restore → signal loop
        self._undo_debounce = QTimer()
        self._undo_debounce.setSingleShot(True)
        self._undo_debounce.timeout.connect(self._push_undo_snapshot)
        self._MAX_UNDO = 50

        # Auto-save (enabled by default)
        self.auto_save_enabled = True
        self.auto_save_interval = 5 * 60 * 1000  # 5 minutes
        self.auto_save_timer = QTimer()
        self.auto_save_timer.timeout.connect(self.auto_save_template)
        self.auto_save_timer.start(self.auto_save_interval)

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
        self.chroma_key_colors = []
        self.chroma_key_colors_all = []
        self.chroma_key_display_count = 10
    
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

        # Status bar setup
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_material_label = QLabel("Materials: 0")
        self._status_group_label = QLabel("Group: —")
        self._status_autosave_label = QLabel("Auto-save: ON")
        self._status_bar.addPermanentWidget(self._status_material_label)
        self._status_bar.addPermanentWidget(self._status_group_label)
        self._status_bar.addPermanentWidget(self._status_autosave_label)
        self._status_bar.showMessage("Ready", 3000)

        # Keyboard shortcuts
        self._setup_shortcuts()

        # Capture the initial (empty) snapshot so Undo can return to it
        self._capture_initial_snapshot()

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
        """Four full-screen top-level tabs.

        Composer / Tile Splitter share a single Material Library panel that is
        dynamically reparented (via QSplitter.insertWidget) when switching tabs.
        Batch Processor and GIF Optimizer have their own independent image lists.
        """
        # ── Shared Material Library (single widget, moved between tabs 0 & 1) ─
        self._material_lib_panel = self.create_material_library_panel()

        # ── Tab 0: Composer — [Material Library | Editor | Preview] ───────────
        editor_preview_splitter = QSplitter(Qt.Orientation.Horizontal)
        editor_preview_splitter.addWidget(self.create_middle_panel())
        editor_preview_splitter.addWidget(self.create_right_panel())
        editor_preview_splitter.setSizes([800, 400])

        self._composer_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._composer_splitter.addWidget(self._material_lib_panel)   # starts here
        self._composer_splitter.addWidget(editor_preview_splitter)
        self._composer_splitter.setSizes([320, 1280])

        # ── Tab 1: Tile Splitter — [Material Library | Image list | Tile preview]
        self.tile_splitter_page = TileSplitterPage()
        self.tile_splitter_page.tiles_created.connect(self.on_tiles_created)

        self._tile_outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        # material lib will be inserted at index 0 when this tab is active;
        # tile_splitter_page already has its own internal splitter
        self._tile_outer_splitter.addWidget(self.tile_splitter_page)

        # ── Tab 2: Batch Processor (self-contained, own image list) ───────────
        self.batch_processor = BatchProcessorWidget()
        self.batch_processor.batch_complete.connect(self.on_batch_complete)
        self.batch_processor.set_templates(self.templates)

        # ── Tab 3: GIF Optimizer (self-contained, own image list) ─────────────
        self.gif_optimizer = GifOptimizerWidget()

        # ── Tab 4: Video to GIF (self-contained, multi-format input) ──────────
        self.video_to_gif = VideoToGifWidget()

        # ── Tab 5: Clip to GIF (single video, visual range selector) ──────────
        self.clip_to_gif = ClipToGifWidget()

        # ── Top-level QTabWidget ───────────────────────────────────────────────
        self.tool_tabs = QTabWidget()
        self.tool_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tool_tabs.addTab(self._composer_splitter,   tr("🎬 Composer"))
        self.tool_tabs.addTab(self._tile_outer_splitter, tr("✂️ Tile Splitter"))
        self.tool_tabs.addTab(self.batch_processor,      tr("⚡ Batch Processor"))
        self.tool_tabs.addTab(self.gif_optimizer,        tr("🔧 GIF Optimizer"))
        self.tool_tabs.addTab(self.video_to_gif,         tr("🎥 Video to GIF"))
        self.tool_tabs.addTab(self.clip_to_gif,          tr("🎞️ Clip to GIF"))

        self.tool_tabs.currentChanged.connect(self._on_tool_tab_changed)

        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tool_tabs)
        return wrapper

    def _on_tool_tab_changed(self, index: int):
        """Dynamically move the shared Material Library into the active tab's splitter."""
        if index == 0:   # Composer
            self._composer_splitter.insertWidget(0, self._material_lib_panel)
            self._material_lib_panel.show()
            self._composer_splitter.setSizes([320, 1280])
        elif index == 1:  # Tile Splitter
            self._tile_outer_splitter.insertWidget(0, self._material_lib_panel)
            self._material_lib_panel.show()
            self._tile_outer_splitter.setSizes([320, 1280])
        else:
            # Batch / Optimizer — hide the panel (collapses in current splitter)
            self._material_lib_panel.hide()
    
    def show_main_page(self):
        """顯示主頁面"""
        self.stacked_widget.setCurrentWidget(self.main_page)
    
    def show_preview_page(self):
        """顯示預覽頁面"""
        self.stacked_widget.setCurrentWidget(self.preview_page)
    
    def create_material_library_panel(self) -> QWidget:
        """Permanent left-side material library panel, always visible across all tool tabs."""
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)

        title = QLabel(tr("Material Library"))
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #e6eaf6; padding: 4px 0;")
        layout.addWidget(title)

        layout.addWidget(self.create_materials_tab())

        panel.setLayout(layout)
        return panel
    
    def create_materials_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        
        load_group = QGroupBox(tr("Load Materials"))
        load_layout = QVBoxLayout()
        
        self.load_image_btn = QPushButton(tr("Load Image"))
        self.load_image_btn.clicked.connect(self.load_image_material)
        load_layout.addWidget(self.load_image_btn)

        self.load_gif_btn = QPushButton(tr("Load GIF (Extract Frames)"))
        self.load_gif_btn.clicked.connect(self.load_gif_material)
        load_layout.addWidget(self.load_gif_btn)

        self.load_multiple_btn = QPushButton(tr("Load Multiple Images"))
        self.load_multiple_btn.clicked.connect(self.load_multiple_materials)
        load_layout.addWidget(self.load_multiple_btn)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        lib_header_row = QHBoxLayout()
        list_label = QLabel(tr("Material Library"))
        list_label.setStyleSheet("font-weight: 600; font-size: 12px; color: #8a95b8;")
        lib_header_row.addWidget(list_label)
        lib_header_row.addStretch()
        self.material_view_btn = QPushButton(tr("⊞ Grid"))
        self.material_view_btn.setFixedSize(80, 26)
        self.material_view_btn.setToolTip("Switch between list and grid (icon) view")
        self.material_view_btn.setCheckable(True)
        self.material_view_btn.clicked.connect(self._toggle_material_view)
        lib_header_row.addWidget(self.material_view_btn)
        layout.addLayout(lib_header_row)

        self._material_icon_mode = False  # False = list, True = icon/grid

        # Sorting controls for materials
        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel(tr("Sort:")))
        self.material_sort_combo = QComboBox()
        self.material_sort_combo.addItems([
            tr("Default"),
            tr("Name (A→Z)"),
            tr("Name (Z→A)"),
            tr("Width (Large→Small)"),
            tr("Height (Large→Small)"),
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

        self.remove_material_btn = QPushButton(tr("Remove Selected"))
        self.remove_material_btn.clicked.connect(self.remove_selected_material)
        material_actions.addWidget(self.remove_material_btn)

        self.clear_materials_btn2 = QPushButton(tr("Clear All"))
        self.clear_materials_btn2.clicked.connect(self.clear_materials)
        material_actions.addWidget(self.clear_materials_btn2)

        layout.addLayout(material_actions)

        # Group addition buttons
        group_add_layout = QVBoxLayout()
        group_add_layout.setSpacing(4)

        self.add_to_existing_group_btn = QPushButton(tr("➕ Add to Selected Group"))
        self.add_to_existing_group_btn.setToolTip("Add selected materials to the currently selected group")
        self.add_to_existing_group_btn.clicked.connect(self.add_materials_to_existing_group)
        group_add_layout.addWidget(self.add_to_existing_group_btn)

        self.add_as_single_group_btn = QPushButton(tr("📦 Add as New Group"))
        self.add_as_single_group_btn.setToolTip("Create a standalone new group from selected materials (not nested into any group)")
        self.add_as_single_group_btn.clicked.connect(self.add_materials_as_standalone_group)
        group_add_layout.addWidget(self.add_as_single_group_btn)

        self.add_to_group_as_subgroup_btn = QPushButton(tr("📦➕ Add to Selected Group as New Group"))
        self.add_to_group_as_subgroup_btn.setToolTip("Create a new group from selected materials and nest it into the currently selected group")
        self.add_to_group_as_subgroup_btn.clicked.connect(self.add_materials_as_single_group)
        group_add_layout.addWidget(self.add_to_group_as_subgroup_btn)

        self.add_each_as_group_btn = QPushButton(tr("📦📦 Add Each as Group"))
        self.add_each_as_group_btn.setToolTip("Create a separate group for each selected material and add to timeline")
        self.add_each_as_group_btn.clicked.connect(self.add_materials_as_separate_groups)
        group_add_layout.addWidget(self.add_each_as_group_btn)

        layout.addLayout(group_add_layout)
        
        # Export materials section
        export_group = QGroupBox(tr("Export Materials"))
        export_layout = QVBoxLayout()

        self.export_selected_btn = QPushButton(tr("Export Selected Images"))
        self.export_selected_btn.clicked.connect(self.export_selected_materials)
        export_layout.addWidget(self.export_selected_btn)

        self.export_all_btn = QPushButton(tr("Export All Images"))
        self.export_all_btn.clicked.connect(self.export_all_materials)
        export_layout.addWidget(self.export_all_btn)
        
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)
        
        widget.setLayout(layout)
        return widget
    
    def create_middle_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        title = QLabel(tr("Composition (Groups)"))
        title.setStyleSheet("font-weight: 600; font-size: 14px; color: #e6eaf6; padding: 4px 0;")
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
        if getattr(self, 'auto_size_checkbox', None) and self.auto_size_checkbox.isChecked():
            self.auto_fit_output_size()
        self.update_preview()
        self._update_status_labels()

    def _on_auto_size_toggled(self, state: int):
        """Enable/disable size spinboxes based on Auto checkbox; auto-fit immediately when enabled."""
        manual = (state == 0)
        self.width_spinbox.setEnabled(manual)
        self.height_spinbox.setEnabled(manual)
        if not manual:
            self.auto_fit_output_size()

    def _on_group_entries_changed(self):
        self.update_preview()
        if not self._undo_in_progress:
            self._undo_debounce.start(300)
    
    def create_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        # Preview background color button (compact toolbar)
        preview_controls = QHBoxLayout()
        self.preview_bg_btn = QPushButton(tr("🎨 BG"))
        self.preview_bg_btn.setToolTip("Set preview background color (does not affect export)")
        self.preview_bg_btn.setMaximumWidth(60)
        self.preview_bg_btn.clicked.connect(self.on_choose_preview_bg)
        preview_controls.addWidget(self.preview_bg_btn)
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
        template_group = QGroupBox(tr("Template Manager"))
        template_layout = QVBoxLayout()
        template_layout.setSpacing(3)
        
        # Template list (larger for easier management)
        self.template_list = QListWidget()
        self.template_list.setMinimumHeight(120)  # More visible space
        self.template_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        template_layout.addWidget(self.template_list)
        
        # Template action buttons (2 rows)
        template_row1 = QHBoxLayout()
        self.save_template_btn = QPushButton(tr("💾 Save"))
        self.save_template_btn.clicked.connect(self.quick_save_template)
        self.save_template_btn.setToolTip("Save current timeline as template")
        template_row1.addWidget(self.save_template_btn)

        self.apply_template_btn = QPushButton(tr("✓ Apply"))
        self.apply_template_btn.clicked.connect(self.quick_apply_template)
        self.apply_template_btn.setToolTip("Apply selected template to current materials")
        template_row1.addWidget(self.apply_template_btn)
        template_layout.addLayout(template_row1)

        template_row2 = QHBoxLayout()
        self.import_template_btn = QPushButton(tr("📂 Import"))
        self.import_template_btn.clicked.connect(self.quick_import_template)
        self.import_template_btn.setToolTip("Import template from file")
        template_row2.addWidget(self.import_template_btn)

        self.export_template_btn = QPushButton(tr("💾 Export"))
        self.export_template_btn.clicked.connect(self.quick_export_template)
        self.export_template_btn.setToolTip("Export selected template to file")
        template_row2.addWidget(self.export_template_btn)

        self.remove_template_btn = QPushButton(tr("🗑 Remove"))
        self.remove_template_btn.clicked.connect(self.remove_template)
        self.remove_template_btn.setToolTip("Remove selected template from list")
        template_row2.addWidget(self.remove_template_btn)
        template_layout.addLayout(template_row2)
        
        template_group.setLayout(template_layout)
        layout.addWidget(template_group, stretch=1)  # Allow template section to expand
        
        # Compact settings section
        settings_group = QGroupBox(tr("Settings"))
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(3)
        
        # Size (more compact) — with Auto checkbox
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel(tr("Size:")))
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
        self.auto_size_checkbox = QCheckBox(tr("Auto"))
        self.auto_size_checkbox.setToolTip(
            "Auto-fit output size to materials whenever the selected group changes"
        )
        self.auto_size_checkbox.stateChanged.connect(self._on_auto_size_toggled)
        size_layout.addWidget(self.auto_size_checkbox)
        size_layout.addStretch()
        settings_layout.addLayout(size_layout)
        
        # Loop (compact)
        loop_layout = QHBoxLayout()
        loop_layout.addWidget(QLabel(tr("Loop:")))
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setMinimum(0)
        self.loop_spinbox.setMaximum(1000)
        self.loop_spinbox.setValue(0)
        self.loop_spinbox.setSpecialValueText("∞")
        loop_layout.addWidget(self.loop_spinbox)
        loop_layout.addStretch()
        settings_layout.addLayout(loop_layout)
        
        # Transparent BG
        self.transparent_bg_checkbox = QCheckBox(tr("Transparent BG"))
        self.transparent_bg_checkbox.stateChanged.connect(self.on_transparent_bg_changed)
        settings_layout.addWidget(self.transparent_bg_checkbox)
        
        # Color palette selection
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel(tr("Colors:")))
        self.color_palette_combo = QComboBox()
        self.color_palette_combo.addItems(["256", "128", "64", "32", "16"])
        self.color_palette_combo.setCurrentText("256")
        self.color_palette_combo.currentTextChanged.connect(self.on_color_palette_changed)
        color_layout.addWidget(self.color_palette_combo)
        color_layout.addStretch()
        settings_layout.addLayout(color_layout)
        
        # Chroma key (green screen) selection
        chroma_layout = QHBoxLayout()
        chroma_layout.addWidget(QLabel(tr("Chroma Key:")))
        self.chroma_key_combo = QComboBox()
        self.chroma_key_combo.addItem(tr("None (Disabled)"))
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
        auto_layout_group = QGroupBox(tr("Auto Layout"))
        auto_layout_layout = QVBoxLayout()
        auto_layout_layout.setSpacing(3)
        
        # Auto fit size button
        self.auto_fit_size_btn = QPushButton(tr("🔧 Auto Fit Size"))
        self.auto_fit_size_btn.clicked.connect(self.auto_fit_output_size)
        self.auto_fit_size_btn.setToolTip("Automatically adjust output size to fit all materials")
        auto_layout_layout.addWidget(self.auto_fit_size_btn)
        
        # Horizontal alignment buttons
        h_align_label = QLabel(tr("Horizontal:"))
        h_align_label.setStyleSheet("font-size: 10px; color: #8a95b8;")
        auto_layout_layout.addWidget(h_align_label)

        h_align_layout = QHBoxLayout()
        self.align_left_btn = QPushButton(tr("⬅ Left"))
        self.align_left_btn.clicked.connect(self.align_all_left)
        self.align_left_btn.setToolTip("Align all materials to the left")
        h_align_layout.addWidget(self.align_left_btn)

        self.align_center_h_btn = QPushButton(tr("↔ Center"))
        self.align_center_h_btn.clicked.connect(self.align_all_center_horizontal)
        self.align_center_h_btn.setToolTip("Center all materials horizontally")
        h_align_layout.addWidget(self.align_center_h_btn)

        self.align_right_btn = QPushButton(tr("➡ Right"))
        self.align_right_btn.clicked.connect(self.align_all_right)
        self.align_right_btn.setToolTip("Align all materials to the right")
        h_align_layout.addWidget(self.align_right_btn)

        auto_layout_layout.addLayout(h_align_layout)

        v_align_label = QLabel(tr("Vertical:"))
        v_align_label.setStyleSheet("font-size: 10px; color: #8a95b8;")
        auto_layout_layout.addWidget(v_align_label)

        v_align_layout = QHBoxLayout()
        self.align_top_btn = QPushButton(tr("⬆ Top"))
        self.align_top_btn.clicked.connect(self.align_all_top)
        self.align_top_btn.setToolTip("Align all materials to the top")
        v_align_layout.addWidget(self.align_top_btn)

        self.align_middle_btn = QPushButton(tr("↕ Middle"))
        self.align_middle_btn.clicked.connect(self.align_all_middle_vertical)
        self.align_middle_btn.setToolTip("Center all materials vertically")
        v_align_layout.addWidget(self.align_middle_btn)

        self.align_bottom_btn = QPushButton(tr("⬇ Bottom"))
        self.align_bottom_btn.clicked.connect(self.align_all_bottom)
        self.align_bottom_btn.setToolTip("Align all materials to the bottom")
        v_align_layout.addWidget(self.align_bottom_btn)
        
        auto_layout_layout.addLayout(v_align_layout)
        
        auto_layout_group.setLayout(auto_layout_layout)
        layout.addWidget(auto_layout_group, stretch=0)
        
        # Action buttons (compact)
        self.update_preview_btn = QPushButton(tr("🔄 Preview"))
        self.update_preview_btn.clicked.connect(self.update_preview)
        layout.addWidget(self.update_preview_btn)

        self.export_gif_btn = QPushButton(tr("💾 Export GIF"))
        self.export_gif_btn.clicked.connect(self.export_gif)
        self.export_gif_btn.setStyleSheet(
            "font-weight: 600; font-size: 13px; background-color: #1f6b40; "
            "color: #c8f0d8; border: 1px solid #2d8a54; border-radius: 4px; padding: 6px 14px;"
        )
        layout.addWidget(self.export_gif_btn)
        
        panel.setLayout(layout)
        return panel
    
    def create_menu_bar(self):
        menubar = self.menuBar()

        # Edit menu — Undo / Redo
        edit_menu = menubar.addMenu(tr("Edit"))
        self._undo_action = edit_menu.addAction(tr("Undo"), self.undo)
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._redo_action = edit_menu.addAction(tr("Redo"), self.redo)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Y"))

        file_menu = menubar.addMenu(tr("File"))

        file_menu.addAction(tr("Load Image"), self.load_image_material)
        file_menu.addAction(tr("Load GIF"), self.load_gif_material)
        file_menu.addSeparator()

        # Recent Files submenu (populated dynamically)
        self._recent_menu = file_menu.addMenu(tr("Recent Files"))
        self._rebuild_recent_menu()
        file_menu.addSeparator()

        file_menu.addAction(tr("Export GIF"), self.export_gif)
        file_menu.addAction(tr("Export All Groups as GIF"), self.batch_export_all_groups)
        file_menu.addAction(tr("Export Spritesheet (PNG)"), self.export_spritesheet)
        file_menu.addSeparator()
        file_menu.addAction(tr("Export Selected Materials"), self.export_selected_materials)
        file_menu.addAction(tr("Export All Materials"), self.export_all_materials)
        file_menu.addSeparator()

        # Auto-save menu items
        auto_save_menu = file_menu.addMenu(tr("Auto-Save"))
        auto_save_menu.addAction(tr("Restore Auto-Save"), self.restore_auto_save)
        auto_save_menu.addAction(tr("Toggle Auto-Save"), self.toggle_auto_save)

        file_menu.addSeparator()
        file_menu.addAction(tr("Exit"), self.close)

        # Settings menu
        settings_menu = menubar.addMenu(tr("Settings"))
        settings_menu.addAction(tr("Application Settings"), self._open_settings_dialog)

        help_menu = menubar.addMenu(tr("Help"))
        help_menu.addAction(tr("About"), self.show_about)

    def _open_settings_dialog(self):
        dlg = SettingsDialog(self)
        dlg.exec()
    
    def load_image_material(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image",
            self.last_image_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                self.last_image_dir = str(Path(file_path).parent)
                self.material_manager.load_from_image(file_path)
                self.refresh_materials_list()
                self._add_to_recent_files(file_path)
                self._status(f"Loaded: {Path(file_path).name}")
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
                self.last_gif_dir = str(Path(file_path).parent)
                self.material_manager.load_from_gif(file_path)
                self.refresh_materials_list()
                self._add_to_recent_files(file_path)
                self._status(f"GIF loaded — {len(self.material_manager)} frames total")
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
                self.last_image_dir = str(Path(file_paths[0]).parent)
                for file_path in file_paths:
                    self.material_manager.load_from_image(file_path)
                    self._add_to_recent_files(file_path)
                self.refresh_materials_list()
                self._status(f"Loaded {len(file_paths)} image(s)")
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
        self.material_view_btn.setText(tr("☰ List") if checked else tr("⊞ Grid"))
        self.refresh_materials_list()

    def refresh_materials_list(self):
        self.materials_list.clear()
        self._update_status_labels()

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
        self._status(f"Added {len(material_indices)} frame(s) to '{group.name}' ({len(group.entries)} entries total)")
    
    def add_materials_as_standalone_group(self):
        """Create a new CompositionGroup from selected materials as a top-level group (not nested)."""
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
        self.group_manager.add_group(comp_group)
        self.refresh_timeline()
        self.update_preview()
        self._status(f"Created standalone group '{comp_group.name}'")

    def add_materials_as_single_group(self):
        """Create a new CompositionGroup from selected materials and nest it into the current group."""
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
        self._status(f"Created group '{comp_group.name}' and nested into current group")
    
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
        self._status(f"Created {len(material_indices)} group(s) and added to timeline")
    
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
        
        self.width_spinbox.setValue(max_width)
        self.height_spinbox.setValue(max_height)
        self.update_preview()
        self._status(f"Output size set to {max_width} × {max_height}")
    
    def align_all_left(self):
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'x', 0))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Aligned {count} frame(s) to left")

    def align_all_center_horizontal(self):
        out_w = self.width_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'x', (out_w - sz[0]) // 2))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Centered {count} frame(s) horizontally")

    def align_all_right(self):
        out_w = self.width_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'x', out_w - sz[0]))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Aligned {count} frame(s) to right")

    def align_all_top(self):
        count = self._align_current_group_entries(lambda e, _: setattr(e, 'y', 0))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Aligned {count} frame(s) to top")

    def align_all_middle_vertical(self):
        out_h = self.height_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'y', (out_h - sz[1]) // 2))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Centered {count} frame(s) vertically")

    def align_all_bottom(self):
        out_h = self.height_spinbox.value()
        count = self._align_current_group_entries(lambda e, sz: setattr(e, 'y', out_h - sz[1]))
        if count == 0:
            self._status("No materials in group to align")
            return
        self.refresh_timeline(); self.update_preview()
        self._status(f"Aligned {count} frame(s) to bottom")
    
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
        """Kept for backwards compatibility; preview always shows full animation."""
        self.update_preview()

    def update_single_frame_preview(self):
        self.update_preview()

    def update_preview(self):
        """Update preview from the currently selected group (always full animation)."""
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
            self.preview.set_frames(frames)
        except Exception as e:
            print(f"ERROR in update_preview: {e}")
            import traceback
            traceback.print_exc()
    
    def quick_save_template(self):
        """Save current group composition to in-memory template list (prompts for name)."""
        if len(self.group_manager.groups) == 0:
            QMessageBox.warning(self, "Warning", "No groups to save as template!")
            return
        suggested = f"Template {len(self.templates) + 1}"
        name, ok = QInputDialog.getText(self, "Save Template", "Template name:", text=suggested)
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.templates:
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Template '{name}' already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            color_count = int(self.color_palette_combo.currentText())
            template = TemplateManager.export_composition_template(
                self.group_manager,
                self.transparent_bg_checkbox.isChecked(),
                color_count,
            )
            self.templates[name] = template
            self.refresh_template_list()
            info = TemplateManager.get_template_info(template)
            self._status(
                f"Saved '{name}' — {info['group_count']} group(s), "
                f"{info['materials_needed']} material(s) needed"
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
            ts = datetime.now().strftime("%H:%M:%S")
            if hasattr(self, '_status_autosave_label'):
                self._status_autosave_label.setText(f"Auto-saved {ts}")
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
            self._status("Auto-save enabled")
        else:
            self.auto_save_timer.stop()
            self._status("Auto-save disabled")
        self._update_status_labels()
    
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
        self.chroma_key_combo.addItem(tr("None (Disabled)"))
        
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
                self.gif_builder.clear_chroma_key()
            else:
                color_index = index - 1
                display_colors = self.chroma_key_colors_all[:self.chroma_key_display_count]
                if 0 <= color_index < len(display_colors):
                    color_rgb, _, _ = display_colors[color_index]
                    r, g, b = color_rgb
                    self.gif_builder.set_chroma_key(r, g, b, threshold=30)
            self.update_preview()
        except Exception as e:
            print(f"Error applying chroma key: {e}")
            import traceback
            traceback.print_exc()

    # ──────────────────────────────────────────────────────────────
    # Status bar helpers
    # ──────────────────────────────────────────────────────────────

    def _status(self, msg: str, timeout_ms: int = 5000):
        """Show a temporary message in the status bar."""
        if hasattr(self, '_status_bar'):
            self._status_bar.showMessage(msg, timeout_ms)

    def _update_status_labels(self):
        """Refresh the permanent status bar labels."""
        if not hasattr(self, '_status_material_label'):
            return
        self._status_material_label.setText(f"Materials: {len(self.material_manager)}")
        # Current group name
        grp = None
        if self.current_group_id is not None:
            grp = self.group_manager.get_group(self.current_group_id)
        self._status_group_label.setText(f"Group: {grp.name if grp else '—'}")
        # Auto-save state (only update text label if not showing "saved HH:MM:SS")
        autosave_txt = self._status_autosave_label.text()
        if autosave_txt in ("Auto-save: ON", "Auto-save: OFF"):
            self._status_autosave_label.setText(
                "Auto-save: ON" if self.auto_save_enabled else "Auto-save: OFF"
            )

    # ──────────────────────────────────────────────────────────────
    # Undo / Redo  (Snapshot + Debounce)
    # ──────────────────────────────────────────────────────────────

    def _make_snapshot(self) -> dict:
        """Serialize current GroupManager state into a snapshot dict."""
        return {
            "snapshot": TemplateManager.export_composition_template(self.group_manager),
            "current_group_id": self.current_group_id,
        }

    def _capture_initial_snapshot(self):
        """Store the very first snapshot so Undo can return to initial state."""
        self._undo_stack = [self._make_snapshot()]
        self._redo_stack = []

    def _push_undo_snapshot(self):
        """Called by debounce timer: push current state onto undo stack."""
        if self._undo_in_progress:
            return
        snap = self._make_snapshot()
        self._undo_stack.append(snap)
        # Keep stack bounded
        if len(self._undo_stack) > self._MAX_UNDO + 1:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _restore_snapshot(self, snap: dict):
        """Restore GroupManager and UI from a snapshot dict."""
        self._undo_in_progress = True
        try:
            new_gm, _ = TemplateManager.import_composition_template(snap["snapshot"])
            self.group_manager = new_gm
            if hasattr(self, "group_composition_widget"):
                self.group_composition_widget.set_group_manager(self.group_manager)
            gid = snap.get("current_group_id")
            if gid is not None and self.group_manager.get_group(gid) is not None:
                self.current_group_id = gid
            else:
                self.current_group_id = self.group_manager.get_root_group_id()
            self.update_preview()
            self._update_status_labels()
        finally:
            self._undo_in_progress = False

    def undo(self):
        """Restore the previous composition state (Ctrl+Z)."""
        # Need at least 2 entries: [initial, current] to undo one step
        if len(self._undo_stack) < 2:
            self._status("Nothing to undo")
            return
        # Push current state to redo before restoring
        self._redo_stack.append(self._undo_stack.pop())
        self._restore_snapshot(self._undo_stack[-1])
        self._status(f"Undo  ({len(self._undo_stack) - 1} step(s) remain)")

    def redo(self):
        """Re-apply the next composition state (Ctrl+Y / Ctrl+Shift+Z)."""
        if not self._redo_stack:
            self._status("Nothing to redo")
            return
        snap = self._redo_stack.pop()
        self._undo_stack.append(snap)
        self._restore_snapshot(snap)
        self._status(f"Redo  ({len(self._redo_stack)} step(s) available)")

    # ──────────────────────────────────────────────────────────────
    # Keyboard Shortcuts
    # ──────────────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        """Register global keyboard shortcuts."""
        # Del / Backspace — delete selected materials
        del_action = QAction(self)
        del_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        del_action.triggered.connect(self._shortcut_delete)
        self.addAction(del_action)

        backspace_action = QAction(self)
        backspace_action.setShortcut(QKeySequence(Qt.Key.Key_Backspace))
        backspace_action.triggered.connect(self._shortcut_delete)
        self.addAction(backspace_action)

        # Ctrl+E — Export GIF
        export_action = QAction(self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.export_gif)
        self.addAction(export_action)

        # Ctrl+O — Load Image
        load_action = QAction(self)
        load_action.setShortcut(QKeySequence("Ctrl+O"))
        load_action.triggered.connect(self.load_image_material)
        self.addAction(load_action)

        # F5 — Refresh preview
        preview_action = QAction(self)
        preview_action.setShortcut(QKeySequence(Qt.Key.Key_F5))
        preview_action.triggered.connect(self.update_preview)
        self.addAction(preview_action)

        # Ctrl+Shift+Z — alternate Redo (macOS / Linux convention)
        redo_alt = QAction(self)
        redo_alt.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        redo_alt.triggered.connect(self.redo)
        self.addAction(redo_alt)

    def _shortcut_delete(self):
        """Delete selected materials if the materials list has focus or items selected."""
        if self.materials_list.hasFocus() and self.materials_list.selectedItems():
            self.remove_selected_material()

    # ──────────────────────────────────────────────────────────────
    # Recent Files
    # ──────────────────────────────────────────────────────────────

    def _add_to_recent_files(self, path: str):
        path = str(Path(path).resolve())
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:8]
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        if not hasattr(self, '_recent_menu'):
            return
        self._recent_menu.clear()
        if not self.recent_files:
            self._recent_menu.addAction("(empty)").setEnabled(False)
            return
        for fpath in self.recent_files:
            label = Path(fpath).name
            action = self._recent_menu.addAction(label)
            action.setToolTip(fpath)
            action.triggered.connect(lambda checked, p=fpath: self._open_recent_file(p))
        self._recent_menu.addSeparator()
        self._recent_menu.addAction("Clear Recent Files", lambda: self._clear_recent_files())

    def _clear_recent_files(self):
        self.recent_files.clear()
        self._rebuild_recent_menu()

    def _open_recent_file(self, path: str):
        if not Path(path).exists():
            QMessageBox.warning(self, "File Not Found", f"File no longer exists:\n{path}")
            self.recent_files.remove(path)
            self._rebuild_recent_menu()
            return
        ext = Path(path).suffix.lower()
        try:
            if ext == ".gif":
                self.material_manager.load_from_gif(path)
            else:
                self.material_manager.load_from_image(path)
            self.refresh_materials_list()
            self._add_to_recent_files(path)
            self._status(f"Loaded: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open:\n{str(e)}")

    # ──────────────────────────────────────────────────────────────
    # Batch Export All Groups
    # ──────────────────────────────────────────────────────────────

    def batch_export_all_groups(self):
        """Export each top-level group as a separate GIF file."""
        groups = self.group_manager.get_all_groups()
        if not groups:
            QMessageBox.warning(self, "Warning", "No groups to export!")
            return
        export_dir = QFileDialog.getExistingDirectory(
            self, "Select Export Directory", self.last_export_dir
        )
        if not export_dir:
            return
        self.last_export_dir = export_dir

        width = self.width_spinbox.value()
        height = self.height_spinbox.value()
        loop = self.loop_spinbox.value()
        color_count = int(self.color_palette_combo.currentText())
        transparent = self.transparent_bg_checkbox.isChecked()

        self.gif_builder.set_output_size(width, height)
        self.gif_builder.set_loop(loop)
        self.gif_builder.set_color_count(color_count)
        if transparent:
            self.gif_builder.set_background_color(0, 0, 0, 0)
        else:
            self.gif_builder.set_background_color(255, 255, 255, 255)

        success, failed = 0, 0
        used_names: set = set()
        for i, group in enumerate(groups):
            try:
                group_id = i  # GroupManager uses integer index as ID
                safe_name = "".join(c for c in group.name if c.isalnum() or c in (' ', '-', '_')).strip() or f"group_{i}"
                base = safe_name
                n = 1
                while safe_name + ".gif" in used_names:
                    safe_name = f"{base}_{n}"; n += 1
                used_names.add(safe_name + ".gif")
                out_path = str(Path(export_dir) / (safe_name + ".gif"))
                self.gif_builder.build_gif_from_group(
                    group_id, self.group_manager, self.material_manager, out_path
                )
                success += 1
            except Exception as e:
                failed += 1
                print(f"Batch export error for group {i}: {e}")

        msg = f"Exported {success}/{len(groups)} group(s) to:\n{export_dir}"
        if failed:
            msg += f"\n({failed} failed — see console for details)"
        QMessageBox.information(self, "Batch Export Complete", msg)
        self._status(f"Batch exported {success} group(s)")

    # ──────────────────────────────────────────────────────────────
    # Spritesheet Export
    # ──────────────────────────────────────────────────────────────

    def export_spritesheet(self):
        """Export all frames of the current group as a single PNG spritesheet."""
        if self.current_group_id is None:
            QMessageBox.warning(self, "Warning", "No group selected!")
            return
        try:
            self.gif_builder.set_output_size(
                self.width_spinbox.value(), self.height_spinbox.value()
            )
            if self.transparent_bg_checkbox.isChecked():
                self.gif_builder.set_background_color(0, 0, 0, 0)
            else:
                self.gif_builder.set_background_color(255, 255, 255, 255)
            frames = self.gif_builder.get_preview_frames_for_group(
                self.current_group_id, self.group_manager, self.material_manager
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to render frames:\n{str(e)}")
            return

        if not frames:
            QMessageBox.warning(self, "Warning", "No frames in current group!")
            return

        # Ask how many columns
        n_cols, ok = QInputDialog.getInt(
            self, "Spritesheet Columns",
            f"Frames: {len(frames)}\nColumns per row:",
            value=min(len(frames), 8), min=1, max=len(frames)
        )
        if not ok:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Spritesheet", self.last_export_dir, "PNG Files (*.png)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"
        self.last_export_dir = str(Path(file_path).parent)

        try:
            frame_w = self.width_spinbox.value()
            frame_h = self.height_spinbox.value()
            n_rows = (len(frames) + n_cols - 1) // n_cols
            sheet = Image.new("RGBA", (frame_w * n_cols, frame_h * n_rows), (0, 0, 0, 0))
            for idx, (img, _) in enumerate(frames):
                col = idx % n_cols
                row = idx // n_cols
                frame_img = img.convert("RGBA").resize((frame_w, frame_h), Image.Resampling.LANCZOS)
                sheet.paste(frame_img, (col * frame_w, row * frame_h))
            sheet.save(file_path, "PNG")
            self._status(f"Spritesheet saved ({len(frames)} frames, {n_cols}×{n_rows})")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save spritesheet:\n{str(e)}")


def main():
    AppSettings.load()
    set_language(AppSettings.get("language", "en"))

    app = QApplication(sys.argv)
    AppTheme.apply(app)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

