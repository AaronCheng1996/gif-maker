"""Tests for binding a group to materials by name instead of by index.

A template stored material indices, so it only fitted the sprite it was built
from: the moment a clip was a different length, every group after it pointed at
the wrong material. Binding a group to a glob makes it as long as the match is,
which is what lets one template cover a whole cast.
"""
from PIL import Image, ImageSequence

from src.core.composition_group import (
    CompositionGroup, FrameEntry, SubGroupEntry,
    resolve_source_indices,
)
from src.core.gif_builder import GifBuilder
from src.core.group_manager import GroupManager
from src.core.image_loader import MaterialManager
from src.core.template_manager import TemplateManager


def _materials(*names):
    mm = MaterialManager()
    for i, n in enumerate(names):
        mm.add_material(Image.new("RGB", (8, 8), (i * 7 % 256, 0, 0)), name=n)
    return mm


def _names(mm):
    return [n for _, n in mm.get_all_materials()]


# ── Which materials a glob picks, and in what order ──────────────────────────

def test_a_glob_picks_the_materials_whose_name_matches():
    names = ["dh01_idle01", "dh01_org01", "dh01_org02", "dh01_pis01"]
    assert [names[i] for i in resolve_source_indices("*_org*", names)] == \
        ["dh01_org01", "dh01_org02"]


def test_digit_runs_are_read_as_numbers():
    """org10 sorts after org2 — lexicographic order drops it mid-sequence."""
    names = ["org10", "org2", "org1"]
    assert [names[i] for i in resolve_source_indices("org*", names)] == \
        ["org1", "org2", "org10"]


def test_matching_ignores_case():
    names = ["DH01_Org01"]
    assert resolve_source_indices("*_org*", names) == [0]


def test_order_does_not_depend_on_the_order_they_were_loaded():
    loaded = ["org03", "org01", "org02"]
    assert [loaded[i] for i in resolve_source_indices("org*", loaded)] == \
        ["org01", "org02", "org03"]


def test_materials_with_the_same_name_keep_their_load_order():
    names = ["org01", "org01"]
    assert resolve_source_indices("org*", names) == [0, 1]


def test_an_empty_pattern_matches_nothing():
    assert resolve_source_indices("", ["org01"]) == []


def test_a_pattern_that_matches_nothing_returns_nothing():
    assert resolve_source_indices("walk*", ["org01"]) == []


def test_a_bare_name_matches_only_that_name():
    """fnmatch is anchored at both ends, so 'org' is not a prefix search."""
    names = ["org", "org01"]
    assert resolve_source_indices("org", names) == [0]


# ── What a bound group exports ───────────────────────────────────────────────

def _bound(pattern, mm, **kw):
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="G", source_pattern=pattern, **kw))
    return GifBuilder()._expand_composition_group(gid, gm, mm), gm, gid


def test_a_bound_group_expands_to_the_materials_it_matched():
    mm = _materials("org01", "org02", "idle01")
    (frames, durations), _, _ = _bound("org*", mm)

    assert frames == [[(0, 0, 0)], [(1, 0, 0)]]
    assert durations == [100, 100]


def test_a_bound_group_holds_as_many_frames_as_the_material_set_has():
    short = _materials(*[f"org{i:02d}" for i in range(1, 4)])
    long = _materials(*[f"org{i:02d}" for i in range(1, 10)])

    (short_frames, _), _, _ = _bound("org*", short)
    (long_frames, _), _, _ = _bound("org*", long)

    assert len(short_frames) == 3
    assert len(long_frames) == 9


def test_a_bound_group_runs_at_the_group_default():
    mm = _materials("org01", "org02")
    (_, durations), _, _ = _bound("org*", mm, default_duration_ms=66)
    assert durations == [66, 66]


def test_a_pinned_pause_still_lands_on_the_last_matched_frame():
    mm = _materials("org01", "org02", "org03")
    (_, durations), _, _ = _bound("org*", mm, tail_duration_ms=2000)
    assert durations == [100, 100, 2000]


def test_a_bound_group_that_matches_nothing_expands_to_nothing():
    mm = _materials("idle01")
    (frames, durations), _, _ = _bound("org*", mm, tail_duration_ms=2000)
    assert frames == [] and durations == []


def test_binding_sets_entries_aside_rather_than_deleting_them():
    """Unbinding has to bring the hand-built timeline straight back."""
    mm = _materials("org01", "org02")
    gm = GroupManager()
    g = CompositionGroup(name="G", source_pattern="org*")
    g.entries.append(FrameEntry(material_index=0, duration_ms=999))
    gid = gm.add_group(g)
    gb = GifBuilder()

    bound_frames, _ = gb._expand_composition_group(gid, gm, mm)
    assert len(bound_frames) == 2, "the binding wins while it is on"
    assert len(g.entries) == 1, "and the entry is still there"

    g.source_pattern = None
    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations == [999]


# ── One template over sprites whose clips differ in length ───────────────────

