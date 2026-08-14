"""Unit tests for Spine bone transforms, animation timelines and draw order."""
import math

import pytest

from src.core.spine.animation import Animation, PropertyTimeline, _apply_draw_order
from src.core.spine.skeleton import Skeleton


def _skeleton(bones, slots=None, **extra):
    data = {
        "skeleton": {"x": -10, "y": -20, "width": 100, "height": 200, "spine": "4.1.23"},
        "bones": bones,
        "slots": slots or [],
        "skins": [{"name": "default", "attachments": {}}],
    }
    data.update(extra)
    return Skeleton(data)


# ── bone transforms ──────────────────────────────────────────────────────

def test_skeleton_block_xy_is_bounds_not_position():
    """The skeleton block's x/y is the exported bounding box, so the root bone
    must still sit at the world origin."""
    sk = _skeleton([{"name": "root"}])
    assert (sk.bounds_x, sk.bounds_y) == (-10, -20)
    assert (sk.x, sk.y) == (0.0, 0.0)
    sk.update_world_transform()
    root = sk.bones_by_name["root"]
    assert root.world_x == pytest.approx(0.0)
    assert root.world_y == pytest.approx(0.0)


def test_child_bone_inherits_parent_translation():
    sk = _skeleton([
        {"name": "root"},
        {"name": "child", "parent": "root", "x": 10, "y": 5},
    ])
    sk.update_world_transform()
    child = sk.bones_by_name["child"]
    assert child.world_x == pytest.approx(10)
    assert child.world_y == pytest.approx(5)


def test_child_bone_inherits_parent_rotation():
    sk = _skeleton([
        {"name": "root", "rotation": 90},
        {"name": "child", "parent": "root", "x": 10},
    ])
    sk.update_world_transform()
    child = sk.bones_by_name["child"]
    # Rotating the parent 90 deg sends the child's +X offset to +Y.
    assert child.world_x == pytest.approx(0, abs=1e-6)
    assert child.world_y == pytest.approx(10)


def test_child_bone_inherits_parent_scale():
    sk = _skeleton([
        {"name": "root", "scaleX": 2, "scaleY": 3},
        {"name": "child", "parent": "root", "x": 10, "y": 10},
    ])
    sk.update_world_transform()
    child = sk.bones_by_name["child"]
    assert child.world_x == pytest.approx(20)
    assert child.world_y == pytest.approx(30)


def test_only_translation_inherit_ignores_parent_rotation():
    sk = _skeleton([
        {"name": "root", "rotation": 90},
        {"name": "child", "parent": "root", "x": 10, "inherit": "onlyTranslation"},
    ])
    sk.update_world_transform()
    child = sk.bones_by_name["child"]
    # Position still follows the parent, but the child's own axes stay unrotated.
    assert child.a == pytest.approx(1.0)
    assert child.c == pytest.approx(0.0, abs=1e-6)


def test_no_scale_inherit_drops_parent_scale():
    sk = _skeleton([
        {"name": "root", "scaleX": 4, "scaleY": 4},
        {"name": "child", "parent": "root", "inherit": "noScale"},
    ])
    sk.update_world_transform()
    child = sk.bones_by_name["child"]
    assert child.get_world_scale_x() == pytest.approx(1.0, abs=1e-6)


def test_legacy_transform_key_is_read_as_inherit():
    sk = _skeleton([
        {"name": "root"},
        {"name": "child", "parent": "root", "transform": "onlyTranslation"},
    ])
    assert sk.bones_by_name["child"].data.inherit == "onlyTranslation"


# ── timelines ────────────────────────────────────────────────────────────

def test_linear_interpolation():
    tl = PropertyTimeline([{"time": 0, "value": 0}, {"time": 1, "value": 10}],
                          ["value"], {"value": 0.0})
    assert tl.value_at(0.0, "value") == pytest.approx(0)
    assert tl.value_at(0.5, "value") == pytest.approx(5)
    assert tl.value_at(1.0, "value") == pytest.approx(10)


def test_time_defaults_to_zero_when_omitted():
    tl = PropertyTimeline([{"value": 7}, {"time": 1, "value": 9}], ["value"], {"value": 0.0})
    assert tl.times[0] == 0.0
    assert tl.value_at(0.0, "value") == pytest.approx(7)


def test_stepped_curve_holds_previous_value():
    tl = PropertyTimeline([{"time": 0, "value": 0, "curve": "stepped"},
                           {"time": 1, "value": 10}], ["value"], {"value": 0.0})
    assert tl.value_at(0.99, "value") == pytest.approx(0)
    assert tl.value_at(1.0, "value") == pytest.approx(10)


def test_bezier_curve_is_monotonic_between_keys():
    tl = PropertyTimeline(
        [{"time": 0, "value": 0, "curve": [0.25, 0, 0.75, 10]}, {"time": 1, "value": 10}],
        ["value"], {"value": 0.0})
    vals = [tl.value_at(t / 10, "value") for t in range(11)]
    assert vals[0] == pytest.approx(0)
    assert vals[-1] == pytest.approx(10)
    assert all(b >= a - 1e-6 for a, b in zip(vals, vals[1:]))


def test_clamps_outside_keyframe_range():
    tl = PropertyTimeline([{"time": 1, "value": 3}, {"time": 2, "value": 6}],
                          ["value"], {"value": 0.0})
    assert tl.value_at(0.0, "value") == pytest.approx(3)
    assert tl.value_at(99.0, "value") == pytest.approx(6)


