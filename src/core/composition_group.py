"""
Composition Group - Group-led nested composition model

A CompositionGroup is the root of GIF composition. It contains a sequence of
entries: FrameEntry (single frame), SubGroupEntry (nested group with loop),
or LayerBlockEntry (multiple timelines composited frame-by-frame).
Groups can be nested; preview and export target the currently selected group.
"""

import fnmatch
import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


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

    tail_duration_ms pins the pause before the group loops to *whichever* frame
    ends the group rather than to one particular frame. It is resolved at
    expansion time, so appending a frame moves the pause onto the new last frame
    and hands the old one its own duration back — where writing the pause into
    the entry would have stranded it mid-timeline. None times every frame by
    itself. Ignored while the group ends on a sub-group or a layer block, which
    carry their own timing.

    source_pattern binds the group to the materials whose names match a glob
    instead of to a fixed list of entries: it resolves at expansion time, so the
    group holds as many frames as the current material set actually has. While
    it is set, entries are not exported (they are kept, so unbinding restores
    them). See resolve_source_indices for why binding by name matters.

    collapse_repeats merges runs of consecutive frames that draw the same thing
    into one frame held for the sum of their durations. Sprite exporters spell a
    held pose out as repeated images — ten copies of one frame, or two files
    that happen to be identical — and the run and the single long frame play the
    same, so the timeline reads as the poses it has rather than as the padding.
    Matching is on pixels, not on which material an entry points at, because the
    repeats are usually separate files.
    """
    name: str = ""
    entries: List[Entry] = field(default_factory=list)
    default_duration_ms: int = 100
    tail_duration_ms: Optional[int] = None
    source_pattern: Optional[str] = None
    collapse_repeats: bool = False

    def __post_init__(self):
        if not self.name:
            self.name = "Group"


# ----- Repeat runs -----

def image_digest(image) -> str:
    """Content fingerprint of a material, for spotting repeated frames.

    Exporters write a held pose as separate files, so repeats are different
    materials carrying the same pixels — comparing indices would miss every
    one of them."""
    return hashlib.md5(image.tobytes()).hexdigest()


def collapse_repeat_runs(keys: List) -> List[Tuple[int, int]]:
    """Runs of equal neighbouring keys, as (index of the first, run length)."""
    runs: List[Tuple[int, int]] = []
    for i, key in enumerate(keys):
        if runs and key == keys[runs[-1][0]]:
            start, length = runs[-1]
            runs[-1] = (start, length + 1)
        else:
            runs.append((i, 1))
    return runs


# ----- Material selectors -----

def natural_key(name: str) -> tuple:
    """Sort key that reads runs of digits as numbers, so org2 sorts before org10.

    These names carry frame numbers, and plain lexicographic order drops org10
    into the middle of the sequence."""
    return tuple(
        (1, int(part), "") if part.isdigit() else (0, 0, part.lower())
        for part in re.split(r"(\d+)", name) if part != ""
    )


def resolve_source_indices(pattern: str, names: List[str]) -> List[int]:
    """Indices of the materials whose name matches `pattern`, in natural order.

    `pattern` is a case-insensitive glob matched against the material name —
    the file stem, for frames loaded from disk. Selecting by name instead of by
    position is the whole point: a group bound to ``*_org*`` holds however many
    org frames the current sprite has, so one template survives a clip that is
    27 frames on one character and 36 on the next. A list of indices could not:
    every group after the one that changed length pointed at the wrong material.
    """
    if not pattern:
        return []
    lowered = pattern.lower()
    hits = [i for i, n in enumerate(names) if fnmatch.fnmatch(n.lower(), lowered)]
    hits.sort(key=lambda i: (natural_key(names[i]), i))
    return hits


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
        "tail_duration_ms": group.tail_duration_ms,
        "source_pattern": group.source_pattern,
        "collapse_repeats": group.collapse_repeats,
        "entries": [entry_to_dict(e) for e in group.entries],
    }


def group_from_dict(d: dict) -> "CompositionGroup":
    return CompositionGroup(
        name=d.get("name", "Group"),
        default_duration_ms=d.get("default_duration_ms", 100),
        tail_duration_ms=d.get("tail_duration_ms"),
        source_pattern=d.get("source_pattern"),
        collapse_repeats=bool(d.get("collapse_repeats", False)),
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
