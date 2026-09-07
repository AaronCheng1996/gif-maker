"""Tests for the header "last" duration box and for references never expanding.

The last frame of a group is the one held on screen before it loops, so its
duration is the pause between loops — reaching it used to mean scrolling past
every frame in the group. The header box edits the same number the bottom frame
row does, which is why most of these tests are about the two staying in step.

Which frame that is changes as materials arrive, so the pause can also be
pinned to the group: it then lands on whatever frame ends the timeline, and the
header box — not the frame row — is what edits it.
"""
import pytest

from PyQt6.QtWidgets import QApplication

from src.core.composition_group import (CompositionGroup, FrameEntry, SubGroupEntry,
                                        LayerBlockEntry)
from src.core.group_manager import GroupManager
from src.widgets.group_composition_widget import GroupCompositionWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def widget(qapp):
    w = GroupCompositionWidget()
    gm = GroupManager()
    root = gm.add_group(CompositionGroup(name="Root", default_duration_ms=100))
    child = gm.add_group(CompositionGroup(name="Child", default_duration_ms=100))
    gm.set_root_group_id(root)
    gm.get_group(root).entries.extend([
        FrameEntry(material_index=0),
        FrameEntry(material_index=1),
    ])
    gm.get_group(child).entries.append(FrameEntry(material_index=2))
    w.set_group_manager(gm)
    w.gm, w.root, w.child = gm, root, child
    yield w


@pytest.fixture()
def fired(widget):
    """Count entries_changed emissions — the signal undo and preview hang off."""
    seen = []
    widget.entries_changed.connect(lambda: seen.append(1))
    return seen


# ── Which frame the header box points at ─────────────────────────────────────

def test_the_tail_is_the_last_entry_when_it_is_a_frame(widget):
    assert widget._tail_frame_index(widget.gm.get_group(widget.root)) == 1


def test_a_group_ending_on_a_sub_group_has_no_tail_frame(widget):
    root = widget.gm.get_group(widget.root)
    root.entries.append(SubGroupEntry(group_id=widget.child))
    assert widget._tail_frame_index(root) is None


def test_a_group_ending_on_a_layer_block_has_no_tail_frame(widget):
    root = widget.gm.get_group(widget.root)
    root.entries.append(LayerBlockEntry())
    assert widget._tail_frame_index(root) is None


def test_an_empty_group_has_no_tail_frame(widget):
    assert widget._tail_frame_index(CompositionGroup(name="Empty")) is None


def test_a_tail_frame_without_its_own_duration_shows_the_group_default(widget):
    root = widget.gm.get_group(widget.root)
    root.default_duration_ms = 250
    assert widget._tail_duration(root) == 250


def test_a_tail_frame_with_its_own_duration_shows_that(widget):
    root = widget.gm.get_group(widget.root)
    root.entries[-1].duration_ms = 2000
    assert widget._tail_duration(root) == 2000


# ── The header box edits the last frame ──────────────────────────────────────

def test_the_header_box_is_read_only_until_the_pause_is_pinned(widget):
    """Unpinned it only reports the last frame's duration; taking that number
    over is what the box beside it is for."""
    spin = widget._tail_spin[widget.root]
    assert not spin.isEnabled()

    spin.setValue(2000)          # a programmatic move still reaches the handler

    root = widget.gm.get_group(widget.root)
    assert root.entries[1].duration_ms is None
    assert root.tail_duration_ms is None


def test_the_header_box_is_off_when_the_group_ends_on_a_sub_group(widget):
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()

    spin = widget._tail_spin[widget.root]
    assert not spin.isEnabled()
    spin.setValue(2000)          # nothing to write it to
    assert widget.gm.get_group(widget.root).entries[1].duration_ms is None


def test_the_header_box_is_off_for_an_empty_group(widget):
    empty = widget.gm.add_group(CompositionGroup(name="Empty"))
    widget.refresh()
    assert not widget._tail_spin[empty].isEnabled()


def test_a_reference_gets_no_header_box_of_its_own(widget):
    """The tail belongs to the group, not to a place that plays it, so the box
    lives on the section that owns the frames — a reference keeps loop/x/y."""
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()
    # One box per group, from its own top-level section.
    assert sorted(widget._tail_spin) == [widget.root, widget.child]


# ── Header box and frame row are two views of one number ─────────────────────

def test_editing_a_pinned_header_box_moves_the_last_frames_row(widget):
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)
    assert widget._row_dur_spin[(widget.root, 1)].value() == 2000


def test_editing_the_last_frames_row_moves_the_header_box(widget):
    widget._row_dur_spin[(widget.root, 1)].setValue(1500)
    assert widget._tail_spin[widget.root].value() == 1500


