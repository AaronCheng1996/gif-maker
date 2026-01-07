"""
Tests for Batch Processor and Template Manager fixes
"""

import pytest
import json
from pathlib import Path
from PIL import Image
from src.core.batch_processor import BatchProcessor
from src.core.template_manager import TemplateManager
from src.core.image_loader import MaterialManager
from src.core.layer_timeline import LayerTimelineEditor, LayerFrame
from src.core.group_manager import GroupManager
from src.core.material_group import MaterialGroup


def test_batch_processor_with_layer_timeline_template(tmp_path):
    """Test batch processor with layer timeline template (multi-timeline format with groups)"""
    # Create a template with groups
    editor = LayerTimelineEditor()
    tl_idx = editor.add_layer_track("Main")
    editor.add_timebase_frames(2, duration_ms=100)
    editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=5, y=5)
    editor.layer_tracks[tl_idx].frames[1] = LayerFrame(group_index=0, x=10, y=10)
    
    group_mgr = GroupManager()
    group = MaterialGroup(
        material_indices=[0, 1],
        frame_duration=100,
        loop_count=2,
        name="Test Group"
    )
    group_mgr.add_group(group)
    
    settings = {
        'output_width': 32,
        'output_height': 32,
        'transparent_bg': True,
        'color_count': 256
    }
    
    # Export template
    template_dict = TemplateManager.export_layer_timeline_template(
        editor, group_mgr, settings['transparent_bg'], settings['color_count']
    )
    
    # Create a source image
    source_img = Image.new('RGB', (16, 16), (100, 150, 200))
    source_path = tmp_path / "source.png"
    source_img.save(source_path)
    
    output_path = tmp_path / "output.gif"
    
    # Use batch processor's process_single_image method
    bp = BatchProcessor()
    result = bp.process_single_image(
        image_path=str(source_path),
        template=template_dict,
        split_mode="grid",
        split_rows=1,
        split_cols=2,  # Split into 2 tiles
        tile_width=0,
        tile_height=0,
        color_count=256,
        output_path=str(output_path)
    )
    
    # Verify result
    assert Path(result).exists()
    with Image.open(result) as gif:
        assert gif.format == 'GIF'
        # Should have frames from the template
        assert gif.n_frames >= 1


def test_template_manager_returns_group_manager(tmp_path):
    """Test that apply_multi_template returns three values: editor, group_manager, settings
    
    This test verifies the fix for BATCH_PROCESSOR_FIX where the method was only
    receiving 2 values instead of 3, causing settings to be a GroupManager object.
    """
    # Create a template
    editor = LayerTimelineEditor()
    tl_idx = editor.add_layer_track("Main")
    editor.add_timebase_frames(1, duration_ms=100)
    editor.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=0, x=0, y=0)
    
    group_mgr = GroupManager()
    group = MaterialGroup(
        material_indices=[0],
        frame_duration=100,
        loop_count=1,
        name="Test Group"
    )
    group_mgr.add_group(group)
    
    transparent_bg = True
    color_count = 128
    
    # Export template
    template_dict = TemplateManager.export_layer_timeline_template(
        editor, group_mgr, transparent_bg, color_count
    )
    
    # Apply template - should return 3 values (this is the fix)
    # BEFORE FIX: Only 2 values were received, causing settings to be GroupManager
    # AFTER FIX: Correctly returns 3 values
    result = TemplateManager.apply_layer_timeline_template(template_dict)
    assert len(result) == 3, "apply_layer_timeline_template should return 3 values"
    
    returned_editor, returned_group_mgr, returned_settings = result
    
    # Verify types (the bug would make settings a GroupManager object)
    assert isinstance(returned_editor, LayerTimelineEditor), "First value should be LayerTimelineEditor"
    assert isinstance(returned_group_mgr, GroupManager), "Second value should be GroupManager"
    assert isinstance(returned_settings, dict), "Third value should be dict (bug would make it GroupManager)"
    
    # Verify settings content (bug would cause KeyError or AttributeError)
    # Note: In v3.0, output_width/height are NOT stored in templates
    assert returned_settings['transparent_bg'] is True
    assert returned_settings['color_count'] == 128
    
    # Verify group was loaded correctly
    assert len(returned_group_mgr) == 1
    loaded_group = returned_group_mgr.get_group(0)
    assert loaded_group is not None
    assert loaded_group.name == "Test Group"


def test_template_with_empty_groups_no_crash(tmp_path):
    """Test that templates with empty groups don't cause ZeroDivisionError
    
    This test verifies the fix for EMPTY_GROUP_FIX where empty groups (all materials
    filtered out) would cause a ZeroDivisionError in gif_builder.py
    """
    # Create a template with an empty group
    editor = LayerTimelineEditor()
    tl_idx = editor.add_layer_track("Main")
    editor.add_timebase_frames(2, duration_ms=100)
    editor.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=0, y=0)  # Empty group
    editor.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=0, x=0, y=0)  # Normal material
    
    group_mgr = GroupManager()
    empty_group = MaterialGroup(
        material_indices=[],  # Empty group (simulating filtered out materials)
        frame_duration=100,
        loop_count=1,
        name="Empty Group"
    )
    group_mgr.add_group(empty_group)
    
    settings = {
        'output_width': 16,
        'output_height': 16,
        'transparent_bg': False,
        'color_count': 256
    }
    
    # Export template
    template_dict = TemplateManager.export_layer_timeline_template(
        editor, group_mgr, settings['transparent_bg'], settings['color_count']
    )
    
    # Create source image
    source_img = Image.new('RGB', (16, 16), (100, 150, 200))
    source_path = tmp_path / "test.png"
    source_img.save(source_path)
    
    output_path = tmp_path / "output.gif"
    
    # Run batch processor - should not crash with ZeroDivisionError
    bp = BatchProcessor()
    result = bp.process_single_image(
        image_path=str(source_path),
        template=template_dict,
        split_mode="grid",
        split_rows=1,
        split_cols=1,  # Single tile
        tile_width=0,
        tile_height=0,
        color_count=256,
        output_path=str(output_path)
    )
    
    # Should succeed without ZeroDivisionError
    assert Path(result).exists()
    with Image.open(result) as gif:
        assert gif.format == 'GIF'
        # Empty group produces no frames, so only 1 frame from normal material
        assert gif.n_frames >= 1

