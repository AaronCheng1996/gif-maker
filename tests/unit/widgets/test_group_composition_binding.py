"""Tests for the group header's material binding field.

Binding a group to a glob is what lets one template fit sprites whose clips are
different lengths, so the tree has to show what the binding resolved to rather
than the entries it set aside — and it has to keep the two from being edited at
once.
"""
import pytest

from PIL import Image
from PyQt6.QtWidgets import QApplication

from src.core.composition_group import CompositionGroup, FrameEntry, SubGroupEntry
from src.core.group_manager import GroupManager
from src.core.image_loader import MaterialManager
from src.widgets.group_composition_widget import GroupCompositionWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def widget(qapp):
    mm = MaterialManager()
    for name in ["dh01_idle01", "dh01_idle02",
                 "dh01_org01", "dh01_org02", "dh01_org03"]:
        mm.add_material(Image.new("RGBA", (8, 8), (0, 0, 0, 255)), name=name)

    gm = GroupManager()
    root = gm.add_group(CompositionGroup(name="Root", default_duration_ms=100))
    gm.set_root_group_id(root)
    gm.get_group(root).entries.extend([
        FrameEntry(material_index=0),
        FrameEntry(material_index=1),
    ])

    w = GroupCompositionWidget()
    w.set_material_manager(mm)
    w.set_group_manager(gm)
    w.gm, w.mm, w.root = gm, mm, root
    yield w


@pytest.fixture()
def bound_rows(widget, monkeypatch):
    """Record every row the tree draws for a binding."""
    drawn = []
    original = GroupCompositionWidget._build_bound_row

    def spy(self, material_index, position, group):
        drawn.append(material_index)
        return original(self, material_index, position, group)

    monkeypatch.setattr(GroupCompositionWidget, "_build_bound_row", spy)
    return drawn


def _bind(widget, pattern):
    widget.gm.get_group(widget.root).source_pattern = pattern
    widget.refresh()


# ── What the binding resolves to ─────────────────────────────────────────────

def test_a_group_starts_unbound(widget):
    assert widget.gm.get_group(widget.root).source_pattern is None
    assert widget._bound_indices(widget.gm.get_group(widget.root)) is None


def test_a_bound_group_resolves_to_the_matching_materials(widget):
    _bind(widget, "*_org*")
    assert widget._bound_indices(widget.gm.get_group(widget.root)) == [2, 3, 4]


def test_a_bound_group_draws_a_row_per_matched_material(widget, bound_rows):
    _bind(widget, "*_org*")
    assert bound_rows == [2, 3, 4]


def test_a_bound_group_draws_no_rows_for_its_own_entries(widget, monkeypatch):
    drawn = []
    original = GroupCompositionWidget._build_frame_row
    monkeypatch.setattr(
        GroupCompositionWidget, "_build_frame_row",
        lambda self, e, pg, ei, d: (drawn.append((pg, ei)), original(self, e, pg, ei, d))[1],
    )
    _bind(widget, "*_org*")
    assert drawn == [], "the entries are held aside, not exported"


def test_unbinding_brings_the_entry_rows_back(widget, bound_rows):
    _bind(widget, "*_org*")
    _bind(widget, None)

    assert widget._row_dur_spin[(widget.root, 0)].isEnabled()
    assert len(widget.gm.get_group(widget.root).entries) == 2


def test_a_binding_that_matches_nothing_draws_no_rows(widget, bound_rows):
    _bind(widget, "*_walk*")
    assert bound_rows == []
    assert widget._bound_indices(widget.gm.get_group(widget.root)) == []


def test_binding_without_a_material_manager_resolves_to_nothing(widget):
    widget.set_material_manager(None)
    _bind(widget, "*_org*")
    assert widget._bound_indices(widget.gm.get_group(widget.root)) == []


# ── The header field is what sets the binding ────────────────────────────────

def test_the_field_starts_empty_and_shows_the_pattern_once_bound(widget):
    assert widget._bind_edit[widget.root].text() == ""
    _bind(widget, "*_org*")
    assert widget._bind_edit[widget.root].text() == "*_org*"


def test_typing_a_pattern_binds_the_group(widget, bound_rows):
    ed = widget._bind_edit[widget.root]
    ed.setText("*_org*")
    ed.editingFinished.emit()

    assert widget.gm.get_group(widget.root).source_pattern == "*_org*"
    assert bound_rows == [2, 3, 4], "and the tree redraws from the binding"


