"""
Template Manager - Export and import composition templates (v4 format).

Templates capture the full GroupManager state (all CompositionGroups,
root_group_id) plus render settings. Material indices are positional
references so the same template can be applied to different tile sets.
"""

import json
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .composition_group import (
    group_to_dict, group_from_dict, max_material_index, remap_material_indices,
)
from .group_manager import GroupManager


FORMAT = "composition_group"
VERSION = "4.0"


class TemplateManager:
    """
    Export / import CompositionGroup templates (JSON).

    Template schema
    ───────────────
    {
      "version": "4.0",
      "format": "composition_group",
      "settings": {
        "transparent_bg": bool,
        "color_count": int        # 16 / 32 / 64 / 128 / 256
      },
      "root_group_id": int | null,
      "groups": [
        {
          "id": int,
          "name": str,
          "default_duration_ms": int,
          "entries": [
            { "type": "frame",     "material_index": int, "x": int, "y": int, "duration_ms": int|null },
            { "type": "subgroup",  "group_id": int, "loop_count": int, "x": int, "y": int,
                                   "duration_override_ms": int|null },
            { "type": "layerblock","default_duration_ms": int,
              "timelines": [
                [ {"type": "frameslot", "material_index": int, "x": int, "y": int}, ... ],
                [ {"type": "groupslot", "group_id": int, "loop_count": int, "x": int, "y": int}, ... ]
              ]
            }
          ]
        },
        ...
      ]
    }
    """

    # ── Export ────────────────────────────────────────────────────────────────

    @staticmethod
    def export_composition_template(
        group_manager: GroupManager,
        transparent_bg: bool = False,
        color_count: int = 256,
    ) -> Dict[str, Any]:
        """Serialize a GroupManager into a template dict."""
        groups_list = []
        for gid, group in enumerate(group_manager.groups):
            groups_list.append(group_to_dict(gid, group))

        return {
            "version": VERSION,
            "format": FORMAT,
            "settings": {
                "transparent_bg": transparent_bg,
                "color_count": color_count,
            },
            "root_group_id": group_manager.get_root_group_id(),
            "groups": groups_list,
        }

    # ── Import ────────────────────────────────────────────────────────────────

    @staticmethod
    def import_composition_template(
        template: Dict[str, Any],
        material_index_mapping: Optional[Dict[int, int]] = None,
    ) -> Tuple[GroupManager, Dict[str, Any]]:
        """
        Deserialize a template dict back into a GroupManager.

        Args:
            template: Template dict (must be format "composition_group").
            material_index_mapping: Optional {old_idx: new_idx} remapping for
                                    applying the template to a different tile set.

        Returns:
            (GroupManager, settings_dict)
        """
        if template.get("format") != FORMAT:
            raise ValueError(
                f"Expected format={FORMAT!r}, got {template.get('format')!r}"
            )

        gm = GroupManager()
        for group_data in template.get("groups", []):
            gm.add_group(group_from_dict(group_data))

        root = template.get("root_group_id")
        if root is not None and 0 <= root < len(gm.groups):
            gm.set_root_group_id(root)

        if material_index_mapping:
            remap_material_indices(gm, material_index_mapping)

        settings = dict(template.get("settings", {}))
        return gm, settings

    # ── File I/O ──────────────────────────────────────────────────────────────

    @staticmethod
    def save_template_to_file(template: Dict[str, Any], file_path: str) -> None:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_template_from_file(file_path: str) -> Dict[str, Any]:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── Info & validation ─────────────────────────────────────────────────────

    @staticmethod
    def get_template_info(template: Dict[str, Any]) -> Dict[str, Any]:
        """Return a summary dict for display in the UI."""
        if template.get("format") == FORMAT:
            groups = template.get("groups", [])
            settings = template.get("settings", {})

            # Count total frame entries across all groups
            total_frames = 0
            total_subgroups = 0
            total_layerblocks = 0
            mat_indices: set = set()

            def _scan_entries(entries):
                nonlocal total_frames, total_subgroups, total_layerblocks
                for e in entries:
                    t = e.get("type")
                    if t == "frame":
                        total_frames += 1
                        mat_indices.add(e.get("material_index", 0))
                    elif t == "subgroup":
                        total_subgroups += 1
                    elif t == "layerblock":
                        total_layerblocks += 1
                        for tl in e.get("timelines", []):
                            for s in tl:
                                if s.get("type") == "frameslot":
                                    mat_indices.add(s.get("material_index", 0))

            for g in groups:
                _scan_entries(g.get("entries", []))

            return {
                "version": template.get("version", VERSION),
                "format": FORMAT,
                "group_count": len(groups),
                "root_group_id": template.get("root_group_id"),
                "total_frame_entries": total_frames,
                "total_subgroup_entries": total_subgroups,
                "total_layerblock_entries": total_layerblocks,
                "unique_material_indices": sorted(mat_indices),
                "materials_needed": (max(mat_indices) + 1) if mat_indices else 0,
                "transparent_bg": settings.get("transparent_bg", False),
                "color_count": settings.get("color_count", 256),
            }

        raise ValueError(
            f"Unsupported template format: {template.get('format')!r} "
            f"(expected {FORMAT!r})"
        )

    @staticmethod
    def validate_template(template: Dict[str, Any]) -> bool:
        """
        Validate that a template has the required structure.

        Raises ValueError if invalid, returns True if valid.
        """
        if not isinstance(template, dict):
            raise ValueError("Template must be a dict")
        if "version" not in template:
            raise ValueError("Template missing 'version'")
        if template.get("format") != FORMAT:
            raise ValueError(
                f"Unsupported format {template.get('format')!r}; "
                f"expected {FORMAT!r}"
            )
        if "groups" not in template:
            raise ValueError("Template missing 'groups'")
        return True

    @staticmethod
    def estimate_required_tiles(template: Dict[str, Any]) -> int:
        """Return max_material_index + 1 for the template (tiles needed for batch)."""
        if template.get("format") != FORMAT:
            return 0
        info = TemplateManager.get_template_info(template)
        return info.get("materials_needed", 0)
