"""Software renderer: poses a skeleton and rasterizes it into a PIL image.

Textured triangles are filled with barycentric coordinates in numpy. Clipping
attachments are applied as a rasterized polygon mask covering the slot range
they declare.
"""
import math
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .attachments import (ClippingAttachment, MeshAttachment, RegionAttachment,
                          VertexAttachment)
from .loader import SpineProject

BLEND_NORMAL = "normal"
BLEND_ADDITIVE = "additive"
BLEND_MULTIPLY = "multiply"
BLEND_SCREEN = "screen"


class RenderSettings:
    """Framing and quality options for a render."""

    def __init__(self, scale: float = 1.0, padding: int = 0,
                 background: Optional[Tuple[int, int, int, int]] = None,
                 bounds: Optional[Tuple[float, float, float, float]] = None):
        self.scale = scale
        self.padding = padding
        self.background = background  # None = transparent
        self.bounds = bounds  # (x, y, width, height) in skeleton space


class SpineRenderer:
    def __init__(self, project: SpineProject):
        self.project = project
        self.skeleton = project.skeleton

    # ── posing ───────────────────────────────────────────────────────────

    def pose(self, animation_name: Optional[str], time: float):
        skeleton = self.skeleton
        skeleton.set_to_setup_pose()
        if animation_name:
            animation = self.project.animations.get(animation_name)
            if animation is not None:
                animation.apply(skeleton, time)
        skeleton.update_world_transform()

    # ── framing ──────────────────────────────────────────────────────────

    def _frame(self, settings: RenderSettings):
        if settings.bounds is not None:
            bx, by, bw, bh = settings.bounds
        else:
            bx, by, bw, bh = self.project.bounds()
        if bw <= 0 or bh <= 0:
            bx, by, bw, bh = self.compute_bounds()
        scale = settings.scale
        pad = settings.padding
        width = max(1, int(round(bw * scale)) + pad * 2)
        height = max(1, int(round(bh * scale)) + pad * 2)
        # Skeleton space has +Y up; image space has +Y down.
        ox = -bx * scale + pad
        oy = (by + bh) * scale + pad
        return width, height, ox, oy

    def compute_bounds(self, animation_name: Optional[str] = None, samples: int = 12):
        """Bounding box over the whole animation (or the current pose)."""
        min_x = min_y = float("inf")
        max_x = max_y = float("-inf")
        animation = self.project.animations.get(animation_name) if animation_name else None
        times = [0.0]
        if animation is not None and animation.duration > 0:
            times = [animation.duration * i / max(samples - 1, 1) for i in range(samples)]

        for t in times:
            self.pose(animation_name, t)
            for slot_index in self.skeleton.draw_order:
                slot = self.skeleton.slots[slot_index]
                att = self._slot_attachment(slot)
                if att is None or not isinstance(att, (MeshAttachment, RegionAttachment)):
                    continue
                try:
                    xy = att.compute_world_vertices(slot)
                except Exception:
                    continue
                if len(xy) == 0:
                    continue
                min_x = min(min_x, float(xy[:, 0].min()))
                max_x = max(max_x, float(xy[:, 0].max()))
                min_y = min(min_y, float(xy[:, 1].min()))
                max_y = max(max_y, float(xy[:, 1].max()))

        if min_x > max_x:
            return self.project.bounds()
        return min_x, min_y, max_x - min_x, max_y - min_y

    def _slot_attachment(self, slot):
        if not slot.attachment_name:
            return None
        return self.skeleton.get_attachment(slot.name, slot.attachment_name)

    # ── rendering ────────────────────────────────────────────────────────

    def render(self, animation_name: Optional[str], time: float,
               settings: Optional[RenderSettings] = None) -> Image.Image:
        settings = settings or RenderSettings()
        self.pose(animation_name, time)
        return self.render_current_pose(settings)

    def render_current_pose(self, settings: RenderSettings) -> Image.Image:
        width, height, ox, oy = self._frame(settings)
        scale = settings.scale
        # Compositing happens in premultiplied alpha so that overlapping
        # semi-transparent parts accumulate correctly; un-premultiplied at the end.
        canvas = np.zeros((height, width, 4), dtype=np.float32)

        clip_mask: Optional[np.ndarray] = None
        clip_end_slot: Optional[str] = None

        for slot_index in self.skeleton.draw_order:
            slot = self.skeleton.slots[slot_index]
            att = self._slot_attachment(slot)

            if clip_end_slot is not None and slot.name == clip_end_slot:
                clip_mask = None
                clip_end_slot = None

            if att is None:
                continue

            if isinstance(att, ClippingAttachment):
                clip_mask = self._rasterize_clip(att, slot, width, height, ox, oy, scale)
                clip_end_slot = att.end_slot_name
                continue

            if not isinstance(att, (MeshAttachment, RegionAttachment)):
                continue
            region = getattr(att, "region", None)
            if region is None or not hasattr(att, "atlas_uvs"):
                continue

            texture = self.project.textures.get(region.page.name)
            if texture is None:
                continue

            try:
                xy = att.compute_world_vertices(slot)
            except Exception:
                continue
            if len(xy) == 0:
                continue

            sxy = np.empty_like(xy, dtype=np.float32)
            sxy[:, 0] = xy[:, 0] * scale + ox
            sxy[:, 1] = -xy[:, 1] * scale + oy

            tint = _slot_tint(slot, att)
            if tint[3] <= 0.001:
                continue

            _draw_mesh(canvas, texture, sxy, att.atlas_uvs, att.triangles, tint,
                       slot.data.blend_mode, clip_mask)

        img = Image.fromarray(_unpremultiply(canvas), mode="RGBA")
        if settings.background is not None:
            bg = Image.new("RGBA", img.size, settings.background)
            bg.alpha_composite(img)
            img = bg
        return img

    def _rasterize_clip(self, att: ClippingAttachment, slot, width, height, ox, oy, scale):
        try:
            xy = att.compute_world_vertices(slot)
        except Exception:
            return None
        if len(xy) < 3:
            return None
        pts = [(float(x * scale + ox), float(-y * scale + oy)) for x, y in xy]
        mask_img = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask_img).polygon(pts, fill=255)
        return np.asarray(mask_img, dtype=np.float32) / 255.0


