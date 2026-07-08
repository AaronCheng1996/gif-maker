from pathlib import Path

from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from ..i18n import tr
from ..widgets import SettingsDialog


class MenuMixin:
    """Menu bar, keyboard shortcuts, recent files, and the About dialog."""

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
