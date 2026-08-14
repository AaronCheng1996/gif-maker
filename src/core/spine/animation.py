"""Animation timelines and curve evaluation (Spine 4.1 JSON format).

Keyframe curves come in three flavours: linear (no `curve` key), `"stepped"`,
and a cubic Bezier given as absolute control points. For timelines carrying
several properties (translate has x and y, rgba has r/g/b/a) the `curve` array
holds four numbers per property, in property order.

Bezier curves are sampled once at load time into the same 10 segments the
official runtime uses, so playback matches Spine's own interpolation.
"""
import math
from typing import Dict, List, Optional, Sequence

BEZIER_SEGMENTS = 10


class _Curve:
    """Interpolator between one keyframe and the next, for a single property."""
    __slots__ = ("kind", "xs", "ys")

    LINEAR = 0
    STEPPED = 1
    BEZIER = 2

    def __init__(self, kind, xs=None, ys=None):
        self.kind = kind
        self.xs = xs
        self.ys = ys

    @classmethod
    def linear(cls):
        return cls(cls.LINEAR)

    @classmethod
    def stepped(cls):
        return cls(cls.STEPPED)

    @classmethod
    def bezier(cls, t1, v1, cx1, cy1, cx2, cy2, t2, v2):
        xs = [t1]
        ys = [v1]
        for i in range(1, BEZIER_SEGMENTS):
            t = i / BEZIER_SEGMENTS
            u = 1 - t
            uu, tt = u * u, t * t
            b0 = uu * u
            b1 = 3 * uu * t
            b2 = 3 * u * tt
            b3 = tt * t
            xs.append(b0 * t1 + b1 * cx1 + b2 * cx2 + b3 * t2)
            ys.append(b0 * v1 + b1 * cy1 + b2 * cy2 + b3 * v2)
        xs.append(t2)
        ys.append(v2)
        return cls(cls.BEZIER, xs, ys)

    def apply(self, time, t1, v1, t2, v2):
        if self.kind == _Curve.STEPPED:
            return v1
        if self.kind == _Curve.LINEAR:
            span = t2 - t1
            if span <= 0:
                return v1
            return v1 + (v2 - v1) * ((time - t1) / span)
        xs, ys = self.xs, self.ys
        # Samples are monotonic in x; find the bracketing pair.
        for i in range(1, len(xs)):
            if xs[i] >= time:
                x0, y0 = xs[i - 1], ys[i - 1]
                span = xs[i] - x0
                if span <= 0:
                    return y0
                return y0 + (ys[i] - y0) * ((time - x0) / span)
        return ys[-1]


class PropertyTimeline:
    """Keyframes for one or more numeric properties that share times and curves."""

    def __init__(self, keys: Sequence[dict], props: Sequence[str], defaults: Dict[str, float],
                 aliases: Optional[Dict[str, Sequence[str]]] = None):
        self.props = list(props)
        self.times: List[float] = []
        self.values: Dict[str, List[float]] = {p: [] for p in self.props}
        raw_curves: List[Optional[object]] = []

        for k in keys:
            self.times.append(float(k.get("time", 0.0)))
            for p in self.props:
                v = k.get(p)
                if v is None and aliases and p in aliases:
                    for alt in aliases[p]:
                        if alt in k:
                            v = k[alt]
                            break
                if v is None:
                    v = defaults[p]
                self.values[p].append(float(v))
            raw_curves.append(k.get("curve"))

        # Build one interpolator per (keyframe, property).
        self.curves: List[List[_Curve]] = []
        for i, raw in enumerate(raw_curves):
            per_prop: List[_Curve] = []
            has_next = i + 1 < len(self.times)
            for pi, p in enumerate(self.props):
                if raw is None or not has_next:
                    per_prop.append(_Curve.linear())
                elif raw == "stepped":
                    per_prop.append(_Curve.stepped())
                else:
                    off = pi * 4
                    if isinstance(raw, (list, tuple)) and len(raw) >= off + 4:
                        cx1, cy1, cx2, cy2 = raw[off:off + 4]
                        per_prop.append(_Curve.bezier(
                            self.times[i], self.values[p][i],
                            float(cx1), float(cy1), float(cx2), float(cy2),
                            self.times[i + 1], self.values[p][i + 1]))
                    else:
                        per_prop.append(_Curve.linear())
            self.curves.append(per_prop)

    @property
    def duration(self) -> float:
        return self.times[-1] if self.times else 0.0

    def value_at(self, time: float, prop: str) -> float:
        times = self.times
        vals = self.values[prop]
        if not times:
            return 0.0
        if time <= times[0]:
            return vals[0]
        if time >= times[-1]:
            return vals[-1]
        i = _search(times, time)
        pi = self.props.index(prop)
        return self.curves[i][pi].apply(time, times[i], vals[i], times[i + 1], vals[i + 1])

    def values_at(self, time: float) -> Dict[str, float]:
        return {p: self.value_at(time, p) for p in self.props}


