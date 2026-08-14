"""IK and transform constraints (Spine 4.1 semantics).

Only the modes these projects use are fully implemented: one- and two-bone IK
(with stretch/compress/softness) and world-space absolute transform constraints.
Local/relative transform constraints fall back to the absolute path.
"""
import math
from typing import List

from .skeleton import Bone, _sort_bone, _sort_reset

DEG_RAD = math.pi / 180.0
RAD_DEG = 180.0 / math.pi
PI = math.pi
PI2 = math.pi * 2


# ─────────────────────────────── IK ───────────────────────────────

class IkConstraintData:
    __slots__ = ("name", "order", "skin_required", "bone_names", "target_name",
                 "bend_direction", "compress", "stretch", "uniform", "mix", "softness")

    def __init__(self, data: dict):
        self.name = data["name"]
        self.order = data.get("order", 0)
        self.skin_required = data.get("skin", False)
        self.bone_names = data.get("bones", [])
        self.target_name = data.get("target")
        self.bend_direction = 1 if data.get("bendPositive", True) else -1
        self.compress = data.get("compress", False)
        self.stretch = data.get("stretch", False)
        self.uniform = data.get("uniform", False)
        self.mix = data.get("mix", 1.0)
        self.softness = data.get("softness", 0.0)


class IkConstraint:
    def __init__(self, data: IkConstraintData, skeleton):
        self.data = data
        self.skeleton = skeleton
        self.bones: List[Bone] = [skeleton.bones_by_name[n] for n in data.bone_names]
        self.target: Bone = skeleton.bones_by_name[data.target_name]
        self.active = True
        self.set_to_setup_pose()

    def set_to_setup_pose(self):
        d = self.data
        self.bend_direction = d.bend_direction
        self.compress = d.compress
        self.stretch = d.stretch
        self.mix = d.mix
        self.softness = d.softness

    def sort(self, cache: List):
        _sort_bone(self.target, cache)
        parent = self.bones[0]
        _sort_bone(parent, cache)
        if len(self.bones) == 1:
            cache.append(self)
            _sort_reset(parent.children, cache)
        else:
            child = self.bones[-1]
            _sort_bone(child, cache)
            cache.append(self)
            _sort_reset(parent.children, cache)
            child.sorted = True

    def update(self):
        if self.mix == 0:
            return
        target = self.target
        if len(self.bones) == 1:
            apply_ik1(self.bones[0], target.world_x, target.world_y,
                      self.compress, self.stretch, self.data.uniform, self.mix)
        else:
            apply_ik2(self.bones[0], self.bones[1], target.world_x, target.world_y,
                      self.bend_direction, self.stretch, self.data.uniform,
                      self.softness, self.mix)


def apply_ik1(bone: Bone, target_x, target_y, compress, stretch, uniform, alpha):
    p = bone.parent
    if p is None:
        return
    pa, pb, pc, pd = p.a, p.b, p.c, p.d
    rotation_ik = -bone.ashear_x - bone.arotation
    inherit = bone.data.inherit

    if inherit == "onlyTranslation":
        tx = target_x - bone.world_x
        ty = target_y - bone.world_y
    else:
        if inherit == "noRotationOrReflection":
            s = abs(pa * pd - pb * pc) / max(pa * pa + pc * pc, 1e-9)
            sa = pa / bone.skeleton.scale_x
            sc = pc / bone.skeleton.scale_y
            pb = -sc * s * bone.skeleton.scale_x
            pd = sa * s * bone.skeleton.scale_y
            rotation_ik += math.atan2(sc, sa) * RAD_DEG
        x = target_x - p.world_x
        y = target_y - p.world_y
        det = pa * pd - pb * pc
        if abs(det) <= 0.0001:
            tx = ty = 0.0
        else:
            tx = (x * pd - y * pb) / det - bone.ax
            ty = (y * pa - x * pc) / det - bone.ay

    rotation_ik += math.atan2(ty, tx) * RAD_DEG
    if bone.ascale_x < 0:
        rotation_ik += 180
    if rotation_ik > 180:
        rotation_ik -= 360
    elif rotation_ik < -180:
        rotation_ik += 360

    sx, sy = bone.ascale_x, bone.ascale_y
    if compress or stretch:
        if bone.data.inherit in ("noScale", "noScaleOrReflection"):
            tx = target_x - bone.world_x
            ty = target_y - bone.world_y
        b = bone.data.length * sx
        dd = math.sqrt(tx * tx + ty * ty)
        if b > 0.0001 and ((compress and dd < b) or (stretch and dd > b)):
            s = (dd / b - 1) * alpha + 1
            sx *= s
            if uniform:
                sy *= s
    bone.update_world_transform_with(bone.ax, bone.ay, bone.arotation + rotation_ik * alpha,
                                     sx, sy, bone.ashear_x, bone.ashear_y)