def test_editing_a_frame_that_is_not_last_leaves_the_header_box_alone(widget):
    before = widget._tail_spin[widget.root].value()
    widget._row_dur_spin[(widget.root, 0)].setValue(555)
    assert widget._tail_spin[widget.root].value() == before


def test_following_along_does_not_write_the_change_twice(widget, fired):
    """The follower is moved with its signals blocked; otherwise the edit lands
    in the model twice and leaves two undo steps behind one keystroke."""
    widget._tail_chk[widget.root].setChecked(True)
    fired.clear()

    widget._tail_spin[widget.root].setValue(2000)
    assert len(fired) == 1


def test_the_two_boxes_do_not_bounce_the_value_back(widget):
    widget._row_dur_spin[(widget.root, 1)].setValue(1500)
    assert widget.gm.get_group(widget.root).entries[1].duration_ms == 1500
    assert widget._tail_spin[widget.root].value() == 1500


# ── The group default is what unset frames display ───────────────────────────

def test_changing_the_group_default_moves_the_boxes_that_showed_it(widget):
    widget.gm.get_group(widget.root).default_duration_ms = 100
    widget.refresh()

    # The default's own spinbox is not registered, so drive the handler the way
    # the spinbox does: through the group, then ask the widget to re-show it.
    widget.gm.get_group(widget.root).default_duration_ms = 250
    widget._sync_duration_spins(widget.root)

    assert widget._row_dur_spin[(widget.root, 0)].value() == 250
    assert widget._tail_spin[widget.root].value() == 250


def test_a_frame_with_its_own_duration_ignores_the_group_default(widget):
    widget.gm.get_group(widget.root).entries[0].duration_ms = 40
    widget.refresh()

    widget.gm.get_group(widget.root).default_duration_ms = 250
    widget._sync_duration_spins(widget.root)

    assert widget._row_dur_spin[(widget.root, 0)].value() == 40


def test_syncing_an_unknown_group_is_a_no_op(widget):
    widget._sync_duration_spins(999)      # must not raise


# ── Pinning the pause to whichever frame ends the group ──────────────────────

def test_a_group_starts_unpinned(widget):
    assert widget.gm.get_group(widget.root).tail_duration_ms is None
    assert not widget._tail_chk[widget.root].isChecked()


def test_pinning_makes_the_header_box_editable(widget):
    assert not widget._tail_spin[widget.root].isEnabled()
    widget._tail_chk[widget.root].setChecked(True)
    assert widget._tail_spin[widget.root].isEnabled()


def test_pinning_seeds_from_what_the_last_frame_already_showed(widget, fired):
    widget.gm.get_group(widget.root).entries[-1].duration_ms = 1500
    widget.refresh()

    widget._tail_chk[widget.root].setChecked(True)

    assert widget.gm.get_group(widget.root).tail_duration_ms == 1500
    assert widget._tail_spin[widget.root].value() == 1500, "the number must not jump"
    assert fired, "the pin has to be undoable and repaint the preview"


def test_pinning_an_untimed_frame_seeds_from_the_group_default(widget):
    widget.gm.get_group(widget.root).default_duration_ms = 250
    widget.refresh()

    widget._tail_chk[widget.root].setChecked(True)
    assert widget.gm.get_group(widget.root).tail_duration_ms == 250


def test_a_pinned_box_writes_the_group_not_the_frame(widget):
    """Writing the frame is what stranded the pause when a material arrived."""
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)

    root = widget.gm.get_group(widget.root)
    assert root.tail_duration_ms == 2000
    assert root.entries[1].duration_ms is None


def test_pinning_hands_the_last_frames_row_over_to_the_header(widget):
    widget._tail_chk[widget.root].setChecked(True)

    assert not widget._row_dur_spin[(widget.root, 1)].isEnabled()
    assert widget._row_dur_spin[(widget.root, 0)].isEnabled(), "only the last one"


def test_a_rebuild_keeps_the_last_frames_row_read_only(widget):
    widget._tail_chk[widget.root].setChecked(True)
    widget.refresh()

    assert not widget._row_dur_spin[(widget.root, 1)].isEnabled()
    assert widget._tail_spin[widget.root].isEnabled()
    assert widget._tail_chk[widget.root].isChecked()


def test_unpinning_gives_the_frame_its_own_duration_back(widget):
    root = widget.gm.get_group(widget.root)
    root.entries[-1].duration_ms = 40
    widget.refresh()

    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)
    widget._tail_chk[widget.root].setChecked(False)

    assert root.tail_duration_ms is None
    assert root.entries[-1].duration_ms == 40
    assert widget._tail_spin[widget.root].value() == 40
    assert widget._row_dur_spin[(widget.root, 1)].isEnabled()


