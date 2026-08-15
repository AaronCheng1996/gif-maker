"""End-to-end Spine tests: build a tiny synthetic project on disk, load it and render."""
import json

import numpy as np
import pytest
from PIL import Image

from src.core.spine import RenderSettings, SpineLoadError, SpineRenderer, load_project
from src.core.spine.loader import find_project_files

# A 64x64 atlas page holding two 16x16 solid squares:
#   "red"  at (0, 0)
#   "blue" at (16, 0)
ATLAS = """sprites.png
size: 64, 64
filter: Linear, Linear
red
bounds: 0, 0, 16, 16
blue
bounds: 16, 0, 16, 16
"""


def _write_project(tmp_path, skeleton_dict, name="test"):
    page = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    page.paste(Image.new("RGBA", (16, 16), (255, 0, 0, 255)), (0, 0))
    page.paste(Image.new("RGBA", (16, 16), (0, 0, 255, 255)), (16, 0))
    page.save(tmp_path / "sprites.png")
    (tmp_path / f"{name}.atlas").write_text(ATLAS, encoding="utf-8")
    (tmp_path / f"{name}.json").write_text(json.dumps(skeleton_dict), encoding="utf-8")
    return tmp_path / f"{name}.json"


def _region_skeleton(**overrides):
    skel = {
        "skeleton": {"spine": "4.1.23", "x": -32, "y": -32, "width": 64, "height": 64},
        "bones": [{"name": "root"}],
        "slots": [{"name": "square", "bone": "root", "attachment": "red"}],
        "skins": [{
            "name": "default",
            "attachments": {
                "square": {
                    "red": {"type": "region", "path": "red", "width": 16, "height": 16},
                    "blue": {"type": "region", "path": "blue", "width": 16, "height": 16},
                }
            }
        }],
        "animations": {},
    }
    skel.update(overrides)
    return skel


@pytest.fixture()
def region_project(tmp_path):
    return _write_project(tmp_path, _region_skeleton())


def test_load_project_reads_structure(region_project):
    p = load_project(region_project)
    assert p.name == "test"
    assert p.skin_names == ["default"]
    assert len(p.skeleton.bones) == 1
    assert len(p.skeleton.slots) == 1
    assert "sprites.png" in p.textures
    assert p.textures["sprites.png"].shape == (64, 64, 4)


def test_load_missing_skeleton_raises(tmp_path):
    with pytest.raises(SpineLoadError):
        load_project(tmp_path / "nope.json")


def test_load_missing_atlas_raises(tmp_path):
    (tmp_path / "solo.json").write_text(json.dumps(_region_skeleton()), encoding="utf-8")
    with pytest.raises(SpineLoadError):
        load_project(tmp_path / "solo.json")


def test_load_non_skeleton_json_raises(tmp_path):
    (tmp_path / "x.json").write_text('{"hello": 1}', encoding="utf-8")
    (tmp_path / "x.atlas").write_text(ATLAS, encoding="utf-8")
    with pytest.raises(SpineLoadError):
        load_project(tmp_path / "x.json")


def test_find_project_files_skips_config_json(tmp_path):
    _write_project(tmp_path, _region_skeleton())
    (tmp_path / "test.config.json").write_text("{}", encoding="utf-8")
    found = find_project_files(tmp_path)
    assert [f.name for f in found] == ["test.json"]


def test_renders_the_attached_region(region_project):
    p = load_project(region_project)
    img = SpineRenderer(p).render(None, 0.0, RenderSettings(scale=1.0))
    assert img.size == (64, 64)
    a = np.asarray(img)
    # The 16x16 red square sits centred on the root bone at the origin, which is
    # the middle of the 64x64 bounding box.
    assert tuple(a[32, 32]) == (255, 0, 0, 255)
    assert a[0, 0, 3] == 0  # corner stays transparent


def test_attachment_switch_changes_what_is_drawn(tmp_path):
    skel = _region_skeleton(animations={
        "swap": {"slots": {"square": {"attachment": [
            {"time": 0, "name": "red"}, {"time": 1, "name": "blue"}]}}}
    })
    path = _write_project(tmp_path, skel)
    p = load_project(path)
    r = SpineRenderer(p)
    assert tuple(np.asarray(r.render("swap", 0.0, RenderSettings(1.0)))[32, 32]) == (255, 0, 0, 255)
    assert tuple(np.asarray(r.render("swap", 1.0, RenderSettings(1.0)))[32, 32]) == (0, 0, 255, 255)