def _cast_template():
    """idle x3, pis x6, pis x10 sped up, then org once — the shape in use."""
    gm = GroupManager()
    idle = gm.add_group(CompositionGroup(name="idle", source_pattern="*_idle*"))
    pis = gm.add_group(CompositionGroup(name="pis", source_pattern="*_pis*"))
    org = gm.add_group(CompositionGroup(name="org", source_pattern="*_org*",
                                        tail_duration_ms=2000))
    root = CompositionGroup(name="Root")
    root.entries.extend([
        SubGroupEntry(group_id=idle, loop_count=3),
        SubGroupEntry(group_id=pis, loop_count=6),
        SubGroupEntry(group_id=pis, loop_count=10, duration_override_ms=66),
        SubGroupEntry(group_id=org, loop_count=1),
    ])
    gm.set_root_group_id(gm.add_group(root))
    return TemplateManager.export_composition_template(gm, {})


def _sprite(unit, n_idle, n_pis, n_org):
    names = []
    for clip, n in (("idle", n_idle), ("pis", n_pis), ("org", n_org)):
        names += [f"{unit}_{clip}{i:02d}" for i in range(1, n + 1)]
    return _materials(*names)


def test_one_template_fits_sprites_whose_clips_are_different_lengths():
    template = _cast_template()

    for unit, n_idle, n_pis, n_org in [("dh01", 6, 6, 36), ("dh02", 6, 6, 27)]:
        gm, _ = TemplateManager.import_composition_template(template)
        frames, _ = GifBuilder()._expand_composition_group(
            gm.get_root_group_id(), gm, _sprite(unit, n_idle, n_pis, n_org)
        )
        assert len(frames) == n_idle * 3 + n_pis * 16 + n_org


def test_a_clip_changing_length_does_not_shift_the_groups_after_it():
    """The failure that made templates unusable: org was 36 frames on one
    sprite and 27 on the next, so every index past it pointed elsewhere."""
    template = _cast_template()
    gm, _ = TemplateManager.import_composition_template(template)
    mm = _sprite("dh02", 6, 6, 27)

    frames, _ = GifBuilder()._expand_composition_group(gm.get_root_group_id(), gm, mm)
    names = _names(mm)

    assert [names[frames[i][0][0]] for i in range(3)] == \
        ["dh02_idle01", "dh02_idle02", "dh02_idle03"]
    assert names[frames[-1][0][0]] == "dh02_org27", "the run still ends on org"


def test_the_pinned_pause_survives_the_clip_changing_length():
    template = _cast_template()
    for n_org in (27, 36):
        gm, _ = TemplateManager.import_composition_template(template)
        _, durations = GifBuilder()._expand_composition_group(
            gm.get_root_group_id(), gm, _sprite("dh", 6, 6, n_org)
        )
        assert durations[-1] == 2000


# ── Templates carry the binding ──────────────────────────────────────────────

def test_a_binding_survives_a_template_round_trip():
    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="G", source_pattern="*_org*"))
    gm.set_root_group_id(gid)

    restored, _ = TemplateManager.import_composition_template(
        TemplateManager.export_composition_template(gm, {})
    )
    assert restored.get_group(gid).source_pattern == "*_org*"


def test_a_template_written_before_binding_loads_unbound():
    template = {
        "version": "4.0", "format": "composition_group", "settings": {},
        "root_group_id": 0,
        "groups": [{"id": 0, "name": "G", "default_duration_ms": 100, "entries": []}],
    }
    restored, _ = TemplateManager.import_composition_template(template)
    assert restored.get_group(0).source_pattern is None


# ── The batch path accepts a template that needs no fixed indices ────────────

def test_a_bound_template_needs_no_tiles_up_front():
    """estimate_required_tiles counts indices the entries name; a bound group
    names none, and the batch run must not refuse it for having too few."""
    gm = GroupManager()
    gm.set_root_group_id(
        gm.add_group(CompositionGroup(name="all", source_pattern="*_tile_*"))
    )
    template = TemplateManager.export_composition_template(gm, {})
    assert TemplateManager.estimate_required_tiles(template) == 0


def test_a_bound_template_builds_a_gif_through_the_batch_processor(tmp_path):
    from src.core.batch_processor import BatchProcessor

    sheet = tmp_path / "sheet.png"
    strip = Image.new("RGB", (40, 10))
    for i in range(4):
        strip.paste(Image.new("RGB", (10, 10), (i * 60, 20, 20)), (i * 10, 0))
    strip.save(sheet)

    gm = GroupManager()
    gm.set_root_group_id(gm.add_group(
        CompositionGroup(name="all", default_duration_ms=100,
                         source_pattern="*_tile_*", tail_duration_ms=500)
    ))
    template = TemplateManager.export_composition_template(gm, {})

    out = BatchProcessor().process_single_image(
        str(sheet), template, split_mode="grid", split_rows=1, split_cols=4,
        tile_width=10, tile_height=10, output_path=str(tmp_path / "o.gif"),
        output_width=10, output_height=10,
    )

    with Image.open(out) as im:
        durations = [f.info.get("duration") for f in ImageSequence.Iterator(im)]
    assert durations == [100, 100, 100, 500]