def test_clearing_the_field_unbinds_the_group(widget):
    _bind(widget, "*_org*")
    ed = widget._bind_edit[widget.root]
    ed.setText("")
    ed.editingFinished.emit()

    assert widget.gm.get_group(widget.root).source_pattern is None


def test_surrounding_whitespace_is_trimmed(widget):
    ed = widget._bind_edit[widget.root]
    ed.setText("  *_org*  ")
    ed.editingFinished.emit()
    assert widget.gm.get_group(widget.root).source_pattern == "*_org*"


def test_editing_the_field_makes_the_change_undoable(widget):
    fired = []
    widget.entries_changed.connect(lambda: fired.append(1))

    ed = widget._bind_edit[widget.root]
    ed.setText("*_org*")
    ed.editingFinished.emit()

    assert fired


def test_leaving_the_field_untouched_changes_nothing(widget):
    """editingFinished also fires on focus-out, and a rebuild for every glance
    at the field would delete the row being clicked."""
    _bind(widget, "*_org*")
    fired = []
    widget.entries_changed.connect(lambda: fired.append(1))

    widget._bind_edit[widget.root].editingFinished.emit()
    assert fired == []


def test_a_reference_gets_no_bind_field_of_its_own(widget):
    child = widget.gm.add_group(CompositionGroup(name="Child"))
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=child))
    widget.refresh()

    assert sorted(widget._bind_edit) == [widget.root, child]


# ── Only one of the two can be edited ────────────────────────────────────────

def test_the_add_buttons_are_off_while_the_group_is_bound(widget):
    from PyQt6.QtWidgets import QPushButton

    def add_buttons():
        # Only the live section: the one the last refresh replaced is still
        # parented here until deleteLater runs, with its old enabled state.
        section = widget._top_sections[widget.root]
        return [b for b in section.findChildren(QPushButton)
                if b.text() in ("+Frame", "+Group", "+Layer")]

    widget.refresh()
    assert all(b.isEnabled() for b in add_buttons())

    _bind(widget, "*_org*")
    assert add_buttons(), "the buttons are still drawn"
    assert not any(b.isEnabled() for b in add_buttons())


# ── The pinned pause works on a binding too ──────────────────────────────────

def test_a_bound_group_ends_on_a_frame(widget):
    _bind(widget, "*_org*")
    assert widget._has_tail_frame(widget.gm.get_group(widget.root))


def test_a_binding_that_matches_nothing_has_no_tail_frame(widget):
    _bind(widget, "*_walk*")
    assert not widget._has_tail_frame(widget.gm.get_group(widget.root))
    assert not widget._tail_chk[widget.root].isEnabled()


def test_a_bound_group_can_have_its_pause_pinned(widget):
    _bind(widget, "*_org*")

    assert widget._tail_chk[widget.root].isEnabled()
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)

    assert widget.gm.get_group(widget.root).tail_duration_ms == 2000
    assert widget._tail_spin[widget.root].isEnabled()


def test_a_bound_groups_pause_shows_the_pinned_value(widget):
    _bind(widget, "*_org*")
    widget._tail_chk[widget.root].setChecked(True)
    widget._tail_spin[widget.root].setValue(2000)
    widget.refresh()

    assert widget._tail_duration(widget.gm.get_group(widget.root)) == 2000
    assert widget._tail_spin[widget.root].value() == 2000


def test_an_unpinned_bound_group_shows_the_group_default(widget):
    root = widget.gm.get_group(widget.root)
    root.default_duration_ms = 66
    _bind(widget, "*_org*")
    assert widget._tail_duration(root) == 66


def test_refreshing_the_tail_of_a_bound_group_is_safe(widget):
    _bind(widget, "*_org*")
    widget._refresh_tail_widgets(widget.root)      # no frame row to hand over to


# ── A reference still gets no controls of its own ────────────────────────────

def test_a_reference_to_a_bound_group_draws_its_rows_once(widget, bound_rows):
    child = widget.gm.add_group(CompositionGroup(name="Child", source_pattern="*_org*"))
    widget.gm.get_group(widget.root).entries.append(SubGroupEntry(group_id=child))
    widget.refresh()

    assert bound_rows == [2, 3, 4], "only the section that owns the group draws them"