def test_bone_translation_moves_the_sprite(tmp_path):
    skel = _region_skeleton(animations={
        "slide": {"bones": {"root": {"translate": [
            {"time": 0, "x": 0, "y": 0}, {"time": 1, "x": 16, "y": 0}]}}}
    })
    path = _write_project(tmp_path, skel)
    r = SpineRenderer(load_project(path))
    before = np.asarray(r.render("slide", 0.0, RenderSettings(1.0)))
    after = np.asarray(r.render("slide", 1.0, RenderSettings(1.0)))
    assert tuple(before[32, 32]) == (255, 0, 0, 255)
    assert after[32, 32, 3] == 0            # moved away from the centre
    assert tuple(after[32, 48]) == (255, 0, 0, 255)  # ...to +16 in x


def test_slot_alpha_fades_the_sprite(tmp_path):
    skel = _region_skeleton(animations={
        "fade": {"slots": {"square": {"alpha": [
            {"time": 0, "value": 1.0}, {"time": 1, "value": 0.0}]}}}
    })
    path = _write_project(tmp_path, skel)
    r = SpineRenderer(load_project(path))
    mid = np.asarray(r.render("fade", 0.5, RenderSettings(1.0)))
    assert 80 < int(mid[32, 32, 3]) < 175  # roughly half transparent


def test_render_scale_changes_output_size(region_project):
    p = load_project(region_project)
    img = SpineRenderer(p).render(None, 0.0, RenderSettings(scale=0.5))
    assert img.size == (32, 32)


def test_opaque_background_option(region_project):
    p = load_project(region_project)
    img = SpineRenderer(p).render(None, 0.0,
                                  RenderSettings(scale=1.0, background=(0, 255, 0, 255)))
    a = np.asarray(img)
    assert tuple(a[0, 0]) == (0, 255, 0, 255)
    assert tuple(a[32, 32]) == (255, 0, 0, 255)


def test_mesh_attachment_renders(tmp_path):
    """A two-triangle mesh covering the same area as the region quad."""
    skel = _region_skeleton()
    skel["skins"][0]["attachments"]["square"]["red"] = {
        "type": "mesh",
        "path": "red",
        "uvs": [0, 0, 1, 0, 1, 1, 0, 1],
        "triangles": [0, 1, 2, 2, 3, 0],
        "vertices": [-8, 8, 8, 8, 8, -8, -8, -8],
        "hull": 4,
    }
    path = _write_project(tmp_path, skel)
    a = np.asarray(SpineRenderer(load_project(path)).render(None, 0.0, RenderSettings(1.0)))
    assert tuple(a[32, 32]) == (255, 0, 0, 255)


def test_weighted_mesh_follows_its_bone(tmp_path):
    """Each vertex is bound to bone index 1 with weight 1, so it tracks that bone."""
    skel = _region_skeleton()
    skel["bones"] = [{"name": "root"}, {"name": "driver", "parent": "root"}]
    skel["skins"][0]["attachments"]["square"]["red"] = {
        "type": "mesh",
        "path": "red",
        "uvs": [0, 0, 1, 0, 1, 1, 0, 1],
        "triangles": [0, 1, 2, 2, 3, 0],
        # weighted layout: boneCount, (boneIndex, x, y, weight) per vertex
        "vertices": [1, 1, -8, 8, 1, 1, 1, 8, 8, 1, 1, 1, 8, -8, 1, 1, 1, -8, -8, 1],
        "hull": 4,
    }
    skel["animations"] = {"move": {"bones": {"driver": {"translate": [
        {"time": 0, "x": 0, "y": 0}, {"time": 1, "x": 16, "y": 0}]}}}}
    path = _write_project(tmp_path, skel)
    r = SpineRenderer(load_project(path))
    after = np.asarray(r.render("move", 1.0, RenderSettings(1.0)))
    assert after[32, 32, 3] == 0
    assert tuple(after[32, 48]) == (255, 0, 0, 255)


