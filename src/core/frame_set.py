"""
Frame folders - group loose image files into one material set per output.

The Batch Processor's other source is a sprite sheet, which carries its own
structure: split it and the tiles arrive in a known order. A folder of exported
frames carries that structure in the file names instead, and every project spells
it differently — so the rule is a regex the user supplies rather than a
convention baked in here.

No PyQt6: src/cli.py drives this headlessly, and the tests run without a display.
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Pattern, Tuple

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


# ─── Suggesting a rule ───────────────────────────────────────────────────────
#
# The rule is the one setting with no safe default, and a regex is a hard thing
# to ask of someone who only wants their frames turned into GIFs. So rather than
# guess one, read the names that are actually there, derive the handful of rules
# that fit them, and run each one to show what it produces. The numbers a
# suggestion carries are measured, never estimated: by the time a rule is
# offered it has already been executed against the folder.

# A name splits into runs of letters, runs of digits, and runs of anything else.
# dhD19_ho_… -> ['dhD', '19', '_', 'ho', …], which is what lets the letter and
# the number of a scene id be generalised separately.
_TOKEN_RE = re.compile(r"[A-Za-z]+|\d+|[^A-Za-z\d]+")

_TRAILING_INDEX_RE = re.compile(r"([^A-Za-z\d]*)(\d+)$")

# How many leading tokens to try grouping on. Past this the units are one file
# each on any real naming scheme, and the list stops being a list of choices.
MAX_PREFIX_TOKENS = 8

# Below this share of numbered names, a trailing number is a coincidence in a
# couple of file names rather than a frame index.
_INDEXED_SHARE = 0.6


@dataclass
class Phrase:
    """A sentence to show a user: an English template plus its values.

    core/ must not import the UI and the UI must not re-derive the numbers, so
    the two travel separately and whoever displays it runs the template through
    tr() before formatting it."""
    template: str
    args: dict = field(default_factory=dict)

    def __str__(self) -> str:
        return self.template.format(**self.args)


@dataclass
class UnitSuggestion:
    """One candidate rule, and what it did to this folder when it was run."""
    pattern: Optional[str]
    label: Phrase
    units: int
    frames: int
    skipped: int
    min_frames: int
    max_frames: int
    example: str = ""                       # "dhD19_ho_…_1  ->  dhD19"
    warnings: List[Phrase] = field(default_factory=list)

    def describe(self) -> str:
        text = f"{self.units} GIF(s), {self.min_frames}-{self.max_frames} frame(s) each"
        if self.skipped:
            text += f", {self.skipped} file(s) skipped"
        return f"{self.label} - {text}"


def _tokenize(stem: str) -> List[str]:
    return _TOKEN_RE.findall(stem)


def _generalize(values: List[str]) -> str:
    """One regex covering every value seen at one token position.

    Written to stay readable, because the point of offering a rule is that the
    user can look at it and edit it: {dhD, dhL, dhS} becomes dh[DLS], not an
    alternation of three escaped literals."""
    seen = sorted(set(values))
    if len(seen) == 1:
        return re.escape(seen[0])
    if all(v.isdigit() for v in seen):
        return r"\d+"

    prefix = os.path.commonprefix(seen)
    rest = sorted({v[len(prefix):] for v in seen})
    head = re.escape(prefix)
    if all(len(r) == 1 for r in rest):
        return head + "[" + "".join(re.escape(c) for c in rest) + "]"
    if len(rest) <= 6:
        # Longest first: 'org' must not shadow 'org1' the way an alternation
        # tried in sorted order would.
        alts = sorted(rest, key=lambda s: (-len(s), s))
        return head + "(?:" + "|".join(re.escape(a) for a in alts) + ")"
    return head + r"[^_]+"


def _index_separator(stems: List[str]) -> Optional[str]:
    """What sits between a name and its frame number, as a regex, or None.

    A pattern rather than a character, so one rule covers the folder that spells
    the same separator two ways - 'org1_12' and 'org1_ 12' are frames of the
    same animation, and a rule reading only the first drops the second in
    silence."""
    hits = [_TRAILING_INDEX_RE.search(s) for s in stems]
    found = [m for m in hits if m]
    if len(found) < len(stems) * _INDEXED_SHARE:
        return None

    chars = sorted({c for m in found for c in m.group(1).strip()})
    if not chars:
        return r"\s*"
    if len(chars) == 1:
        return re.escape(chars[0]) + r"\s*"
    return "[" + "".join(re.escape(c) for c in chars) + r"]\s*"


def _candidate_rules(stems: List[str]) -> List[Tuple[Phrase, Optional[str]]]:
    """The rules worth trying on these names."""
    out: List[Tuple[Phrase, Optional[str]]] = [
        (Phrase("The whole folder as one GIF"), None)
    ]

    sep = _index_separator(stems)
    if sep is not None:
        out.append((Phrase("One GIF per numbered sequence"),
                    r"(?P<unit>.+?)" + sep + r"\d+$"))

    tokens = [_tokenize(s) for s in stems]
    depth = min(len(t) for t in tokens)
    for k in range(1, min(depth, MAX_PREFIX_TOKENS)):
        columns = [[t[i] for t in tokens] for i in range(k)]
        # A cut ending on a separator names its units 'dhD19_'; the same
        # grouping without the trailing underscore is already on the list.
        if not any(c.isalnum() for c in columns[-1][0]):
            continue
        body = "".join(_generalize(col) for col in columns)
        # Anchor on what follows when the folder always spells it the same way,
        # so 'dhD19x_…' is reported as unmatched instead of joining dhD19.
        after = {t[k] for t in tokens}
        boundary = re.escape(after.pop()) if len(after) == 1 else ""
        out.append((Phrase("Group by the first {n} part(s) of the name", {"n": k}),
                    "(?P<unit>" + body + ")" + boundary))
    return out


def rule_warnings(scan: FrameScan) -> List[Phrase]:
    """What looks wrong about a grouping, phrased as what to go and check.

    Public because a hand-typed rule needs the same second pair of eyes a
    suggested one gets - more so, since nothing else has looked at it."""
    warnings: List[Phrase] = []

    if scan.skipped:
        warnings.append(Phrase(
            "{n} file(s) match nothing and will not be exported, e.g. {sample}",
            {"n": len(scan.skipped),
             "sample": ", ".join(p.name for p in scan.skipped[:3])}))

    singles = [u.unit for u in scan.units if len(u) == 1]
    if singles:
        warnings.append(Phrase(
            "{n} unit(s) hold a single frame, e.g. {sample}",
            {"n": len(singles), "sample": ", ".join(singles[:3])}))

    # A still mixed in with an animation: the unit is mostly numbered frames and
    # a few of its names carry no number at all. Backgrounds exported beside the
    # frames land this way, and they play as a flash of empty scene.
    odd: List[str] = []
    for unit in scan.units:
        numbered = sum(1 for p in unit.paths if _TRAILING_INDEX_RE.search(p.stem))
        if numbered >= len(unit) * _INDEXED_SHARE:
            odd.extend(p.name for p in unit.paths
                       if not _TRAILING_INDEX_RE.search(p.stem))
    if odd:
        warnings.append(Phrase(
            "{n} file(s) have no frame number and may be stills, e.g. {sample}",
            {"n": len(odd), "sample": ", ".join(odd[:3])}))
    return warnings


def suggest_unit_patterns(
    folder: str,
    recursive: bool = False,
    extensions: Optional[tuple] = None,
) -> List[UnitSuggestion]:
    """Rules that fit this folder's names, each with what it actually produces.

    Ordered coarsest cut first, so the list reads as one question - how finely
    should this folder be divided - rather than as a set of regexes. Candidates
    that group the files identically are one choice and only the first survives;
    ones that make a GIF of every single file are dropped.
    """
    root = Path(folder)
    if not root.is_dir():
        raise FrameSetError(f"Not a folder: {folder}")

    exts = tuple(e.lower() for e in (extensions or IMAGE_EXTENSIONS))
    stems = sorted(
        (p.stem for p in (root.rglob("*") if recursive else root.glob("*"))
         if p.is_file() and p.suffix.lower() in exts),
        key=natural_key,
    )
    if not stems:
        return []

    out: List[UnitSuggestion] = []
    seen: set = set()
    for label, pattern in _candidate_rules(stems):
        try:
            scan = scan_frame_folder(str(root), pattern, recursive=recursive,
                                     extensions=exts)
        except FrameSetError:
            continue
        if not scan.units or len(scan.units) == len(stems):
            continue

        # Two rules that cut the folder the same way are one choice, not two.
        shape = frozenset(frozenset(str(p) for p in u.paths) for u in scan.units)
        if shape in seen:
            continue
        seen.add(shape)

        counts = [len(u) for u in scan.units]
        first = scan.units[0]
        out.append(UnitSuggestion(
            pattern=pattern,
            label=label,
            units=len(scan.units),
            frames=sum(counts),
            skipped=len(scan.skipped),
            min_frames=min(counts),
            max_frames=max(counts),
            example=f"{first.paths[0].stem}  →  {first.unit}",
            warnings=rule_warnings(scan),
        ))

    out.sort(key=lambda s: s.units)
    return out
