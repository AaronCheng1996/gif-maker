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

