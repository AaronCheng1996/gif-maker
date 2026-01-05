from src.core.layer_timeline import LayerTimelineEditor, LayerFrame


def test_add_layer_tracks_and_timebase():
    ed = LayerTimelineEditor()
    a = ed.add_layer_track("A")
    b = ed.add_layer_track("B")
    ed.add_timebase_frames(3, duration_ms=80)
    assert ed.get_frame_count() == 3
    assert len(ed.layer_tracks[a].frames) == 3
    assert len(ed.layer_tracks[b].frames) == 3


def test_move_duplicate_remove_timebase():
    ed = LayerTimelineEditor()
    ed.add_layer_track("A")
    ed.add_timebase_frames(3, duration_ms=100)
    ed.move_timebase_frame(0, 2)
    assert ed.durations_ms == [100, 100, 100]
    ed.duplicate_timebase_frame(1)
    assert ed.get_frame_count() == 4
    ed.remove_timebase_frames([0, 3])
    assert ed.get_frame_count() == 2


def test_iter_frame_layers_offsets():
    ed = LayerTimelineEditor()
    t1 = ed.add_layer_track("Bottom")
    t2 = ed.add_layer_track("Top")
    ed.add_timebase_frames(2, duration_ms=90)

    ed.layer_tracks[t1].offset_x = 1
    ed.layer_tracks[t1].offset_y = 2
    ed.layer_tracks[t1].frames[0] = LayerFrame(material_index=0, x=5, y=6)
    ed.layer_tracks[t2].frames[0] = LayerFrame(material_index=1, x=7, y=8)

    layers = ed.iter_frame_layers(0)
    # bottom to top (material_index, group_index, x, y)
    assert layers == [(0, None, 5 + 1, 6 + 2), (1, None, 7, 8)]


