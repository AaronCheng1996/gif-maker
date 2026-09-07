from PIL import Image
from src.core.gif_builder import GifBuilder
from src.core.image_loader import MaterialManager
from src.core.sequence_editor import SequenceEditor
from src.core.layer_timeline import LayerTimelineEditor, LayerFrame
from src.core.group_manager import GroupManager


def test_build_from_sequence_solid_bg(tmp_gif_path, rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="a", duration=90)
    # Second material slightly different color to prevent optimization collapsing frames
    different = Image.new('RGB', rgb_image_small.size, (11, 21, 31))
    mm.add_material(different, name="b", duration=110)
    se = SequenceEditor()
    se.add_frame(0, 90)
    se.add_frame(1, 110)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 0, 0, 255)
    gb.build_from_sequence(mm, se, output_path=str(tmp_gif_path))
    info = gb.get_gif_info(str(tmp_gif_path))
    assert info['frame_count'] == 2
    assert info['has_transparency'] is False


def test_resize_and_info(tmp_path, rgba_image_small):
    # Prepare a small gif first
    gb = GifBuilder()
    gb.set_output_size(12, 10)
    gb.set_background_color(0, 0, 0, 0)
    out = tmp_path / "a.gif"
    img1 = rgba_image_small.copy()
    img2 = rgba_image_small.copy()
    img2.putpixel((0, 0), (0, 255, 0, 255))
    gb.build_from_images([img1, img2], durations=[50, 50], output_path=str(out))

    resized = tmp_path / "a_small.gif"
    gb.resize_gif(str(out), str(resized), scale_factor=0.5)
    info = gb.get_gif_info(str(resized))
    assert info['frame_count'] == 2
    assert info['size'][0] == 6 and info['size'][1] == 5


def test_build_from_layer_timeline(tmp_gif_path, rgb_image_small):
    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="a")
    mm.add_material(rgb_image_small, name="b")

    ed = LayerTimelineEditor()
    tl_a = ed.add_layer_track("A")
    tl_b = ed.add_layer_track("B")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.layer_tracks[tl_a].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    ed.layer_tracks[tl_b].frames[1] = LayerFrame(material_index=1, x=1, y=1)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(0, 0, 0, 0)
    gb.build_from_layer_timeline(ed, mm, output_path=str(tmp_gif_path))
    info = gb.get_gif_info(str(tmp_gif_path))
    assert info['frame_count'] == 2


def test_build_gif_from_group_with_loops(tmp_gif_path):
    """CompositionGroup: SubGroupEntry with loop_count=2 → 6 frames + 1 = 7 total."""
    from src.core.composition_group import CompositionGroup, FrameEntry, SubGroupEntry

    mm = MaterialManager()
    for i in range(4):
        mm.add_material(Image.new("RGB", (10, 10), (i * 60, i * 40, i * 20)), name=f"mat_{i}")

    # sub group: 3 frames (mat 0,1,2)
    group_mgr = GroupManager()
    sub = CompositionGroup(name="Sub", default_duration_ms=100)
    sub.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    sub.entries.append(FrameEntry(material_index=1, x=0, y=0, duration_ms=100))
    sub.entries.append(FrameEntry(material_index=2, x=0, y=0, duration_ms=100))
    group_mgr.add_group(sub)  # id=0

    # root: sub×2 + single mat3 → 3×2 + 1 = 7 frames
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(SubGroupEntry(group_id=0, loop_count=2))
    root.entries.append(FrameEntry(material_index=3, x=0, y=0, duration_ms=100))
    group_mgr.add_group(root)  # id=1

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 255, 255, 255)
    gb.build_gif_from_group(1, group_mgr, mm, str(tmp_gif_path))

    info = gb.get_gif_info(str(tmp_gif_path))
    assert info["frame_count"] == 7


