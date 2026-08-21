"""Tests for the per-group Clear button in the composition editor."""
import pytest

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.core.composition_group import (CompositionGroup, FrameEntry, SubGroupEntry,
                                        LayerBlockEntry, GroupSlot)
from src.core.group_manager import GroupManager
from src.widgets.group_composition_widget import GroupCompositionWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture()
def yes(monkeypatch):
    """Answer the confirmation with Yes, and record what it said."""
    seen = {}

    def question(_parent, title, text, *a, **k):
        seen["title"], seen["text"] = title, text
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", question)
    return seen


@pytest.fixture()
def no(monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)


@pytest.fixture()
def widget(qapp):
    w = GroupCompositionWidget()
    gm = GroupManager()
    root = gm.add_group(CompositionGroup(name="Root"))
    child = gm.add_group(CompositionGroup(name="Child"))
    gm.set_root_group_id(root)
    gm.get_group(root).entries.extend([
        FrameEntry(material_index=0),
        FrameEntry(material_index=1),
        SubGroupEntry(group_id=child),
    ])
    gm.get_group(child).entries.append(FrameEntry(material_index=2))
    w.set_group_manager(gm)
    w.gm, w.root, w.child = gm, root, child
    yield w


def test_clearing_empties_the_group_but_keeps_it(widget, yes):
    widget._cmd_clear_group(widget.root)

    assert widget.gm.get_group(widget.root).entries == []
    assert widget.gm.get_group(widget.root) is not None
    assert widget.gm.get_group(widget.root).name == "Root"
    # Only that group is touched.
    assert len(widget.gm.get_group(widget.child).entries) == 1


def test_declining_the_confirmation_changes_nothing(widget, no):
    widget._cmd_clear_group(widget.root)
    assert len(widget.gm.get_group(widget.root).entries) == 3


def test_the_confirmation_says_what_will_go(widget, yes):
    widget._cmd_clear_group(widget.root)
    text = yes["text"]
    assert "2 frame(s)" in text
    assert "1 sub-group entr(ies)" in text
    assert "Root" in text
    # Undo is the safety net, so it is worth mentioning.
    assert "Ctrl+Z" in text


def test_clearing_notifies_so_the_change_is_undoable(widget, yes, qapp):
    """The undo snapshot hangs off entries_changed, so it has to be emitted."""
    fired = []
    widget.entries_changed.connect(lambda: fired.append(1))
    widget._cmd_clear_group(widget.root)
    qapp.processEvents()
    assert fired


def test_an_empty_group_is_left_alone(widget, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.Yes)
    empty = widget.gm.add_group(CompositionGroup(name="Empty"))
    widget._cmd_clear_group(empty)
    assert not asked


def test_a_shared_group_warns_that_every_copy_is_emptied(widget, yes):
    """Sub-group entries share one object, so this is not a local edit."""
    second = widget.gm.add_group(CompositionGroup(name="Second"))
    widget.gm.get_group(second).entries.append(SubGroupEntry(group_id=widget.child))
    assert widget._reference_count(widget.child) == 2

    widget._cmd_clear_group(widget.child)
    assert "appears 2 times" in yes["text"]
    assert widget.gm.get_group(widget.child).entries == []


def test_a_group_used_once_does_not_warn(widget, yes):
    assert widget._reference_count(widget.child) == 1
    widget._cmd_clear_group(widget.child)
    assert "appears" not in yes["text"]


def test_references_from_layer_block_slots_are_counted(widget):
    block = LayerBlockEntry(timelines=[[GroupSlot(group_id=widget.child)]])
    widget.gm.get_group(widget.root).entries.append(block)
    assert widget._reference_count(widget.child) == 2


def test_clearing_an_unknown_group_is_a_no_op(widget, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.Yes)
    widget._cmd_clear_group(999)
    assert not asked


def test_clearing_without_a_manager_is_a_no_op(qapp):
    bare = GroupCompositionWidget()
    bare._cmd_clear_group(0)     # must not raise
    assert bare._reference_count(0) == 0
