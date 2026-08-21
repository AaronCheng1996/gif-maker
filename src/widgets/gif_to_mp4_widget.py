"""GIF to Video — shrink finished animations by re-encoding them as video.

A GIF holds 256 colours per frame and compresses every frame on its own, so a
long one gets very large. Re-encoding it as H.264 typically lands between three
and eight times smaller while still looking like the GIF it came from.

The one thing this tab has to make impossible to miss is that H.264 has no alpha
channel. Animations exported from Spine are commonly a third transparent, and
that transparency has to become *some* colour on the way to MP4. So the preview
shows each file composited onto the chosen background before anything is
converted, and the file list says outright which entries carry transparency.

For anything where the transparency has to survive, the VP9/WebM option keeps
it — about half the saving, but still smaller than the GIF.
"""
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QComboBox, QSpinBox,
                             QGroupBox, QFileDialog, QMessageBox, QProgressBar,
                             QSplitter, QSizePolicy, QAbstractItemView, QCheckBox,
                             QColorDialog)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QColor

from PIL import Image, ImageSequence

from ..i18n import tr
from ..core import gif_to_mp4
from ..core.video_to_gif import (VideoConversionError, get_ffmpeg_install_info,
                                 is_ffmpeg_available)
from .theme import AppTheme as _T


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimg)
    del data
    return pixmap


class SourceFile:
    """One queued animation and what was learned by opening it."""

    __slots__ = ("path", "width", "height", "frames", "fps", "transparent", "error")

    def __init__(self, path: Path):
        self.path = path
        self.width = self.height = self.frames = 0
        self.fps = 0.0
        self.transparent = False
        self.error = ""
        self._probe()

    def _probe(self):
        """Read size, frame count and whether any pixel is see-through.

        Pillow rather than ffprobe: it is quick for a GIF's first frame and it
        is also the honest way to find out whether the extension is telling the
        truth, which for ripped assets it often is not."""
        try:
            with Image.open(self.path) as im:
                self.width, self.height = im.size
                self.frames = getattr(im, "n_frames", 1)
                first = im.convert("RGBA")
                duration = im.info.get("duration") or 0
            self.fps = (1000.0 / duration) if duration else 0.0
            self.transparent = first.getchannel("A").getextrema()[0] < 255
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"

    @property
    def size_mb(self) -> float:
        try:
            return self.path.stat().st_size / 1e6
        except OSError:
            return 0.0

    def label(self) -> str:
        if self.error:
            return f"{self.path.name}\n⚠ unreadable — {self.error[:60]}"
        alpha = "  ·  has transparency" if self.transparent else ""
        return (f"{self.path.name}\n{self.width}×{self.height}  ·  {self.frames} frames"
                f"  ·  {self.size_mb:.1f} MB{alpha}")


