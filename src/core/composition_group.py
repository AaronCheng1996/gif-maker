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


# ─── Serialization helpers ────────────────────────────────────────────────────

def slot_to_dict(slot: "Slot") -> dict:
    if isinstance(slot, FrameSlot):
        return {"type": "frameslot", "material_index": slot.material_index,
                "x": slot.x, "y": slot.y}
    if isinstance(slot, GroupSlot):
        return {"type": "groupslot", "group_id": slot.group_id,
                "loop_count": slot.loop_count, "x": slot.x, "y": slot.y}
    raise ValueError(f"Unknown slot type: {type(slot)}")


def slot_from_dict(d: dict) -> "Slot":
    t = d.get("type")
    if t == "frameslot":
        return FrameSlot(material_index=d["material_index"],
                         x=d.get("x", 0), y=d.get("y", 0))
    if t == "groupslot":
        return GroupSlot(group_id=d["group_id"], loop_count=d.get("loop_count", 1),
                         x=d.get("x", 0), y=d.get("y", 0))
    raise ValueError(f"Unknown slot type: {t!r}")


def entry_to_dict(entry: "Entry") -> dict:
    if isinstance(entry, FrameEntry):
        return {"type": "frame", "material_index": entry.material_index,
                "x": entry.x, "y": entry.y, "duration_ms": entry.duration_ms}
    if isinstance(entry, SubGroupEntry):
        return {"type": "subgroup", "group_id": entry.group_id,
                "loop_count": entry.loop_count, "x": entry.x, "y": entry.y,
                "duration_override_ms": entry.duration_override_ms}
    if isinstance(entry, LayerBlockEntry):
        return {"type": "layerblock", "default_duration_ms": entry.default_duration_ms,
                "timelines": [[slot_to_dict(s) for s in tl] for tl in entry.timelines]}
    raise ValueError(f"Unknown entry type: {type(entry)}")


def entry_from_dict(d: dict) -> "Entry":
    t = d.get("type")
    if t == "frame":
        return FrameEntry(material_index=d["material_index"],
                          x=d.get("x", 0), y=d.get("y", 0),
                          duration_ms=d.get("duration_ms"))
    if t == "subgroup":
        return SubGroupEntry(group_id=d["group_id"], loop_count=d.get("loop_count", 1),
                             x=d.get("x", 0), y=d.get("y", 0),
                             duration_override_ms=d.get("duration_override_ms"))
    if t == "layerblock":
        return LayerBlockEntry(
            timelines=[[slot_from_dict(s) for s in tl] for tl in d.get("timelines", [])],
            default_duration_ms=d.get("default_duration_ms", 100),
        )
    raise ValueError(f"Unknown entry type: {t!r}")


def group_to_dict(group_id: int, group: "CompositionGroup") -> dict:
    return {
        "id": group_id,
        "name": group.name,
        "default_duration_ms": group.default_duration_ms,
        "entries": [entry_to_dict(e) for e in group.entries],
    }


def group_from_dict(d: dict) -> "CompositionGroup":
    return CompositionGroup(
        name=d.get("name", "Group"),
        default_duration_ms=d.get("default_duration_ms", 100),
        entries=[entry_from_dict(e) for e in d.get("entries", [])],
    )


def max_material_index(gm: "GroupManager") -> int:  # type: ignore[name-defined]
    """Return the highest material_index used anywhere in the group manager (-1 if none)."""
    hi = -1
    for group in gm.groups:
        for entry in group.entries:
            if isinstance(entry, FrameEntry):
                hi = max(hi, entry.material_index)
            elif isinstance(entry, LayerBlockEntry):
                for tl in entry.timelines:
                    for slot in tl:
                        if isinstance(slot, FrameSlot):
                            hi = max(hi, slot.material_index)
    return hi


def remap_material_indices(gm: "GroupManager", mapping: dict) -> None:  # type: ignore[name-defined]
    """Remap material indices in-place using {old_idx: new_idx} mapping."""
    for group in gm.groups:
        for entry in group.entries:
            if isinstance(entry, FrameEntry):
                entry.material_index = mapping.get(entry.material_index, entry.material_index)
            elif isinstance(entry, LayerBlockEntry):
                for tl in entry.timelines:
                    for slot in tl:
                        if isinstance(slot, FrameSlot):
                            slot.material_index = mapping.get(slot.material_index, slot.material_index)
