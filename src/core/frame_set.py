"""
Frame folders - group loose image files into one material set per output.

The Batch Processor's other source is a sprite sheet, which carries its own
structure: split it and the tiles arrive in a known order. A folder of exported
frames carries that structure in the file names instead, and every project spells
it differently — so the rule is a regex the user supplies rather than a
convention baked in here.

No PyQt6: src/cli.py drives this headlessly, and the tests run without a display.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Pattern

from .composition_group import natural_key

# What the file dialogs offer; a frame folder holds stills, one image per frame.
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

UNIT_GROUP = "unit"


class FrameSetError(ValueError):
    """The naming rule cannot be used as given."""


@dataclass
class FrameSet:
    """The files that make up one output, in the order they will play."""
    unit: str
    paths: List[Path] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.paths)


@dataclass
class FrameScan:
    """What a folder held: the units found, and the files no rule claimed."""
    units: List[FrameSet] = field(default_factory=list)
    skipped: List[Path] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.units)

    def summary(self) -> str:
        if not self.units:
            return f"No files matched ({len(self.skipped)} skipped)"
        frames = sum(len(u) for u in self.units)
        text = f"{len(self.units)} unit(s), {frames} frame(s)"
        if self.skipped:
            text += f", {len(self.skipped)} skipped"
        return text


def compile_unit_pattern(pattern: Optional[str]) -> Optional[Pattern]:
    """Compile a naming rule, or None to treat the whole folder as one unit.

    Raises FrameSetError rather than re.error so callers have one exception to
    show the user — a bad regex is a typo in a text field, not a crash."""
    if not pattern or not pattern.strip():
        return None
    try:
        return re.compile(pattern)
    except re.error as e:
        raise FrameSetError(f"Invalid naming rule: {e}") from e


def unit_of(stem: str, rule: Optional[Pattern]) -> Optional[str]:
    """Which output `stem` belongs to, or None when the rule does not claim it.

    The rule is anchored at the start of the name and read for a group named
    'unit'; failing that its first capture, failing that the whole match. Being
    anchored is what lets a greedy optional part separate neighbours that share
    a prefix — `(?P<unit>dh\\d+(?:_sleep)?)_` keeps dh03_sleep_org01 out of
    dh03, which an unanchored search would have swallowed."""
    if rule is None:
        return ""
    m = rule.match(stem)
    if m is None:
        return None
    if UNIT_GROUP in (m.groupdict() or {}):
        return m.group(UNIT_GROUP)
    if m.groups():
        return m.group(1)
    return m.group(0)


def scan_frame_folder(
    folder: str,
    pattern: Optional[str] = None,
    recursive: bool = False,
    extensions: Optional[tuple] = None,
) -> FrameScan:
    """Group the images in `folder` into one FrameSet per unit.

    Units come out in natural order and so do the frames inside them, so org2
    plays before org10 however the filesystem chose to list them.
    """
    root = Path(folder)
    if not root.is_dir():
        raise FrameSetError(f"Not a folder: {folder}")

    rule = compile_unit_pattern(pattern)
    exts = tuple(e.lower() for e in (extensions or IMAGE_EXTENSIONS))

    files = sorted(
        (p for p in (root.rglob("*") if recursive else root.glob("*"))
         if p.is_file() and p.suffix.lower() in exts),
        key=lambda p: natural_key(p.name),
    )

    buckets: dict = {}
    skipped: List[Path] = []
    for path in files:
        unit = unit_of(path.stem, rule)
        if unit is None:
            skipped.append(path)
            continue
        buckets.setdefault(unit, []).append(path)

    if rule is None and buckets:
        # No rule: the folder itself is the one output, and it is named after it.
        buckets = {root.name or "frames": buckets[""]}

    units = [FrameSet(unit=name, paths=paths)
             for name, paths in sorted(buckets.items(), key=lambda kv: natural_key(kv[0]))]
    return FrameScan(units=units, skipped=skipped)