def apply_ik2(parent: Bone, child: Bone, target_x, target_y, bend_dir, stretch, uniform,
              softness, alpha):
    px, py = parent.ax, parent.ay
    psx, psy = parent.ascale_x, parent.ascale_y
    sx, sy = psx, psy
    cx, cy = child.ax, child.ay
    csx = child.ascale_x

    if psx < 0:
        psx = -psx
        os1 = 180.0
        s2 = -1
    else:
        os1 = 0.0
        s2 = 1
    if psy < 0:
        psy = -psy
        s2 = -s2
    if csx < 0:
        csx = -csx
        os2 = 180.0
    else:
        os2 = 0.0

    a, b, c, d = parent.a, parent.b, parent.c, parent.d
    u = abs(psx - psy) <= 0.0001
    if not u or stretch:
        cy = 0.0
        cwx = a * cx + parent.world_x
        cwy = c * cx + parent.world_y
    else:
        cwx = a * cx + b * cy + parent.world_x
        cwy = c * cx + d * cy + parent.world_y

    pp = parent.parent
    if pp is None:
        return
    a, b, c, d = pp.a, pp.b, pp.c, pp.d
    det = a * d - b * c
    x = cwx - pp.world_x
    y = cwy - pp.world_y
    inv = 0.0 if abs(det) <= 0.0001 else 1.0 / det
    dx = (x * d - y * b) * inv - px
    dy = (y * a - x * c) * inv - py
    l1 = math.sqrt(dx * dx + dy * dy)
    l2 = child.data.length * csx

    if l1 < 0.0001:
        apply_ik1(parent, target_x, target_y, False, stretch, False, alpha)
        child.update_world_transform_with(cx, cy, 0, child.ascale_x, child.ascale_y,
                                          child.ashear_x, child.ashear_y)
        return

    x = target_x - pp.world_x
    y = target_y - pp.world_y
    tx = (x * d - y * b) * inv - px
    ty = (y * a - x * c) * inv - py
    dd = tx * tx + ty * ty

    if softness != 0:
        softness *= psx * (csx + 1) * 0.5
        td = math.sqrt(dd)
        sd = td - l1 - l2 * psx + softness
        if sd > 0:
            p = min(1.0, sd / (softness * 2)) - 1
            p = (sd - softness * (1 - p * p)) / td if td != 0 else 0.0
            tx -= p * tx
            ty -= p * ty
            dd = tx * tx + ty * ty

    a1 = a2 = 0.0
    solved = False
    if u:
        l2 *= psx
        denom = 2 * l1 * l2
        cos = (dd - l1 * l1 - l2 * l2) / denom if denom != 0 else -1.0
        if cos < -1:
            cos = -1.0
            a2 = PI * bend_dir
        elif cos > 1:
            cos = 1.0
            a2 = 0.0
            if stretch:
                sqdd = math.sqrt(dd)
                s = (sqdd / (l1 + l2) - 1) * alpha + 1 if (l1 + l2) != 0 else 1.0
                sx *= s
                if uniform:
                    sy *= s
        else:
            a2 = math.acos(cos) * bend_dir
        aa = l1 + l2 * cos
        bb = l2 * math.sin(a2)
        a1 = math.atan2(ty * aa - tx * bb, tx * aa + ty * bb)
    else:
        aa = psx * l2
        bb = psy * l2
        a_sq, b_sq = aa * aa, bb * bb
        ta = math.atan2(ty, tx)
        cc = b_sq * l1 * l1 + a_sq * dd - a_sq * b_sq
        c1 = -2 * b_sq * l1
        c2 = b_sq - a_sq
        dsc = c1 * c1 - 4 * c2 * cc
        if dsc >= 0:
            q = math.sqrt(dsc)
            if c1 < 0:
                q = -q
            q = -(c1 + q) * 0.5
            r0 = q / c2 if c2 != 0 else 0.0
            r1 = cc / q if q != 0 else 0.0
            r = r0 if abs(r0) < abs(r1) else r1
            if r * r <= dd:
                yy = math.sqrt(max(dd - r * r, 0.0)) * bend_dir
                a1 = ta - math.atan2(yy, r)
                a2 = math.atan2(yy / psy, (r - l1) / psx)
                solved = True
        if not solved:
            min_angle, max_angle = PI, 0.0
            min_x = l1 - aa
            min_dist = min_x * min_x
            min_y = 0.0
            max_x = l1 + aa
            max_dist = max_x * max_x
            max_y = 0.0
            denom = a_sq - b_sq
            cc = -aa * l1 / denom if denom != 0 else 2.0
            if -1 <= cc <= 1:
                cc = math.acos(cc)
                xx = aa * math.cos(cc) + l1
                yy = bb * math.sin(cc)
                dsq = xx * xx + yy * yy
                if dsq < min_dist:
                    min_angle, min_dist, min_x, min_y = cc, dsq, xx, yy
                if dsq > max_dist:
                    max_angle, max_dist, max_x, max_y = cc, dsq, xx, yy
            if dd <= (min_dist + max_dist) / 2:
                a1 = ta - math.atan2(min_y * bend_dir, min_x)
                a2 = min_angle * bend_dir
            else:
                a1 = ta - math.atan2(max_y * bend_dir, max_x)
                a2 = max_angle * bend_dir

    os = math.atan2(cy, cx) * s2
    rotation = parent.arotation
    a1 = (a1 - os) * RAD_DEG + os1 - rotation
    if a1 > 180:
        a1 -= 360
    elif a1 < -180:
        a1 += 360
    parent.update_world_transform_with(px, py, rotation + a1 * alpha, sx, sy, 0, 0)

    rotation = child.arotation
    a2 = ((a2 + os) * RAD_DEG - child.ashear_x) * s2 + os2 - rotation
    if a2 > 180:
        a2 -= 360
    elif a2 < -180:
        a2 += 360
    child.update_world_transform_with(cx, cy, rotation + a2 * alpha, child.ascale_x,
                                      child.ascale_y, child.ashear_x, child.ashear_y)


