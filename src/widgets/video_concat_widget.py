"""Video Concat — a library of material, a timeline that uses it, and a join.

Still not an editor: no tracks, no transitions, no effects. But two things a
join needs constantly turned out to be worth the room.

**The library is separate from the timeline.** Adding a file and using a file
are different acts. Keeping one list of material and a second list of uses means
a clip can appear on the timeline more than once — an intro reused as an outro,
one shot cut into before and after — which a single list of paths cannot express
at all.

**Segments carry their own in and out points.** Most clips need their head and
tail taken off before they will join cleanly, and doing that in another tool
first turns a one-step job into three. Trimming is per use, not per file, so the
same material can be cut differently in each place it appears.

The preview shows the scrubbed frame inside the frame the join will produce,
bars and all: whether a clip gets letterboxed is much easier to catch by eye
than to work out from a settings panel.
"""
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QListWidgetItem, QGroupBox, QComboBox,
                             QDoubleSpinBox, QProgressBar, QFileDialog, QMessageBox,
                             QAbstractItemView, QSizePolicy, QSplitter, QSlider)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
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
LIBRARY_ROW_MIME = "application/x-gifmaker-concat-library"

SCRUB_WIDTH = 480      # preview frames are only ever shown small
SCRUB_FRAMES = 120     # enough to land on a cut, few enough to hold in memory
SCRUB_CACHE = 4        # sources kept decoded, so flicking between clips is quick


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class LibraryList(QListWidget):
    """Drag source. Carries the row so the timeline knows what was dropped."""

    def mimeData(self, items):
        data = super().mimeData(items)
        if items:
            row = items[0].data(Qt.ItemDataRole.UserRole)
            if row is not None:
                data.setData(LIBRARY_ROW_MIME, str(row).encode("utf-8"))
        return data


class TimelineList(QListWidget):
    """Accepts material from the library and reordering from itself.

    Both drops are reported rather than performed. Qt's own drop handling edits
    the view's items, which would leave the view and the segment list saying
    different things; the owner moves the data and rebuilds instead.
    """

    library_dropped = pyqtSignal(int, int)     # library row, insert position
    segment_moved = pyqtSignal(int, int)       # from row, insert position

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def _accepts(self, event) -> bool:
        return (event.mimeData().hasFormat(LIBRARY_ROW_MIME)
                or event.source() is self)

    def dragEnterEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._accepts(event):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def _insert_row(self, pos) -> int:
        index = self.indexAt(pos)
        if not index.isValid():
            return self.count()
        rect = self.visualRect(index)
        return index.row() + (1 if pos.y() > rect.center().y() else 0)

    def dropEvent(self, event):
        pos = event.position().toPoint()
        at = self._insert_row(pos)
        mime = event.mimeData()
        if mime.hasFormat(LIBRARY_ROW_MIME):
            row = int(bytes(mime.data(LIBRARY_ROW_MIME)).decode("utf-8"))
            event.acceptProposedAction()
            self.library_dropped.emit(row, at)
        elif event.source() is self and self.currentRow() >= 0:
            event.acceptProposedAction()
            self.segment_moved.emit(self.currentRow(), at)
        else:
            super().dropEvent(event)


class _ScrubLoader(QThread):
    """Decodes a strip of frames spread across a source, for scrubbing."""
    done = pyqtSignal(str, list)
    failed = pyqtSignal(str)

    def __init__(self, path: Path, duration: float, parent=None):
        super().__init__(parent)
        self.path = path
        self.duration = duration

    def run(self):
        try:
            # Frames spread over the whole file, not the first few seconds:
            # the point of scrubbing is to find the cut, which is rarely at
            # the start.
            fps = (SCRUB_FRAMES / self.duration) if self.duration > 0 else 10.0
            frames = extract_preview_frames(
                str(self.path), fps=max(0.2, min(fps, 30.0)),
                max_width=SCRUB_WIDTH,
                max_duration=self.duration if self.duration > 0 else 10.0)
            if not frames:
                self.failed.emit(str(self.path))
                return
            self.done.emit(str(self.path), [img for img, _ms in frames])
        except Exception:
            self.failed.emit(str(self.path))