def test_compute_bounds_tracks_animation_extent(tmp_path):
    skel = _region_skeleton(animations={
        "slide": {"bones": {"root": {"translate": [
            {"time": 0, "x": 0, "y": 0}, {"time": 1, "x": 100, "y": 0}]}}}
    })
    path = _write_project(tmp_path, skel)
    r = SpineRenderer(load_project(path))
    x, y, w, h = r.compute_bounds("slide")
    assert w > 100  # spans the full travel plus the sprite width
    assert h == pytest.approx(16, abs=1e-6)


def test_attachment_name_field_selects_the_atlas_region(tmp_path):
    """Skinned exports key an attachment by the slot-facing name but point at a
    differently-named region via a "name" field. Missing that override makes the
    region lookup fail and the part silently disappear."""
    skel = _region_skeleton()
    skel["skins"] = [{
        "name": "default",
        "attachments": {
            # Slot asks for "square"; the real region is "blue".
            "square": {"square": {"type": "region", "name": "blue",
                                  "width": 16, "height": 16}}
        },
    }]
    skel["slots"] = [{"name": "square", "bone": "root", "attachment": "square"}]
    path = _write_project(tmp_path, skel)

    p = load_project(path)
    att = p.skeleton.get_attachment("square", "square")
    assert att is not None
    assert att.region is not None, "the name field should resolve the atlas region"
    assert att.region.name == "blue"

    a = np.asarray(SpineRenderer(p).render(None, 0.0, RenderSettings(1.0)))
    assert tuple(a[32, 32]) == (0, 0, 255, 255)


def test_explicit_path_wins_over_the_name_field(tmp_path):
    skel = _region_skeleton()
    skel["skins"] = [{
        "name": "default",
        "attachments": {
            "square": {"square": {"type": "region", "name": "blue", "path": "red",
                                  "width": 16, "height": 16}}
        },
    }]
    skel["slots"] = [{"name": "square", "bone": "root", "attachment": "square"}]
    p = load_project(_write_project(tmp_path, skel))
    assert p.skeleton.get_attachment("square", "square").region.name == "red"


def test_rotated_region_samples_the_right_pixels(tmp_path):
    """A 90-degree packed region must un-rotate correctly, otherwise the mesh
    samples empty atlas space and the part renders full of holes."""
    # Page: a 16x32 red block laid on its side at (0,0), i.e. 32x16 on the page.
    page = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    page.paste(Image.new("RGBA", (32, 16), (255, 0, 0, 255)), (0, 0))
    page.save(tmp_path / "sprites.png")
    (tmp_path / "rot.atlas").write_text(
        "sprites.png\nsize: 64, 64\nred\nbounds: 0, 0, 16, 32\nrotate: 90\n",
        encoding="utf-8")
    (tmp_path / "rot.json").write_text(json.dumps({
        "skeleton": {"spine": "4.1.23", "x": -32, "y": -32, "width": 64, "height": 64},
        "bones": [{"name": "root"}],
        "slots": [{"name": "s", "bone": "root", "attachment": "red"}],
        "skins": [{"name": "default", "attachments": {
            "s": {"red": {"type": "region", "path": "red", "width": 16, "height": 32}}}}],
        "animations": {},
    }), encoding="utf-8")

    p = load_project(tmp_path / "rot.json")
    region = p.atlas.find_region("red")
    assert (region.packed_width, region.packed_height) == (32, 16)

    a = np.asarray(SpineRenderer(p).render(None, 0.0, RenderSettings(1.0)))
    # The 16x32 sprite is centred: every pixel inside it must be opaque red,
    # with no holes from sampling outside the packed area.
    inner = a[32 - 14:32 + 14, 32 - 6:32 + 6]
    assert (inner[:, :, 3] == 255).all()
    assert (inner[:, :, 0] == 255).all()


def test_draw_order_puts_later_slots_on_top(tmp_path):
    """Two overlapping opaque squares: the one later in draw order wins."""
    skel = _region_skeleton()
    skel["slots"] = [
        {"name": "back", "bone": "root", "attachment": "red"},
        {"name": "front", "bone": "root", "attachment": "blue"},
    ]
    atts = skel["skins"][0]["attachments"]["square"]
    skel["skins"][0]["attachments"] = {"back": atts, "front": atts}
    path = _write_project(tmp_path, skel)
    a = np.asarray(SpineRenderer(load_project(path)).render(None, 0.0, RenderSettings(1.0)))
    assert tuple(a[32, 32]) == (0, 0, 255, 255)
