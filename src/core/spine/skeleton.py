"""Spine skeleton: bones, slots, skins and the world-transform update pass.

Follows the Spine 4.1 runtime semantics, including the `inherit` (transform)
modes and the update cache that interleaves bones with constraints so that a
constraint runs only after the bones it depends on are up to date.
"""
import math
from typing import Dict, List, Optional

from .attachments import Attachment, create_attachment

DEG_RAD = math.pi / 180.0
RAD_DEG = 180.0 / math.pi

INHERIT_NORMAL = "normal"
INHERIT_ONLY_TRANSLATION = "onlyTranslation"
INHERIT_NO_ROTATION_OR_REFLECTION = "noRotationOrReflection"
INHERIT_NO_SCALE = "noScale"
INHERIT_NO_SCALE_OR_REFLECTION = "noScaleOrReflection"


class BoneData:
    __slots__ = ("index", "name", "parent", "length", "x", "y", "rotation",
                 "scale_x", "scale_y", "shear_x", "shear_y", "inherit")

    def __init__(self, index: int, data: dict, parent: Optional["BoneData"]):
        self.index = index
        self.name = data["name"]
        self.parent = parent
        self.length = data.get("length", 0.0)
        self.x = data.get("x", 0.0)
        self.y = data.get("y", 0.0)
        self.rotation = data.get("rotation", 0.0)
        self.scale_x = data.get("scaleX", 1.0)
        self.scale_y = data.get("scaleY", 1.0)
        self.shear_x = data.get("shearX", 0.0)
        self.shear_y = data.get("shearY", 0.0)
        # Spine 4.2 renamed "transform" to "inherit"; accept both.
        self.inherit = data.get("inherit", data.get("transform", INHERIT_NORMAL))


