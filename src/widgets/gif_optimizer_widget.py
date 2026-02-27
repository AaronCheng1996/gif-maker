from __future__ import annotations

import tempfile
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QFileDialog, QGroupBox, QSpinBox, QCheckBox, QMessageBox, QLineEdit,
    QScrollArea, QSplitter
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal

from pathlib import Path
from typing import List, Optional

from ..core.gif_optimizer import optimize_gif_lossy, GifOptimizationError, is_gifsicle_available
from .theme import AppTheme as _T


class _OptimizePreviewWorker(QThread):
    """Background thread: optimize one GIF to a temp file for preview."""
    done = pyqtSignal(str)   # temp file path on success
    error = pyqtSignal(str)

    def __init__(self, src: str, lossy: int, colors: Optional[int], parent=None):
        super().__init__(parent)
        self.src = src
        self.lossy = lossy
        self.colors = colors
        self._tmp_path: Optional[str] = None

    def run(self):
        try:
            f = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
            f.close()
            self._tmp_path = f.name
            result = optimize_gif_lossy(
                input_path=self.src,
                output_path=self._tmp_path,
                lossy=self.lossy,
                colors=self.colors,
                overwrite=True,
            )
            self.done.emit(result)
        except Exception as e:
            if self._tmp_path and os.path.exists(self._tmp_path):
                os.unlink(self._tmp_path)
            self.error.emit(str(e))