class _ConvertWorker(QThread):
    """Converts the queue, one file at a time."""
    file_started = pyqtSignal(int, str)        # index, name
    file_progress = pyqtSignal(int)            # percent within the current file
    file_done = pyqtSignal(str, float, float)  # name, source MB, produced MB
    finished_all = pyqtSignal(int, list)       # converted, [(name, reason)]

    def __init__(self, jobs, out_dir: Optional[Path], codec: str, crf: int,
                 background: str, fps: float, width: int, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.out_dir = out_dir
        self.codec = codec
        self.crf = crf
        self.background = background
        self.fps = fps
        self.width = width
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        converted, failures = 0, []
        ext = gif_to_mp4.extension_for(self.codec)
        for i, source in enumerate(self.jobs):
            if self._cancelled:
                break
            self.file_started.emit(i, source.path.name)
            folder = self.out_dir if self.out_dir else source.path.parent
            out = Path(folder) / f"{source.path.stem}.{ext}"
            try:
                gif_to_mp4.convert_to_video(
                    source.path, out, codec=self.codec, crf=self.crf,
                    background=self.background, fps=self.fps, width=self.width,
                    on_progress=self.file_progress.emit,
                    should_stop=lambda: self._cancelled)
            except VideoConversionError as e:
                if not self._cancelled:
                    failures.append((source.path.name, str(e).splitlines()[0][:120]))
                continue
            except Exception as e:
                failures.append((source.path.name, f"{type(e).__name__}: {e}"))
                continue
            a, b, _ = gif_to_mp4.size_change(source.path, out)
            converted += 1
            self.file_done.emit(source.path.name, a / 1e6, b / 1e6)
        self.finished_all.emit(converted, failures)


class GifToMp4Widget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sources: List[SourceFile] = []
        self.out_dir: Optional[Path] = None
        self.last_dir = ""
        self._background = "white"
        self._worker: Optional[_ConvertWorker] = None
        self._ffmpeg_ok = is_ffmpeg_available()
        self._current_pixmap: Optional[QPixmap] = None
        self._init_ui()
        self._apply_ffmpeg_state()
        self._update_enabled_state()

    # ── UI ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([420, 680])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        title = QLabel(tr("Animations"))
        title.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {_T.TEXT}; padding: 4px 0;")
        v.addWidget(title)

        buttons = QHBoxLayout()
        self.add_btn = QPushButton(tr("📂 Add Files…"))
        self.add_btn.clicked.connect(self.add_files)
        buttons.addWidget(self.add_btn)
        self.remove_btn = QPushButton(tr("Remove"))
        self.remove_btn.clicked.connect(self.remove_selected)
        buttons.addWidget(self.remove_btn)
        self.clear_btn = QPushButton(tr("Clear All"))
        self.clear_btn.clicked.connect(self.clear_files)
        buttons.addWidget(self.clear_btn)
        v.addLayout(buttons)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        v.addWidget(self.file_list, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.summary_label)

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        self.preview_label = QLabel(tr("Add a GIF to see how it will look"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumSize(280, 240)
        self.preview_label.setStyleSheet(
            f"background-color: {_T.CARD}; border: 1px solid {_T.BORDER}; border-radius: 4px;"
            f" color: {_T.TEXT_HINT};")
        v.addWidget(self.preview_label, stretch=1)

        self.preview_note = QLabel("")
        self.preview_note.setWordWrap(True)
        self.preview_note.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.preview_note)

        settings = QGroupBox(tr("Output"))
        s = QVBoxLayout()

        codec_row = QHBoxLayout()
        codec_row.addWidget(QLabel(tr("Format:")))
        self.codec_combo = QComboBox()
        self.codec_combo.addItems(gif_to_mp4.CODECS)
        self.codec_combo.currentTextChanged.connect(self._on_codec_changed)
        codec_row.addWidget(self.codec_combo, stretch=1)
        s.addLayout(codec_row)

        quality_row = QHBoxLayout()
        quality_row.addWidget(QLabel(tr("Quality:")))
        self.quality_combo = QComboBox()
        for label, crf in gif_to_mp4.QUALITY_PRESETS:
            self.quality_combo.addItem(f"{label}  (crf {crf})", crf)
        self.quality_combo.setCurrentIndex(
            [c for _, c in gif_to_mp4.QUALITY_PRESETS].index(gif_to_mp4.DEFAULT_CRF))
        quality_row.addWidget(self.quality_combo, stretch=1)
        s.addLayout(quality_row)

        bg_row = QHBoxLayout()
        self.bg_caption = QLabel(tr("Transparent becomes:"))
        bg_row.addWidget(self.bg_caption)
        self.bg_combo = QComboBox()
        for label, value in gif_to_mp4.BACKGROUND_PRESETS:
            self.bg_combo.addItem(label, value)
        self.bg_combo.currentIndexChanged.connect(self._on_background_changed)
        bg_row.addWidget(self.bg_combo, stretch=1)
        self.bg_pick_btn = QPushButton(tr("Pick…"))
        self.bg_pick_btn.setFixedWidth(56)
        self.bg_pick_btn.clicked.connect(self.pick_background)
        bg_row.addWidget(self.bg_pick_btn)
        s.addLayout(bg_row)

        resize_row = QHBoxLayout()
        self.resize_checkbox = QCheckBox(tr("Resize width to"))
        self.resize_checkbox.toggled.connect(self._on_resize_toggled)
        resize_row.addWidget(self.resize_checkbox)
        self.width_spinbox = QSpinBox()
        self.width_spinbox.setRange(64, 4096)
        self.width_spinbox.setSingleStep(16)
        self.width_spinbox.setValue(800)
        self.width_spinbox.setSuffix(" px")
        self.width_spinbox.setEnabled(False)
        resize_row.addWidget(self.width_spinbox)
        resize_row.addStretch()
        s.addLayout(resize_row)

        self.dest_label = QLabel("")
        self.dest_label.setWordWrap(True)
        self.dest_label.setStyleSheet(f"color: {_T.TEXT_HINT}; font-size: 10px;")
        s.addWidget(self.dest_label)

        dest_row = QHBoxLayout()
        self.beside_btn = QPushButton(tr("Save Beside Source"))
        self.beside_btn.clicked.connect(self.use_source_folder)
        dest_row.addWidget(self.beside_btn)
        self.folder_btn = QPushButton(tr("Choose Folder…"))
        self.folder_btn.clicked.connect(self.choose_output_folder)
        dest_row.addWidget(self.folder_btn)
        s.addLayout(dest_row)

        settings.setLayout(s)
        v.addWidget(settings)

        self.convert_btn = QPushButton(tr("🎬 Convert"))
        self.convert_btn.clicked.connect(self.convert)
        v.addWidget(self.convert_btn)

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel)
        v.addWidget(self.cancel_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        v.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.status_label)

        self._ffmpeg_hint = QLabel()
        self._ffmpeg_hint.setWordWrap(True)
        self._ffmpeg_hint.setStyleSheet("font-size: 10px;")
        v.addWidget(self._ffmpeg_hint)

        self._install_ffmpeg_btn = QPushButton(tr("How to Install FFmpeg…"))
        self._install_ffmpeg_btn.setStyleSheet("font-size: 10px;")
        self._install_ffmpeg_btn.clicked.connect(self._show_install_dialog)
        v.addWidget(self._install_ffmpeg_btn)

        self._update_dest_label()
        return panel

    # ── files ────────────────────────────────────────────────────────────

    def add_files(self):
        patterns = " ".join(f"*{s}" for s in gif_to_mp4.INPUT_SUFFIXES)
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Add Animations"), self.last_dir,
            f"Animations ({patterns});;All files (*)")
        self.add_paths(paths)

    def add_paths(self, paths):
        known = {s.path for s in self.sources}
        for raw in paths:
            path = Path(raw)
            if path in known:
                continue
            known.add(path)          # also catches repeats within this one call
            self.sources.append(SourceFile(path))
            self.last_dir = str(path.parent)
        self._rebuild_list()
        if self.sources and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def remove_selected(self):
        for item in self.file_list.selectedItems():
            source = item.data(Qt.ItemDataRole.UserRole)
            if source in self.sources:
                self.sources.remove(source)
        self._rebuild_list()

    def clear_files(self):
        self.sources = []
        self._current_pixmap = None
        self.preview_label.setText(tr("Add a GIF to see how it will look"))
        self.preview_note.setText("")
        self._rebuild_list()

    def _rebuild_list(self):
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for source in self.sources:
            item = QListWidgetItem(source.label())
            item.setData(Qt.ItemDataRole.UserRole, source)
            if source.error:
                item.setForeground(QColor(_T.ERROR))
            self.file_list.addItem(item)
        self.file_list.blockSignals(False)
        self._update_summary()
        self._update_enabled_state()

    def _update_summary(self):
        usable = [s for s in self.sources if not s.error]
        if not self.sources:
            self.summary_label.setText("")
            return
        total = sum(s.size_mb for s in usable)
        clear = sum(1 for s in usable if s.transparent)
        text = f"{len(usable)} file(s), {total:.1f} MB"
        if clear:
            text += f"  ·  {clear} with transparency"
        bad = len(self.sources) - len(usable)
        if bad:
            text += f"  ·  {bad} unreadable"
        self.summary_label.setText(text)

    # ── preview ──────────────────────────────────────────────────────────

    def _on_file_selected(self, _row: int):
        self._refresh_preview()

    def _refresh_preview(self):
        item = self.file_list.currentItem()
        source = item.data(Qt.ItemDataRole.UserRole) if item else None
        if source is None:
            return
        if source.error:
            self._current_pixmap = None
            self.preview_label.setText(tr("This file could not be read"))
            self.preview_note.setText(source.error)
            return
        try:
            with Image.open(source.path) as im:
                frame = next(ImageSequence.Iterator(im)).convert("RGBA")
        except Exception as e:
            self._current_pixmap = None
            self.preview_label.setText(tr("This file could not be read"))
            self.preview_note.setText(f"{type(e).__name__}: {e}")
            return

        keeps_alpha = self.codec_combo.currentText() == gif_to_mp4.VP9_ALPHA
        if source.transparent and not keeps_alpha:
            # Show the decision that is about to be baked in, rather than
            # letting it be a surprise in the finished file.
            flat = Image.new("RGBA", frame.size, self._background_rgba())
            flat.alpha_composite(frame)
            frame = flat
            note = f"transparent areas will become {self._background_name()}"
        elif source.transparent:
            note = "transparency is kept (VP9/WebM)"
        else:
            note = "no transparency in this file"
        self._current_pixmap = _pil_to_pixmap(frame)
        self._paint_preview()
        self.preview_note.setText(f"{source.width}×{source.height}  ·  {note}")

    def _paint_preview(self):
        pixmap = self._current_pixmap
        if pixmap is None or pixmap.isNull():
            return
        avail = self.preview_label.size()
        if avail.width() > 1 and avail.height() > 1:
            pixmap = pixmap.scaled(avail, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_preview()

    # ── settings ─────────────────────────────────────────────────────────

    def _background_name(self) -> str:
        return self._background

    def _background_rgba(self):
        colour = QColor(self._background)
        if not colour.isValid():
            colour = QColor("white")
        return colour.red(), colour.green(), colour.blue(), 255

    def _on_background_changed(self, _index: int):
        value = self.bg_combo.currentData()
        if value:
            self._background = value
        self._refresh_preview()

    def pick_background(self):
        chosen = QColorDialog.getColor(QColor(self._background), self, tr("Background Colour"))
        if not chosen.isValid():
            return
        self._background = chosen.name()
        if self.bg_combo.findData(self._background) < 0:
            self.bg_combo.addItem(self._background, self._background)
        self.bg_combo.setCurrentIndex(self.bg_combo.findData(self._background))
        self._refresh_preview()

    def _on_codec_changed(self, codec: str):
        keeps_alpha = codec == gif_to_mp4.VP9_ALPHA
        for w in (self.bg_caption, self.bg_combo, self.bg_pick_btn):
            w.setEnabled(not keeps_alpha)
        self._update_dest_label()
        self._refresh_preview()

    def _on_resize_toggled(self, checked: bool):
        self.width_spinbox.setEnabled(checked)

    def use_source_folder(self):
        self.out_dir = None
        self._update_dest_label()

    def choose_output_folder(self):
        chosen = QFileDialog.getExistingDirectory(
            self, tr("Select Output Folder"), self.last_dir)
        if chosen:
            self.out_dir = Path(chosen)
            self._update_dest_label()

    def _update_dest_label(self):
        ext = gif_to_mp4.extension_for(self.codec_combo.currentText())
        where = str(self.out_dir) if self.out_dir else "beside each source file"
        self.dest_label.setText(f"Writing <name>.{ext} to {where}")

    # ── conversion ───────────────────────────────────────────────────────

    def convert(self):
        jobs = [s for s in self.sources if not s.error]
        if not jobs:
            QMessageBox.warning(self, "Warning", "Add at least one readable animation first!")
            return
        if not self._ffmpeg_ok:
            QMessageBox.warning(self, "Warning", "ffmpeg is required to convert.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.convert_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)
        self.cancel_btn.setEnabled(True)

        self._worker = _ConvertWorker(
            jobs, self.out_dir, self.codec_combo.currentText(),
            self.quality_combo.currentData(), self._background, 0.0,
            self.width_spinbox.value() if self.resize_checkbox.isChecked() else 0, self)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_progress.connect(self.progress_bar.setValue)
        self._worker.file_done.connect(self._on_file_done)
        self._worker.finished_all.connect(self._on_all_done)
        self._worker.start()

    def _on_file_started(self, index: int, name: str):
        total = len([s for s in self.sources if not s.error])
        self.status_label.setText(f"Converting {name}  ({index + 1}/{total})")
        self.progress_bar.setValue(0)

    def _on_file_done(self, name: str, before: float, after: float):
        ratio = before / after if after else 0.0
        self.status_label.setText(
            f"{name}: {before:.1f} MB → {after:.1f} MB  ({ratio:.1f}× smaller)")

    def _on_all_done(self, converted: int, failures: list):
        self.progress_bar.setVisible(False)
        self.cancel_btn.setVisible(False)
        self.convert_btn.setEnabled(True)
        message = f"Converted {converted} file(s)."
        if failures:
            listed = "\n".join(f"· {n}: {why}" for n, why in failures[:8])
            more = f"\n…and {len(failures) - 8} more" if len(failures) > 8 else ""
            message += f"\n\n{len(failures)} failed:\n{listed}{more}"
        QMessageBox.information(self, "GIF to Video", message)
        self.status_label.setText(f"Converted {converted}, {len(failures)} failed")

    def _cancel(self):
        if self._worker is not None:
            self._worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Cancelling…")

    # ── ffmpeg presence ──────────────────────────────────────────────────

    def _apply_ffmpeg_state(self):
        if self._ffmpeg_ok:
            self._ffmpeg_hint.setText(tr("ffmpeg found — ready to convert."))
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.SUCCESS}; font-size: 10px;")
            self._install_ffmpeg_btn.setVisible(False)
        else:
            info = get_ffmpeg_install_info()
            self._ffmpeg_hint.setText(
                "ffmpeg not found — conversion unavailable.\n"
                f"Recommended: {info['command']}")
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.ERROR}; font-size: 10px;")
            self._install_ffmpeg_btn.setVisible(True)

    def _show_install_dialog(self):
        info = get_ffmpeg_install_info()
        QMessageBox.information(
            self, "Install FFmpeg",
            f"{info['platform']} — {info['method']}\n\n"
            f"{info['command']}\n\n{info['url']}\n\n{info['note']}")
        self._ffmpeg_ok = is_ffmpeg_available()
        self._apply_ffmpeg_state()
        self._update_enabled_state()

    # ── misc ─────────────────────────────────────────────────────────────

    def _update_enabled_state(self):
        usable = any(not s.error for s in self.sources)
        self.convert_btn.setEnabled(usable and self._ffmpeg_ok)
        self.remove_btn.setEnabled(bool(self.sources))
        self.clear_btn.setEnabled(bool(self.sources))

    def stop_workers(self, timeout_ms: int = 30000):
        """Qt aborts the process if a QThread outlives its widget."""
        if self._worker is not None:
            self._worker.cancel()
            if self._worker.isRunning():
                self._worker.wait(timeout_ms)

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
