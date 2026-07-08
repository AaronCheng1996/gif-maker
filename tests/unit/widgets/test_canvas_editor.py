import pytest
from PIL import Image

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF, Qt, QMimeData
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QEvent

from src.widgets.canvas_editor import CanvasEditorWidget, MIN_ZOOM, MAX_ZOOM, MATERIAL_INDEX_MIME_TYPE
from src.core.image_loader import MaterialManager
from src.core.composition_group import FrameEntry, SubGroupEntry


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def canvas(qapp):
    return CanvasEditorWidget()


def test_default_output_size_and_scene_content(canvas):
    """The output rect item should start at the default 400x400 size, rooted at origin."""
    rect = canvas.output_rect()
    assert rect.x() == 0 and rect.y() == 0
    assert rect.width() == 400 and rect.height() == 400
    assert canvas.output_rect_item in canvas.scene.items()


def test_set_output_size_resizes_rect_and_scene(canvas):
    canvas.set_output_size(128, 64)
    rect = canvas.output_rect()
    assert (rect.width(), rect.height()) == (128, 64)
    # Scene should be padded well beyond the output bounds to allow panning.
    scene_rect = canvas.scene.sceneRect()
    assert scene_rect.width() > 128
    assert scene_rect.height() > 64


def test_set_output_size_rejects_non_positive_values(canvas):
    canvas.set_output_size(0, -5)
    rect = canvas.output_rect()
    assert rect.width() >= 1 and rect.height() >= 1


def test_zoom_starts_at_100_percent(canvas):
    assert canvas.zoom_percent() == pytest.approx(100.0)


def test_zoom_by_scales_and_updates_label(canvas):
    canvas.zoom_by(2.0)
    assert canvas.zoom_percent() == pytest.approx(200.0)
    assert canvas.zoom_label.text() == "200%"

    canvas.zoom_by(0.5)
    assert canvas.zoom_percent() == pytest.approx(100.0)


def test_zoom_is_clamped_to_min_and_max(canvas):
    for _ in range(30):
        canvas.zoom_by(0.5)
    assert canvas.view.current_zoom() == pytest.approx(MIN_ZOOM, rel=1e-3)

    for _ in range(30):
        canvas.zoom_by(2.0)
    assert canvas.view.current_zoom() == pytest.approx(MAX_ZOOM, rel=1e-3)


def test_reset_view_restores_100_percent(canvas):
    canvas.zoom_by(3.0)
    canvas.reset_view()
    assert canvas.zoom_percent() == pytest.approx(100.0)


def test_coordinate_transform_round_trip(canvas):
    """view -> scene -> view should return (approximately) the original point."""
    original = QPointF(37, 52).toPoint()
    scene_pt = canvas.view_to_scene(original)
    back_to_view = canvas.scene_to_view(scene_pt)
    assert abs(back_to_view.x() - original.x()) <= 1
    assert abs(back_to_view.y() - original.y()) <= 1


def test_coordinate_transform_scales_with_zoom(canvas):
    """At 2x zoom, moving 1 scene unit should map to 2 view pixels (approximately)."""
    canvas.zoom_by(2.0)
    p0 = canvas.scene_to_view(QPointF(0, 0))
    p1 = canvas.scene_to_view(QPointF(10, 0))
    assert abs((p1.x() - p0.x()) - 20) <= 1


def test_mouse_scene_pos_changed_updates_coords_label(canvas):
    canvas.view.mouse_scene_pos_changed.emit(QPointF(12, 34))
    assert canvas.coords_label.text() == "x: 12, y: 34"


@pytest.fixture()
def material_manager():
    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (10, 20), (255, 0, 0, 255)), "red")
    mm.add_material(Image.new("RGBA", (30, 5), (0, 255, 0, 255)), "green")
    return mm


def test_set_entries_renders_frame_entries_at_their_offsets(canvas, material_manager):
    entries = [
        FrameEntry(material_index=0, x=10, y=20),
        FrameEntry(material_index=1, x=-5, y=0),
    ]
    canvas.set_entries(entries, material_manager)
    assert len(canvas._material_items) == 2
    assert canvas._material_items[0].pos().x() == 10
    assert canvas._material_items[0].pos().y() == 20
    assert canvas._material_items[1].pos().x() == -5
    assert canvas._material_items[0].pixmap().size().width() == 10
    assert canvas._material_items[0].pixmap().size().height() == 20


