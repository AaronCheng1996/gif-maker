"""Godot-style scene canvas for the Composer.

CanvasEditorWidget hosts a zoomable/pannable QGraphicsView showing the GIF
output bounds as a bordered rectangle with a transparency checkerboard fill.
It renders each FrameEntry of the current group as a selectable, draggable
pixmap item positioned at its x/y offset. Dragging an item writes the new
offset straight back into the live FrameEntry (P1-3); the entries_edited
signal fires once a drag ends so the caller can refresh the preview/tree.
"""
from typing import List, Optional

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QGraphicsView, QGraphicsScene, QGraphicsRectItem,
                              QGraphicsPixmapItem, QGraphicsItem, QStyle,
                              QCheckBox, QSpinBox)
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QBrush, QPen, QPixmap, QImage

from .theme import AppTheme as _T
from ..core import is_frame_entry
from ..i18n import tr

MIN_ZOOM = 0.05
MAX_ZOOM = 20.0
_CHECKER_TILE = 8  # px per checker square, in scene units
_CHECKER_LIGHT = QColor("#33374a")
_CHECKER_DARK = QColor("#262a38")
_SELECTION_COLOR = QColor("#ff9d3d")  # Godot-style orange selection outline
_ARROW_KEYS = {
    Qt.Key.Key_Left: (-1, 0),
    Qt.Key.Key_Right: (1, 0),
    Qt.Key.Key_Up: (0, -1),
    Qt.Key.Key_Down: (0, 1),
}


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


def _pil_to_qpixmap(pil_image) -> QPixmap:
    """Convert a PIL image to a QPixmap (RGBA)."""
    if pil_image.mode != 'RGBA':
        pil_image = pil_image.convert('RGBA')
    data = pil_image.tobytes('raw', 'RGBA')
    qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimage)
    del data  # keep alive until fromImage() has copied the pixel data
    return pixmap


class _MaterialPixmapItem(QGraphicsPixmapItem):
    """A placed material frame; draws a Godot-style orange outline when selected."""

    def __init__(self, pixmap: QPixmap, entry_index: int):
        super().__init__(pixmap)
        self.entry_index = entry_index
        self.on_position_changed = None  # callback(entry_index, x, y), set by CanvasEditorWidget
        self.snap_fn = None  # callback(QPointF) -> QPointF, set by CanvasEditorWidget
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)

    def paint(self, painter, option, widget=None):
        # Suppress Qt's default dashed selection rectangle; we draw our own outline.
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)
        if self.isSelected():
            pen = QPen(_SELECTION_COLOR, 2)
            pen.setCosmetic(True)  # constant on-screen width regardless of zoom
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.snap_fn:
            return self.snap_fn(value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.on_position_changed:
            self.on_position_changed(self.entry_index, value.x(), value.y())
        return super().itemChange(change, value)


class _CanvasGraphicsView(QGraphicsView):
    """QGraphicsView with cursor-anchored wheel zoom and middle/space-drag panning."""

    zoom_changed = pyqtSignal(float)
    mouse_scene_pos_changed = pyqtSignal(QPointF)
    item_interaction_finished = pyqtSignal()  # any left-button release (click or drag end)

    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        # RubberBandDrag only activates when the press lands on empty scene
        # space; clicking a movable/selectable item still selects+drags it.
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

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
        if event.button() == Qt.MouseButton.LeftButton:
            self.item_interaction_finished.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            if not self._panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif event.key() in _ARROW_KEYS and self.scene().selectedItems():
            dx, dy = _ARROW_KEYS[event.key()]
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            for item in self.scene().selectedItems():
                item.moveBy(dx * step, dy * step)
            self.item_interaction_finished.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)


