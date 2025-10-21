from src.core.multi_timeline import MultiTimelineEditor, TimelineFrame


def test_add_timelines_and_timebase():
    ed = MultiTimelineEditor()
    a = ed.add_timeline("A")
    b = ed.add_timeline("B")
    ed.add_timebase_frames(3, duration_ms=80)
    assert ed.get_frame_count() == 3
    assert len(ed.timelines[a].frames) == 3
    assert len(ed.timelines[b].frames) == 3


def test_move_duplicate_remove_timebase():
    ed = MultiTimelineEditor()
    ed.add_timeline("A")
    ed.add_timebase_frames(3, duration_ms=100)
    ed.move_timebase_frame(0, 2)
    assert ed.durations_ms == [100, 100, 100]
    ed.duplicate_timebase_frame(1)
    assert ed.get_frame_count() == 4
    ed.remove_timebase_frames([0, 3])
    assert ed.get_frame_count() == 2


def test_iter_frame_layers_offsets():
    ed = MultiTimelineEditor()
    t1 = ed.add_timeline("Bottom")
    t2 = ed.add_timeline("Top")
    ed.add_timebase_frames(2, duration_ms=90)

    ed.timelines[t1].offset_x = 1
    ed.timelines[t1].offset_y = 2
    ed.timelines[t1].frames[0] = TimelineFrame(material_index=0, x=5, y=6)
    ed.timelines[t2].frames[0] = TimelineFrame(material_index=1, x=7, y=8)

    layers = ed.iter_frame_layers(0)
    # bottom to top
    assert layers == [(0, 5 + 1, 6 + 2), (1, 7, 8)]


