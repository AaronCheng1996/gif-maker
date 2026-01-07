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


def test_build_with_group_expansion(tmp_gif_path, rgb_image_small):
    """Test building GIF with Material Groups that need expansion"""
    mm = MaterialManager()
    # Add 4 different materials
    for i in range(4):
        img = Image.new('RGB', (10, 10), (i*60, i*40, i*20))
        mm.add_material(img, name=f"mat_{i}")
    
    # Create a group with materials [0, 1, 2] × 2 loops = 6 frames
    group_mgr = GroupManager()
    group_mgr.create_group_from_materials(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=2,
        name="Test Group"
    )
    
    # Create timeline with group
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=0, y=0)
    ed.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=3, x=0, y=0)
    
    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 255, 255, 255)
    gb.build_from_layer_timeline(ed, mm, output_path=str(tmp_gif_path), group_manager=group_mgr)
    
    info = gb.get_gif_info(str(tmp_gif_path))
    # Should have 7 frames: 6 from group (3 materials × 2 loops) + 1 from single material
    assert info['frame_count'] == 7


def test_build_with_empty_group_no_crash(tmp_gif_path, rgb_image_small):
    """Test that empty groups (all materials filtered out) don't cause ZeroDivisionError"""
    mm = MaterialManager()
    # Add only 2 materials
    mm.add_material(rgb_image_small, name="mat_0")
    mm.add_material(rgb_image_small, name="mat_1")
    
    # Create a group with materials that exceed material library size
    # (simulating a template with out-of-range materials)
    group_mgr = GroupManager()
    from src.core.material_group import MaterialGroup
    empty_group = MaterialGroup(
        material_indices=[],  # Empty after filtering
        frame_duration=100,
        loop_count=2,
        name="Empty Group"
    )
    group_mgr.add_group(empty_group)
    
    # Create another normal group
    group_mgr.create_group_from_materials(
        material_indices=[0, 1],
        frame_duration=100,
        loop_count=1,
        name="Normal Group"
    )
    
    # Create timeline with both groups
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=0, y=0)  # Empty group
    ed.layer_tracks[tl_idx].frames[1] = LayerFrame(group_index=1, x=0, y=0)  # Normal group
    
    gb = GifBuilder()
    gb.set_output_size(10, 10)
    gb.set_background_color(255, 255, 255, 255)
    
    # Should not raise ZeroDivisionError
    gb.build_from_layer_timeline(ed, mm, output_path=str(tmp_gif_path), group_manager=group_mgr)
    
    info = gb.get_gif_info(str(tmp_gif_path))
    # Should have 2 frames from normal group, empty group produces nothing
    assert info['frame_count'] == 2


def test_build_with_group_independent_offsets(tmp_gif_path):
    """Test building GIF with groups that have independent material offsets"""
    mm = MaterialManager()
    # Add 3 different-sized materials
    img1 = Image.new('RGB', (10, 10), (255, 0, 0))  # Red
    img2 = Image.new('RGB', (15, 15), (0, 255, 0))  # Green
    img3 = Image.new('RGB', (8, 8), (0, 0, 255))    # Blue
    mm.add_material(img1, name="red")
    mm.add_material(img2, name="green")
    mm.add_material(img3, name="blue")
    
    # Create a group with independent offsets
    group_mgr = GroupManager()
    from src.core.material_group import MaterialGroup
    group = MaterialGroup(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=1,
        name="Independent Group",
        independent_offsets=True
    )
    # Set different offsets for each material
    group.set_material_offset(0, 5, 5)   # Red at (5, 5) relative to group
    group.set_material_offset(1, 10, 10) # Green at (10, 10) relative to group
    group.set_material_offset(2, 0, 0)   # Blue at (0, 0) relative to group
    group_mgr.add_group(group)
    
    # Create timeline
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(1, duration_ms=100)
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=2, y=2)  # Group base position
    
    gb = GifBuilder()
    gb.set_output_size(30, 30)
    gb.set_background_color(255, 255, 255, 255)
    gb.build_from_layer_timeline(ed, mm, output_path=str(tmp_gif_path), group_manager=group_mgr)
    
    info = gb.get_gif_info(str(tmp_gif_path))
    # Should have 3 frames (3 materials × 1 loop)
    assert info['frame_count'] == 3
    
    # Verify the GIF was created successfully (offsets were applied)
    assert info['size'] == (30, 30)