class AttachmentTimeline:
    def __init__(self, keys: Sequence[dict]):
        self.times = [float(k.get("time", 0.0)) for k in keys]
        self.names = [k.get("name") for k in keys]

    @property
    def duration(self):
        return self.times[-1] if self.times else 0.0

    def value_at(self, time: float):
        if not self.times or time < self.times[0]:
            return None
        if time >= self.times[-1]:
            return self.names[-1]
        return self.names[_search(self.times, time)]


class DrawOrderTimeline:
    def __init__(self, keys: Sequence[dict]):
        self.times = [float(k.get("time", 0.0)) for k in keys]
        self.offsets = [k.get("offsets", []) for k in keys]

    @property
    def duration(self):
        return self.times[-1] if self.times else 0.0

    def value_at(self, time: float):
        if not self.times or time < self.times[0]:
            return None
        if time >= self.times[-1]:
            return self.offsets[-1]
        return self.offsets[_search(self.times, time)]


class Animation:
    """One named animation: all timelines plus the logic to pose a skeleton."""

    def __init__(self, name: str, data: dict, skeleton):
        self.name = name
        self.raw = data
        self.bone_timelines: Dict[str, Dict[str, PropertyTimeline]] = {}
        self.slot_property_timelines: Dict[str, Dict[str, PropertyTimeline]] = {}
        self.slot_attachment_timelines: Dict[str, AttachmentTimeline] = {}
        self.ik_timelines: Dict[str, PropertyTimeline] = {}
        self.transform_timelines: Dict[str, PropertyTimeline] = {}
        self.draw_order_timeline: Optional[DrawOrderTimeline] = None

        for bone_name, timelines in data.get("bones", {}).items():
            per_bone: Dict[str, PropertyTimeline] = {}
            for ttype, keys in timelines.items():
                if not keys:
                    continue
                if ttype == "rotate":
                    per_bone[ttype] = PropertyTimeline(keys, ["value"], {"value": 0.0})
                elif ttype in ("translate", "shear"):
                    per_bone[ttype] = PropertyTimeline(keys, ["x", "y"], {"x": 0.0, "y": 0.0})
                elif ttype == "scale":
                    per_bone[ttype] = PropertyTimeline(keys, ["x", "y"], {"x": 1.0, "y": 1.0})
                elif ttype in ("translatex", "translatey", "scalex", "scaley",
                               "shearx", "sheary"):
                    default = 1.0 if ttype.startswith("scale") else 0.0
                    per_bone[ttype] = PropertyTimeline(keys, ["value"], {"value": default})
            if per_bone:
                self.bone_timelines[bone_name] = per_bone

        for slot_name, timelines in data.get("slots", {}).items():
            per_slot: Dict[str, PropertyTimeline] = {}
            for ttype, keys in timelines.items():
                if not keys:
                    continue
                if ttype == "attachment":
                    self.slot_attachment_timelines[slot_name] = AttachmentTimeline(keys)
                elif ttype in ("rgba", "rgb", "rgba2", "rgb2"):
                    expanded = [_expand_color_key(k, ttype) for k in keys]
                    props = ["r", "g", "b"] + (["a"] if ttype in ("rgba", "rgba2") else [])
                    per_slot[ttype] = PropertyTimeline(
                        expanded, props, {p: 1.0 for p in props})
                elif ttype == "alpha":
                    per_slot[ttype] = PropertyTimeline(keys, ["value"], {"value": 1.0})
            if per_slot:
                self.slot_property_timelines[slot_name] = per_slot

        for ik_name, keys in data.get("ik", {}).items():
            if keys:
                self.ik_timelines[ik_name] = PropertyTimeline(
                    keys, ["mix", "softness"], {"mix": 1.0, "softness": 0.0})
                # bendPositive/compress/stepped flags are stepped booleans.
                self.ik_timelines[ik_name].flags = [
                    {"bendPositive": k.get("bendPositive", True),
                     "compress": k.get("compress", False),
                     "stretch": k.get("stretch", False)} for k in keys]

        for tc_name, keys in data.get("transform", {}).items():
            if keys:
                props = ["mixRotate", "mixX", "mixY", "mixScaleX", "mixScaleY", "mixShearY"]
                self.transform_timelines[tc_name] = PropertyTimeline(
                    keys, props, {p: 1.0 for p in props},
                    aliases={"mixY": ["mixX"], "mixScaleY": ["mixScaleX"]})

        draw_order = data.get("drawOrder")
        if draw_order:
            self.draw_order_timeline = DrawOrderTimeline(draw_order)

        self.duration = self._compute_duration()

    def _compute_duration(self) -> float:
        d = 0.0
        for per_bone in self.bone_timelines.values():
            for tl in per_bone.values():
                d = max(d, tl.duration)
        for per_slot in self.slot_property_timelines.values():
            for tl in per_slot.values():
                d = max(d, tl.duration)
        for tl in self.slot_attachment_timelines.values():
            d = max(d, tl.duration)
        for tl in self.ik_timelines.values():
            d = max(d, tl.duration)
        for tl in self.transform_timelines.values():
            d = max(d, tl.duration)
        if self.draw_order_timeline:
            d = max(d, self.draw_order_timeline.duration)
        return d

    # ── posing ───────────────────────────────────────────────────────────

    def apply(self, skeleton, time: float):
        """Pose `skeleton` at `time`. Assumes the skeleton is at its setup pose."""
        for bone_name, timelines in self.bone_timelines.items():
            bone = skeleton.bones_by_name.get(bone_name)
            if bone is None:
                continue
            d = bone.data
            for ttype, tl in timelines.items():
                if ttype == "rotate":
                    bone.rotation = d.rotation + tl.value_at(time, "value")
                elif ttype == "translate":
                    v = tl.values_at(time)
                    bone.x = d.x + v["x"]
                    bone.y = d.y + v["y"]
                elif ttype == "scale":
                    v = tl.values_at(time)
                    bone.scale_x = d.scale_x * v["x"]
                    bone.scale_y = d.scale_y * v["y"]
                elif ttype == "shear":
                    v = tl.values_at(time)
                    bone.shear_x = d.shear_x + v["x"]
                    bone.shear_y = d.shear_y + v["y"]
                elif ttype == "translatex":
                    bone.x = d.x + tl.value_at(time, "value")
                elif ttype == "translatey":
                    bone.y = d.y + tl.value_at(time, "value")
                elif ttype == "scalex":
                    bone.scale_x = d.scale_x * tl.value_at(time, "value")
                elif ttype == "scaley":
                    bone.scale_y = d.scale_y * tl.value_at(time, "value")
                elif ttype == "shearx":
                    bone.shear_x = d.shear_x + tl.value_at(time, "value")
                elif ttype == "sheary":
                    bone.shear_y = d.shear_y + tl.value_at(time, "value")

        for slot_name, timelines in self.slot_property_timelines.items():
            slot = skeleton.slots_by_name.get(slot_name)
            if slot is None:
                continue
            for ttype, tl in timelines.items():
                if ttype == "rgba":
                    v = tl.values_at(time)
                    slot.color = [v["r"], v["g"], v["b"], v["a"]]
                elif ttype == "rgb":
                    v = tl.values_at(time)
                    slot.color = [v["r"], v["g"], v["b"], slot.color[3]]
                elif ttype == "alpha":
                    slot.color[3] = tl.value_at(time, "value")

        for slot_name, tl in self.slot_attachment_timelines.items():
            slot = skeleton.slots_by_name.get(slot_name)
            if slot is None:
                continue
            name = tl.value_at(time)
            if name is not None or tl.times:
                slot.attachment_name = name

        for ik_name, tl in self.ik_timelines.items():
            c = _find_by_name(skeleton.ik_constraints, ik_name)
            if c is None:
                continue
            v = tl.values_at(time)
            c.mix = v["mix"]
            c.softness = v["softness"]
            flags = getattr(tl, "flags", None)
            if flags:
                idx = 0 if time <= tl.times[0] else (
                    len(tl.times) - 1 if time >= tl.times[-1] else _search(tl.times, time))
                f = flags[idx]
                c.bend_direction = 1 if f["bendPositive"] else -1
                c.compress = f["compress"]
                c.stretch = f["stretch"]

        for tc_name, tl in self.transform_timelines.items():
            c = _find_by_name(skeleton.transform_constraints, tc_name)
            if c is None:
                continue
            v = tl.values_at(time)
            c.mix_rotate = v["mixRotate"]
            c.mix_x = v["mixX"]
            c.mix_y = v["mixY"]
            c.mix_scale_x = v["mixScaleX"]
            c.mix_scale_y = v["mixScaleY"]
            c.mix_shear_y = v["mixShearY"]

        if self.draw_order_timeline is not None:
            offsets = self.draw_order_timeline.value_at(time)
            skeleton.draw_order = _apply_draw_order(skeleton, offsets)


