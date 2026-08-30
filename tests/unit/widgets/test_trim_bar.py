import pytest
from PIL import Image

from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from src.widgets.trim_bar import GRAB_SLOP, TrimBar


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def bar(qapp):
    b = TrimBar()
    b.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    b.show()
    b.resize(400, b.height())
    frames = [Image.new("RGB", (40, 30), (i * 8, 60, 120)) for i in range(20)]
    b.set_clip(frames, 4.0)          # 4 seconds across 400 px
    qapp.processEvents()
    return b


def _click(bar, qapp, x, kind=QEvent.Type.MouseButtonPress):
    ev = QMouseEvent(kind, QPointF(x, bar.height() / 2),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    if kind == QEvent.Type.MouseButtonPress:
        bar.mousePressEvent(ev)
    elif kind == QEvent.Type.MouseMove:
        bar.mouseMoveEvent(ev)
    else:
        bar.mouseReleaseEvent(ev)
    qapp.processEvents()


def _drag(bar, qapp, from_x, to_x):
    _click(bar, qapp, from_x)
    _click(bar, qapp, to_x, QEvent.Type.MouseMove)
    _click(bar, qapp, to_x, QEvent.Type.MouseButtonRelease)


# ── mapping ──────────────────────────────────────────────────────────────

def test_time_and_position_agree(bar):
    assert bar._time_at(0) == pytest.approx(0.0)
    assert bar._time_at(bar.width() - 1) == pytest.approx(4.0)
    assert bar._time_at(bar._x_for(1.5)) == pytest.approx(1.5, abs=0.02)


def test_a_bar_with_no_clip_does_not_divide_by_zero(qapp):
    empty = TrimBar()
    assert empty._time_at(50) == 0.0
    assert empty._x_for(3.0) == 0
    assert empty.out_point == 0.0


def test_an_open_ended_out_point_means_the_end(bar):
    bar.set_trim(0.5, 0.0)
    assert bar.out_point == pytest.approx(4.0)
    bar.set_trim(0.5, 2.5)
    assert bar.out_point == pytest.approx(2.5)


# ── dragging ─────────────────────────────────────────────────────────────

def test_dragging_the_start_handle_reports_a_new_in_point(bar, qapp):
    seen = []
    bar.start_changed.connect(seen.append)
    _drag(bar, qapp, bar._x_for(0.0), bar._x_for(1.0))
    assert seen and seen[-1] == pytest.approx(1.0, abs=0.05)


def test_dragging_the_end_handle_reports_a_new_out_point(bar, qapp):
    seen = []
    bar.end_changed.connect(seen.append)
    _drag(bar, qapp, bar._x_for(4.0), bar._x_for(3.0))
    assert seen and seen[-1] == pytest.approx(3.0, abs=0.05)


def test_the_handles_cannot_cross(bar, qapp):
    bar.set_trim(1.0, 3.0)
    _drag(bar, qapp, bar._x_for(3.0), bar._x_for(0.2))   # out point past the in
    assert bar.out_point >= bar._start

    bar.set_trim(1.0, 3.0)
    _drag(bar, qapp, bar._x_for(1.0), bar._x_for(3.9))   # in point past the out
    assert bar._start <= bar.out_point


def test_clicking_away_from_the_handles_scrubs(bar, qapp):
    bar.set_trim(0.0, 0.0)
    seen = []
    bar.playhead_changed.connect(seen.append)
    # Far from either handle, so this is a scrub rather than a grab.
    _click(bar, qapp, bar._x_for(2.0))
    assert seen and seen[-1] == pytest.approx(2.0, abs=0.05)


def test_a_press_near_a_handle_grabs_it_rather_than_scrubbing(bar, qapp):
    bar.set_trim(1.0, 3.0)
    moved = []
    bar.start_changed.connect(moved.append)
    _click(bar, qapp, bar._x_for(1.0) + GRAB_SLOP - 1)
    assert moved, "a press within the grab margin should take the handle"
