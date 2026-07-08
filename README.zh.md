# GIF Maker

一款為遊戲開發者和動畫師設計的 GIF 動畫編輯器。從精靈圖（sprite sheet）組合影格序列、套用範本，並匯出 GIF。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

---

## 架構

編輯器採用以群組為主（group-led）的合成模型。素材（Material）是最基本的單位，其餘所有內容都透過 Composition Group（合成群組）來組織。

```
素材（Materials）
    |
合成群組（Composition Groups）
    FrameEntry / SubGroupEntry / LayerBlockEntry
    |
GIF 匯出
```

### 合成群組（Composition Group）

每個 `CompositionGroup` 包含一個有序的項目（entry）清單，支援三種項目類型：

- `FrameEntry` — 將單張素材放置於 (x, y) 座標，可設定獨立持續時間
- `SubGroupEntry` — 引用另一個群組，並指定循環次數與偏移量
- `LayerBlockEntry` — 多軌時間軸，逐格合成多個圖層

群組可透過 `SubGroupEntry` 巢狀嵌套，讓可重用的動畫片段組合進更大的序列中。

---

## 功能說明

### 素材管理

- 載入單張圖片（PNG、JPG、BMP）
- 載入 GIF 並將每一幀單獨解出為素材
- 批次載入多張圖片
- 素材庫支援**列表視圖**和**格狀（圖示）視圖**切換，點擊素材庫標頭的按鈕即可切換
- 依名稱或尺寸排序
- 支援 Ctrl/Shift 多選
- 匯出選取或全部素材為 PNG 檔
- **切割工具（Tile Splitter）**：依格數或固定尺寸切割精靈圖，選擇要保留的位置，直接送入素材庫

### 群組合成

- 視覺化樹狀編輯器（`GroupCompositionWidget`）顯示群組層級結構
- 可將素材加入目前選取的群組、建立新的合併群組，或為每張素材各建立一個群組
- 每個項目可設定持續時間與 x/y 偏移座標
- 透過 SubGroupEntry 將群組嵌套進其他群組，並設定獨立的循環次數與偏移量
- 透過 LayerBlockEntry 進行多圖層合成（每幀合成多個時間軸）
- 項目可展開或收合

### 預覽

- 即時播放目前選取群組的動畫預覽
- 播放控制：播放、暫停、停止、上一幀、下一幀
- 可切換單幀預覽與完整動畫預覽模式
- 全螢幕預覽頁面（點擊預覽圖或使用展開按鈕）
- 可自訂預覽背景顏色（僅影響預覽，不影響匯出）

### GIF 匯出

- 自訂輸出寬度與高度
- 循環次數（0 = 無限循環）
- 透明背景選項
- 色盤選擇：256、128、64、32 或 16 色
- **色度鍵（Chroma Key）**：分析第一幀的顏色，選取要透明化的顏色（綠幕效果）

### 自動排版

所有操作皆套用至目前選取的群組。

- **Auto Fit Size**：依群組中最大的素材自動設定輸出尺寸
- **對齊按鈕**：靠左、水平置中、靠右、靠上、垂直置中、靠下

### 範本管理

- 將目前的群組合成儲存為命名範本
- 套用已儲存的範本至目前的素材庫
- 以 JSON 格式匯入或匯出範本
- 範本儲存影格序列、偏移量、群組引用與編碼設定

### 批次處理

- 選取多張來源圖片與一個範本
- 設定切割參數（格數或尺寸）
- 一鍵處理所有圖片：切割、套用範本、匯出 GIF
- 進度條與每個檔案的處理狀態回報

### GIF 最佳化器

- 使用有損壓縮縮小 GIF 檔案大小（需要 gifsicle）
- 可調整有損值（0-200）；數值越高，檔案越小，品質越低
- 一次批次最佳化多個 GIF 檔案
- 若系統找不到 gifsicle，最佳化功能會自動改用 Pillow 重新儲存（調色盤量化 + `optimize=True`）作為替代方案 —— 功能仍可運作並縮小檔案，只是壓縮效果不如 gifsicle 的真正有損壓縮

### 影片轉 GIF（Video to GIF）

