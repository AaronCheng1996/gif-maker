from src.core.template_manager import TemplateManager
from src.core.layer_timeline import LayerTimelineEditor, LayerFrame
from src.core.group_manager import GroupManager


def test_export_apply_layer_timeline_template_roundtrip(tmp_path):
    """Test exporting and applying layer timeline template with material index mapping"""
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=3, x=1, y=2)
    ed.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=None, x=0, y=0)

    # Use new template format (v3.0) - only encoding settings
    tmpl = TemplateManager.export_layer_timeline_template(
        ed, group_manager=None, transparent_bg=True, color_count=128
    )

    p = tmp_path / "tmpl.json"
    TemplateManager.save_template_to_file(tmpl, str(p))
    loaded = TemplateManager.load_template_from_file(str(p))

    new_ed, new_group_manager, settings = TemplateManager.apply_layer_timeline_template(
        loaded, material_index_mapping={3: 7}
    )
    assert settings["transparent_bg"] is True
    assert settings["color_count"] == 128
    assert new_ed.get_frame_count() == 2
    # mapped index
    assert new_ed.layer_tracks[0].frames[0].material_index == 7


def test_export_apply_template_with_groups(tmp_path):
    """Test template export/import with Material Groups"""
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(2, duration_ms=100)
    
    # Create a group
    group_mgr = GroupManager()
    group_mgr.create_group_from_materials(
        material_indices=[0, 1, 2],
        frame_duration=100,
        loop_count=2,
        name="Test Group"
    )
    
    # Use group in timeline
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=0, y=0)
    ed.layer_tracks[tl_idx].frames[1] = LayerFrame(material_index=5, x=10, y=10)
    
    # Export with groups
    tmpl = TemplateManager.export_layer_timeline_template(
        ed, group_manager=group_mgr, transparent_bg=False, color_count=256
    )
    
    # Verify groups are in template
    assert "groups" in tmpl
    assert len(tmpl["groups"]) == 1
    assert tmpl["groups"][0]["name"] == "Test Group"
    
    # Save and reload
    p = tmp_path / "tmpl_with_groups.json"
    TemplateManager.save_template_to_file(tmpl, str(p))
    loaded = TemplateManager.load_template_from_file(str(p))
    
    # Apply template
    new_ed, new_group_mgr, settings = TemplateManager.apply_layer_timeline_template(loaded)
    
    # Verify groups were restored
    assert len(new_group_mgr) == 1
    restored_group = new_group_mgr.get_group(0)
    assert restored_group.name == "Test Group"
    assert restored_group.material_indices == [0, 1, 2]
    assert restored_group.frame_duration == 100
    assert restored_group.loop_count == 2
    
    # Verify timeline references group
    assert new_ed.layer_tracks[0].frames[0].group_index == 0
    assert new_ed.layer_tracks[0].frames[1].material_index == 5


def test_template_auto_filter_materials(tmp_path):
    """Test that templates auto-filter out-of-range materials"""
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("Main")
    ed.add_timebase_frames(1, duration_ms=100)
    
    # Create a group with materials 0-22
    group_mgr = GroupManager()
    group_mgr.create_group_from_materials(
        material_indices=list(range(23)),  # 0-22
        frame_duration=100,
        loop_count=1,
        name="Large Group"
    )
    
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(group_index=0, x=0, y=0)
    
    # Export template
    tmpl = TemplateManager.export_layer_timeline_template(
        ed, group_manager=group_mgr, transparent_bg=True
    )
    
    # Apply template with max_material_index=19 (only 0-18 exist)
    new_ed, new_group_mgr, settings = TemplateManager.apply_layer_timeline_template(
        tmpl, max_material_index=19
    )
    
    # Verify materials were filtered
    restored_group = new_group_mgr.get_group(0)
    assert len(restored_group.material_indices) == 19  # Only 0-18
    assert max(restored_group.material_indices) < 19


def test_get_template_info_layer_timeline():
    """Test getting template info from layer timeline format"""
    ed = LayerTimelineEditor()
    tl_idx = ed.add_layer_track("T")
    ed.add_timebase_frames(1, duration_ms=90)
    ed.layer_tracks[tl_idx].frames[0] = LayerFrame(material_index=5, x=0, y=0)
    tmpl = TemplateManager.export_layer_timeline_template(ed, None, True)

    info = TemplateManager.get_template_info(tmpl)
    assert info["format"] == "layer_timeline"
    assert info["frame_count"] == 1
    assert info["layer_track_count"] == 1