# ────────────────────────── Transform ──────────────────────────

class TransformConstraintData:
    __slots__ = ("name", "order", "bone_names", "target_name", "local", "relative",
                 "offset_rotation", "offset_x", "offset_y", "offset_scale_x",
                 "offset_scale_y", "offset_shear_y",
                 "mix_rotate", "mix_x", "mix_y", "mix_scale_x", "mix_scale_y", "mix_shear_y")

    def __init__(self, data: dict):
        self.name = data["name"]
        self.order = data.get("order", 0)
        self.bone_names = data.get("bones", [])
        self.target_name = data.get("target")
        self.local = data.get("local", False)
        self.relative = data.get("relative", False)
        self.offset_rotation = data.get("rotation", 0.0)
        self.offset_x = data.get("x", 0.0)
        self.offset_y = data.get("y", 0.0)
        self.offset_scale_x = data.get("scaleX", 0.0)
        self.offset_scale_y = data.get("scaleY", 0.0)
        self.offset_shear_y = data.get("shearY", 0.0)
        self.mix_rotate = data.get("mixRotate", data.get("rotateMix", 1.0))
        # Spine writes mixX and lets mixY default to it.
        self.mix_x = data.get("mixX", data.get("translateMix", 1.0))
        self.mix_y = data.get("mixY", self.mix_x)
        self.mix_scale_x = data.get("mixScaleX", data.get("scaleMix", 1.0))
        self.mix_scale_y = data.get("mixScaleY", self.mix_scale_x)
        self.mix_shear_y = data.get("mixShearY", data.get("shearMix", 1.0))