class Bone:
    __slots__ = ("data", "skeleton", "parent", "children",
                 "x", "y", "rotation", "scale_x", "scale_y", "shear_x", "shear_y",
                 "ax", "ay", "arotation", "ascale_x", "ascale_y", "ashear_x", "ashear_y",
                 "a", "b", "c", "d", "world_x", "world_y", "sorted", "active")

    def __init__(self, data: BoneData, skeleton: "Skeleton", parent: Optional["Bone"]):
        self.data = data
        self.skeleton = skeleton
        self.parent = parent
        self.children: List[Bone] = []
        self.sorted = False
        self.active = True
        self.set_to_setup_pose()

    @property
    def name(self):
        return self.data.name

    def set_to_setup_pose(self):
        d = self.data
        self.x, self.y = d.x, d.y
        self.rotation = d.rotation
        self.scale_x, self.scale_y = d.scale_x, d.scale_y
        self.shear_x, self.shear_y = d.shear_x, d.shear_y

    def update_world_transform(self):
        self.update_world_transform_with(
            self.x, self.y, self.rotation, self.scale_x, self.scale_y,
            self.shear_x, self.shear_y,
        )

    def update_world_transform_with(self, x, y, rotation, scale_x, scale_y, shear_x, shear_y):
        # Remember the values the world transform was computed from; IK writes
        # these back so later constraints see a consistent local pose.
        self.ax, self.ay = x, y
        self.arotation = rotation
        self.ascale_x, self.ascale_y = scale_x, scale_y
        self.ashear_x, self.ashear_y = shear_x, shear_y

        sk = self.skeleton
        parent = self.parent
        if parent is None:
            rx = (rotation + shear_x) * DEG_RAD
            ry = (rotation + 90 + shear_y) * DEG_RAD
            self.a = math.cos(rx) * scale_x * sk.scale_x
            self.b = math.cos(ry) * scale_y * sk.scale_x
            self.c = math.sin(rx) * scale_x * sk.scale_y
            self.d = math.sin(ry) * scale_y * sk.scale_y
            self.world_x = x * sk.scale_x + sk.x
            self.world_y = y * sk.scale_y + sk.y
            return

        pa, pb, pc, pd = parent.a, parent.b, parent.c, parent.d
        self.world_x = pa * x + pb * y + parent.world_x
        self.world_y = pc * x + pd * y + parent.world_y

        inherit = self.data.inherit
        if inherit == INHERIT_NORMAL:
            rx = (rotation + shear_x) * DEG_RAD
            ry = (rotation + 90 + shear_y) * DEG_RAD
            la = math.cos(rx) * scale_x
            lb = math.cos(ry) * scale_y
            lc = math.sin(rx) * scale_x
            ld = math.sin(ry) * scale_y
            self.a = pa * la + pb * lc
            self.b = pa * lb + pb * ld
            self.c = pc * la + pd * lc
            self.d = pc * lb + pd * ld
            return

        if inherit == INHERIT_ONLY_TRANSLATION:
            rx = (rotation + shear_x) * DEG_RAD
            ry = (rotation + 90 + shear_y) * DEG_RAD
            self.a = math.cos(rx) * scale_x
            self.b = math.cos(ry) * scale_y
            self.c = math.sin(rx) * scale_x
            self.d = math.sin(ry) * scale_y

        elif inherit == INHERIT_NO_ROTATION_OR_REFLECTION:
            s = pa * pa + pc * pc
            if s > 0.0001:
                s = abs(pa * pd - pb * pc) / s
                pa /= sk.scale_x
                pc /= sk.scale_y
                pb = pc * s
                pd = pa * s
                prx = math.atan2(pc, pa) * RAD_DEG
            else:
                pa = pc = 0.0
                prx = 90 - math.atan2(pd, pb) * RAD_DEG
            rx = (rotation + shear_x - prx) * DEG_RAD
            ry = (rotation + shear_y - prx + 90) * DEG_RAD
            la = math.cos(rx) * scale_x
            lb = math.cos(ry) * scale_y
            lc = math.sin(rx) * scale_x
            ld = math.sin(ry) * scale_y
            self.a = pa * la - pb * lc
            self.b = pa * lb - pb * ld
            self.c = pc * la + pd * lc
            self.d = pc * lb + pd * ld

        else:  # noScale / noScaleOrReflection
            rr = rotation * DEG_RAD
            cos, sin = math.cos(rr), math.sin(rr)
            za = (pa * cos + pb * sin) / sk.scale_x
            zc = (pc * cos + pd * sin) / sk.scale_y
            s = math.sqrt(za * za + zc * zc)
            if s > 0.00001:
                s = 1 / s
            za *= s
            zc *= s
            s = math.sqrt(za * za + zc * zc)
            if (inherit == INHERIT_NO_SCALE
                    and (pa * pd - pb * pc < 0) != ((sk.scale_x < 0) != (sk.scale_y < 0))):
                s = -s
            r = math.pi / 2 + math.atan2(zc, za)
            zb = math.cos(r) * s
            zd = math.sin(r) * s
            la = math.cos(shear_x * DEG_RAD) * scale_x
            lb = math.cos((90 + shear_y) * DEG_RAD) * scale_y
            lc = math.sin(shear_x * DEG_RAD) * scale_x
            ld = math.sin((90 + shear_y) * DEG_RAD) * scale_y
            self.a = za * la + zb * lc
            self.b = za * lb + zb * ld
            self.c = zc * la + zd * lc
            self.d = zc * lb + zd * ld

        self.a *= sk.scale_x
        self.b *= sk.scale_x
        self.c *= sk.scale_y
        self.d *= sk.scale_y

    # ── helpers used by constraints ──────────────────────────────────────

    def local_to_world(self, local_x: float, local_y: float):
        return (local_x * self.a + local_y * self.b + self.world_x,
                local_x * self.c + local_y * self.d + self.world_y)

    def world_to_local_rotation(self, world_rotation: float) -> float:
        sin = math.sin(world_rotation * DEG_RAD)
        cos = math.cos(world_rotation * DEG_RAD)
        return (math.atan2(self.a * sin - self.c * cos, self.d * cos - self.b * sin) * RAD_DEG
                + self.rotation - self.shear_x)

    def get_world_rotation_x(self) -> float:
        return math.atan2(self.c, self.a) * RAD_DEG

    def get_world_scale_x(self) -> float:
        return math.sqrt(self.a * self.a + self.c * self.c)

    def update_applied_transform(self):
        """Recover local (applied) values from the world matrix.

        Constraints mutate a/b/c/d and worldX/worldY directly; child bones are
        computed from the parent's world matrix, but anything that later reads
        this bone's local pose (another constraint, or IK) needs these back in
        sync with what the world matrix now says."""
        parent = self.parent
        if parent is None:
            self.ax = self.world_x - self.skeleton.x
            self.ay = self.world_y - self.skeleton.y
            self.arotation = math.atan2(self.c, self.a) * RAD_DEG
            self.ascale_x = math.sqrt(self.a * self.a + self.c * self.c)
            self.ascale_y = math.sqrt(self.b * self.b + self.d * self.d)
            self.ashear_x = 0.0
            self.ashear_y = math.atan2(self.a * self.b + self.c * self.d,
                                       self.a * self.d - self.b * self.c) * RAD_DEG
            return

        pa, pb, pc, pd = parent.a, parent.b, parent.c, parent.d
        pid = pa * pd - pb * pc
        pid = 0.0 if abs(pid) <= 0.0001 else 1.0 / pid
        dx = self.world_x - parent.world_x
        dy = self.world_y - parent.world_y
        self.ax = (dx * pd * pid - dy * pb * pid)
        self.ay = (dy * pa * pid - dx * pc * pid)

        ia = pid * pd
        id_ = pid * pa
        ib = pid * pb
        ic = pid * pc
        ra = ia * self.a - ib * self.c
        rb = ia * self.b - ib * self.d
        rc = id_ * self.c - ic * self.a
        rd = id_ * self.d - ic * self.b

        self.ashear_x = 0.0
        self.ascale_x = math.sqrt(ra * ra + rc * rc)
        if self.ascale_x > 0.0001:
            det = ra * rd - rb * rc
            self.ascale_y = det / self.ascale_x
            self.ashear_y = math.atan2(ra * rb + rc * rd, det) * RAD_DEG
            self.arotation = math.atan2(rc, ra) * RAD_DEG
        else:
            self.ascale_x = 0.0
            self.ascale_y = math.sqrt(rb * rb + rd * rd)
            self.ashear_y = 0.0
            self.arotation = 90 - math.atan2(rd, rb) * RAD_DEG


