"""Tests for grouping a folder of exported frames into one unit per output.

A sprite sheet carries its own structure — split it and the tiles arrive in a
known order. A folder of frames carries that structure in the file names, and
every project spells it differently, so the rule is a regex the user supplies.
"""
import pytest
from PIL import Image

from src.core.frame_set import (
    FrameSetError, compile_unit_pattern, scan_frame_folder, unit_of,
)

DH = r"(?P<unit>s?dh\d+(?:_sleep)?)_"


def _folder(tmp_path, *names, subdir=None):
    root = tmp_path / (subdir or "")
    root.mkdir(parents=True, exist_ok=True)
    for n in names:
        Image.new("RGB", (4, 4), (10, 20, 30)).save(root / n)
    return tmp_path


# ── Reading a unit out of one name ───────────────────────────────────────────

def test_the_named_group_says_which_output_a_file_belongs_to():
    assert unit_of("dh01_org01", compile_unit_pattern(DH)) == "dh01"


def test_a_greedy_optional_part_keeps_neighbours_apart():
    """dh03 and dh03_sleep share a prefix; anchoring plus greed separates them."""
    rule = compile_unit_pattern(DH)
    assert unit_of("dh03_org01", rule) == "dh03"
    assert unit_of("dh03_sleep_org01", rule) == "dh03_sleep"


def test_a_rule_without_a_named_group_falls_back_to_its_first_capture():
    assert unit_of("dh01_org01", compile_unit_pattern(r"(dh\d+)_")) == "dh01"


def test_a_rule_that_captures_nothing_uses_the_whole_match():
    assert unit_of("dh01_org01", compile_unit_pattern(r"dh\d+")) == "dh01"


def test_a_name_the_rule_does_not_claim_has_no_unit():
    assert unit_of("h_f_unknown", compile_unit_pattern(DH)) is None


def test_the_rule_is_anchored_at_the_start_of_the_name():
    """Otherwise a stray prefix would quietly join a unit it is not part of."""
    assert unit_of("copy_of_dh01_org01", compile_unit_pattern(DH)) is None


def test_no_rule_puts_everything_in_one_unit():
    assert unit_of("anything", None) == ""


def test_a_broken_regex_is_reported_rather_than_raised_raw():
    with pytest.raises(FrameSetError, match="Invalid naming rule"):
        compile_unit_pattern("(?P<unit>")


def test_a_blank_rule_is_the_same_as_no_rule():
    assert compile_unit_pattern("   ") is None


# ── Scanning a folder ────────────────────────────────────────────────────────

def test_files_are_grouped_into_one_unit_per_match(tmp_path):
    _folder(tmp_path, "dh01_org01.png", "dh01_org02.png", "dh02_org01.png")
    scan = scan_frame_folder(str(tmp_path), DH)

    assert [u.unit for u in scan.units] == ["dh01", "dh02"]
    assert [len(u) for u in scan.units] == [2, 1]


def test_frames_inside_a_unit_are_in_natural_order(tmp_path):
    _folder(tmp_path, "dh01_org10.png", "dh01_org02.png", "dh01_org01.png")
    scan = scan_frame_folder(str(tmp_path), DH)

    assert [p.stem for p in scan.units[0].paths] == \
        ["dh01_org01", "dh01_org02", "dh01_org10"]


def test_units_are_in_natural_order(tmp_path):
    _folder(tmp_path, "dh10_org01.png", "dh02_org01.png")
    scan = scan_frame_folder(str(tmp_path), DH)
    assert [u.unit for u in scan.units] == ["dh02", "dh10"]


def test_files_the_rule_does_not_claim_are_skipped_not_dropped_silently(tmp_path):
    _folder(tmp_path, "dh01_org01.png", "h_f_unknown.png")
    scan = scan_frame_folder(str(tmp_path), DH)

    assert [u.unit for u in scan.units] == ["dh01"]
    assert [p.name for p in scan.skipped] == ["h_f_unknown.png"]
    assert "1 skipped" in scan.summary()


def test_non_images_are_ignored(tmp_path):
    _folder(tmp_path, "dh01_org01.png")
    (tmp_path / "dh01_notes.txt").write_text("hi", encoding="utf-8")

    scan = scan_frame_folder(str(tmp_path), DH)
    assert [len(u) for u in scan.units] == [1]
    assert scan.skipped == []


def test_no_rule_makes_the_folder_one_unit_named_after_it(tmp_path):
    _folder(tmp_path, "a01.png", "a02.png", subdir="walk_cycle")
    scan = scan_frame_folder(str(tmp_path / "walk_cycle"))

    assert [u.unit for u in scan.units] == ["walk_cycle"]
    assert len(scan.units[0]) == 2


def test_sub_folders_are_left_alone_unless_asked_for(tmp_path):
    _folder(tmp_path, "dh01_org01.png")
    _folder(tmp_path, "dh02_org01.png", subdir="more")

    assert [u.unit for u in scan_frame_folder(str(tmp_path), DH).units] == ["dh01"]
    assert [u.unit for u in
            scan_frame_folder(str(tmp_path), DH, recursive=True).units] == ["dh01", "dh02"]


def test_an_empty_folder_scans_to_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    scan = scan_frame_folder(str(tmp_path / "empty"), DH)
    assert scan.units == [] and "No files matched" in scan.summary()


def test_scanning_something_that_is_not_a_folder_is_reported(tmp_path):
    with pytest.raises(FrameSetError, match="Not a folder"):
        scan_frame_folder(str(tmp_path / "nope"), DH)


def test_the_summary_counts_units_and_frames(tmp_path):
    _folder(tmp_path, "dh01_org01.png", "dh01_org02.png", "dh02_org01.png")
    assert scan_frame_folder(str(tmp_path), DH).summary() == "2 unit(s), 3 frame(s)"
