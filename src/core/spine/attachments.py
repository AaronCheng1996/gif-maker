"""Spine attachment types and their world-space vertex computation.

Only the attachment kinds these projects actually use are implemented:
region, mesh (incl. weighted), linkedmesh (resolved to its parent mesh) and
clipping. Point/boundingbox/path attachments are parsed but do not render.
"""
import math
from typing import List, Optional

import numpy as np

REGION = "region"
MESH = "mesh"
LINKED_MESH = "linkedmesh"
CLIPPING = "clipping"
BOUNDING_BOX = "boundingbox"
PATH = "path"
POINT = "point"


class Attachment:
    type = None

    def __init__(self, name: str, data: dict):
        # `name` is the key the slot looks this attachment up by. An optional
        # "name" field overrides the attachment's own name, and the atlas region
        # is resolved as: path -> name field -> key. Skinned exports rely on
        # this: skin1's {"armL": {"name": "armL skin12"}} must load the region
        # "armL skin12" while still being addressable by the slot as "armL".
        self.name = name
        self.data = data
        self.path = data.get("path", data.get("name", name))
        color = data.get("color")
        self.color = _parse_color(color) if color else (1.0, 1.0, 1.0, 1.0)

    def compute_world_vertices(self, slot) -> np.ndarray:
        raise NotImplementedError


class RegionAttachment(Attachment):
    type = REGION

    def __init__(self, name, data):
        super().__init__(name, data)
        self.x = data.get("x", 0.0)
        self.y = data.get("y", 0.0)
        self.rotation = data.get("rotation", 0.0)
        self.scale_x = data.get("scaleX", 1.0)
        self.scale_y = data.get("scaleY", 1.0)
        self.width = data.get("width", 0.0)
        self.height = data.get("height", 0.0)
        self.region = None  # AtlasRegion, wired up by the loader
        # Region attachments are a single quad: BL, UL, UR, BR (Spine's vertex order).
        self.uvs = np.array([[0.0, 1.0], [0.0, 0.0], [1.0, 0.0], [1.0, 1.0]])
        self.triangles = [0, 1, 2, 2, 3, 0]
        # Overwritten by the loader once the atlas region is known, to account
        # for whitespace stripping. Defaults to the full, untrimmed quad.
        w2, h2 = self.width / 2, self.height / 2
        self.local_corners = ((-w2, -h2), (-w2, h2), (w2, h2), (w2, -h2))

    def compute_world_vertices(self, slot) -> np.ndarray:
        bone = slot.bone
        (lx, ly), (_, ly2), (lx2, _), _ = self.local_corners
        sx, sy = self.scale_x, self.scale_y
        lx, ly, lx2, ly2 = lx * sx, ly * sy, lx2 * sx, ly2 * sy
        r = math.radians(self.rotation)
        cos, sin = math.cos(r), math.sin(r)
        x, y = self.x, self.y
        lx_cos, lx_sin = lx * cos + x, lx * sin
        ly_cos, ly_sin = ly * cos + y, ly * sin
        lx2_cos, lx2_sin = lx2 * cos + x, lx2 * sin
        ly2_cos, ly2_sin = ly2 * cos + y, ly2 * sin
        corners = (
            (lx_cos - ly_sin, ly_cos + lx_sin),      # bottom-left
            (lx_cos - ly2_sin, ly2_cos + lx_sin),    # upper-left
            (lx2_cos - ly2_sin, ly2_cos + lx2_sin),  # upper-right
            (lx2_cos - ly_sin, ly_cos + lx2_sin),    # bottom-right
        )
        out = np.empty((4, 2), dtype=np.float64)
        for i, (cx, cy) in enumerate(corners):
            out[i, 0] = cx * bone.a + cy * bone.b + bone.world_x
            out[i, 1] = cx * bone.c + cy * bone.d + bone.world_y
        return out


