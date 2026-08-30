"""A filmstrip with draggable in and out handles.

Two numbers in spin boxes describe a trim exactly and show nothing. What is
actually being asked — does this clip start after the slate, does it end before
the camera swings away — is a question about pictures, so the control is the
pictures: the clip laid end to end across the width, the kept span at full
brightness, the discarded head and tail dimmed, and a handle on each boundary.

The spin boxes stay, because pictures are bad at exact numbers.
"""
from typing import List, Optional

from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPixmap, QImage

from PIL import Image

from .theme import AppTheme as _T

BAR_HEIGHT = 74
HANDLE_WIDTH = 7
GRAB_SLOP = 9          # how near a handle counts as grabbing it
DIM = 165              # alpha of the veil over the discarded parts


def _pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgba = img.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                  QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class TrimBar(QWidget):
    """Shows one clip as a strip; reports the in point, out point and playhead."""

    start_changed = pyqtSignal(float)
    end_changed = pyqtSignal(float)
    playhead_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._frames: List[Image.Image] = []
        self._thumbs: List[QPixmap] = []
        self._thumb_width = 0
        self._duration = 0.0
        self._start = 0.0
        self._end = 0.0            # 0 means "to the end", as on a Segment
        self._playhead = 0.0
        self._drag: Optional[str] = None

    # ── contents ─────────────────────────────────────────────────────────
    def set_clip(self, frames: List[Image.Image], duration: float):
        self._frames = list(frames)
        self._thumbs = []
        self._thumb_width = 0
        self._duration = max(0.0, float(duration))
        self.update()

    def set_trim(self, start: float, end: float):
        self._start, self._end = start, end
        self.update()

    def set_playhead(self, seconds: float):
        self._playhead = seconds
        self.update()

    def clear(self):
        self.set_clip([], 0.0)

    @property
    def out_point(self) -> float:
        end = self._end if self._end > 0 else self._duration
        return min(end, self._duration) if self._duration else end

    # ── geometry ─────────────────────────────────────────────────────────
    def _x_for(self, seconds: float) -> int:
        if self._duration <= 0:
            return 0
        frac = min(max(seconds / self._duration, 0.0), 1.0)
        return int(frac * max(1, self.width() - 1))

    def _time_at(self, x: int) -> float:
        if self._duration <= 0:
            return 0.0
        frac = min(max(x / max(1, self.width() - 1), 0.0), 1.0)
        return frac * self._duration

    # ── painting ─────────────────────────────────────────────────────────
    def _build_thumbs(self, height: int):
        """One thumbnail per slot across the width, sampled from the frames."""
        if not self._frames or height <= 0:
            self._thumbs = []
            return
        src = self._frames[0]
        width = max(1, int(src.width * height / max(1, src.height)))
        slots = max(1, self.width() // max(1, width))
        picks = [self._frames[min(len(self._frames) - 1,
                                  int(i * len(self._frames) / slots))]
                 for i in range(slots)]
        self._thumbs = [_pil_to_pixmap(
            p.resize((width, height), Image.Resampling.BILINEAR)) for p in picks]
        self._thumb_width = width

    def paintEvent(self, _event):
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, QColor(_T.PANEL))

        if not self._frames or self._duration <= 0:
            painter.setPen(QColor(_T.TEXT_HINT))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                             "no clip selected")
            painter.end()
            return

        strip = QRect(0, 0, self.width(), self.height())
        if not self._thumbs or self._thumbs[0].height() != strip.height():
            self._build_thumbs(strip.height())
        x = 0
        for thumb in self._thumbs:
            painter.drawPixmap(x, 0, thumb)
            x += self._thumb_width
        if x < self.width() and self._thumbs:
            painter.drawPixmap(x, 0, self._thumbs[-1])

        # Everything outside the kept span is veiled rather than hidden: what is
        # being thrown away is as much a part of the decision as what is kept.
        left, right = self._x_for(self._start), self._x_for(self.out_point)
        veil = QColor(_T.BG)
        veil.setAlpha(DIM)
        if left > 0:
            painter.fillRect(QRect(0, 0, left, self.height()), veil)
        if right < self.width():
            painter.fillRect(QRect(right, 0, self.width() - right, self.height()),
                             veil)

        keep = QColor(_T.ACCENT)
        painter.setPen(keep)
        painter.drawRect(QRect(left, 0, max(1, right - left - 1), self.height() - 1))

        for x_pos in (left, right):
            handle = QRect(x_pos - HANDLE_WIDTH // 2, 0, HANDLE_WIDTH, self.height())
            painter.fillRect(handle, keep)

        head = self._x_for(self._playhead)
        painter.setPen(QColor(_T.TEXT))
        painter.drawLine(head, 0, head, self.height())
        painter.end()

    # ── interaction ──────────────────────────────────────────────────────
    def _hit(self, x: int) -> Optional[str]:
        if self._duration <= 0:
            return None
        if abs(x - self._x_for(self._start)) <= GRAB_SLOP:
            return "start"
        if abs(x - self._x_for(self.out_point)) <= GRAB_SLOP:
            return "end"
        return None

    def mouseMoveEvent(self, event):
        x = int(event.position().x())
        if self._drag is None:
            over = self._hit(x)
            self.setCursor(Qt.CursorShape.SizeHorCursor if over
                           else Qt.CursorShape.PointingHandCursor)
            return
        self._apply_drag(x)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self._duration <= 0:
            return
        x = int(event.position().x())
        self._drag = self._hit(x)
        if self._drag is None:
            # Not on a handle, so this is a scrub.
            self._playhead = self._time_at(x)
            self.playhead_changed.emit(self._playhead)
            self.update()
        else:
            self._apply_drag(x)

    def mouseReleaseEvent(self, _event):
        self._drag = None

    def _apply_drag(self, x: int):
        t = self._time_at(x)
        if self._drag == "start":
            self._start = min(t, max(0.0, self.out_point - 0.01))
            self.start_changed.emit(self._start)
        elif self._drag == "end":
            self._end = max(t, self._start + 0.01)
            self.end_changed.emit(self._end)
        else:
            return
        self._playhead = t
        self.playhead_changed.emit(t)
        self.update()