def test_build_gif_from_group_empty_group_no_crash(tmp_gif_path, rgb_image_small):
    """Empty subgroup produces no frames; root still exports the non-empty entries."""
    from src.core.composition_group import CompositionGroup, FrameEntry, SubGroupEntry

    mm = MaterialManager()
    mm.add_material(rgb_image_small, name="mat_0")

    group_mgr = GroupManager()
    empty = CompositionGroup(name="Empty")  # no entries
    group_mgr.add_group(empty)  # id=0

    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(SubGroupEntry(group_id=0, loop_count=1))  # expands to nothing
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    group_mgr.add_group(root)  # id=1

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 255, 255, 255)
    gb.build_gif_from_group(1, group_mgr, mm, str(tmp_gif_path))

    info = gb.get_gif_info(str(tmp_gif_path))
    assert info["frame_count"] == 1


def test_build_gif_from_group_subgroup_xy_offset(tmp_gif_path):
    """SubGroupEntry x/y offset shifts materials during expansion."""
    from src.core.composition_group import CompositionGroup, FrameEntry, SubGroupEntry

    mm = MaterialManager()
    img = Image.new("RGB", (8, 8), (0, 128, 255))
    mm.add_material(img, name="tile")

    group_mgr = GroupManager()
    sub = CompositionGroup(name="Sub", default_duration_ms=100)
    sub.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    group_mgr.add_group(sub)  # id=0

    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(SubGroupEntry(group_id=0, loop_count=1, x=5, y=10))
    group_mgr.add_group(root)  # id=1

    gb = GifBuilder()
    gb.set_output_size(30, 30)
    gb.set_background_color(255, 255, 255, 255)
    gb.build_gif_from_group(1, group_mgr, mm, str(tmp_gif_path))

    info = gb.get_gif_info(str(tmp_gif_path))
    assert info["frame_count"] == 1
    assert info["size"] == (30, 30)


def test_build_apng_and_webp_from_group(tmp_path):
    from src.core.composition_group import CompositionGroup, FrameEntry

    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), name="a")
    mm.add_material(Image.new("RGBA", (10, 10), (0, 255, 0, 255)), name="b")

    group_mgr = GroupManager()
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=80))
    root.entries.append(FrameEntry(material_index=1, x=0, y=0, duration_ms=120))
    gid = group_mgr.add_group(root)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(0, 0, 0, 0)  # transparent
    gb.set_loop(0)

    apng_path = tmp_path / "out.png"
    webp_path = tmp_path / "out.webp"
    gb.build_apng_from_group(gid, group_mgr, mm, str(apng_path))
    gb.build_webp_from_group(gid, group_mgr, mm, str(webp_path), quality=70)

    assert apng_path.exists()
    assert webp_path.exists()
    assert getattr(Image.open(apng_path), "n_frames", 1) == 2
    assert getattr(Image.open(webp_path), "n_frames", 1) == 2


def test_build_apng_from_group_raises_on_empty_materials(tmp_path):
    from src.core.composition_group import CompositionGroup

    mm = MaterialManager()
    group_mgr = GroupManager()
    root = CompositionGroup(name="Root", default_duration_ms=100)
    gid = group_mgr.add_group(root)

    gb = GifBuilder()
    gb.set_output_size(10, 10)

    import pytest
    with pytest.raises(ValueError):
        gb.build_apng_from_group(gid, group_mgr, mm, str(tmp_path / "out.png"))


def test_build_webp_from_group_respects_solid_background(tmp_path):
    """A solid (non-transparent) background should flatten the material's own
    alpha channel to fully opaque, unlike the transparent-background case."""
    from src.core.composition_group import CompositionGroup, FrameEntry

    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 128)), name="a")

    group_mgr = GroupManager()
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(FrameEntry(material_index=0, x=0, y=0, duration_ms=100))
    gid = group_mgr.add_group(root)

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(0, 0, 255, 255)  # solid blue, opaque

    out = tmp_path / "solid.webp"
    gb.build_webp_from_group(gid, group_mgr, mm, str(out))

    img = Image.open(out).convert("RGBA")
    _, _, _, a = img.getpixel((5, 5))
    assert a == 255