def test_the_pause_moves_to_the_frame_a_new_material_adds(widget):
    """The reason for pinning: adding a material used to leave the pause on the
    frame that was last when it was set, and bring the new one in at the group
    default."""
    root = widget.gm.get_group(widget.root)
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)

    root.entries.append(FrameEntry(material_index=3))
    widget.refresh()

    assert widget._tail_chk[widget.root].isChecked()
    assert widget._tail_spin[widget.root].value() == 2000
    assert not widget._row_dur_spin[(widget.root, 2)].isEnabled(), "the new last frame"
    assert widget._row_dur_spin[(widget.root, 1)].isEnabled(), "handed back"
    assert root.entries[1].duration_ms is None, "and never written to"


def test_the_pin_is_off_when_the_group_ends_on_a_sub_group(widget):
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()

    chk = widget._tail_chk[widget.root]
    assert not chk.isEnabled()
    chk.setChecked(True)          # nothing to pin it to
    assert widget.gm.get_group(widget.root).tail_duration_ms is None


def test_the_pin_is_off_for_an_empty_group(widget):
    empty = widget.gm.add_group(CompositionGroup(name="Empty"))
    widget.refresh()
    assert not widget._tail_chk[empty].isEnabled()


def test_a_reference_gets_no_pin_of_its_own(widget):
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()
    assert sorted(widget._tail_chk) == [widget.root, widget.child]


def test_the_group_default_cannot_move_a_pinned_pause(widget):
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)

    widget.gm.get_group(widget.root).default_duration_ms = 250
    widget._sync_duration_spins(widget.root)

    assert widget._tail_spin[widget.root].value() == 2000
    assert widget._row_dur_spin[(widget.root, 1)].value() == 2000
    assert widget._row_dur_spin[(widget.root, 0)].value() == 250, "unpinned frames follow"


def test_refreshing_an_unknown_group_is_a_no_op(widget):
    widget._refresh_tail_widgets(999)      # must not raise


# ── A referenced group is a header row, not a second copy of the tree ────────

@pytest.fixture()
def frame_rows(widget, monkeypatch):
    """Record (group_id, entry_idx) for every frame row the tree draws."""
    drawn = []
    original = GroupCompositionWidget._build_frame_row

    def spy(self, entry, parent_gid, entry_idx, group_default_dur):
        drawn.append((parent_gid, entry_idx))
        return original(self, entry, parent_gid, entry_idx, group_default_dur)

    monkeypatch.setattr(GroupCompositionWidget, "_build_frame_row", spy)
    return drawn


def test_a_referenced_groups_frames_are_drawn_once(widget, frame_rows):
    """Collapse was tracked per group id, so the reference under root and the
    group's own section were the same switch — opening one opened both."""
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()

    assert frame_rows.count((widget.child, 0)) == 1


def test_collapsing_a_group_hides_only_its_own_section(widget, frame_rows):
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget._cmd_toggle(widget.child)
    frame_rows.clear()
    widget.refresh()

    assert (widget.child, 0) not in frame_rows
    assert (widget.root, 0) in frame_rows, "root is a different section"


def test_a_reference_stays_shut_even_when_its_group_is_open(widget, frame_rows):
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=widget.child))
    widget._collapsed.discard(widget.child)
    widget.refresh()

    assert frame_rows.count((widget.child, 0)) == 1


def test_a_self_referencing_group_does_not_recurse(widget):
    """A reference draws no contents, so a cycle cannot run away."""
    widget.gm.get_group(widget.child).entries.append(SubGroupEntry(group_id=widget.child))
    widget.refresh()      # used to recurse until the stack ran out


# ── Jumping from a reference to the section that owns it ─────────────────────

def test_jumping_selects_the_group_and_queues_the_scroll(widget):
    widget._collapsed.add(widget.child)
    picked = []
    widget.current_group_changed.connect(picked.append)

    widget._cmd_reveal_group(widget.child)

    assert widget.get_current_group_id() == widget.child
    assert widget.child not in widget._collapsed, "jumping to a shut section opens it"
    assert picked == [widget.child]
    assert widget._pending_reveal == widget.child


def test_the_scroll_reveals_the_section_and_forgets_the_request(widget):
    widget._cmd_reveal_group(widget.child)
    widget._restore_scroll()
    assert widget._pending_reveal is None


def test_an_ordinary_rebuild_still_puts_the_scroll_back(widget):
    bar = widget._scroll.verticalScrollBar()
    bar.setRange(0, 100)      # nothing is laid out offscreen, so it has no range
    widget._pending_scroll = 37
    widget._restore_scroll()
    assert bar.value() == 37
