"""Rebuild images that a game stored as "diced" texture atlases.

Some engines cut every picture into a grid of small cells, throw away cells that
repeat, and pack the survivors into one texture. Forty expression variants of the
same character then cost barely more than one, because they share every cell that
did not change. The packed texture looks like noise: neighbouring cells in it
come from unrelated parts of the picture.

Rebuilding needs the table that says which cell goes where. Two systems are
supported, and they keep that table in quite different places:

* **Utage** (`DicingTextures`) stores a flat list of cell indices per image
  inside a ScriptableObject. That lives in the game's own `.assets` file, so
  reading it needs UnityPy — an asset-ripper export usually drops it.
* **Naninovel SpriteDicing** stores a mesh per image instead: a quad per cell,
  carrying the destination rectangle and the UV rectangle to copy from. That
  travels with the Sprite asset, so an exported `.json` is enough and no extra
  dependency is needed.

Nothing here imports PyQt6.
"""
import base64
import json
import math
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# Utage's DicingTextures MonoScript, by class name. Matching on the name rather
# than a path id keeps this working across games.
UTAGE_SCRIPT = "DicingTextures"


class DicingError(Exception):
    pass


class DicedImage:
    """One rebuildable picture, plus whatever its source needs to rebuild it."""

    __slots__ = ("name", "width", "height", "atlas", "cells", "quads", "texture_id")

    def __init__(self, name: str, width: int, height: int, atlas: str,
                 cells: Optional[List[int]] = None,
                 quads: Optional[List[Tuple[Tuple[int, int, int, int],
                                            Tuple[float, float, float, float]]]] = None,
                 texture_id: Optional[int] = None):
        self.name = name
        self.width = width
        self.height = height
        self.atlas = atlas          # atlas identifier, meaning depends on the source
        self.cells = cells          # Utage: one atlas cell index per grid position
        self.quads = quads          # Naninovel: (dest_rect_px, uv_rect) per cell
        self.texture_id = texture_id  # which texture the sprite samples, when known

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1e6

    def __repr__(self):
        return f"DicedImage({self.name!r}, {self.width}x{self.height})"


# ── Utage ────────────────────────────────────────────────────────────────