- 將影片與動態圖片檔案（mp4、mov、avi、mkv、webm、flv、wmv、m4v、ts、3gp、mts、webp、gif、apng）轉換為最佳化的 GIF
- 支援批次轉換：加入多個檔案後可單獨或一次全部轉換
- 可調整輸出 FPS、寬度、起訖裁切時間、調色盤大小（32-256 色）與抖色演算法（bayer、floyd_steinberg、sierra2、none）
- 採用兩階段 ffmpeg 調色盤產生流程以確保輸出品質，並可選擇加入 gifsicle 有損壓縮後製
- 來源與輸出並排即時預覽，設定變更後會延遲（debounce）自動重新編碼預覽
- 需要 ffmpeg —— 詳見下方「外部工具相依性」

### 剪輯轉 GIF（Clip to GIF）

- 單一影片工作流程：開啟一支影片，拖曳雙滑塊時間軸選取欲擷取的片段後匯出
- 視覺化時間範圍滑桿（含刻度標記）、拖曳式時間軸與即時同步的靜態影格預覽
- 「尋找智慧循環」（Find Smart Loop）會分析候選的起訖幀組合（比對像素、邊緣與動態差異相似度），自動修剪片段以產生無縫循環動畫
- 手動觸發、可取消的預覽產生流程（不會隨每次設定變更自動重新產生）
- 與影片轉 GIF 相同的 FPS／寬度／色彩／抖色／gifsicle 有損壓縮選項
- 需要 ffmpeg —— 詳見下方「外部工具相依性」

### 設定與語言

- 設定對話框（選單列 → 設定）目前提供介面語言選擇
- 支援英文與繁體中文；選擇會儲存於 `~/.gif_maker/settings.json`，下次啟動時自動套用
- 變更語言後會提示需要重新啟動才能完整套用變更

---

## 外部工具相依性

部分功能會呼叫外部命令列工具，這些工具**未**隨應用程式一起打包，也**未**列在 `requirements.txt` 中（因為它們不是 Python 套件）：

- **FFmpeg** —— 「影片轉 GIF」與「剪輯轉 GIF」功能所必需（用於影片解碼、影格擷取，以及兩階段調色盤 GIF 編碼）。程式透過 `shutil.which("ffmpeg")` 偵測，並在 Windows 上額外讀取登錄檔中的使用者／系統 `PATH`，因此即使在程式啟動後才透過 winget 安裝 ffmpeg，也能被偵測到而不需重啟（`src/core/video_to_gif.py`：`find_ffmpeg()`、`is_ffmpeg_available()`）。
  - **若未安裝 ffmpeg：** 兩個工具分頁會在啟動時偵測到，並顯示紅色提示（「ffmpeg not found — conversion unavailable」），附帶「How to Install FFmpeg…」按鈕（依平台顯示對應安裝方式：Windows 用 winget、macOS 用 Homebrew、Linux 用 apt/dnf/pacman）與「Refresh Detection」按鈕。轉換／匯出／產生預覽／尋找智慧循環等按鈕會保持停用直到偵測到 ffmpeg 為止。不會造成程式崩潰，其餘功能不受影響。
- **gifsicle** —— 非必要相依套件，供 GIF 最佳化器進行真正的有損壓縮，也可選擇作為「影片轉 GIF」／「剪輯轉 GIF」的後製有損壓縮步驟。程式透過 `shutil.which("gifsicle")` 偵測（`src/core/gif_optimizer.py`：`is_gifsicle_available()`）。
  - **若未安裝 gifsicle：** GIF 最佳化器會自動改用 Pillow 重新儲存（自適應調色盤量化 + `optimize=True`），而非直接失敗 —— 檔案仍會比原檔小，但壓縮效果不如真正的 gifsicle 有損壓縮（`src/core/gif_optimizer.py`：`optimize_gif_lossy()`）。在「影片轉 GIF」／「剪輯轉 GIF」中，可選的 gifsicle 後製步驟會直接被略過（`if lossy > 0 and shutil.which("gifsicle")`），僅保留 ffmpeg 產生的 GIF。

---

## 快速開始

安裝相依套件：

```bash
pip install -r requirements.txt
```

啟動程式：

```bash
python run.py
```

建立 Windows 獨立執行檔：

```bash
pip install pyinstaller
python build_exe.py
```

執行檔輸出至 `dist/GIF-Maker.exe`，詳細說明請參考 `build_instructions.md`。

