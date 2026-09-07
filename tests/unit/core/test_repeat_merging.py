"""Tests for merging runs of identical frames into one held frame.

Sprite exporters spell a held pose out as repeated images — ten copies of one
frame, or two files that happen to be identical — so a timeline built straight
from the files is mostly padding. The run and the single long frame play the
same, and collapsing them is what turns a folder of files into the timeline the
animator actually drew.
"""
from PIL import Image

from src.core.composition_group import (
    CompositionGroup, FrameEntry, collapse_repeat_runs, image_digest,
)
from src.core.gif_builder import GifBuilder
from src.core.group_manager import GroupManager
from src.core.image_loader import MaterialManager
from src.core.template_manager import TemplateManager


def _shade(v):
    return Image.new("RGB", (8, 8), (v, v, v))


def _mm(shades, names=None):
    """One material per shade; equal shades are separate materials, same pixels."""
    mm = MaterialManager()
    for i, v in enumerate(shades):
        mm.add_material(_shade(v), name=(names[i] if names else f"f{i + 1:02d}"))
    return mm


def _expand(mm, **kw):
    gm = GroupManager()
    g = CompositionGroup(name="G", collapse_repeats=True, **kw)
    g.entries.extend(FrameEntry(material_index=i) for i in range(len(mm)))
    gid = gm.add_group(g)
    return GifBuilder()._expand_composition_group(gid, gm, mm)


# ── The run helper ───────────────────────────────────────────────────────────

def test_runs_are_the_first_index_and_the_length():
    assert collapse_repeat_runs(["a", "a", "b", "c", "c", "c"]) == [(0, 2), (2, 1), (3, 3)]


def test_nothing_has_no_runs():
    assert collapse_repeat_runs([]) == []


def test_only_neighbours_join_a_run():
    assert collapse_repeat_runs(["a", "b", "a"]) == [(0, 1), (1, 1), (2, 1)]


def test_identical_pixels_have_the_same_digest():
    assert image_digest(_shade(9)) == image_digest(_shade(9))
    assert image_digest(_shade(9)) != image_digest(_shade(10))


# ── What the builder merges ──────────────────────────────────────────────────

def test_merging_is_off_unless_asked_for():
    mm = _mm([1, 1, 2])
    gm = GroupManager()
    g = CompositionGroup(name="G")
    g.entries.extend(FrameEntry(material_index=i) for i in range(3))
    gid = gm.add_group(g)

    _, durations = GifBuilder()._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100, 100]


def test_neighbouring_repeats_become_one_frame_held_longer():
    frames, durations = _expand(_mm([1, 1, 1, 2]))
    assert len(frames) == 2
    assert durations == [300, 100]


def test_repeats_are_matched_on_pixels_not_on_which_material():
    """The ten copies of a held pose are ten separate files."""
    mm = _mm([5, 5], names=["org34_1", "org34_2"])
    frames, durations = _expand(mm)
    assert len(frames) == 1 and durations == [200]


def test_a_frame_that_comes_back_later_is_not_merged_into_the_earlier_one():
    """org06 repeats org03's drawing but plays as its own beat."""
    _, durations = _expand(_mm([1, 2, 1]))
    assert durations == [100, 100, 100]


def test_a_frames_own_duration_is_carried_into_the_sum():
    mm = _mm([1, 1])
    gm = GroupManager()
    g = CompositionGroup(name="G", collapse_repeats=True)
    g.entries.append(FrameEntry(material_index=0, duration_ms=250))
    g.entries.append(FrameEntry(material_index=1, duration_ms=50))
    gid = gm.add_group(g)

    _, durations = GifBuilder()._expand_composition_group(gid, gm, mm)
    assert durations == [300]


def test_frames_placed_at_different_offsets_are_not_the_same_frame():
    mm = _mm([1, 1])
    gm = GroupManager()
    g = CompositionGroup(name="G", collapse_repeats=True)
    g.entries.append(FrameEntry(material_index=0))
    g.entries.append(FrameEntry(material_index=1, x=4))
    gid = gm.add_group(g)

    _, durations = GifBuilder()._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100]


def test_an_empty_group_merges_to_nothing():
    frames, durations = _expand(_mm([]))
    assert frames == [] and durations == []


def test_a_pinned_pause_replaces_the_merged_total_on_the_last_run():
    _, durations = _expand(_mm([1, 2, 2, 2]), tail_duration_ms=2000)
    assert durations == [100, 2000]


def test_merging_also_works_on_a_bound_group():
    mm = _mm([1, 1, 2], names=["org01", "org02", "org03"])
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(
        name="org", source_pattern="org*", collapse_repeats=True))

    _, durations = GifBuilder()._expand_composition_group(gid, gm, mm)
    assert durations == [200, 100]


# ── The shape the exporter actually produces ─────────────────────────────────

def test_a_folder_of_exported_frames_becomes_the_timeline_it_stands_for():
    """org01..org33 with an adjacent duplicate pair, then a pose written as ten
    copies and two written as pairs — 48 files, 36 beats."""
    shades = list(range(1, 26))          # org01..org25, all different
    shades += [26, 26]                   # org26 == org27, adjacent duplicates
    shades += list(range(28, 34))        # org28..org33
    shades += [90] * 10                  # org34_1..org34_10
    shades += [91, 91]                   # org35_1, org35_2
    shades += [92, 92]                   # org36_1, org36_2
    shades += [93]                       # org37
    assert len(shades) == 48

    frames, durations = _expand(_mm(shades))

    assert len(frames) == 36
    assert durations == [100] * 25 + [200] + [100] * 6 + [1000, 200, 200, 100]


# ── Templates carry the setting ──────────────────────────────────────────────

def test_merging_survives_a_template_round_trip():
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="G", collapse_repeats=True))
    gm.set_root_group_id(gid)

    restored, _ = TemplateManager.import_composition_template(
        TemplateManager.export_composition_template(gm, {})
    )
    assert restored.get_group(gid).collapse_repeats is True


def test_a_template_written_before_merging_loads_with_it_off():
    template = {
        "version": "4.0", "format": "composition_group", "settings": {},
        "root_group_id": 0,
        "groups": [{"id": 0, "name": "G", "default_duration_ms": 100, "entries": []}],
    }
    restored, _ = TemplateManager.import_composition_template(template)
    assert restored.get_group(0).collapse_repeats is False
