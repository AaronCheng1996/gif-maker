"""Load a Spine project (skeleton .json + .atlas + texture pages) into memory."""
import contextlib
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from PIL import Image

# Pillow refuses images past ~179 MPix by default as a decompression-bomb guard.
# Spine atlases are legitimately huge — 16384x16384 (268 MPix) is common for
# detailed models — so the ceiling is raised while reading atlas pages only,
# rather than switching the guard off process-wide.
MAX_ATLAS_PIXELS = 32768 * 32768


@contextlib.contextmanager
def _relaxed_image_limit(limit: int = MAX_ATLAS_PIXELS):
    previous = Image.MAX_IMAGE_PIXELS
    if previous is not None and previous < limit:
        Image.MAX_IMAGE_PIXELS = limit
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = previous

from .animation import Animation
from .atlas import Atlas, AtlasRegion
from .attachments import MeshAttachment, RegionAttachment
from .constraints import (IkConstraint, IkConstraintData, TransformConstraint,
                          TransformConstraintData)
from .skeleton import Skeleton


class SpineLoadError(Exception):
    pass


class SpineProject:
    """A loaded skeleton with its atlas, textures and animations."""

    def __init__(self, skeleton: Skeleton, atlas: Atlas, textures: Dict[str, np.ndarray],
                 animations: Dict[str, Animation], name: str, directory: Path):
        self.skeleton = skeleton
        self.atlas = atlas
        self.textures = textures
        self.animations = animations
        self.name = name
        self.directory = directory

    @property
    def animation_names(self) -> List[str]:
        return list(self.animations.keys())

    @property
    def skin_names(self) -> List[str]:
        return [s.name for s in self.skeleton.skins]

    def bounds(self):
        """(x, y, width, height) bounding box Spine recorded at export time."""
        sk = self.skeleton
        return sk.bounds_x, sk.bounds_y, sk.width, sk.height


def find_project_files(directory) -> List[Path]:
    """Return skeleton .json files in `directory` that have a sibling .atlas."""
    directory = Path(directory)
    out = []
    for json_path in sorted(directory.glob("*.json")):
        if json_path.name.endswith(".config.json"):
            continue
        if (json_path.with_suffix(".atlas")).exists():
            out.append(json_path)
    return out


def atlas_is_premultiplied(skeleton_path, atlas_path=None) -> bool:
    """Whether a model's atlas declares premultiplied alpha, without loading it.

    Only the atlas text is read — no texture pages — so this is cheap enough to
    call while opening a model, including when the skeleton itself is a format
    the built-in runtime cannot parse."""
    skeleton_path = Path(skeleton_path)
    atlas_path = Path(atlas_path) if atlas_path else skeleton_path.with_suffix(".atlas")
    if not atlas_path.exists():
        return False
    try:
        return Atlas.parse(atlas_path).premultiplied
    except Exception:
        return False