def _slot_tint(slot, att):
    c = slot.color
    ac = att.color
    return (c[0] * ac[0], c[1] * ac[1], c[2] * ac[2], c[3] * ac[3])


def _draw_mesh(canvas, texture, sxy, uvs, triangles, tint, blend_mode, clip_mask):
    tex_h, tex_w = texture.shape[:2]
    for i in range(0, len(triangles) - 2, 3):
        idx = (triangles[i], triangles[i + 1], triangles[i + 2])
        _draw_triangle(canvas, texture, sxy[idx, :], uvs[idx, :], tex_w, tex_h,
                       tint, blend_mode, clip_mask)


def _draw_triangle(canvas, texture, tri_xy, tri_uv, tex_w, tex_h, tint, blend_mode, clip_mask):
    H, W = canvas.shape[:2]
    xs = tri_xy[:, 0]
    ys = tri_xy[:, 1]
    min_x = int(math.floor(xs.min()))
    max_x = int(math.ceil(xs.max())) + 1
    min_y = int(math.floor(ys.min()))
    max_y = int(math.ceil(ys.max())) + 1
    if min_x < 0:
        min_x = 0
    if min_y < 0:
        min_y = 0
    if max_x > W:
        max_x = W
    if max_y > H:
        max_y = H
    if min_x >= max_x or min_y >= max_y:
        return

    x0, y0 = tri_xy[0]
    x1, y1 = tri_xy[1]
    x2, y2 = tri_xy[2]
    denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denom) < 1e-9:
        return
    inv_denom = 1.0 / denom

    px = np.arange(min_x, max_x, dtype=np.float32) + 0.5
    py = np.arange(min_y, max_y, dtype=np.float32) + 0.5
    gx = px[None, :]
    gy = py[:, None]

    l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) * inv_denom
    l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) * inv_denom
    l2 = 1.0 - l0 - l1
    inside = (l0 >= 0) & (l1 >= 0) & (l2 >= 0)
    if not inside.any():
        return

    u = l0 * tri_uv[0, 0] + l1 * tri_uv[1, 0] + l2 * tri_uv[2, 0]
    v = l0 * tri_uv[0, 1] + l1 * tri_uv[1, 1] + l2 * tri_uv[2, 1]
    sx = np.clip((u * tex_w).astype(np.int32), 0, tex_w - 1)
    sy = np.clip((v * tex_h).astype(np.int32), 0, tex_h - 1)

    src = texture[sy[inside], sx[inside]].astype(np.float32)
    if tint != (1.0, 1.0, 1.0, 1.0):
        src = src * np.array(tint, dtype=np.float32)

    src_a = src[:, 3:4]
    if clip_mask is not None:
        m = clip_mask[min_y:max_y, min_x:max_x][inside]
        if not m.any():
            return
        src_a = src_a * m[:, None]

    sa = src_a * (1.0 / 255.0)          # source coverage, 0..1
    src_rgb = src[:, :3] * sa           # premultiplied source colour

    region = canvas[min_y:max_y, min_x:max_x]
    dst = region[inside]
    dst_rgb = dst[:, :3]
    dst_a = dst[:, 3:4]

    if blend_mode == BLEND_ADDITIVE:
        out_rgb = dst_rgb + src_rgb
        out_a = np.minimum(dst_a + src_a, 255.0)
    elif blend_mode == BLEND_MULTIPLY:
        out_rgb = src_rgb * dst_rgb * (1.0 / 255.0) + dst_rgb * (1.0 - sa)
        out_a = src_a + dst_a * (1.0 - sa)
    elif blend_mode == BLEND_SCREEN:
        out_rgb = src_rgb + dst_rgb - src_rgb * dst_rgb * (1.0 / 255.0)
        out_a = src_a + dst_a * (1.0 - sa)
    else:  # normal (source-over)
        out_rgb = src_rgb + dst_rgb * (1.0 - sa)
        out_a = src_a + dst_a * (1.0 - sa)

    region[inside] = np.concatenate([out_rgb, out_a], axis=1)


def _unpremultiply(canvas: np.ndarray) -> np.ndarray:
    """Convert the premultiplied float canvas back to straight 8-bit RGBA."""
    alpha = canvas[:, :, 3:4]
    safe = np.where(alpha > 0.0, alpha, 1.0)
    rgb = canvas[:, :, :3] * (255.0 / safe)
    out = np.empty(canvas.shape, dtype=np.uint8)
    out[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    out[:, :, 3] = np.clip(alpha[:, :, 0], 0, 255).astype(np.uint8)
    return out
