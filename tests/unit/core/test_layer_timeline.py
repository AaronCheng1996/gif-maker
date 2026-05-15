"""Unit tests for src/core/layer_timeline.py"""

import pytest
from src.core.layer_timeline import LayerTimelineEditor, LayerFrame, LayerTrack


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_editor(n_tracks: int = 1, n_frames: int = 3, duration_ms: int = 100):
    ed = LayerTimelineEditor()
    for i in range(n_tracks):
        ed.add_layer_track(f"Track{i}")
    if n_frames > 0:
        ed.add_timebase_frames(n_frames, duration_ms=duration_ms)
    return ed


# ──────────────────────────────────────────────────────────────────────────────
# Layer track management
# ──────────────────────────────────────────────────────────────────────────────

class TestAddLayerTracks:
    def test_returns_sequential_indices(self):
        ed = LayerTimelineEditor()
        assert ed.add_layer_track("A") == 0
        assert ed.add_layer_track("B") == 1
        assert ed.add_layer_track("C") == 2

    def test_track_count_matches(self):
        ed = _make_editor(n_tracks=3, n_frames=0)
        assert len(ed.layer_tracks) == 3

    def test_each_track_gets_timebase_frames(self):
        ed = _make_editor(n_tracks=2, n_frames=4)
        assert len(ed.layer_tracks[0].frames) == 4
        assert len(ed.layer_tracks[1].frames) == 4

    def test_frames_default_to_blank_layer_frame(self):
        ed = _make_editor(n_tracks=1, n_frames=2)
        frame = ed.layer_tracks[0].frames[0]
        assert frame.material_index is None
        assert frame.x == 0 and frame.y == 0


class TestRemoveLayerTrack:
    def test_remove_middle_track(self):
        ed = _make_editor(n_tracks=3, n_frames=0)
        ed.remove_layer_track(1)
        assert len(ed.layer_tracks) == 2
        assert ed.layer_tracks[0].name == "Track0"
        assert ed.layer_tracks[1].name == "Track2"

    def test_cannot_remove_last_track(self):
        ed = _make_editor(n_tracks=1, n_frames=0)
        ed.remove_layer_track(0)
        assert len(ed.layer_tracks) == 1

    def test_main_track_index_clamped_after_remove(self):
        ed = _make_editor(n_tracks=2, n_frames=0)
        ed.set_main_track(1)
        ed.remove_layer_track(1)
        assert ed.main_track_index == 0


class TestMoveLayerTrack:
    def test_move_forward(self):
        ed = _make_editor(n_tracks=3, n_frames=0)
        ed.move_layer_track(0, 2)
        assert [t.name for t in ed.layer_tracks] == ["Track1", "Track2", "Track0"]

    def test_main_track_index_follows_moved_track(self):
        ed = _make_editor(n_tracks=3, n_frames=0)
        ed.set_main_track(0)
        ed.move_layer_track(0, 2)
        assert ed.main_track_index == 2

    def test_move_out_of_bounds_is_noop(self):
        ed = _make_editor(n_tracks=2, n_frames=0)
        original = [t.name for t in ed.layer_tracks]
        ed.move_layer_track(0, 99)
        assert [t.name for t in ed.layer_tracks] == original


# ──────────────────────────────────────────────────────────────────────────────
# Timebase (frame count and durations)
# ──────────────────────────────────────────────────────────────────────────────

class TestTimebase:
    def test_add_multiple_frames(self):
        ed = _make_editor(n_tracks=1, n_frames=5)
        assert ed.get_frame_count() == 5
        assert ed.durations_ms == [100] * 5

    def test_custom_duration(self):
        ed = _make_editor(n_tracks=1, n_frames=3, duration_ms=42)
        assert all(d == 42 for d in ed.durations_ms)

    def test_move_timebase_frame_shifts_position(self):
        ed = _make_editor(n_tracks=1, n_frames=3)
        ed.layer_tracks[0].frames[0] = LayerFrame(material_index=99)
        ed.move_timebase_frame(0, 2)
        # The frame that was at index 0 should now be at index 2
        assert ed.layer_tracks[0].frames[2].material_index == 99

    def test_duplicate_timebase_frame_grows_count(self):
        ed = _make_editor(n_tracks=1, n_frames=2)
        ed.duplicate_timebase_frame(0)
        assert ed.get_frame_count() == 3

    def test_remove_timebase_frames_reduces_count(self):
        ed = _make_editor(n_tracks=1, n_frames=5)
        ed.remove_timebase_frames([1, 3])
        assert ed.get_frame_count() == 3

    def test_remove_all_frames_leaves_empty(self):
        ed = _make_editor(n_tracks=1, n_frames=3)
        ed.remove_timebase_frames([0, 1, 2])
        assert ed.get_frame_count() == 0

    def test_frame_count_zero_on_empty_editor(self):
        ed = LayerTimelineEditor()
        ed.add_layer_track("A")
        assert ed.get_frame_count() == 0

    def test_add_timebase_frames_to_multiple_tracks(self):
        ed = LayerTimelineEditor()
        t1 = ed.add_layer_track("A")
        t2 = ed.add_layer_track("B")
        ed.add_timebase_frames(4, duration_ms=80)
        assert len(ed.layer_tracks[t1].frames) == 4
        assert len(ed.layer_tracks[t2].frames) == 4