class GifOptimizerWidget(QWidget):
    """UI for optimizing GIF size with lossy compression (single or batch).

    Layout: controls (320 px) | Before preview | After preview

    - Selecting a GIF or changing settings triggers a real-time After preview
      (optimized in background, debounced 500 ms).
    - Before and After play in sync: Before's timer drives After's frame index.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_files: List[str] = []
        self._preview_worker: Optional[_OptimizePreviewWorker] = None
        self._preview_tmp: Optional[str] = None  # current temp preview file
        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._refresh_after_preview)
        self.init_ui()

    def init_ui(self):
        # ── Column 1: controls (320 px — same as Material Library) ───────────
        controls = QWidget()
        layout = QVBoxLayout(controls)
        layout.setSpacing(8)

        title = QLabel("GIF Optimizer (Lossy)")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
        layout.addWidget(title)

        desc = QLabel(
            "Reduce GIF size using lossy compression.\n"
            "Set a lossy value (0-200). Higher = smaller file, lower quality."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(desc)

        # Inputs group
        input_group = QGroupBox("1. Select GIFs")
        input_layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add GIFs")
        add_btn.clicked.connect(self.add_gifs)
        btn_row.addWidget(add_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_gifs)
        btn_row.addWidget(clear_btn)
        input_layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        input_layout.addWidget(self.list_widget)

        self.count_label = QLabel("No GIFs selected")
        self.count_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        input_layout.addWidget(self.count_label)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # Settings
        settings_group = QGroupBox("2. Settings")
        settings_layout = QVBoxLayout()

        lossy_row = QHBoxLayout()
        lossy_row.addWidget(QLabel("Lossy (0-200):"))
        self.lossy_spin = QSpinBox()
        self.lossy_spin.setRange(0, 200)
        self.lossy_spin.setValue(80)
        lossy_row.addWidget(self.lossy_spin)
        lossy_row.addStretch()
        settings_layout.addLayout(lossy_row)

        colors_row = QHBoxLayout()
        self.limit_colors_checkbox = QCheckBox("Limit palette")
        self.limit_colors_checkbox.setChecked(False)
        colors_row.addWidget(self.limit_colors_checkbox)
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(2, 256)
        self.colors_spin.setSingleStep(2)
        self.colors_spin.setValue(256)
        colors_row.addWidget(self.colors_spin)
        colors_row.addStretch()
        settings_layout.addLayout(colors_row)

        overwrite_row = QHBoxLayout()
        self.overwrite_checkbox = QCheckBox("Overwrite originals")
        overwrite_row.addWidget(self.overwrite_checkbox)
        settings_layout.addLayout(overwrite_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Dir:"))
        self.output_dir_edit = QLineEdit()
        out_row.addWidget(self.output_dir_edit, 1)
        browse_out_btn = QPushButton("Browse")
        browse_out_btn.setMaximumWidth(70)
        browse_out_btn.clicked.connect(self.browse_output_dir)
        out_row.addWidget(browse_out_btn)
        settings_layout.addLayout(out_row)

        hint = QLabel(
            "gifsicle " + ("found on PATH" if is_gifsicle_available() else "not found — using Pillow fallback")
        )
        hint.setStyleSheet(f"color: {_T.TEXT_HINT}; font-size: 10px;")
        settings_layout.addWidget(hint)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Actions
        actions_row = QHBoxLayout()
        run_single_btn = QPushButton("Optimize Selected")
        run_single_btn.clicked.connect(self.optimize_single)
        actions_row.addWidget(run_single_btn)

        run_batch_btn = QPushButton("Optimize All")
        run_batch_btn.clicked.connect(self.optimize_batch)
        actions_row.addWidget(run_batch_btn)
        layout.addLayout(actions_row)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        layout.addWidget(self.status_label)

        layout.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidget(controls)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(240)

        # ── Column 2: Before preview ──────────────────────────────────────────
        from .preview_widget import PreviewWidget

        before_col = QWidget()
        before_layout = QVBoxLayout(before_col)
        before_layout.setContentsMargins(4, 4, 4, 4)
        before_lbl = QLabel("Before")
        before_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        before_layout.addWidget(before_lbl)
        self._before_size_label = QLabel("")
        self._before_size_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        before_layout.addWidget(self._before_size_label)
        self.before_preview = PreviewWidget()
        before_layout.addWidget(self.before_preview)

        # ── Column 3: After preview ───────────────────────────────────────────
        after_col = QWidget()
        after_layout = QVBoxLayout(after_col)
        after_layout.setContentsMargins(4, 4, 4, 4)
        after_lbl = QLabel("After")
        after_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        after_layout.addWidget(after_lbl)
        self._after_size_label = QLabel("")
        self._after_size_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        after_layout.addWidget(self._after_size_label)
        self.after_preview = PreviewWidget()
        after_layout.addWidget(self.after_preview)

        # ── 3-column splitter ─────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(before_col)
        splitter.addWidget(after_col)
        splitter.setSizes([320, 640, 640])

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self.setLayout(outer)

        # Wire list selection → Before preview + trigger After refresh
        self.list_widget.currentRowChanged.connect(self._on_list_row_changed)

        # Real-time After preview: any settings change schedules a refresh
        self.lossy_spin.valueChanged.connect(self._schedule_after_refresh)
        self.colors_spin.valueChanged.connect(self._schedule_after_refresh)
        self.limit_colors_checkbox.toggled.connect(self._schedule_after_refresh)

        # Sync playback: Before's next_frame also advances After
        self.before_preview.timer.timeout.connect(self._sync_after_frame)

    # ── Sync & real-time preview helpers ─────────────────────────────────────

    def _sync_after_frame(self):
        """Called each time Before's timer fires — keep After at the same frame."""
        self.after_preview.go_to_frame(self.before_preview.current_frame_index)

    def _schedule_after_refresh(self):
        """Debounce: rebuild After preview 500 ms after the last settings change."""
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.input_files):
            self._debounce.start(500)

    def _refresh_after_preview(self):
        """Kick off a background optimization to a temp file for live preview."""
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.input_files)):
            return
        src = self.input_files[row]

        # Cancel any in-progress worker
        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.quit()
            self._preview_worker.wait()

        colors = self.colors_spin.value() if self.limit_colors_checkbox.isChecked() else None
        worker = _OptimizePreviewWorker(src, self.lossy_spin.value(), colors, parent=self)
        worker.done.connect(self._on_preview_ready)
        worker.error.connect(lambda msg: self._after_size_label.setText(f"Preview failed: {msg}"))
        self._preview_worker = worker
        self._after_size_label.setText("Generating preview…")
        worker.start()

    def _on_preview_ready(self, path: str):
        """Worker finished — load the optimized temp GIF into After preview."""
        # Clean up previous temp file
        if self._preview_tmp and self._preview_tmp != path:
            try:
                os.unlink(self._preview_tmp)
            except OSError:
                pass
        self._preview_tmp = path

        # Stop After's own timer (Before drives the frame index)
        self.after_preview.pause()
        self._load_gif_into_preview(path, self.after_preview, self._after_size_label)
        # After is loaded; stop its auto-play and let _sync_after_frame drive it
        self.after_preview.pause()

    # ── Load helper ───────────────────────────────────────────────────────────

    def _load_gif_into_preview(self, path: str, preview_widget, size_label: QLabel):
        """Load a GIF file and display its frames in a PreviewWidget."""
        try:
            from PIL import Image
            frames = []
            with Image.open(path) as img:
                file_size = Path(path).stat().st_size
                size_label.setText(
                    f"{Path(path).name}  —  {file_size / 1024:.1f} KB  "
                    f"({img.width}×{img.height})"
                )
                try:
                    while True:
                        duration = img.info.get("duration", 100)
                        frames.append((img.copy().convert("RGBA"), duration))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass
            if frames:
                preview_widget.set_frames(frames)
                preview_widget.play()
        except Exception as e:
            size_label.setText(f"Cannot load: {e}")

    def _on_list_row_changed(self, row: int):
        if 0 <= row < len(self.input_files):
            self._load_gif_into_preview(
                self.input_files[row], self.before_preview, self._before_size_label
            )
            self.after_preview.set_frames([])
            self._after_size_label.setText("Generating preview…")
            # Immediately schedule After preview (short delay so Before renders first)
            self._debounce.start(200)

    def add_gifs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select GIF files", "", "GIF Files (*.gif)")
        if files:
            for f in files:
                if f not in self.input_files:
                    self.input_files.append(f)
                    self.list_widget.addItem(Path(f).name)
            self.update_count()

    def clear_gifs(self):
        self.input_files = []
        self.list_widget.clear()
        self.update_count()
        self.before_preview.set_frames([])
        self.after_preview.set_frames([])
        self._before_size_label.setText("")
        self._after_size_label.setText("")

    def browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir_edit.setText(directory)

    def update_count(self):
        n = len(self.input_files)
        self.count_label.setText(f"{n} file(s) selected" if n else "No GIFs selected")

    def _compute_output_path(self, src: str) -> str:
        out_dir = self.output_dir_edit.text().strip()
        overwrite = self.overwrite_checkbox.isChecked()
        if overwrite:
            return src
        if out_dir:
            p = Path(src)
            return str(Path(out_dir) / (p.stem + "-optimized.gif"))
        return ""  # signal to optimizer to choose default alongside

    def _get_colors(self) -> int | None:
        return self.colors_spin.value() if self.limit_colors_checkbox.isChecked() else None

    def optimize_single(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "No GIF selected")
            return
        self.optimize_paths([self.input_files[0]])

    def optimize_batch(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "No GIFs to process")
            return
        self.optimize_paths(self.input_files)

    def optimize_paths(self, paths: List[str]):
        lossy = self.lossy_spin.value()
        colors = self._get_colors()
        overwrite = self.overwrite_checkbox.isChecked()
        success = 0
        failed: List[str] = []
        last_result: Optional[str] = None
        for src in paths:
            out_path = self._compute_output_path(src)
            if out_path == "":
                out_path = None
            try:
                result = optimize_gif_lossy(
                    input_path=src,
                    output_path=out_path,
                    lossy=lossy,
                    colors=colors,
                    overwrite=overwrite,
                )
                success += 1
                last_result = result
                self.status_label.setText(f"Optimized: {Path(result).name}")
            except GifOptimizationError as e:
                failed.append(f"{Path(src).name}: {str(e)}")

        # Update After preview with the last successfully saved file
        if last_result:
            self.after_preview.pause()
            self._load_gif_into_preview(last_result, self.after_preview, self._after_size_label)
            self.after_preview.pause()  # sync mode: Before drives frame index

        if failed:
            QMessageBox.warning(self, "Completed with errors", "\n".join(failed))
        else:
            QMessageBox.information(self, "Success", f"Optimized {success} file(s)")