def test_set_entries_skips_non_frame_entries(canvas, material_manager):
    entries = [
        FrameEntry(material_index=0, x=0, y=0),
        SubGroupEntry(group_id=0),
    ]
    canvas.set_entries(entries, material_manager)
    assert len(canvas._material_items) == 1
    assert canvas._material_items[0].entry_index == 0


def test_set_entries_clears_previous_items(canvas, material_manager):
    canvas.set_entries([FrameEntry(material_index=0, x=0, y=0)], material_manager)
    assert len(canvas._material_items) == 1
    canvas.set_entries([], material_manager)
    assert len(canvas._material_items) == 0
    # Output rect must survive clearing material items.
    assert canvas.output_rect_item in canvas.scene.items()


def test_selecting_item_emits_entry_selected(canvas, material_manager, qapp):
    entries = [FrameEntry(material_index=0, x=0, y=0), FrameEntry(material_index=1, x=5, y=5)]
    canvas.set_entries(entries, material_manager)

    received = []
    canvas.entry_selected.connect(received.append)

    canvas._material_items[1].setSelected(True)
    assert received[-1] == 1
    assert canvas.selected_entry_index() == 1

    canvas.scene.clearSelection()
    assert received[-1] == -1
    assert canvas.selected_entry_index() is None


def test_select_entry_programmatically_selects_matching_item(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0), FrameEntry(material_index=1, x=5, y=5)]
    canvas.set_entries(entries, material_manager)

    canvas.select_entry(1)
    assert canvas.selected_entry_index() == 1
    assert canvas._material_items[0].isSelected() is False
    assert canvas._material_items[1].isSelected() is True

    canvas.select_entry(None)
    assert canvas.selected_entry_index() is None


def test_dragging_item_writes_offset_back_to_live_entry(canvas, material_manager):
    """Moving an item (simulating a drag) should mutate the FrameEntry in place."""
    entries = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries, material_manager)

    item = canvas._material_items[0]
    item.setPos(42, -17)

    assert entries[0].x == 42
    assert entries[0].y == -17


def test_entries_edited_fires_once_after_drag_finishes(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries, material_manager)

    received = []
    canvas.entries_edited.connect(lambda: received.append(True))

    item = canvas._material_items[0]
    item.setPos(10, 10)   # simulates in-progress drag movement
    item.setPos(20, 20)
    assert received == []  # not yet — only on interaction-finished (mouse release)

    canvas.view.item_interaction_finished.emit()
    assert len(received) == 1
    assert entries[0].x == 20 and entries[0].y == 20

    # A release with no pending change should not fire again.
    canvas.view.item_interaction_finished.emit()
    assert len(received) == 1


def test_set_entries_preserves_selection_for_same_group_rerender(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0), FrameEntry(material_index=1, x=5, y=5)]
    canvas.set_entries(entries, material_manager)
    canvas.select_entry(1)

    # Re-render with the *same* entries list (as _refresh_canvas does after a drag).
    canvas.set_entries(entries, material_manager)
    assert canvas.selected_entry_index() == 1


def test_set_entries_clears_selection_when_switching_groups(canvas, material_manager):
    entries_a = [FrameEntry(material_index=0, x=0, y=0), FrameEntry(material_index=1, x=5, y=5)]
    canvas.set_entries(entries_a, material_manager)
    canvas.select_entry(1)

    entries_b = [FrameEntry(material_index=0, x=1, y=1)]
    canvas.set_entries(entries_b, material_manager)
    assert canvas.selected_entry_index() is None


def _make_key_event(key, modifiers=Qt.KeyboardModifier.NoModifier):
    return QKeyEvent(QEvent.Type.KeyPress, key, modifiers)


def test_arrow_key_nudges_selected_item_by_1px(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=10, y=10)]
    canvas.set_entries(entries, material_manager)
    canvas.select_entry(0)

    canvas.view.keyPressEvent(_make_key_event(Qt.Key.Key_Right))
    assert entries[0].x == 11
    assert entries[0].y == 10


def test_shift_arrow_key_nudges_selected_item_by_10px(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=10, y=10)]
    canvas.set_entries(entries, material_manager)
    canvas.select_entry(0)

    canvas.view.keyPressEvent(_make_key_event(Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier))
    assert entries[0].y == 20
    assert entries[0].x == 10


def test_arrow_key_nudge_emits_entries_edited(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries, material_manager)
    canvas.select_entry(0)

    received = []
    canvas.entries_edited.connect(lambda: received.append(True))
    canvas.view.keyPressEvent(_make_key_event(Qt.Key.Key_Left))
    assert len(received) == 1
    assert entries[0].x == -1


