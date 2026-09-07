"""
Group Composition Widget - Group-led composition editor

Collapsible group tree with:
- Click anywhere on a group header to select it (Preview / Export target)
- A group's frames are shown in its own top-level section; nested references are
  single header rows exposing loop-count, x, y offset, and a jump to that section
- Group headers carry both the default frame duration and the last frame's, which
  is the pause before the group loops; pinning that pause keeps it on whichever
  frame ends the group as materials are added
- A group can be bound to a material glob instead of to entries, so it holds as
  many frames as the current material set matches
- FrameEntry rows have large thumbnails (≈¼ of row width)
- LayerBlock timelines show slot rows with full x/y editing
"""

import copy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSpinBox, QInputDialog, QMessageBox,
    QLineEdit, QSizePolicy, QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QImage, QCursor
from typing import Optional, Callable, List
from PIL import Image

from ..core.composition_group import (
    CompositionGroup, FrameEntry, SubGroupEntry, LayerBlockEntry,
    FrameSlot, GroupSlot,
    is_frame_entry, is_sub_group_entry, is_layer_block_entry,
    is_frame_slot, is_group_slot,
    resolve_source_indices,
)
from .theme import AppTheme as _T

# Thumbnail dimensions (frame entries & layer-block slot rows)
_TW, _TH = 100, 70

# Width of a millisecond spinbox. Measured against the app stylesheet: below
# this the text is clipped, and a pause of "2000ms" reads back as "2000n".
_DUR_W = 106


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _pil_to_pixmap(img: Image.Image, w: int, h: int) -> Optional[QPixmap]:
    try:
        thumb = img.copy()
        thumb.thumbnail((w, h), Image.Resampling.LANCZOS)
        if thumb.mode != "RGBA":
            thumb = thumb.convert("RGBA")
        tw, th = thumb.size
        data = thumb.tobytes("raw", "RGBA")
        qimg = QImage(data, tw, th, tw * 4, QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(qimg)
    except Exception:
        return None


class _ClickableHeader(QFrame):
    """Header frame that emits clicked() for any click on the background."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _small_btn(text: str, color: str = _T.TEXT_DIM, width: int = 28) -> QPushButton:
    b = QPushButton(text)
    b.setFixedSize(width, 22)
    b.setStyleSheet(
        f"QPushButton {{ color: {color}; font-size: 11px; font-weight: bold; "
        f"background: {_T.BTN_BG}; border: 1px solid {_T.BTN_BORDER}; "
        f"border-radius: 3px; padding: 0 2px; }}"
        f"QPushButton:hover {{ background: {_T.BTN_HOVER}; border-color: {_T.BORDER_MID}; }}"
        f"QPushButton:pressed {{ background: {_T.BTN_PRESSED}; }}"
    )
    return b


def _lighten(hex_color: str, amount: int = 28) -> str:
    """Return a slightly lighter hex color for hover states."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{min(255, r + amount):02x}{min(255, g + amount):02x}{min(255, b + amount):02x}"


def _action_btn(label: str, bg: str) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(22)
    b.setStyleSheet(
        f"QPushButton {{ background: {bg}; color: {_T.TEXT}; border: none; "
        f"border-radius: 3px; padding: 0 8px; font-size: 11px; font-weight: bold; }}"
        f"QPushButton:hover {{ background: {_lighten(bg)}; }}"
        f"QPushButton:pressed {{ background: {bg}; }}"
    )
    return b


def _spinbox(lo: int, hi: int, val: int, suffix: str = "", w: int = 60) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setMaximumWidth(w)
    if suffix:
        s.setSuffix(suffix)
    return s


def _set_spin_quietly(spin: Optional[QSpinBox], value: int) -> None:
    """Move a spinbox to a value without firing its valueChanged handler.

    Two spinboxes can show the same duration (a frame row and the "last" box in
    its group header), and each has to follow the other without writing the
    model twice. The target may also belong to an already-rebuilt tree, whose
    C++ half is gone — touching that raises rather than returning None."""
    if spin is None:
        return
    try:
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)
    except RuntimeError:
        pass


def _lbl(text: str, style: str = f"color: {_T.TEXT_DIM}; font-size: 10px;") -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(style)
    return l


# ─── Main widget ─────────────────────────────────────────────────────────────

