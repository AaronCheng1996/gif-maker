"""
Composition Group - Group-led nested composition model

A CompositionGroup is the root of GIF composition. It contains a sequence of
entries: FrameEntry (single frame), SubGroupEntry (nested group with loop),
or LayerBlockEntry (multiple timelines composited frame-by-frame).
Groups can be nested; preview and export target the currently selected group.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


# ----- Slots (used inside a timeline of a LayerBlock) -----

@dataclass
class FrameSlot:
    """Single frame in a timeline slot: material + position."""
    material_index: int
    x: int = 0
    y: int = 0


@dataclass
class GroupSlot:
    """Reference to a group in a timeline slot; loop_count applies when expanding."""
    group_id: int
    loop_count: int = 1
    x: int = 0
    y: int = 0


Slot = Union[FrameSlot, GroupSlot]


def is_frame_slot(s: Slot) -> bool:
    return isinstance(s, FrameSlot)


def is_group_slot(s: Slot) -> bool:
    return isinstance(s, GroupSlot)


# ----- Timeline (list of slots; all timelines in a LayerBlock must have same length) -----

Timeline = List[Slot]


# ----- Entries (items in a CompositionGroup's sequence) -----

@dataclass
class FrameEntry:
    """Single frame entry: one material at (x, y) with optional duration."""
    material_index: int
    x: int = 0
    y: int = 0
    duration_ms: Optional[int] = None  # None = use group default_duration


@dataclass
class SubGroupEntry:
    """Reference to another group; expand that group, then repeat loop_count times.
    x, y shift every material in the expanded frames by this offset.
    duration_override_ms: when set, overrides every frame's duration for this reference only."""
    group_id: int
    loop_count: int = 1
    x: int = 0
    y: int = 0
    duration_override_ms: Optional[int] = None


@dataclass
class LayerBlockEntry:
    """Multiple timelines composited frame-by-frame (same length). At index i, composite all timeline[i]."""
    timelines: List[Timeline] = field(default_factory=list)
    default_duration_ms: int = 100


Entry = Union[FrameEntry, SubGroupEntry, LayerBlockEntry]


def is_frame_entry(e: Entry) -> bool:
    return isinstance(e, FrameEntry)


def is_sub_group_entry(e: Entry) -> bool:
    return isinstance(e, SubGroupEntry)


def is_layer_block_entry(e: Entry) -> bool:
    return isinstance(e, LayerBlockEntry)


# ----- CompositionGroup -----

@dataclass
class CompositionGroup:
    """
    Group-led composition: ordered list of entries.
    Each entry is FrameEntry, SubGroupEntry, or LayerBlockEntry.
    Leaf group: only FrameEntry. Container: can have SubGroupEntry and LayerBlockEntry.
    """
    name: str = ""
    entries: List[Entry] = field(default_factory=list)
    default_duration_ms: int = 100

    def __post_init__(self):
        if not self.name:
            self.name = "Group"