def test_multi_property_timeline_uses_per_property_curves():
    """translate carries x and y; the curve array holds 4 numbers per property."""
    tl = PropertyTimeline(
        [{"time": 0, "x": 0, "y": 0, "curve": ["stepped"][0:0] or
          [0.25, 0, 0.75, 10, 0.25, 0, 0.75, 20]},
         {"time": 1, "x": 10, "y": 20}],
        ["x", "y"], {"x": 0.0, "y": 0.0})
    v = tl.values_at(1.0)
    assert v["x"] == pytest.approx(10)
    assert v["y"] == pytest.approx(20)


def test_missing_property_falls_back_to_default():
    tl = PropertyTimeline([{"time": 0}, {"time": 1, "x": 2}], ["x", "y"],
                          {"x": 1.0, "y": 1.0})
    assert tl.value_at(0.0, "x") == pytest.approx(1.0)
    assert tl.value_at(1.0, "y") == pytest.approx(1.0)


# ── animation application ────────────────────────────────────────────────

def _animated_skeleton():
    sk = _skeleton(
        [{"name": "root"}, {"name": "arm", "parent": "root", "x": 5, "rotation": 10}],
        slots=[{"name": "slot1", "bone": "arm", "attachment": "a"}],
    )
    return sk


def test_rotate_timeline_is_relative_to_setup_pose():
    sk = _animated_skeleton()
    anim = Animation("a", {"bones": {"arm": {"rotate": [
        {"time": 0, "value": 0}, {"time": 1, "value": 90}]}}}, sk)
    anim.apply(sk, 1.0)
    assert sk.bones_by_name["arm"].rotation == pytest.approx(100)  # setup 10 + 90


def test_scale_timeline_multiplies_setup_scale():
    sk = _skeleton([{"name": "root"}, {"name": "b", "parent": "root", "scaleX": 2}])
    anim = Animation("a", {"bones": {"b": {"scale": [
        {"time": 0, "x": 1, "y": 1}, {"time": 1, "x": 3, "y": 1}]}}}, sk)
    anim.apply(sk, 1.0)
    assert sk.bones_by_name["b"].scale_x == pytest.approx(6)  # 2 * 3


def test_translate_timeline_offsets_setup_position():
    sk = _animated_skeleton()
    anim = Animation("a", {"bones": {"arm": {"translate": [
        {"time": 0, "x": 0, "y": 0}, {"time": 1, "x": 100, "y": 50}]}}}, sk)
    anim.apply(sk, 1.0)
    arm = sk.bones_by_name["arm"]
    assert arm.x == pytest.approx(105)  # setup 5 + 100
    assert arm.y == pytest.approx(50)


def test_attachment_timeline_switches_slot_attachment():
    sk = _animated_skeleton()
    anim = Animation("a", {"slots": {"slot1": {"attachment": [
        {"time": 0, "name": "a"}, {"time": 1, "name": "b"}]}}}, sk)
    anim.apply(sk, 0.0)
    assert sk.slots_by_name["slot1"].attachment_name == "a"
    anim.apply(sk, 1.0)
    assert sk.slots_by_name["slot1"].attachment_name == "b"


def test_attachment_timeline_can_hide_a_slot():
    sk = _animated_skeleton()
    anim = Animation("a", {"slots": {"slot1": {"attachment": [
        {"time": 0, "name": None}]}}}, sk)
    anim.apply(sk, 0.0)
    assert sk.slots_by_name["slot1"].attachment_name is None


def test_rgba_timeline_sets_slot_colour():
    sk = _animated_skeleton()
    anim = Animation("a", {"slots": {"slot1": {"rgba": [
        {"time": 0, "color": "ff0000ff"}, {"time": 1, "color": "0000ffff"}]}}}, sk)
    anim.apply(sk, 0.0)
    r, g, b, a = sk.slots_by_name["slot1"].color
    assert (r, g, b, a) == pytest.approx((1.0, 0.0, 0.0, 1.0))


def test_alpha_timeline_only_touches_alpha():
    sk = _animated_skeleton()
    anim = Animation("a", {"slots": {"slot1": {"alpha": [
        {"time": 0, "value": 1.0}, {"time": 1, "value": 0.0}]}}}, sk)
    anim.apply(sk, 1.0)
    assert sk.slots_by_name["slot1"].color[3] == pytest.approx(0.0)


def test_animation_duration_is_the_last_keyframe():
    sk = _animated_skeleton()
    anim = Animation("a", {"bones": {"arm": {"rotate": [
        {"time": 0, "value": 0}, {"time": 2.5, "value": 90}]}}}, sk)
    assert anim.duration == pytest.approx(2.5)


# ── draw order ───────────────────────────────────────────────────────────

def test_draw_order_offsets_move_slots():
    sk = _skeleton([{"name": "root"}], slots=[
        {"name": "a", "bone": "root"},
        {"name": "b", "bone": "root"},
        {"name": "c", "bone": "root"},
    ])
    order = _apply_draw_order(sk, [{"slot": "a", "offset": 2}])
    assert order == [1, 2, 0]


def test_empty_draw_order_restores_setup_order():
    sk = _skeleton([{"name": "root"}], slots=[
        {"name": "a", "bone": "root"}, {"name": "b", "bone": "root"}])
    assert _apply_draw_order(sk, []) == [0, 1]
    assert _apply_draw_order(sk, None) == [0, 1]
