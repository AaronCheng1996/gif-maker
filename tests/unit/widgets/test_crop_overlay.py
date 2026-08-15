"""Tests for the draggable crop rectangle drawn over the preview."""
import pytest

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from src.widgets.crop_overlay import MIN_NORM, CropOverlayLabel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def overlay(qapp):
    w = CropOverlayLabel()
    w.resize(200, 100)
    pm = QPixmap(200, 100)
    pm.fill(Qt.GlobalColor.red)
    w.set_preview_pixmap(pm)
    return w


def _press(w, x, y):
    w.mousePressEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonPress, QPointF(x, y), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def _move(w, x, y):
    w.mouseMoveEvent(QMouseEvent(
        QMouseEvent.Type.MouseMove, QPointF(x, y), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


def _release(w, x, y):
    w.mouseReleaseEvent(QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease, QPointF(x, y), Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))


# ── state ────────────────────────────────────────────────────────────────

def test_starts_disabled_and_full_frame(overlay):
    assert overlay.is_crop_enabled() is False
    assert overlay.crop_rect() == (0.0, 0.0, 1.0, 1.0)


def test_preview_pixmap_round_trips(overlay):
    assert overlay.preview_pixmap() is not None
    assert overlay.preview_pixmap().size().width() == 200


def test_enabling_emits_change(overlay):
    seen = []
    overlay.crop_changed.connect(lambda: seen.append(1))
    overlay.set_crop_enabled(True)
    assert overlay.is_crop_enabled() is True
    assert seen


def test_set_crop_rect_round_trips(overlay):
    overlay.set_crop_rect(0.25, 0.1, 0.5, 0.4)
    x, y, w, h = overlay.crop_rect()
    assert (round(x, 3), round(y, 3)) == (0.25, 0.1)
    assert (round(w, 3), round(h, 3)) == (0.5, 0.4)


def test_crop_rect_is_clamped_into_the_image(overlay):
    overlay.set_crop_rect(-0.5, -0.5, 3.0, 3.0)
    x, y, w, h = overlay.crop_rect()
    assert x >= 0 and y >= 0
    assert x + w <= 1.0001 and y + h <= 1.0001


def test_tiny_crop_is_floored_to_a_minimum(overlay):
    overlay.set_crop_rect(0.5, 0.5, 0.0, 0.0)
    _, _, w, h = overlay.crop_rect()
    assert w >= MIN_NORM and h >= MIN_NORM


def test_reset_restores_the_full_frame(overlay):
    overlay.set_crop_rect(0.2, 0.2, 0.3, 0.3)
    overlay.reset_crop()
    assert overlay.crop_rect() == (0.0, 0.0, 1.0, 1.0)


# ── geometry ─────────────────────────────────────────────────────────────

def test_image_rect_fills_a_matching_widget(overlay):
    rect = overlay.image_rect()
    assert (rect.width(), rect.height()) == (200, 100)


def test_image_rect_is_letterboxed_when_the_widget_is_larger(overlay):
    overlay.resize(400, 400)
    rect = overlay.image_rect()
    # Aspect ratio preserved, centred, never upscaled past 1:1.
    assert rect.width() == 200 and rect.height() == 100
    assert rect.x() == 100 and rect.y() == 150


def test_image_rect_is_none_without_a_pixmap(qapp):
    w = CropOverlayLabel()
    assert w.image_rect() is None


# ── mouse interaction ────────────────────────────────────────────────────

def test_dragging_on_empty_space_draws_a_new_rect(overlay):
    overlay.set_crop_enabled(True)
    _press(overlay, 20, 10)
    _move(overlay, 120, 60)
    _release(overlay, 120, 60)
    x, y, w, h = overlay.crop_rect()
    assert round(x, 2) == 0.10 and round(y, 2) == 0.10
    assert round(w, 2) == 0.50 and round(h, 2) == 0.50


def test_dragging_inside_moves_the_rect_without_resizing(overlay):
    overlay.set_crop_enabled(True)
    overlay.set_crop_rect(0.1, 0.1, 0.4, 0.4)
    _press(overlay, 60, 30)      # inside the rect
    _move(overlay, 80, 40)       # +20px x, +10px y => +0.1 in both
    _release(overlay, 80, 40)
    x, y, w, h = overlay.crop_rect()
    assert round(w, 2) == 0.40 and round(h, 2) == 0.40
    assert round(x, 2) == 0.20 and round(y, 2) == 0.20


def test_moving_cannot_push_the_rect_out_of_the_image(overlay):
    overlay.set_crop_enabled(True)
    overlay.set_crop_rect(0.5, 0.5, 0.5, 0.5)
    _press(overlay, 150, 75)
    _move(overlay, 400, 400)
    _release(overlay, 400, 400)
    x, y, w, h = overlay.crop_rect()
    assert x + w <= 1.0001 and y + h <= 1.0001


def test_dragging_a_corner_resizes(overlay):
    overlay.set_crop_enabled(True)
    overlay.set_crop_rect(0.2, 0.2, 0.6, 0.6)
    # Bottom-right corner sits at (0.8*200, 0.8*100) = (160, 80).
    _press(overlay, 160, 80)
    _move(overlay, 120, 60)
    _release(overlay, 120, 60)
    x, y, w, h = overlay.crop_rect()
    assert round(x, 2) == 0.20 and round(y, 2) == 0.20
    assert w < 0.6 and h < 0.6


def test_mouse_is_ignored_while_crop_is_disabled(overlay):
    overlay.set_crop_enabled(False)
    _press(overlay, 20, 10)
    _move(overlay, 120, 60)
    _release(overlay, 120, 60)
    assert overlay.crop_rect() == (0.0, 0.0, 1.0, 1.0)


def test_paint_does_not_raise_with_crop_enabled(overlay):
    """Exercise the painter path, including the dimmed surround and handles."""
    overlay.set_crop_enabled(True)
    overlay.set_crop_rect(0.25, 0.25, 0.5, 0.5)
    pm = QPixmap(overlay.size())
    overlay.render(pm)