def test_arrow_key_with_no_selection_does_nothing(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=5, y=5)]
    canvas.set_entries(entries, material_manager)
    # Nothing selected — the key event should be a no-op for the model.
    canvas.view.keyPressEvent(_make_key_event(Qt.Key.Key_Right))
    assert entries[0].x == 5


def test_snap_to_grid_rounds_position_when_enabled(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries, material_manager)
    canvas.set_snap_enabled(True)
    canvas.set_snap_size(10)

    item = canvas._material_items[0]
    item.setPos(23, 47)
    assert entries[0].x == 20
    assert entries[0].y == 50


def test_snap_disabled_keeps_exact_position(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries, material_manager)
    assert canvas.is_snap_enabled() is False

    item = canvas._material_items[0]
    item.setPos(23, 47)
    assert entries[0].x == 23
    assert entries[0].y == 47


def test_snap_checkbox_and_spinbox_reflect_programmatic_changes(canvas):
    canvas.set_snap_enabled(True)
    assert canvas.snap_checkbox.isChecked() is True

    canvas.set_snap_size(25)
    assert canvas.snap_size_spinbox.value() == 25
    assert canvas.snap_size() == 25


def test_selected_entry_indices_returns_all_selected_sorted(canvas, material_manager):
    entries = [
        FrameEntry(material_index=0, x=0, y=0),
        FrameEntry(material_index=1, x=1, y=1),
    ]
    canvas.set_entries(entries, material_manager)
    canvas._material_items[1].setSelected(True)
    canvas._material_items[0].setSelected(True)
    assert canvas.selected_entry_indices() == [0, 1]


def test_view_uses_rubber_band_drag_mode(canvas):
    from PyQt6.QtWidgets import QGraphicsView
    assert canvas.view.dragMode() == QGraphicsView.DragMode.RubberBandDrag


def _make_five_entry_scene(canvas, material_manager):
    entries = [FrameEntry(material_index=0, x=i * 10, y=0) for i in range(5)]
    canvas.set_entries(entries, material_manager)
    return entries


