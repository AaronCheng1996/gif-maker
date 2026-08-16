"""Spine texture atlas parser (supports both the 4.1 and the legacy formats).

The 4.1 format writes one `key: value` block per region::

    skeleton.png
    size: 8192, 8192
    filter: Linear, Linear
    head
    bounds: 12, 34, 100, 200
    offsets: 0, 18, 183, 195
    rotate: 270

Older exports instead use `xy:` / `size:` / `orig:` / `offset:` / `rotate: true|false`.
Both are handled here so the loader does not care which exporter produced the file.
"""
from pathlib import Path
from typing import Dict, List, Optional


class AtlasRegion:
    """One packed image inside an atlas page."""

    __slots__ = ("name", "page", "x", "y", "width", "height", "degrees",
                 "offset_x", "offset_y", "original_width", "original_height")

    def __init__(self, name: str, page: "AtlasPage"):
        self.name = name
        self.page = page
        self.x = self.y = 0
        self.width = self.height = 0
        self.degrees = 0
        self.offset_x = self.offset_y = 0
        self.original_width = self.original_height = 0

    # `width`/`height` are the source image's dimensions *before* rotation, which
    # is what Spine's UV maths expects. A 90/270 region therefore occupies a
    # swapped footprint on the page — verified against real atlases, where the
    # unswapped reading pushes regions past the page edge.
    @property
    def packed_width(self) -> int:
        """Horizontal extent actually occupied on the atlas page."""
        return self.height if self.degrees in (90, 270) else self.width

    @property
    def packed_height(self) -> int:
        """Vertical extent actually occupied on the atlas page."""
        return self.width if self.degrees in (90, 270) else self.height

    def __repr__(self):
        return (f"AtlasRegion({self.name!r}, page={self.page.name!r}, "
                f"x={self.x}, y={self.y}, w={self.width}, h={self.height}, rot={self.degrees})")


class AtlasPage:
    """One texture file referenced by the atlas."""

    __slots__ = ("name", "width", "height", "pma")

    def __init__(self, name: str):
        self.name = name
        self.width = self.height = 0
        self.pma = False  # premultiplied alpha

    def __repr__(self):
        return f"AtlasPage({self.name!r}, {self.width}x{self.height}, pma={self.pma})"


class Atlas:
    def __init__(self, pages: List[AtlasPage], regions: Dict[str, AtlasRegion]):
        self.pages = pages
        self.regions = regions

    @property
    def premultiplied(self) -> bool:
        """Whether the pages store colour already multiplied by alpha.

        Rendering a premultiplied page as if it were straight alpha multiplies
        by alpha a second time, which shows up as black fringes around soft
        edges and mask attachments."""
        return any(page.pma for page in self.pages)

    def find_region(self, name: str) -> Optional[AtlasRegion]:
        return self.regions.get(name)

    @classmethod
    def parse(cls, path) -> "Atlas":
        path = Path(path)
        return cls.parse_text(path.read_text(encoding="utf-8"))

    @classmethod
    def parse_text(cls, text: str) -> "Atlas":
        lines = text.splitlines()
        pages: List[AtlasPage] = []
        regions: Dict[str, AtlasRegion] = {}
        page: Optional[AtlasPage] = None
        i = 0
        n = len(lines)

        while i < n:
            raw = lines[i]
            line = raw.strip()
            if not line:
                # A blank line ends the current page; the next non-blank line is a new page.
                page = None
                i += 1
                continue

            if page is None:
                page = AtlasPage(line)
                pages.append(page)
                i += 1
                i = cls._read_page_properties(lines, i, page)
                continue

            # Region entry: name followed by its property lines.
            region = AtlasRegion(line, page)
            i += 1
            i = cls._read_region_properties(lines, i, region)
            cls._finalize_region(region)
            regions[region.name] = region

        return cls(pages, regions)

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _split_values(value: str) -> List[str]:
        return [p.strip() for p in value.split(",")]

    @classmethod
    def _read_page_properties(cls, lines, i, page) -> int:
        while i < len(lines):
            line = lines[i].strip()
            if not line or ":" not in line:
                break
            key, _, value = line.partition(":")
            key = key.strip()
            vals = cls._split_values(value)
            if key == "size":
                page.width, page.height = int(vals[0]), int(vals[1])
            elif key == "pma":
                page.pma = vals[0] == "true"
            elif key == "format" and len(vals) >= 3 and vals[0].isdigit():
                # Legacy "size" written as part of format is not used; ignore.
                pass
            i += 1
        return i

    @classmethod
    def _read_region_properties(cls, lines, i, region) -> int:
        has_bounds = False
        while i < len(lines):
            line = lines[i].strip()
            if not line or ":" not in line:
                break
            key, _, value = line.partition(":")
            key = key.strip()
            vals = cls._split_values(value)

            if key == "bounds":  # 4.1
                region.x, region.y, region.width, region.height = (int(v) for v in vals[:4])
                has_bounds = True
            elif key == "offsets":  # 4.1
                region.offset_x, region.offset_y = int(vals[0]), int(vals[1])
                region.original_width, region.original_height = int(vals[2]), int(vals[3])
            elif key == "xy":  # legacy
                region.x, region.y = int(vals[0]), int(vals[1])
            elif key == "size":  # legacy
                region.width, region.height = int(vals[0]), int(vals[1])
                has_bounds = True
            elif key == "orig":  # legacy
                region.original_width, region.original_height = int(vals[0]), int(vals[1])
            elif key == "offset":  # legacy
                region.offset_x, region.offset_y = int(vals[0]), int(vals[1])
            elif key == "rotate":
                v = vals[0]
                if v == "true":
                    region.degrees = 90
                elif v == "false":
                    region.degrees = 0
                else:
                    region.degrees = int(v)
            i += 1

        if not has_bounds:
            raise ValueError(f"Atlas region {region.name!r} has no bounds/size")
        return i

    @staticmethod
    def _finalize_region(region: AtlasRegion) -> None:
        """Without an `offsets`/`orig` line nothing was stripped, so the untrimmed
        source size equals the recorded (already un-rotated) size."""
        if not region.original_width:
            region.original_width = region.width
        if not region.original_height:
            region.original_height = region.height
