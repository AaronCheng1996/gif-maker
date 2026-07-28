import pytest
from PIL import Image

from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.widgets.image_merge_widget import ImageMergeWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def widget(qapp):
    return ImageMergeWidget()


@pytest.fixture(autouse=True)
def _no_blocking_dialogs(monkeypatch):
    """Prevent QMessageBox popups from blocking the test run."""
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)


def _make_images(tmp_path, specs):
    """specs: list of (name, size, color) -> list of saved file paths."""
    paths = []
    for name, size, color in specs:
        p = tmp_path / name
        Image.new("RGBA", size, color).save(p)
        paths.append(str(p))
    return paths


def test_load_images_creates_staggered_entries(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [
        ("a.png", (50, 50), (255, 0, 0, 255)),
        ("b.png", (30, 30), (0, 255, 0, 255)),
        ("c.png", (20, 20), (0, 0, 255, 255)),
    ])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))

    widget.load_images()

    assert len(widget.material_manager) == 3
    assert len(widget.entries) == 3
    assert [(e.material_index, e.x, e.y) for e in widget.entries] == [
        (0, 0, 0), (1, 20, 20), (2, 40, 40)
    ]
    assert len(widget.canvas._material_items) == 3
    assert widget.images_list.count() == 3


def test_dragging_canvas_item_updates_entry_position(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [("a.png", (10, 10), (255, 0, 0, 255))])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()

    item = widget.canvas._material_items[0]
    item.setPos(77, 88)

    assert widget.entries[0].x == 77
    assert widget.entries[0].y == 88


def test_remove_selected_images_remaps_material_indices(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [
        ("a.png", (10, 10), (255, 0, 0, 255)),
        ("b.png", (20, 20), (0, 255, 0, 255)),
        ("c.png", (30, 30), (0, 0, 255, 255)),
    ])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()

    # Move entry 1 somewhere distinctive before removing entry 0.
    widget.entries[1].x, widget.entries[1].y = 111, 222

    widget.images_list.setCurrentRow(0)
    widget.remove_selected_images()

    assert len(widget.material_manager) == 2
    assert len(widget.entries) == 2
    # The old entry[1] (now entries[0]) must still reference the correct
    # (remapped) material and keep its position.
    assert widget.entries[0].x == 111 and widget.entries[0].y == 222
    assert widget.entries[0].material_index == 0
    assert widget.entries[1].material_index == 1
    assert widget.images_list.count() == 2


def test_remove_with_no_selection_warns_and_does_nothing(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [("a.png", (10, 10), (255, 0, 0, 255))])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()

    widget.images_list.clearSelection()
    widget.remove_selected_images()

    assert len(widget.entries) == 1


def test_clear_all_images_empties_everything(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [("a.png", (10, 10), (255, 0, 0, 255))])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()

    widget.clear_all_images()

    assert len(widget.entries) == 0
    assert len(widget.material_manager) == 0
    assert widget.images_list.count() == 0
    assert len(widget.canvas._material_items) == 0


def test_auto_fit_output_size_uses_bounding_box(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [
        ("a.png", (10, 10), (255, 0, 0, 255)),
        ("b.png", (20, 20), (0, 255, 0, 255)),
    ])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()
    # entries: (0,0) size 10x10 -> extends to 10,10; (20,20) size 20x20 -> extends to 40,40
    widget.auto_fit_output_size()

    assert widget.width_spinbox.value() == 40
    assert widget.height_spinbox.value() == 40


def test_auto_fit_with_no_images_warns_and_does_nothing(widget):
    original_w, original_h = widget.width_spinbox.value(), widget.height_spinbox.value()
    widget.auto_fit_output_size()
    assert widget.width_spinbox.value() == original_w
    assert widget.height_spinbox.value() == original_h


def test_export_png_with_no_images_warns_and_does_nothing(widget, tmp_path, monkeypatch):
    save_called = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: save_called.append(True) or (str(tmp_path / "x.png"), ""))
    widget.export_png()
    assert not save_called
    assert not (tmp_path / "x.png").exists()


def test_export_png_flattens_layers_bottom_to_top(widget, tmp_path, monkeypatch):
    """Two fully-opaque, same-size, overlapping images: the top (later) layer should win."""
    paths = _make_images(tmp_path, [
        ("bottom.png", (20, 20), (255, 0, 0, 255)),
        ("top.png", (20, 20), (0, 255, 0, 255)),
    ])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()
    # Force both to the exact same position so they fully overlap.
    widget.entries[0].x = widget.entries[0].y = 0
    widget.entries[1].x = widget.entries[1].y = 0
    widget.width_spinbox.setValue(20)
    widget.height_spinbox.setValue(20)

    out_path = str(tmp_path / "merged.png")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out_path, ""))
    widget.export_png()

    merged = Image.open(out_path).convert("RGBA")
    assert merged.size == (20, 20)
    assert merged.getpixel((10, 10)) == (0, 255, 0, 255)  # top layer wins


def test_export_png_adds_extension_if_missing(widget, tmp_path, monkeypatch):
    paths = _make_images(tmp_path, [("a.png", (10, 10), (255, 0, 0, 255))])
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *a, **k: (paths, ""))
    widget.load_images()

    out_path_no_ext = str(tmp_path / "merged_no_ext")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (out_path_no_ext, ""))
    widget.export_png()

    assert (tmp_path / "merged_no_ext.png").exists()
