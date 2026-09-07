"""Unit tests for src/cli.py — the headless batch CLI (no PyQt6 required)."""
import pytest
from PIL import Image, ImageSequence

from src.cli import main, _parse_positions
from src.core.group_manager import GroupManager
from src.core.composition_group import CompositionGroup, FrameEntry
from src.core.template_manager import TemplateManager


def _make_two_tile_template(tmp_path):
    """A template whose root group references material indices 0 and 1
    (matching a 1x2 grid split of a sprite sheet)."""
    gm = GroupManager()
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    root.entries.append(FrameEntry(material_index=1, x=0, y=0, duration_ms=100))
    gm.add_group(root)
    tpl = TemplateManager.export_composition_template(gm, transparent_bg=False, color_count=256)
    path = tmp_path / "template.json"
    TemplateManager.save_template_to_file(tpl, str(path))
    return str(path)


def _make_sheet_image(tmp_path, name="sheet.png"):
    img = Image.new("RGB", (40, 20), (200, 50, 50))
    img.putpixel((0, 0), (0, 255, 0))
    path = tmp_path / name
    img.save(path)
    return str(path)


def test_main_processes_single_image_successfully(tmp_path):
    template_path = _make_two_tile_template(tmp_path)
    image_path = _make_sheet_image(tmp_path)
    out_dir = tmp_path / "out"

    rc = main([
        "--images", image_path,
        "--template", template_path,
        "--output-dir", str(out_dir),
        "--split-mode", "grid",
        "--split-rows", "1",
        "--split-cols", "2",
    ])

    assert rc == 0
    assert (out_dir / "sheet.gif").exists()


def test_main_processes_multiple_images(tmp_path):
    template_path = _make_two_tile_template(tmp_path)
    image1 = _make_sheet_image(tmp_path, "a.png")
    image2 = _make_sheet_image(tmp_path, "b.png")
    out_dir = tmp_path / "out"

    rc = main([
        "--images", image1, image2,
        "--template", template_path,
        "--output-dir", str(out_dir),
        "--split-rows", "1", "--split-cols", "2",
    ])

    assert rc == 0
    assert (out_dir / "a.gif").exists()
    assert (out_dir / "b.gif").exists()


def test_main_returns_1_for_missing_template(tmp_path, capsys):
    image_path = _make_sheet_image(tmp_path)
    rc = main(["--images", image_path, "--template", str(tmp_path / "nope.json")])
    assert rc == 1
    assert "template file not found" in capsys.readouterr().err


def test_main_returns_1_for_missing_image(tmp_path, capsys):
    template_path = _make_two_tile_template(tmp_path)
    rc = main(["--images", str(tmp_path / "nope.png"), "--template", template_path])
    assert rc == 1
    assert "image file not found" in capsys.readouterr().err


def test_main_returns_1_for_invalid_template_json(tmp_path, capsys):
    bad_template = tmp_path / "bad.json"
    bad_template.write_text("{not valid json")
    image_path = _make_sheet_image(tmp_path)

    rc = main(["--images", image_path, "--template", str(bad_template)])
    assert rc == 1
    assert "invalid template" in capsys.readouterr().err


def test_main_returns_2_when_template_needs_more_tiles_than_available(tmp_path, capsys):
    """Template needs 2 tiles; a 1x1 split only produces 1, so processing should fail."""
    template_path = _make_two_tile_template(tmp_path)
    image_path = _make_sheet_image(tmp_path)

    rc = main([
        "--images", image_path,
        "--template", template_path,
        "--split-mode", "grid",
        "--split-rows", "1", "--split-cols", "1",
    ])
    assert rc == 2
    assert "FAILED" in capsys.readouterr().err


def test_main_output_alongside_source_when_no_output_dir(tmp_path):
    template_path = _make_two_tile_template(tmp_path)
    image_path = _make_sheet_image(tmp_path)

    rc = main([
        "--images", image_path,
        "--template", template_path,
        "--split-rows", "1", "--split-cols", "2",
    ])
    assert rc == 0
    assert (tmp_path / "sheet.gif").exists()


def test_parse_positions_valid():
    assert _parse_positions(["0,0", "1,2"]) == [(0, 0), (1, 2)]


def test_parse_positions_none_when_empty():
    assert _parse_positions(None) is None
    assert _parse_positions([]) is None


def test_parse_positions_invalid_format_raises():
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        _parse_positions(["not-a-position"])


def test_main_with_invalid_positions_returns_1(tmp_path, capsys):
    template_path = _make_two_tile_template(tmp_path)
    image_path = _make_sheet_image(tmp_path)

    rc = main([
        "--images", image_path,
        "--template", template_path,
        "--positions", "garbage",
    ])
    assert rc == 1
    assert "Invalid position" in capsys.readouterr().err


# ── The frame-folder source ──────────────────────────────────────────────────

