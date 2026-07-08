import pytest
from PIL import Image

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QPointF

from src.widgets.canvas_editor import CanvasEditorWidget, MIN_ZOOM, MAX_ZOOM
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