class CanvasEditorWidget(QWidget):
    """Godot-style scene canvas: zoomable/pannable view of the GIF output bounds."""

    entry_selected = pyqtSignal(int)  # entry index, or -1 when nothing is selected
    entries_edited = pyqtSignal()     # fired once after a drag actually changes an offset

    def __init__(self, parent=None):
        super().__init__(parent)

        self._output_width = 400
        self._output_height = 400
        self._material_items: List[_MaterialPixmapItem] = []
        self._entries: Optional[list] = None
        self._drag_dirty = False
        self._snap_enabled = False
        self._snap_size = 10

        self.scene = QGraphicsScene(self)
        self.scene.setBackgroundBrush(QBrush(QColor(_T.BG)))
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)

        self.output_rect_item = QGraphicsRectItem()
        self.output_rect_item.setBrush(_make_checker_brush())
        self.output_rect_item.setPen(QPen(QColor(_T.ACCENT), 0))
        self.output_rect_item.setZValue(-1)
        self.scene.addItem(self.output_rect_item)

        self.view = _CanvasGraphicsView(self.scene, self)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.mouse_scene_pos_changed.connect(self._on_mouse_scene_pos_changed)
        self.view.item_interaction_finished.connect(self._on_item_interaction_finished)

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

        self.snap_checkbox = QCheckBox(tr("Snap"))
        self.snap_checkbox.setToolTip("Snap dragged/nudged items to a grid")
        self.snap_checkbox.toggled.connect(self.set_snap_enabled)
        status_bar.addWidget(self.snap_checkbox)

        self.snap_size_spinbox = QSpinBox()
        self.snap_size_spinbox.setRange(1, 999)
        self.snap_size_spinbox.setValue(self._snap_size)
        self.snap_size_spinbox.setSuffix("px")
        self.snap_size_spinbox.setMaximumWidth(70)
        self.snap_size_spinbox.valueChanged.connect(self.set_snap_size)
        status_bar.addWidget(self.snap_size_spinbox)
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

    # ── Material rendering & selection ──────────────────────────────────
    def set_entries(self, entries: list, material_manager) -> None:
        """Render the given group's entries as pixmap items positioned at their
        x/y offsets. Only FrameEntry items are rendered — SubGroupEntry and
        LayerBlockEntry are out of scope until later phases.

        Keeps a reference to `entries` (the live list, not a copy) so that
        drag-to-move can write x/y offsets straight back into the model."""
        # Only carry the selection over when re-rendering the *same* group's
        # entries (e.g. after a drag-end refresh) — a different entries list
        # means a different group, so any prior index would be coincidental.
        same_group = entries is self._entries
        previously_selected = self.selected_entry_index() if same_group else None
        self._entries = entries
        self._drag_dirty = False
        self._clear_material_items()
        for idx, entry in enumerate(entries):
            if not is_frame_entry(entry):
                continue
            mat = material_manager.get_material(entry.material_index)
            if not mat:
                continue
            img, _name = mat
            item = _MaterialPixmapItem(_pil_to_qpixmap(img), idx)
            item.on_position_changed = self._mark_item_moved
            item.snap_fn = self._apply_snap
            item.setPos(entry.x, entry.y)
            item.setZValue(idx)
            self.scene.addItem(item)
            self._material_items.append(item)
        if previously_selected is not None:
            self.select_entry(previously_selected)

    def _clear_material_items(self) -> None:
        for item in self._material_items:
            self.scene.removeItem(item)
        self._material_items = []

    def selected_entry_index(self) -> Optional[int]:
        """Return the entry index of the currently selected material item, or None."""
        selected = self.scene.selectedItems()
        if not selected:
            return None
        return selected[0].entry_index

    def selected_entry_indices(self) -> List[int]:
        """Return entry indices for every currently selected material item (multi-select)."""
        return sorted(item.entry_index for item in self.scene.selectedItems())

    def select_entry(self, entry_index: Optional[int]) -> None:
        """Programmatically select the item matching entry_index (or clear if None).

        Used to mirror a selection made in the group tree editor onto the canvas."""
        for item in self._material_items:
            item.setSelected(item.entry_index == entry_index)

    def _on_scene_selection_changed(self) -> None:
        idx = self.selected_entry_index()
        self.entry_selected.emit(idx if idx is not None else -1)

    # ── Snap-to-grid ─────────────────────────────────────────────────────
    def is_snap_enabled(self) -> bool:
        return self._snap_enabled

    def set_snap_enabled(self, enabled: bool) -> None:
        self._snap_enabled = bool(enabled)
        if self.snap_checkbox.isChecked() != self._snap_enabled:
            self.snap_checkbox.setChecked(self._snap_enabled)

    def snap_size(self) -> int:
        return self._snap_size

    def set_snap_size(self, size: int) -> None:
        self._snap_size = max(1, int(size))
        if self.snap_size_spinbox.value() != self._snap_size:
            self.snap_size_spinbox.setValue(self._snap_size)

    def _apply_snap(self, pos: QPointF) -> QPointF:
        if not self._snap_enabled:
            return pos
        size = self._snap_size
        return QPointF(round(pos.x() / size) * size, round(pos.y() / size) * size)

    # ── Drag-to-move ─────────────────────────────────────────────────────
    def _mark_item_moved(self, entry_index: int, x: float, y: float) -> None:
        """Write a dragged item's new position straight back into its FrameEntry."""
        if self._entries is None or not (0 <= entry_index < len(self._entries)):
            return
        entry = self._entries[entry_index]
        if is_frame_entry(entry):
            entry.x = int(round(x))
            entry.y = int(round(y))
            self._drag_dirty = True

    def _on_item_interaction_finished(self) -> None:
        """After any left-button release, notify listeners once if a drag changed an offset."""
        if self._drag_dirty:
            self._drag_dirty = False
            self.entries_edited.emit()
