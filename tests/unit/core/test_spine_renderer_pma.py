"""Premultiplied-alpha handling in the built-in renderer.

A page marked `pma: true` stores colour already multiplied by alpha. Scaling by
alpha a second time darkens every partly transparent texel by alpha squared,
which is what black fringes around soft edges and mask attachments are.
"""
import json

import pytest
from PIL import Image

from src.core.spine import RenderSettings, SpineRenderer, atlas_is_premultiplied, load_project

# A 50%-alpha red texel, stored premultiplied: straight red (255,0,0) at alpha
# 128 becomes (128,0,0) once multiplied through.
PREMULTIPLIED_RED = (128, 0, 0, 128)


def _write_project(tmp_path, pma: bool):
    page = Image.new("RGBA", (16, 16), PREMULTIPLIED_RED)
    page.save(tmp_path / "sprites.png")
    pma_line = "pma: true\n" if pma else ""
    (tmp_path / "toy.atlas").write_text(
        f"sprites.png\nsize: 16, 16\nfilter: Linear, Linear\n{pma_line}"
        "red\nbounds: 0, 0, 16, 16\n", encoding="utf-8")
    (tmp_path / "toy.json").write_text(json.dumps({
        "skeleton": {"spine": "4.1.23", "x": -8, "y": -8, "width": 16, "height": 16},
        "bones": [{"name": "root"}],
        "slots": [{"name": "s", "bone": "root", "attachment": "red"}],
        "skins": [{"name": "default", "attachments": {
            "s": {"red": {"type": "region", "path": "red", "width": 16, "height": 16}}}}],
        "animations": {"idle": {}},
    }), encoding="utf-8")
    return tmp_path / "toy.json"


def _centre_pixel(project, **kwargs):
    renderer = SpineRenderer(project)
    img = renderer.render("idle", 0.0, RenderSettings(scale=1.0, **kwargs))
    return img.convert("RGBA").getpixel((img.width // 2, img.height // 2))


def test_premultiplied_page_keeps_its_colour(tmp_path):
    project = load_project(_write_project(tmp_path, pma=True))
    r, g, b, a = _centre_pixel(project)
    # Un-premultiplying (128,0,0) at alpha 128 gets the original red back.
    assert a == pytest.approx(128, abs=2)
    assert r == pytest.approx(255, abs=3)
    assert (g, b) == (0, 0)


def test_treating_a_premultiplied_page_as_straight_alpha_darkens_it(tmp_path):
    """The bug this guards against: red halves to a muddy dark red."""
    project = load_project(_write_project(tmp_path, pma=True))
    r, _g, _b, a = _centre_pixel(project, premultiplied=False)
    assert a == pytest.approx(128, abs=2)
    assert r == pytest.approx(128, abs=3)   # darkened by alpha a second time


def test_straight_alpha_page_is_multiplied_through_as_before(tmp_path):
    project = load_project(_write_project(tmp_path, pma=False))
    r, _g, _b, a = _centre_pixel(project)
    # No pma flag, so (128,0,0) is taken at face value and survives the round trip.
    assert a == pytest.approx(128, abs=2)
    assert r == pytest.approx(128, abs=3)


def test_setting_overrides_the_page_flag(tmp_path):
    project = load_project(_write_project(tmp_path, pma=False))
    r, _g, _b, _a = _centre_pixel(project, premultiplied=True)
    assert r == pytest.approx(255, abs=3)


def test_atlas_is_premultiplied_reads_the_flag_off_disk(tmp_path):
    assert atlas_is_premultiplied(_write_project(tmp_path, pma=True)) is True


def test_atlas_is_premultiplied_without_the_flag(tmp_path):
    assert atlas_is_premultiplied(_write_project(tmp_path, pma=False)) is False


def test_atlas_is_premultiplied_tolerates_a_missing_atlas(tmp_path):
    assert atlas_is_premultiplied(tmp_path / "nothing.json") is False