class GroupCompositionWidget(QWidget):
    """
    Collapsible tree editor for group-led composition.

    Public API (unchanged — main.py needs no edits):
      set_group_manager / set_material_manager / set_get_selected_material_indices
      get_current_group_id / set_current_group_id
      refresh_groups_list / refresh_entries_list
      signals: current_group_changed(int), entries_changed()
    """

    current_group_changed = pyqtSignal(int)
    entries_changed = pyqtSignal()
    frame_entry_selected = pyqtSignal(int, int)  # (parent_group_id, entry_idx)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._gm = None
        self._mm = None
        self._current_gid: Optional[int] = None
        self._get_sel_mat: Optional[Callable] = None
        self._collapsed: set = set()
        self._building = False
        self._selected_entry: Optional[tuple] = None  # (parent_group_id, entry_idx)
        # Live widget registries, rebuilt by refresh(). Editing a duration must
        # not rebuild the tree — that would delete the spinbox being typed into
        # — so the other view of the same number is moved directly instead.
        self._row_dur_spin: dict = {}    # (group_id, entry_idx) -> frame row's ⏱
        self._tail_spin: dict = {}       # group_id -> its header's "last" ⏱
        self._tail_chk: dict = {}        # group_id -> its header's "pin last" box
        self._bind_edit: dict = {}       # group_id -> its header's material-glob field
        self._top_sections: dict = {}    # group_id -> its top-level section widget
        self._pending_reveal: Optional[int] = None
        # Rebuilding the tree resets the scroll position, so it is put back once
        # the new widgets have been laid out. The timer is parented to self so
        # it dies with the widget: a bare QTimer.singleShot outlives it and the
        # callback then writes to a scrollbar whose C++ half is already gone.
        self._scroll_restore = QTimer(self)
        self._scroll_restore.setSingleShot(True)
        self._scroll_restore.timeout.connect(self._restore_scroll)
        self._pending_scroll = 0
        self._init_ui()

    def _restore_scroll(self):
        gid, self._pending_reveal = self._pending_reveal, None
        if gid is not None:
            section = self._top_sections.get(gid)
            if section is not None:
                try:
                    self._scroll.ensureWidgetVisible(section, 0, 40)
                    return
                except RuntimeError:
                    pass          # rebuilt again before this ran
        self._scroll.verticalScrollBar().setValue(self._pending_scroll)

    # ── Public setters ────────────────────────────────────────────────────────

    def set_group_manager(self, gm):
        self._gm = gm
        if gm and gm.get_root_group_id() is not None:
            self._current_gid = gm.get_root_group_id()
        self.refresh()
        if self._current_gid is not None:
            self.current_group_changed.emit(self._current_gid)

    def set_material_manager(self, mm):
        self._mm = mm

    def set_get_selected_material_indices(self, fn: Callable):
        self._get_sel_mat = fn

    def get_current_group_id(self) -> Optional[int]:
        return self._current_gid

    def set_current_group_id(self, gid: Optional[int]):
        self._current_gid = gid
        self.refresh()

    def set_selected_entry(self, parent_gid: Optional[int], entry_idx: Optional[int]):
        """Highlight the given FrameEntry row without emitting frame_entry_selected.

        Used to mirror a selection made elsewhere (e.g. the Canvas tab) onto the tree."""
        new_sel = (parent_gid, entry_idx) if parent_gid is not None and entry_idx is not None else None
        if new_sel == self._selected_entry:
            return
        self._selected_entry = new_sel
        self.refresh()

    def refresh_groups_list(self):
        self.refresh()

    def refresh_entries_list(self):
        self.refresh()

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._inner = QWidget()
        self._inner_layout = QVBoxLayout(self._inner)
        self._inner_layout.setContentsMargins(4, 4, 4, 4)
        self._inner_layout.setSpacing(6)
        self._inner_layout.addStretch()

        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll, stretch=1)

        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background: {_T.PANEL}; border-top: 1px solid {_T.BORDER}; }}"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(6, 4, 6, 4)
        new_btn = _action_btn("＋ New Group", _T.SUCCESS)
        new_btn.setToolTip(
            "Create a standalone group (shown as unlinked below root tree).\n"
            "Drag it into the tree via +Group in any group header."
        )
        new_btn.clicked.connect(self._cmd_new_group)
        bl.addWidget(new_btn)
        bl.addStretch()
        outer.addWidget(bar)

    # ── Rebuild ───────────────────────────────────────────────────────────────

    def refresh(self):
        if self._building:
            return
        self._building = True
        try:
            vbar = self._scroll.verticalScrollBar()
            pos = vbar.value()

            self._row_dur_spin.clear()
            self._tail_spin.clear()
            self._tail_chk.clear()
            self._bind_edit.clear()
            self._top_sections.clear()

            layout = self._inner_layout
            while layout.count() > 1:
                item = layout.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()

            if self._gm:
                root = self._gm.get_root_group_id()
                insert_at = 0

                if root is not None:
                    w = self._build_group_section(
                        root, depth=0, parent_gid=None, entry_idx=None, is_root=True
                    )
                    self._top_sections[root] = w
                    layout.insertWidget(insert_at, w)
                    insert_at += 1

                # Show ALL non-root groups so they are always directly editable
                non_root = [
                    i for i in range(len(self._gm.groups))
                    if i != root and self._gm.get_group(i) is not None
                ]
                if non_root:
                    sep = _lbl(
                        "── All Groups ──",
                        f"color: {_T.SEP_COLOR}; font-size: 10px; font-style: italic;"
                    )
                    sep.setContentsMargins(4, 8, 4, 2)
                    layout.insertWidget(insert_at, sep)
                    insert_at += 1
                    for gid in non_root:
                        w = self._build_group_section(
                            gid, depth=0, parent_gid=None, entry_idx=None, is_root=False
                        )
                        self._top_sections[gid] = w
                        layout.insertWidget(insert_at, w)
                        insert_at += 1

            self._pending_scroll = pos
            self._scroll_restore.start(0)
        finally:
            self._building = False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_referenced(self, gid: int) -> bool:
        """Return True if any group in the manager references this gid."""
        if not self._gm:
            return False
        for group in self._gm.groups:
            for entry in group.entries:
                if is_sub_group_entry(entry) and entry.group_id == gid:
                    return True
                if is_layer_block_entry(entry):
                    for tl in entry.timelines:
                        for slot in tl:
                            if is_group_slot(slot) and slot.group_id == gid:
                                return True
        return False

    def _reference_count(self, gid: int) -> int:
        """How many places in the tree point at this group.

        Sub-group entries share one group object rather than copying it, so
        emptying a group empties it everywhere it appears — worth saying out loud
        before doing it."""
        if not self._gm:
            return 0
        count = 0
        for group in self._gm.groups:
            for entry in group.entries:
                if is_sub_group_entry(entry) and entry.group_id == gid:
                    count += 1
                if is_layer_block_entry(entry):
                    for tl in entry.timelines:
                        for slot in tl:
                            if is_group_slot(slot) and slot.group_id == gid:
                                count += 1
        return count

    def _tail_frame_index(self, group: CompositionGroup) -> Optional[int]:
        """Index of the group's last entry when it is a frame, else None.

        That frame is the one held on screen just before the group loops, so it
        is the one people reach for when they want a pause. A group ending on a
        sub-group or a layer block has no such frame of its own: the timing
        lives in whatever it ends on."""
        if group.entries and is_frame_entry(group.entries[-1]):
            return len(group.entries) - 1
        return None

    def _material_names(self) -> List[str]:
        return [name for _, name in self._mm.get_all_materials()] if self._mm else []

    def _bound_indices(self, group: CompositionGroup) -> Optional[List[int]]:
        """Materials a bound group resolves to right now, or None when unbound.

        The tree has to show what the group will export, and for a bound group
        that is a slice of the material library rather than its entries — which
        are kept, but sit out while the binding is on."""
        if not group.source_pattern:
            return None
        return resolve_source_indices(group.source_pattern, self._material_names())

    def _has_tail_frame(self, group: CompositionGroup) -> bool:
        """Whether the group ends on a frame of its own, bound or not."""
        bound = self._bound_indices(group)
        if bound is not None:
            return bool(bound)
        return self._tail_frame_index(group) is not None

    def _tail_duration(self, group: CompositionGroup) -> int:
        """Effective duration of the tail frame (the group default when unset).

        A pinned pause wins over the frame's own duration, because that is what
        the group will actually export — see CompositionGroup.tail_duration_ms."""
        if not self._has_tail_frame(group):
            return group.default_duration_ms
        if group.tail_duration_ms is not None:
            return group.tail_duration_ms
        i = self._tail_frame_index(group)
        if i is None:
            return group.default_duration_ms   # bound: every frame runs at the default
        entry = group.entries[i]
        return entry.duration_ms if entry.duration_ms is not None else group.default_duration_ms

    def _sync_duration_spins(self, gid: int) -> None:
        """Re-show the durations of a group whose default just changed.

        Frames with no duration of their own display the group default, so the
        spinboxes standing for them are stale the moment it moves — and a stale
        one writes its old number back into the model on the next click."""
        group = self._gm.get_group(gid) if self._gm else None
        if group is None:
            return
        pinned_idx = (self._tail_frame_index(group)
                      if group.tail_duration_ms is not None else None)
        for i, entry in enumerate(group.entries):
            if i == pinned_idx:
                continue  # shows the pinned pause, which the default cannot move
            if is_frame_entry(entry) and entry.duration_ms is None:
                _set_spin_quietly(self._row_dur_spin.get((gid, i)), group.default_duration_ms)
        _set_spin_quietly(self._tail_spin.get(gid), self._tail_duration(group))

    def _refresh_tail_widgets(self, gid: int) -> None:
        """Re-show the "last" box and the tail frame's row after a pin toggle.

        Pinning moves ownership of that one duration between the two, and each
        has to come out enabled on exactly one side. Doing it in place rather
        than through refresh() is what lets the handler run at all: a rebuild
        would delete the checkbox that is mid-click."""
        group = self._gm.get_group(gid) if self._gm else None
        if group is None:
            return
        pinned = group.tail_duration_ms is not None
        tail_idx = self._tail_frame_index(group)
        effective = self._tail_duration(group)

        spin = self._tail_spin.get(gid)
        if spin is not None:
            _set_spin_quietly(spin, effective)
            try:
                spin.setEnabled(self._has_tail_frame(group) and pinned)
            except RuntimeError:
                pass

        row = self._row_dur_spin.get((gid, tail_idx)) if tail_idx is not None else None
        if row is not None:
            _set_spin_quietly(row, effective)
            try:
                row.setEnabled(not pinned)
            except RuntimeError:
                pass

    def _get_orphan_gids(self) -> List[int]:
        """Return group IDs not referenced anywhere (safe to delete)."""
        if not self._gm:
            return []
        return [i for i in range(len(self._gm.groups)) if not self._is_referenced(i)]

    # ── Group section ─────────────────────────────────────────────────────────

    def _build_group_section(
        self,
        gid: int,
        depth: int,
        parent_gid: Optional[int],
        entry_idx: Optional[int],
        is_root: bool = False,
    ) -> QWidget:
        group = self._gm.get_group(gid) if self._gm else None
        if group is None:
            lbl = QLabel(f"⚠ Group {gid} not found")
            lbl.setStyleSheet(f"color: {_T.ERROR};")
            return lbl

        # Retrieve the SubGroupEntry (if any) so we can edit loop/x/y inline
        sub_entry: Optional[SubGroupEntry] = None
        if parent_gid is not None and entry_idx is not None and self._gm:
            pg = self._gm.get_group(parent_gid)
            if pg and 0 <= entry_idx < len(pg.entries):
                e = pg.entries[entry_idx]
                if is_sub_group_entry(e):
                    sub_entry = e

        # A nested occurrence is a *reference*, drawn as a single header row
        # that never opens. Collapse used to be tracked per group id, which
        # every occurrence shared: opening one deep in the tree also opened the
        # copy under root. A group's frames are editable in its own top-level
        # section anyway, so that is the one place allowed to show them.
        is_reference = parent_gid is not None
        is_collapsed = True if is_reference else (gid in self._collapsed)
        is_selected  = (gid == self._current_gid)
        bound_indices = self._bound_indices(group)

        # Outer frame
        outer = QFrame()
        border = _T.GRP_BORDER_SEL if is_selected else _T.GRP_BORDER_DEF
        outer.setObjectName("grp_outer")
        outer.setStyleSheet(
            f"QFrame#grp_outer {{ border: 2px solid {border}; border-radius: 5px; }}"
        )
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = _ClickableHeader()
        hdr_bg = _T.GRP_HEADER_SEL if is_selected else _T.GRP_HEADER_DEF
        hdr.setStyleSheet(
            f"QFrame {{ background: {hdr_bg}; border: none; "
            f"border-radius: 4px 4px 0 0; }}"
        )
        hdr.clicked.connect(lambda g=gid: self._cmd_select(g))
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(5, 4, 5, 4)
        hl.setSpacing(4)

        # Collapse toggle — or, on a reference, a jump to the section that owns
        # the frames, since a reference has nothing of its own to open.
        if is_reference:
            tog = _small_btn("↗", _T.CLONE_BTN, width=22)
            tog.setToolTip("Go to this group's own section, where its frames are edited")
            tog.clicked.connect(lambda _=None, g=gid: self._cmd_reveal_group(g))
        else:
            tog = QPushButton("▶" if is_collapsed else "▼")
            tog.setFixedSize(20, 20)
            tog.setStyleSheet(
                f"QPushButton {{ background: none; border: none; "
                f"color: {_T.TEXT_DIM}; font-size: 11px; }}"
            )
            tog.clicked.connect(lambda _=None, g=gid: self._cmd_toggle(g))
        hl.addWidget(tog)

        # Selected indicator
        star = QLabel("★" if is_selected else "☆")
        star.setStyleSheet(
            f"color: {_T.STAR}; font-size: 14px; background: transparent; border: none;"
        )
        hl.addWidget(star)

        # Group name
        name_lbl = QLabel(group.name)
        name_lbl.setStyleSheet(
            f"color: {_T.TEXT}; font-weight: bold; font-size: 12px; "
            "background: transparent; border: none;"
        )
        hl.addWidget(name_lbl)

        # Rename — always visible for every group header
        ren = _small_btn("Rn", _T.TEXT, width=28)
        ren.setToolTip("Rename this group")
        ren.clicked.connect(lambda _=None, g=gid: self._cmd_rename_group(g))
        hl.addWidget(ren)

        hl.addStretch()

        # ── SubGroupEntry controls (loop, x, y, duration-override) — only when nested ──
        if sub_entry is not None:
            hl.addWidget(_lbl("loop"))
            loop_sp = _spinbox(1, 999, sub_entry.loop_count, w=50)
            loop_sp.setToolTip("Loop count for this reference")
            def _set_loop(v, e=sub_entry):
                e.loop_count = v
                self.entries_changed.emit()
            loop_sp.valueChanged.connect(_set_loop)
            hl.addWidget(loop_sp)

            hl.addWidget(_lbl("x"))
            x_sp = _spinbox(-9999, 9999, sub_entry.x, w=55)
            x_sp.setToolTip("X offset applied to all frames in this reference")
            def _set_x(v, e=sub_entry):
                e.x = v
                self.entries_changed.emit()
            x_sp.valueChanged.connect(_set_x)
            hl.addWidget(x_sp)

            hl.addWidget(_lbl("y"))
            y_sp = _spinbox(-9999, 9999, sub_entry.y, w=55)
            y_sp.setToolTip("Y offset applied to all frames in this reference")
            def _set_y(v, e=sub_entry):
                e.y = v
                self.entries_changed.emit()
            y_sp.valueChanged.connect(_set_y)
            hl.addWidget(y_sp)

            # Per-reference duration override (0 = use each frame's own duration)
            hl.addWidget(_lbl("⏱"))
            ov_val = sub_entry.duration_override_ms or 0
            dur_ov = _spinbox(0, 99999, ov_val, suffix="ms", w=80)
            dur_ov.setSpecialValueText("auto")
            dur_ov.setToolTip(
                "Duration override for this reference.\n"
                "\"auto\" = use each frame's own duration.\n"
                "Any other value overrides all frames in this reference."
            )
            def _set_dur_ov(v, e=sub_entry):
                e.duration_override_ms = v if v > 0 else None
                self.entries_changed.emit()
            dur_ov.valueChanged.connect(_set_dur_ov)
            hl.addWidget(dur_ov)

        # Timing of the group itself — shown on the section that owns the
        # frames, not on a reference to it (which has loop/x/y/⏱ of its own).
        if not is_reference:
            # Binding the group to a material glob is what lets one template
            # fit sprites whose clips are different lengths: the group is as
            # long as the match is, so nothing downstream shifts.
            hl.addWidget(_lbl("bind"))
            bind_ed = QLineEdit(group.source_pattern or "")
            bind_ed.setPlaceholderText("entries")
            bind_ed.setMaximumWidth(108)
            bind_ed.setToolTip(
                "Bind this group to every material whose name matches a glob, "
                "e.g. *_org*\n(case-insensitive, ordered by the numbers in the "
                "name so org2 precedes org10).\n"
                "The group then holds as many frames as match, which is what "
                "lets one\ntemplate fit clips of different lengths.\n"
                "Leave it empty to use the entries listed below instead — they "
                "are kept\neither way."
            )
            def _set_bind(ed=bind_ed, g=group):
                text = ed.text().strip()
                wanted = text or None
                if wanted == g.source_pattern:
                    return
                g.source_pattern = wanted
                self._notify()
            bind_ed.editingFinished.connect(_set_bind)
            hl.addWidget(bind_ed)
            self._bind_edit[gid] = bind_ed

            if bound_indices is not None:
                n = len(bound_indices)
                hl.addWidget(_lbl(
                    f"→{n}",
                    f"color: {_T.SUCCESS if n else _T.ERROR}; font-size: 10px; "
                    "font-weight: bold;"
                ))

            hl.addWidget(_lbl("⏱"))
            dur_sp = _spinbox(10, 99999, group.default_duration_ms, suffix="ms", w=_DUR_W)
            dur_sp.setToolTip("Default frame duration for this group")
            def _set_gdur(v, g=group, gg=gid):
                g.default_duration_ms = v
                self._sync_duration_spins(gg)
                self.entries_changed.emit()
            dur_sp.valueChanged.connect(_set_gdur)
            hl.addWidget(dur_sp)

            # The last frame's duration is the pause before the group loops, so
            # it gets adjusted often — and reaching it meant scrolling past
            # every frame in the group.
            #
            # Pinning it (the checkbox) stores that pause on the group instead
            # of on the frame, so it follows the end of the timeline: add
            # materials or apply a template and the pause lands on the new last
            # frame while the old one goes back to its own duration. Unpinned,
            # the box only reports what the bottom frame row's ⏱ already says.
            has_tail = self._has_tail_frame(group)
            pinned = group.tail_duration_ms is not None
            hl.addWidget(_lbl("last"))

            tail_chk = QCheckBox()
            tail_chk.setChecked(pinned and has_tail)
            tail_chk.setEnabled(has_tail)
            tail_chk.setToolTip(
                "Pin the pause before this group loops.\n"
                "On: the value beside this box is forced onto whichever frame "
                "ends the group,\nso adding frames moves it to the new last one "
                "and gives the old one\nits own duration back.\n"
                "Off: the last frame keeps whatever duration it was given."
                if has_tail else
                "This group has no last frame to pin."
            )
            hl.addWidget(tail_chk)
            self._tail_chk[gid] = tail_chk

            tail_sp = _spinbox(10, 99999, self._tail_duration(group), suffix="ms", w=_DUR_W)
            tail_sp.setEnabled(has_tail and pinned)
            if not has_tail:
                tail_sp.setToolTip(
                    "Nothing matches this group's binding yet."
                    if group.source_pattern else
                    "This group is empty — add a frame first." if not group.entries else
                    "This group ends on a sub-group or a layer block, which "
                    "carries its own\ntiming — set the pause there instead."
                )
            elif pinned:
                tail_sp.setToolTip(
                    "How long the frame ending this group is held — the pause "
                    "before it loops.\nPinned, so it stays on the last frame as "
                    "frames are added."
                )
            else:
                tail_sp.setToolTip(
                    "How long the last frame is held — the pause before this "
                    "group loops.\nTick the box to edit it here; otherwise set "
                    "it on the bottom frame row's ⏱."
                )

            def _set_tail(v, g=group, gg=gid):
                # Only reachable while pinned — the box is disabled otherwise.
                if g.tail_duration_ms is None:
                    return
                g.tail_duration_ms = v
                i = self._tail_frame_index(g)
                if i is not None:
                    _set_spin_quietly(self._row_dur_spin.get((gg, i)), v)
                self.entries_changed.emit()
            tail_sp.valueChanged.connect(_set_tail)
            hl.addWidget(tail_sp)
            self._tail_spin[gid] = tail_sp

            def _set_tail_pinned(checked, g=group, gg=gid):
                if not self._has_tail_frame(g):
                    return
                # Seeding from the effective duration leaves the number on
                # screen unchanged as the box is ticked; clearing it hands the
                # frame back to its own.
                g.tail_duration_ms = self._tail_duration(g) if checked else None
                self._refresh_tail_widgets(gg)
                self.entries_changed.emit()
            tail_chk.toggled.connect(_set_tail_pinned)

        # Action buttons
        for label, tip, fn, color in [
            ("+Frame", "Add frame(s) from selected materials",
             lambda _=None, g=gid: self._cmd_add_frame(g), _T.ADD_FRAME),
            ("+Group", "Add sub-group entry",
             lambda _=None, g=gid: self._cmd_add_subgroup(g), _T.ADD_GROUP),
            ("+Layer", "Add layer-block entry",
             lambda _=None, g=gid: self._cmd_add_layerblock(g), _T.ADD_LAYER),
        ]:
            btn = _action_btn(label, color)
            btn.setToolTip(
                "This group is bound to materials — clear its bind field to "
                "edit entries." if bound_indices is not None else tip
            )
            btn.setEnabled(bound_indices is None)
            btn.clicked.connect(fn)
            hl.addWidget(btn)

        group_obj = self._gm.get_group(gid) if self._gm else None
        entry_count = len(group_obj.entries) if group_obj else 0
        clear_btn = _small_btn("🗑", _T.ERROR, width=30)
        clear_btn.setToolTip(
            "Empty this group — remove every frame, sub-group and layer block "
            "inside it.\nThe group itself stays, and Undo brings the contents back."
            if entry_count else "This group is already empty")
        clear_btn.setEnabled(entry_count > 0 and bound_indices is None)
        clear_btn.clicked.connect(lambda _=None, g=gid: self._cmd_clear_group(g))
        hl.addWidget(clear_btn)

        # Top-level: delete button for non-root groups
        if parent_gid is None and not is_root:
            del_btn = _small_btn("X", _T.ERROR, width=34)
            del_btn.setToolTip("Delete this group from the project")
            del_btn.clicked.connect(lambda _=None, g=gid: self._cmd_delete_group(g))
            hl.addWidget(del_btn)

        # Nested: clone / move / remove
        if parent_gid is not None and entry_idx is not None:
            clone_btn = _small_btn("⎘", _T.CLONE_BTN, width=26)
            clone_btn.setToolTip(
                "Duplicate this group into an independent copy.\n"
                "After cloning, adding/removing frames no longer affects other references."
            )
            clone_btn.clicked.connect(
                lambda _=None, g=gid, pg=parent_gid, ei=entry_idx:
                    self._cmd_clone_group(g, pg, ei)
            )
            hl.addWidget(clone_btn)

            for ico, d in [("↑", -1), ("↓", +1)]:
                b = _small_btn(ico)
                b.clicked.connect(
                    lambda _=None, pg=parent_gid, ei=entry_idx, dd=d:
                        self._cmd_move(pg, ei, dd)
                )
                hl.addWidget(b)
            rm = _small_btn("✕", color=_T.ERROR)
            rm.setToolTip("Remove this sub-group entry from the parent (group is kept)")
            rm.clicked.connect(
                lambda _=None, pg=parent_gid, ei=entry_idx: self._cmd_remove(pg, ei)
            )
            hl.addWidget(rm)

        vl.addWidget(hdr)

        # ── Content ──────────────────────────────────────────────────────────
        if not is_collapsed:
            content = QWidget()
            cl = QVBoxLayout(content)
            cl.setContentsMargins(6, 4, 6, 6)
            cl.setSpacing(3)

            if bound_indices is not None:
                for pos, midx in enumerate(bound_indices):
                    cl.addWidget(self._build_bound_row(midx, pos, group))
                if not bound_indices:
                    cl.addWidget(_lbl(
                        f"Nothing in the material library matches "
                        f"'{group.source_pattern}'.",
                        f"color: {_T.TEXT_HINT}; font-style: italic; font-size: 10px;"
                    ))
                elif group.entries:
                    cl.addWidget(_lbl(
                        f"{len(group.entries)} entr"
                        f"{'y is' if len(group.entries) == 1 else 'ies are'} held "
                        f"aside while this group is bound.",
                        f"color: {_T.TEXT_HINT}; font-style: italic; font-size: 10px;"
                    ))
            else:
                for i, entry in enumerate(group.entries):
                    if is_frame_entry(entry):
                        cl.addWidget(
                            self._build_frame_row(entry, gid, i, group.default_duration_ms)
                        )
                    elif is_sub_group_entry(entry):
                        cl.addWidget(
                            self._build_group_section(
                                entry.group_id, depth=depth + 1,
                                parent_gid=gid, entry_idx=i,
                            )
                        )
                    elif is_layer_block_entry(entry):
                        cl.addWidget(self._build_layerblock(entry, gid, i))

                if not group.entries:
                    hint = _lbl(
                        "Empty — use +Frame, +Group, or +Layer to add entries.",
                        f"color: {_T.TEXT_HINT}; font-style: italic; font-size: 10px;"
                    )
                    cl.addWidget(hint)

            vl.addWidget(content)

        # Indent nested groups via a wrapper margin
        if depth > 0:
            wrapper = QWidget()
            wl = QHBoxLayout(wrapper)
            wl.setContentsMargins(depth * 12, 0, 0, 0)
            wl.setSpacing(0)
            wl.addWidget(outer)
            return wrapper

        return outer

    # ── Bound-group row ───────────────────────────────────────────────────────

    def _build_bound_row(self, material_index: int, position: int,
                         group: CompositionGroup) -> QWidget:
        """One frame a binding resolved to: thumbnail and name, nothing to edit.

        The binding decides which materials and in what order, so this row
        reports rather than offers — the numbers that *are* editable (the group
        default, and the pinned pause) live on the header."""
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {_T.FRAME_ROW_BG}; "
            f"border: 1px dashed {_T.FRAME_ROW_BORDER}; border-radius: 3px; }}"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(6, 2, 6, 2)
        rl.setSpacing(6)

        rl.addWidget(_lbl(f"{position + 1}", f"color: {_T.TEXT_DIM}; font-size: 10px;"))

        thumb = QLabel()
        thumb.setFixedSize(52, 36)
        thumb.setStyleSheet("background: transparent; border: none;")
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name = f"#{material_index}"
        if self._mm:
            mat = self._mm.get_material(material_index)
            if mat:
                img, name = mat
                px = _pil_to_pixmap(img, 52, 36)
                if px:
                    thumb.setPixmap(px)
        rl.addWidget(thumb)

        rl.addWidget(_lbl(name, f"color: {_T.MAT_NAME}; font-size: 11px;"))
        rl.addStretch()

        is_last = position == len(self._bound_indices(group) or []) - 1
        ms = self._tail_duration(group) if is_last else group.default_duration_ms
        rl.addWidget(_lbl(f"{ms}ms", f"color: {_T.TEXT_DIM}; font-size: 10px;"))
        return row

    # ── FrameEntry row ────────────────────────────────────────────────────────

    def _build_frame_row(
        self, entry: FrameEntry, parent_gid: int, entry_idx: int,
        group_default_dur: int,
    ) -> QWidget:
        is_row_selected = self._selected_entry == (parent_gid, entry_idx)
        row = _ClickableHeader()
        border = f"2px solid {_T.GRP_BORDER_SEL}" if is_row_selected else f"1px solid {_T.FRAME_ROW_BORDER}"
        row.setStyleSheet(
            f"QFrame {{ background: {_T.FRAME_ROW_BG}; "
            f"border: {border}; border-radius: 3px; }}"
        )
        row.clicked.connect(
            lambda pg=parent_gid, ei=entry_idx: self._cmd_select_entry(pg, ei)
        )
        hl = QHBoxLayout(row)
        hl.setContentsMargins(4, 4, 4, 4)
        hl.setSpacing(6)

        # ── Thumbnail (≈¼ width) ─────────────────────────────────────────────
        thumb = QLabel()
        thumb.setFixedSize(_TW, _TH)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(
            f"border: 1px solid {_T.THUMB_BORDER}; background: {_T.THUMB_BG};"
        )
        if self._mm:
            mat = self._mm.get_material(entry.material_index)
            if mat:
                img, _ = mat
                px = _pil_to_pixmap(img, _TW, _TH)
                if px:
                    thumb.setPixmap(
                        px.scaled(_TW, _TH, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                    )
        hl.addWidget(thumb)

        # ── Info column (name + controls) ────────────────────────────────────
        info = QWidget()
        info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(2)

        # Material name
        mat_name = f"#{entry.material_index}"
        if self._mm:
            mat = self._mm.get_material(entry.material_index)
            if mat:
                _, mat_name = mat
        name_lbl = _lbl(
            mat_name, f"color: {_T.MAT_NAME}; font-size: 11px; font-weight: bold;"
        )
        il.addWidget(name_lbl)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(4)

        ctrl.addWidget(_lbl("⏱"))
        # A pinned group pause owns whichever frame ends the group, so that row
        # reports it read-only instead of offering a second number that the
        # export would ignore.
        row_group = self._gm.get_group(parent_gid) if self._gm else None
        row_pinned = (row_group is not None
                      and row_group.tail_duration_ms is not None
                      and self._tail_frame_index(row_group) == entry_idx)
        shown = (row_group.tail_duration_ms if row_pinned
                 else (entry.duration_ms if entry.duration_ms is not None
                       else group_default_dur))
        dur = _spinbox(10, 99999, shown, suffix="ms", w=_DUR_W)
        dur.setEnabled(not row_pinned)
        if row_pinned:
            dur.setToolTip(
                "The pause before this group loops is pinned to its last frame "
                "— edit it on the group header's 'last' box."
            )
        def _set_dur(v, e=entry, pg=parent_gid, ei=entry_idx):
            e.duration_ms = v
            group = self._gm.get_group(pg) if self._gm else None
            if group is not None and self._tail_frame_index(group) == ei:
                _set_spin_quietly(self._tail_spin.get(pg), v)
            self.entries_changed.emit()
        dur.valueChanged.connect(_set_dur)
        ctrl.addWidget(dur)
        self._row_dur_spin[(parent_gid, entry_idx)] = dur

        ctrl.addWidget(_lbl("x"))
        xs = _spinbox(-9999, 9999, entry.x)
        def _set_x(v, e=entry):
            e.x = v
            self.entries_changed.emit()
        xs.valueChanged.connect(_set_x)
        ctrl.addWidget(xs)

        ctrl.addWidget(_lbl("y"))
        ys = _spinbox(-9999, 9999, entry.y)
        def _set_y(v, e=entry):
            e.y = v
            self.entries_changed.emit()
        ys.valueChanged.connect(_set_y)
        ctrl.addWidget(ys)

        ctrl.addStretch()
        il.addLayout(ctrl)
        hl.addWidget(info)

        # ── Move / Duplicate / Remove ─────────────────────────────────────────
        btn_col = QVBoxLayout()
        btn_col.setSpacing(2)
        for ico, d in [("↑", -1), ("↓", +1)]:
            b = _small_btn(ico)
            b.clicked.connect(
                lambda _=None, pg=parent_gid, ei=entry_idx, dd=d:
                    self._cmd_move(pg, ei, dd)
            )
            btn_col.addWidget(b)
        dup = _small_btn("Dup", _T.TEXT_DIM, width=34)
        dup.setToolTip("Duplicate this frame (insert a copy right after)")
        dup.clicked.connect(
            lambda _=None, pg=parent_gid, ei=entry_idx: self._cmd_duplicate_frame(pg, ei)
        )
        btn_col.addWidget(dup)
        rm = _small_btn("X", _T.ERROR, width=34)
        rm.setToolTip("Remove this frame")
        rm.clicked.connect(
            lambda _=None, pg=parent_gid, ei=entry_idx: self._cmd_remove(pg, ei)
        )
        btn_col.addWidget(rm)
        hl.addLayout(btn_col)

        return row

    # ── LayerBlockEntry widget ────────────────────────────────────────────────

    def _build_layerblock(
        self, entry: LayerBlockEntry, parent_gid: int, entry_idx: int
    ) -> QWidget:
        lb_id = id(entry)
        is_collapsed = lb_id in self._collapsed

        outer = QFrame()
        outer.setObjectName("lb_outer")
        outer.setStyleSheet(
            f"QFrame#lb_outer {{ border: 1px solid {_T.LB_BORDER}; border-radius: 4px; }}"
        )
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        # Header
        hdr = QFrame()
        hdr.setStyleSheet(
            f"QFrame {{ background: {_T.LB_HEADER}; border: none; "
            f"border-radius: 3px 3px 0 0; }}"
        )
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(5, 4, 5, 4)
        hl.setSpacing(4)

        tog = QPushButton("▶" if is_collapsed else "▼")
        tog.setFixedSize(20, 20)
        tog.setStyleSheet(
            f"QPushButton {{ background: none; border: none; "
            f"color: {_T.TEXT_DIM}; font-size: 11px; }}"
        )
        tog.clicked.connect(lambda _=None, lid=lb_id: self._cmd_toggle(lid))
        hl.addWidget(tog)

        hl.addWidget(_lbl("🎞 Layer Block", f"color: {_T.LB_LABEL}; font-size: 11px;"))

        hl.addWidget(_lbl("⏱"))
        bk_dur = _spinbox(10, 99999, entry.default_duration_ms, suffix="ms", w=80)
        def _set_bkdur(v, e=entry):
            e.default_duration_ms = v
            self.entries_changed.emit()
        bk_dur.valueChanged.connect(_set_bkdur)
        hl.addWidget(bk_dur)

        tl_lbl = _lbl(
            f"({len(entry.timelines)} timelines)",
            f"color: {_T.TEXT_HINT}; font-size: 10px;"
        )
        hl.addWidget(tl_lbl)
        hl.addStretch()

        add_tl = _action_btn("+Timeline", _T.ADD_LAYER)
        add_tl.clicked.connect(
            lambda _=None, e=entry, pg=parent_gid: self._cmd_add_timeline(e, pg)
        )
        hl.addWidget(add_tl)

        for ico, d in [("↑", -1), ("↓", +1)]:
            b = _small_btn(ico)
            b.clicked.connect(
                lambda _=None, pg=parent_gid, ei=entry_idx, dd=d:
                    self._cmd_move(pg, ei, dd)
            )
            hl.addWidget(b)

        rm = _small_btn("✕", _T.ERROR)
        rm.clicked.connect(
            lambda _=None, pg=parent_gid, ei=entry_idx: self._cmd_remove(pg, ei)
        )
        hl.addWidget(rm)

        vl.addWidget(hdr)

        if not is_collapsed:
            content = QWidget()
            cl = QVBoxLayout(content)
            cl.setContentsMargins(6, 4, 6, 6)
            cl.setSpacing(6)

            for ti, timeline in enumerate(entry.timelines):
                cl.addWidget(
                    self._build_timeline_section(timeline, entry, ti, parent_gid)
                )
            if not entry.timelines:
                cl.addWidget(_lbl("No timelines — click +Timeline to add."))

            vl.addWidget(content)

        return outer

    # ── One timeline inside a LayerBlock ──────────────────────────────────────

    def _build_timeline_section(
        self,
        timeline: list,
        lb_entry: LayerBlockEntry,
        tl_idx: int,
        parent_gid: int,
    ) -> QWidget:
        outer = QFrame()
        outer.setStyleSheet(
            f"QFrame {{ background: {_T.TL_BG}; border: 1px solid {_T.TL_BORDER}; "
            f"border-radius: 3px; }}"
        )
        vl = QVBoxLayout(outer)
        vl.setContentsMargins(4, 3, 4, 6)
        vl.setSpacing(3)

        # Timeline header
        th = QHBoxLayout()
        th.addWidget(
            _lbl(f"Layer {tl_idx}", f"color: {_T.TL_LABEL}; font-size: 11px; font-weight: bold;")
        )
        th.addWidget(
            _lbl(f"({len(timeline)} slots)", f"color: {_T.TEXT_HINT}; font-size: 10px;")
        )
        th.addStretch()

        for label, fn in [
            ("+Frame", lambda _=None, e=lb_entry, ti=tl_idx, pg=parent_gid:
                 self._cmd_add_frameslot(e, ti, pg)),
            ("+Group", lambda _=None, e=lb_entry, ti=tl_idx, pg=parent_gid:
                 self._cmd_add_groupslot(e, ti, pg)),
        ]:
            b = _small_btn(label, _T.TEXT_DIM, width=56)
            b.clicked.connect(fn)
            th.addWidget(b)

        # Layer reorder buttons
        for ico, d in [("↑", -1), ("↓", +1)]:
            b = _small_btn(ico)
            b.setToolTip("Move this layer up/down")
            b.clicked.connect(
                lambda _=None, e=lb_entry, ti=tl_idx, dd=d, pg=parent_gid:
                    self._cmd_move_timeline(e, ti, dd, pg)
            )
            th.addWidget(b)

        rm_tl = _small_btn("✕ TL", _T.ERROR, width=44)
        rm_tl.clicked.connect(
            lambda _=None, e=lb_entry, ti=tl_idx, pg=parent_gid:
                self._cmd_remove_timeline(e, ti, pg)
        )
        th.addWidget(rm_tl)
        vl.addLayout(th)

        # Slot rows (same style as FrameEntry rows for consistency)
        for si, slot in enumerate(timeline):
            vl.addWidget(
                self._build_slot_row(slot, lb_entry, tl_idx, si, parent_gid)
            )

        if not timeline:
            vl.addWidget(
                _lbl("  (empty)", f"color: {_T.TEXT_HINT}; font-style: italic; font-size: 10px;")
            )

        return outer

    # ── One slot row ──────────────────────────────────────────────────────────

    def _build_slot_row(
        self,
        slot,
        lb_entry: LayerBlockEntry,
        tl_idx: int,
        slot_idx: int,
        parent_gid: int,
    ) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background: {_T.SLOT_BG}; border: 1px solid {_T.SLOT_BORDER}; "
            f"border-radius: 3px; }}"
        )
        hl = QHBoxLayout(row)
        hl.setContentsMargins(4, 4, 4, 4)
        hl.setSpacing(6)

        # Thumbnail
        thumb = QLabel()
        thumb.setFixedSize(_TW, _TH)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(
            f"border: 1px solid {_T.THUMB_BORDER}; background: {_T.THUMB_BG};"
        )

        # Info column
        info = QWidget()
        info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        il = QVBoxLayout(info)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(2)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(4)

        if is_frame_slot(slot):
            if self._mm:
                mat = self._mm.get_material(slot.material_index)
                if mat:
                    img, _ = mat
                    px = _pil_to_pixmap(img, _TW, _TH)
                    if px:
                        thumb.setPixmap(
                            px.scaled(_TW, _TH, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
                        )
            mat_name = f"#{slot.material_index}"
            if self._mm:
                mat = self._mm.get_material(slot.material_index)
                if mat:
                    _, mat_name = mat
            il.addWidget(_lbl(mat_name, f"color: {_T.MAT_NAME}; font-size: 11px;"))

            ctrl.addWidget(_lbl("x"))
            xs = _spinbox(-9999, 9999, slot.x)
            def _set_sx(v, s=slot):
                s.x = v
                self.entries_changed.emit()
            xs.valueChanged.connect(_set_sx)
            ctrl.addWidget(xs)

            ctrl.addWidget(_lbl("y"))
            ys = _spinbox(-9999, 9999, slot.y)
            def _set_sy(v, s=slot):
                s.y = v
                self.entries_changed.emit()
            ys.valueChanged.connect(_set_sy)
            ctrl.addWidget(ys)

        elif is_group_slot(slot):
            grp = self._gm.get_group(slot.group_id) if self._gm else None
            name = grp.name if grp else f"Group {slot.group_id}"
            il.addWidget(_lbl(name, f"color: {_T.CLONE_BTN}; font-size: 11px; font-weight: bold;"))

            ctrl.addWidget(_lbl("×"))
            lp = _spinbox(1, 999, slot.loop_count, w=50)
            def _set_slp(v, s=slot):
                s.loop_count = v
                self.entries_changed.emit()
            lp.valueChanged.connect(_set_slp)
            ctrl.addWidget(lp)

            ctrl.addWidget(_lbl("x"))
            xs = _spinbox(-9999, 9999, slot.x)
            def _set_gsx(v, s=slot):
                s.x = v
                self.entries_changed.emit()
            xs.valueChanged.connect(_set_gsx)
            ctrl.addWidget(xs)

            ctrl.addWidget(_lbl("y"))
            ys = _spinbox(-9999, 9999, slot.y)
            def _set_gsy(v, s=slot):
                s.y = v
                self.entries_changed.emit()
            ys.valueChanged.connect(_set_gsy)
            ctrl.addWidget(ys)

        ctrl.addStretch()
        il.addLayout(ctrl)
        hl.addWidget(thumb)
        hl.addWidget(info)

        # Remove slot
        rm = _small_btn("✕", _T.ERROR)
        rm.clicked.connect(
            lambda _=None, e=lb_entry, ti=tl_idx, si=slot_idx, pg=parent_gid:
                self._cmd_remove_slot(e, ti, si, pg)
        )
        hl.addWidget(rm)

        return row

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_toggle(self, key):
        if key in self._collapsed:
            self._collapsed.discard(key)
        else:
            self._collapsed.add(key)
        self.refresh()

    def _cmd_reveal_group(self, gid: int):
        """Select a referenced group and scroll to the section that owns it."""
        self._current_gid = gid
        self._collapsed.discard(gid)
        self.current_group_changed.emit(gid)
        self._pending_reveal = gid
        self.refresh()

    def _cmd_select(self, gid: int):
        self._current_gid = gid
        self.current_group_changed.emit(gid)
        self.refresh()

    def _cmd_select_entry(self, parent_gid: int, entry_idx: int):
        self._selected_entry = (parent_gid, entry_idx)
        self.frame_entry_selected.emit(parent_gid, entry_idx)
        self.refresh()

    def _cmd_clone_group(self, gid: int, parent_gid: int, entry_idx: int):
        """Deep-copy a group into a new independent group; update the SubGroupEntry to point to it."""
        if not self._gm:
            return
        src = self._gm.get_group(gid)
        if not src:
            return
        parent = self._gm.get_group(parent_gid)
        if not parent or not (0 <= entry_idx < len(parent.entries)):
            return
        entry = parent.entries[entry_idx]
        if not is_sub_group_entry(entry):
            return

        # Deep copy group (all FrameEntry / nested entry objects become independent)
        new_group = copy.deepcopy(src)
        suffix = 1
        base = src.name.rstrip("0123456789_")
        while any(g.name == f"{base}_{suffix}" for g in self._gm.groups):
            suffix += 1
        new_group.name = f"{base}_{suffix}"

        new_gid = self._gm.add_group(new_group)
        entry.group_id = new_gid          # redirect this entry to the new copy
        self._notify()

    def _cmd_rename_group(self, gid: int):
        if not self._gm:
            return
        group = self._gm.get_group(gid)
        if not group:
            return
        name, ok = QInputDialog.getText(
            self.window(), "Rename Group", "New name:",
            QLineEdit.EchoMode.Normal, group.name
        )
        if ok and name.strip():
            group.name = name.strip()
            self.refresh()

    def _cmd_delete_group(self, gid: int):
        if not self._gm:
            return
        group = self._gm.get_group(gid)
        if not group:
            return
        # Safety: block deletion if any other group references this one
        if self._is_referenced(gid):
            QMessageBox.warning(
                self.window(), "Cannot Delete",
                "This group is still referenced in the tree.\n"
                "Remove all sub-group entries / slots pointing to it first."
            )
            return
        reply = QMessageBox.question(
            self.window(), "Delete Group",
            f"Delete group \"{group.name}\"? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._gm.remove_group(gid)
        if self._current_gid == gid:
            root = self._gm.get_root_group_id()
            self._current_gid = root
            if root is not None:
                self.current_group_changed.emit(root)
        self.refresh()

    def _cmd_clear_group(self, gid: int):
        """Empty a group without deleting it.

        Confirmed rather than instant, because one click can throw away a lot of
        arranging — but it goes through the ordinary change signal, so Undo puts
        it all back."""
        if not self._gm:
            return
        group = self._gm.get_group(gid)
        if not group or not group.entries:
            return

        frames = sum(1 for e in group.entries if is_frame_entry(e))
        subgroups = sum(1 for e in group.entries if is_sub_group_entry(e))
        blocks = sum(1 for e in group.entries if is_layer_block_entry(e))
        parts = [f"{n} {name}" for n, name in
                 ((frames, "frame(s)"), (subgroups, "sub-group entr(ies)"),
                  (blocks, "layer block(s)")) if n]

        message = f"Remove {', '.join(parts)} from \"{group.name}\"?"
        references = self._reference_count(gid)
        if references > 1:
            message += (f"\n\nThis group appears {references} times in the tree, "
                        "and they all share these contents — every one of them "
                        "will be emptied.")
        message += "\n\nUndo (Ctrl+Z) restores it."

        reply = QMessageBox.question(
            self.window(), "Clear Group", message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        group.entries.clear()
        self._notify()

    def _notify(self):
        self.entries_changed.emit()
        self.refresh()

    def _cmd_new_group(self):
        """Create a new standalone group. Sets root only if none exists yet."""
        if not self._gm:
            return
        is_first = self._gm.get_root_group_id() is None
        default_name = "Root" if is_first else "Group"
        name, ok = QInputDialog.getText(
            self.window(), "New Group", "Group name:",
            QLineEdit.EchoMode.Normal, default_name
        )
        if not ok:
            return
        from ..core.composition_group import CompositionGroup
        g = CompositionGroup(name=(name.strip() or default_name))
        gid = self._gm.add_group(g)
        if is_first:
            self._gm.set_root_group_id(gid)
        if self._current_gid is None:
            self._current_gid = gid
            self.current_group_changed.emit(gid)
        self.refresh()

    def _cmd_add_frame(self, gid: int):
        if not self._gm:
            return
        mats = self._get_sel_mat() if self._get_sel_mat else []
        if not mats:
            QMessageBox.information(
                self.window(), "Add Frame",
                "Select material(s) in the Materials panel first."
            )
            return
        group = self._gm.get_group(gid)
        if not group:
            return
        for m in mats:
            group.entries.append(FrameEntry(material_index=m, x=0, y=0, duration_ms=None))
        self._notify()

    def _cmd_add_subgroup(self, gid: int):
        if not self._gm:
            return
        groups = self._gm.get_all_groups()
        others = [(i, g.name) for i, g in enumerate(groups) if i != gid]
        choices = ["[Create New Group…]"] + [f"[{i}] {n}" for i, n in others]

        if len(choices) > 1:
            choice, ok = QInputDialog.getItem(
                self.window(), "Add Sub-group",
                "Select group to reference:", choices, 0, False
            )
            if not ok:
                return
        else:
            choice = choices[0]

        if choice == choices[0]:
            name, ok = QInputDialog.getText(
                self.window(), "New Group", "Group name:",
                QLineEdit.EchoMode.Normal, ""
            )
            if not ok:
                return
            from ..core.composition_group import CompositionGroup
            ng = CompositionGroup(name=(name.strip() or "Group"))
            new_gid = self._gm.add_group(ng)
        else:
            sel_pos = choices.index(choice) - 1
            new_gid = others[sel_pos][0]

        loop, ok = QInputDialog.getInt(
            self.window(), "Loop Count", "Repeat count:", 1, 1, 999
        )
        if not ok:
            return
        group = self._gm.get_group(gid)
        if group:
            group.entries.append(SubGroupEntry(group_id=new_gid, loop_count=loop, x=0, y=0))
            self._notify()

    def _cmd_add_layerblock(self, gid: int):
        if not self._gm:
            return
        group = self._gm.get_group(gid)
        if not group:
            return
        group.entries.append(LayerBlockEntry(timelines=[], default_duration_ms=100))
        self._notify()

    def _cmd_remove(self, parent_gid: int, entry_idx: int):
        if not self._gm:
            return
        group = self._gm.get_group(parent_gid)
        if not group or not (0 <= entry_idx < len(group.entries)):
            return
        group.entries.pop(entry_idx)
        self._notify()

    def _cmd_duplicate_frame(self, parent_gid: int, entry_idx: int):
        """Insert a shallow copy of the FrameEntry right after entry_idx."""
        if not self._gm:
            return
        group = self._gm.get_group(parent_gid)
        if not group or not (0 <= entry_idx < len(group.entries)):
            return
        original = group.entries[entry_idx]
        if not is_frame_entry(original):
            return
        copy = FrameEntry(
            material_index=original.material_index,
            x=original.x,
            y=original.y,
            duration_ms=original.duration_ms,
        )
        group.entries.insert(entry_idx + 1, copy)
        self._notify()

    def _cmd_move(self, parent_gid: int, entry_idx: int, direction: int):
        if not self._gm:
            return
        group = self._gm.get_group(parent_gid)
        if not group:
            return
        ni = entry_idx + direction
        if not (0 <= ni < len(group.entries)):
            return
        e = group.entries
        e[entry_idx], e[ni] = e[ni], e[entry_idx]
        self._notify()

    # ── LayerBlock commands ───────────────────────────────────────────────────

    def _cmd_add_timeline(self, lb: LayerBlockEntry, parent_gid: int):
        lb.timelines.append([])
        self._notify()

    def _cmd_remove_timeline(self, lb: LayerBlockEntry, tl_idx: int, parent_gid: int):
        if 0 <= tl_idx < len(lb.timelines):
            lb.timelines.pop(tl_idx)
            self._notify()

    def _cmd_move_timeline(self, lb: LayerBlockEntry, tl_idx: int, direction: int, parent_gid: int):
        ni = tl_idx + direction
        if 0 <= ni < len(lb.timelines):
            lb.timelines[tl_idx], lb.timelines[ni] = lb.timelines[ni], lb.timelines[tl_idx]
            self._notify()

    def _cmd_add_frameslot(self, lb: LayerBlockEntry, tl_idx: int, parent_gid: int):
        mats = self._get_sel_mat() if self._get_sel_mat else []
        if not mats:
            QMessageBox.information(
                self.window(), "Add Frame Slot",
                "Select material(s) in the Materials panel first."
            )
            return
        if tl_idx >= len(lb.timelines):
            return
        for m in mats:
            lb.timelines[tl_idx].append(FrameSlot(material_index=m, x=0, y=0))
        self._notify()

    def _cmd_add_groupslot(self, lb: LayerBlockEntry, tl_idx: int, parent_gid: int):
        if not self._gm:
            return
        groups = self._gm.get_all_groups()
        if not groups:
            QMessageBox.information(self.window(), "Add Group Slot", "No groups available.")
            return
        names = [f"[{i}] {g.name}" for i, g in enumerate(groups)]
        choice, ok = QInputDialog.getItem(
            self.window(), "Add Group Slot", "Select group:", names, 0, False
        )
        if not ok:
            return
        sel_idx = names.index(choice)
        loop, ok = QInputDialog.getInt(
            self.window(), "Loop Count", "Loop count:", 1, 1, 999
        )
        if not ok:
            return
        if tl_idx >= len(lb.timelines):
            return
        lb.timelines[tl_idx].append(GroupSlot(group_id=sel_idx, loop_count=loop, x=0, y=0))
        self._notify()

    def _cmd_remove_slot(
        self, lb: LayerBlockEntry, tl_idx: int, slot_idx: int, parent_gid: int
    ):
        if tl_idx >= len(lb.timelines):
            return
        tl = lb.timelines[tl_idx]
        if 0 <= slot_idx < len(tl):
            tl.pop(slot_idx)
            self._notify()
