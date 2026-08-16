"""Spine to GIF — load a Spine project, browse its animations, preview and export.

Two export engines:

* **SpineViewerCLI** (preferred when installed) shells out to
  https://github.com/ww-rm/SpineViewer, which bundles the official Spine
  runtimes 2.1-4.2 and its own ffmpeg. It exports straight to GIF/APNG/WebP/MP4,
  replacing the manual "render to MP4, then convert to GIF" round trip.
* **Built-in** uses this app's pure-Python runtime — no external dependency,
  but JSON-format Spine 4.x only.

The animation list is multi-select so a whole model can be exported in one go.
The scrubbable preview always uses the built-in renderer (a subprocess per
scrubbed frame would be far too slow); when the built-in runtime cannot parse a
model, export via the CLI still works and only the preview is unavailable.
"""
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QListWidget, QListWidgetItem, QGroupBox, QSpinBox,
                              QDoubleSpinBox, QComboBox, QCheckBox, QSlider, QFileDialog,
                              QMessageBox, QProgressBar, QSplitter, QSizePolicy,
                              QAbstractItemView)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from PIL import Image

from .. import settings as AppSettings
from ..i18n import tr
from ..core.gif_builder import GifBuilder
from ..core.spine import RenderSettings, SpineProject, SpineRenderer, load_project
from ..core.spine import cli_backend
from .theme import AppTheme as _T

PREVIEW_MAX = 460
ENGINE_CLI = "SpineViewerCLI"
ENGINE_BUILTIN = "Built-in"
CLI_PATH_SETTING = "spineviewer_cli_path"


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimg)
    del data
    return pixmap


class _LoadWorker(QThread):
    """Reads a model with the CLI (authoritative) and the built-in runtime (preview)."""
    done = pyqtSignal(object, object, str)   # SpineProject|None, ModelInfo|None, warning
    error = pyqtSignal(str)

    def __init__(self, skeleton_path: Path, cli_path: Optional[str], parent=None):
        super().__init__(parent)
        self.skeleton_path = skeleton_path
        self.cli_path = cli_path

    def run(self):
        info = None
        cli_error = ""
        if self.cli_path:
            try:
                info = cli_backend.query_model(self.skeleton_path, cli_path=self.cli_path)
            except Exception as e:
                cli_error = str(e)

        project = None
        builtin_error = ""
        try:
            project = load_project(self.skeleton_path)
        except Exception as e:
            builtin_error = str(e)

        if project is None and info is None:
            self.error.emit(builtin_error or cli_error or "Unknown error")
            return

        warning = ""
        if project is None:
            warning = ("Preview unavailable — the built-in renderer could not read this "
                       f"model ({builtin_error}). Export via SpineViewerCLI still works.")
        elif info is None and cli_error:
            warning = f"SpineViewerCLI query failed: {cli_error}"
        self.done.emit(project, info, warning)


class _PreviewWorker(QThread):
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, project, animation, time, settings, skin, parent=None):
        super().__init__(parent)
        self.project = project
        self.animation = animation
        self.time = time
        self.settings = settings
        self.skin = skin

    def run(self):
        try:
            self.project.skeleton.set_skin(self.skin)
            renderer = SpineRenderer(self.project)
            self.done.emit(renderer.render(self.animation, self.time, self.settings))
        except Exception as e:
            self.error.emit(str(e))


