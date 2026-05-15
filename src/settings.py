"""
GIF Maker – Persistent Application Settings
=============================================
Stores settings as JSON in ~/.gif_maker/settings.json.

Usage:
    from src.settings import AppSettings

    AppSettings.load()                      # call once at startup
    lang = AppSettings.get("language", "en")
    AppSettings.set("language", "zh_TW")
    AppSettings.save()
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SETTINGS_DIR  = Path.home() / ".gif_maker"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

_data: dict[str, Any] = {}


def load() -> None:
    """Load settings from disk (silently ignores missing / corrupt files)."""
    global _data
    try:
        if _SETTINGS_FILE.exists():
            _data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        _data = {}


def save() -> None:
    """Persist current settings to disk."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[settings] save failed: {exc}")


def get(key: str, default: Any = None) -> Any:
    """Return the value for *key*, or *default* if absent."""
    return _data.get(key, default)


def set(key: str, value: Any) -> None:  # noqa: A001
    """Write *value* for *key* and immediately persist to disk."""
    _data[key] = value
    save()
