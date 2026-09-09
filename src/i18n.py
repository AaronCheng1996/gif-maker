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
        "🧩 Tile Splitter":                   "🧩 切割工具",
        "⚡ Batch Export":                 "⚡ 批次輸出",
        "🔧 GIF Optimizer":                   "🔧 GIF 最佳化",
        "🎥 Video to GIF":                    "🎥 影片轉 GIF",
        "🎞️ Clip to GIF":                     "🎞️ 剪輯轉 GIF",
        "🖼️ Image Merge":                     "🖼️ 圖片合併",
        "🦴 Spine Export":                    "🦴 Spine 輸出",
        "✂️ Crop":                        "✂️ 裁切",
        "📦 GIF to Video":                    "📦 GIF 轉影片",
        "🔗 Join":                    "🔗 拼接",
        "▶ Preview the join":                   "▶ 預覽拼接結果",
        "■ Stop":                               "■ 停止",
        "Building preview…":
            "正在建立預覽…",
        "Previewing the whole join — {total:.1f}s at {w}px wide":
            "預覽完整拼接——{total:.1f} 秒，寬 {w}px",
        "🔎 Match the previous segment":         "🔎 對齊前一個片段",
        "Matched at {t:.2f}s — {quality}":      "對齊於 {t:.2f} 秒——{quality}",
        "Previewing {done:.1f}s / {total:.1f}s": "預覽中 {done:.1f} / {total:.1f} 秒",
        "seamless":                             "完全連貫",
        "close":                                "接近",
        "no good match":                        "找不到合適的畫面",
        "Could not read one of the clips.":     "其中一個片段無法讀取。",
        "No frame to match against.":           "沒有可供對齊的畫面。",
        "🌳 Tree":                            "🌳 樹狀圖",
        "🖼 Canvas":                          "🖼 畫布",

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
        "Format:":                           "格式：",
        "Quality:":                          "品質：",
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

        # ── Canvas tab ────────────────────────────────────────────────────────
        "Snap":                              "吸附",
        "Prev":                              "上一個",
        "Next":                              "下一個",
        "Onion Skin":                        "洋蔥皮",
        "Opacity:":                          "透明度：",
        "Range:":                            "範圍：",

        # ── Image Merge tab ───────────────────────────────────────────────────
        "Images":                            "圖片",
        "Load Images":                       "載入圖片",
        "Output":                            "輸出",
        "Save PNG":                          "儲存 PNG",

        # ── GIF to Video tab ──────────────────────────────────────────────────
        "📂 Add Files…":                     "📂 加入檔案…",
        "Remove":                            "移除",
        "Add a GIF to see how it will look":  "加入 GIF 以預覽轉檔後的樣子",
        "This file could not be read":       "無法讀取這個檔案",
        "Transparent becomes:":              "透明處填成：",
        "Pick…":                             "選色…",
        "Background Colour":                 "背景色",
        "Resize width to":                   "縮放寬度至",
        "Save Beside Source":                "存到來源旁",
        "Choose Folder…":                    "選擇資料夾…",
        "🎬 Convert":                        "🎬 開始轉檔",
        "How to Install FFmpeg…":            "如何安裝 FFmpeg…",
        "ffmpeg found — ready to convert.":  "已找到 ffmpeg，可以轉檔。",

        # ── Video Concat tab ──────────────────────────────────────────
        "Library":                           "素材庫",
        "📂 Add Files…":                     "📂 加入檔案…",
        "Select Files":                      "選擇檔案",
        "Add to Timeline ↓":                 "加入時間軸 ↓",
        "Forget":                            "移出素材庫",
        "Remove from the library. Segments already on the timeline are left alone.":
            "從素材庫移除。已經放在時間軸上的片段不受影響。",
        "Double-click or drag a file onto the timeline.":
            "雙擊或拖曳檔案到時間軸上。",
        "Timeline":                          "時間軸",
        "Segments play top to bottom.":      "片段依由上而下的順序播放。",
        "Move up":                           "上移",
        "Move down":                         "下移",
        "Remove":                            "移除",
        "Clear":                             "清空",
        "Add files, then build a timeline":  "先加入檔案，再排出時間軸",
        "No preview":                        "無法預覽",
        "Trim this segment":                 "裁切這個片段",
        "Start":                             "起點",
        "End":                               "終點",
        "Set from playhead":                 "以目前位置設定",
        "Use the whole clip":                "使用整段",
        "Using {used:.2f}s of {total:.2f}s":  "使用 {used:.2f} 秒，共 {total:.2f} 秒",
        "Whole clip — {total:.2f}s":         "整段——{total:.2f} 秒",
        "kept":                              "保留",
        "trimmed away":                      "已裁掉",
        "padded to fit":                     "有留白",
        "Frame size":                        "畫面尺寸",
        "Frame rate":                        "影格率",
        "Auto":                              "自動",
        "Padding / background":              "留白／背景",
        "Match the first file":              "比照第一個檔案",
        "Fit the largest file":              "容納最大的檔案",
        "Put at least two segments on the timeline.": "時間軸上至少要有兩個片段。",
        "sound kept":                        "保留聲音",
        "sound dropped — not every clip has it": "已捨棄聲音——並非每個片段都有",
        "{n} padded":                        "{n} 個有留白",
        "{n} trimmed":                       "{n} 個有裁切",
        "Output Folder…":                    "輸出資料夾…",
        "Saved beside the first clip":       "輸出到第一個片段旁邊",
        "Saved to: {d}":                     "輸出到：{d}",
        "These files could not be read and would break the join:\n":
            "這些檔案無法讀取，會導致拼接失敗：\n",
        "Wrote {name} ({mb:.1f} MB)":        "已輸出 {name}（{mb:.1f} MB）",
        "🔗 Join":                           "🔗 拼接",

        # ── Spine to GIF tab ──────────────────────────────────────────────────
        "Spine Project":                     "Spine 專案",
        "📂 Open Spine Project…":            "📂 開啟 Spine 專案…",
        "Open Spine Project":                "開啟 Spine 專案",
        "No project loaded":                 "尚未載入專案",
        "Loading…":                          "載入中…",
        "Skin:":                             "外觀：",
        "Animations":                        "動畫",
        "Slots":                             "圖層",
        "Premultiplied alpha":               "預乘 Alpha",
        "Show All":                          "全部顯示",
        "Filter slots (e.g. shadow, mask, bg)": "篩選圖層（例如 shadow、mask、bg）",
        "Open a Spine project to preview":   "開啟 Spine 專案以預覽",
        "Rendering…":                        "算圖中…",
        "Rendering with SpineViewerCLI…":    "SpineViewerCLI 算圖中…",
        "Starting SpineViewerCLI…":          "正在啟動 SpineViewerCLI…",
        "SpineViewerCLI produced no frames.": "SpineViewerCLI 沒有產生任何影格。",
        "Preview unavailable":               "無法預覽",
        "Export Settings":                   "匯出設定",
        "FPS:":                              "每秒影格：",
        "Scale:":                            "縮放：",
        "Crop to animation":                 "裁切至動畫範圍",
        "Cancel":                            "取消",
        "Export Engine":                     "匯出引擎",
        "Locate SpineViewerCLI…":            "指定 SpineViewerCLI…",
        "Locate SpineViewerCLI":             "指定 SpineViewerCLI",
        "Change SpineViewerCLI path…":       "變更 SpineViewerCLI 路徑…",
        "Select All":                        "全選",
        "Files":                             "檔案",
        "📂 Add Animations…":                "📂 加入動畫檔…",
        "Add Animations":                    "加入動畫檔",
        "Add an animation to crop":          "加入要裁切的動畫",
        "The same crop is applied to every file listed.": "清單中所有檔案都會套用同一個裁切框。",
        "No preview for video files — cropping still works": "影片格式無預覽，但仍可裁切",
        "Crop Region":                       "裁切區域",
        "X:":                                "X：",
        "Y:":                                "Y：",
        "Width:":                            "寬：",
        "Height:":                           "高：",
        "Reset to full frame":               "重設為完整畫面",
        "Overwrite originals":               "覆蓋原始檔案",
        "Suffix:":                           "檔名後綴：",
        "Output folder…":                    "輸出資料夾…",
        "Same folder as each source":        "與各來源檔同一資料夾",
        "✂ Crop":                            "✂ 裁切",
        "Ctrl/Shift-click to select several, then export them all at once.":
                                             "按住 Ctrl／Shift 可複選多個動畫，一次全部匯出。",
        "💾 Export {n} animations":          "💾 匯出 {n} 個動畫",
        "💾 Export {n} stills":              "💾 匯出 {n} 張靜圖",
        "Save":                              "儲存",

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

        # ── Batch Export: working out the unit rule ───────────────────────────
        "Analyse":                           "分析",
        "Scan":                              "掃描",
        "Suggestions:":                      "建議規則：",
        "Read the file names and offer the rules that fit them, each with "
        "the number of GIFs it would actually produce.":
            "讀取檔名，列出符合的分組規則，並附上每種規則實際會產生幾個 GIF。",
        "Pick a folder of frames first.":     "請先選擇影格資料夾。",
        "No rule fits these names — write one by hand":
            "沒有規則符合這些檔名 — 請自行輸入",
        "The whole folder as one GIF":        "整個資料夾合成一個 GIF",
        "One GIF per numbered sequence":      "每一段編號序列一個 GIF",
        "Group by the first {n} part(s) of the name":
            "依檔名開頭的前 {n} 段分組",
        "{n} GIF(s), {lo}-{hi} frame(s) each":
            "{n} 個 GIF，每個 {lo}-{hi} 格",
        ", {n} file(s) skipped":              "，跳過 {n} 個檔案",
        "{n} file(s) match nothing and will not be exported, e.g. {sample}":
            "{n} 個檔案不符合規則，不會被輸出，例如 {sample}",
        "{n} unit(s) hold a single frame, e.g. {sample}":
            "{n} 個單位只有一格，例如 {sample}",
        "{n} file(s) have no frame number and may be stills, e.g. {sample}":
            "{n} 個檔案沒有影格編號，可能是靜態圖，例如 {sample}",
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
