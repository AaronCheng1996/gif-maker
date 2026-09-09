"""Tests for grouping a folder of exported frames into one unit per output.

A sprite sheet carries its own structure — split it and the tiles arrive in a
known order. A folder of frames carries that structure in the file names, and
every project spells it differently, so the rule is a regex the user supplies.
"""
import pytest
from PIL import Image

from src.core.frame_set import (
    FrameSetError, compile_unit_pattern, scan_frame_folder,
    suggest_unit_patterns, unit_of,
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


# ── Suggesting a rule from the names that are there ──────────────────────────

def _suggest(tmp_path, *names, subdir=None):
    _folder(tmp_path, *names, subdir=subdir)
    return suggest_unit_patterns(str(tmp_path / (subdir or "")))


def test_a_scene_id_is_generalised_into_a_readable_rule(tmp_path):
    """dhD/dhL/dhS becomes dh[DLS], not three escaped literals: the offered rule
    is meant to be read and edited, not just accepted."""
    found = _suggest(
        tmp_path,
        "dhD19_idle_1.png", "dhD19_idle_2.png",
        "dhD19_org_1.png", "dhD19_org_2.png",
        "dhD20_org_1.png", "dhD20_org_2.png",
        "dhL01_org_1.png", "dhL01_org_2.png",
        "dhS20_org_1.png", "dhS20_org_2.png",
    )
    assert any(s.pattern == r"(?P<unit>dh[DLS]\d+)_" for s in found)


def test_every_offered_rule_produces_what_it_claims(tmp_path):
    """The numbers are the point, so they have to survive being run again."""
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_2.png",
                     "dh02_org_1.png", "dh02_org_2.png")

    for s in found:
        scan = scan_frame_folder(str(tmp_path), s.pattern)
        assert len(scan.units) == s.units
        assert sum(len(u) for u in scan.units) == s.frames
        assert len(scan.skipped) == s.skipped
        assert min(len(u) for u in scan.units) == s.min_frames
        assert max(len(u) for u in scan.units) == s.max_frames


def test_suggestions_run_from_the_coarsest_cut_to_the_finest(tmp_path):
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_2.png",
                     "dh02_org_1.png", "dh02_org_2.png")
    assert [s.units for s in found] == sorted(s.units for s in found)
    assert found[0].pattern is None


def test_rules_that_cut_the_folder_the_same_way_are_one_choice(tmp_path):
    """'dh01' and 'dh01_' group the same files; offering both is offering the
    user a difference that is not there."""
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_2.png",
                     "dh02_org_1.png", "dh02_org_2.png")
    shapes = [(s.units, s.frames, s.skipped) for s in found]
    assert len(shapes) == len(set(shapes))


def test_a_rule_that_makes_a_gif_of_every_file_is_not_offered(tmp_path):
    found = _suggest(tmp_path, "a_1.png", "b_1.png", "c_1.png")
    assert all(s.units < 3 for s in found)


def test_a_separator_spelled_two_ways_still_gathers_one_animation(tmp_path):
    """An exporter that wrote 'org_ 1' beside 'org_2' names one animation; a
    rule reading only the tidy half drops the rest without saying so."""
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_ 2.png",
                     "dh02_org_1.png", "dh02_org_ 2.png")
    numbered = [s for s in found
                if s.pattern and s.pattern.endswith(r"\d+$")]
    assert numbered and all(s.skipped == 0 for s in numbered)


def test_a_still_among_numbered_frames_is_called_out(tmp_path):
    """A background exported beside the frames builds without complaint and
    plays as a flash of empty scene, so the scan has to be the one to notice."""
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_2.png",
                     "dh01_org_3.png", "dh01_bg.png")
    grouped = [s for s in found if s.units == 1]
    assert grouped
    assert any("dh01_bg.png" in str(w) and "still" in str(w)
               for s in grouped for w in s.warnings)


def test_files_a_rule_drops_are_reported_against_that_rule(tmp_path):
    found = _suggest(tmp_path, "dh01_org_1.png", "dh01_org_2.png", "notes.png")
    dropped = [s for s in found if s.skipped]
    assert dropped
    assert any("notes.png" in str(w) for s in dropped for w in s.warnings)


def test_a_phrase_keeps_its_values_apart_from_its_wording(tmp_path):
    """The UI translates the template and must not have to re-derive the
    numbers, so they travel beside it rather than baked into a string."""
    found = _suggest(tmp_path, "dhD19_org_1.png", "dhD20_org_1.png",
                     "dhL01_org_1.png", "dhS20_org_1.png")
    labelled = [s for s in found if s.label.args]
    assert labelled and all(isinstance(v, int) for s in labelled
                            for v in s.label.args.values())
    assert all("{" not in str(s.label) for s in found)


def test_a_folder_with_no_images_suggests_nothing(tmp_path):
    (tmp_path / "empty").mkdir()
    assert suggest_unit_patterns(str(tmp_path / "empty")) == []


def test_suggesting_for_something_that_is_not_a_folder_is_reported(tmp_path):
    with pytest.raises(FrameSetError, match="Not a folder"):
        suggest_unit_patterns(str(tmp_path / "nope"))
