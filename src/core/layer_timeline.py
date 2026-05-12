"""
Layer Timeline data model and editor

This module manages a layer-based composition system for GIF animation:
- One main timebase defines global frame count and durations
- Multiple layer tracks (LayerTrack) each contain per-frame material placements
- Final frames are composited by stacking layers from bottom to top

This was previously called "Multi-Timeline" but has been renamed to better
reflect its purpose as a layer composition system, not multiple independent timelines.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class LayerFrame:
    """A single frame entry pointing to a material (or group) and its offset within the canvas."""
    material_index: Optional[int] = None
    group_index: Optional[int] = None  # Reference to a CompositionGroup (by group_id)
    x: int = 0
    y: int = 0


@dataclass
class LayerTrack:
    """A named layer track with its own sequence of frames (materials/groups + offsets)."""
    name: str
    frames: List[LayerFrame] = field(default_factory=list)
    offset_x: int = 0
    offset_y: int = 0

    def add_frame(self, frame: LayerFrame):
        self.frames.append(frame)

    def insert_frame(self, position: int, frame: LayerFrame):
        position = max(0, min(position, len(self.frames)))
        self.frames.insert(position, frame)

    def remove_frame(self, position: int):
        if 0 <= position < len(self.frames):
            del self.frames[position]

    def move_frame(self, from_pos: int, to_pos: int):
        if 0 <= from_pos < len(self.frames) and 0 <= to_pos < len(self.frames):
            frame = self.frames.pop(from_pos)
            self.frames.insert(to_pos, frame)


class LayerTimelineEditor:
    """Holds multiple layer tracks; one track serves as the main timebase."""

    def __init__(self):
        self.layer_tracks: List[LayerTrack] = []
        self.main_track_index: int = 0
        self.default_duration: int = 100
        self.durations_ms: List[int] = []  # durations for frames, from main timebase

    # ----- Layer tracks management -----
    def add_layer_track(self, name: str) -> int:
        self.layer_tracks.append(LayerTrack(name=name))
        return len(self.layer_tracks) - 1

    def remove_layer_track(self, index: int):
        if 0 <= index < len(self.layer_tracks):
            # Prevent removing the last track
            if len(self.layer_tracks) == 1:
                return
            del self.layer_tracks[index]
            # Adjust main track index if needed
            if self.main_track_index >= len(self.layer_tracks):
                self.main_track_index = max(0, len(self.layer_tracks) - 1)

    def move_layer_track(self, from_index: int, to_index: int):
        if 0 <= from_index < len(self.layer_tracks) and 0 <= to_index < len(self.layer_tracks):
            t = self.layer_tracks.pop(from_index)
            self.layer_tracks.insert(to_index, t)
            # Keep main track index pointing to the same object if possible
            if from_index == self.main_track_index:
                self.main_track_index = to_index
            else:
                # If we moved another track past the main index, adjust
                if from_index < self.main_track_index <= to_index:
                    self.main_track_index -= 1
                elif to_index <= self.main_track_index < from_index:
                    self.main_track_index += 1

    def set_main_track(self, index: int):
        if 0 <= index < len(self.layer_tracks):
            self.main_track_index = index

    def get_main_track(self) -> Optional[LayerTrack]:
        if not self.layer_tracks:
            return None
        return self.layer_tracks[self.main_track_index]

    # ----- Frames (timebase) -----
    def get_frame_count(self) -> int:
        return len(self.durations_ms)

    def add_timebase_frames(self, count: int, duration_ms: Optional[int] = None):
        if count <= 0:
            return
        duration = self.default_duration if duration_ms is None else duration_ms
        self.durations_ms.extend([duration] * count)
        # Append placeholder frames for all tracks
        for t in self.layer_tracks:
            for _ in range(count):
                t.frames.append(LayerFrame())

    def insert_timebase_frames(self, position: int, count: int, duration_ms: Optional[int] = None):
        duration = self.default_duration if duration_ms is None else duration_ms
        position = max(0, min(position, len(self.durations_ms)))
        for _ in range(count):
            self.durations_ms.insert(position, duration)
        # Insert placeholder frames in every track
        for t in self.layer_tracks:
            for _ in range(count):
                t.frames.insert(position, LayerFrame())

    def remove_timebase_frames(self, positions: List[int]):
        # Remove in reverse order to keep indices stable
        for pos in sorted(positions, reverse=True):
            if 0 <= pos < len(self.durations_ms):
                del self.durations_ms[pos]
                for t in self.layer_tracks:
                    if 0 <= pos < len(t.frames):
                        del t.frames[pos]

    def set_timebase_duration(self, position: int, duration_ms: int):
        if 0 <= position < len(self.durations_ms):
            self.durations_ms[position] = duration_ms

    def set_timebase_all_durations(self, duration_ms: int):
        self.durations_ms = [duration_ms for _ in self.durations_ms]

    def move_timebase_frame(self, from_pos: int, to_pos: int):
        if 0 <= from_pos < len(self.durations_ms) and 0 <= to_pos < len(self.durations_ms):
            dur = self.durations_ms.pop(from_pos)
            self.durations_ms.insert(to_pos, dur)
            for t in self.layer_tracks:
                f = t.frames.pop(from_pos)
                t.frames.insert(to_pos, f)

    def duplicate_timebase_frame(self, position: int):
        if 0 <= position < len(self.durations_ms):
            dur = self.durations_ms[position]
            self.durations_ms.insert(position + 1, dur)
            for t in self.layer_tracks:
                if 0 <= position < len(t.frames):
                    # shallow copy is fine as fields are immutable ints
                    orig = t.frames[position]
                    t.frames.insert(position + 1, LayerFrame(
                        material_index=orig.material_index,
                        group_index=orig.group_index,
                        x=orig.x,
                        y=orig.y,
                    ))

    # ----- Per-track frames -----
    def get_layer_track(self, index: int) -> Optional[LayerTrack]:
        if 0 <= index < len(self.layer_tracks):
            return self.layer_tracks[index]
        return None

    def ensure_track_length(self, track_index: int, length: int):
        t = self.get_layer_track(track_index)
        if t is None:
            return
        while len(t.frames) < length:
            t.frames.append(LayerFrame())

    # ----- Rendering helpers -----
    def iter_frame_layers(self, frame_index: int) -> List[Tuple[Optional[int], Optional[int], int, int]]:
        """
        Returns bottom-to-top list of (material_index, group_index, x, y) for a given frame index.
        Skips missing materials/groups or tracks without that frame index.
        """
        result: List[Tuple[Optional[int], Optional[int], int, int]] = []
        for track in self.layer_tracks:
            if frame_index < len(track.frames):
                f = track.frames[frame_index]
                if f.material_index is not None or f.group_index is not None:
                    # Add per-track global offset to per-frame offset
                    result.append((
                        f.material_index,
                        f.group_index,
                        f.x + (track.offset_x or 0),
                        f.y + (track.offset_y or 0),
                    ))
        return result


