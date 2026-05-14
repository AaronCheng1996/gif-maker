"""Clip to GIF – extract a specific time range from a single video as a GIF.

Layout:
  Left   – file selector, conversion settings, export
  Middle – visual TimeRangeSlider + scrub bar + static frame preview
  Right  – animated output GIF preview
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import (
    QPoint, QRect, QRectF, Qt, QThread, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient,
    QMouseEvent, QPainter, QPainterPath, QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QSlider, QSpinBox, QSplitter,
    QVBoxLayout, QWidget,
)

from ..core.video_to_gif import (
    VideoConversionError,
    convert_to_gif,
    extract_preview_frames,
    get_ffmpeg_install_info,
    get_video_info,
    is_ffmpeg_available,
    find_ffmpeg,
)
from .theme import AppTheme as _T


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt_size(byte_count: int) -> str:
    kb = byte_count / 1024
    return f"{kb / 1024:.2f} MB" if kb >= 1000 else f"{kb:.2f} KB"


def _fmt_time(seconds: float) -> str:
    """Format seconds as M:SS.s or SS.s."""
    if seconds < 0:
        seconds = 0.0
    m = int(seconds) // 60
    s = seconds - m * 60
    return f"{m}:{s:04.1f}" if m > 0 else f"{s:.1f}s"


_VIDEO_FILTER = (
    "Video & Animated Files ("
    "*.mp4 *.mov *.avi *.mkv *.webm *.flv *.wmv *.m4v *.ts *.3gp *.mts "
    "*.webp *.gif *.apng"
    ")"
)

# ── Colours ────────────────────────────────────────────────────────────────────
_TRACK_BG     = QColor(45, 50, 68)
_TRACK_FILL   = QColor(99, 149, 255, 180)
_HANDLE_IDLE  = QColor(160, 190, 255)
_HANDLE_HOVER = QColor(200, 220, 255)
_HANDLE_DRAG  = QColor(255, 255, 255)
_HDL_BORDER   = QColor(70, 100, 200)
_LABEL_COL    = QColor(170, 185, 215)
_TICK_COL     = QColor(90, 100, 130)
_SCRUB_LINE   = QColor(255, 200, 80)


# ── PIL → QPixmap ──────────────────────────────────────────────────────────────

def _pil_to_pixmap(img) -> QPixmap:
    """Convert a PIL Image to QPixmap (lossless, handles RGBA/RGB)."""
    from PIL import Image as _Img
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimg = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


# ── TimeRangeSlider ────────────────────────────────────────────────────────────

class TimeRangeSlider(QWidget):
    """Dual-handle slider for selecting a video time range.

    Emits ``range_changed(start, end)`` whenever a handle moves.
    Emits ``scrub_requested(t)`` when the user clicks the track (not a handle)
    so callers can jump the preview frame.
    """

    range_changed   = pyqtSignal(float, float)  # (start_s, end_s)
    scrub_requested = pyqtSignal(float)          # single time position

    _R       = 9     # handle radius
    _TRACK_H = 10    # track bar height
    _LABEL_H = 22    # vertical space below track for labels
    _MX      = 14    # horizontal margin

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration: float = 0.0
        self._start:    float = 0.0
        self._end:      float = 0.0
        self._scrub:    float = 0.0   # position of the visual scrub indicator

        self._dragging: Optional[str] = None   # "start" | "end" | None
        self._hover:    Optional[str] = None

        self.setMinimumHeight(56)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    # ── Public ─────────────────────────────────────────────────────────────────

    def set_duration(self, duration: float):
        self._duration = max(0.0, duration)
        self._start = 0.0
        self._end   = self._duration
        self._scrub = 0.0
        self.update()

    def set_range(self, start: float, end: float):
        if self._duration <= 0:
            return
        self._start = max(0.0, min(start, self._duration))
        self._end   = max(self._start, min(end, self._duration))
        self.update()

    def set_scrub(self, t: float):
        self._scrub = max(0.0, min(t, self._duration))
        self.update()

    @property
    def start_time(self) -> float:
        return self._start

    @property
    def end_time(self) -> float:
        return self._end

    # ── Geometry ───────────────────────────────────────────────────────────────

    def _track_rect(self) -> QRect:
        cy = (self.height() - self._LABEL_H) // 2
        h  = self._TRACK_H
        return QRect(self._MX, cy - h // 2, self.width() - 2 * self._MX, h)

    def _time_to_x(self, t: float) -> int:
        tr = self._track_rect()
        if self._duration <= 0:
            return tr.left()
        frac = max(0.0, min(1.0, t / self._duration))
        return int(tr.left() + frac * tr.width())

    def _x_to_time(self, x: int) -> float:
        tr = self._track_rect()
        if tr.width() <= 0 or self._duration <= 0:
            return 0.0
        frac = max(0.0, min(1.0, (x - tr.left()) / tr.width()))
        return frac * self._duration

    def _handle_rect(self, name: str) -> QRect:
        t  = self._start if name == "start" else self._end
        cx = self._time_to_x(t)
        cy = self._track_rect().center().y()
        return QRect(cx - self._R, cy - self._R, 2 * self._R, 2 * self._R)

    def _hit_handle(self, pos: QPoint) -> Optional[str]:
        inflate = 5
        for name in ("start", "end"):
            if self._handle_rect(name).adjusted(-inflate, -inflate, inflate, inflate).contains(pos):
                return name
        return None

    # ── Paint ──────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tr = self._track_rect()

        # Track background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_TRACK_BG))
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(tr), tr.height() / 2, tr.height() / 2)
        p.drawPath(bg_path)

        # Selected range fill
        if self._duration > 0:
            sx = self._time_to_x(self._start)
            ex = self._time_to_x(self._end)
            fr = QRect(sx, tr.top(), max(0, ex - sx), tr.height())
            if fr.width() > 0:
                grad = QLinearGradient(fr.left(), 0, fr.right(), 0)
                grad.setColorAt(0, QColor(80, 130, 255, 200))
                grad.setColorAt(1, QColor(130, 170, 255, 200))
                p.setBrush(QBrush(grad))
                fp = QPainterPath()
                fp.addRoundedRect(QRectF(fr), tr.height() / 2, tr.height() / 2)
                p.drawPath(fp)

        # Tick marks
        if self._duration > 0:
            p.setPen(QPen(_TICK_COL, 1))
            self._draw_ticks(p, tr)

        # Scrub position indicator
        if self._duration > 0:
            sx2 = self._time_to_x(self._scrub)
            p.setPen(QPen(_SCRUB_LINE, 1.5, Qt.PenStyle.DotLine))
            p.drawLine(sx2, tr.top() - 3, sx2, tr.bottom() + 3)

        # Handles
        for name in ("start", "end"):
            self._draw_handle(p, name)

        # Labels below track
        if self._duration > 0:
            label_y = tr.bottom() + 3
            font = QFont()
            font.setPointSize(8)
            p.setFont(font)

            # Start label
            s_x = self._time_to_x(self._start)
            p.setPen(QPen(QColor(120, 170, 255)))
            p.drawText(s_x - 22, label_y, 46, self._LABEL_H,
                       Qt.AlignmentFlag.AlignCenter, _fmt_time(self._start))

            # End label (only if far enough)
            e_x = self._time_to_x(self._end)
            if e_x - s_x > 52:
                p.drawText(e_x - 22, label_y, 46, self._LABEL_H,
                           Qt.AlignmentFlag.AlignCenter, _fmt_time(self._end))

            # Total duration at right edge
            p.setPen(QPen(_TICK_COL))
            p.drawText(tr.right() - 34, label_y, 36, self._LABEL_H,
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _fmt_time(self._duration))

        p.end()

    def _draw_ticks(self, p: QPainter, tr: QRect):
        intervals = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600]
        interval = intervals[-1]
        for iv in intervals:
            if self._duration / iv <= 20:
                interval = iv
                break
        t = interval
        while t < self._duration:
            x = self._time_to_x(t)
            tick_h = 5 if (round(t / interval) % 5 == 0) else 3
            p.drawLine(x, tr.bottom() - tick_h, x, tr.bottom())
            t += interval

    def _draw_handle(self, p: QPainter, name: str):
        r  = self._handle_rect(name)
        cx, cy = r.center().x(), r.center().y()
        radius = self._R

        color = (
            _HANDLE_DRAG  if self._dragging == name else
            _HANDLE_HOVER if self._hover    == name else
            _HANDLE_IDLE
        )

        # Shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QPoint(cx + 1, cy + 1), radius, radius)

        # Fill + border
        p.setPen(QPen(_HDL_BORDER, 1.5))
        p.setBrush(QBrush(color))
        p.drawEllipse(QPoint(cx, cy), radius, radius)

        # Inner dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(_HDL_BORDER))
        p.drawEllipse(QPoint(cx, cy), 2, 2)

    # ── Mouse ──────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._duration > 0:
            hit = self._hit_handle(event.pos())
            if hit:
                self._dragging = hit
            else:
                t = self._x_to_time(event.pos().x())
                # Snap nearest handle
                self._dragging = (
                    "start" if abs(t - self._start) <= abs(t - self._end)
                    else "end"
                )
                self._move_handle(self._dragging, event.pos().x())
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):  # noqa: N802
        if self._dragging:
            self._move_handle(self._dragging, event.pos().x())
            self.update()
        else:
            prev = self._hover
            self._hover = self._hit_handle(event.pos())
            if self._hover != prev:
                self.update()
                self.setCursor(
                    Qt.CursorShape.SizeHorCursor
                    if self._hover else Qt.CursorShape.ArrowCursor
                )

    def mouseReleaseEvent(self, event: QMouseEvent):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = None
            self.update()

    def _move_handle(self, handle: str, x: int):
        t = self._x_to_time(x)
        if handle == "start":
            self._start = max(0.0, min(t, self._end - 0.05))
            self._scrub = self._start
        else:
            self._end = max(self._start + 0.05, min(t, self._duration))
            self._scrub = self._end
        self.range_changed.emit(self._start, self._end)
        self.scrub_requested.emit(self._scrub)


# ── Background workers ─────────────────────────────────────────────────────────

class _FrameExtractWorker(QThread):
    """Extract a single frame at a specific timestamp for the scrub preview."""
    done  = pyqtSignal(object)   # PIL.Image (RGBA)
    error = pyqtSignal(str)

    def __init__(self, path: str, timestamp: float, parent=None):
        super().__init__(parent)
        self._path      = path
        self._timestamp = timestamp

    def run(self):
        try:
            frames = extract_preview_frames(
                self._path,
                fps=4.0,
                max_width=800,
                max_duration=0.4,
                start_time=max(0.0, self._timestamp),
                end_time=self._timestamp + 0.4,
            )
            if frames:
                self.done.emit(frames[0][0])
            else:
                self.error.emit("No frame extracted")
        except Exception as e:
            self.error.emit(str(e))


class _CancellablePreviewWorker(QThread):
    """Two-pass ffmpeg GIF conversion that can be killed mid-run.

    Uses subprocess.Popen so the OS process can be killed via cancel().
    Emits progress messages for each phase, and silently stops on cancel.
    """
    done     = pyqtSignal(str)   # output GIF path
    error    = pyqtSignal(str)
    progress = pyqtSignal(str)   # status text for display

    def __init__(self, src, fps, width, start_t, end_t, colors, dither, lossy,
                 parent=None):
        super().__init__(parent)
        self._src    = src
        self._fps    = fps
        self._width  = width
        self._start  = start_t
        self._end    = end_t
        self._colors = colors
        self._dither = dither
        self._lossy  = lossy
        self._tmp:  Optional[str]              = None
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._lock = threading.Lock()

    def cancel(self):
        """Kill the running ffmpeg process and flag as cancelled."""
        self._cancelled = True
        with self._lock:
            if self._proc is not None:
                try:
                    self._proc.kill()
                except OSError:
                    pass

    def _run_cmd(self, cmd: list[str]):
        """Run one ffmpeg command via Popen; raises InterruptedError if cancelled."""
        if self._cancelled:
            raise InterruptedError()
        with self._lock:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        proc = self._proc
        _out, _err = proc.communicate()
        with self._lock:
            self._proc = None
        if self._cancelled:
            raise InterruptedError()
        if proc.returncode != 0:
            raise VideoConversionError(
                f"{cmd[0]} failed (code {proc.returncode}): "
                f"{_err.decode(errors='ignore').strip()}"
            )

    def run(self):
        try:
            ffmpeg_exe = find_ffmpeg()
            if ffmpeg_exe is None:
                raise VideoConversionError("ffmpeg not found")

            fps    = max(1.0, min(60.0, self._fps))
            colors = max(2, min(256, self._colors))

            input_args: list[str] = []
            if self._start > 0:
                input_args += ["-ss", str(self._start)]
            if self._end > 0 and self._end > self._start:
                input_args += ["-t", str(self._end - self._start)]

            scale = f",scale={self._width}:-2:flags=lanczos" if self._width > 0 else ""

            if self._dither == "bayer":
                dither_opts = "dither=bayer:bayer_scale=5:diff_mode=rectangle"
            elif self._dither == "none":
                dither_opts = "dither=none:diff_mode=rectangle"
            else:
                dither_opts = f"dither={self._dither}:diff_mode=rectangle"

            f = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
            f.close()
            self._tmp = f.name

            with tempfile.TemporaryDirectory() as tmpdir:
                palette = str(Path(tmpdir) / "palette.png")
                tmp_gif = str(Path(tmpdir) / "out.gif")

                # Pass 1 – palette
                self.progress.emit("Pass 1/2: Generating palette…")
                self._run_cmd([
                    ffmpeg_exe, *input_args, "-i", self._src,
                    "-vf", f"fps={fps}{scale},palettegen=max_colors={colors}:stats_mode=diff",
                    "-y", palette,
                ])

                # Pass 2 – encode
                self.progress.emit("Pass 2/2: Encoding GIF…")
                self._run_cmd([
                    ffmpeg_exe, *input_args, "-i", self._src, "-i", palette,
                    "-filter_complex",
                    f"[0:v]fps={fps}{scale}[x];[x][1:v]paletteuse={dither_opts}",
                    "-y", tmp_gif,
                ])

                # Optional gifsicle lossy pass
                if self._lossy > 0 and shutil.which("gifsicle"):
                    self.progress.emit("Optimising with gifsicle…")
                    try:
                        subprocess.run(
                            ["gifsicle", f"--lossy={self._lossy}", "-O3",
                             tmp_gif, "-o", tmp_gif],
                            check=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        )
                    except subprocess.CalledProcessError:
                        pass  # best-effort

                shutil.move(tmp_gif, self._tmp)

            self.done.emit(self._tmp)

        except InterruptedError:
            self._cleanup_tmp()
            # Silently swallow – cancel() caller handles UI update

        except Exception as e:
            self._cleanup_tmp()
            self.error.emit(str(e))

    def _cleanup_tmp(self):
        if self._tmp and os.path.exists(self._tmp):
            try:
                os.unlink(self._tmp)
            except OSError:
                pass
        self._tmp = None


# ── Smart-loop worker ─────────────────────────────────────────────────────────

def _extract_candidates(
    path: str,
    t_start: float,
    t_end: float,
    fps: float = 3.0,
    max_width: int = 128,
) -> list[tuple]:
    """Return [(PIL.Image, timestamp_sec), …] for candidate loop frames."""
    duration = max(0.0, t_end - t_start)
    if duration <= 0:
        return []
    frames = extract_preview_frames(
        path, fps=fps, max_width=max_width,
        max_duration=duration,
        start_time=t_start, end_time=t_end,
    )
    step = 1.0 / fps
    return [(img, t_start + i * step) for i, (img, _) in enumerate(frames)]


class _SmartLoopWorker(QThread):
    """Find the (start_t, end_t) pair within the current clip that produces the
    most seamless loop — i.e. the head and tail frames connect smoothly.

    Strategy:
      • Search window = min(clip_duration × 50%, 6 s) at each end.
      • Extract candidate frames at 6 fps for more choices.
      • Score each (start_frame, end_frame) pair with a *combined* metric:
          – Pixel MSE       (60%): overall colour/brightness similarity
          – Edge MSE        (20%): structural gradient similarity, less
                                   sensitive to lighting drift
          – Motion-delta MSE(20%): the frame-to-frame change *leaving* the
                                   start frame vs *arriving at* the end frame;
                                   matching motion vectors prevents visible
                                   "jump" at the loop point
      • Minimum preserved clip = 30% of the original selection.
      • Emit found(new_start, new_end, similarity_pct).
    """

    progress = pyqtSignal(str)
    found    = pyqtSignal(float, float, float)  # (start_t, end_t, similarity_pct)
    error    = pyqtSignal(str)

    _THUMB     = (128, 128)  # was 64 — more detail for reliable comparison
    _FPS       = 6.0         # was 3 — more candidates to choose from
    _MAX_WIN   = 6.0         # was 3 s — wider search window
    _WIN_PCT   = 0.50        # was 0.30 — search half the clip at each end
    _MIN_PCT   = 0.30        # was 0.40 — allow somewhat shorter trimmed clips
    _MAX_WIDTH = 200         # thumbnail extraction width (pixels)

    def __init__(self, path: str, start_t: float, end_t: float, parent=None):
        super().__init__(parent)
        self._path  = path
        self._start = start_t
        self._end   = end_t

    # ------------------------------------------------------------------
    @staticmethod
    def _to_arr(img, thumb):
        return img.resize(thumb).convert("RGB")

    @staticmethod
    def _edge_map(arr_np):
        """Return per-pixel edge magnitude (simple finite-difference gradient)."""
        import numpy as np
        gray = arr_np.mean(axis=2)
        gx = np.abs(np.diff(gray, axis=1, append=gray[:, -1:]))
        gy = np.abs(np.diff(gray, axis=0, append=gray[-1:, :]))
        return np.sqrt(gx ** 2 + gy ** 2)

    @staticmethod
    def _motion_deltas(arrs):
        """Frame-to-frame difference for each frame in the list."""
        import numpy as np
        n = len(arrs)
        deltas = []
        for i in range(n):
            if i + 1 < n:
                d = arrs[i + 1] - arrs[i]
            elif i > 0:
                d = arrs[i] - arrs[i - 1]
            else:
                d = np.zeros_like(arrs[i])
            deltas.append(d)
        return deltas

    # ------------------------------------------------------------------
    def run(self):
        try:
            import numpy as np

            clip_dur = self._end - self._start
            if clip_dur < 0.5:
                self.error.emit("Clip is too short for loop analysis (need ≥ 0.5 s).")
                return

            window   = min(clip_dur * self._WIN_PCT, self._MAX_WIN)
            min_span = clip_dur * self._MIN_PCT

            self.progress.emit("Analysing start frames…")
            start_cands = _extract_candidates(
                self._path, self._start, self._start + window,
                self._FPS, self._MAX_WIDTH,
            )

            self.progress.emit("Analysing end frames…")
            end_cands = _extract_candidates(
                self._path, self._end - window, self._end,
                self._FPS, self._MAX_WIDTH,
            )

            if not start_cands or not end_cands:
                self.error.emit("Could not extract enough frames for analysis.")
                return

            self.progress.emit(
                f"Comparing {len(start_cands)} × {len(end_cands)} frame pairs…"
            )

            thumb = self._THUMB

            # Pre-compute numpy arrays, edge maps, and motion deltas once
            s_arrs  = [np.array(img.resize(thumb).convert("RGB"), dtype=np.float32)
                       for img, _ in start_cands]
            e_arrs  = [np.array(img.resize(thumb).convert("RGB"), dtype=np.float32)
                       for img, _ in end_cands]
            s_times = [t for _, t in start_cands]
            e_times = [t for _, t in end_cands]

            s_edges  = [self._edge_map(a) for a in s_arrs]
            e_edges  = [self._edge_map(a) for a in e_arrs]

            # start_deltas[i]: motion *leaving*  frame i (what happens right after)
            # end_deltas[j]:   motion *arriving* at frame j (what happened just before)
            s_deltas = self._motion_deltas(s_arrs)
            e_deltas = self._motion_deltas(e_arrs)

            best_score = float("inf")
            best_s_t   = self._start
            best_e_t   = self._end

            for i, s_t in enumerate(s_times):
                for j, e_t in enumerate(e_times):
                    if e_t - s_t < min_span:
                        continue

                    pixel_mse  = float(np.mean((s_arrs[i]   - e_arrs[j])   ** 2))
                    edge_mse   = float(np.mean((s_edges[i]  - e_edges[j])  ** 2))
                    motion_mse = float(np.mean((s_deltas[i] - e_deltas[j]) ** 2))

                    # Weighted combined score:
                    #   60% pixel colour · 20% edge structure · 20% motion continuity
                    score = pixel_mse * 0.6 + edge_mse * 0.2 + motion_mse * 0.2

                    if score < best_score:
                        best_score = score
                        best_s_t   = s_t
                        best_e_t   = e_t

            similarity = max(0.0, 100.0 * (1.0 - best_score / (255.0 ** 2)))
            self.found.emit(best_s_t, best_e_t, similarity)

        except Exception as exc:
            self.error.emit(str(exc))


# ── Static frame display ───────────────────────────────────────────────────────

class _FrameLabel(QLabel):
    """QLabel that scales its pixmap to fit while preserving aspect ratio."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_orig: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(120, 90)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #1a1d2e; border-radius: 4px;")
        self.setText("Frame preview will appear here")
        self.setStyleSheet(
            "background: #1a1d2e; border-radius: 4px; color: #4a5068; font-size: 11px;"
        )

    def set_pixmap_scaled(self, px: QPixmap):
        self._pixmap_orig = px
        self._refresh()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self):
        if self._pixmap_orig and not self._pixmap_orig.isNull():
            scaled = self._pixmap_orig.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(scaled)
            self.setText("")