def _bound_template_file(tmp_path, **group_kw):
    """A template bound to *_org*, so it needs no fixed material indices."""
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(
        name="org", default_duration_ms=100, source_pattern="*_org*", **group_kw))
    gm.set_root_group_id(gid)
    tpl = TemplateManager.export_composition_template(gm)
    tpl["settings"]["output_width"] = 8
    tpl["settings"]["output_height"] = 8
    path = tmp_path / "bound.json"
    TemplateManager.save_template_to_file(tpl, str(path))
    return str(path)


def _frame_folder(tmp_path, units):
    """units: {"dh01": [shade, ...]} written as dh01_org01.png ..."""
    folder = tmp_path / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    for unit, shades in units.items():
        for i, shade in enumerate(shades, 1):
            Image.new("RGB", (8, 8), (shade, shade, shade)).save(
                folder / f"{unit}_org{i:02d}.png")
    return str(folder)


def test_a_frame_folder_builds_one_gif_per_unit(tmp_path):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10, 20], "dh02": [30, 40, 50]})
    out_dir = tmp_path / "out"

    rc = main(["--frames", frames, "--unit-pattern", r"(?P<unit>dh\d+)_",
               "--template", template, "--output-dir", str(out_dir)])

    assert rc == 0
    assert sorted(p.name for p in out_dir.glob("*.gif")) == ["dh01.gif", "dh02.gif"]


def test_a_dry_run_lists_the_units_without_building(tmp_path, capsys):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10], "dh02": [20]})
    out_dir = tmp_path / "out"

    rc = main(["--frames", frames, "--unit-pattern", r"(?P<unit>dh\d+)_",
               "--template", template, "--output-dir", str(out_dir), "--dry-run"])

    assert rc == 0
    printed = capsys.readouterr().out
    assert "dh01" in printed and "dh02" in printed
    assert not out_dir.exists(), "a dry run writes nothing"


def test_a_pattern_that_matches_nothing_is_an_error(tmp_path, capsys):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10]})

    rc = main(["--frames", frames, "--unit-pattern", r"(?P<unit>zz\d+)_",
               "--template", template])

    assert rc == 1
    assert "check --unit-pattern" in capsys.readouterr().err


def test_a_broken_pattern_is_reported_not_raised(tmp_path, capsys):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10]})

    rc = main(["--frames", frames, "--unit-pattern", "(?P<unit>",
               "--template", template])

    assert rc == 1
    assert "Invalid naming rule" in capsys.readouterr().err


def test_a_missing_frame_folder_is_reported(tmp_path, capsys):
    template = _bound_template_file(tmp_path)

    rc = main(["--frames", str(tmp_path / "nope"), "--template", template])

    assert rc == 1
    assert "not a folder" in capsys.readouterr().err.lower()


def test_no_pattern_treats_the_folder_as_one_output(tmp_path):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10, 20]})
    out_dir = tmp_path / "out"

    rc = main(["--frames", frames, "--template", template,
               "--output-dir", str(out_dir)])

    assert rc == 0
    assert [p.name for p in out_dir.glob("*.gif")] == ["frames.gif"]


def test_repeats_are_merged_when_the_template_asks(tmp_path):
    template = _bound_template_file(tmp_path, collapse_repeats=True)
    frames = _frame_folder(tmp_path, {"dh01": [10, 10, 10, 20]})
    out_dir = tmp_path / "out"

    assert main(["--frames", frames, "--unit-pattern", r"(?P<unit>dh\d+)_",
                 "--template", template, "--output-dir", str(out_dir)]) == 0

    with Image.open(out_dir / "dh01.gif") as im:
        durations = [f.info.get("duration") for f in ImageSequence.Iterator(im)]
    assert durations == [300, 100]


def test_a_source_has_to_be_given(tmp_path):
    template = _bound_template_file(tmp_path)
    with pytest.raises(SystemExit):
        main(["--template", template])


def test_the_two_sources_are_mutually_exclusive(tmp_path):
    template = _bound_template_file(tmp_path)
    frames = _frame_folder(tmp_path, {"dh01": [10]})
    with pytest.raises(SystemExit):
        main(["--frames", frames, "--images", "a.png", "--template", template])


def test_auto_size_fits_each_unit_to_its_own_frames(tmp_path):
    template = _bound_template_file(tmp_path)
    folder = tmp_path / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    for unit, size in (("dh01", (37, 91)), ("dh02", (120, 44))):
        for i in (1, 2):
            Image.new("RGB", size, (i * 60, 0, 0)).save(folder / f"{unit}_org{i:02d}.png")
    out_dir = tmp_path / "out"

    rc = main(["--frames", str(folder), "--unit-pattern", r"(?P<unit>dh\d+)_",
               "--template", template, "--output-dir", str(out_dir), "--auto-size"])

    assert rc == 0
    with Image.open(out_dir / "dh01.gif") as im:
        assert im.size == (37, 91)
    with Image.open(out_dir / "dh02.gif") as im:
        assert im.size == (120, 44)
