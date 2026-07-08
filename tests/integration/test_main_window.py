from pathlib import Path

import pytest

from PyQt6.QtWidgets import QApplication
from src.main import MainWindow


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_main_window_group_manager_initialized(qapp):
    """MainWindow should start with a root CompositionGroup in group_manager."""
    from src.core.group_manager import GroupManager
    from src.core.composition_group import CompositionGroup

    window = MainWindow()
    assert isinstance(window.group_manager, GroupManager)
    assert len(window.group_manager.groups) >= 1
    assert isinstance(window.group_manager.groups[0], CompositionGroup)
    root_id = window.group_manager.get_root_group_id()
    assert root_id is not None


def test_template_save_and_apply_roundtrip(qapp):
    """Save the current composition as a template, apply it back, verify group count preserved."""
    from src.core.composition_group import FrameEntry
    from src.core.template_manager import TemplateManager

    window = MainWindow()
    # Add an entry to the root group so it has content
    root_gid = window.group_manager.get_root_group_id()
    root = window.group_manager.get_group(root_gid)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))

    groups_before = len(window.group_manager.groups)

    # Export
    tpl = TemplateManager.export_composition_template(window.group_manager)
    assert tpl["format"] == "composition_group"

    # Import back
    gm2, settings = TemplateManager.import_composition_template(tpl)
    assert len(gm2.groups) == groups_before


def test_align_respects_canvas_selection(qapp):
    """When items are selected on the Canvas tab, align buttons only touch those;
    with nothing selected, alignment still applies to every FrameEntry (default)."""
    from PIL import Image
    from src.core.composition_group import FrameEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), "a")
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (0, 255, 0, 255)), "b")

    root = window.group_manager.get_group(window.current_group_id)
    root.entries.append(FrameEntry(material_index=0, x=50, y=0))
    root.entries.append(FrameEntry(material_index=1, x=60, y=0))
    window.group_manager.update_group(window.current_group_id, root)
    window._on_group_entries_changed()

    # Only select entry index 1 on the canvas.
    window.canvas_editor.select_entry(1)
    window.align_all_left()
    assert root.entries[0].x == 50  # untouched — not selected
    assert root.entries[1].x == 0   # aligned — selected

    # With nothing selected, alignment applies to every FrameEntry again.
    window.canvas_editor.select_entry(None)
    window.align_all_left()
    assert root.entries[0].x == 0
    assert root.entries[1].x == 0


def test_canvas_and_tree_entry_selection_stay_in_sync(qapp):
    """Selecting a frame on the canvas highlights it in the tree, and vice versa."""
    from PIL import Image
    from src.core.composition_group import FrameEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), "a")
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (0, 255, 0, 255)), "b")

    root = window.group_manager.get_group(window.current_group_id)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0))
    root.entries.append(FrameEntry(material_index=1, x=5, y=5))
    window.group_manager.update_group(window.current_group_id, root)
    window._on_group_entries_changed()

    # Canvas -> tree
    window.canvas_editor.select_entry(1)
    assert window.group_composition_widget._selected_entry == (window.current_group_id, 1)

    # Tree -> canvas
    window.group_composition_widget._cmd_select_entry(window.current_group_id, 0)
    assert window.canvas_editor.selected_entry_index() == 0


def test_dragging_canvas_item_updates_model_and_refreshes_tree(qapp):
    """Dragging an item on the canvas writes x/y back into the live FrameEntry and,
    once the interaction finishes, refreshes the tree/preview without losing selection."""
    from PIL import Image
    from src.core.composition_group import FrameEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), "a")

    root = window.group_manager.get_group(window.current_group_id)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0))
    window.group_manager.update_group(window.current_group_id, root)
    window._on_group_entries_changed()

    item = window.canvas_editor._material_items[0]
    item.setSelected(True)
    item.setPos(33, 44)
    window.canvas_editor.view.item_interaction_finished.emit()

    assert root.entries[0].x == 33
    assert root.entries[0].y == 44
    assert window.canvas_editor.selected_entry_index() == 0


def test_dropping_material_on_canvas_adds_centered_frame_entry(qapp):
    """Dragging a material from the library and dropping it on the canvas should
    add a new FrameEntry to the current group, centered on the drop point."""
    from PIL import Image

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (20, 10), (255, 0, 0, 255)), "a")

    root = window.group_manager.get_group(window.current_group_id)
    assert len(root.entries) == 0

    window.canvas_editor.material_dropped.emit(0, 100, 50)

    assert len(root.entries) == 1
    new_entry = root.entries[0]
    assert new_entry.material_index == 0
    # Centered: drop point minus half the material's width/height.
    assert new_entry.x == 100 - 10
    assert new_entry.y == 50 - 5
    # Canvas should reflect the new entry too.
    assert len(window.canvas_editor._material_items) == 1


def test_export_format_combo_toggles_webp_quality_visibility(qapp):
    """WebP shows a quality spinbox; GIF/APNG hide it."""
    window = MainWindow()

    window.export_format_combo.setCurrentText("WebP")
    assert window.webp_quality_spinbox.isHidden() is False

    window.export_format_combo.setCurrentText("GIF")
    assert window.webp_quality_spinbox.isHidden() is True

    window.export_format_combo.setCurrentText("APNG")
    assert window.webp_quality_spinbox.isHidden() is True


def test_export_gif_supports_apng_and_webp_formats(qapp, tmp_path, monkeypatch):
    """export_gif() should call the matching GifBuilder method for each format
    and use the correct file extension as the save-dialog default."""
    from PIL import Image
    from PyQt6.QtWidgets import QFileDialog, QMessageBox
    from src.core.composition_group import FrameEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), "a")
    root = window.group_manager.get_group(window.current_group_id)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    window.group_manager.update_group(window.current_group_id, root)

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)

    for fmt, ext in [("GIF", "gif"), ("APNG", "png"), ("WebP", "webp")]:
        window.export_format_combo.setCurrentText(fmt)
        out_path = str(tmp_path / f"out_{fmt.lower()}.{ext}")
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, p=out_path, **k: (p, ""))
        window.export_gif()
        assert Path(out_path).exists(), f"{fmt} export did not produce a file"


def test_saving_template_generates_thumbnail_and_shows_in_list(qapp, monkeypatch):
    """Saving a template should produce a QIcon thumbnail, list it with that icon,
    and show it in the larger preview label once selected."""
    from PIL import Image
    from PyQt6.QtWidgets import QInputDialog, QMessageBox
    from src.core.composition_group import FrameEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), "a")
    root = window.group_manager.get_group(window.current_group_id)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    window.group_manager.update_group(window.current_group_id, root)

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("MyTemplate", True)))
    window.quick_save_template()

    assert "MyTemplate" in window.templates
    thumb = window.template_thumbnails.get("MyTemplate")
    assert thumb is not None and not thumb.isNull()
    assert window.template_list.count() == 1
    assert not window.template_list.item(0).icon().isNull()

    window.template_list.setCurrentRow(0)
    preview_pixmap = window.template_preview_label.pixmap()
    assert preview_pixmap is not None and not preview_pixmap.isNull()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.remove_template()
    assert "MyTemplate" not in window.template_thumbnails

