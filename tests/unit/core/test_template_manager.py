from src.core.template_manager import TemplateManager
from src.core.multi_timeline import MultiTimelineEditor, TimelineFrame


def test_export_apply_multi_template_roundtrip(tmp_path):
    ed = MultiTimelineEditor()
    tl_idx = ed.add_timeline("Main")
    ed.add_timebase_frames(2, duration_ms=100)
    ed.timelines[tl_idx].frames[0] = TimelineFrame(material_index=3, x=1, y=2)
    ed.timelines[tl_idx].frames[1] = TimelineFrame(material_index=None, x=0, y=0)

    tmpl = TemplateManager.export_multi_template(
        ed, output_width=32, output_height=32, loop_count=0, transparent_bg=True, color_count=128
    )

    p = tmp_path / "tmpl.json"
    TemplateManager.save_template_to_file(tmpl, str(p))
    loaded = TemplateManager.load_template_from_file(str(p))

    new_ed, settings = TemplateManager.apply_multi_template(loaded, material_index_mapping={3: 7})
    assert settings["output_width"] == 32
    assert new_ed.get_frame_count() == 2
    # mapped index
    assert new_ed.timelines[0].frames[0].material_index == 7


def test_get_template_info_multi():
    ed = MultiTimelineEditor()
    tl_idx = ed.add_timeline("T")
    ed.add_timebase_frames(1, duration_ms=90)
    ed.timelines[tl_idx].frames[0] = TimelineFrame(material_index=5, x=0, y=0)
    tmpl = TemplateManager.export_multi_template(ed, 16, 16, 0, True)

    info = TemplateManager.get_template_info(tmpl)
    assert info["format"] == "multi_timeline"
    assert info["frame_count"] == 1
    assert info["timeline_count"] == 1


