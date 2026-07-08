import sys
from pathlib import Path
from typing import Optional, List
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                              QTabWidget, QStackedWidget, QStatusBar, QLabel, QSplitter)
from PyQt6.QtCore import Qt, QTimer

from .core import MaterialManager, GifBuilder, GroupManager, CompositionGroup
from .widgets import (AppTheme, PreviewPageWidget, TileSplitterPage, BatchProcessorWidget,
                      GifOptimizerWidget, VideoToGifWidget, ClipToGifWidget)
from .i18n import tr, set_language
from . import settings as AppSettings
from .main_window import (MaterialsPanelMixin, ComposerPanelMixin, TemplateMixin,
                          MenuMixin, ExportMixin, UndoMixin, StatusMixin)


class MainWindow(QMainWindow, MaterialsPanelMixin, ComposerPanelMixin, TemplateMixin,
                 MenuMixin, ExportMixin, UndoMixin, StatusMixin):
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
        # Template preview thumbnails: {name: QIcon}, kept in memory only (not persisted)
        self.template_thumbnails = {}

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
