from __future__ import annotations

import os
import tempfile

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout, QWidget,
)
from pathlib import Path
from typing import List, Optional

from ..core.video_to_gif import (
    VideoConversionError,
    convert_to_gif,
    extract_preview_frames,
    get_video_info,
    is_ffmpeg_available,
    find_ffmpeg,
)
from .theme import AppTheme as _T


def _fmt_size(byte_count: int) -> str:
    """Format byte count as KB or MB (auto-upgrade at 1 000 KB, 2 decimal places)."""
    kb = byte_count / 1024
    if kb >= 1000:
        return f"{kb / 1024:.2f} MB"
    return f"{kb:.2f} KB"

# ── Supported input formats ────────────────────────────────────────────────────
_VIDEO_FILTER = (
    "Video & Animated Files ("
    "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v *.ts *.3gp *.mts "
    "*.webp *.gif *.apng"
    ")"
)


# ── Background workers ─────────────────────────────────────────────────────────

class _SourcePreviewWorker(QThread):
    """Extract animated preview frames from a video for the source column."""
    done = pyqtSignal(list)   # list[tuple[PIL.Image, int]]
    error = pyqtSignal(str)

    def __init__(
        self,
        path: str,
        fps: float,
        start_time: float,
        end_time: float,
        parent=None,
    ):
        super().__init__(parent)
        self.path = path
        self.fps = fps
        self.start_time = start_time
        self.end_time = end_time

    def run(self):
        try:
            frames = extract_preview_frames(
                self.path,
                fps=self.fps,
                max_width=480,
                max_duration=10.0,
                start_time=self.start_time,
                end_time=self.end_time,
            )
            self.done.emit(frames)
        except Exception as e:
            self.error.emit(str(e))


class _ConvertPreviewWorker(QThread):
    """Background thread: convert one file to a temp GIF for live preview."""
    done = pyqtSignal(str)   # temp file path on success
    error = pyqtSignal(str)

    def __init__(
        self,
        src: str,
        fps: float,
        width: int,
        start_time: float,
        end_time: float,
        colors: int,
        dither: str,
        lossy: int,
        parent=None,
    ):
        super().__init__(parent)
        self.src = src
        self.fps = fps
        self.width = width
        self.start_time = start_time
        self.end_time = end_time
        self.colors = colors
        self.dither = dither
        self.lossy = lossy
        self._tmp_path: Optional[str] = None

    def run(self):
        try:
            f = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
            f.close()
            self._tmp_path = f.name
            result = convert_to_gif(
                input_path=self.src,
                output_path=self._tmp_path,
                fps=self.fps,
                width=self.width,
                start_time=self.start_time,
                end_time=self.end_time,
                colors=self.colors,
                dither=self.dither,
                lossy=self.lossy,
                overwrite=True,
            )
            self.done.emit(result)
        except Exception as e:
            if self._tmp_path and os.path.exists(self._tmp_path):
                os.unlink(self._tmp_path)
            self.error.emit(str(e))


# ── Main widget ────────────────────────────────────────────────────────────────