def test_compose_flat_image_stacks_layers_bottom_to_top():
    """compose_flat_image treats FrameEntry order as simultaneous stacked layers,
    not a sequential animation — later entries paint over earlier ones."""
    from src.core.composition_group import FrameEntry

    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (10, 10), (255, 0, 0, 255)), name="bottom")
    mm.add_material(Image.new("RGBA", (10, 10), (0, 255, 0, 255)), name="top")

    entries = [
        FrameEntry(material_index=0, x=0, y=0),
        FrameEntry(material_index=1, x=0, y=0),
    ]

    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(0, 0, 0, 0)

    result = gb.compose_flat_image(entries, mm)
    assert result.size == (10, 10)
    assert result.getpixel((5, 5)) == (0, 255, 0, 255)


def test_compose_flat_image_respects_offsets():
    from src.core.composition_group import FrameEntry

    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (5, 5), (255, 0, 0, 255)), name="a")

    entries = [FrameEntry(material_index=0, x=8, y=3)]

    gb = GifBuilder()
    gb.set_output_size(20, 20)
    gb.set_background_color(0, 0, 0, 0)

    result = gb.compose_flat_image(entries, mm)
    assert result.getpixel((10, 5)) == (255, 0, 0, 255)  # inside the placed square
    assert result.getpixel((0, 0))[3] == 0                # outside, still transparent


def test_compose_flat_image_skips_non_frame_entries():
    from src.core.composition_group import FrameEntry, SubGroupEntry

    mm = MaterialManager()
    mm.add_material(Image.new("RGBA", (5, 5), (255, 0, 0, 255)), name="a")

    entries = [FrameEntry(material_index=0, x=0, y=0), SubGroupEntry(group_id=0)]

    gb = GifBuilder()
    gb.set_output_size(5, 5)
    gb.set_background_color(0, 0, 0, 0)

    # Should not raise despite the SubGroupEntry being present.
    result = gb.compose_flat_image(entries, mm)
    assert result.size == (5, 5)


# ── A pinned tail pause belongs to the group, not to one frame ───────────────

def _pinned_group(tail_ms, frame_count=3):
    """A group of frame_count frames at 100ms whose loop pause is pinned."""
    from src.core.composition_group import CompositionGroup, FrameEntry

    mm = MaterialManager()
    for i in range(frame_count + 1):
        mm.add_material(Image.new("RGB", (10, 10), (i * 50, i * 30, i * 10)), name=f"m{i}")

    gm = GroupManager()
    g = CompositionGroup(name="G", default_duration_ms=100, tail_duration_ms=tail_ms)
    for i in range(frame_count):
        g.entries.append(FrameEntry(material_index=i))
    gid = gm.add_group(g)
    return GifBuilder(), gid, gm, mm, g


def test_a_pinned_pause_lands_on_the_last_frame():
    gb, gid, gm, mm, _ = _pinned_group(2000)
    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100, 2000]


def test_an_unpinned_group_times_every_frame_by_itself():
    gb, gid, gm, mm, _ = _pinned_group(None)
    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100, 100]


def test_appending_a_frame_moves_the_pause_and_frees_the_old_last_one():
    """The point of pinning: a new material must not strand the pause mid-timeline."""
    from src.core.composition_group import FrameEntry

    gb, gid, gm, mm, g = _pinned_group(2000)
    g.entries.append(FrameEntry(material_index=3))

    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100, 100, 2000]


def test_the_pause_overrides_the_last_frames_own_duration():
    gb, gid, gm, mm, g = _pinned_group(2000)
    g.entries[-1].duration_ms = 40
    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations[-1] == 2000


