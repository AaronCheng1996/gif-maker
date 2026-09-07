"""Tests for the Batch Processor tab's frame-folder source.

A sprite sheet is split into tiles; a folder of frames is already cut up and is
divided by a naming rule instead. The two sources share the template, output and
palette settings, so most of this is about the tab showing the right half and
validating whichever one is on.
"""
import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from src.core.composition_group import CompositionGroup, FrameEntry
from src.core.group_manager import GroupManager
from src.core.template_manager import TemplateManager
from src.widgets.batch_processor_widget import BatchProcessorWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _template(**group_kw):
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="org", default_duration_ms=100, **group_kw))
    gm.set_root_group_id(gid)
    return TemplateManager.export_composition_template(gm)


def _bound_template():
    return _template(source_pattern="*_org*")


def _indexed_template(n):
    gm = GroupManager()
    root = CompositionGroup(name="Root", default_duration_ms=100)
    for i in range(n):
        root.entries.append(FrameEntry(material_index=i))
    gm.set_root_group_id(gm.add_group(root))
    return TemplateManager.export_composition_template(gm)


@pytest.fixture()
def frames_dir(tmp_path):
    folder = tmp_path / "frames"
    folder.mkdir()
    for unit, count in (("dh01", 3), ("dh02", 2)):
        for i in range(1, count + 1):
            Image.new("RGB", (8, 8), (i * 40, 0, 0)).save(folder / f"{unit}_org{i:02d}.png")
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    Image.new("RGB", (8, 8), (1, 1, 1)).save(folder / "stray.png")
    return folder


@pytest.fixture()
def widget(qapp, frames_dir):
    w = BatchProcessorWidget()
    w.set_templates({"bound": _bound_template()})
    w.template_combo.setCurrentIndex(w.template_combo.count() - 1)
    w.same_dir_checkbox.setChecked(True)
    w.frames_dir = frames_dir
    yield w


def _use_folder(widget, pattern=r"(?P<unit>dh\d+)_"):
    widget.folder_source_radio.setChecked(True)
    widget.frames_dir_edit.setText(str(widget.frames_dir))
    widget.unit_pattern_edit.setText(pattern)
    widget.rescan_frame_folder()


# ── Which half of the tab is showing ─────────────────────────────────────────

def test_sprite_sheets_are_the_default_source(widget):
    assert not widget.is_frame_folder_source()


def test_choosing_a_folder_swaps_the_panels(widget):
    widget.folder_source_radio.setChecked(True)

    assert widget.is_frame_folder_source()
    assert widget.folder_source_panel.isVisibleTo(widget)
    assert not widget.sheet_source_panel.isVisibleTo(widget)


def test_the_tile_split_settings_belong_to_sprite_sheets(widget):
    """A folder of frames arrives already cut up; splitting it means nothing."""
    widget.folder_source_radio.setChecked(True)
    assert not widget.split_group.isVisibleTo(widget)

    widget.sheet_source_radio.setChecked(True)
    assert widget.split_group.isVisibleTo(widget)


# ── Scanning, before anything is built ───────────────────────────────────────

def test_scanning_lists_the_units_the_rule_finds(widget):
    _use_folder(widget)

    assert widget.unit_list.count() == 2
    assert widget.unit_list.item(0).text().startswith("dh01")
    assert "3 frame(s)" in widget.unit_list.item(0).text()


def test_the_summary_says_what_the_rule_left_out(widget):
    _use_folder(widget)
    assert "1 skipped" in widget.unit_count_label.text(), "stray.png matched no unit"


def test_a_different_rule_gives_a_different_split(widget):
    _use_folder(widget, r"(?P<unit>dh)\d+_")
    assert [widget.unit_list.item(i).text().split()[0]
            for i in range(widget.unit_list.count())] == ["dh"]


def test_no_rule_makes_the_folder_one_unit(widget):
    _use_folder(widget, "")
    assert widget.unit_list.count() == 1
    assert widget.unit_list.item(0).text().startswith("frames")


def test_a_broken_rule_is_reported_where_it_was_typed(widget):
    _use_folder(widget, "(?P<unit>")

    assert "Invalid naming rule" in widget.unit_count_label.text()
    assert widget.unit_list.count() == 0
    assert not widget.process_btn.isEnabled()


