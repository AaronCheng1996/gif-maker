"""Godot-style scene canvas for the Composer.

CanvasEditorWidget hosts a zoomable/pannable QGraphicsView showing the GIF
output bounds as a bordered rectangle with a transparency checkerboard fill.
This is the P1-1 skeleton: it does not yet render material frames or accept
selection (see P1-2 onward) — it only establishes the viewport, zoom/pan
behavior, and the output-bounds rectangle.
"""
from typing import Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QGraphicsView, QGraphicsScene, QGraphicsRectItem)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap

from .theme import AppTheme as _T

MIN_ZOOM = 0.05
MAX_ZOOM = 20.0
_CHECKER_TILE = 8  # px per checker square, in scene units
_CHECKER_LIGHT = QColor("#33374a")
_CHECKER_DARK = QColor("#262a38")


def _make_checker_brush() -> QBrush:
    """Build a tiling brush for the transparency checkerboard."""
    size = _CHECKER_TILE * 2
    pixmap = QPixmap(size, size)
    pixmap.fill(_CHECKER_LIGHT)
    painter = QPainter(pixmap)
    painter.fillRect(0, 0, _CHECKER_TILE, _CHECKER_TILE, _CHECKER_DARK)
    painter.fillRect(_CHECKER_TILE, _CHECKER_TILE, _CHECKER_TILE, _CHECKER_TILE, _CHECKER_DARK)
    painter.end()
    return QBrush(pixmap)


class _CanvasGraphicsView(QGraphicsView):
    """QGraphicsView with cursor-anchored wheel zoom and middle/space-drag panning."""

    zoom_changed = pyqtSignal(float)
    mouse_scene_pos_changed = pyqtSignal(QPointF)

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self._panning = False
        self._pan_start = QPointF()
        self._space_held = False

    # ── Zoom ─────────────────────────────────────────────────────────────
    def current_zoom(self) -> float:
        return self.transform().m11()

    def zoom_by(self, factor: float) -> None:
        """Apply a multiplicative zoom factor, clamped to [MIN_ZOOM, MAX_ZOOM]."""
        new_zoom = self.current_zoom() * factor
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, new_zoom))
        actual_factor = new_zoom / self.current_zoom() if self.current_zoom() else 1.0
        self.scale(actual_factor, actual_factor)
        self.zoom_changed.emit(self.current_zoom())

    def set_zoom(self, zoom: float) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        current = self.current_zoom()
        if current:
            self.scale(zoom / current, zoom / current)
        self.zoom_changed.emit(self.current_zoom())

    def wheelEvent(self, event):
        angle = event.angleDelta().y()
        if angle == 0:
            super().wheelEvent(event)
            return
        factor = 1.15 if angle > 0 else 1 / 1.15
        self.zoom_by(factor)
        event.accept()

    # ── Pan (middle-mouse or Space+drag) ────────────────────────────────
    def _start_pan(self, pos: QPointF):
        self._panning = True
        self._pan_start = pos
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _stop_pan(self):
        self._panning = False
        self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_held else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton or (
            self._space_held and event.button() == Qt.MouseButton.LeftButton
        ):
            self._start_pan(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        self.mouse_scene_pos_changed.emit(self.mapToScene(event.position().toPoint()))
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            h_bar.setValue(h_bar.value() - int(delta.x()))
            v_bar.setValue(v_bar.value() - int(delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._stop_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)


class CanvasEditorWidget(QWidget):
    """Godot-style scene canvas: zoomable/pannable view of the GIF output bounds."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._output_width = 400
        self._output_height = 400

        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor(_T.BG)))

        self.output_rect_item = QGraphicsRectItem()
        self.output_rect_item.setBrush(_make_checker_brush())
        self.output_rect_item.setPen(QPen(QColor(_T.ACCENT), 0))
        self.output_rect_item.setZValue(-1)
        self.scene.addItem(self.output_rect_item)

        self.view = _CanvasGraphicsView(self.scene, self)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.mouse_scene_pos_changed.connect(self._on_mouse_scene_pos_changed)

        self.set_output_size(self._output_width, self._output_height)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view, stretch=1)

        status_bar = QHBoxLayout()
        status_bar.setContentsMargins(6, 2, 6, 2)
        self.zoom_label = QLabel("100%")
        self.coords_label = QLabel("x: 0, y: 0")
        for lbl in (self.zoom_label, self.coords_label):
            lbl.setStyleSheet(f"color: {_T.TEXT_DIM}; font-size: 11px;")
        status_bar.addWidget(self.zoom_label)
        status_bar.addWidget(self.coords_label)
        status_bar.addStretch()
        status_widget = QWidget()
        status_widget.setLayout(status_bar)
        status_widget.setStyleSheet(f"background-color: {_T.PANEL}; border-top: 1px solid {_T.BORDER};")
        layout.addWidget(status_widget)

    # ── Output bounds ────────────────────────────────────────────────────
    def set_output_size(self, width: int, height: int) -> None:
        """Resize the canvas' output-bounds rectangle to (width, height)."""
        width = max(1, int(width))
        height = max(1, int(height))
        self._output_width = width
        self._output_height = height
        self.output_rect_item.setRect(0, 0, width, height)

        # Generous padding around the output rect so there's room to pan.
        pad_x = max(width, 200)
        pad_y = max(height, 200)
        self.scene.setSceneRect(QRectF(-pad_x, -pad_y, width + 2 * pad_x, height + 2 * pad_y))

    def output_rect(self) -> QRectF:
        return self.output_rect_item.rect()

    # ── Coordinate transforms (exposed for testing / future item logic) ─
    def view_to_scene(self, view_point) -> QPointF:
        return self.view.mapToScene(view_point)

    def scene_to_view(self, scene_point):
        return self.view.mapFromScene(scene_point)

    def zoom_percent(self) -> float:
        return self.view.current_zoom() * 100.0

    def zoom_by(self, factor: float) -> None:
        self.view.zoom_by(factor)

    def reset_view(self) -> None:
        """Reset zoom to 100% and center the view on the output bounds."""
        self.view.resetTransform()
        self.view.zoom_changed.emit(self.view.current_zoom())
        self.view.centerOn(self.output_rect_item)

    # ── Status bar updates ───────────────────────────────────────────────
    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{zoom * 100:.0f}%")

    def _on_mouse_scene_pos_changed(self, pos: QPointF) -> None:
        self.coords_label.setText(f"x: {pos.x():.0f}, y: {pos.y():.0f}")
