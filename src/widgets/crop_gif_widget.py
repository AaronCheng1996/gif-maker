"""Crop GIF — trim finished animations to a rectangle you drag on the real frames.

Unlike cropping during a render, the preview here *is* the file, so what you see
is exactly what gets written. One rectangle can be applied to a whole batch,
which suits a folder of animations exported from the same model.
"""
from pathlib import Path
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QListWidget, QListWidgetItem, QGroupBox, QSpinBox,
                              QCheckBox, QFileDialog, QMessageBox, QProgressBar,
                              QSplitter, QSizePolicy, QAbstractItemView, QLineEdit)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from PIL import Image, ImageSequence

from ..i18n import tr
from ..core import gif_to_mp4
from ..core.cropping import CropError, crop_animation_file, is_noop, pixel_box
from ..core.video_to_gif import extract_preview_frames
from .crop_overlay import CropOverlayLabel
from .theme import AppTheme as _T
from . import ui

PREVIEW_MAX = 720
SUPPORTED = "Animations (*.gif *.png *.webp *.apng *.mp4 *.mov *.webm *.mkv);;All files (*)"
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv"}
# Video is sampled rather than fully decoded: the rectangle is stored as
# fractions, so a shorter, slower preview places it just as precisely.
PREVIEW_VIDEO_FPS = 10.0
PREVIEW_VIDEO_SECONDS = 12.0


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimg)
    del data
    return pixmap


