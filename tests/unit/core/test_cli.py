"""Unit tests for src/cli.py — the headless batch CLI (no PyQt6 required)."""
import pytest
from PIL import Image

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