def test_an_empty_folder_field_clears_the_list(widget):
    _use_folder(widget)
    widget.frames_dir_edit.setText("")
    widget.rescan_frame_folder()

    assert widget.unit_list.count() == 0
    assert widget.frame_scan is None


def test_a_folder_that_does_not_exist_is_reported(widget, tmp_path):
    widget.folder_source_radio.setChecked(True)
    widget.frames_dir_edit.setText(str(tmp_path / "nope"))
    widget.rescan_frame_folder()

    assert "Not a folder" in widget.unit_count_label.text()


# ── Validation ───────────────────────────────────────────────────────────────

def test_a_scanned_folder_with_a_template_validates(widget):
    _use_folder(widget)

    assert widget.validate_settings()
    assert "2 GIF(s) from 5 frame(s)" in widget.validation_label.text()


def test_validation_mentions_the_files_the_rule_skipped(widget):
    _use_folder(widget)
    widget.validate_settings()
    assert "skipped by the unit rule" in widget.validation_label.text()


def test_nothing_scanned_does_not_validate(widget):
    widget.folder_source_radio.setChecked(True)
    assert not widget.validate_settings()
    assert "check the unit rule" in widget.validation_label.text()


def test_a_template_needing_more_materials_than_a_unit_has_is_caught(widget):
    """A bound template needs none; one built from indices needs that many."""
    widget.set_templates({"indexed": _indexed_template(3)})
    widget.template_combo.setCurrentIndex(widget.template_combo.count() - 1)
    _use_folder(widget)

    assert not widget.validate_settings()
    assert "dh02" in widget.validation_label.text(), "the 2-frame unit is short"


def test_a_missing_output_directory_is_caught(widget, tmp_path):
    _use_folder(widget)
    widget.same_dir_checkbox.setChecked(False)
    widget.output_dir_edit.setText(str(tmp_path / "nope"))

    assert not widget.validate_settings()
    assert "does not exist" in widget.validation_label.text()


# ── Buttons follow the source that is showing ────────────────────────────────

def test_processing_stays_off_until_a_folder_has_units(widget):
    widget.folder_source_radio.setChecked(True)
    assert not widget.process_btn.isEnabled()

    _use_folder(widget)
    assert widget.process_btn.isEnabled()


def test_images_added_for_the_other_source_do_not_enable_a_folder_run(widget):
    widget.image_paths = ["a.png"]
    widget.folder_source_radio.setChecked(True)
    assert not widget.process_btn.isEnabled()


def test_the_gif_preview_is_for_sprite_sheets_only(widget):
    """It renders one sheet; a folder has no single sheet to render."""
    _use_folder(widget)
    assert not widget._gen_preview_btn.isEnabled()


def test_switching_source_clears_a_stale_verdict(widget):
    _use_folder(widget)
    widget.validate_settings()
    assert widget.validation_label.text()

    widget.sheet_source_radio.setChecked(True)
    assert widget.validation_label.text() == ""


# ── A long run has to be stoppable ───────────────────────────────────────────

def test_stopping_with_no_run_in_flight_is_a_no_op(widget):
    widget.stop_workers()      # must not raise before anything has started


def test_cancelling_stops_a_batch_between_units(tmp_path):
    """A folder can hold dozens of units, so quitting during a run is ordinary."""
    from src.core.batch_processor import BatchProcessor

    folder = tmp_path / "frames"
    folder.mkdir()
    for unit in ("dh01", "dh02", "dh03"):
        Image.new("RGB", (8, 8), (10, 10, 10)).save(folder / f"{unit}_org01.png")

    bp = BatchProcessor()
    started = []

    def on_progress(current, total, message):
        started.append(message)
        if message.startswith("Done"):
            bp.cancel()

    bp.set_progress_callback(on_progress)
    ok, failed = bp.process_frame_folder(
        str(folder), r"(?P<unit>dh\d+)_", _bound_template(),
        output_directory=str(tmp_path / "out"), output_width=8, output_height=8)

    assert len(ok) == 1, "the unit in flight finishes, the rest do not start"
    assert failed == []
    assert "Cancelled" in started
