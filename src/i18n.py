"""
GIF Maker – Minimal i18n module
================================
Supports English (en) and Traditional Chinese (zh_TW).

Usage:
    from src.i18n import tr, set_language, get_language

    # At startup, load saved preference:
    from src.settings import AppSettings
    set_language(AppSettings.get("language", "en"))

    # In UI code:
    button = QPushButton(tr("Load Image"))
"""
from __future__ import annotations
from typing import Dict

# fmt: off
_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "zh_TW": {
        # ── Menu bar ──────────────────────────────────────────────────────────
        "Edit":                              "編輯",
        "Undo":                              "復原",
        "Redo":                              "重做",
        "File":                              "檔案",
        "Load Image":                        "載入圖片",
        "Load GIF":                          "載入 GIF",
        "Recent Files":                      "最近檔案",
        "Export GIF":                        "匯出 GIF",
        "Export All Groups as GIF":          "批次匯出所有群組",
        "Export Spritesheet (PNG)":          "匯出精靈圖 (PNG)",
        "Export Selected Materials":         "匯出選取的素材",
        "Export All Materials":              "匯出所有素材",
        "Auto-Save":                         "自動儲存",
        "Restore Auto-Save":                 "還原自動儲存",
        "Toggle Auto-Save":                  "切換自動儲存",
        "Exit":                              "結束",
        "Help":                              "說明",
        "About":                             "關於",
        "Settings":                          "設定",
        "Language":                          "語言",

        # ── Tabs ──────────────────────────────────────────────────────────────
        "🎬 Composer":                        "🎬 合成器",
        "✂️ Tile Splitter":                   "✂️ 切割工具",
        "⚡ Batch Processor":                 "⚡ 批次處理",
        "🔧 GIF Optimizer":                   "🔧 GIF 最佳化",
        "🎥 Video to GIF":                    "🎥 影片轉 GIF",
        "🎞️ Clip to GIF":                     "🎞️ 剪輯轉 GIF",

        # ── Material Library panel ────────────────────────────────────────────
        "Material Library":                  "素材庫",
        "Load Materials":                    "載入素材",
        "Load GIF (Extract Frames)":         "載入 GIF（提取幀）",
        "Load Multiple Images":              "載入多張圖片",
        "Sort:":                             "排序：",
        "Default":                           "預設",
        "Name (A→Z)":                        "名稱 (A→Z)",
        "Name (Z→A)":                        "名稱 (Z→A)",
        "Width (Large→Small)":               "寬度（大→小）",
        "Height (Large→Small)":              "高度（大→小）",
        "⊞ Grid":                            "⊞ 格狀",
        "☰ List":                            "☰ 列表",
        "Remove Selected":                   "移除選取",
        "Clear All":                         "清除全部",
        "➕ Add to Selected Group":           "➕ 加入選取群組",
        "📦 Add as New Group":               "📦 新增群組",
        "📦➕ Add to Selected Group as New Group": "📦➕ 在選取群組中建立子群組",
        "📦📦 Add Each as Group":             "📦📦 各自新增群組",
        "Export Materials":                  "匯出素材",
        "Export Selected Images":            "匯出選取圖片",
        "Export All Images":                 "匯出所有圖片",

        # ── Composition panel ─────────────────────────────────────────────────
        "Composition (Groups)":              "合成（群組）",

        # ── Right panel ───────────────────────────────────────────────────────
        "🎨 BG":                             "🎨 背景",
        "Frame: 0/0":                        "幀：0/0",
        "Template Manager":                  "範本管理",
        "💾 Save":                           "💾 儲存",
        "✓ Apply":                           "✓ 套用",
        "📂 Import":                         "📂 匯入",
        "💾 Export":                         "💾 匯出",
        "🗑 Remove":                         "🗑 移除",
        "Settings":                          "設定",
        "Size:":                             "尺寸：",
        "Auto":                              "自動",
        "Loop:":                             "迴圈：",
        "Transparent BG":                    "透明背景",
        "Colors:":                           "色彩：",
        "Chroma Key:":                       "去背色：",
        "None (Disabled)":                   "無（停用）",
        "🔍":                                "🔍",
        "+10":                               "+10",
        "Auto Layout":                       "自動排版",
        "Horizontal:":                       "水平：",
        "Vertical:":                         "垂直：",
        "🔧 Auto Fit Size":                  "🔧 自動適合尺寸",
        "⬅ Left":                            "⬅ 左對齊",
        "↔ Center":                          "↔ 置中",
        "➡ Right":                           "➡ 右對齊",
        "⬆ Top":                             "⬆ 上對齊",
        "↕ Middle":                          "↕ 垂直置中",
        "⬇ Bottom":                          "⬇ 下對齊",
        "🔄 Preview":                        "🔄 預覽",
        "💾 Export GIF":                     "💾 匯出 GIF",

        # ── Status bar ────────────────────────────────────────────────────────
        "Materials: 0":                      "素材：0",
        "Group: —":                          "群組：—",
        "Auto-save: ON":                     "自動儲存：開",
        "Auto-save: OFF":                    "自動儲存：關",
        "Ready":                             "就緒",

        # ── Settings dialog ───────────────────────────────────────────────────
        "Application Settings":              "應用程式設定",
        "Language Settings":                 "語言設定",
        "Interface Language:":               "介面語言：",
        "English":                           "English",
        "Traditional Chinese (繁體中文)":    "繁體中文",
        "Restart to apply language change":  "重新啟動以完整套用語言變更",
        "OK":                                "確定",
        "Cancel":                            "取消",

        # ── Common dialog strings ─────────────────────────────────────────────
        "Warning":                           "警告",
        "Error":                             "錯誤",
        "Success":                           "成功",
        "Info":                              "資訊",
        "Confirm":                           "確認",
        "Select Image":                      "選取圖片",
        "Select GIF":                        "選取 GIF",
        "Select Images":                     "選取圖片",
        "Save GIF":                          "儲存 GIF",
        "Select Export Directory":           "選取匯出資料夾",
        "New Group":                         "新增群組",
        "Add to Group":                      "加入群組",
        "Group name:":                       "群組名稱：",
        "Template name:":                    "範本名稱：",
        "Overwrite?":                        "覆蓋？",
        "Spritesheet Columns":               "精靈圖欄數",
        "About GIF Maker":                   "關於 GIF Maker",
        "No Auto-Save":                      "沒有自動儲存",
        "Auto-Save Restored":                "自動儲存已還原",
        "Restore Failed":                    "還原失敗",
        "Imported":                          "已匯入",
        "Batch Export Complete":             "批次匯出完成",
        "File Not Found":                    "找不到檔案",
    }
}
# fmt: on

_current_lang: str = "en"


def set_language(lang: str) -> None:
    """Set the active language.  Supported codes: 'en', 'zh_TW'."""
    global _current_lang
    if lang in ("en", "zh_TW"):
        _current_lang = lang


def get_language() -> str:
    """Return the current language code."""
    return _current_lang


def get_available_languages() -> list[tuple[str, str]]:
    """Return [(code, display_name), ...] for all supported languages."""
    return [
        ("en",    "English"),
        ("zh_TW", "繁體中文"),
    ]


def tr(key: str) -> str:
    """Translate *key* to the current language.  Falls back to the key itself."""
    if _current_lang == "en":
        return key
    return _TRANSLATIONS.get(_current_lang, {}).get(key, key)