---

## 批次處理 CLI（無需 GUI）

適合自動化腳本／CI 管線使用，`src/cli.py` 重用與批次處理分頁相同的 `BatchProcessor`，不需要 import PyQt6：

```bash
python -m src.cli --images sheet1.png sheet2.png --template my_template.json --output-dir out/
```

執行 `python -m src.cli --help` 查看所有參數（切割模式/格數、指定 tile 位置、色彩數、輸出尺寸覆寫等）。結束代碼：全部成功為 `0`、參數錯誤或找不到檔案為 `1`、有圖片處理失敗為 `2`。

---

## 測試

安裝開發相依套件並執行測試：

```bash
pip install -r requirements-dev.txt
python -m pytest
```

如需覆蓋率報告：

```bash
pip install pytest-cov
python -m pytest --cov=src --cov-report=term-missing
```

---

## 專案結構

```
src/
  main.py                       應用程式進入點與 MainWindow 骨架（分頁、初始化）
  cli.py                        無 GUI 的批次處理 CLI（python -m src.cli），不需要 PyQt6
  i18n.py                       輕量 i18n 模組（英文／繁體中文），提供 tr()
  settings.py                   持久化應用程式設定，以 JSON 儲存於 ~/.gif_maker/settings.json
  main_window/                  MainWindow 邏輯，依職責拆成多個 mixin
    materials_panel_mixin.py    素材庫面板：載入/列表/匯出，也是拖放到 Canvas 的來源
    composer_panel_mixin.py     Composer 中/右面板、Canvas 與樹狀編輯器同步、去背色、自動排版
    template_mixin.py           範本存/套用/匯入/匯出、縮圖、自動儲存
    menu_mixin.py                選單列、快捷鍵、最近檔案
    export_mixin.py             GIF/APNG/WebP 匯出、批次匯出、精靈圖匯出
    undo_mixin.py                快照式 Undo/Redo
    status_mixin.py              狀態列輔助函式
  core/
    utils.py                    PIL 輔助函式：ensure_rgba、resize_image、create_background、paste_center、validate_image_file
    image_loader.py             圖片載入、GIF 解幀、切割工具
    material_group.py           MaterialGroup（舊版動畫片段）
    composition_group.py        CompositionGroup 及各 Entry 型別
    group_manager.py            CompositionGroup 集合管理
    sequence_editor.py          SequenceEditor／Frame —— 簡單的有序影格序列，各幀可設定獨立持續時間
    layer_system.py             Layer／LayeredFrame／LayerCompositor —— 每個圖層的位置、裁切、縮放、透明度
    layer_timeline.py           多軌圖層時間軸模型
    gif_builder.py              GIF／APNG／WebP 合成與渲染
    gif_optimizer.py            gifsicle 有損 GIF 壓縮（若找不到 gifsicle 會改用 Pillow 重新儲存）
    video_to_gif.py             以 ffmpeg 進行影片／動態圖片轉 GIF、ffmpeg 偵測與安裝說明輔助函式
    template_manager.py         範本序列化與套用
    batch_processor.py          批次處理流程（cli.py 也重用此模組）
  widgets/
    theme.py                    全域深色主題與色盤
    canvas_editor.py             Godot 風格的 Composer 畫布：縮放/平移、拖曳移動、吸附、Onion Skin、時間軸
    group_composition_widget.py 群組樹狀編輯器（主要合成介面）
    preview_widget.py           動畫預覽
    preview_page_widget.py      全螢幕預覽頁面
    tile_editor.py              精靈圖切割工具
    batch_processor_widget.py   批次處理介面
    gif_optimizer_widget.py     GIF 最佳化介面
    video_to_gif_widget.py      影片轉 GIF 工具介面（多檔批次轉換）
    clip_to_gif_widget.py       剪輯轉 GIF 工具介面（單一影片視覺化範圍選取、智慧循環）
    settings_dialog.py          設定對話框（語言選擇）
    group_editor_dialog.py      群組建立/編輯對話框
    group_selector_dialog.py    群組選取對話框
    material_selector_dialog.py 素材選取對話框
```

---

## 授權

MIT License，詳見 `LICENSE`。

## 聯絡方式

有問題或建議請開 Issue。