class VideoToGifWidget(QWidget):
    """UI for converting video / animated-image files to optimised GIFs.

    Layout: controls (320 px) | Source (first-frame + metadata) | Output GIF (PreviewWidget)

    Mirrors the GifOptimizerWidget 3-column QSplitter design:
    - Selecting a file loads the source thumbnail and triggers a live GIF preview.
    - Any settings change debounces 500 ms then rebuilds the preview in background.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.input_files: List[str] = []
        self._preview_worker: Optional[_ConvertPreviewWorker] = None
        self._source_worker: Optional[_SourcePreviewWorker] = None
        self._preview_tmp: Optional[str] = None

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._refresh_preview)

        self._ffmpeg_ok = is_ffmpeg_available()
        self.init_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def init_ui(self):
        # ── Left column: controls ─────────────────────────────────────────────
        controls = QWidget()
        layout = QVBoxLayout(controls)
        layout.setSpacing(8)

        title = QLabel("Video → GIF Converter")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
        layout.addWidget(title)

        desc = QLabel(
            "Convert video & animated images to GIF.\n"
            "Supports mp4, mov, webm, webp, gif, apng, and more."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(desc)

        # ── 1. Select Files ───────────────────────────────────────────────────
        input_group = QGroupBox("1. Select Files")
        input_layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("Add Files")
        self._add_btn.clicked.connect(self.add_files)
        btn_row.addWidget(self._add_btn)

        clear_btn = QPushButton("Clear All")
        clear_btn.clicked.connect(self.clear_files)
        btn_row.addWidget(clear_btn)
        input_layout.addLayout(btn_row)

        self.list_widget = QListWidget()
        input_layout.addWidget(self.list_widget)

        self.count_label = QLabel("No files selected")
        self.count_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        input_layout.addWidget(self.count_label)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # ── 2. Conversion Settings ────────────────────────────────────────────
        settings_group = QGroupBox("2. Conversion Settings")
        settings_layout = QVBoxLayout()

        # FPS
        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Output FPS:"))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(1.0, 60.0)
        self.fps_spin.setSingleStep(1.0)
        self.fps_spin.setDecimals(1)
        self.fps_spin.setValue(10.0)
        fps_row.addWidget(self.fps_spin)
        fps_row.addStretch()
        settings_layout.addLayout(fps_row)

        # Width
        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Width px:"))
        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 3840)
        self.width_spin.setSingleStep(50)
        self.width_spin.setValue(0)
        self.width_spin.setSpecialValueText("0 = keep original")
        width_row.addWidget(self.width_spin)
        width_row.addStretch()
        settings_layout.addLayout(width_row)

        # Start / End time
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Start (s):"))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 86400.0)
        self.start_spin.setDecimals(2)
        self.start_spin.setValue(0.0)
        time_row.addWidget(self.start_spin)
        time_row.addWidget(QLabel("End (s):"))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(0.0, 86400.0)
        self.end_spin.setDecimals(2)
        self.end_spin.setValue(0.0)
        self.end_spin.setSpecialValueText("0 = full")
        time_row.addWidget(self.end_spin)
        settings_layout.addLayout(time_row)

        # Colors
        colors_row = QHBoxLayout()
        colors_row.addWidget(QLabel("Colors:"))
        self.colors_spin = QSpinBox()
        self.colors_spin.setRange(32, 256)
        self.colors_spin.setSingleStep(8)
        self.colors_spin.setValue(256)
        colors_row.addWidget(self.colors_spin)
        colors_row.addStretch()
        settings_layout.addLayout(colors_row)

        # Dither
        dither_row = QHBoxLayout()
        dither_row.addWidget(QLabel("Dither:"))
        self.dither_combo = QComboBox()
        self.dither_combo.addItems(["bayer", "floyd_steinberg", "sierra2", "none"])
        dither_row.addWidget(self.dither_combo)
        dither_row.addStretch()
        settings_layout.addLayout(dither_row)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # ── 3. Post-process Optimization ─────────────────────────────────────
        opt_group = QGroupBox("3. Post-process Optimization")
        opt_layout = QVBoxLayout()

        lossy_row = QHBoxLayout()
        self.lossy_checkbox = QCheckBox("Lossy compress via gifsicle")
        self.lossy_checkbox.setChecked(False)
        lossy_row.addWidget(self.lossy_checkbox)
        self.lossy_spin = QSpinBox()
        self.lossy_spin.setRange(0, 200)
        self.lossy_spin.setValue(80)
        self.lossy_spin.setEnabled(False)
        lossy_row.addWidget(self.lossy_spin)
        lossy_row.addStretch()
        opt_layout.addLayout(lossy_row)

        self.lossy_checkbox.toggled.connect(self.lossy_spin.setEnabled)
        self.lossy_checkbox.toggled.connect(self._schedule_preview)

        opt_group.setLayout(opt_layout)
        layout.addWidget(opt_group)

        # ── 4. Output ─────────────────────────────────────────────────────────
        out_group = QGroupBox("4. Output")
        out_layout = QVBoxLayout()

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Output Dir:"))
        self.output_dir_edit = QLineEdit()
        out_row.addWidget(self.output_dir_edit, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setMaximumWidth(70)
        browse_btn.clicked.connect(self.browse_output_dir)
        out_row.addWidget(browse_btn)
        out_layout.addLayout(out_row)

        self.overwrite_checkbox = QCheckBox("Overwrite originals")
        out_layout.addWidget(self.overwrite_checkbox)

        out_group.setLayout(out_layout)
        layout.addWidget(out_group)

        # ── Actions ───────────────────────────────────────────────────────────
        actions_row = QHBoxLayout()
        self._convert_single_btn = QPushButton("Convert Selected")
        self._convert_single_btn.clicked.connect(self.convert_single)
        actions_row.addWidget(self._convert_single_btn)

        self._convert_all_btn = QPushButton("Convert All")
        self._convert_all_btn.clicked.connect(self.convert_all)
        actions_row.addWidget(self._convert_all_btn)
        layout.addLayout(actions_row)

        self.status_label = QLabel("Ready")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {_T.TEXT_DIM};")
        layout.addWidget(self.status_label)

        # ffmpeg status hint + Refresh button
        self._ffmpeg_hint = QLabel()
        self._ffmpeg_hint.setWordWrap(True)
        self._ffmpeg_hint.setStyleSheet("font-size: 10px;")
        layout.addWidget(self._ffmpeg_hint)

        refresh_btn = QPushButton("Refresh ffmpeg detection")
        refresh_btn.setStyleSheet("font-size: 10px;")
        refresh_btn.clicked.connect(self._refresh_ffmpeg_status)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        # Set initial hint text and button states
        self._apply_ffmpeg_state()

        left_scroll = QScrollArea()
        left_scroll.setWidget(controls)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(240)

        from .preview_widget import PreviewWidget

        # ── Middle column: Source ──────────────────────────────────────────────
        source_col = QWidget()
        source_layout = QVBoxLayout(source_col)
        source_layout.setContentsMargins(4, 4, 4, 4)

        source_lbl = QLabel("Source")
        source_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        source_layout.addWidget(source_lbl)

        self._source_meta_label = QLabel("")
        self._source_meta_label.setWordWrap(True)
        self._source_meta_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        source_layout.addWidget(self._source_meta_label)

        self.source_preview = PreviewWidget()
        source_layout.addWidget(self.source_preview, 1)

        # ── Right column: Output GIF ───────────────────────────────────────────
        output_col = QWidget()
        output_layout = QVBoxLayout(output_col)
        output_layout.setContentsMargins(4, 4, 4, 4)

        output_lbl = QLabel("Output GIF")
        output_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        output_layout.addWidget(output_lbl)

        self._output_size_label = QLabel("")
        self._output_size_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        output_layout.addWidget(self._output_size_label)

        self.output_preview = PreviewWidget()
        output_layout.addWidget(self.output_preview)

        # ── 3-column splitter ──────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(source_col)
        splitter.addWidget(output_col)
        splitter.setSizes([320, 640, 640])

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self.setLayout(outer)

        # ── Wire signals ───────────────────────────────────────────────────────
        self.list_widget.currentRowChanged.connect(self._on_list_row_changed)

        for widget in (
            self.fps_spin, self.width_spin, self.start_spin, self.end_spin,
            self.colors_spin,
        ):
            widget.valueChanged.connect(self._schedule_preview)
        self.dither_combo.currentIndexChanged.connect(self._schedule_preview)
        self.lossy_spin.valueChanged.connect(self._schedule_preview)

        # Sync output playback: source timer drives output frame index
        self.source_preview.timer.timeout.connect(self._sync_output_frame)

    # ── ffmpeg detection ───────────────────────────────────────────────────────

    def _apply_ffmpeg_state(self):
        """Update hint label and button states to match current self._ffmpeg_ok."""
        if self._ffmpeg_ok:
            self._ffmpeg_hint.setText("ffmpeg found on PATH")
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.SUCCESS}; font-size: 10px;")
        else:
            self._ffmpeg_hint.setText(
                "ffmpeg not found — conversion unavailable.\n"
                "Install:  winget install Gyan.FFmpeg\n"
                "Then click Refresh (no restart needed)."
            )
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.ERROR}; font-size: 10px;")
        self._convert_single_btn.setEnabled(self._ffmpeg_ok)
        self._convert_all_btn.setEnabled(self._ffmpeg_ok)

    def _refresh_ffmpeg_status(self):
        """Re-detect ffmpeg (reads Windows registry PATH for post-install changes)."""
        self._ffmpeg_ok = find_ffmpeg() is not None
        self._apply_ffmpeg_state()
        if self._ffmpeg_ok:
            # Re-trigger metadata + preview for the currently selected file
            self._on_list_row_changed(self.list_widget.currentRow())

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _sync_output_frame(self):
        """Keep output frame in step with the source preview timer."""
        self.output_preview.go_to_frame(self.source_preview.current_frame_index)

    def _schedule_preview(self):
        """Debounce: rebuild output GIF preview 500 ms after last settings change."""
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.input_files):
            self._debounce.start(500)

    def _refresh_preview(self):
        """Kick off background conversion to a temp file for live preview."""
        if not self._ffmpeg_ok:
            self._output_size_label.setText("ffmpeg not found — install to enable preview")
            return
        row = self.list_widget.currentRow()
        if not (0 <= row < len(self.input_files)):
            return
        src = self.input_files[row]

        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.quit()
            self._preview_worker.wait()

        worker = _ConvertPreviewWorker(
            src=src,
            fps=self.fps_spin.value(),
            width=self.width_spin.value(),
            start_time=self.start_spin.value(),
            end_time=self.end_spin.value(),
            colors=self.colors_spin.value(),
            dither=self.dither_combo.currentText(),
            lossy=self.lossy_spin.value() if self.lossy_checkbox.isChecked() else 0,
            parent=self,
        )
        worker.done.connect(self._on_preview_ready)
        worker.error.connect(
            lambda msg: self._output_size_label.setText(f"Preview failed: {msg}")
        )
        self._preview_worker = worker
        self._output_size_label.setText("Generating preview…")
        worker.start()

    def _on_preview_ready(self, path: str):
        """Worker finished — load the temp GIF into the output PreviewWidget."""
        if self._preview_tmp and self._preview_tmp != path:
            try:
                os.unlink(self._preview_tmp)
            except OSError:
                pass
        self._preview_tmp = path
        self._load_gif_into_preview(path)

    def _load_gif_into_preview(self, path: str):
        """Load a GIF into the output PreviewWidget and update the size label."""
        try:
            from PIL import Image
            frames = []
            with Image.open(path) as img:
                file_size = Path(path).stat().st_size
                self._output_size_label.setText(
                    f"{Path(path).name}  —  {_fmt_size(file_size)}  "
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
                self.output_preview.set_frames(frames)
                # Let source preview drive frame index for side-by-side comparison
                self.output_preview.pause()
        except Exception as e:
            self._output_size_label.setText(f"Cannot load: {e}")

    def _on_list_row_changed(self, row: int):
        if not (0 <= row < len(self.input_files)):
            return
        src = self.input_files[row]

        # Clear both previews
        self.source_preview.set_frames([])
        self.output_preview.set_frames([])

        p = Path(src)
        try:
            file_size = p.stat().st_size
        except OSError:
            file_size = 0

        if not self._ffmpeg_ok:
            self._source_meta_label.setText(f"{p.name}  ·  {_fmt_size(file_size)}")
            self._output_size_label.setText("ffmpeg not found — install to convert")
            return

        self._output_size_label.setText("Generating preview…")

        # Metadata line
        info = get_video_info(src)
        parts = [p.name]
        if info["width"]:
            parts.append(f"{info['width']}×{info['height']}")
        if info["fps"]:
            parts.append(f"{info['fps']:.1f} fps")
        if info["duration"]:
            parts.append(f"{info['duration']:.1f} s")
        parts.append(_fmt_size(file_size))
        self._source_meta_label.setText("  ·  ".join(parts))

        # Animated source preview in background
        if self._source_worker and self._source_worker.isRunning():
            self._source_worker.quit()
            self._source_worker.wait()
        source_worker = _SourcePreviewWorker(
            path=src,
            fps=self.fps_spin.value(),
            start_time=self.start_spin.value(),
            end_time=self.end_spin.value(),
            parent=self,
        )
        source_worker.done.connect(self._on_source_frames_ready)
        source_worker.error.connect(
            lambda msg: self._source_meta_label.setText(
                self._source_meta_label.text() + f"\n[preview error: {msg}]"
            )
        )
        self._source_worker = source_worker
        source_worker.start()

        # Schedule GIF preview (short delay so source starts loading first)
        self._debounce.start(300)

    def _on_source_frames_ready(self, frames: list):
        """Source worker finished — load frames into source PreviewWidget."""
        if frames:
            self.source_preview.set_frames(frames)
            self.source_preview.play()

    # ── File management ────────────────────────────────────────────────────────

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Video / Animated Image Files", "", _VIDEO_FILTER
        )
        if files:
            for f in files:
                if f not in self.input_files:
                    self.input_files.append(f)
                    self.list_widget.addItem(Path(f).name)
            self._update_count()

    def clear_files(self):
        self.input_files = []
        self.list_widget.clear()
        self._update_count()
        self.source_preview.set_frames([])
        self.output_preview.set_frames([])
        self._output_size_label.setText("")
        self._source_meta_label.setText("")

    def browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_dir_edit.setText(directory)

    def _update_count(self):
        n = len(self.input_files)
        self.count_label.setText(f"{n} file(s) selected" if n else "No files selected")

    # ── Output path ────────────────────────────────────────────────────────────

    def _compute_output_path(self, src: str) -> Optional[str]:
        out_dir = self.output_dir_edit.text().strip()
        overwrite = self.overwrite_checkbox.isChecked()
        p = Path(src)
        stem = p.stem
        if overwrite and p.suffix.lower() == ".gif":
            return src
        if out_dir:
            return str(Path(out_dir) / (stem + ".gif"))
        return None  # let convert_to_gif derive alongside source

    # ── Conversion actions ─────────────────────────────────────────────────────

    def convert_single(self):
        row = self.list_widget.currentRow()
        if row < 0 or not self.input_files:
            QMessageBox.warning(self, "Warning", "No file selected")
            return
        self._convert_paths([self.input_files[row]])

    def convert_all(self):
        if not self.input_files:
            QMessageBox.warning(self, "Warning", "No files to convert")
            return
        self._convert_paths(self.input_files)

    def _convert_paths(self, paths: List[str]):
        overwrite = self.overwrite_checkbox.isChecked()
        lossy = self.lossy_spin.value() if self.lossy_checkbox.isChecked() else 0

        success = 0
        failed: List[str] = []
        last_result: Optional[str] = None

        for src in paths:
            out_path = self._compute_output_path(src)
            self.status_label.setText(f"Converting: {Path(src).name}…")
            # Force UI update so the label is visible during long conversions
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            try:
                result = convert_to_gif(
                    input_path=src,
                    output_path=out_path,
                    fps=self.fps_spin.value(),
                    width=self.width_spin.value(),
                    start_time=self.start_spin.value(),
                    end_time=self.end_spin.value(),
                    colors=self.colors_spin.value(),
                    dither=self.dither_combo.currentText(),
                    lossy=lossy,
                    overwrite=overwrite,
                )
                success += 1
                last_result = result
                self.status_label.setText(f"Done: {Path(result).name}")
            except VideoConversionError as e:
                failed.append(f"{Path(src).name}: {e}")

        # Update output preview with the last saved file
        if last_result:
            self._load_gif_into_preview(last_result)

        if failed:
            QMessageBox.warning(self, "Completed with errors", "\n".join(failed))
        else:
            QMessageBox.information(self, "Success", f"Converted {success} file(s)")