class SlotData:
    __slots__ = ("index", "name", "bone_name", "color", "dark_color",
                 "attachment_name", "blend_mode")

    def __init__(self, index: int, data: dict):
        self.index = index
        self.name = data["name"]
        self.bone_name = data["bone"]
        self.color = _parse_color(data.get("color", "ffffffff"))
        dark = data.get("dark")
        self.dark_color = _parse_color(dark) if dark else None
        self.attachment_name = data.get("attachment")
        self.blend_mode = data.get("blend", "normal")


class Slot:
    __slots__ = ("data", "bone", "skeleton", "color", "dark_color", "attachment_name")

    def __init__(self, data: SlotData, bone: Bone, skeleton: "Skeleton"):
        self.data = data
        self.bone = bone
        self.skeleton = skeleton
        self.set_to_setup_pose()

    @property
    def name(self):
        return self.data.name

    def set_to_setup_pose(self):
        self.color = list(self.data.color)
        self.dark_color = list(self.data.dark_color) if self.data.dark_color else None
        self.attachment_name = self.data.attachment_name


class Skin:
    def __init__(self, name: str):
        self.name = name
        # {slot_name: {attachment_name: Attachment}}
        self.attachments: Dict[str, Dict[str, Attachment]] = {}

    def add(self, slot_name: str, attachment_name: str, attachment: Attachment):
        self.attachments.setdefault(slot_name, {})[attachment_name] = attachment

    def get(self, slot_name: str, attachment_name: str) -> Optional[Attachment]:
        return self.attachments.get(slot_name, {}).get(attachment_name)