class _ExportWorker(QThread):
    """Exports one or many animations with the selected engine."""
    progress = pyqtSignal(int, int, str)   # done, total, current animation
    frame_progress = pyqtSignal(int, int)  # frame, total (built-in engine only)
    done = pyqtSignal(list, list)          # written paths, [(animation, error)]
    error = pyqtSignal(str)

    def __init__(self, *, engine, skeleton_path, project, animations, skin, outputs,
                 fps, scale, loop_count, transparent, colors, fmt, cli_path,
                 bounds, margin, max_resolution, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.skeleton_path = skeleton_path
        self.project = project
        self.animations = animations
        self.skin = skin
        self.outputs = outputs          # {animation: output path}
        self.fps = fps
        self.scale = scale
        self.loop_count = loop_count
        self.transparent = transparent
        self.colors = colors
        self.fmt = fmt
        self.cli_path = cli_path
        self.bounds = bounds
        self.margin = margin
        self.max_resolution = max_resolution
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        written: List[str] = []
        failures: List[tuple] = []
        total = len(self.animations)
        try:
            for i, anim in enumerate(self.animations):
                if self._cancelled:
                    break
                self.progress.emit(i, total, anim)
                try:
                    if self.engine == ENGINE_CLI:
                        self._export_with_cli(anim)
                    else:
                        self._export_with_builtin(anim)
                    written.append(self.outputs[anim])
                except Exception as e:
                    failures.append((anim, str(e)))
            self.progress.emit(total, total, "")
            self.done.emit(written, failures)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))

    def _export_with_cli(self, animation: str):
        options = cli_backend.ExportOptions(
            fmt=self.fmt,
            fps=self.fps,
            scale=self.scale,
            loop=self.loop_count == 0,
            skins=[self.skin] if self.skin else [],
            background=None if self.transparent else "#FFFFFFFF",
            margin=self.margin,
            max_resolution=self.max_resolution,
        )
        cli_backend.export_animation(
            self.skeleton_path, self.outputs[animation], [animation],
            options=options, cli_path=self.cli_path)

    def _export_with_builtin(self, animation: str):
        if self.project is None:
            raise RuntimeError("The built-in renderer could not read this model")
        self.project.skeleton.set_skin(self.skin)
        renderer = SpineRenderer(self.project)
        settings = RenderSettings(
            scale=self.scale,
            background=None if self.transparent else (255, 255, 255, 255),
            bounds=self.bounds)

        duration = self.project.animations[animation].duration
        frame_count = max(1, int(round(duration * self.fps)))
        frame_ms = int(round(1000.0 / self.fps))

        builder = GifBuilder()
        builder.set_loop(self.loop_count)
        builder.set_color_count(self.colors)
        if self.transparent:
            builder.set_background_color(0, 0, 0, 0)
        else:
            builder.set_background_color(255, 255, 255, 255)

        frames = []
        for i in range(frame_count):
            if self._cancelled:
                raise RuntimeError("Cancelled")
            t = (i / frame_count) * duration if frame_count > 1 else 0.0
            frames.append(builder._convert_frame_for_gif(
                renderer.render(animation, t, settings)))
            self.frame_progress.emit(i + 1, frame_count)

        builder.save_gif(frames, [frame_ms] * len(frames), self.outputs[animation])


class SpineToGifWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[SpineProject] = None
        self.model_info = None
        self.skeleton_path: Optional[Path] = None
        self.animations: Dict[str, float] = {}
        self.last_dir = ""
        self.last_export_dir = ""
        self._cached_bounds = None

        self.cli_path: Optional[str] = cli_backend.find_cli()

        self._load_worker: Optional[_LoadWorker] = None
        self._preview_worker: Optional[_PreviewWorker] = None
        self._export_worker: Optional[_ExportWorker] = None
        self._preview_pending = False

        self._preview_debounce = QTimer(self)
        self._preview_debounce.setSingleShot(True)
        self._preview_debounce.timeout.connect(self._render_preview)

        self._play_timer = QTimer(self)
        self._play_timer.timeout.connect(self._advance_playback)
        self._playing = False

        self._init_ui()
        self._refresh_engine_state()
        self._update_enabled_state()

    # ── UI ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_center_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([320, 660, 300])
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        title = QLabel(tr("Spine Project"))
        title.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {_T.TEXT}; padding: 4px 0;")
        v.addWidget(title)

        self.open_btn = QPushButton(tr("📂 Open Spine Project…"))
        self.open_btn.setToolTip("Choose a Spine skeleton file (.json or .skel)")
        self.open_btn.clicked.connect(self.open_project)
        v.addWidget(self.open_btn)

        self.project_label = QLabel(tr("No project loaded"))
        self.project_label.setWordWrap(True)
        self.project_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.project_label)

        skin_row = QHBoxLayout()
        skin_row.addWidget(QLabel(tr("Skin:")))
        self.skin_combo = QComboBox()
        self.skin_combo.currentTextChanged.connect(self._on_settings_changed)
        skin_row.addWidget(self.skin_combo, stretch=1)
        v.addLayout(skin_row)

        anim_header = QHBoxLayout()
        anim_label = QLabel(tr("Animations"))
        anim_label.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {_T.TEXT_DIM};")
        anim_header.addWidget(anim_label)
        anim_header.addStretch()
        self.select_all_btn = QPushButton(tr("Select All"))
        self.select_all_btn.setFixedHeight(22)
        self.select_all_btn.setToolTip("Select every animation for batch export")
        self.select_all_btn.clicked.connect(self.select_all_animations)
        anim_header.addWidget(self.select_all_btn)
        v.addLayout(anim_header)

        self.animation_list = QListWidget()
        # Multi-select is what turns this from a one-at-a-time chore into a batch job.
        self.animation_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.animation_list.currentRowChanged.connect(self._on_animation_selected)
        self.animation_list.itemSelectionChanged.connect(self._update_export_button_text)
        v.addWidget(self.animation_list, stretch=1)

        hint = QLabel(tr("Ctrl/Shift-click to select several, then export them all at once."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_T.TEXT_HINT}; font-size: 10px;")
        v.addWidget(hint)

        return panel

    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        self.preview_label = QLabel(tr("Open a Spine project to preview"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_label.setMinimumSize(320, 320)
        self.preview_label.setStyleSheet(
            f"background-color: {_T.CARD}; border: 1px solid {_T.BORDER}; border-radius: 4px;"
            f" color: {_T.TEXT_HINT};")
        v.addWidget(self.preview_label, stretch=1)

        controls = QHBoxLayout()
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(36)
        self.play_btn.setToolTip("Play / pause the preview")
        self.play_btn.clicked.connect(self.toggle_playback)
        controls.addWidget(self.play_btn)

        self.time_slider = QSlider(Qt.Orientation.Horizontal)
        self.time_slider.setMinimum(0)
        self.time_slider.setMaximum(0)
        self.time_slider.valueChanged.connect(self._on_time_changed)
        controls.addWidget(self.time_slider, stretch=1)

        self.time_label = QLabel("0.00s / 0.00s")
        self.time_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        controls.addWidget(self.time_label)
        v.addLayout(controls)

        self.preview_status = QLabel("")
        self.preview_status.setWordWrap(True)
        self.preview_status.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.preview_status)

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        engine_group = QGroupBox(tr("Export Engine"))
        eg = QVBoxLayout()
        self.engine_combo = QComboBox()
        self.engine_combo.addItems([ENGINE_CLI, ENGINE_BUILTIN])
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        eg.addWidget(self.engine_combo)

        self.engine_status = QLabel("")
        self.engine_status.setWordWrap(True)
        self.engine_status.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        eg.addWidget(self.engine_status)

        self.browse_cli_btn = QPushButton(tr("Locate SpineViewerCLI…"))
        self.browse_cli_btn.setFixedHeight(24)
        self.browse_cli_btn.clicked.connect(self.browse_for_cli)
        eg.addWidget(self.browse_cli_btn)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel(tr("Format:")))
        self.format_combo = QComboBox()
        self.format_combo.addItems(cli_backend.EXPORT_FORMATS)
        self.format_combo.setToolTip("SpineViewerCLI can export these directly")
        self.format_combo.currentTextChanged.connect(self._on_format_changed)
        fmt_row.addWidget(self.format_combo, stretch=1)
        eg.addLayout(fmt_row)

        engine_group.setLayout(eg)
        v.addWidget(engine_group)

        out_group = QGroupBox(tr("Export Settings"))
        form = QVBoxLayout()

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel(tr("FPS:")))
        self.fps_spinbox = QSpinBox()
        self.fps_spinbox.setRange(1, 60)
        self.fps_spinbox.setValue(24)
        self.fps_spinbox.valueChanged.connect(self._update_frame_estimate)
        fps_row.addWidget(self.fps_spinbox)
        fps_row.addStretch()
        form.addLayout(fps_row)

        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel(tr("Scale:")))
        self.scale_spinbox = QDoubleSpinBox()
        self.scale_spinbox.setRange(0.05, 2.0)
        self.scale_spinbox.setSingleStep(0.05)
        self.scale_spinbox.setValue(0.35)
        self.scale_spinbox.setDecimals(2)
        self.scale_spinbox.valueChanged.connect(self._update_frame_estimate)
        scale_row.addWidget(self.scale_spinbox)
        scale_row.addStretch()
        form.addLayout(scale_row)

        self.size_label = QLabel("")
        self.size_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        form.addWidget(self.size_label)

        self.tight_bounds_checkbox = QCheckBox(tr("Crop to animation"))
        self.tight_bounds_checkbox.setToolTip(
            "Built-in engine only: fit the canvas to what the animation actually "
            "covers instead of the skeleton's exported bounding box")
        self.tight_bounds_checkbox.toggled.connect(self._on_bounds_mode_changed)
        form.addWidget(self.tight_bounds_checkbox)

        self.transparent_checkbox = QCheckBox(tr("Transparent BG"))
        self.transparent_checkbox.setChecked(True)
        self.transparent_checkbox.toggled.connect(self._on_settings_changed)
        form.addWidget(self.transparent_checkbox)

        colors_row = QHBoxLayout()
        self.colors_label = QLabel(tr("Colors:"))
        colors_row.addWidget(self.colors_label)
        self.colors_combo = QComboBox()
        self.colors_combo.addItems(["256", "128", "64", "32", "16"])
        colors_row.addWidget(self.colors_combo)
        colors_row.addStretch()
        form.addLayout(colors_row)

        loop_row = QHBoxLayout()
        loop_row.addWidget(QLabel(tr("Loop:")))
        self.loop_spinbox = QSpinBox()
        self.loop_spinbox.setRange(0, 1000)
        self.loop_spinbox.setValue(0)
        self.loop_spinbox.setSpecialValueText("∞")
        loop_row.addWidget(self.loop_spinbox)
        loop_row.addStretch()
        form.addLayout(loop_row)

        out_group.setLayout(form)
        v.addWidget(out_group)

        self.estimate_label = QLabel("")
        self.estimate_label.setWordWrap(True)
        self.estimate_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.estimate_label)

        v.addStretch()

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        v.addWidget(self.progress_bar)

        self.export_btn = QPushButton(tr("💾 Export GIF"))
        self.export_btn.setStyleSheet(
            "font-weight: 600; font-size: 13px; background-color: #1f6b40; "
            "color: #c8f0d8; border: 1px solid #2d8a54; border-radius: 4px; padding: 6px 14px;")
        self.export_btn.clicked.connect(self.export_gif)
        v.addWidget(self.export_btn)

        self.cancel_btn = QPushButton(tr("Cancel"))
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_export)
        v.addWidget(self.cancel_btn)

        return panel

    # ── engine ───────────────────────────────────────────────────────────

    def _refresh_engine_state(self):
        """Pick a sane default engine and describe it in the UI."""
        self.cli_path = cli_backend.find_cli()
        has_cli = self.cli_path is not None
        self.engine_combo.blockSignals(True)
        if not has_cli and self.engine_combo.currentText() == ENGINE_CLI:
            self.engine_combo.setCurrentText(ENGINE_BUILTIN)
        elif has_cli:
            self.engine_combo.setCurrentText(ENGINE_CLI)
        self.engine_combo.blockSignals(False)

        if has_cli:
            self.engine_status.setText(f"Found: {self.cli_path}")
            self.engine_status.setStyleSheet(f"color: {_T.SUCCESS}; font-size: 10px;")
            self.browse_cli_btn.setText(tr("Change SpineViewerCLI path…"))
        else:
            self.engine_status.setText(
                "SpineViewerCLI not found — using the built-in renderer "
                "(JSON Spine 4.x only). Locate it to export any Spine version "
                "straight to GIF/MP4/WebP.")
            self.engine_status.setStyleSheet(f"color: {_T.WARNING}; font-size: 10px;")
            self.browse_cli_btn.setText(tr("Locate SpineViewerCLI…"))
        self._on_engine_changed(self.engine_combo.currentText())

    def _on_engine_changed(self, engine: str):
        using_cli = engine == ENGINE_CLI
        self.format_combo.setEnabled(using_cli)
        # Palette size is the built-in encoder's knob; the CLI generates its own
        # palette through ffmpeg.
        self.colors_combo.setEnabled(not using_cli)
        self.colors_label.setEnabled(not using_cli)
        # Framing is the built-in renderer's business; the CLI picks its own.
        self.tight_bounds_checkbox.setEnabled(not using_cli)
        self.tight_bounds_checkbox.setToolTip(
            "SpineViewerCLI chooses its own canvas, so this only affects the "
            "preview and the built-in engine."
            if using_cli else
            "Fit the canvas to what the animation actually covers instead of the "
            "skeleton's exported bounding box")
        self._cached_bounds = None
        self._update_export_button_text()
        self._update_frame_estimate()
        self._schedule_preview()

    def browse_for_cli(self):
        start = str(Path(self.cli_path).parent) if self.cli_path else ""
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Locate SpineViewerCLI"), start,
            f"{cli_backend.EXE_NAME} ({cli_backend.EXE_NAME});;All files (*)")
        if not file_path:
            return
        AppSettings.set(CLI_PATH_SETTING, file_path)
        self._refresh_engine_state()
        if self.cli_path:
            QMessageBox.information(self, "SpineViewerCLI",
                                    f"Using SpineViewerCLI at:\n{self.cli_path}")

    @property
    def engine(self) -> str:
        return self.engine_combo.currentText()

    # ── project loading ──────────────────────────────────────────────────

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open Spine Project"), self.last_dir,
            "Spine skeleton (*.json *.skel);;All files (*)")
        if not file_path:
            return
        self.load_project_file(Path(file_path))

    def load_project_file(self, path: Path):
        self.last_dir = str(path.parent)
        self.skeleton_path = path
        self.project_label.setText(tr("Loading…"))
        self.open_btn.setEnabled(False)
        self._load_worker = _LoadWorker(path, self.cli_path, self)
        self._load_worker.done.connect(self._on_project_loaded)
        self._load_worker.error.connect(self._on_project_error)
        self._load_worker.start()

    def _on_project_loaded(self, project, info, warning: str):
        self.open_btn.setEnabled(True)
        self.project = project
        self.model_info = info
        self._cached_bounds = None

        # The CLI's list is authoritative (it understands every Spine version).
        if info is not None and info.animations:
            self.animations = dict(info.animations)
            skins = info.skins
        elif project is not None:
            self.animations = {n: a.duration for n, a in project.animations.items()}
            skins = project.skin_names
        else:
            self.animations = {}
            skins = []

        name = self.skeleton_path.stem if self.skeleton_path else "?"
        if project is not None:
            sk = project.skeleton
            _, _, w, h = project.bounds()
            self.project_label.setText(
                f"{name}  ·  Spine {sk.spine_version}\n"
                f"{len(sk.bones)} bones, {len(sk.slots)} slots, {int(w)}×{int(h)}")
        else:
            self.project_label.setText(f"{name}  ·  {len(self.animations)} animations")

        self.skin_combo.blockSignals(True)
        self.skin_combo.clear()
        self.skin_combo.addItems(skins)
        self.skin_combo.blockSignals(False)

        self.animation_list.blockSignals(True)
        self.animation_list.clear()
        fps = self.fps_spinbox.value()
        for anim_name, duration in self.animations.items():
            frames = max(1, int(round(duration * fps)))
            item = QListWidgetItem(f"{anim_name}\n{duration:.2f}s · ~{frames} frames")
            item.setData(Qt.ItemDataRole.UserRole, anim_name)
            self.animation_list.addItem(item)
        self.animation_list.blockSignals(False)

        self.preview_status.setText(warning)
        self._update_enabled_state()
        if self.animation_list.count():
            self.animation_list.setCurrentRow(0)
        else:
            self._update_frame_estimate()
        self._update_export_button_text()

    def _on_project_error(self, message: str):
        self.open_btn.setEnabled(True)
        self.project = None
        self.model_info = None
        self.animations = {}
        self.animation_list.clear()
        self.project_label.setText(tr("No project loaded"))
        self._update_enabled_state()
        QMessageBox.critical(self, "Error", f"Failed to load Spine project:\n{message}")

    # ── animation selection / preview ────────────────────────────────────

    @property
    def current_animation(self) -> Optional[str]:
        item = self.animation_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_animations(self) -> List[str]:
        items = self.animation_list.selectedItems()
        if not items and self.animation_list.currentItem():
            items = [self.animation_list.currentItem()]
        return [i.data(Qt.ItemDataRole.UserRole) for i in items]

    def select_all_animations(self):
        self.animation_list.selectAll()

    def _update_export_button_text(self):
        count = len(self.selected_animations())
        fmt = self.format_combo.currentText() if self.engine == ENGINE_CLI else "GIF"
        if count > 1:
            self.export_btn.setText(tr("💾 Export {n} animations").replace("{n}", str(count)))
        else:
            self.export_btn.setText(f"💾 Export {fmt}")

    def _on_animation_selected(self, _row: int):
        self.pause_playback()
        self._cached_bounds = None
        anim_name = self.current_animation
        if not anim_name:
            return
        duration = self.animations.get(anim_name, 0.0)
        steps = max(1, int(round(duration * self.fps_spinbox.value())))
        self.time_slider.blockSignals(True)
        self.time_slider.setMaximum(steps)
        self.time_slider.setValue(0)
        self.time_slider.blockSignals(False)
        self._update_time_label()
        self._update_frame_estimate()
        self._schedule_preview()

    def _on_time_changed(self, _value: int):
        self._update_time_label()
        self._schedule_preview()

    def _on_settings_changed(self, *_):
        self._cached_bounds = None
        self._schedule_preview()

    def _on_bounds_mode_changed(self, _checked: bool):
        self._cached_bounds = None
        self._update_frame_estimate()
        self._schedule_preview()

    def _on_format_changed(self, _fmt: str):
        self._update_export_button_text()
        self._update_frame_estimate()

    def _current_time(self) -> float:
        anim = self.current_animation
        if not anim:
            return 0.0
        duration = self.animations.get(anim, 0.0)
        steps = max(self.time_slider.maximum(), 1)
        return duration * (self.time_slider.value() / steps)

    def _update_time_label(self):
        anim = self.current_animation
        if not anim:
            self.time_label.setText("0.00s / 0.00s")
            return
        self.time_label.setText(
            f"{self._current_time():.2f}s / {self.animations.get(anim, 0.0):.2f}s")

    def _render_bounds(self):
        """Framing for the preview and the built-in exporter.

        This does not try to mirror SpineViewerCLI's canvas: it picks its own,
        and matching it exactly needs a probe export that made selecting an
        animation take seconds. Cropping now happens in the Crop GIF tab, on the
        finished file, so the preview only has to be representative."""
        if self.project is None or not self.tight_bounds_checkbox.isChecked():
            return None
        if self._cached_bounds is None:
            renderer = SpineRenderer(self.project)
            self.project.skeleton.set_skin(self.skin_combo.currentText())
            self._cached_bounds = renderer.compute_bounds(self.current_animation)
        return self._cached_bounds

    def _schedule_preview(self):
        if self.project is None or not self.current_animation:
            return
        self._preview_debounce.start(60)

    def _render_preview(self):
        if self.project is None or not self.current_animation:
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            self._preview_pending = True
            return

        bounds = self._render_bounds()
        _, _, bw, bh = bounds if bounds is not None else self.project.bounds()
        scale = min(PREVIEW_MAX / max(bw, bh, 1), 1.0)

        settings = RenderSettings(
            scale=scale,
            background=None if self.transparent_checkbox.isChecked() else (255, 255, 255, 255),
            bounds=bounds)

        self.preview_status.setText(tr("Rendering…"))
        self._preview_worker = _PreviewWorker(
            self.project, self.current_animation, self._current_time(), settings,
            self.skin_combo.currentText(), self)
        self._preview_worker.done.connect(self._on_preview_done)
        self._preview_worker.error.connect(self._on_preview_error)
        self._preview_worker.start()

    def _on_preview_done(self, img: Image.Image):
        pixmap = _pil_to_pixmap(img)
        avail = self.preview_label.size()
        if pixmap.width() > avail.width() or pixmap.height() > avail.height():
            pixmap = pixmap.scaled(avail, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(pixmap)
        self.preview_status.setText(f"{img.width}×{img.height}")
        if self._preview_pending:
            self._preview_pending = False
            self._render_preview()

    def _on_preview_error(self, message: str):
        self.preview_status.setText(f"Preview failed: {message}")

    # ── playback ─────────────────────────────────────────────────────────

    def toggle_playback(self):
        self.pause_playback() if self._playing else self.play_playback()

    def play_playback(self):
        if self.project is None or not self.current_animation:
            return
        self._playing = True
        self.play_btn.setText("⏸")
        self._play_timer.start(int(1000 / max(self.fps_spinbox.value(), 1)))

    def pause_playback(self):
        self._playing = False
        self.play_btn.setText("▶")
        self._play_timer.stop()

    def _advance_playback(self):
        if self.time_slider.maximum() <= 0:
            return
        nxt = self.time_slider.value() + 1
        if nxt > self.time_slider.maximum():
            nxt = 0
        self.time_slider.setValue(nxt)

    # ── export ───────────────────────────────────────────────────────────

    def _update_frame_estimate(self):
        anim = self.current_animation
        if not anim:
            self.size_label.setText("")
            self.estimate_label.setText("")
            return
        duration = self.animations.get(anim, 0.0)
        fps = self.fps_spinbox.value()
        frames = max(1, int(round(duration * fps)))
        scale = self.scale_spinbox.value()

        if self.project is not None and self.engine == ENGINE_BUILTIN:
            bounds = self._render_bounds()
            _, _, bw, bh = bounds if bounds is not None else self.project.bounds()
            self.size_label.setText(f"Output: {int(bw * scale)}×{int(bh * scale)} px")
        else:
            # SpineViewerCLI decides its own canvas, so the exact size is only
            # known once it has run.
            self.size_label.setText(f"Scale ×{scale:.2f} (canvas chosen by the CLI)")

        if self.engine == ENGINE_CLI:
            self.estimate_label.setText(
                f"{frames} frames at {fps} fps, rendered by SpineViewerCLI "
                f"(official runtime, direct {self.format_combo.currentText()} output).")
        else:
            self.estimate_label.setText(
                f"{frames} frames at {fps} fps. The built-in renderer is CPU-bound, "
                f"so large scales take noticeably longer.")

        if self.time_slider.maximum() != frames:
            value = self.time_slider.value()
            old_max = max(self.time_slider.maximum(), 1)
            self.time_slider.blockSignals(True)
            self.time_slider.setMaximum(frames)
            self.time_slider.setValue(int(value / old_max * frames))
            self.time_slider.blockSignals(False)
            self._update_time_label()

    def _extension_for_format(self) -> str:
        if self.engine != ENGINE_CLI:
            return "gif"
        return {
            "Gif": "gif", "Apng": "png", "Webp": "webp", "Webpa": "webp",
            "Png": "png", "Frames": "", "Mp4": "mp4", "Mov": "mov",
            "Webm": "webm", "Mkv": "mkv",
        }.get(self.format_combo.currentText(), "gif")

    def export_gif(self):
        animations = self.selected_animations()
        if not animations or self.skeleton_path is None:
            QMessageBox.warning(self, "Warning", "Load a project and pick an animation first!")
            return
        if self.engine == ENGINE_CLI and not self.cli_path:
            QMessageBox.warning(self, "Warning", cli_backend.get_install_hint())
            return
        if self.engine == ENGINE_BUILTIN and self.project is None:
            QMessageBox.warning(self, "Warning",
                                "The built-in renderer cannot read this model. "
                                "Use SpineViewerCLI instead.")
            return

        ext = self._extension_for_format()
        model = self.skeleton_path.stem
        outputs: Dict[str, str] = {}

        if len(animations) == 1:
            default_name = f"{model}_{animations[0]}.{ext}" if ext else f"{model}_{animations[0]}"
            default_path = str(Path(self.last_export_dir or ".") / default_name)
            filter_str = f"{ext.upper()} Files (*.{ext})" if ext else "All files (*)"
            file_path, _ = QFileDialog.getSaveFileName(
                self, tr("Save"), default_path, filter_str)
            if not file_path:
                return
            if ext and not file_path.lower().endswith(f".{ext}"):
                file_path += f".{ext}"
            outputs[animations[0]] = file_path
            self.last_export_dir = str(Path(file_path).parent)
        else:
            # Batch: one folder, files named <model>_<animation>.<ext>
            directory = QFileDialog.getExistingDirectory(
                self, tr("Select Export Directory"), self.last_export_dir)
            if not directory:
                return
            self.last_export_dir = directory
            for anim in animations:
                safe = "".join(c for c in anim if c.isalnum() or c in " -_").strip() or anim
                name = f"{model}_{safe}.{ext}" if ext else f"{model}_{safe}"
                outputs[anim] = str(Path(directory) / name)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(len(animations))
        self.export_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

        self._export_worker = _ExportWorker(
            engine=self.engine,
            skeleton_path=self.skeleton_path,
            project=self.project,
            animations=animations,
            skin=self.skin_combo.currentText(),
            outputs=outputs,
            fps=self.fps_spinbox.value(),
            scale=self.scale_spinbox.value(),
            loop_count=self.loop_spinbox.value(),
            transparent=self.transparent_checkbox.isChecked(),
            colors=int(self.colors_combo.currentText()),
            fmt=self.format_combo.currentText(),
            cli_path=self.cli_path,
            bounds=self._render_bounds(),
            margin=0,
            max_resolution=4096,
            parent=self)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.frame_progress.connect(self._on_frame_progress)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_progress(self, current: int, total: int, animation: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        if animation:
            self.progress_bar.setFormat(f"{current}/{total} · {animation}")
        else:
            self.progress_bar.setFormat(f"{current}/{total}")

    def _on_frame_progress(self, frame: int, total: int):
        anim = self.progress_bar.format().split("·")[-1].strip()
        self.progress_bar.setFormat(f"{anim} — frame {frame}/{total}")

    def _finish_export(self):
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def _on_export_done(self, written: List[str], failures: List[tuple]):
        self._finish_export()
        if failures and not written:
            QMessageBox.critical(
                self, "Export failed",
                "\n".join(f"{a}: {e}" for a, e in failures[:8]))
            return
        message = f"Exported {len(written)} file(s)."
        if written:
            message += f"\n\nInto: {Path(written[0]).parent}"
        if failures:
            message += ("\n\nFailed:\n" +
                        "\n".join(f"  {a}: {e}" for a, e in failures[:5]))
        QMessageBox.information(self, "Export complete", message)

    def _on_export_error(self, message: str):
        self._finish_export()
        QMessageBox.critical(self, "Error", f"Export failed:\n{message}")

    def _cancel_export(self):
        if self._export_worker is not None:
            self._export_worker.cancel()

    # ── misc ─────────────────────────────────────────────────────────────

    def _update_enabled_state(self):
        has = bool(self.animations)
        for w in (self.skin_combo, self.animation_list, self.export_btn,
                  self.select_all_btn):
            w.setEnabled(has)
        can_preview = self.project is not None and has
        self.play_btn.setEnabled(can_preview)
        self.time_slider.setEnabled(can_preview)

    def stop_workers(self, timeout_ms: int = 30000):
        """Stop timers and wait for background work to finish.

        Qt aborts the process if a QThread is destroyed while still running, so
        this must run before the widget goes away."""
        self._preview_debounce.stop()
        self._play_timer.stop()
        self._playing = False
        if self._export_worker is not None:
            self._export_worker.cancel()
        for worker in (self._load_worker, self._preview_worker, self._export_worker):
            if worker is not None and worker.isRunning():
                worker.wait(timeout_ms)
        self._preview_pending = False

    def closeEvent(self, event):
        self.stop_workers()
        super().closeEvent(event)
