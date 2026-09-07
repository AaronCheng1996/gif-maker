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


def test_image_merge_tab_is_wired_into_main_window(qapp):
    """The Image Merge tab should be present as its own independent tool tab."""
    from src.widgets.image_merge_widget import ImageMergeWidget

    window = MainWindow()
    assert isinstance(window.image_merge, ImageMergeWidget)
    # By identity, not by position: the tabs get reordered.
    index = window.tool_tabs.indexOf(window.image_merge)
    assert index >= 0
    assert window.tool_tabs.widget(index) is window.image_merge

    # Switching to and away from it shouldn't touch the shared material library panel.
    window._on_tool_tab_changed(index)
    assert window._material_lib_panel.isHidden()


def test_spine_to_gif_tab_is_wired_into_main_window(qapp):
    """The Spine to GIF tab exists and starts in a disabled, no-project state."""
    from src.widgets.spine_to_gif_widget import SpineToGifWidget

    window = MainWindow()
    assert isinstance(window.spine_to_gif, SpineToGifWidget)
    assert window.tool_tabs.indexOf(window.spine_to_gif) >= 0

    tab = window.spine_to_gif
    assert tab.project is None
    assert tab.export_btn.isEnabled() is False
    assert tab.animation_list.count() == 0

    window._on_tool_tab_changed(window.tool_tabs.indexOf(tab))
    assert window._material_lib_panel.isHidden()
    tab.stop_workers()


    # Loading a project and exporting is covered in tests/unit/widgets, against the
    # widget directly — building extra MainWindows there just to drive render
    # threads is wasteful and destabilises the Qt event loop across tests.


def test_every_tab_name_has_a_translation(qapp):
    """A rename that forgets i18n leaves a tab in English for zh users, which
    nothing else in the suite would notice."""
    from src.i18n import set_language, tr

    window = MainWindow()                      # built while the language is en,
    labels = [window.tool_tabs.tabText(i)      # so these are the lookup keys
              for i in range(window.tool_tabs.count())]
    set_language("zh_TW")
    try:
        untranslated = [t for t in labels if tr(t) == t]
        assert not untranslated, f"no zh_TW translation for: {untranslated}"
    finally:
        set_language("en")


def test_the_tabs_run_from_assembling_to_shrinking(qapp):
    """Order is meaning here: work travels left to right, and the tools that
    shrink a finished file sit at the end."""
    window = MainWindow()
    order = [window.tool_tabs.indexOf(w) for w in (
        window._composer_splitter, window.image_merge, window.spine_to_gif,
        window.crop_gif, window.video_concat, window.gif_to_mp4)]
    assert order == sorted(order), f"tabs are out of stage order: {order}"


# ── Add to Group picker: where it opens ──────────────────────────────────────

def _window_with_a_material():
    """A MainWindow with one material, selected in the library list."""
    from PIL import Image

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (8, 8), (255, 0, 0, 255)), "a")
    window.refresh_materials_list()
    window.materials_list.setCurrentRow(0)
    return window


@pytest.fixture()
def picker(monkeypatch):
    """Answer the Add to Group dialog, recording what it was opened on.

    Returns (calls, reply): append-only record of each dialog, and a dict whose
    "row" says which group the next one picks."""
    from src.main_window import materials_panel_mixin as mpm

    calls = []
    reply = {"row": 0}

    def get_item(_parent, _title, _label, items, current, _editable, *a, **k):
        calls.append({"items": list(items), "current": current})
        return items[reply["row"]], True

    monkeypatch.setattr(mpm.QInputDialog, "getItem", get_item)
    return calls, reply


def test_the_group_picker_opens_on_the_selected_group(qapp, picker):
    """Nothing added yet, so the ★ group is the best guess — and it is what the
    button's own label promises."""
    from src.core.composition_group import CompositionGroup

    calls, _reply = picker
    window = _window_with_a_material()
    walk = window.group_manager.add_group(CompositionGroup(name="Walk"))
    window.current_group_id = walk

    window.add_materials_to_existing_group()

    assert calls[0]["current"] == walk