def test_a_displaced_frame_keeps_the_duration_it_was_given():
    """Pinning must not have written into the frame it was standing on."""
    from src.core.composition_group import FrameEntry

    gb, gid, gm, mm, g = _pinned_group(2000)
    g.entries[-1].duration_ms = 40
    g.entries.append(FrameEntry(material_index=3))

    _, durations = gb._expand_composition_group(gid, gm, mm)
    assert durations == [100, 100, 40, 2000]


def test_a_group_ending_on_a_sub_group_ignores_the_pause():
    """That group has no last frame of its own — the timing lives in what it
    ends on, and overwriting the sub-group's final frame would reach across a
    boundary the editor does not show."""
    from src.core.composition_group import CompositionGroup, FrameEntry, SubGroupEntry

    mm = MaterialManager()
    for i in range(3):
        mm.add_material(Image.new("RGB", (10, 10), (i * 50, 0, 0)), name=f"m{i}")

    gm = GroupManager()
    sub = CompositionGroup(name="Sub", default_duration_ms=70)
    sub.entries.append(FrameEntry(material_index=0))
    sub_id = gm.add_group(sub)

    root = CompositionGroup(name="Root", default_duration_ms=100, tail_duration_ms=2000)
    root.entries.append(FrameEntry(material_index=1))
    root.entries.append(SubGroupEntry(group_id=sub_id))
    root_id = gm.add_group(root)

    _, durations = GifBuilder()._expand_composition_group(root_id, gm, mm)
    assert durations == [100, 70]


def test_an_empty_group_with_a_pause_still_expands_to_nothing():
    from src.core.composition_group import CompositionGroup

    gm = GroupManager()
    gid = gm.add_group(CompositionGroup(name="Empty", tail_duration_ms=2000))
    frames, durations = GifBuilder()._expand_composition_group(gid, gm, MaterialManager())
    assert frames == [] and durations == []


def test_the_pause_repeats_with_every_loop_of_the_group():
    """It is the pause *before the group loops*, so each pass ends on it."""
    from src.core.composition_group import CompositionGroup, SubGroupEntry

    gb, gid, gm, mm, _ = _pinned_group(2000, frame_count=2)
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(SubGroupEntry(group_id=gid, loop_count=2))
    root_id = gm.add_group(root)

    _, durations = gb._expand_composition_group(root_id, gm, mm)
    assert durations == [100, 2000, 100, 2000]


def test_a_reference_override_still_wins_over_the_pause():
    """duration_override_ms retimes every frame of that one reference, pause
    included — it is the coarser instrument and stays the outer one."""
    from src.core.composition_group import CompositionGroup, SubGroupEntry

    gb, gid, gm, mm, _ = _pinned_group(2000, frame_count=2)
    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(SubGroupEntry(group_id=gid, duration_override_ms=66))
    root_id = gm.add_group(root)

    _, durations = gb._expand_composition_group(root_id, gm, mm)
    assert durations == [66, 66]


def test_a_pinned_pause_survives_a_template_round_trip():
    from src.core.composition_group import CompositionGroup, FrameEntry
    from src.core.template_manager import TemplateManager

    gm = GroupManager()
    g = CompositionGroup(name="G", default_duration_ms=100, tail_duration_ms=2000)
    g.entries.append(FrameEntry(material_index=0))
    gid = gm.add_group(g)
    gm.set_root_group_id(gid)

    template = TemplateManager.export_composition_template(gm, {})
    restored, _ = TemplateManager.import_composition_template(template)

    assert restored.get_group(gid).tail_duration_ms == 2000


def test_a_template_written_before_pinning_loads_unpinned():
    from src.core.template_manager import TemplateManager

    template = {
        "version": "4.0",
        "format": "composition_group",
        "settings": {},
        "root_group_id": 0,
        "groups": [{
            "id": 0, "name": "G", "default_duration_ms": 100,
            "entries": [{"type": "frame", "material_index": 0,
                         "x": 0, "y": 0, "duration_ms": None}],
        }],
    }
    restored, _ = TemplateManager.import_composition_template(template)
    assert restored.get_group(0).tail_duration_ms is None
