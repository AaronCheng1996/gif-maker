"""Tests for measuring the canvas a group needs.

Auto-fit used to walk the group's own entries, which saw only plain frames
sitting directly in it — not the materials a binding matched, not what a
sub-group contributes, and not the offset it contributes them at. Measuring the
expansion instead is the same view the export uses.
"""
from PIL import Image

from src.core.composition_group import (
    CompositionGroup, FrameEntry, LayerBlockEntry, SubGroupEntry, FrameSlot,
)
from src.core.gif_builder import GifBuilder
from src.core.group_manager import GroupManager
from src.core.image_loader import MaterialManager


def _mm(*sizes_and_names):
    mm = MaterialManager()
    for (w, h), name in sizes_and_names:
        mm.add_material(Image.new("RGB", (w, h), (30, 60, 90)), name=name)
    return mm


def _measure(gid, gm, mm):
    return GifBuilder().measure_group_output_size(gid, gm, mm)


# ── Plain entries ────────────────────────────────────────────────────────────

def test_a_group_of_frames_fits_its_largest_material():
    mm = _mm(((10, 40), "a"), ((30, 20), "b"))
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.extend([FrameEntry(material_index=0), FrameEntry(material_index=1)])
    gid = gm.add_group(g)

    assert _measure(gid, gm, mm) == (30, 40)


def test_an_offset_frame_needs_room_for_the_offset():
    """Materials are pasted top-left, so the widest one alone would clip it."""
    mm = _mm(((10, 10), "a"))
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.append(FrameEntry(material_index=0, x=50, y=5))
    gid = gm.add_group(g)

    assert _measure(gid, gm, mm) == (60, 15)


def test_a_frame_pushed_off_the_left_is_measured_where_it_ends():
    mm = _mm(((20, 20), "a"))
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.append(FrameEntry(material_index=0, x=-8, y=0))
    gid = gm.add_group(g)

    assert _measure(gid, gm, mm) == (12, 20), "only the visible part can be fitted"


def test_an_empty_group_needs_nothing():
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="Empty"))
    assert _measure(gid, gm, MaterialManager()) == (0, 0)


def test_a_frame_pointing_at_a_missing_material_is_skipped():
    mm = _mm(((10, 10), "a"))
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.extend([FrameEntry(material_index=0), FrameEntry(material_index=99)])
    gid = gm.add_group(g)

    assert _measure(gid, gm, mm) == (10, 10)


# ── The cases entry-walking missed ───────────────────────────────────────────

def test_a_bound_group_is_measured_from_the_materials_it_matched():
    """It has no entries at all, so walking them reported nothing to fit."""
    mm = _mm(((10, 10), "x_idle01"), ((40, 90), "x_org01"), ((30, 20), "x_org02"))
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="org", source_pattern="*_org*"))

    assert _measure(gid, gm, mm) == (40, 90)


def test_a_bound_group_that_matches_nothing_needs_nothing():
    mm = _mm(((10, 10), "x_idle01"))
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="org", source_pattern="*_org*"))

    assert _measure(gid, gm, mm) == (0, 0)


def test_a_root_of_sub_group_references_is_measured_through_them():
    """A root holding only references had no frame entry of its own."""
    mm = _mm(((10, 10), "a"), ((70, 25), "b"))
    gm = GroupManager()
    child = CompositionGroup(name="Child")
    child.entries.append(FrameEntry(material_index=1))
    cid = gm.add_group(child)
    root = CompositionGroup(name="Root")
    root.entries.append(SubGroupEntry(group_id=cid))
    rid = gm.add_group(root)

    assert _measure(rid, gm, mm) == (70, 25)


def test_a_reference_offset_counts_towards_the_size():
    mm = _mm(((20, 20), "a"))
    gm = GroupManager()
    child = CompositionGroup(name="Child")
    child.entries.append(FrameEntry(material_index=0))
    cid = gm.add_group(child)
    root = CompositionGroup(name="Root")
    root.entries.append(SubGroupEntry(group_id=cid, x=15, y=7))
    rid = gm.add_group(root)

    assert _measure(rid, gm, mm) == (35, 27)


def test_a_bound_group_reached_through_a_reference_is_measured():
    mm = _mm(((10, 10), "x_idle01"), ((45, 60), "x_org01"))
    gm = GroupManager()
    cid = gm.add_group(CompositionGroup(name="org", source_pattern="*_org*"))
    root = CompositionGroup(name="Root")
    root.entries.append(SubGroupEntry(group_id=cid))
    rid = gm.add_group(root)

    assert _measure(rid, gm, mm) == (45, 60)


def test_every_layer_of_a_layer_block_counts():
    mm = _mm(((10, 80), "a"), ((60, 10), "b"))
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.append(LayerBlockEntry(timelines=[
        [FrameSlot(material_index=0)],
        [FrameSlot(material_index=1, x=5, y=5)],
    ]))
    gid = gm.add_group(g)

    assert _measure(gid, gm, mm) == (65, 80)


def test_the_biggest_of_several_references_wins():
    mm = _mm(((10, 10), "a"), ((25, 15), "b"), ((12, 40), "c"))
    gm = GroupManager()
    ids = []
    for i in range(3):
        child = CompositionGroup(name=f"C{i}")
        child.entries.append(FrameEntry(material_index=i))
        ids.append(gm.add_group(child))
    root = CompositionGroup(name="Root")
    root.entries.extend(SubGroupEntry(group_id=i) for i in ids)
    rid = gm.add_group(root)

    assert _measure(rid, gm, mm) == (25, 40)


def test_merging_repeats_does_not_change_the_size():
    """Merging drops frames from the timeline, never materials from the box."""
    mm = _mm(((10, 10), "org01"), ((10, 10), "org02"), ((40, 20), "org03"))
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(
        name="org", source_pattern="org*", collapse_repeats=True))

    assert _measure(gid, gm, mm) == (40, 20)
