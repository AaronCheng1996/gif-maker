"""
Multi-Timeline data model and editor

This replaces the old per-frame layer editing with a simpler concept:
- One main timeline defines global frame count and durations
- Additional timelines define per-frame material and offset
- Final frames are composited by stacking timelines from bottom to top
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class TimelineFrame:
    """A single frame entry pointing to a material and its offset within the canvas."""
    material_index: Optional[int] = None
    x: int = 0
    y: int = 0


@dataclass
class Timeline:
    """A named timeline with its own sequence of frames (materials + offsets)."""
    name: str
    frames: List[TimelineFrame] = field(default_factory=list)

    def add_frame(self, frame: TimelineFrame):
        self.frames.append(frame)

    def insert_frame(self, position: int, frame: TimelineFrame):
        position = max(0, min(position, len(self.frames)))
        self.frames.insert(position, frame)

    def remove_frame(self, position: int):
        if 0 <= position < len(self.frames):
            del self.frames[position]

    def move_frame(self, from_pos: int, to_pos: int):
        if 0 <= from_pos < len(self.frames) and 0 <= to_pos < len(self.frames):
            frame = self.frames.pop(from_pos)
            self.frames.insert(to_pos, frame)


class MultiTimelineEditor:
    """Holds multiple timelines; one timeline is the main timebase."""

    def __init__(self):
        self.timelines: List[Timeline] = []
        self.main_timeline_index: int = 0
        self.default_duration: int = 100
        self.durations_ms: List[int] = []  # durations for frames, from main timeline

    # ----- Timelines management -----
    def add_timeline(self, name: str) -> int:
        self.timelines.append(Timeline(name=name))
        return len(self.timelines) - 1

    def remove_timeline(self, index: int):
        if 0 <= index < len(self.timelines):
            # Prevent removing the last timeline
            if len(self.timelines) == 1:
                return
            del self.timelines[index]
            # Adjust main timeline index if needed
            if self.main_timeline_index >= len(self.timelines):
                self.main_timeline_index = max(0, len(self.timelines) - 1)

    def move_timeline(self, from_index: int, to_index: int):
        if 0 <= from_index < len(self.timelines) and 0 <= to_index < len(self.timelines):
            t = self.timelines.pop(from_index)
            self.timelines.insert(to_index, t)
            # Keep main timeline index pointing to the same object if possible
            if from_index == self.main_timeline_index:
                self.main_timeline_index = to_index
            else:
                # If we moved another timeline past the main index, adjust
                if from_index < self.main_timeline_index <= to_index:
                    self.main_timeline_index -= 1
                elif to_index <= self.main_timeline_index < from_index:
                    self.main_timeline_index += 1

    def set_main_timeline(self, index: int):
        if 0 <= index < len(self.timelines):
            self.main_timeline_index = index

    def get_main_timeline(self) -> Optional[Timeline]:
        if not self.timelines:
            return None
        return self.timelines[self.main_timeline_index]

    # ----- Frames (timebase) -----
    def get_frame_count(self) -> int:
        return len(self.durations_ms)

    def add_timebase_frames(self, count: int, duration_ms: Optional[int] = None):
        if count <= 0:
            return
        duration = self.default_duration if duration_ms is None else duration_ms
        self.durations_ms.extend([duration] * count)
        # Append placeholder frames for all timelines
        for t in self.timelines:
            for _ in range(count):
                t.frames.append(TimelineFrame())

    def insert_timebase_frames(self, position: int, count: int, duration_ms: Optional[int] = None):
        duration = self.default_duration if duration_ms is None else duration_ms
        position = max(0, min(position, len(self.durations_ms)))
        for _ in range(count):
            self.durations_ms.insert(position, duration)
        # Insert placeholder frames in every timeline
        for t in self.timelines:
            for _ in range(count):
                t.frames.insert(position, TimelineFrame())

    def remove_timebase_frames(self, positions: List[int]):
        # Remove in reverse order to keep indices stable
        for pos in sorted(positions, reverse=True):
            if 0 <= pos < len(self.durations_ms):
                del self.durations_ms[pos]
                for t in self.timelines:
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
            for t in self.timelines:
                f = t.frames.pop(from_pos)
                t.frames.insert(to_pos, f)

    def duplicate_timebase_frame(self, position: int):
        if 0 <= position < len(self.durations_ms):
            dur = self.durations_ms[position]
            self.durations_ms.insert(position + 1, dur)
            for t in self.timelines:
                if 0 <= position < len(t.frames):
                    # shallow copy is fine as fields are immutable ints
                    orig = t.frames[position]
                    t.frames.insert(position + 1, TimelineFrame(
                        material_index=orig.material_index,
                        x=orig.x,
                        y=orig.y,
                    ))

    # ----- Per-timeline frames -----
    def get_timeline(self, index: int) -> Optional[Timeline]:
        if 0 <= index < len(self.timelines):
            return self.timelines[index]
        return None

    def ensure_timeline_length(self, timeline_index: int, length: int):
        t = self.get_timeline(timeline_index)
        if t is None:
            return
        while len(t.frames) < length:
            t.frames.append(TimelineFrame())

    # ----- Rendering helpers -----
    def iter_frame_layers(self, frame_index: int) -> List[Tuple[int, int, int]]:
        """
        Returns bottom-to-top list of (material_index, x, y) for a given frame index.
        Skips missing materials or timelines without that frame index.
        """
        result: List[Tuple[int, int, int]] = []
        for timeline in self.timelines:
            if frame_index < len(timeline.frames):
                f = timeline.frames[frame_index]
                if f.material_index is not None:
                    result.append((f.material_index, f.x, f.y))
        return result