class VertexAttachment(Attachment):
    """Base for attachments whose vertices may be bone-weighted."""

    def __init__(self, name, data):
        super().__init__(name, data)
        self._set_vertices(data.get("vertices", []), data.get("vertexCount"))

    def _set_vertices(self, vertices, vertex_count=None):
        self.bones: Optional[List[int]] = None
        if vertex_count is None:
            # Meshes derive the count from their UVs; clipping/boundingbox declare it.
            vertex_count = getattr(self, "vertex_count", None)
        self.vertex_count = vertex_count

        if vertex_count is not None and len(vertices) == vertex_count * 2:
            self.vertices = np.array(vertices, dtype=np.float64).reshape(-1, 2)
            self.weighted = False
            return

        # Weighted layout: per vertex -> boneCount, (boneIndex, x, y, weight) * boneCount
        self.weighted = True
        bone_idx: List[int] = []
        verts: List[float] = []
        i = 0
        n = len(vertices)
        counts: List[int] = []
        while i < n:
            bc = int(vertices[i]); i += 1
            counts.append(bc)
            for _ in range(bc):
                bone_idx.append(int(vertices[i]))
                verts.extend((vertices[i + 1], vertices[i + 2], vertices[i + 3]))
                i += 4
        self.bones = bone_idx
        self.bone_counts = counts
        self.vertices = np.array(verts, dtype=np.float64).reshape(-1, 3)  # x, y, weight
        self.vertex_count = len(counts)

    def compute_world_vertices(self, slot) -> np.ndarray:
        skeleton_bones = slot.skeleton.bones
        if not self.weighted:
            bone = slot.bone
            v = self.vertices
            x = v[:, 0] * bone.a + v[:, 1] * bone.b + bone.world_x
            y = v[:, 0] * bone.c + v[:, 1] * bone.d + bone.world_y
            return np.stack([x, y], axis=1)

        out = np.empty((self.vertex_count, 2), dtype=np.float64)
        vi = 0
        for i, bc in enumerate(self.bone_counts):
            wx = wy = 0.0
            for _ in range(bc):
                b = skeleton_bones[self.bones[vi]]
                vx, vy, w = self.vertices[vi]
                wx += (vx * b.a + vy * b.b + b.world_x) * w
                wy += (vx * b.c + vy * b.d + b.world_y) * w
                vi += 1
            out[i, 0] = wx
            out[i, 1] = wy
        return out


class MeshAttachment(VertexAttachment):
    type = MESH

    def __init__(self, name, data):
        uvs = data.get("uvs", [])
        self.vertex_count = len(uvs) // 2
        super().__init__(name, data)
        self.uvs = np.array(uvs, dtype=np.float64).reshape(-1, 2)
        self.triangles = data.get("triangles", [])
        self.region = None

    def link_from(self, parent: "MeshAttachment", inherit_deform: bool):
        """Adopt geometry from a parent mesh (used to resolve linkedmesh)."""
        self.uvs = parent.uvs
        self.triangles = parent.triangles
        self.vertices = parent.vertices
        self.bones = parent.bones
        self.bone_counts = getattr(parent, "bone_counts", None)
        self.weighted = parent.weighted
        self.vertex_count = parent.vertex_count


class ClippingAttachment(VertexAttachment):
    type = CLIPPING

    def __init__(self, name, data):
        self.vertex_count = data.get("vertexCount", 0)
        super().__init__(name, data)
        self.end_slot_name = data.get("end")


class BoundingBoxAttachment(VertexAttachment):
    type = BOUNDING_BOX

    def __init__(self, name, data):
        self.vertex_count = data.get("vertexCount", 0)
        super().__init__(name, data)


class PointAttachment(Attachment):
    type = POINT


def _parse_color(hex_str: str):
    h = hex_str.lstrip("#")
    if len(h) == 6:
        h += "ff"
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4, 6))


def create_attachment(name: str, data: dict) -> Optional[Attachment]:
    """Build an attachment from its JSON dict. linkedmesh is returned as a
    MeshAttachment placeholder for the loader to resolve."""
    atype = data.get("type", REGION)
    if atype == REGION:
        return RegionAttachment(name, data)
    if atype == MESH:
        return MeshAttachment(name, data)
    if atype == LINKED_MESH:
        att = MeshAttachment(name, {**data, "uvs": [], "triangles": []})
        att.link_parent = data.get("parent")
        att.link_skin = data.get("skin")
        att.link_deform = data.get("deform", True)
        return att
    if atype == CLIPPING:
        return ClippingAttachment(name, data)
    if atype == BOUNDING_BOX:
        return BoundingBoxAttachment(name, data)
    if atype == POINT:
        return PointAttachment(name, data)
    return None