class TransformConstraint:
    def __init__(self, data: TransformConstraintData, skeleton):
        self.data = data
        self.skeleton = skeleton
        self.bones: List[Bone] = [skeleton.bones_by_name[n] for n in data.bone_names
                                  if n in skeleton.bones_by_name]
        self.target: Bone = skeleton.bones_by_name[data.target_name]
        self.active = True
        self.set_to_setup_pose()

    def set_to_setup_pose(self):
        d = self.data
        self.mix_rotate = d.mix_rotate
        self.mix_x = d.mix_x
        self.mix_y = d.mix_y
        self.mix_scale_x = d.mix_scale_x
        self.mix_scale_y = d.mix_scale_y
        self.mix_shear_y = d.mix_shear_y

    def sort(self, cache: List):
        _sort_bone(self.target, cache)
        for bone in self.bones:
            _sort_bone(bone, cache)
        cache.append(self)
        for bone in self.bones:
            _sort_reset(bone.children, cache)
            bone.sorted = True

    def update(self):
        if (self.mix_rotate == 0 and self.mix_x == 0 and self.mix_y == 0
                and self.mix_scale_x == 0 and self.mix_scale_y == 0 and self.mix_shear_y == 0):
            return
        self._apply_absolute_world()

    def _apply_absolute_world(self):
        d = self.data
        mix_rotate, mix_x, mix_y = self.mix_rotate, self.mix_x, self.mix_y
        mix_scale_x, mix_scale_y, mix_shear_y = self.mix_scale_x, self.mix_scale_y, self.mix_shear_y
        translate = mix_x != 0 or mix_y != 0

        target = self.target
        ta, tb, tc, td = target.a, target.b, target.c, target.d
        deg_rad_reflect = DEG_RAD if (ta * td - tb * tc > 0) else -DEG_RAD
        offset_rotation = d.offset_rotation * deg_rad_reflect
        offset_shear_y = d.offset_shear_y * deg_rad_reflect

        for bone in self.bones:
            if mix_rotate != 0:
                a, b, c, dd = bone.a, bone.b, bone.c, bone.d
                r = math.atan2(tc, ta) - math.atan2(c, a) + offset_rotation
                if r > PI:
                    r -= PI2
                elif r < -PI:
                    r += PI2
                r *= mix_rotate
                cos, sin = math.cos(r), math.sin(r)
                bone.a = cos * a - sin * c
                bone.b = cos * b - sin * dd
                bone.c = sin * a + cos * c
                bone.d = sin * b + cos * dd

            if translate:
                wx, wy = target.local_to_world(d.offset_x, d.offset_y)
                bone.world_x += (wx - bone.world_x) * mix_x
                bone.world_y += (wy - bone.world_y) * mix_y

            if mix_scale_x != 0:
                s = math.sqrt(bone.a * bone.a + bone.c * bone.c)
                if s != 0:
                    s = (s + (math.sqrt(ta * ta + tc * tc) - s + d.offset_scale_x) * mix_scale_x) / s
                bone.a *= s
                bone.c *= s
            if mix_scale_y != 0:
                s = math.sqrt(bone.b * bone.b + bone.d * bone.d)
                if s != 0:
                    s = (s + (math.sqrt(tb * tb + td * td) - s + d.offset_scale_y) * mix_scale_y) / s
                bone.b *= s
                bone.d *= s

            if mix_shear_y > 0:
                b, dd = bone.b, bone.d
                by = math.atan2(dd, b)
                r = (math.atan2(td, tb) - math.atan2(tc, ta)
                     - (by - math.atan2(bone.c, bone.a)))
                if r > PI:
                    r -= PI2
                elif r < -PI:
                    r += PI2
                r = by + (r + offset_shear_y) * mix_shear_y
                s = math.sqrt(b * b + dd * dd)
                bone.b = math.cos(r) * s
                bone.d = math.sin(r) * s

            bone.update_applied_transform()