class _JoinWorker(QThread):
    progress = pyqtSignal(int)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, segments, destination, options: dict, parent=None):
        super().__init__(parent)
        self.segments = segments
        self.destination = destination
        self.options = options
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            out = concat.concat(self.segments, self.destination,
                                on_progress=self.progress.emit,
                                should_stop=lambda: self._cancelled,
                                **self.options)
            self.done.emit(out)
        except Exception as e:
            self.error.emit(str(e))


class VideoConcatWidget(QWidget):
    """Join GIFs and videos end to end, with per-use trimming."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library: List[Path] = []
        self.infos: Dict[str, dict] = {}
        self.segments: List[concat.Segment] = []
        self.last_dir = ""
        self.output_dir = ""
        self._scrub: Dict[str, List[Image.Image]] = {}
        self._scrub_order: List[str] = []
        self._loader: Optional[_ScrubLoader] = None
        self._worker: Optional[_JoinWorker] = None
        self._updating = False
        self._ffmpeg_ok = is_ffmpeg_available()
        self._init_ui()
        self._apply_ffmpeg_state()
        self._refresh_all()

    # ── UI ───────────────────────────────────────────────────────────────
    def _init_ui(self):
        layout = ui.tab_layout(self)
        layout.addWidget(self._create_left_panel())
        layout.addWidget(self._create_center_panel(), stretch=1)
        layout.addWidget(self._create_right_panel())

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setMaximumWidth(360)
        v = ui.panel_layout(panel)

        split = QSplitter(Qt.Orientation.Vertical)

        lib = QWidget()
        lv = QVBoxLayout(lib)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(ui.GAP_TIGHT)
        lv.addWidget(ui.title_label(tr("Library")))
        self.add_btn = QPushButton(tr("📂 Add Files…"))
        self.add_btn.clicked.connect(self.add_files)
        lv.addWidget(self.add_btn)
        self.library_list = LibraryList()
        self.library_list.setDragEnabled(True)
        self.library_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.library_list.itemDoubleClicked.connect(
            lambda _i: self.add_selected_to_timeline())
        lv.addWidget(self.library_list, stretch=1)
        lib_row = ui.row_layout()
        self.to_timeline_btn = QPushButton(tr("Add to Timeline ↓"))
        self.to_timeline_btn.clicked.connect(self.add_selected_to_timeline)
        lib_row.addWidget(self.to_timeline_btn)
        self.forget_btn = QPushButton(tr("Forget"))
        self.forget_btn.setToolTip(tr("Remove from the library. Segments already "
                                      "on the timeline are left alone."))
        self.forget_btn.clicked.connect(self.forget_selected)
        lib_row.addWidget(self.forget_btn)
        lv.addLayout(lib_row)
        lv.addWidget(ui.hint_label(
            tr("Double-click or drag a file onto the timeline.")))
        split.addWidget(lib)

        tl = QWidget()
        tv = QVBoxLayout(tl)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(ui.GAP_TIGHT)
        tv.addWidget(ui.title_label(tr("Timeline")))
        self.timeline_list = TimelineList()
        self.timeline_list.currentRowChanged.connect(self._on_segment_selected)
        self.timeline_list.library_dropped.connect(self._on_library_dropped)
        self.timeline_list.segment_moved.connect(self._on_segment_moved)
        tv.addWidget(self.timeline_list, stretch=1)

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
        self.remove_btn.clicked.connect(self.remove_segment)
        order.addWidget(self.remove_btn)
        self.clear_btn = QPushButton(tr("Clear"))
        self.clear_btn.clicked.connect(self.clear_timeline)
        order.addWidget(self.clear_btn)
        tv.addLayout(order)
        tv.addWidget(ui.hint_label(tr("Segments play top to bottom.")))
        split.addWidget(tl)

        split.setSizes([220, 340])
        v.addWidget(split, stretch=1)
        return panel

    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        v = ui.panel_layout(panel)

        self.preview = QLabel(tr("Add files, then build a timeline"))
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(320, 220)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self.preview.setStyleSheet(
            f"background-color: {_T.PANEL}; border: 1px solid {_T.BORDER}; "
            f"color: {_T.TEXT_DIM};")
        v.addWidget(self.preview, stretch=1)

        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.valueChanged.connect(self._on_scrub)
        v.addWidget(self.scrub)

        self.scrub_label = ui.hint_label("")
        self.scrub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.scrub_label)

        trim = QGroupBox(tr("Trim this segment"))
        tg = ui.group_layout()

        start_row = ui.row_layout()
        start_row.addWidget(ui.body_label(tr("Start")))
        self.start_spin = QDoubleSpinBox()
        self.start_spin.setDecimals(2)
        self.start_spin.setSuffix(" s")
        self.start_spin.setKeyboardTracking(False)
        self.start_spin.valueChanged.connect(self._on_trim_typed)
        start_row.addWidget(self.start_spin)
        self.set_start_btn = QPushButton(tr("Set from playhead"))
        self.set_start_btn.clicked.connect(lambda: self._set_from_scrub("start"))
        start_row.addWidget(self.set_start_btn)
        tg.addLayout(start_row)

        end_row = ui.row_layout()
        end_row.addWidget(ui.body_label(tr("End")))
        self.end_spin = QDoubleSpinBox()
        self.end_spin.setDecimals(2)
        self.end_spin.setSuffix(" s")
        self.end_spin.setKeyboardTracking(False)
        self.end_spin.valueChanged.connect(self._on_trim_typed)
        end_row.addWidget(self.end_spin)
        self.set_end_btn = QPushButton(tr("Set from playhead"))
        self.set_end_btn.clicked.connect(lambda: self._set_from_scrub("end"))
        end_row.addWidget(self.set_end_btn)
        tg.addLayout(end_row)

        self.reset_trim_btn = QPushButton(tr("Use the whole clip"))
        self.reset_trim_btn.clicked.connect(self.reset_trim)
        tg.addWidget(self.reset_trim_btn)

        self.trim_label = ui.body_label("")
        self.trim_label.setWordWrap(True)
        tg.addWidget(self.trim_label)

        trim.setLayout(tg)
        v.addWidget(trim)
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

        self.dest_btn = QPushButton(tr("Output Folder…"))
        self.dest_btn.clicked.connect(self.choose_output_folder)
        v.addWidget(self.dest_btn)
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

    # ── library ──────────────────────────────────────────────────────────
    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("Select Files"), self.last_dir, SUPPORTED)
        if paths:
            self.add_paths(paths)

    def add_paths(self, paths):
        added = 0
        for raw in paths:
            p = Path(raw)
            if p.suffix.lower() not in concat.INPUT_SUFFIXES or p in self.library:
                continue
            self.library.append(p)
            self.infos[str(p)] = concat.probe(p)
            added += 1
        if added:
            self.last_dir = str(Path(paths[0]).parent)
            self._refresh_library()
            if self.library_list.currentRow() < 0:
                self.library_list.setCurrentRow(0)
        return added

    def forget_selected(self):
        rows = sorted((self.library_list.row(i)
                       for i in self.library_list.selectedItems()), reverse=True)
        for row in rows:
            if 0 <= row < len(self.library):
                del self.library[row]
        self._refresh_library()

    def info_for(self, path: Path) -> dict:
        key = str(path)
        if key not in self.infos:
            self.infos[key] = concat.probe(path)
        return self.infos[key]

    def _library_label(self, path: Path) -> str:
        i = self.info_for(path)
        if not (i.get("width") and i.get("height")):
            return f"{path.name}   —   unreadable"
        bits = [f"{i['width']}×{i['height']}"]
        if i.get("duration"):
            bits.append(f"{i['duration']:.2f}s")
        if i.get("has_audio"):
            bits.append("sound")
        return f"{path.name}   —   {'  ·  '.join(bits)}"

    def _refresh_library(self):
        self.library_list.blockSignals(True)
        self.library_list.clear()
        for row, path in enumerate(self.library):
            item = QListWidgetItem(self._library_label(path))
            item.setData(Qt.ItemDataRole.UserRole, row)
            if not self.info_for(path).get("width"):
                item.setForeground(QColor(_T.ERROR))
            self.library_list.addItem(item)
        self.library_list.blockSignals(False)
        self._update_enabled_state()

    # ── timeline ─────────────────────────────────────────────────────────
    def add_selected_to_timeline(self, at: Optional[int] = None):
        rows = sorted(self.library_list.row(i)
                      for i in self.library_list.selectedItems())
        if not rows and self.library_list.currentRow() >= 0:
            rows = [self.library_list.currentRow()]
        insert = self.timeline_list.count() if at is None else at
        made = 0
        for row in rows:
            if not (0 <= row < len(self.library)):
                continue
            path = self.library[row]
            self.segments.insert(insert + made,
                                 concat.Segment(path, info=self.info_for(path)))
            made += 1
        if made:
            self._refresh_all()
            self.timeline_list.setCurrentRow(insert)
        return made

    def _on_library_dropped(self, row: int, at: int):
        self.library_list.setCurrentRow(row)
        self.library_list.clearSelection()
        self.library_list.item(row).setSelected(True)
        self.add_selected_to_timeline(at)

    def _on_segment_moved(self, source: int, at: int):
        if not (0 <= source < len(self.segments)):
            return
        seg = self.segments.pop(source)
        # Removing first shifts everything after it up by one.
        if at > source:
            at -= 1
        at = max(0, min(at, len(self.segments)))
        self.segments.insert(at, seg)
        self._refresh_all()
        self.timeline_list.setCurrentRow(at)

    def remove_segment(self):
        rows = sorted((self.timeline_list.row(i)
                       for i in self.timeline_list.selectedItems()), reverse=True)
        if not rows and self.timeline_list.currentRow() >= 0:
            rows = [self.timeline_list.currentRow()]
        for row in rows:
            if 0 <= row < len(self.segments):
                del self.segments[row]
        self._refresh_all()

    def clear_timeline(self):
        self.segments = []
        self._refresh_all()

    def _move(self, delta: int):
        row = self.timeline_list.currentRow()
        target = row + delta
        if not (0 <= row < len(self.segments) and 0 <= target < len(self.segments)):
            return
        self.segments[row], self.segments[target] = \
            self.segments[target], self.segments[row]
        self._refresh_all()
        self.timeline_list.setCurrentRow(target)

    def _refresh_timeline(self):
        current = self.timeline_list.currentRow()
        self.timeline_list.blockSignals(True)
        self.timeline_list.clear()
        for n, seg in enumerate(self.segments, 1):
            item = QListWidgetItem(f"{n}.  {seg.label()}")
            if not seg.info.get("width"):
                item.setForeground(QColor(_T.ERROR))
            self.timeline_list.addItem(item)
        self.timeline_list.blockSignals(False)
        if self.segments:
            self.timeline_list.setCurrentRow(
                min(max(current, 0), len(self.segments) - 1))

    def current_segment(self) -> Optional[concat.Segment]:
        row = self.timeline_list.currentRow()
        return self.segments[row] if 0 <= row < len(self.segments) else None

    # ── scrubbing and trimming ───────────────────────────────────────────
    def _on_segment_selected(self, _row: int):
        seg = self.current_segment()
        self._sync_trim_controls()
        if seg is None or not seg.info.get("width"):
            self._paint_preview()
            return
        key = str(seg.path)
        if key in self._scrub:
            self._apply_scrub_frames()
            return
        self._stop_loader()
        self._loader = _ScrubLoader(seg.path, seg.source_duration, self)
        self._loader.done.connect(self._on_scrub_ready)
        self._loader.failed.connect(lambda _p: self._paint_preview())
        self._loader.start()

    def _on_scrub_ready(self, path: str, frames: list):
        self._scrub[path] = frames
        self._scrub_order.append(path)
        while len(self._scrub_order) > SCRUB_CACHE:
            self._scrub.pop(self._scrub_order.pop(0), None)
        self._apply_scrub_frames()

    def _frames_for_current(self) -> List[Image.Image]:
        seg = self.current_segment()
        return self._scrub.get(str(seg.path), []) if seg else []

    def _apply_scrub_frames(self):
        frames = self._frames_for_current()
        self._updating = True
        try:
            self.scrub.setRange(0, max(0, len(frames) - 1))
            self.scrub.setValue(0)
        finally:
            self._updating = False
        self._paint_preview()

    def _scrub_time(self) -> float:
        """Where the playhead sits, in seconds of the source."""
        seg = self.current_segment()
        frames = self._frames_for_current()
        if seg is None or len(frames) < 2 or seg.source_duration <= 0:
            return 0.0
        return seg.source_duration * self.scrub.value() / (len(frames) - 1)

    def _on_scrub(self, _value: int):
        if not self._updating:
            self._paint_preview()

    def _set_from_scrub(self, which: str):
        seg = self.current_segment()
        if seg is None:
            return
        t = round(self._scrub_time(), 2)
        if which == "start":
            seg.start = min(t, max(0.0, seg.out_point - 0.01))
        else:
            seg.end = max(t, seg.start + 0.01)
        self._sync_trim_controls()
        self._refresh_all()

    def _on_trim_typed(self, _value: float):
        if self._updating:
            return
        seg = self.current_segment()
        if seg is None:
            return
        seg.start = self.start_spin.value()
        end = self.end_spin.value()
        # The spin sits at the source length when nothing is trimmed; storing 0
        # keeps "to the end" meaning exactly that rather than a hard number.
        seg.end = 0.0 if end >= seg.source_duration - 1e-6 else end
        if seg.duration <= 0:
            seg.start = max(0.0, seg.out_point - 0.01)
        self._refresh_all()

    def reset_trim(self):
        seg = self.current_segment()
        if seg is None:
            return
        seg.start, seg.end = 0.0, 0.0
        self._sync_trim_controls()
        self._refresh_all()

    def _sync_trim_controls(self):
        seg = self.current_segment()
        self._updating = True
        try:
            enabled = seg is not None and seg.source_duration > 0
            for w in (self.start_spin, self.end_spin, self.set_start_btn,
                      self.set_end_btn, self.reset_trim_btn, self.scrub):
                w.setEnabled(enabled and self._worker is None)
            if not enabled:
                self.start_spin.setValue(0.0)
                self.end_spin.setValue(0.0)
                self.trim_label.setText("")
                return
            span = seg.source_duration
            self.start_spin.setRange(0.0, span)
            self.end_spin.setRange(0.0, span)
            self.start_spin.setValue(seg.start)
            self.end_spin.setValue(seg.out_point)
        finally:
            self._updating = False
        self._update_trim_label()

    def _update_trim_label(self):
        seg = self.current_segment()
        if seg is None or seg.source_duration <= 0:
            self.trim_label.setText("")
            return
        if seg.trimmed:
            self.trim_label.setText(tr(
                "Using {used:.2f}s of {total:.2f}s").format(
                    used=seg.duration, total=seg.source_duration))
        else:
            self.trim_label.setText(tr("Whole clip — {total:.2f}s").format(
                total=seg.source_duration))

    # ── preview ──────────────────────────────────────────────────────────
    def current_plan(self) -> Optional[dict]:
        if not self.segments:
            return None
        try:
            return concat.plan(self.segments,
                               size_mode=self.size_combo.currentText(),
                               fps=self.fps_spin.value())
        except concat.ConcatError:
            return None

    def _paint_preview(self):
        plan = self.current_plan()
        frames = self._frames_for_current()
        seg = self.current_segment()
        if not frames or plan is None or seg is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(tr("Add files, then build a timeline")
                                 if not self.segments else tr("No preview"))
            self.scrub_label.setText("")
            return

        index = min(max(self.scrub.value(), 0), len(frames) - 1)
        src = frames[index]

        box_w, box_h = plan["width"], plan["height"]
        avail = self.preview.size()
        scale = min((avail.width() - 8) / box_w, (avail.height() - 8) / box_h, 1.0)
        vw, vh = max(1, int(box_w * max(scale, 0.05))), \
                 max(1, int(box_h * max(scale, 0.05)))

        canvas = QPixmap(vw, vh)
        canvas.fill(QColor(self._background_value()))
        fit = min(vw / src.width, vh / src.height)
        fw, fh = max(1, int(src.width * fit)), max(1, int(src.height * fit))
        painter = QPainter(canvas)
        painter.drawPixmap((vw - fw) // 2, (vh - fh) // 2,
                           _pil_to_pixmap(src.resize((fw, fh),
                                                     Image.Resampling.BILINEAR)))
        painter.end()
        self.preview.setPixmap(canvas)
        self.preview.setText("")

        t = self._scrub_time()
        inside = seg.start <= t <= seg.out_point
        row = self.timeline_list.currentRow()
        padded = plan["padded"][row] if 0 <= row < len(plan["padded"]) else False
        bits = [f"{t:.2f}s / {seg.source_duration:.2f}s",
                tr("kept") if inside else tr("trimmed away")]
        if padded:
            bits.append(tr("padded to fit"))
        self.scrub_label.setText("   ·   ".join(bits))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._paint_preview()

    # ── settings and summary ─────────────────────────────────────────────
    def _background_value(self) -> str:
        idx = max(0, self.bg_combo.currentIndex())
        return concat.BACKGROUND_PRESETS[idx][1]

    def _on_settings_changed(self, *_a):
        self._update_summary()
        self._paint_preview()

    def _refresh_all(self):
        self._refresh_timeline()
        self._update_trim_label()
        self._update_summary()
        self._paint_preview()

    def _update_summary(self):
        plan = self.current_plan()
        if plan is None or len(self.segments) < 2:
            self.recipe.setText(tr("Put at least two segments on the timeline."))
            self._update_enabled_state()
            return

        bits = [self.format_combo.currentText(),
                f"{plan['width']}×{plan['height']}",
                f"{plan['fps']:.4g} fps",
                f"{len(self.segments)} segments",
                f"{plan['duration']:.1f}s"]
        if plan["keep_audio"]:
            bits.append(tr("sound kept"))
        elif any(s.info.get("has_audio") for s in self.segments):
            bits.append(tr("sound dropped — not every clip has it"))
        padded = sum(1 for p in plan["padded"] if p)
        if padded:
            bits.append(tr("{n} padded").format(n=padded))
        trimmed = sum(1 for s in self.segments if s.trimmed)
        if trimmed:
            bits.append(tr("{n} trimmed").format(n=trimmed))
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
        if len(self.segments) < 2:
            return None
        ext = concat.extension_for(self.format_combo.currentText())
        first = self.segments[0].path
        folder = Path(self.output_dir) if self.output_dir else first.parent
        return folder / f"{first.stem}_joined.{ext}"

    def join(self):
        if self._worker is not None:
            self._worker.cancel()
            return
        if len(self.segments) < 2:
            QMessageBox.warning(self, "Video Concat",
                                tr("Put at least two segments on the timeline."))
            return
        broken = [s.path.name for s in self.segments if not s.info.get("width")]
        if broken:
            QMessageBox.warning(
                self, "Video Concat",
                tr("These files could not be read and would break the join:\n")
                + "\n".join(broken[:8]))
            return

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

        self._worker = _JoinWorker(list(self.segments), self.destination(),
                                   options, self)
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
        self._sync_trim_controls()
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
        ready = self._ffmpeg_ok and len(self.segments) >= 2
        self.join_btn.setEnabled(ready or running)
        for w in (self.add_btn, self.forget_btn, self.to_timeline_btn,
                  self.remove_btn, self.clear_btn, self.up_btn, self.down_btn,
                  self.format_combo, self.size_combo, self.fps_spin,
                  self.bg_combo, self.dest_btn):
            w.setEnabled(not running)

    # ── shutdown ─────────────────────────────────────────────────────────
    def _stop_loader(self):
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(5000)
        self._loader = None

    def stop_workers(self, timeout_ms: int = 30000):
        if self._worker is not None:
            self._worker.cancel()
            self._worker.wait(timeout_ms)
            self._worker = None
        self._stop_loader()

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