class Skeleton:
    def __init__(self, data: dict):
        self.raw = data
        info = data.get("skeleton", {})
        self.spine_version = info.get("spine", "")
        # The skeleton block's x/y/width/height is the bounding box Spine recorded
        # at export time — a framing hint, NOT the skeleton's position.
        self.bounds_x = info.get("x", 0.0)
        self.bounds_y = info.get("y", 0.0)
        self.width = info.get("width", 0.0)
        self.height = info.get("height", 0.0)
        # Position of this skeleton instance in world space (root bone origin).
        self.x = 0.0
        self.y = 0.0
        self.scale_x = 1.0
        self.scale_y = 1.0

        # ── bones ────────────────────────────────────────────────────────
        self.bone_data: List[BoneData] = []
        bone_data_by_name: Dict[str, BoneData] = {}
        for i, bd in enumerate(data.get("bones", [])):
            parent = bone_data_by_name.get(bd.get("parent"))
            b = BoneData(i, bd, parent)
            self.bone_data.append(b)
            bone_data_by_name[b.name] = b

        self.bones: List[Bone] = []
        self.bones_by_name: Dict[str, Bone] = {}
        for bd in self.bone_data:
            parent = self.bones_by_name.get(bd.parent.name) if bd.parent else None
            bone = Bone(bd, self, parent)
            if parent:
                parent.children.append(bone)
            self.bones.append(bone)
            self.bones_by_name[bone.name] = bone

        # ── slots ────────────────────────────────────────────────────────
        self.slots: List[Slot] = []
        self.slots_by_name: Dict[str, Slot] = {}
        for i, sd in enumerate(data.get("slots", [])):
            sdata = SlotData(i, sd)
            slot = Slot(sdata, self.bones_by_name[sdata.bone_name], self)
            self.slots.append(slot)
            self.slots_by_name[slot.name] = slot
        # Draw order is a permutation of slot indices; animations may reorder it.
        self.draw_order: List[int] = list(range(len(self.slots)))

        # ── skins ────────────────────────────────────────────────────────
        self.skins: List[Skin] = []
        self.skins_by_name: Dict[str, Skin] = {}
        for skin_data in data.get("skins", []):
            skin = Skin(skin_data.get("name", "default"))
            for slot_name, atts in skin_data.get("attachments", {}).items():
                for att_name, att_dict in atts.items():
                    att = create_attachment(att_name, att_dict)
                    if att is not None:
                        skin.add(slot_name, att_name, att)
            self.skins.append(skin)
            self.skins_by_name[skin.name] = skin

        self.default_skin = self.skins_by_name.get("default")
        self.skin: Optional[Skin] = self.default_skin

        self._resolve_linked_meshes()

        # Constraints are attached by the loader (they need the skeleton to exist).
        self.ik_constraints = []
        self.transform_constraints = []
        self._update_cache: List = []

    # ── skins / attachments ──────────────────────────────────────────────

    def set_skin(self, skin_name: Optional[str]):
        if skin_name is None:
            self.skin = self.default_skin
        else:
            self.skin = self.skins_by_name.get(skin_name, self.default_skin)

    def get_attachment(self, slot_name: str, attachment_name: str) -> Optional[Attachment]:
        if self.skin is not None:
            att = self.skin.get(slot_name, attachment_name)
            if att is not None:
                return att
        if self.default_skin is not None and self.default_skin is not self.skin:
            return self.default_skin.get(slot_name, attachment_name)
        return None

    def _resolve_linked_meshes(self):
        for skin in self.skins:
            for slot_name, atts in skin.attachments.items():
                for att in atts.values():
                    parent_name = getattr(att, "link_parent", None)
                    if not parent_name:
                        continue
                    source_skin_name = getattr(att, "link_skin", None)
                    source_skin = (self.skins_by_name.get(source_skin_name)
                                   if source_skin_name else None) or self.default_skin or skin
                    parent = source_skin.get(slot_name, parent_name)
                    if parent is None:
                        # Fall back to scanning every skin for the parent mesh.
                        for s in self.skins:
                            parent = s.get(slot_name, parent_name)
                            if parent is not None:
                                break
                    if parent is not None:
                        att.link_from(parent, getattr(att, "link_deform", True))

    # ── pose ─────────────────────────────────────────────────────────────

    def set_to_setup_pose(self):
        for bone in self.bones:
            bone.set_to_setup_pose()
        for slot in self.slots:
            slot.set_to_setup_pose()
        self.draw_order = list(range(len(self.slots)))
        for c in self.ik_constraints:
            c.set_to_setup_pose()
        for c in self.transform_constraints:
            c.set_to_setup_pose()

    # ── update cache (bones interleaved with constraints) ────────────────

    def update_cache(self):
        cache: List = []
        for bone in self.bones:
            bone.sorted = False
            bone.active = True

        constraints = sorted(
            [(c.data.order, i, c) for i, c in
             enumerate(list(self.ik_constraints) + list(self.transform_constraints))]
        )
        for _, _, c in constraints:
            c.sort(cache)

        for bone in self.bones:
            _sort_bone(bone, cache)

        self._update_cache = cache

    def update_world_transform(self):
        if not self._update_cache:
            self.update_cache()
        for item in self._update_cache:
            item.update()


def _sort_bone(bone: Bone, cache: List):
    if bone.sorted:
        return
    if bone.parent is not None:
        _sort_bone(bone.parent, cache)
    bone.sorted = True
    cache.append(_BoneUpdate(bone))


def _sort_reset(children: List[Bone], cache: List):
    for child in children:
        if not child.active:
            continue
        if child.sorted:
            _sort_reset(child.children, cache)
        child.sorted = False


class _BoneUpdate:
    """Adapter so bones and constraints share one `update()` interface in the cache."""
    __slots__ = ("bone",)

    def __init__(self, bone: Bone):
        self.bone = bone

    def update(self):
        self.bone.update_world_transform()


def _parse_color(hex_str: str):
    h = hex_str.lstrip("#")
    if len(h) == 6:
        h += "ff"
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4, 6)]
