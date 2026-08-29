"""Video Concat — play several clips one after another as a single file.

Not an editor: there is no timeline, no trimming and no transitions. The whole
job is "these, in this order, as one file", and everything on the tab exists
because joining unlike parts forces a decision that the user should be able to
see before it is made.

The preview is the point of the layout. Clips rarely share a shape, so most of
them get letterboxed, and a padded clip looks wrong in a way that is much easier
to catch by eye than to read out of a settings panel. Selecting a clip shows it
inside the frame the join will actually produce, bars and all.
"""
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QGroupBox, QComboBox,
                             QDoubleSpinBox, QProgressBar, QFileDialog, QMessageBox,
                             QAbstractItemView, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPainter, QPixmap, QColor

from PIL import Image

from ..i18n import tr
from ..core import concat
from ..core.video_to_gif import (extract_preview_frames, get_ffmpeg_install_info,
                                 is_ffmpeg_available)
from .theme import AppTheme as _T
from . import ui

SUPPORTED = ("Video and animation (*.gif *.apng *.png *.webp "
             "*.mp4 *.mov *.webm *.mkv *.avi);;All files (*)")
THUMB_MAX = 640


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class Clip:
    """One file in the join, with the numbers ffprobe reported for it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.info = concat.probe(self.path)

    @property
    def ok(self) -> bool:
        return bool(self.info.get("width") and self.info.get("height"))

    def label(self) -> str:
        if not self.ok:
            return f"{self.path.name}   —   unreadable"
        i = self.info
        bits = [f"{i['width']}×{i['height']}"]
        if i.get("fps"):
            bits.append(f"{i['fps']:.4g} fps")
        if i.get("duration"):
            bits.append(f"{i['duration']:.2f}s")
        if i.get("has_audio"):
            bits.append("sound")
        return f"{self.path.name}   —   {'  ·  '.join(bits)}"


class _ThumbLoader(QThread):
    """Decodes one frame of a clip for the preview."""
    done = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            frames = extract_preview_frames(str(self.path), fps=1.0,
                                            max_width=THUMB_MAX, max_duration=1.0)
            if not frames:
                self.failed.emit(str(self.path))
                return
            self.done.emit(str(self.path), frames[0][0])
        except Exception:
            self.failed.emit(str(self.path))


class _JoinWorker(QThread):
    progress = pyqtSignal(int)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, paths, destination, options: dict, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.destination = destination
        self.options = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            out = concat.concat(self.paths, self.destination,
                                on_progress=self.progress.emit,
                                should_stop=lambda: self._cancelled,
                                **self.options)
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))


class VideoConcatWidget(QWidget):
    """Join GIFs and videos end to end into one file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.clips: List[Clip] = []
        self.last_dir = ""
        self.output_dir = ""
        self._thumb: Optional[_ThumbLoader] = None
        self._thumb_image: Optional[Image.Image] = None
        self._worker: Optional[_JoinWorker] = None
        self._ffmpeg_ok = is_ffmpeg_available()
        self._init_ui()
        self._apply_ffmpeg_state()
        self._update_summary()

    # ── UI ───────────────────────────────────────────────────────────────
    def _init_ui(self):
        layout = ui.tab_layout(self)
        layout.addWidget(self._create_left_panel())
        layout.addWidget(self._create_center_panel(), stretch=1)
        layout.addWidget(self._create_right_panel())

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(340)
        v = ui.panel_layout(panel)

        v.addWidget(ui.title_label(tr("Clips")))

        self.add_btn = QPushButton(tr("📂 Add Clips…"))
        self.add_btn.clicked.connect(self.add_files)
        v.addWidget(self.add_btn)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.currentRowChanged.connect(self._on_row_changed)
        v.addWidget(self.list, stretch=1)

        # Order is the whole point of a join, so moving a clip has to be direct.
        order = ui.row_layout()
        self.up_btn = QPushButton("▲")
        self.up_btn.setToolTip(tr("Move up"))
        self.up_btn.clicked.connect(lambda: self._move(-1))
        order.addWidget(self.up_btn)
        self.down_btn = QPushButton("▼")
        self.down_btn.setToolTip(tr("Move down"))
        self.down_btn.clicked.connect(lambda: self._move(+1))
        order.addWidget(self.down_btn)
        order.addStretch()
        self.remove_btn = QPushButton(tr("Remove"))
        self.remove_btn.clicked.connect(self.remove_selected)
        order.addWidget(self.remove_btn)
        self.clear_btn = QPushButton(tr("Clear"))
        self.clear_btn.clicked.connect(self.clear_clips)
        order.addWidget(self.clear_btn)
        v.addLayout(order)

        self.order_hint = ui.hint_label(
            tr("Clips play top to bottom, in this order."))
        v.addWidget(self.order_hint)
        return panel

    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        self.preview = QLabel(tr("Add two or more clips to join"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 240)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet(
            f"background-color: {_T.PANEL}; border: 1px solid {_T.BORDER}; "
            f"color: {_T.TEXT_DIM};")
        v.addWidget(self.preview, stretch=1)

        self.preview_caption = ui.hint_label("")
        self.preview_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.preview_caption)
        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(300)
        v = ui.panel_layout(panel)

        v.addWidget(ui.title_label(tr("Output")))

        out_group = QGroupBox(tr("Format"))
        og = ui.group_layout()

        self.format_combo = QComboBox()
        self.format_combo.addItems(concat.OUTPUTS)
        self.format_combo.currentIndexChanged.connect(self._on_settings_changed)
        og.addWidget(self.format_combo)

        og.addWidget(ui.body_label(tr("Frame size")))
        self.size_combo = QComboBox()
        self.size_combo.addItems(concat.SIZE_MODES)
        self.size_combo.setToolTip(
            "Clips that are a different shape are fitted inside this frame and "
            "padded — never stretched.")
        self.size_combo.currentIndexChanged.connect(self._on_settings_changed)
        og.addWidget(self.size_combo)

        fps_row = ui.row_layout()
        fps_row.addWidget(ui.body_label(tr("Frame rate")))
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(0.0, 120.0)
        self.fps_spin.setDecimals(2)
        self.fps_spin.setSpecialValueText(tr("Auto"))
        self.fps_spin.setValue(0.0)
        self.fps_spin.setToolTip(
            "Auto uses the highest frame rate among the clips, so the smoothest "
            "one is not decimated to match the worst.")
        self.fps_spin.valueChanged.connect(self._on_settings_changed)
        fps_row.addWidget(self.fps_spin)
        og.addLayout(fps_row)

        og.addWidget(ui.body_label(tr("Padding / background")))
        self.bg_combo = QComboBox()
        for label, _value in concat.BACKGROUND_PRESETS:
            self.bg_combo.addItem(tr(label))
        self.bg_combo.currentIndexChanged.connect(self._on_settings_changed)
        og.addWidget(self.bg_combo)

        out_group.setLayout(og)
        v.addWidget(out_group)

        self.recipe = ui.body_label("")
        self.recipe.setWordWrap(True)
        v.addWidget(self.recipe)

        v.addStretch()

        self._ffmpeg_hint = ui.hint_label("")
        self._ffmpeg_hint.setWordWrap(True)
        v.addWidget(self._ffmpeg_hint)
        self._install_ffmpeg_btn = QPushButton(tr("How to Install FFmpeg…"))
        self._install_ffmpeg_btn.clicked.connect(self._show_install_dialog)
        v.addWidget(self._install_ffmpeg_btn)

        dest_row = ui.row_layout()
        self.dest_btn = QPushButton(tr("Output Folder…"))
        self.dest_btn.clicked.connect(self.choose_output_folder)
        dest_row.addWidget(self.dest_btn)
        v.addLayout(dest_row)
        self.dest_label = ui.hint_label("")
        self.dest_label.setWordWrap(True)
        v.addWidget(self.dest_label)
        self._update_dest_label()

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        v.addWidget(self.progress)

        self.result_label = ui.body_label("")
        self.result_label.setWordWrap(True)
        v.addWidget(self.result_label)

        self.join_btn = QPushButton(tr("🔗 Join"))
        self.join_btn.setStyleSheet(ui.GO_QSS)
        self.join_btn.clicked.connect(self.join)
        v.addWidget(self.join_btn)
        return panel

    # ── clip list ────────────────────────────────────────────────────────
    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Select Clips"), self.last_dir, SUPPORTED)
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        known = {c.path for c in self.clips}
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.suffix.lower() not in concat.INPUT_SUFFIXES or p in known:
                continue
            known.add(p)
            self.clips.append(Clip(p))
            added += 1
        if added:
            self.last_dir = str(Path(paths[0]).parent)
            self._rebuild_list()
            if self.list.currentRow() < 0:
                self.list.setCurrentRow(0)
        self._update_summary()

    def remove_selected(self):
        rows = sorted((self.list.row(i) for i in self.list.selectedItems()),
                      reverse=True)
        for row in rows:
            if 0 <= row < len(self.clips):
                del self.clips[row]
        self._rebuild_list()
        self._update_summary()

    def clear_clips(self):
        self.clips = []
        self._thumb_image = None
        self._rebuild_list()
        self._update_summary()

    def _move(self, delta: int):
        row = self.list.currentRow()
        target = row + delta
        if not (0 <= row < len(self.clips) and 0 <= target < len(self.clips)):
            return
        self.clips[row], self.clips[target] = self.clips[target], self.clips[row]
        self._rebuild_list()
        self.list.setCurrentRow(target)
        self._update_summary()

    def _rebuild_list(self):
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for n, clip in enumerate(self.clips, 1):
            item = QListWidgetItem(f"{n}.  {clip.label()}")
            if not clip.ok:
                item.setForeground(QColor(_T.ERROR))
            self.list.addItem(item)
        self.list.blockSignals(False)
        if self.clips:
            self.list.setCurrentRow(min(max(current, 0), len(self.clips) - 1))

    # ── preview ──────────────────────────────────────────────────────────
    def _on_row_changed(self, row: int):
        self._thumb_image = None
        if not (0 <= row < len(self.clips)) or not self.clips[row].ok:
            self._paint_preview()
            return
        clip = self.clips[row]
        self._stop_thumb()
        self._thumb = _ThumbLoader(clip.path, self)
        self._thumb.done.connect(self._on_thumb_ready)
        self._thumb.failed.connect(lambda _p: self._paint_preview())
        self._thumb.start()

    def _on_thumb_ready(self, _path: str, image):
        self._thumb_image = image
        self._paint_preview()

    def current_plan(self) -> Optional[dict]:
        """The geometry the join will use, or None if it cannot be worked out."""
        usable = [c.info for c in self.clips if c.ok]
        if not usable:
            return None
        try:
            return concat.plan([c.info for c in self.clips],
                               size_mode=self.size_combo.currentText(),
                               fps=self.fps_spin.value())
        except concat.ConcatError:
            return None

    def _paint_preview(self):
        """Show the selected clip inside the frame the join will produce."""
        plan = self.current_plan()
        if self._thumb_image is None or plan is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(tr("Add two or more clips to join")
                                 if len(self.clips) < 2 else tr("No preview"))
            self.preview_caption.setText("")
            return

        box_w, box_h = plan["width"], plan["height"]
        avail = self.preview.size()
        scale = min((avail.width() - 8) / box_w, (avail.height() - 8) / box_h, 1.0)
        scale = max(scale, 0.05)
        vw, vh = max(1, int(box_w * scale)), max(1, int(box_h * scale))

        canvas = QPixmap(vw, vh)
        canvas.fill(QColor(self._background_value()))
        src = self._thumb_image
        fit = min(vw / src.width, vh / src.height)
        fw, fh = max(1, int(src.width * fit)), max(1, int(src.height * fit))
        thumb = _pil_to_pixmap(src.resize((fw, fh), Image.Resampling.BILINEAR))
        painter = QPainter(canvas)
        painter.drawPixmap((vw - fw) // 2, (vh - fh) // 2, thumb)
        painter.end()
        self.preview.setPixmap(canvas)
        self.preview.setText("")

        row = self.list.currentRow()
        pad = plan["padded"][row] if 0 <= row < len(plan["padded"]) else False
        self.preview_caption.setText(
            tr("Padded to fit the output frame") if pad
            else tr("Fills the output frame exactly"))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_preview()

    # ── settings ─────────────────────────────────────────────────────────
    def _background_value(self) -> str:
        idx = max(0, self.bg_combo.currentIndex())
        return concat.BACKGROUND_PRESETS[idx][1]

    def _on_settings_changed(self, *_a):
        self._update_summary()
        self._paint_preview()

    def _update_summary(self):
        plan = self.current_plan()
        if plan is None or len(self.clips) < 2:
            self.recipe.setText(tr("Pick at least two clips."))
            self._update_enabled_state()
            return

        fmt = self.format_combo.currentText()
        bits = [fmt, f"{plan['width']}×{plan['height']}", f"{plan['fps']:.4g} fps",
                f"{len(self.clips)} clips", f"{plan['duration']:.1f}s"]
        if plan["keep_audio"]:
            bits.append(tr("sound kept"))
        elif any(c.info.get("has_audio") for c in self.clips):
            # Saying so matters: mixing a silent clip into a join is exactly how
            # sound goes missing without anyone noticing until playback.
            bits.append(tr("sound dropped — not every clip has it"))
        padded = sum(1 for p in plan["padded"] if p)
        if padded:
            bits.append(tr("{n} padded").format(n=padded))
        self.recipe.setText("  ·  ".join(bits))
        self._update_enabled_state()

    def _update_dest_label(self):
        self.dest_label.setText(
            tr("Saved beside the first clip") if not self.output_dir
            else tr("Saved to: {d}").format(d=self.output_dir))

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("Select Output Folder"), self.output_dir or self.last_dir)
        if folder:
            self.output_dir = folder
            self._update_dest_label()

    # ── running ──────────────────────────────────────────────────────────
    def destination(self) -> Optional[Path]:
        if len(self.clips) < 2:
            return None
        ext = concat.extension_for(self.format_combo.currentText())
        first = self.clips[0].path
        folder = Path(self.output_dir) if self.output_dir else first.parent
        return folder / f"{first.stem}_joined.{ext}"

    def join(self):
        if self._worker is not None:
            self._worker.cancel()
            return
        if len(self.clips) < 2:
            QMessageBox.warning(self, "Video Concat", tr("Pick at least two clips."))
            return
        unreadable = [c.path.name for c in self.clips if not c.ok]
        if unreadable:
            QMessageBox.warning(
                self, "Video Concat",
                tr("These files could not be read and would break the join:\n")
                + "\n".join(unreadable[:8]))
            return

        dest = self.destination()
        options = {
            "output": self.format_combo.currentText(),
            "size_mode": self.size_combo.currentText(),
            "fps": self.fps_spin.value(),
            "background": self._background_value(),
        }
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.result_label.setText("")
        self.join_btn.setText(tr("Cancel"))

        self._worker = _JoinWorker([c.path for c in self.clips], dest, options, self)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()
        self._update_enabled_state()

    def _on_done(self, path: str):
        size = Path(path).stat().st_size / (1024 * 1024)
        self.result_label.setText(tr("Wrote {name} ({mb:.1f} MB)").format(
            name=Path(path).name, mb=size))

    def _on_error(self, message: str):
        self.result_label.setText("")
        QMessageBox.critical(self, "Video Concat", message)

    def _on_finished(self):
        self._worker = None
        self.progress.setVisible(False)
        self.join_btn.setText(tr("🔗 Join"))
        self._update_enabled_state()

    # ── state ────────────────────────────────────────────────────────────
    def _apply_ffmpeg_state(self):
        if self._ffmpeg_ok:
            self._ffmpeg_hint.setText(tr("ffmpeg found — ready to convert."))
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.SUCCESS}; font-size: 10px;")
            self._install_ffmpeg_btn.setVisible(False)
        else:
            info = get_ffmpeg_install_info()
            self._ffmpeg_hint.setText(
                "ffmpeg not found — joining unavailable.\n"
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

    def _update_enabled_state(self):
        running = self._worker is not None
        ready = self._ffmpeg_ok and len(self.clips) >= 2
        self.join_btn.setEnabled(ready or running)
        for w in (self.add_btn, self.remove_btn, self.clear_btn,
                  self.up_btn, self.down_btn, self.format_combo,
                  self.size_combo, self.fps_spin, self.bg_combo, self.dest_btn):
            w.setEnabled(not running)

    # ── shutdown ─────────────────────────────────────────────────────────
    def _stop_thumb(self):
        if self._thumb is not None and self._thumb.isRunning():
            self._thumb.wait(5000)
        self._thumb = None

    def stop_workers(self, timeout_ms: int = 30000):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(timeout_ms)
            self._worker = None
        self._stop_thumb()

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
