"""Image Merge — simple standalone tool: stack multiple images and export as one PNG.

Loads images into its own MaterialManager (independent of the Composer's material
library), positions them on a CanvasEditorWidget (reusing its zoom/pan/drag-to-move/
snap/multi-select), and flattens them bottom-to-top into a single PNG on export.
"""
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QListWidget, QListWidgetItem, QGroupBox, QSpinBox,
                              QCheckBox, QFileDialog, QMessageBox)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap, QImage

from PIL import Image

from ..i18n import tr
from ..core.image_loader import MaterialManager
from ..core.composition_group import FrameEntry
from ..core.gif_builder import GifBuilder
from .theme import AppTheme as _T
from . import ui
from .canvas_editor import CanvasEditorWidget

_NEW_IMAGE_STAGGER = 20  # px offset applied to each successively loaded image


def _pil_to_pixmap(img: Image.Image, w: int, h: int) -> Optional[QPixmap]:
    try:
        thumb = img.copy()
        thumb.thumbnail((w, h), Image.Resampling.LANCZOS)
        if thumb.mode != "RGBA":
            thumb = thumb.convert("RGBA")
        data = thumb.tobytes("raw", "RGBA")
        qimg = QImage(data, thumb.width, thumb.height, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


class ImageMergeWidget(QWidget):
    """Load several images, drag them into place on the canvas, export as one PNG."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.material_manager = MaterialManager()
        self.entries: List[FrameEntry] = []
        self.last_load_dir = ""
        self.last_export_dir = ""
        self._init_ui()

    def _init_ui(self):
        layout = ui.tab_layout(self)

        layout.addWidget(self._create_left_panel())
        self.canvas = CanvasEditorWidget()
        layout.addWidget(self.canvas, stretch=1)
        layout.addWidget(self._create_right_panel())

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(260)
        vlayout = ui.panel_layout(panel)

        title = QLabel(tr("Images"))
        title.setStyleSheet(ui.TITLE_QSS)
        vlayout.addWidget(title)

        self.load_btn = QPushButton(tr("Load Images"))
        self.load_btn.clicked.connect(self.load_images)
        vlayout.addWidget(self.load_btn)

        self.images_list = QListWidget()
        self.images_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.images_list.setIconSize(QSize(48, 48))
        self.images_list.currentRowChanged.connect(self._on_list_row_changed)
        vlayout.addWidget(self.images_list, stretch=1)

        btn_row = QHBoxLayout()
        self.remove_btn = QPushButton(tr("Remove Selected"))
        self.remove_btn.clicked.connect(self.remove_selected_images)
        btn_row.addWidget(self.remove_btn)

        self.clear_btn = QPushButton(tr("Clear All"))
        self.clear_btn.clicked.connect(self.clear_all_images)
        btn_row.addWidget(self.clear_btn)
        vlayout.addLayout(btn_row)

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(220)
        vlayout = ui.panel_layout(panel)

        settings_group = QGroupBox(tr("Output"))
        settings_layout = QVBoxLayout()

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(tr("Size:")))
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(1, 8192)
        self.width_spinbox.setValue(400)
        self.width_spinbox.valueChanged.connect(self._on_output_size_changed)
        size_row.addWidget(self.width_spinbox)
        size_row.addWidget(QLabel("×"))
        self.height_spinbox = QSpinBox()
        self.height_spinbox.setRange(1, 8192)
        self.height_spinbox.setValue(400)
        self.height_spinbox.valueChanged.connect(self._on_output_size_changed)
        size_row.addWidget(self.height_spinbox)
        settings_layout.addLayout(size_row)

        self.auto_fit_btn = QPushButton(tr("🔧 Auto Fit Size"))
        self.auto_fit_btn.setToolTip("Fit the output size to the bounding box of all placed images")
        self.auto_fit_btn.clicked.connect(self.auto_fit_output_size)
        settings_layout.addWidget(self.auto_fit_btn)

        self.transparent_bg_checkbox = QCheckBox(tr("Transparent BG"))
        self.transparent_bg_checkbox.setChecked(True)
        settings_layout.addWidget(self.transparent_bg_checkbox)

        settings_group.setLayout(settings_layout)
        vlayout.addWidget(settings_group)
        vlayout.addStretch()

        self.export_btn = QPushButton(tr("💾 Export PNG"))
        self.export_btn.setStyleSheet(ui.GO_QSS)
        self.export_btn.clicked.connect(self.export_png)
        vlayout.addWidget(self.export_btn)

        return panel

    # ── Loading / removing images ────────────────────────────────────────
    def load_images(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Select Images"), self.last_load_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_paths:
            return
        self.last_load_dir = str(Path(file_paths[0]).parent)
        for file_path in file_paths:
            try:
                self.material_manager.load_from_image(file_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load {file_path}:\n{str(e)}")
                continue
            offset = len(self.entries) * _NEW_IMAGE_STAGGER
            self.entries.append(FrameEntry(material_index=len(self.material_manager) - 1, x=offset, y=offset))
        self._refresh_images_list()
        self._refresh_canvas()

    def remove_selected_images(self):
        rows = sorted((self.images_list.row(i) for i in self.images_list.selectedItems()), reverse=True)
        if not rows:
            QMessageBox.warning(self, "Warning", "Please select at least one image to remove!")
            return
        for row in rows:
            if not (0 <= row < len(self.entries)):
                continue
            del self.entries[row]
            self.material_manager.remove_material(row)
            for entry in self.entries:
                if entry.material_index > row:
                    entry.material_index -= 1
        self._refresh_images_list()
        self._refresh_canvas()

    def clear_all_images(self):
        self.entries = []
        self.material_manager.clear()
        self._refresh_images_list()
        self._refresh_canvas()

    def _refresh_images_list(self):
        self.images_list.clear()
        for i, entry in enumerate(self.entries):
            mat = self.material_manager.get_material(entry.material_index)
            name = mat[1] if mat else f"#{entry.material_index}"
            item = QListWidgetItem(name)
            if mat:
                pixmap = _pil_to_pixmap(mat[0], 48, 48)
                if pixmap is not None:
                    item.setIcon(QIcon(pixmap))
            self.images_list.addItem(item)

    def _on_list_row_changed(self, row: int):
        entry_index = row if 0 <= row < len(self.entries) else None
        self.canvas.select_entry(entry_index)

    # ── Canvas sync ──────────────────────────────────────────────────────
    def _refresh_canvas(self):
        self.canvas.set_output_size(self.width_spinbox.value(), self.height_spinbox.value())
        self.canvas.set_entries(self.entries, self.material_manager)

    def _on_output_size_changed(self):
        self.canvas.set_output_size(self.width_spinbox.value(), self.height_spinbox.value())

    def auto_fit_output_size(self):
        if not self.entries:
            QMessageBox.warning(self, "Warning", "No images loaded to fit to!")
            return
        max_w = max_h = 0
        for entry in self.entries:
            mat = self.material_manager.get_material(entry.material_index)
            if mat:
                img, _ = mat
                max_w = max(max_w, entry.x + img.width)
                max_h = max(max_h, entry.y + img.height)
        self.width_spinbox.setValue(max(1, max_w))
        self.height_spinbox.setValue(max(1, max_h))

    # ── Export ───────────────────────────────────────────────────────────
    def export_png(self):
        if not self.entries:
            QMessageBox.warning(self, "Warning", "No images loaded to export!")
            return

        default_path = "merged.png"
        if self.last_export_dir:
            default_path = str(Path(self.last_export_dir) / "merged.png")

        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Save PNG"), default_path, "PNG Files (*.png)"
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".png"):
            file_path += ".png"

        try:
            self.last_export_dir = str(Path(file_path).parent)
            gif_builder = GifBuilder()
            gif_builder.set_output_size(self.width_spinbox.value(), self.height_spinbox.value())
            if self.transparent_bg_checkbox.isChecked():
                gif_builder.set_background_color(0, 0, 0, 0)
            else:
                gif_builder.set_background_color(255, 255, 255, 255)
            composed = gif_builder.compose_flat_image(self.entries, self.material_manager)
            composed.save(file_path, "PNG")
            QMessageBox.information(self, "Success", f"Exported to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export PNG:\n{str(e)}")
