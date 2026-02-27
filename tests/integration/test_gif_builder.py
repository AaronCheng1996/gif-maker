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


