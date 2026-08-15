"""A preview label with a draggable crop rectangle drawn over the image.

The rectangle is stored in normalized (0..1) coordinates relative to the
displayed image, so it survives preview rescaling and can be applied to an
export of any size.
"""
from typing import Optional, Tuple

from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap

from .theme import AppTheme as _T

HANDLE = 9          # on-screen size of a corner/edge grab handle
MIN_NORM = 0.02     # smallest crop, as a fraction of the image

# What a drag is doing to the rectangle.
_NONE, _MOVE, _NEW, _RESIZE = 0, 1, 2, 3
# Which edges a resize is pulling. Named _EDGE_* rather than _L/_R/_T/_B so that
# the top-edge flag cannot shadow the `_T` theme alias imported above.
_EDGE_L, _EDGE_R, _EDGE_T, _EDGE_B = 1 << 2, 1 << 3, 1 << 4, 1 << 5


class CropOverlayLabel(QLabel):
    """Shows a pixmap and, when enabled, an adjustable crop rectangle."""

    crop_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._crop = QRectF(0.0, 0.0, 1.0, 1.0)   # normalized
        self._crop_enabled = False
        self._drag_mode = _NONE
        self._drag_edges = 0
        self._drag_origin = QPoint()
        self._crop_at_press = QRectF()
        self.setMouseTracking(True)

    # ── state ────────────────────────────────────────────────────────────

    def set_preview_pixmap(self, pixmap: Optional[QPixmap]):
        self._pixmap = pixmap
        self.update()

    def preview_pixmap(self) -> Optional[QPixmap]:
        """The image being displayed. Kept separate from QLabel.pixmap() because
        this widget scales and paints it itself, to keep the crop rectangle
        aligned to the image rather than the widget."""
        return self._pixmap

    def crop_rect(self) -> Tuple[float, float, float, float]:
        """(x, y, w, h) normalized to the image, origin top-left."""
        r = self._crop
        return (r.x(), r.y(), r.width(), r.height())

    def set_crop_rect(self, x: float, y: float, w: float, h: float):
        self._crop = _clamp_rect(QRectF(x, y, w, h))
        self.update()
        self.crop_changed.emit()

    def is_crop_enabled(self) -> bool:
        return self._crop_enabled

    def set_crop_enabled(self, enabled: bool):
        self._crop_enabled = bool(enabled)
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()
        self.crop_changed.emit()

    def reset_crop(self):
        self._crop = QRectF(0.0, 0.0, 1.0, 1.0)
        self.update()
        self.crop_changed.emit()

    # ── geometry helpers ─────────────────────────────────────────────────

    def image_rect(self) -> Optional[QRect]:
        """Where the pixmap is actually drawn inside this widget."""
        if self._pixmap is None or self._pixmap.isNull():
            return None
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph, 1.0)
        w, h = int(pw * scale), int(ph * scale)
        return QRect((ww - w) // 2, (wh - h) // 2, w, h)

    def _crop_pixels(self) -> Optional[QRect]:
        img = self.image_rect()
        if img is None:
            return None
        return QRect(
            img.x() + int(self._crop.x() * img.width()),
            img.y() + int(self._crop.y() * img.height()),
            max(1, int(self._crop.width() * img.width())),
            max(1, int(self._crop.height() * img.height())),
        )

    def _edges_at(self, pos: QPoint) -> int:
        rect = self._crop_pixels()
        if rect is None:
            return 0
        edges = 0
        if abs(pos.x() - rect.left()) <= HANDLE:
            edges |= _EDGE_L
        elif abs(pos.x() - rect.right()) <= HANDLE:
            edges |= _EDGE_R
        if abs(pos.y() - rect.top()) <= HANDLE:
            edges |= _EDGE_T
        elif abs(pos.y() - rect.bottom()) <= HANDLE:
            edges |= _EDGE_B
        # Only count edges when the cursor is roughly alongside the rectangle.
        if edges and not rect.adjusted(-HANDLE, -HANDLE, HANDLE, HANDLE).contains(pos):
            return 0
        return edges

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        img = self.image_rect()
        if self._pixmap is None or img is None:
            # Let QLabel draw its placeholder text. This must happen before we
            # open our own painter — one paint device cannot have two painters.
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.drawPixmap(img, self._pixmap)

        if not self._crop_enabled:
            return
        rect = self._crop_pixels()
        if rect is None:
            return

        # Dim everything outside the crop.
        shade = QColor(0, 0, 0, 120)
        for area in (
            QRect(img.left(), img.top(), img.width(), rect.top() - img.top()),
            QRect(img.left(), rect.bottom() + 1, img.width(), img.bottom() - rect.bottom()),
            QRect(img.left(), rect.top(), rect.left() - img.left(), rect.height()),
            QRect(rect.right() + 1, rect.top(), img.right() - rect.right(), rect.height()),
        ):
            if area.width() > 0 and area.height() > 0:
                painter.fillRect(area, shade)

        painter.setPen(QPen(QColor(_T.ACCENT), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # Thirds guides.
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        for i in (1, 2):
            x = rect.left() + rect.width() * i // 3
            y = rect.top() + rect.height() * i // 3
            painter.drawLine(x, rect.top(), x, rect.bottom())
            painter.drawLine(rect.left(), y, rect.right(), y)

        # Corner handles.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_T.ACCENT))
        s = HANDLE
        for cx, cy in ((rect.left(), rect.top()), (rect.right(), rect.top()),
                       (rect.left(), rect.bottom()), (rect.right(), rect.bottom())):
            painter.drawRect(QRect(cx - s // 2, cy - s // 2, s, s))

    # ── mouse ────────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if not self._crop_enabled or event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        img = self.image_rect()
        if img is None:
            return
        pos = event.position().toPoint()
        self._drag_origin = pos
        self._crop_at_press = QRectF(self._crop)
        edges = self._edges_at(pos)
        rect = self._crop_pixels()
        full_frame = (self._crop.width() >= 0.999 and self._crop.height() >= 0.999)
        if full_frame:
            # A full-frame rect has nowhere to move, so the first drag should
            # draw a region rather than silently do nothing.
            self._drag_mode, self._drag_edges = _NEW, 0
            nx = (pos.x() - img.x()) / max(img.width(), 1)
            ny = (pos.y() - img.y()) / max(img.height(), 1)
            self._crop = _clamp_rect(QRectF(nx, ny, MIN_NORM, MIN_NORM))
        elif edges:
            self._drag_mode, self._drag_edges = _RESIZE, edges
        elif rect is not None and rect.contains(pos):
            self._drag_mode, self._drag_edges = _MOVE, 0
        else:
            self._drag_mode, self._drag_edges = _NEW, 0
            nx = (pos.x() - img.x()) / max(img.width(), 1)
            ny = (pos.y() - img.y()) / max(img.height(), 1)
            self._crop = _clamp_rect(QRectF(nx, ny, MIN_NORM, MIN_NORM))
        self.update()

    def mouseMoveEvent(self, event):
        img = self.image_rect()
        if not self._crop_enabled or img is None:
            return super().mouseMoveEvent(event)
        pos = event.position().toPoint()

        if self._drag_mode == _NONE:
            self.setCursor(_cursor_for(self._edges_at(pos)))
            return

        dx = (pos.x() - self._drag_origin.x()) / max(img.width(), 1)
        dy = (pos.y() - self._drag_origin.y()) / max(img.height(), 1)
        base = self._crop_at_press

        if self._drag_mode == _MOVE:
            r = QRectF(base)
            r.moveLeft(min(max(base.x() + dx, 0.0), 1.0 - base.width()))
            r.moveTop(min(max(base.y() + dy, 0.0), 1.0 - base.height()))
            self._crop = r
        elif self._drag_mode == _NEW:
            nx = (pos.x() - img.x()) / max(img.width(), 1)
            ny = (pos.y() - img.y()) / max(img.height(), 1)
            ox = (self._drag_origin.x() - img.x()) / max(img.width(), 1)
            oy = (self._drag_origin.y() - img.y()) / max(img.height(), 1)
            self._crop = _clamp_rect(QRectF(min(ox, nx), min(oy, ny),
                                            abs(nx - ox), abs(ny - oy)))
        else:  # _RESIZE
            left, top = base.left(), base.top()
            right, bottom = base.right(), base.bottom()
            if self._drag_edges & _EDGE_L:
                left = min(base.left() + dx, right - MIN_NORM)
            if self._drag_edges & _EDGE_R:
                right = max(base.right() + dx, left + MIN_NORM)
            if self._drag_edges & _EDGE_T:
                top = min(base.top() + dy, bottom - MIN_NORM)
            if self._drag_edges & _EDGE_B:
                bottom = max(base.bottom() + dy, top + MIN_NORM)
            self._crop = _clamp_rect(QRectF(left, top, right - left, bottom - top))

        self.update()
        self.crop_changed.emit()

    def mouseReleaseEvent(self, event):
        if self._drag_mode != _NONE:
            self._drag_mode = _NONE
            self._drag_edges = 0
            self.crop_changed.emit()
        super().mouseReleaseEvent(event)


def _cursor_for(edges: int) -> Qt.CursorShape:
    if not edges:
        return Qt.CursorShape.CrossCursor
    if edges in (_EDGE_L | _EDGE_T, _EDGE_R | _EDGE_B):
        return Qt.CursorShape.SizeFDiagCursor
    if edges in (_EDGE_R | _EDGE_T, _EDGE_L | _EDGE_B):
        return Qt.CursorShape.SizeBDiagCursor
    if edges & (_EDGE_L | _EDGE_R):
        return Qt.CursorShape.SizeHorCursor
    return Qt.CursorShape.SizeVerCursor


def _clamp_rect(r: QRectF) -> QRectF:
    x = min(max(r.x(), 0.0), 1.0 - MIN_NORM)
    y = min(max(r.y(), 0.0), 1.0 - MIN_NORM)
    w = min(max(r.width(), MIN_NORM), 1.0 - x)
    h = min(max(r.height(), MIN_NORM), 1.0 - y)
    return QRectF(x, y, w, h)
