"""Spine to GIF — load a Spine project, browse its animations, preview and export.

Layout: [project + animation list] | [preview] | [export settings]

Rendering is CPU-bound, so both the preview and the export run on background
threads: the preview re-renders a single frame (debounced) while the export
walks the whole animation and reports progress.
"""
from pathlib import Path
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QListWidget, QListWidgetItem, QGroupBox, QSpinBox,
                              QDoubleSpinBox, QComboBox, QCheckBox, QSlider, QFileDialog,
                              QMessageBox, QProgressBar, QSplitter, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage

from PIL import Image

from ..i18n import tr
from ..core.gif_builder import GifBuilder
from ..core.spine import (RenderSettings, SpineLoadError, SpineProject, SpineRenderer,
                          find_project_files, load_project)
from .theme import AppTheme as _T

PREVIEW_MAX = 460


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimg)
    del data
    return pixmap


class _LoadWorker(QThread):
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, skeleton_path: Path, parent=None):
        super().__init__(parent)
        self.skeleton_path = skeleton_path

    def run(self):
        try:
            self.done.emit(load_project(self.skeleton_path))
        except Exception as e:
            self.error.emit(str(e))


class _PreviewWorker(QThread):
    """Renders one frame off the UI thread."""
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
    progress = pyqtSignal(int, int)   # current, total
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, project, animation, skin, fps, settings, output_path,
                 loop_count, color_count, transparent, parent=None):
        super().__init__(parent)
        self.project = project
        self.animation = animation
        self.skin = skin
        self.fps = fps
        self.settings = settings
        self.output_path = output_path
        self.loop_count = loop_count
        self.color_count = color_count
        self.transparent = transparent
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.project.skeleton.set_skin(self.skin)
            renderer = SpineRenderer(self.project)
            anim = self.project.animations[self.animation]
            duration = anim.duration
            frame_count = max(1, int(round(duration * self.fps)))
            frame_ms = int(round(1000.0 / self.fps))

            builder = GifBuilder()
            builder.set_loop(self.loop_count)
            builder.set_color_count(self.color_count)
            if self.transparent:
                builder.set_background_color(0, 0, 0, 0)
            else:
                builder.set_background_color(255, 255, 255, 255)

            frames = []
            for i in range(frame_count):
                if self._cancelled:
                    self.error.emit("Export cancelled")
                    return
                t = (i / frame_count) * duration if frame_count > 1 else 0.0
                img = renderer.render(self.animation, t, self.settings)
                frames.append(builder._convert_frame_for_gif(img))
                self.progress.emit(i + 1, frame_count)

            builder.save_gif(frames, [frame_ms] * len(frames), self.output_path)
            self.done.emit(self.output_path)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error.emit(str(e))


class SpineToGifWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Optional[SpineProject] = None
        self.project_path: Optional[Path] = None
        self.last_dir = ""
        self.last_export_dir = ""

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
        self._update_enabled_state()

    # ── UI ───────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._create_left_panel())
        splitter.addWidget(self._create_center_panel())
        splitter.addWidget(self._create_right_panel())
        splitter.setSizes([300, 700, 280])
        layout.addWidget(splitter)

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

        title = QLabel(tr("Spine Project"))
        title.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {_T.TEXT}; padding: 4px 0;")
        v.addWidget(title)

        self.open_btn = QPushButton(tr("📂 Open Spine Project…"))
        self.open_btn.setToolTip("Choose a Spine skeleton .json (its .atlas and .png must sit beside it)")
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

        anim_label = QLabel(tr("Animations"))
        anim_label.setStyleSheet(f"font-weight: 600; font-size: 12px; color: {_T.TEXT_DIM}; padding-top: 6px;")
        v.addWidget(anim_label)

        self.animation_list = QListWidget()
        self.animation_list.currentRowChanged.connect(self._on_animation_selected)
        v.addWidget(self.animation_list, stretch=1)

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
        self.preview_status.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        v.addWidget(self.preview_status)

        return panel

    def _create_right_panel(self) -> QWidget:
        panel = QWidget()
        v = QVBoxLayout(panel)

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
            "Fit the canvas to what the animation actually covers instead of the "
            "skeleton's exported bounding box")
        self.tight_bounds_checkbox.toggled.connect(self._on_bounds_mode_changed)
        form.addWidget(self.tight_bounds_checkbox)

        self.transparent_checkbox = QCheckBox(tr("Transparent BG"))
        self.transparent_checkbox.setChecked(True)
        self.transparent_checkbox.toggled.connect(self._on_settings_changed)
        form.addWidget(self.transparent_checkbox)

        colors_row = QHBoxLayout()
        colors_row.addWidget(QLabel(tr("Colors:")))
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

    # ── project loading ──────────────────────────────────────────────────

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open Spine Project"), self.last_dir,
            "Spine skeleton (*.json);;All files (*)")
        if not file_path:
            return
        self.load_project_file(Path(file_path))

    def load_project_file(self, path: Path):
        self.last_dir = str(path.parent)
        self.project_label.setText(tr("Loading…"))
        self.open_btn.setEnabled(False)
        self._load_worker = _LoadWorker(path, self)
        self._load_worker.done.connect(self._on_project_loaded)
        self._load_worker.error.connect(self._on_project_error)
        self._load_worker.start()

    def _on_project_loaded(self, project: SpineProject):
        self.open_btn.setEnabled(True)
        self.project = project
        self.project_path = project.directory / f"{project.name}.json"

        x, y, w, h = project.bounds()
        self.project_label.setText(
            f"{project.name}  ·  Spine {project.skeleton.spine_version}\n"
            f"{len(project.skeleton.bones)} bones, {len(project.skeleton.slots)} slots, "
            f"{int(w)}×{int(h)}")

        self.skin_combo.blockSignals(True)
        self.skin_combo.clear()
        self.skin_combo.addItems(project.skin_names)
        self.skin_combo.blockSignals(False)

        self.animation_list.blockSignals(True)
        self.animation_list.clear()
        fps = self.fps_spinbox.value()
        for name, anim in project.animations.items():
            frames = max(1, int(round(anim.duration * fps)))
            item = QListWidgetItem(f"{name}\n{anim.duration:.2f}s · ~{frames} frames")
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.animation_list.addItem(item)
        self.animation_list.blockSignals(False)

        self._cached_bounds = None
        self._update_enabled_state()
        if self.animation_list.count():
            self.animation_list.setCurrentRow(0)
        else:
            self._update_frame_estimate()

    def _on_project_error(self, message: str):
        self.open_btn.setEnabled(True)
        self.project_label.setText(tr("No project loaded"))
        QMessageBox.critical(self, "Error", f"Failed to load Spine project:\n{message}")

    # ── animation selection / preview ────────────────────────────────────

    @property
    def current_animation(self) -> Optional[str]:
        item = self.animation_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_animation_selected(self, _row: int):
        self.pause_playback()
        self._cached_bounds = None
        anim_name = self.current_animation
        if not anim_name or self.project is None:
            return
        duration = self.project.animations[anim_name].duration
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

    def _current_time(self) -> float:
        if self.project is None or not self.current_animation:
            return 0.0
        duration = self.project.animations[self.current_animation].duration
        steps = max(self.time_slider.maximum(), 1)
        return duration * (self.time_slider.value() / steps)

    def _update_time_label(self):
        if self.project is None or not self.current_animation:
            self.time_label.setText("0.00s / 0.00s")
            return
        duration = self.project.animations[self.current_animation].duration
        self.time_label.setText(f"{self._current_time():.2f}s / {duration:.2f}s")

    def _render_bounds(self):
        """Bounding box to frame with, honouring the 'crop to animation' option."""
        if self.project is None:
            return None
        if not self.tight_bounds_checkbox.isChecked():
            return None
        if getattr(self, "_cached_bounds", None) is None:
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
        if bounds is not None:
            _, _, bw, bh = bounds
        else:
            _, _, bw, bh = self.project.bounds()
        scale = PREVIEW_MAX / max(bw, bh, 1)
        scale = min(scale, 1.0)

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
        if self.project is None or not self.current_animation:
            self.size_label.setText("")
            self.estimate_label.setText("")
            return
        anim = self.project.animations[self.current_animation]
        fps = self.fps_spinbox.value()
        frames = max(1, int(round(anim.duration * fps)))
        bounds = self._render_bounds()
        if bounds is not None:
            _, _, bw, bh = bounds
        else:
            _, _, bw, bh = self.project.bounds()
        scale = self.scale_spinbox.value()
        self.size_label.setText(f"Output: {int(bw * scale)}×{int(bh * scale)} px")
        self.estimate_label.setText(
            f"{frames} frames at {fps} fps. Rendering is CPU-bound — larger scales "
            f"take noticeably longer.")
        # Keep the scrubber resolution in step with fps.
        if self.time_slider.maximum() != frames:
            value = self.time_slider.value()
            old_max = max(self.time_slider.maximum(), 1)
            self.time_slider.blockSignals(True)
            self.time_slider.setMaximum(frames)
            self.time_slider.setValue(int(value / old_max * frames))
            self.time_slider.blockSignals(False)
            self._update_time_label()

    def export_gif(self):
        if self.project is None or not self.current_animation:
            QMessageBox.warning(self, "Warning", "Load a project and pick an animation first!")
            return

        default_name = f"{self.project.name}_{self.current_animation}.gif"
        default_path = str(Path(self.last_export_dir or ".") / default_name)
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Save GIF"), default_path, "GIF Files (*.gif)")
        if not file_path:
            return
        if not file_path.lower().endswith(".gif"):
            file_path += ".gif"
        self.last_export_dir = str(Path(file_path).parent)

        settings = RenderSettings(
            scale=self.scale_spinbox.value(),
            background=None if self.transparent_checkbox.isChecked() else (255, 255, 255, 255),
            bounds=self._render_bounds())

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.export_btn.setEnabled(False)
        self.cancel_btn.setVisible(True)

        self._export_worker = _ExportWorker(
            self.project, self.current_animation, self.skin_combo.currentText(),
            self.fps_spinbox.value(), settings, file_path,
            self.loop_spinbox.value(), int(self.colors_combo.currentText()),
            self.transparent_checkbox.isChecked(), self)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.error.connect(self._on_export_error)
        self._export_worker.start()

    def _on_export_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Rendering frame {current}/{total}")

    def _finish_export(self):
        self.progress_bar.setVisible(False)
        self.export_btn.setEnabled(True)
        self.cancel_btn.setVisible(False)

    def _on_export_done(self, path: str):
        self._finish_export()
        QMessageBox.information(self, "Success", f"GIF exported to:\n{path}")

    def _on_export_error(self, message: str):
        self._finish_export()
        QMessageBox.critical(self, "Error", f"Export failed:\n{message}")

    def _cancel_export(self):
        if self._export_worker is not None:
            self._export_worker.cancel()

    # ── misc ─────────────────────────────────────────────────────────────

    def _update_enabled_state(self):
        has = self.project is not None
        for w in (self.skin_combo, self.animation_list, self.play_btn, self.time_slider,
                  self.export_btn):
            w.setEnabled(has)

    def stop_workers(self, timeout_ms: int = 30000):
        """Stop timers and wait for background renders to finish.

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