def test_onion_skin_disabled_by_default_no_tint(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.select_entry(2)
    assert all(item.onion_tint is None for item in canvas._material_items)


def test_onion_skin_tints_neighbors_red_and_green(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.set_onion_skin_enabled(True)
    canvas.set_onion_skin_range(1)
    canvas.select_entry(2)

    by_index = {item.entry_index: item for item in canvas._material_items}
    assert by_index[2].onion_tint is None       # selected — no tint
    assert by_index[1].onion_tint is not None   # previous — red
    assert by_index[1].onion_tint.red() > by_index[1].onion_tint.green()
    assert by_index[3].onion_tint is not None   # next — green
    assert by_index[3].onion_tint.green() > by_index[3].onion_tint.red()
    assert by_index[0].onion_tint is None       # out of range
    assert by_index[4].onion_tint is None       # out of range


def test_onion_skin_range_extends_tinting_and_fades_with_distance(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.set_onion_skin_enabled(True)
    canvas.set_onion_skin_range(2)
    canvas.select_entry(2)

    by_index = {item.entry_index: item for item in canvas._material_items}
    assert by_index[0].onion_tint is not None
    assert by_index[4].onion_tint is not None
    # The farther neighbor should be more faded (lower alpha) than the closer one.
    assert by_index[0].onion_alpha < by_index[1].onion_alpha
    assert by_index[4].onion_alpha < by_index[3].onion_alpha


def test_onion_skin_clears_when_disabled(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.set_onion_skin_enabled(True)
    canvas.select_entry(2)
    assert any(item.onion_tint is not None for item in canvas._material_items)

    canvas.set_onion_skin_enabled(False)
    assert all(item.onion_tint is None for item in canvas._material_items)


def test_onion_skin_checkbox_and_spinboxes_reflect_programmatic_changes(canvas):
    canvas.set_onion_skin_enabled(True)
    assert canvas.onion_checkbox.isChecked() is True

    canvas.set_onion_skin_opacity(0.5)
    assert canvas.onion_opacity_spinbox.value() == 50
    assert canvas.onion_skin_opacity() == pytest.approx(0.5)

    canvas.set_onion_skin_range(3)
    assert canvas.onion_range_spinbox.value() == 3
    assert canvas.onion_skin_range() == 3


def test_select_next_and_previous_entry_step_through_order(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.select_entry(0)

    canvas.select_next_entry()
    assert canvas.selected_entry_index() == 1

    canvas.select_next_entry()
    assert canvas.selected_entry_index() == 2

    canvas.select_previous_entry()
    assert canvas.selected_entry_index() == 1


def test_select_next_entry_clamps_at_last_index(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.select_entry(4)
    canvas.select_next_entry()
    assert canvas.selected_entry_index() == 4  # clamped, no wraparound


def test_select_previous_entry_clamps_at_first_index(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.select_entry(0)
    canvas.select_previous_entry()
    assert canvas.selected_entry_index() == 0  # clamped, no wraparound


def test_select_next_entry_with_no_selection_selects_first(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.select_next_entry()
    assert canvas.selected_entry_index() == 0


class _FakeDropEvent:
    """Minimal duck-typed stand-in for QDropEvent — dropEvent() only needs
    mimeData()/position()/acceptProposedAction()/ignore()."""

    def __init__(self, mime_data: QMimeData, position: QPointF):
        self._mime = mime_data
        self._position = position
        self.accepted = False
        self.ignored = False

    def mimeData(self):
        return self._mime

    def position(self):
        return self._position

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def test_drop_emits_material_dropped_with_scene_coordinates(canvas):
    mime = QMimeData()
    mime.setData(MATERIAL_INDEX_MIME_TYPE, b"3")
    event = _FakeDropEvent(mime, QPointF(10, 20))

    received = []
    canvas.material_dropped.connect(lambda idx, x, y: received.append((idx, x, y)))
    canvas.view.dropEvent(event)

    assert event.accepted is True
    assert len(received) == 1
    assert received[0][0] == 3


def test_drop_with_invalid_material_index_is_ignored(canvas):
    mime = QMimeData()
    mime.setData(MATERIAL_INDEX_MIME_TYPE, b"not-a-number")
    event = _FakeDropEvent(mime, QPointF(0, 0))

    received = []
    canvas.material_dropped.connect(lambda *a: received.append(a))
    canvas.view.dropEvent(event)

    assert received == []
    assert event.ignored is True


def test_sync_timeline_ui_reflects_entry_count_and_selection(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    assert canvas.frame_slider.maximum() == 4
    assert canvas.frame_label.text() == "Frame: 0/5"

    canvas.select_entry(2)
    assert canvas.frame_slider.value() == 2
    assert canvas.frame_label.text() == "Frame: 3/5"


def test_dragging_frame_slider_selects_matching_entry(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.frame_slider.setValue(3)
    assert canvas.selected_entry_index() == 3


def test_play_button_disabled_with_no_entries(canvas):
    assert canvas.play_btn.isEnabled() is False


def test_play_playback_selects_first_entry_and_toggles_button(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    assert canvas.is_playing() is False

    canvas.play_playback()
    assert canvas.is_playing() is True
    assert canvas.play_btn.text() == "⏸"
    assert canvas.selected_entry_index() == 0

    canvas.pause_playback()
    assert canvas.is_playing() is False
    assert canvas.play_btn.text() == "▶"


def test_toggle_playback_flips_state(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.toggle_playback()
    assert canvas.is_playing() is True
    canvas.toggle_playback()
    assert canvas.is_playing() is False


def test_advance_playback_steps_through_entries_and_wraps(canvas, material_manager):
    _make_five_entry_scene(canvas, material_manager)
    canvas.play_playback()  # selects entry 0

    canvas._advance_playback()
    assert canvas.selected_entry_index() == 1
    canvas._advance_playback()
    assert canvas.selected_entry_index() == 2
    canvas._advance_playback()
    assert canvas.selected_entry_index() == 3
    canvas._advance_playback()
    assert canvas.selected_entry_index() == 4
    canvas._advance_playback()  # wraps back to the start, unlike select_next_entry()
    assert canvas.selected_entry_index() == 0


def test_schedule_next_frame_uses_entry_duration(canvas, material_manager):
    entries = [
        FrameEntry(material_index=0, x=0, y=0, duration_ms=250),
        FrameEntry(material_index=0, x=0, y=0, duration_ms=80),
    ]
    canvas.set_entries(entries, material_manager)
    canvas.select_entry(0)
    canvas._schedule_next_frame()
    assert canvas._play_timer.interval() == 250

    canvas.select_entry(1)
    canvas._schedule_next_frame()
    assert canvas._play_timer.interval() == 80


def test_switching_groups_stops_playback(canvas, material_manager):
    entries_a = _make_five_entry_scene(canvas, material_manager)
    canvas.play_playback()
    assert canvas.is_playing() is True

    entries_b = [FrameEntry(material_index=0, x=0, y=0)]
    canvas.set_entries(entries_b, material_manager)
    assert canvas.is_playing() is False