def _apply_draw_order(skeleton, offsets) -> List[int]:
    n = len(skeleton.slots)
    if not offsets:
        return list(range(n))
    # Spine: shift the listed slots to their new positions, then fill the gaps
    # with the remaining slots in their original order.
    unchanged: List[int] = []
    new_order: List[Optional[int]] = [None] * n
    taken = set()
    for entry in offsets:
        slot = skeleton.slots_by_name.get(entry.get("slot"))
        if slot is None:
            continue
        idx = slot.data.index
        new_order[idx + entry.get("offset", 0)] = idx
        taken.add(idx)
    for i in range(n):
        if i not in taken:
            unchanged.append(i)
    it = iter(unchanged)
    for i in range(n):
        if new_order[i] is None:
            new_order[i] = next(it, i)
    return [i for i in new_order if i is not None]


def _expand_color_key(key: dict, ttype: str) -> dict:
    """Turn {"color": "rrggbbaa"} into separate r/g/b/a entries."""
    field = "dark" if ttype.endswith("2") else "color"
    hex_str = key.get(field, "ffffffff")
    h = hex_str.lstrip("#")
    if len(h) == 6:
        h += "ff"
    out = dict(key)
    out["r"] = int(h[0:2], 16) / 255.0
    out["g"] = int(h[2:4], 16) / 255.0
    out["b"] = int(h[4:6], 16) / 255.0
    out["a"] = int(h[6:8], 16) / 255.0
    return out


def _find_by_name(items, name):
    for it in items:
        if it.data.name == name:
            return it
    return None


def _search(times: Sequence[float], time: float) -> int:
    """Index of the last keyframe whose time is <= `time` (times is sorted)."""
    lo, hi = 0, len(times) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if times[mid] <= time:
            lo = mid
        else:
            hi = mid - 1
    return lo