def test_the_group_picker_remembers_where_the_last_batch_went(qapp, picker):
    from src.core.composition_group import CompositionGroup

    calls, reply = picker
    window = _window_with_a_material()
    walk = window.group_manager.add_group(CompositionGroup(name="Walk"))
    reply["row"] = walk
    window.add_materials_to_existing_group()

    window.current_group_id = window.group_manager.get_root_group_id()
    window.add_materials_to_existing_group()

    assert calls[1]["current"] == walk
    assert len(window.group_manager.get_group(walk).entries) == 2


def test_a_remembered_group_that_is_gone_is_not_trusted(qapp, picker):
    """Group ids are list positions, so a deletion can leave the remembered one
    pointing past the end."""
    from src.core.composition_group import CompositionGroup

    calls, reply = picker
    window = _window_with_a_material()
    walk = window.group_manager.add_group(CompositionGroup(name="Walk"))
    reply["row"] = walk
    window.add_materials_to_existing_group()

    window.group_manager.remove_group(walk)
    window.current_group_id = window.group_manager.get_root_group_id()
    reply["row"] = 0
    window.add_materials_to_existing_group()

    assert calls[1]["current"] == window.group_manager.get_root_group_id()


def test_cancelling_the_group_picker_changes_nothing(qapp, monkeypatch):
    from src.main_window import materials_panel_mixin as mpm

    window = _window_with_a_material()
    monkeypatch.setattr(mpm.QInputDialog, "getItem", lambda *a, **k: ("", False))

    window.add_materials_to_existing_group()

    assert window.last_add_group_id is None
    assert window.group_manager.get_group(window.current_group_id).entries == []


def test_two_groups_sharing_a_name_go_to_the_row_that_was_picked(qapp, picker):
    """The dialog answers with text, so the labels carry the id as well."""
    from src.core.composition_group import CompositionGroup

    calls, reply = picker
    window = _window_with_a_material()
    first = window.group_manager.add_group(CompositionGroup(name="Idle"))
    second = window.group_manager.add_group(CompositionGroup(name="Idle"))
    reply["row"] = second

    window.add_materials_to_existing_group()

    assert calls[0]["items"][second] == f"[{second}] Idle"
    assert len(window.group_manager.get_group(second).entries) == 1
    assert window.group_manager.get_group(first).entries == []


def test_auto_fit_sizes_a_bound_group(qapp):
    """Auto used to report 'no materials' for a group bound to a glob: it has
    no entries, and the size was measured by walking them."""
    from PIL import Image
    from src.core.composition_group import CompositionGroup

    window = MainWindow()
    for name, size in [("dh01_idle01", (40, 90)), ("dh01_org01", (96, 253)),
                       ("dh01_org02", (97, 257))]:
        window.material_manager.add_material(Image.new("RGBA", size), name=name)

    gid = window.group_manager.add_group(
        CompositionGroup(name="org", source_pattern="*_org*"))
    window.current_group_id = gid

    assert window.get_all_materials_max_size() == (97, 257)

    window.auto_fit_output_size()
    assert (window.width_spinbox.value(), window.height_spinbox.value()) == (97, 257)


def test_auto_fit_sizes_a_root_made_of_sub_group_references(qapp):
    """Same blind spot: a root holding only references has no frame of its own."""
    from PIL import Image
    from src.core.composition_group import CompositionGroup, SubGroupEntry

    window = MainWindow()
    window.material_manager.add_material(Image.new("RGBA", (70, 25)), name="a_org01")

    child = window.group_manager.add_group(
        CompositionGroup(name="org", source_pattern="*_org*"))
    root_gid = window.group_manager.get_root_group_id()
    window.group_manager.get_group(root_gid).entries.append(
        SubGroupEntry(group_id=child, x=5, y=0))
    window.current_group_id = root_gid

    window.auto_fit_output_size()
    assert (window.width_spinbox.value(), window.height_spinbox.value()) == (75, 25)