# ──────────────────────────────────────────────────────────────────────────────
# iter_frame_layers
# ──────────────────────────────────────────────────────────────────────────────

class TestIterFrameLayers:
    def test_basic_two_layers_bottom_to_top(self):
        ed = LayerTimelineEditor()
        t1 = ed.add_layer_track("Bottom")
        t2 = ed.add_layer_track("Top")
        ed.add_timebase_frames(1, duration_ms=100)
        ed.layer_tracks[t1].frames[0] = LayerFrame(material_index=0, x=1, y=2)
        ed.layer_tracks[t2].frames[0] = LayerFrame(material_index=1, x=3, y=4)
        layers = ed.iter_frame_layers(0)
        assert layers == [(0, None, 1, 2), (1, None, 3, 4)]

    def test_track_level_offset_applied(self):
        ed = LayerTimelineEditor()
        t = ed.add_layer_track("A")
        ed.add_timebase_frames(1, duration_ms=100)
        ed.layer_tracks[t].offset_x = 10
        ed.layer_tracks[t].offset_y = 20
        ed.layer_tracks[t].frames[0] = LayerFrame(material_index=5, x=1, y=2)
        layers = ed.iter_frame_layers(0)
        assert layers[0] == (5, None, 11, 22)

    def test_blank_frames_excluded(self):
        """Frames with material_index=None and group_index=None are skipped."""
        ed = LayerTimelineEditor()
        ed.add_layer_track("A")
        ed.add_timebase_frames(1, duration_ms=100)
        # Leave frame blank (defaults to None, None)
        layers = ed.iter_frame_layers(0)
        assert layers == []

    def test_frame_index_out_of_range_returns_empty(self):
        ed = _make_editor(n_tracks=1, n_frames=2)
        # Frame index 99 is out of range; should not crash
        layers = ed.iter_frame_layers(99)
        assert layers == []

    def test_no_tracks_returns_empty(self):
        ed = LayerTimelineEditor()
        assert ed.iter_frame_layers(0) == []

    def test_group_index_is_propagated(self):
        ed = LayerTimelineEditor()
        t = ed.add_layer_track("G")
        ed.add_timebase_frames(1, duration_ms=100)
        ed.layer_tracks[t].frames[0] = LayerFrame(group_index=7, x=0, y=0)
        layers = ed.iter_frame_layers(0)
        assert len(layers) == 1
        _, grp, _, _ = layers[0]
        assert grp == 7


# ──────────────────────────────────────────────────────────────────────────────
# LayerTrack frame-level operations
# ──────────────────────────────────────────────────────────────────────────────

class TestLayerTrackFrameOps:
    def test_insert_frame_at_position(self):
        track = LayerTrack(name="T")
        track.add_frame(LayerFrame(material_index=0))
        track.add_frame(LayerFrame(material_index=2))
        track.insert_frame(1, LayerFrame(material_index=1))
        assert [f.material_index for f in track.frames] == [0, 1, 2]

    def test_remove_frame_by_position(self):
        track = LayerTrack(name="T")
        for i in range(3):
            track.add_frame(LayerFrame(material_index=i))
        track.remove_frame(1)
        assert [f.material_index for f in track.frames] == [0, 2]

    def test_move_frame_within_track(self):
        track = LayerTrack(name="T")
        for i in range(3):
            track.add_frame(LayerFrame(material_index=i))
        track.move_frame(0, 2)
        assert [f.material_index for f in track.frames] == [1, 2, 0]

    def test_remove_out_of_bounds_is_noop(self):
        track = LayerTrack(name="T")
        track.add_frame(LayerFrame(material_index=0))
        track.remove_frame(99)
        assert len(track.frames) == 1