class _Reader:
    """Unity's serialised-field layout: little endian, strings and arrays 4-aligned."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def i64(self) -> int:
        v = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return v

    def align(self):
        self.pos = (self.pos + 3) & ~3

    def string(self) -> str:
        n = self.i32()
        s = self.data[self.pos:self.pos + n].decode("utf-8", "replace")
        self.pos += n
        self.align()
        return s

    def pptr(self) -> Tuple[int, int]:
        return self.i32(), self.i64()


class UtageDicingGroup:
    """One `DicingTextures` asset: a cell size and the images sharing its atlases."""

    def __init__(self, name: str, cell_size: int, padding: int, images: List[DicedImage]):
        self.name = name
        self.cell_size = cell_size
        self.padding = padding
        self.images = images

    @property
    def step(self) -> int:
        """Usable pixels per cell — the padding is a bleed margin, not content."""
        return self.cell_size - 2 * self.padding


def parse_utage_group(raw: bytes) -> UtageDicingGroup:
    """Decode a DicingTextures MonoBehaviour from its raw serialised bytes.

    There is no type tree in a stripped build, so the fields are read in
    declaration order. Reaching exactly the end of the buffer is what says the
    layout was understood, and callers rely on that as the validity check."""
    r = _Reader(raw)
    r.pptr()                    # m_GameObject
    r.pos += 1                  # m_Enabled
    r.align()
    r.pptr()                    # m_Script
    name = r.string()           # m_Name
    cell_size = r.i32()
    padding = r.i32()
    for _ in range(r.i32()):    # atlasTextures
        r.pptr()

    images: List[DicedImage] = []
    for _ in range(r.i32()):    # textureDataList
        img_name = r.string()
        atlas = r.string()
        width = r.i32()
        height = r.i32()
        cells = [r.i32() for _ in range(r.i32())]
        r.i32()                 # transparentIndex, only a rendering shortcut
        images.append(DicedImage(img_name, width, height, atlas, cells=cells))

    if r.pos != len(raw):
        raise DicingError(
            f"DicingTextures layout not understood: read {r.pos} of {len(raw)} bytes")
    return UtageDicingGroup(name, cell_size, padding, images)


def looks_like_utage_group(group: UtageDicingGroup) -> bool:
    """Whether a parse is believable rather than a coincidence.

    A stripped build has no type tree, so DicingTextures assets cannot be picked
    out by their script — every MonoBehaviour is simply parsed and the results
    are filtered. Having consumed the buffer exactly *and* having every image's
    cell count agree with its own grid is not something unrelated data does."""
    if group.cell_size not in (16, 32, 64, 128, 256):
        return False
    if not 0 <= group.padding < group.cell_size // 2:
        return False
    if not group.images:
        return False
    step = group.step
    for image in group.images:
        if image.width <= 0 or image.height <= 0 or not image.cells:
            return False
        expected = math.ceil(image.width / step) * math.ceil(image.height / step)
        if len(image.cells) != expected:
            return False
    return True


def read_utage_groups(assets_path) -> List[UtageDicingGroup]:
    """Find every DicingTextures asset in a Unity `.assets` file or bundle."""
    try:
        import UnityPy
    except ImportError as e:
        raise DicingError(
            "Reading Utage dicing tables needs UnityPy (pip install UnityPy)") from e

    env = UnityPy.load(str(assets_path))
    groups: List[UtageDicingGroup] = []
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            raw = obj.get_raw_data()
        except Exception:
            continue
        if len(raw) < 24:
            continue
        try:
            group = parse_utage_group(raw)
        except (DicingError, struct.error, UnicodeDecodeError, MemoryError, ValueError):
            continue
        if looks_like_utage_group(group):
            groups.append(group)
    return groups


def load_utage_textures(assets_path) -> Dict[str, Image.Image]:
    """Decode every Texture2D in a Unity file, keyed by name."""
    try:
        import UnityPy
    except ImportError as e:
        raise DicingError("Reading Unity textures needs UnityPy") from e

    out: Dict[str, Image.Image] = {}
    env = UnityPy.load(str(assets_path))
    for obj in env.objects:
        if obj.type.name != "Texture2D":
            continue
        try:
            data = obj.read()
            out[data.m_Name] = data.image
        except Exception:
            continue
    return out


def rebuild_utage(image: DicedImage, atlas: Image.Image,
                  cell_size: int, padding: int) -> Image.Image:
    """Reassemble one image from its cell index list.

    Unity texture coordinates start at the bottom, so both the atlas and the
    canvas are worked on flipped and the result is flipped back at the end."""
    if image.cells is None:
        raise DicingError(f"{image.name} carries no cell index list")
    step = cell_size - 2 * padding
    if step <= 0:
        raise DicingError(f"padding {padding} leaves no content in a {cell_size}px cell")

    cols = math.ceil(image.width / step)
    rows = math.ceil(image.height / step)
    expected = cols * rows
    if len(image.cells) != expected:
        raise DicingError(
            f"{image.name}: {len(image.cells)} cells but a "
            f"{cols}x{rows} grid needs {expected}")

    src = np.asarray(atlas.convert("RGBA"))[::-1]
    per_row = math.ceil(src.shape[1] / cell_size)
    out = np.zeros((image.height, image.width, 4), dtype=np.uint8)

    for i in range(rows):
        y0, y1 = i * step, min(i * step + step, image.height)
        for j in range(cols):
            x0, x1 = j * step, min(j * step + step, image.width)
            index = image.cells[i * cols + j]
            if index < 0:
                continue
            sx = (index % per_row) * cell_size + padding
            sy = (index // per_row) * cell_size + padding
            patch = src[sy:sy + (y1 - y0), sx:sx + (x1 - x0)]
            if patch.shape[:2] == (y1 - y0, x1 - x0):
                out[y0:y1, x0:x1] = patch
    return Image.fromarray(out[::-1], "RGBA")


# ── Naninovel SpriteDicing ───────────────────────────────────────────────

def read_sprite_dicing(json_path) -> Optional[DicedImage]:
    """Read a diced sprite out of an asset-ripper Sprite `.json`.

    Returns None for sprites that are a single quad — those are ordinary
    sprites that happen to sit next to diced ones."""
    path = Path(json_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None

    rd = data.get("m_RD") or {}
    vertex_data = rd.get("m_VertexData") or {}
    count = vertex_data.get("m_VertexCount") or 0
    if count <= 4:
        return None

    width = int((data.get("m_Rect") or {}).get("m_Width") or 0)
    height = int((data.get("m_Rect") or {}).get("m_Height") or 0)
    if width <= 0 or height <= 0:
        return None

    try:
        positions, uvs = _decode_vertex_streams(vertex_data, count)
        indices = np.frombuffer(base64.b64decode(rd["m_IndexBuffer"]), dtype=np.uint16)
    except Exception:
        return None

    ppu = data.get("m_PixelsToUnits") or 100
    quads = []
    for q in range(len(indices) // 6):
        corners = sorted({int(v) for v in indices[q * 6:q * 6 + 6]})
        if len(corners) != 4:
            continue
        p = positions[corners]
        u = uvs[corners]
        # Positions are in world units around the sprite's centre.
        x0 = int(round(p[:, 0].min() * ppu + width / 2))
        x1 = int(round(p[:, 0].max() * ppu + width / 2))
        y0 = int(round(p[:, 1].min() * ppu + height / 2))
        y1 = int(round(p[:, 1].max() * ppu + height / 2))
        if x1 <= x0 or y1 <= y0:
            continue
        quads.append(((x0, y0, x1, y1),
                      (float(u[:, 0].min()), float(u[:, 1].min()),
                       float(u[:, 0].max()), float(u[:, 1].max()))))
    if not quads:
        return None
    return DicedImage(data.get("m_Name") or path.stem, width, height,
                      atlas="", quads=quads,
                      texture_id=(rd.get("m_Texture") or {}).get("m_PathID"))


def _decode_vertex_streams(vertex_data: dict, count: int):
    """Pull positions and UV0 out of Unity's vertex buffer.

    Channels are grouped into streams that are stored one after another rather
    than interleaved, and each stream starts on a 16-byte boundary."""
    buffer = base64.b64decode(vertex_data["m_Data"])
    channels = vertex_data.get("m_Channels") or []

    widths: Dict[int, int] = {}
    for channel in channels:
        dim = channel.get("m_Dimension", 0)
        if dim:
            widths[channel.get("m_Stream", 0)] = widths.get(channel.get("m_Stream", 0), 0) + dim * 4

    offsets: Dict[int, int] = {}
    cursor = 0
    for stream in sorted(widths):
        offsets[stream] = cursor
        cursor = (cursor + widths[stream] * count + 15) & ~15

    def channel_array(index: int, dim: int):
        channel = channels[index]
        stream = channel.get("m_Stream", 0)
        stride = widths[stream] // 4
        start = offsets[stream] // 4
        flat = np.frombuffer(buffer, dtype=np.float32,
                             count=stride * count, offset=start * 4).reshape(count, stride)
        first = channel.get("m_Offset", 0) // 4
        return flat[:, first:first + dim]

    return channel_array(0, 3), channel_array(4, 2)


def rebuild_sprite_dicing(image: DicedImage, atlas: Image.Image) -> Image.Image:
    """Reassemble one image by copying each quad's UV rectangle into place.

    The UV rectangle is trusted over any assumption about cell size: some atlases
    store the cells at a slightly different scale from the sprite, so a patch is
    resampled when its source and destination sizes disagree."""
    if not image.quads:
        raise DicingError(f"{image.name} carries no quads")
    atlas = atlas.convert("RGBA")
    aw, ah = atlas.size
    out = Image.new("RGBA", (image.width, image.height), (0, 0, 0, 0))

    for (x0, y0, x1, y1), (u0, v0, u1, v1) in image.quads:
        box = (int(round(u0 * aw)), int(round(ah - v1 * ah)),
               int(round(u1 * aw)), int(round(ah - v0 * ah)))
        patch = atlas.crop(box)
        size = (x1 - x0, y1 - y0)
        if patch.size != size:
            patch = patch.resize(size, Image.Resampling.LANCZOS)
        # Destination y also counts from the bottom.
        out.paste(patch, (x0, image.height - y1))
    return out


def scan_sprite_dicing_folder(folder) -> Tuple[List[DicedImage], List[Path]]:
    """Collect the diced sprites in a folder and the PNGs that could be their atlas."""
    folder = Path(folder)
    images = [img for img in (read_sprite_dicing(p) for p in sorted(folder.glob("*.json")))
              if img is not None]
    pngs = sorted(folder.glob("*.png"), key=_png_pixels, reverse=True)
    # A sheet is usually also exported as a sprite covering the whole texture;
    # rebuilding that would just reproduce the sheet.
    sheet_names = {p.stem for p in pngs}
    images = [img for img in images if img.name not in sheet_names]
    if not images:
        return [], pngs
    # An atlas is at least as large as anything packed into it.
    biggest = max(img.width * img.height for img in images)
    candidates = [p for p in pngs if _png_pixels(p) >= biggest]
    return images, candidates or pngs


def choose_atlases(images: List[DicedImage], candidates: List[Path],
                   step: int = 64) -> Dict[Optional[int], Optional[Path]]:
    """Work out which candidate atlas each sprite was packed into.

    The export records which texture a sprite samples only as an id, and the
    exported PNGs carry no id at all, so the pairing is settled by rebuilding one
    sprite per group against each candidate and keeping whichever leaves no seams
    on the cell grid. A wrong atlas is not subtle — it misses by tens of levels."""
    by_texture: Dict[Optional[int], List[DicedImage]] = {}
    for img in images:
        by_texture.setdefault(img.texture_id, []).append(img)

    chosen: Dict[Optional[int], Optional[Path]] = {}
    for texture_id, group in by_texture.items():
        if len(candidates) == 1:
            chosen[texture_id] = candidates[0]
            continue
        sample = min(group, key=lambda i: i.width * i.height)
        best, best_excess = None, float("inf")
        for path in candidates:
            try:
                with Image.open(path) as atlas:
                    rebuilt = rebuild_sprite_dicing(sample, atlas)
            except (OSError, DicingError, ValueError):
                continue
            seam, inner = seam_score(rebuilt, step)
            if seam != seam or inner != inner:      # NaN: nothing to measure
                continue
            if seam - inner < best_excess:
                best, best_excess = path, seam - inner
        chosen[texture_id] = best or (candidates[0] if candidates else None)
    return chosen


def _png_pixels(path: Path) -> int:
    try:
        with Image.open(path) as im:
            return im.width * im.height
    except Exception:
        return 0


# ── seam check ───────────────────────────────────────────────────────────

# How much worse than the picture's own texture a cell border may look before
# the rebuild is treated as wrong. Correct rebuilds land under 1.5; pairing a
# sprite with the wrong atlas overshoots by tens.
SEAM_TOLERANCE = 5.0


def verify_rebuild(image: Image.Image, step: int) -> Tuple[bool, float]:
    """(is the rebuild believable, how much the cell borders stand out).

    Guards against writing a scrambled picture: if a sprite is paired with the
    wrong atlas the cell grid shows up as hard edges, and that is measurable
    without having anything to compare against."""
    seam, inner = seam_score(image, step)
    if seam != seam or inner != inner:      # NaN: too transparent to judge
        return True, 0.0
    excess = seam - inner
    return excess <= SEAM_TOLERANCE, excess


def seam_score(image: Image.Image, step: int) -> Tuple[float, float]:
    """(discontinuity across cell borders, ordinary neighbouring-pixel difference).

    A correct rebuild makes the first indistinguishable from the second; a wrong
    cell table leaves visible edges on the grid. Only pixels that are opaque on
    both sides count, so transparent margins cannot flatter the result."""
    a = np.asarray(image.convert("RGBA"))
    grey = a[..., :3].astype(np.float32).mean(axis=2)
    opaque = a[..., 3] > 200
    if step <= 0 or grey.size == 0:
        return float("nan"), float("nan")

    jumps = []
    for y in range(step, grey.shape[0], step):
        mask = opaque[y] & opaque[y - 1]
        if mask.sum() > 50:
            jumps.append(float(np.abs(grey[y] - grey[y - 1])[mask].mean()))
    for x in range(step, grey.shape[1], step):
        mask = opaque[:, x] & opaque[:, x - 1]
        if mask.sum() > 50:
            jumps.append(float(np.abs(grey[:, x] - grey[:, x - 1])[mask].mean()))

    inner_mask = opaque[1:] & opaque[:-1]
    inner = (float(np.abs(np.diff(grey, axis=0))[inner_mask].mean())
             if inner_mask.any() else float("nan"))
    return (float(np.mean(jumps)) if jumps else float("nan")), inner
