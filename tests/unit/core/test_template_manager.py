"""
Unit tests for TemplateManager (composition_group format v4.0)
"""
import json
import pytest
from pathlib import Path

from src.core.template_manager import TemplateManager, FORMAT, VERSION
from src.core.group_manager import GroupManager
from src.core.composition_group import (
    CompositionGroup, FrameEntry, SubGroupEntry, LayerBlockEntry,
    FrameSlot, GroupSlot,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gm() -> GroupManager:
    """Build a small GroupManager with two groups for reuse across tests."""
    gm = GroupManager()

    root = CompositionGroup(name="Root", default_duration_ms=100)
    root.entries.append(FrameEntry(material_index=0, x=5, y=10, duration_ms=150))
    root.entries.append(SubGroupEntry(group_id=1, loop_count=2, x=0, y=0))
    root.entries.append(
        LayerBlockEntry(
            timelines=[
                [FrameSlot(material_index=1, x=0, y=0)],
                [FrameSlot(material_index=2, x=10, y=20)],
            ],
            default_duration_ms=80,
        )
    )
    gm.add_group(root)

    sub = CompositionGroup(name="Sub", default_duration_ms=200)
    sub.entries.append(FrameEntry(material_index=3, x=0, y=0))
    gm.add_group(sub)

    return gm


# ── Export ────────────────────────────────────────────────────────────────────

def test_export_format_and_version():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    assert tpl["format"] == FORMAT
    assert tpl["version"] == VERSION
    assert tpl["root_group_id"] == 0
    assert len(tpl["groups"]) == 2


def test_export_settings():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm, transparent_bg=True, color_count=64)
    assert tpl["settings"]["transparent_bg"] is True
    assert tpl["settings"]["color_count"] == 64


def test_export_group_entries():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    root_entries = tpl["groups"][0]["entries"]
    assert root_entries[0] == {
        "type": "frame", "material_index": 0, "x": 5, "y": 10, "duration_ms": 150
    }
    assert root_entries[1]["type"] == "subgroup"
    assert root_entries[1]["group_id"] == 1
    assert root_entries[1]["loop_count"] == 2
    assert root_entries[2]["type"] == "layerblock"
    assert len(root_entries[2]["timelines"]) == 2


# ── Round-trip ────────────────────────────────────────────────────────────────

def test_roundtrip():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm, transparent_bg=True, color_count=128)
    gm2, settings = TemplateManager.import_composition_template(tpl)

    assert isinstance(gm2, GroupManager)
    assert isinstance(settings, dict)
    assert settings["transparent_bg"] is True
    assert settings["color_count"] == 128

    assert len(gm2.groups) == len(gm.groups)
    assert gm2.get_root_group_id() == 0

    root2 = gm2.groups[0]
    assert root2.name == "Root"
    assert len(root2.entries) == 3
    assert isinstance(root2.entries[0], FrameEntry)
    assert root2.entries[0].material_index == 0
    assert root2.entries[0].duration_ms == 150
    assert isinstance(root2.entries[1], SubGroupEntry)
    assert root2.entries[1].loop_count == 2
    assert isinstance(root2.entries[2], LayerBlockEntry)
    assert len(root2.entries[2].timelines) == 2

    sub2 = gm2.groups[1]
    assert sub2.name == "Sub"
    assert sub2.entries[0].material_index == 3


# ── File I/O ──────────────────────────────────────────────────────────────────

def test_save_load_file(tmp_path):
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    path = str(tmp_path / "template.json")
    TemplateManager.save_template_to_file(tpl, path)
    loaded = TemplateManager.load_template_from_file(path)
    assert loaded["format"] == FORMAT
    assert len(loaded["groups"]) == 2


# ── get_template_info ─────────────────────────────────────────────────────────

def test_get_template_info():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    info = TemplateManager.get_template_info(tpl)
    assert info["format"] == FORMAT
    assert info["group_count"] == 2
    # Materials 0,1,2,3 → max=3, needed=4
    assert info["materials_needed"] == 4
    assert isinstance(info["unique_material_indices"], list)


def test_get_template_info_wrong_format():
    with pytest.raises(ValueError, match="Unsupported"):
        TemplateManager.get_template_info({"format": "old_format", "version": "3.0"})


# ── validate_template ─────────────────────────────────────────────────────────

def test_validate_ok():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    assert TemplateManager.validate_template(tpl) is True


def test_validate_wrong_format():
    with pytest.raises(ValueError):
        TemplateManager.validate_template({"version": "4.0", "format": "old", "groups": []})


def test_validate_missing_groups():
    with pytest.raises(ValueError, match="groups"):
        TemplateManager.validate_template({"version": "4.0", "format": FORMAT})


# ── estimate_required_tiles ───────────────────────────────────────────────────

def test_estimate_required_tiles():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    assert TemplateManager.estimate_required_tiles(tpl) == 4  # max index = 3


def test_estimate_required_tiles_empty():
    gm = GroupManager()
    gm.add_group(CompositionGroup(name="Empty"))
    tpl = TemplateManager.export_composition_template(gm)
    assert TemplateManager.estimate_required_tiles(tpl) == 0


# ── material_index_mapping ────────────────────────────────────────────────────

def test_import_with_material_mapping():
    gm = _make_gm()
    tpl = TemplateManager.export_composition_template(gm)
    mapping = {0: 10, 1: 11, 2: 12, 3: 13}
    gm2, _ = TemplateManager.import_composition_template(tpl, material_index_mapping=mapping)
    root2 = gm2.groups[0]
    assert root2.entries[0].material_index == 10
    assert root2.entries[2].timelines[0][0].material_index == 11
    assert root2.entries[2].timelines[1][0].material_index == 12
    sub2 = gm2.groups[1]
    assert sub2.entries[0].material_index == 13