def load_project(skeleton_path, atlas_path=None) -> SpineProject:
    skeleton_path = Path(skeleton_path)
    if not skeleton_path.exists():
        raise SpineLoadError(f"Skeleton file not found: {skeleton_path}")
    atlas_path = Path(atlas_path) if atlas_path else skeleton_path.with_suffix(".atlas")
    if not atlas_path.exists():
        raise SpineLoadError(f"Atlas file not found: {atlas_path}")

    try:
        data = json.loads(skeleton_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SpineLoadError(f"Could not parse skeleton JSON: {e}") from e

    if "bones" not in data:
        raise SpineLoadError("Not a Spine skeleton file (no 'bones' section)")

    atlas = Atlas.parse(atlas_path)

    textures: Dict[str, np.ndarray] = {}
    for page in atlas.pages:
        tex_path = atlas_path.parent / page.name
        if not tex_path.exists():
            raise SpineLoadError(f"Atlas page image not found: {tex_path}")
        textures[page.name] = _load_atlas_page(tex_path, page)

    skeleton = Skeleton(data)

    for ik_data in data.get("ik", []):
        try:
            skeleton.ik_constraints.append(IkConstraint(IkConstraintData(ik_data), skeleton))
        except KeyError:
            pass  # references a bone that does not exist; skip it
    for tc_data in data.get("transform", []):
        try:
            skeleton.transform_constraints.append(
                TransformConstraint(TransformConstraintData(tc_data), skeleton))
        except KeyError:
            pass
    skeleton.update_cache()

    _wire_attachments(skeleton, atlas)

    animations = {name: Animation(name, adata, skeleton)
                  for name, adata in data.get("animations", {}).items()}

    return SpineProject(skeleton, atlas, textures, animations,
                        skeleton_path.stem, skeleton_path.parent)


def _load_atlas_page(tex_path: Path, page) -> np.ndarray:
    """Decode one atlas page to an RGBA array, with useful errors when it is
    too large for Pillow's guard or for available memory."""
    try:
        with _relaxed_image_limit():
            with Image.open(tex_path) as img:
                page.width, page.height = img.size
                return np.asarray(img.convert("RGBA"))
    except Image.DecompressionBombError as e:
        raise SpineLoadError(
            f"Atlas page {tex_path.name} is larger than this app will decode "
            f"({MAX_ATLAS_PIXELS:,} pixels max): {e}") from e
    except MemoryError as e:
        w = getattr(page, "width", 0) or 0
        h = getattr(page, "height", 0) or 0
        needed = w * h * 4 / (1024 ** 3)
        raise SpineLoadError(
            f"Ran out of memory decoding atlas page {tex_path.name} "
            f"({w}x{h}, about {needed:.1f} GB as RGBA). Export the GIF with "
            f"SpineViewerCLI instead, which streams the atlas on the GPU.") from e
    except OSError as e:
        raise SpineLoadError(f"Could not read atlas page {tex_path.name}: {e}") from e


def _wire_attachments(skeleton: Skeleton, atlas: Atlas):
    """Attach atlas regions to attachments and pre-compute their atlas-space UVs."""
    for skin in skeleton.skins:
        for slot_name, atts in skin.attachments.items():
            for att in atts.values():
                if not isinstance(att, (RegionAttachment, MeshAttachment)):
                    continue
                region = atlas.find_region(att.path)
                if region is None:
                    region = atlas.find_region(att.name)
                att.region = region
                if region is None:
                    continue
                att.atlas_uvs = _compute_atlas_uvs(att.uvs, region)
                if isinstance(att, RegionAttachment):
                    _apply_region_offsets(att, region)


def _compute_atlas_uvs(region_uvs: np.ndarray, region: AtlasRegion) -> np.ndarray:
    """Map an attachment's 0..1 UVs into normalized atlas-page coordinates,
    honouring rotation and whitespace stripping (Spine 4.1 updateRegion)."""
    tw = float(region.page.width)
    th = float(region.page.height)
    u = region.x / tw
    v = region.y / th
    ow, oh = float(region.original_width), float(region.original_height)
    ox, oy = float(region.offset_x), float(region.offset_y)
    # Spine's updateRegion works with the region's un-rotated size here, not its
    # on-page footprint.
    rw, rh = float(region.width), float(region.height)

    su = region_uvs[:, 0]
    sv = region_uvs[:, 1]
    out = np.empty_like(region_uvs)

    if region.degrees == 90:
        u -= (oh - oy - rh) / tw
        v -= (ow - ox - rw) / th
        w = oh / tw
        h = ow / th
        out[:, 0] = u + sv * w
        out[:, 1] = v + h - su * h
    elif region.degrees == 180:
        u -= (ow - ox - rw) / tw
        v -= oy / th
        w = ow / tw
        h = oh / th
        out[:, 0] = u + w - su * w
        out[:, 1] = v + h - sv * h
    elif region.degrees == 270:
        u -= oy / tw
        v -= ox / th
        w = oh / tw
        h = ow / th
        out[:, 0] = u + w - sv * w
        out[:, 1] = v + su * h
    else:
        u -= ox / tw
        v -= (oh - oy - rh) / th
        w = ow / tw
        h = oh / th
        out[:, 0] = u + su * w
        out[:, 1] = v + sv * h
    return out


def _apply_region_offsets(att: RegionAttachment, region: AtlasRegion):
    """Shrink a region attachment's quad to the trimmed area of its atlas region,
    so whitespace-stripped images stay put (Spine 4.1 updateRegion)."""
    width, height = att.width, att.height
    local_x2 = width / 2
    local_y2 = height / 2
    local_x = -local_x2
    local_y = -local_y2

    ow = float(region.original_width) or 1.0
    oh = float(region.original_height) or 1.0
    local_x += region.offset_x / ow * width
    local_y += region.offset_y / oh * height
    if region.degrees in (90, 270):
        local_x2 -= (ow - region.offset_x - region.packed_height) / ow * width
        local_y2 -= (oh - region.offset_y - region.packed_width) / oh * height
    else:
        local_x2 -= (ow - region.offset_x - region.packed_width) / ow * width
        local_y2 -= (oh - region.offset_y - region.packed_height) / oh * height

    att.local_corners = ((local_x, local_y), (local_x, local_y2),
                         (local_x2, local_y2), (local_x2, local_y))