class _CropSpinBox(QSpinBox):
    """A pixel field that lets a number be typed before it is acted on.

    Qt commits and clamps on every keystroke by default, which makes replacing
    one number with another unreliable: the old digits are still there while the
    new ones arrive, the intermediate value is clamped to the frame size, and
    what lands is neither number. Tracking is off so the value settles on Enter
    or focus-out, and a click selects the field so typing replaces it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setKeyboardTracking(False)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)

    def mousePressEvent(self, event):
        had_focus = self.hasFocus()
        super().mousePressEvent(event)
        if not had_focus:
            QTimer.singleShot(0, self.selectAll)


class _FrameLoader(QThread):
    """Decodes an animation's frames, downscaled for display."""
    done = pyqtSignal(str, list, list, int, int)   # path, pixmaps, durations, w, h
    failed = pyqtSignal(str, str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            if self.path.suffix.lower() in VIDEO_SUFFIXES:
                pixmaps, durations, width, height = self._load_video()
            else:
                pixmaps, durations, width, height = self._load_image()
            if not pixmaps:
                self.failed.emit(str(self.path), "No frames found")
                return
            self.done.emit(str(self.path), pixmaps, durations, width, height)
        except Exception as e:
            self.failed.emit(str(self.path), str(e))

    def _load_image(self):
        with Image.open(self.path) as src:
            width, height = src.size
            scale = min(PREVIEW_MAX / max(width, height), 1.0)
            size = (max(1, int(width * scale)), max(1, int(height * scale)))
            pixmaps, durations = [], []
            for frame in ImageSequence.Iterator(src):
                durations.append(frame.info.get("duration", 100))
                rgba = frame.convert("RGBA")
                if scale < 1.0:
                    rgba = rgba.resize(size, Image.Resampling.BILINEAR)
                pixmaps.append(_pil_to_pixmap(rgba))
                if len(pixmaps) >= 400:   # plenty for a preview
                    break
        return pixmaps, durations, width, height

    def _load_video(self):
        """Decode a video through ffmpeg so it gets the same draggable preview.

        The crop rectangle is stored as fractions of the frame, so a sampled,
        downscaled preview positions it just as accurately as the full file
        would — but the true dimensions still have to come from the container,
        because that is what the pixel readout reports."""
        info = gif_to_mp4.get_animation_info(self.path)
        width, height = info.get("width", 0), info.get("height", 0)
        if not width or not height:
            raise RuntimeError("ffmpeg could not read this video's dimensions")

        fps = min(info.get("fps") or PREVIEW_VIDEO_FPS, PREVIEW_VIDEO_FPS)
        frames = extract_preview_frames(
            str(self.path), fps=fps, max_width=PREVIEW_MAX,
            max_duration=PREVIEW_VIDEO_SECONDS)
        pixmaps = [_pil_to_pixmap(img) for img, _ in frames]
        durations = [ms for _, ms in frames]
        return pixmaps, durations, width, height


class _CropWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(list, list)
    error = pyqtSignal(str)

    def __init__(self, jobs, ffmpeg_path=None, parent=None):
        super().__init__(parent)
        self.jobs = jobs            # [(source, destination, crop)]
        self.ffmpeg_path = ffmpeg_path
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        written, failures = [], []
        total = len(self.jobs)
        try:
            for i, (src, dst, crop) in enumerate(self.jobs):
                if self._cancelled:
                    break
                self.progress.emit(i, total, Path(src).name)
                try:
                    written.append(crop_animation_file(
                        src, crop, ffmpeg_path=self.ffmpeg_path, output_path=dst))
                except Exception as e:
                    failures.append((Path(src).name, str(e)))
            self.progress.emit(total, total, "")
            self.done.emit(written, failures)
        except Exception as e:
            self.error.emit(str(e))


class CropGifWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.files: List[Path] = []
        self.frames: List[QPixmap] = []
        self.durations: List[int] = []
        self.source_size: Optional[Tuple[int, int]] = None
        self.last_dir = ""
        self.last_output_dir = ""

        # Each file keeps its own rectangle, in source pixels rather than
        # fractions: a batch is usually the same shot at the same size, and a
        # proportional rectangle would give every differently-sized file a
        # differently-sized result.
        self._crops: dict = {}          # str(path) -> (x, y, w, h) in pixels
        self._sizes: dict = {}          # str(path) -> (width, height)
        self._shared_size: Optional[Tuple[int, int]] = None

        self._loader: Optional[_FrameLoader] = None
        self._worker: Optional[_CropWorker] = None
        self._frame_index = 0
        self._playing = False
        self._updating_fields = False

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_frame)

        self._init_ui()
        self._update_enabled_state()

    # ── UI ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = ui.tab_layout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_center_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([280, 720, 280])
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        title = QLabel(tr("Files"))
        title.setStyleSheet(ui.TITLE_QSS)
        v.addWidget(title)

        self.add_btn = QPushButton(tr("📂 Add Animations…"))
        self.add_btn.setToolTip("GIF, APNG, WebP, or video files")
        self.add_btn.clicked.connect(self.add_files)
        v.addWidget(self.add_btn)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        v.addWidget(self.file_list, stretch=1)

        row = QHBoxLayout()
        self.remove_btn = QPushButton(tr("Remove Selected"))
        self.remove_btn.clicked.connect(self.remove_selected)
        row.addWidget(self.remove_btn)
        self.clear_btn = QPushButton(tr("Clear All"))
        self.clear_btn.clicked.connect(self.clear_files)
        row.addWidget(self.clear_btn)
        v.addLayout(row)

        hint = QLabel(tr("The same crop is applied to every file listed."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_T.TEXT_HINT}; font-size: 10px;")
        v.addWidget(hint)
        return panel

    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        self.preview = CropOverlayLabel()
        self.preview.setText(tr("Add an animation to crop"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setMinimumSize(360, 360)
        self.preview.setStyleSheet(
            f"background-color: {_T.CARD}; border: 1px solid {_T.BORDER}; border-radius: 4px;"
            f" color: {_T.TEXT_HINT};")
        self.preview.set_crop_enabled(True)
        self.preview.crop_changed.connect(self._on_crop_changed)
        v.addWidget(self.preview, stretch=1)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(36)
        self.play_btn.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_btn)

        self.frame_label = QLabel("—")
        self.frame_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        controls.addWidget(self.frame_label)
        controls.addStretch()

        self.info_label = QLabel("")
        self.info_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        controls.addWidget(self.info_label)
        v.addLayout(controls)
        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        crop_group = QGroupBox(tr("Crop Region"))
        cg = QVBoxLayout()

        self.spin_x = self._make_spin("X:", cg)
        self.spin_y = self._make_spin("Y:", cg)
        self.spin_w = self._make_spin("Width:", cg)
        self.spin_h = self._make_spin("Height:", cg)

        self.reset_btn = QPushButton(tr("Reset to full frame"))
        self.reset_btn.clicked.connect(self.preview.reset_crop)
        cg.addWidget(self.reset_btn)

        self.same_size_checkbox = QCheckBox(tr("Same size for every file"))
        self.same_size_checkbox.setChecked(True)
        self.same_size_checkbox.setToolTip(
            "Keep the rectangle the same number of pixels on every file, so a "
            "batch comes out at one size. Each file still remembers where its "
            "own rectangle sits. Untick to let each file keep its own size too.")
        self.same_size_checkbox.toggled.connect(self._on_same_size_toggled)
        cg.addWidget(self.same_size_checkbox)

        crop_group.setLayout(cg)
        v.addWidget(crop_group)

        out_group = QGroupBox(tr("Output"))
        og = QVBoxLayout()
        self.overwrite_checkbox = QCheckBox(tr("Overwrite originals"))
        self.overwrite_checkbox.setToolTip("Otherwise cropped copies are written alongside them")
        self.overwrite_checkbox.toggled.connect(self._on_overwrite_toggled)
        og.addWidget(self.overwrite_checkbox)

        suffix_row = QHBoxLayout()
        suffix_row.addWidget(QLabel(tr("Suffix:")))
        self.suffix_edit = QLineEdit("_cropped")
        suffix_row.addWidget(self.suffix_edit)
        og.addLayout(suffix_row)

        self.folder_btn = QPushButton(tr("Output folder…"))
        self.folder_btn.clicked.connect(self.choose_output_folder)
        og.addWidget(self.folder_btn)

        self.folder_label = QLabel(tr("Same folder as each source"))
        self.folder_label.setWordWrap(True)
        self.folder_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        og.addWidget(self.folder_label)

        out_group.setLayout(og)
        v.addWidget(out_group)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.result_label)
        v.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        v.addWidget(self.progress_bar)

        self.crop_btn = QPushButton(tr("✂ Crop"))
        self.crop_btn.setStyleSheet(ui.GO_QSS)
        self.crop_btn.clicked.connect(self.run_crop)
        v.addWidget(self.crop_btn)
        return panel

    def _make_spin(self, label: str, layout) -> QSpinBox:
        row = QHBoxLayout()
        row.addWidget(QLabel(tr(label)))
        spin = _CropSpinBox()
        spin.setRange(0, 100000)
        spin.setSuffix(" px")
        # editingFinished, not valueChanged: with per-keystroke updates the
        # rectangle was rewritten mid-word and clamped the half-typed number,
        # so replacing 200 with 1000 passed through 1000200 and came out wrong.
        spin.editingFinished.connect(self._on_spin_committed)
        row.addWidget(spin)
        layout.addLayout(row)
        return spin

    # ── files ────────────────────────────────────────────────────────────

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Add Animations"), self.last_dir, SUPPORTED)
        if not paths:
            return
        self.last_dir = str(Path(paths[0]).parent)
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
                self.file_list.addItem(QListWidgetItem(path.name))
        self._update_enabled_state()
        if self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def remove_selected(self):
        rows = sorted((self.file_list.row(i) for i in self.file_list.selectedItems()),
                      reverse=True)
        if not rows:
            return
        for row in rows:
            self.file_list.takeItem(row)
            del self.files[row]
        if not self.files:
            self._clear_preview()
        self._update_enabled_state()

    def clear_files(self):
        self.files.clear()
        self.file_list.clear()
        self._clear_preview()
        self._update_enabled_state()

    def _clear_preview(self):
        self.pause_playback()
        self.frames = []
        self.durations = []
        self.source_size = None
        self.preview.set_preview_pixmap(None)
        self.preview.setText(tr("Add an animation to crop"))
        self.info_label.setText("")
        self.frame_label.setText("—")
        self._sync_spinboxes()

    def _on_file_selected(self, row: int):
        if not (0 <= row < len(self.files)):
            return
        self.pause_playback()
        path = self.files[row]
        self.info_label.setText(tr("Loading…"))
        self._loader = _FrameLoader(path, self)
        self._loader.done.connect(self._on_frames_loaded)
        self._loader.failed.connect(self._on_frames_failed)
        self._loader.start()

    def _on_frames_loaded(self, path: str, pixmaps, durations, width, height):
        if not self.files or Path(path) != self.files[max(self.file_list.currentRow(), 0)]:
            return   # selection moved on while loading
        self.frames = pixmaps
        self.durations = durations
        self.source_size = (width, height)
        self._frame_index = 0
        self.preview.set_preview_pixmap(self.frames[0])
        self.info_label.setText(f"{width}×{height} · {len(pixmaps)} frames")
        self._sizes[path] = (width, height)
        self._restore_crop_for_current()
        self._update_frame_label()
        self._sync_spinboxes()

    def _on_frames_failed(self, path: str, message: str):
        self.info_label.setText(f"Could not read {Path(path).name}: {message}")

    # ── crop rectangle ───────────────────────────────────────────────────

    def _on_crop_changed(self):
        self._remember_crop()
        self._sync_spinboxes()

    def _restore_crop_for_current(self):
        """Put back whatever rectangle this file should start with."""
        row = self.file_list.currentRow()
        if not (0 <= row < len(self.files)):
            return
        x, y, w, h = self.crop_for(self.files[row])
        self._updating_fields = True
        try:
            self.preview.set_crop_rect(x, y, w, h)
        finally:
            self._updating_fields = False
        self._remember_crop()

    def _on_same_size_toggled(self, checked: bool):
        if checked:
            self._remember_crop()      # adopt the current rectangle as the size

    def _sync_spinboxes(self):
        """Mirror the dragged rectangle into the pixel fields."""
        if self._updating_fields:
            return
        self._updating_fields = True
        try:
            if self.source_size is None:
                for s in (self.spin_x, self.spin_y, self.spin_w, self.spin_h):
                    s.setEnabled(False)
                    s.setValue(0)
                return
            w, h = self.source_size
            left, top, right, bottom = pixel_box(w, h, self.preview.crop_rect())
            for s, value, maximum in ((self.spin_x, left, w), (self.spin_y, top, h),
                                      (self.spin_w, right - left, w),
                                      (self.spin_h, bottom - top, h)):
                s.setEnabled(True)
                s.setMaximum(maximum)
                s.setValue(value)
        finally:
            self._updating_fields = False

    def _on_spin_committed(self):
        """A finished edit feeds the typed pixels back into the rectangle."""
        if self._updating_fields or self.source_size is None:
            return
        w, h = self.source_size
        self._updating_fields = True
        try:
            self.preview.set_crop_rect(self.spin_x.value() / w, self.spin_y.value() / h,
                                       self.spin_w.value() / w, self.spin_h.value() / h)
        finally:
            self._updating_fields = False
        self._sync_spinboxes()

    def active_crop(self):
        return self.preview.crop_rect()

    # ── per-file crop rectangles ─────────────────────────────────────────

    def size_of(self, path: Path) -> Optional[Tuple[int, int]]:
        """Frame size of a queued file, read once and remembered.

        Needed for every file, not just the previewed one: a pixel rectangle has
        to be turned back into fractions against each file's own dimensions."""
        key = str(path)
        if key not in self._sizes:
            size = None
            try:
                if path.suffix.lower() in VIDEO_SUFFIXES:
                    info = gif_to_mp4.get_animation_info(path)
                    if info.get("width") and info.get("height"):
                        size = (info["width"], info["height"])
                else:
                    with Image.open(path) as im:
                        size = im.size
            except Exception:
                size = None
            self._sizes[key] = size
        return self._sizes[key]

    def _remember_crop(self):
        """Store the rectangle against the current file, in source pixels."""
        row = self.file_list.currentRow()
        if not (0 <= row < len(self.files)) or self.source_size is None:
            return
        w, h = self.source_size
        left, top, right, bottom = pixel_box(w, h, self.preview.crop_rect())
        box = (left, top, right - left, bottom - top)
        self._crops[str(self.files[row])] = box
        if self.same_size_checkbox.isChecked():
            self._shared_size = (box[2], box[3])

    def crop_for(self, path: Path):
        """The normalised rectangle to apply to one file.

        Falls back to this file's own remembered box, then to the shared pixel
        size placed where it last sat, then to the whole frame."""
        size = self.size_of(path)
        if size is None:
            return (0.0, 0.0, 1.0, 1.0)
        w, h = size
        box = self._crops.get(str(path))
        if box is None:
            if self._shared_size is None:
                return (0.0, 0.0, 1.0, 1.0)
            box = self._placed_shared_box(w, h)
        x, y, bw, bh = box
        bw = max(1, min(bw, w))
        bh = max(1, min(bh, h))
        x = max(0, min(x, w - bw))
        y = max(0, min(y, h - bh))
        return (x / w, y / h, bw / w, bh / h)

    def _placed_shared_box(self, w: int, h: int):
        """The shared pixel size, centred, clipped to a frame of w x h."""
        sw, sh = self._shared_size
        sw, sh = max(1, min(sw, w)), max(1, min(sh, h))
        return ((w - sw) // 2, (h - sh) // 2, sw, sh)

    # ── playback ─────────────────────────────────────────────────────────

    def toggle_playback(self):
        self.pause_playback() if self._playing else self.play_playback()

    def play_playback(self):
        if len(self.frames) < 2:
            return
        self._playing = True
        self.play_btn.setText("⏸")
        self._play_timer.start(max(self.durations[self._frame_index], 20))

    def pause_playback(self):
        self._playing = False
        self.play_btn.setText("▶")
        self._play_timer.stop()

    def _advance_frame(self):
        if not self.frames:
            return
        self._frame_index = (self._frame_index + 1) % len(self.frames)
        self.preview.set_preview_pixmap(self.frames[self._frame_index])
        self._update_frame_label()
        self._play_timer.start(max(self.durations[self._frame_index], 20))

    def _update_frame_label(self):
        if self.frames:
            self.frame_label.setText(f"Frame {self._frame_index + 1}/{len(self.frames)}")
        else:
            self.frame_label.setText("—")

    # ── output ───────────────────────────────────────────────────────────

    def _on_overwrite_toggled(self, checked: bool):
        self.suffix_edit.setEnabled(not checked)
        self.folder_btn.setEnabled(not checked)

    def choose_output_folder(self):
        directory = QFileDialog.getExistingDirectory(
            self, tr("Select Export Directory"), self.last_output_dir)
        if directory:
            self.last_output_dir = directory
            self.folder_label.setText(directory)

    def _destination_for(self, source: Path) -> Path:
        if self.overwrite_checkbox.isChecked():
            return source
        folder = Path(self.last_output_dir) if self.last_output_dir else source.parent
        suffix = self.suffix_edit.text().strip()
        if folder == source.parent and not suffix:
            suffix = "_cropped"   # never silently overwrite when not asked to
        return folder / f"{source.stem}{suffix}{source.suffix}"

    def run_crop(self):
        if not self.files:
            QMessageBox.warning(self, "Warning", "Add at least one animation first!")
            return
        crop = self.active_crop()
        if is_noop(crop):
            QMessageBox.warning(self, "Warning",
                                "The crop covers the whole frame — drag a smaller "
                                "region on the preview first.")
            return
        if self.overwrite_checkbox.isChecked():
            reply = QMessageBox.question(
                self, "Overwrite?",
                f"Replace {len(self.files)} original file(s) with the cropped version?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        jobs = [(str(p), str(self._destination_for(p)), self.crop_for(p))
                for p in self.files]
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(jobs))
        self.progress_bar.setValue(0)
        self.crop_btn.setEnabled(False)
        self.result_label.setText("")

        self._worker = _CropWorker(jobs, parent=self)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, current: int, total: int, name: str):
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total} · {name}" if name else f"{current}/{total}")

    def _on_done(self, written: List[str], failures: List[tuple]):
        self.progress_bar.setVisible(False)
        self.crop_btn.setEnabled(True)
        if written:
            with_size = ""
            try:
                with Image.open(written[0]) as im:
                    with_size = f" ({im.width}×{im.height})"
            except Exception:
                pass
            self.result_label.setText(f"Cropped {len(written)} file(s){with_size}")
        message = f"Cropped {len(written)} file(s)."
        if written:
            message += f"\n\nInto: {Path(written[0]).parent}"
        if failures:
            message += "\n\nFailed:\n" + "\n".join(f"  {n}: {e}" for n, e in failures[:5])
            QMessageBox.warning(self, "Finished with errors", message)
        else:
            QMessageBox.information(self, "Crop complete", message)
        # Reload the preview so it reflects what is now on disk.
        row = self.file_list.currentRow()
        if row >= 0 and self.overwrite_checkbox.isChecked():
            self.preview.reset_crop()
            self._on_file_selected(row)

    def _on_error(self, message: str):
        self.progress_bar.setVisible(False)
        self.crop_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"Cropping failed:\n{message}")

    # ── misc ─────────────────────────────────────────────────────────────

    def _update_enabled_state(self):
        has = bool(self.files)
        for w in (self.file_list, self.remove_btn, self.clear_btn, self.crop_btn,
                  self.reset_btn, self.play_btn):
            w.setEnabled(has)

    def stop_workers(self, timeout_ms: int = 30000):
        """Join background threads; Qt aborts if one outlives its widget."""
        self._play_timer.stop()
        self._playing = False
        if self._worker is not None:
            self._worker.cancel()
        for worker in (self._loader, self._worker):
            if worker is not None and worker.isRunning():
                worker.wait(timeout_ms)

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