# ── Main widget ────────────────────────────────────────────────────────────────

class ClipToGifWidget(QWidget):
    """Single-video clip-to-GIF tool with visual timeline range selection.

    Layout:
      Left   – video file selector, conversion settings, export
      Middle – TimeRangeSlider + scrub bar + static frame preview
      Right  – animated output GIF preview
    """

    # Resolution of the scrub QSlider (ticks per second)
    _SCRUB_SCALE = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._video_path:    Optional[str]  = None
        self._video_info:    dict           = {}
        self._preview_worker:    Optional[_CancellablePreviewWorker] = None
        self._frame_worker:      Optional[_FrameExtractWorker]       = None
        self._smart_loop_worker: Optional[_SmartLoopWorker]          = None
        self._preview_tmp:       Optional[str]                       = None

        self._frame_debounce = QTimer()
        self._frame_debounce.setSingleShot(True)
        self._frame_debounce.timeout.connect(self._extract_scrub_frame)

        self._ffmpeg_ok = is_ffmpeg_available()
        self._init_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _init_ui(self):
        from .preview_widget import PreviewWidget

        # ══════════════════════════════════════════════════════════════════════
        # LEFT column – controls
        # ══════════════════════════════════════════════════════════════════════
        controls = QWidget()
        cl = QVBoxLayout(controls)
        cl.setSpacing(8)
        cl.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Clip to GIF")
        title.setStyleSheet("font-weight: bold; font-size: 15px; color: #e4e8f4;")
        cl.addWidget(title)

        desc = QLabel(
            "Open a video, drag the timeline to select a clip,\n"
            "then export it as a GIF."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        cl.addWidget(desc)

        # ── 1. Open Video ──────────────────────────────────────────────────────
        file_group = QGroupBox("1. Open Video")
        fl = QVBoxLayout()

        self._open_btn = QPushButton("Open Video…")
        self._open_btn.clicked.connect(self._open_video)
        fl.addWidget(self._open_btn)

        self._file_label = QLabel("No video loaded")
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        fl.addWidget(self._file_label)

        self._meta_label = QLabel("")
        self._meta_label.setWordWrap(True)
        self._meta_label.setStyleSheet("color: #8ab4f8; font-size: 10px;")
        fl.addWidget(self._meta_label)

        file_group.setLayout(fl)
        cl.addWidget(file_group)

        # ── 2. Conversion Settings ─────────────────────────────────────────────
        settings_group = QGroupBox("2. Conversion Settings")
        sl = QVBoxLayout()

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Output FPS:"))
        self._fps_spin = QDoubleSpinBox()
        self._fps_spin.setRange(1.0, 60.0)
        self._fps_spin.setSingleStep(1.0)
        self._fps_spin.setDecimals(1)
        self._fps_spin.setValue(10.0)
        fps_row.addWidget(self._fps_spin)
        fps_row.addStretch()
        sl.addLayout(fps_row)

        width_row = QHBoxLayout()
        width_row.addWidget(QLabel("Width px:"))
        self._width_spin = QSpinBox()
        self._width_spin.setRange(0, 3840)
        self._width_spin.setSingleStep(50)
        self._width_spin.setValue(0)
        self._width_spin.setSpecialValueText("0 = keep original")
        width_row.addWidget(self._width_spin)
        width_row.addStretch()
        sl.addLayout(width_row)

        colors_row = QHBoxLayout()
        colors_row.addWidget(QLabel("Colors:"))
        self._colors_spin = QSpinBox()
        self._colors_spin.setRange(32, 256)
        self._colors_spin.setSingleStep(8)
        self._colors_spin.setValue(256)
        colors_row.addWidget(self._colors_spin)
        colors_row.addStretch()
        sl.addLayout(colors_row)

        dither_row = QHBoxLayout()
        dither_row.addWidget(QLabel("Dither:"))
        self._dither_combo = QComboBox()
        self._dither_combo.addItems(["bayer", "floyd_steinberg", "sierra2", "none"])
        dither_row.addWidget(self._dither_combo)
        dither_row.addStretch()
        sl.addLayout(dither_row)

        settings_group.setLayout(sl)
        cl.addWidget(settings_group)

        # ── 3. Post-process ────────────────────────────────────────────────────
        opt_group = QGroupBox("3. Post-process Optimization")
        ol = QVBoxLayout()
        lossy_row = QHBoxLayout()
        self._lossy_cb = QCheckBox("Lossy compress via gifsicle")
        self._lossy_cb.setChecked(False)
        lossy_row.addWidget(self._lossy_cb)
        self._lossy_spin = QSpinBox()
        self._lossy_spin.setRange(0, 200)
        self._lossy_spin.setValue(80)
        self._lossy_spin.setEnabled(False)
        lossy_row.addWidget(self._lossy_spin)
        lossy_row.addStretch()
        ol.addLayout(lossy_row)
        self._lossy_cb.toggled.connect(self._lossy_spin.setEnabled)
        opt_group.setLayout(ol)
        cl.addWidget(opt_group)

        # ── 4. Export ──────────────────────────────────────────────────────────
        export_group = QGroupBox("4. Export")
        el = QVBoxLayout()
        self._export_btn = QPushButton("💾  Save GIF As…")
        self._export_btn.setMinimumHeight(32)
        self._export_btn.clicked.connect(self._export)
        self._export_btn.setEnabled(False)
        el.addWidget(self._export_btn)

        self._status_label = QLabel("Open a video to get started.")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        el.addWidget(self._status_label)
        export_group.setLayout(el)
        cl.addWidget(export_group)

        # ── ffmpeg hint ────────────────────────────────────────────────────────
        self._ffmpeg_hint = QLabel()
        self._ffmpeg_hint.setWordWrap(True)
        self._ffmpeg_hint.setStyleSheet("font-size: 10px;")
        cl.addWidget(self._ffmpeg_hint)

        ffmpeg_btns = QHBoxLayout()
        self._install_btn = QPushButton("How to Install FFmpeg…")
        self._install_btn.setStyleSheet("font-size: 10px;")
        self._install_btn.clicked.connect(self._show_install_dialog)
        ffmpeg_btns.addWidget(self._install_btn)
        refresh_btn = QPushButton("Refresh Detection")
        refresh_btn.setStyleSheet("font-size: 10px;")
        refresh_btn.clicked.connect(self._refresh_ffmpeg)
        ffmpeg_btns.addWidget(refresh_btn)
        cl.addLayout(ffmpeg_btns)
        cl.addStretch()

        left_scroll = QScrollArea()
        left_scroll.setWidget(controls)
        left_scroll.setWidgetResizable(True)
        left_scroll.setMinimumWidth(230)

        # ══════════════════════════════════════════════════════════════════════
        # MIDDLE column – timeline + scrub + static frame preview
        # ══════════════════════════════════════════════════════════════════════
        mid_col = QWidget()
        mid_layout = QVBoxLayout(mid_col)
        mid_layout.setContentsMargins(6, 6, 6, 6)
        mid_layout.setSpacing(6)

        src_hdr = QLabel("Source Clip")
        src_hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        mid_layout.addWidget(src_hdr)

        self._src_meta = QLabel("")
        self._src_meta.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        mid_layout.addWidget(self._src_meta)

        # ── TimeRangeSlider ────────────────────────────────────────────────────
        range_lbl = QLabel("Clip Range")
        range_lbl.setStyleSheet("font-size: 11px; color: #b0b8d0; font-weight: bold;")
        mid_layout.addWidget(range_lbl)

        self._slider = TimeRangeSlider()
        self._slider.range_changed.connect(self._on_slider_changed)
        self._slider.scrub_requested.connect(self._on_scrub_requested)
        mid_layout.addWidget(self._slider)

        # Fine-tune row
        fine_row = QHBoxLayout()
        fine_row.addWidget(QLabel("Start (s):"))
        self._start_spin = QDoubleSpinBox()
        self._start_spin.setRange(0.0, 86400.0)
        self._start_spin.setDecimals(2)
        self._start_spin.setValue(0.0)
        self._start_spin.setMaximumWidth(90)
        fine_row.addWidget(self._start_spin)
        fine_row.addWidget(QLabel("End (s):"))
        self._end_spin = QDoubleSpinBox()
        self._end_spin.setRange(0.0, 86400.0)
        self._end_spin.setDecimals(2)
        self._end_spin.setValue(0.0)
        self._end_spin.setSpecialValueText("0 = full")
        self._end_spin.setMaximumWidth(90)
        fine_row.addWidget(self._end_spin)
        fine_row.addStretch()
        mid_layout.addLayout(fine_row)

        self._clip_dur_label = QLabel("")
        self._clip_dur_label.setStyleSheet("color: #a0d8af; font-size: 10px;")
        mid_layout.addWidget(self._clip_dur_label)

        # ── Smart Loop ────────────────────────────────────────────────────────
        loop_row = QHBoxLayout()
        self._smart_loop_btn = QPushButton("🔁  Find Smart Loop")
        self._smart_loop_btn.setToolTip(
            "Automatically trim start/end to the pair of frames that look most\n"
            "similar, creating a seamless natural loop."
        )
        self._smart_loop_btn.clicked.connect(self._find_smart_loop)
        self._smart_loop_btn.setEnabled(False)
        loop_row.addWidget(self._smart_loop_btn)
        loop_row.addStretch()
        mid_layout.addLayout(loop_row)

        self._loop_result_label = QLabel("")
        self._loop_result_label.setWordWrap(True)
        self._loop_result_label.setStyleSheet("color: #f0c060; font-size: 10px;")
        mid_layout.addWidget(self._loop_result_label)

        # ── Scrub bar ──────────────────────────────────────────────────────────
        scrub_hdr = QLabel("Frame Preview")
        scrub_hdr.setStyleSheet("font-size: 11px; color: #b0b8d0; font-weight: bold;")
        mid_layout.addWidget(scrub_hdr)

        scrub_hint = QLabel("Drag to scrub through the video")
        scrub_hint.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        mid_layout.addWidget(scrub_hint)

        self._scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self._scrub_slider.setMinimum(0)
        self._scrub_slider.setMaximum(0)
        self._scrub_slider.setEnabled(False)
        self._scrub_slider.valueChanged.connect(self._on_scrub_slider_changed)
        mid_layout.addWidget(self._scrub_slider)

        self._scrub_time_label = QLabel("")
        self._scrub_time_label.setStyleSheet(
            "color: #f0c060; font-size: 10px; font-weight: bold;"
        )
        mid_layout.addWidget(self._scrub_time_label)

        # ── Static frame display ───────────────────────────────────────────────
        self._frame_label = _FrameLabel()
        mid_layout.addWidget(self._frame_label, 1)

        # ══════════════════════════════════════════════════════════════════════
        # RIGHT column – animated output GIF preview (manual refresh)
        # ══════════════════════════════════════════════════════════════════════
        out_col = QWidget()
        out_layout = QVBoxLayout(out_col)
        out_layout.setContentsMargins(6, 6, 6, 6)
        out_layout.setSpacing(4)

        # Header row: label + action buttons
        out_hdr_row = QHBoxLayout()
        out_hdr = QLabel("Output GIF Preview")
        out_hdr.setStyleSheet("font-weight: bold; font-size: 12px; color: #9ba8c0;")
        out_hdr_row.addWidget(out_hdr)
        out_hdr_row.addStretch()

        self._gen_btn = QPushButton("▶  Generate Preview")
        self._gen_btn.setToolTip("Convert the selected clip to GIF and show a preview")
        self._gen_btn.clicked.connect(self._generate_preview)
        self._gen_btn.setEnabled(False)
        out_hdr_row.addWidget(self._gen_btn)

        self._cancel_btn = QPushButton("✕  Cancel")
        self._cancel_btn.setToolTip("Stop the current conversion")
        self._cancel_btn.clicked.connect(self._cancel_preview)
        self._cancel_btn.setVisible(False)
        out_hdr_row.addWidget(self._cancel_btn)

        out_layout.addLayout(out_hdr_row)

        self._out_info = QLabel("Click 'Generate Preview' after adjusting settings.")
        self._out_info.setWordWrap(True)
        self._out_info.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 10px;")
        out_layout.addWidget(self._out_info)

        self.output_preview = PreviewWidget()
        out_layout.addWidget(self.output_preview, 1)

        # ── 3-column splitter ──────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_scroll)
        splitter.addWidget(mid_col)
        splitter.addWidget(out_col)
        splitter.setSizes([270, 560, 560])

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)
        self.setLayout(outer)

        # Spinboxes → slider sync (user types → update slider display)
        self._start_spin.valueChanged.connect(self._on_spin_changed)
        self._end_spin.valueChanged.connect(self._on_spin_changed)

        # Apply ffmpeg state after all widgets are constructed
        self._apply_ffmpeg_state()

    # ── ffmpeg helpers ─────────────────────────────────────────────────────────

    def _apply_ffmpeg_state(self):
        if self._ffmpeg_ok:
            self._ffmpeg_hint.setText("ffmpeg found — ready to convert.")
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.SUCCESS}; font-size: 10px;")
            self._install_btn.setVisible(False)
        else:
            info = get_ffmpeg_install_info()
            self._ffmpeg_hint.setText(
                "ffmpeg not found — conversion unavailable.\n"
                f"Recommended: {info['command']}\n"
                "Click 'How to Install' for details, then 'Refresh'."
            )
            self._ffmpeg_hint.setStyleSheet(f"color: {_T.ERROR}; font-size: 10px;")
            self._install_btn.setVisible(True)
        loaded = self._video_path is not None
        self._export_btn.setEnabled(self._ffmpeg_ok and loaded)
        self._gen_btn.setEnabled(self._ffmpeg_ok and loaded)
        self._smart_loop_btn.setEnabled(self._ffmpeg_ok and loaded)

    def _show_install_dialog(self):
        info = get_ffmpeg_install_info()
        msg = QMessageBox(self)
        msg.setWindowTitle("Install FFmpeg")
        msg.setIcon(QMessageBox.Icon.Information)
        cmd_block = (
            f"<pre style='background:#1e2030;padding:6px;'>{info['command']}</pre>"
            if info["command"] else ""
        )
        msg.setText(
            f"<b>Platform:</b> {info['platform']}<br>"
            f"<b>Method:</b> {info['method']}<br><br>"
            f"{cmd_block}<br><b>Note:</b> {info['note']}<br><br>"
            "After installing, click <i>Refresh Detection</i>."
        )
        copy_btn = msg.addButton("Copy Command", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Ok)
        msg.exec()
        if msg.clickedButton() == copy_btn and info["command"]:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(info["command"])

    def _refresh_ffmpeg(self):
        self._ffmpeg_ok = find_ffmpeg() is not None
        self._apply_ffmpeg_state()
        if self._ffmpeg_ok and self._video_path:
            self._load_video(self._video_path)

    # ── Video loading ──────────────────────────────────────────────────────────

    def _open_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", "", _VIDEO_FILTER
        )
        if path:
            self._load_video(path)

    def _load_video(self, path: str):
        self._video_path = path
        p = Path(path)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        self._file_label.setText(f"{p.name}  ·  {_fmt_size(size)}")

        if not self._ffmpeg_ok:
            self._meta_label.setText("(ffmpeg not found — install to continue)")
            return

        info = get_video_info(path)
        self._video_info = info

        parts = []
        if info["width"]:
            parts.append(f"{info['width']}×{info['height']}")
        if info["fps"]:
            parts.append(f"{info['fps']:.1f} fps")
        if info["duration"]:
            parts.append(_fmt_time(info["duration"]))
        self._meta_label.setText("  ·  ".join(parts))
        self._src_meta.setText("  ·  ".join(parts))

        # Initialise slider + scrub bar to full video range
        dur = info.get("duration", 0.0) or 0.0
        self._slider.set_duration(dur)
        self._update_spins_from_slider()
        self._update_clip_dur_label()

        self._scrub_slider.setMaximum(int(dur * self._SCRUB_SCALE))
        self._scrub_slider.setEnabled(True)
        self._scrub_slider.setValue(0)

        self._export_btn.setEnabled(True)
        self._gen_btn.setEnabled(True)
        self._smart_loop_btn.setEnabled(True)
        self._loop_result_label.setText("")
        self._status_label.setText("Ready — drag handles to select a clip range.")
        self._out_info.setText("Click '▶ Generate Preview' after adjusting settings.")

        # Show first frame immediately
        self._request_frame(0.0)

    # ── Slider / spin sync ─────────────────────────────────────────────────────

    def _on_slider_changed(self, start: float, end: float):
        self._start_spin.blockSignals(True)
        self._end_spin.blockSignals(True)
        self._start_spin.setValue(start)
        self._end_spin.setValue(end)
        self._start_spin.blockSignals(False)
        self._end_spin.blockSignals(False)
        self._update_clip_dur_label()

    def _on_spin_changed(self):
        s = self._start_spin.value()
        e = self._end_spin.value()
        self._slider.blockSignals(True)
        self._slider.set_range(s, e)
        self._slider.blockSignals(False)
        self._update_clip_dur_label()

    def _update_spins_from_slider(self):
        self._start_spin.blockSignals(True)
        self._end_spin.blockSignals(True)
        self._start_spin.setValue(self._slider.start_time)
        self._end_spin.setValue(self._slider.end_time)
        self._start_spin.blockSignals(False)
        self._end_spin.blockSignals(False)

    def _update_clip_dur_label(self):
        s, e = self._slider.start_time, self._slider.end_time
        dur = e - s
        if dur > 0:
            self._clip_dur_label.setText(
                f"Clip: {_fmt_time(s)} → {_fmt_time(e)}  ({_fmt_time(dur)})"
            )
        else:
            self._clip_dur_label.setText("")

    # ── Scrub / frame extraction ───────────────────────────────────────────────

    def _on_scrub_requested(self, t: float):
        """Called when the user drags a range slider handle."""
        self._scrub_slider.blockSignals(True)
        self._scrub_slider.setValue(int(t * self._SCRUB_SCALE))
        self._scrub_slider.blockSignals(False)
        self._slider.set_scrub(t)
        self._request_frame(t)

    def _on_scrub_slider_changed(self, value: int):
        """Called when the user moves the scrub QSlider."""
        t = value / self._SCRUB_SCALE
        self._slider.set_scrub(t)
        self._scrub_time_label.setText(f"↑ {_fmt_time(t)}")
        self._request_frame(t)

    def _request_frame(self, t: float):
        """Debounce frame extraction to avoid hammering ffmpeg."""
        self._pending_scrub_t = t
        self._frame_debounce.start(120)

    def _extract_scrub_frame(self):
        t = getattr(self, "_pending_scrub_t", 0.0)
        if not self._video_path or not self._ffmpeg_ok:
            return

        # Cancel previous worker if still running
        if self._frame_worker and self._frame_worker.isRunning():
            self._frame_worker.quit()
            self._frame_worker.wait()

        self._scrub_time_label.setText(f"↑ {_fmt_time(t)}")
        worker = _FrameExtractWorker(self._video_path, t, parent=self)
        worker.done.connect(self._on_frame_ready)
        worker.error.connect(
            lambda msg: self._scrub_time_label.setText(f"Frame error: {msg}")
        )
        self._frame_worker = worker
        worker.start()

    def _on_frame_ready(self, img):
        px = _pil_to_pixmap(img)
        self._frame_label.set_pixmap_scaled(px)

    # ── Output GIF preview (manual) ────────────────────────────────────────────

    def _generate_preview(self):
        """Manually triggered: start a cancellable GIF conversion for preview."""
        if not self._video_path or not self._ffmpeg_ok:
            return

        # Cancel any previous run
        self._cancel_preview(silent=True)

        worker = _CancellablePreviewWorker(
            src=self._video_path,
            fps=self._fps_spin.value(),
            width=self._width_spin.value(),
            start_t=self._slider.start_time,
            end_t=self._slider.end_time,
            colors=self._colors_spin.value(),
            dither=self._dither_combo.currentText(),
            lossy=self._lossy_spin.value() if self._lossy_cb.isChecked() else 0,
            parent=self,
        )
        worker.done.connect(self._on_preview_ready)
        worker.progress.connect(self._out_info.setText)
        worker.error.connect(self._on_preview_error)
        worker.finished.connect(self._on_preview_worker_finished)
        self._preview_worker = worker

        self._gen_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._out_info.setText("Starting…")
        worker.start()

    def _cancel_preview(self, silent: bool = False):
        """Kill the running preview worker (if any)."""
        if self._preview_worker and self._preview_worker.isRunning():
            self._preview_worker.cancel()
            self._preview_worker.wait(3000)   # give it up to 3 s to exit cleanly
        if not silent:
            self._out_info.setText("Cancelled.")
            self._gen_btn.setEnabled(self._video_path is not None and self._ffmpeg_ok)
            self._cancel_btn.setVisible(False)

    def _on_preview_worker_finished(self):
        """Re-enable buttons when the worker exits for any reason."""
        self._gen_btn.setEnabled(self._video_path is not None and self._ffmpeg_ok)
        self._cancel_btn.setVisible(False)

    def _on_preview_error(self, msg: str):
        self._out_info.setText(f"Preview failed: {msg}")

    def _on_preview_ready(self, path: str):
        if self._preview_tmp and self._preview_tmp != path:
            try:
                os.unlink(self._preview_tmp)
            except OSError:
                pass
        self._preview_tmp = path
        self._load_gif_into_preview(path)

    def _load_gif_into_preview(self, path: str):
        try:
            from PIL import Image
            frames = []
            with Image.open(path) as img:
                file_size = Path(path).stat().st_size
                self._out_info.setText(
                    f"{_fmt_size(file_size)}  ·  {img.width}×{img.height}"
                )
                try:
                    while True:
                        dur = img.info.get("duration", 100)
                        frames.append((img.copy().convert("RGBA"), dur))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass
            if frames:
                self.output_preview.set_frames(frames)
                self.output_preview.play()
        except Exception as e:
            self._out_info.setText(f"Cannot load preview: {e}")

    # ── Smart Loop ────────────────────────────────────────────────────────────

    def _find_smart_loop(self):
        """Launch _SmartLoopWorker to find the best-matching start/end frame pair."""
        if not self._video_path or not self._ffmpeg_ok:
            return

        # Stop any previous run
        if self._smart_loop_worker and self._smart_loop_worker.isRunning():
            self._smart_loop_worker.quit()
            self._smart_loop_worker.wait(2000)

        self._smart_loop_btn.setEnabled(False)
        self._loop_result_label.setText("Analysing…")

        worker = _SmartLoopWorker(
            path=self._video_path,
            start_t=self._slider.start_time,
            end_t=self._slider.end_time,
            parent=self,
        )
        worker.progress.connect(self._loop_result_label.setText)
        worker.found.connect(self._on_smart_loop_found)
        worker.error.connect(self._on_smart_loop_error)
        worker.finished.connect(
            lambda: self._smart_loop_btn.setEnabled(
                self._video_path is not None and self._ffmpeg_ok
            )
        )
        self._smart_loop_worker = worker
        worker.start()

    def _on_smart_loop_found(self, start_t: float, end_t: float, similarity: float):
        """Apply the found loop range and report to the user."""
        # Update slider + spinboxes
        self._slider.set_range(start_t, end_t)
        self._update_spins_from_slider()
        self._update_clip_dur_label()

        # Update scrub slider position to new start
        self._scrub_slider.blockSignals(True)
        self._scrub_slider.setValue(int(start_t * self._SCRUB_SCALE))
        self._scrub_slider.blockSignals(False)
        self._slider.set_scrub(start_t)
        self._request_frame(start_t)

        dur = end_t - start_t
        self._loop_result_label.setText(
            f"✓ Loop found: {_fmt_time(start_t)} → {_fmt_time(end_t)} "
            f"({_fmt_time(dur)})  —  "
            f"similarity {similarity:.1f}%"
        )

    def _on_smart_loop_error(self, msg: str):
        self._loop_result_label.setText(f"Loop search failed: {msg}")

    # ── Export ─────────────────────────────────────────────────────────────────

    def _export(self):
        if not self._video_path:
            QMessageBox.warning(self, "No Video", "Please open a video file first.")
            return
        if not self._ffmpeg_ok:
            QMessageBox.warning(self, "FFmpeg Missing",
                                "Please install ffmpeg to export GIFs.")
            return

        src = Path(self._video_path)
        s = self._slider.start_time
        e = self._slider.end_time
        suggestion = str(src.parent / f"{src.stem}_{s:.0f}s-{e:.0f}s.gif")

        out_path, _ = QFileDialog.getSaveFileName(
            self, "Save GIF As", suggestion, "GIF Image (*.gif)"
        )
        if not out_path:
            return

        self._export_btn.setEnabled(False)
        self._status_label.setText("Exporting…")

        class _ExportWorker(QThread):
            done  = pyqtSignal(str)
            error = pyqtSignal(str)

            def __init__(inner_self, **kw):
                super().__init__(self)
                inner_self.kw = kw

            def run(inner_self):
                try:
                    inner_self.done.emit(convert_to_gif(**inner_self.kw))
                except VideoConversionError as exc:
                    inner_self.error.emit(str(exc))

        worker = _ExportWorker(
            input_path=self._video_path,
            output_path=out_path,
            fps=self._fps_spin.value(),
            width=self._width_spin.value(),
            start_time=s,
            end_time=e,
            colors=self._colors_spin.value(),
            dither=self._dither_combo.currentText(),
            lossy=self._lossy_spin.value() if self._lossy_cb.isChecked() else 0,
            overwrite=True,
        )
        worker.done.connect(self._on_export_done)
        worker.error.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _on_export_done(self, path: str):
        self._export_btn.setEnabled(True)
        size = Path(path).stat().st_size
        self._status_label.setText(
            f"Saved: {Path(path).name}  ({_fmt_size(size)})"
        )
        self._load_gif_into_preview(path)
        QMessageBox.information(self, "Export Complete",
                                f"GIF saved successfully:\n{path}")

    def _on_export_error(self, msg: str):
        self._export_btn.setEnabled(True)
        self._status_label.setText(f"Export failed: {msg}")
        QMessageBox.critical(self, "Export Failed", msg)
