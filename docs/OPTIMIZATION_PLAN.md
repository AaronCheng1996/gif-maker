# GIF Maker 優化計畫（Optimization Plan)

> 本文件是每日自動排程（scheduled task `gif-maker-daily-optimize`）的工作清單。
> 執行規則：每次執行**只完成一個**未勾選項目，由上到下依序進行。
> 完成後將該項目勾選 `[x]`，並在項目下方加上一行 `> 完成於 YYYY-MM-DD：<簡短摘要與 commit hash>`。
> 若某項目無法完成，**不要勾選**，在下方加註 `> 受阻：<原因>`，下次執行時優先重試或跳過。

## 總體方向

1. 核心 UI 目標：把 Composer 改造成**類似 Godot 遊戲引擎場景編輯器**的操作方式 —
   一個可縮放/平移的畫布（canvas），素材以可點選、可拖曳的物件呈現，
   直接在畫布上選取素材圖並調整位置，取代目前純樹狀清單 + 數字輸入的編輯流程。
2. 其餘為程式碼健康度（拆分大檔、文件同步、測試健壯性）與進階功能。

## 工作準則（每次執行都適用）

- 開始前先執行 `pip install -r requirements.txt -r requirements-dev.txt`（若尚未安裝）。
- 實作完成後必須執行 `python -m pytest`，全部通過才能 commit。
- Commit 訊息使用現有風格（`feat:` / `fix:` / `refactor:` / `docs:` / `test:`）。
- 新增 UI 字串一律透過 `src/i18n.py` 的 `tr()`，並同時補上繁體中文翻譯。
- 遵循現有深色主題（`src/widgets/theme.py`）的顏色與樣式。
- 不要一次做多個項目；單一項目若太大，完成可獨立運作的一部分並在計畫中拆分剩餘工作。

---

## Phase 0 — 基礎整備

- [x] **P0-1 開發環境與測試健壯性**
  - `pytest.ini` 目前硬編碼 `--cov=src --cov-report=term-missing`，在沒裝 `pytest-cov` 的環境會直接無法執行任何測試。將 coverage 選項移出 `pytest.ini`（改記載於 `build_instructions.md` 或 Makefile-style 指令說明），確保乾淨環境 `python -m pytest` 可以直接跑。
  - 安裝 `requirements.txt` + `requirements-dev.txt`，執行全部測試（約 161 個），修復任何因環境造成的失敗。
  > 完成於 2026-07-08：`pytest.ini` 移除 `--cov` 選項改為純 `-q`，README.md / README.zh.md 新增「Testing」章節說明基本測試與可選的 coverage 指令；乾淨環境安裝相依套件後 `python -m pytest` 161 個測試全數通過。

- [x] **P0-2 README 與程式碼同步**
  - `README.md` / `README.zh.md` 的 Project Structure 缺少後期新增模組：`video_to_gif.py`、`clip_to_gif_widget.py`、`video_to_gif_widget.py`、`i18n.py`、`settings.py`、`settings_dialog.py`、`layer_system.py`、`sequence_editor.py`、`utils.py`。
  - 補上 Video to GIF、Clip to GIF、i18n（繁體中文）、Settings 的功能說明。
  - 說明外部工具依賴：FFmpeg（video/clip to gif）、gifsicle（optimizer），以及未安裝時的行為。
  > 完成於 2026-07-08：README.md / README.zh.md 補齊 Project Structure 缺漏模組（並核對實際路徑，如 `video_to_gif.py` 實為 `core/video_to_gif.py`），新增 Video to GIF、Clip to GIF、Settings and Language 功能說明段落，並新增「External Tool Dependencies」章節說明 FFmpeg/gifsicle 偵測方式與未安裝時的實際行為（附程式碼位置佐證）。161 個測試全數通過。

- [x] **P0-3 拆分 `src/main.py`（2046 行）**
  - 將各分頁的組裝邏輯抽出（例如 `src/widgets/composer_tab.py` 或 `src/app/` 模組），`main.py` 只保留應用程式進入點與 MainWindow 骨架。
  - 純重構、不改變行為；重構後全部測試需通過，手動確認六個分頁仍可正常載入。
  > 完成於 2026-07-08：新增 `src/main_window/` package，依職責拆成 7 個 mixin（materials_panel_mixin、composer_panel_mixin、template_mixin、menu_mixin、export_mixin、undo_mixin、status_mixin），`MainWindow` 改為多重繼承組合這些 mixin。`src/main.py` 從 2046 行降到 254 行，只保留 `__init__`/`init_ui`/`create_main_page`/`_on_tool_tab_changed`/`closeEvent`/`main()`。純搬移程式碼，無行為變更。161 個測試全數通過；並以無頭方式（無 `.show()`）實例化 `MainWindow`、逐一切換全部 6 個分頁，確認素材庫面板在 Composer/Tile Splitter 分頁間正確 reparent、其餘分頁正確隱藏，行為與重構前一致。

## Phase 1 — Godot 風格 Canvas 編輯器（核心方向）

- [x] **P1-1 CanvasWidget 骨架**
  - 新增 `src/widgets/canvas_editor.py`：基於 `QGraphicsView`/`QGraphicsScene`。
  - 功能：滾輪縮放（以游標為中心）、中鍵或空白鍵+拖曳平移、透明棋盤格背景、一個代表 GIF 輸出範圍的邊框矩形（尺寸取自目前群組輸出設定）。
  - 左下角顯示目前縮放倍率與滑鼠座標（類似 Godot 狀態列）。
  - 先以獨立 widget + 單元測試（scene 內容、座標轉換）交付，尚不需要接入主視窗。
  > 完成於 2026-07-08：新增 `src/widgets/canvas_editor.py`（`CanvasEditorWidget` + 內部 `_CanvasGraphicsView`）。滾輪以游標為錨點縮放（`AnchorUnderMouse`，限制在 5%–2000%）、中鍵或按住空白鍵+左鍵拖曳平移（手動調整捲軸，不影響未來的框選/點選邏輯）、輸出邊界矩形以棋盤格 brush 填色代表透明背景、矩形外的 scene 背景維持深色主題底色、底部狀態列顯示縮放百分比與滑鼠場景座標。已加入 `src/widgets/__init__.py` 匯出，**尚未接入主視窗**（下一步 P1-2 才會顯示素材並接上 Composer）。新增 `tests/unit/widgets/test_canvas_editor.py`（10 個測試，涵蓋輸出尺寸/scene 內容、縮放與夾限、座標轉換往返與縮放比例、滑鼠座標標籤更新）。全專案 161→171 個測試全數通過。

- [x] **P1-2 素材渲染與點選**
  - Canvas 顯示目前選取群組「目前幀」的所有 FrameEntry：每個 entry 渲染為 `QGraphicsPixmapItem`，位置對應其 x/y offset。
  - 點擊物件可選取，選取時顯示高亮外框（類似 Godot 的橘色選取框）；點空白處取消選取。
  - 將 CanvasWidget 以新分頁或 Composer 內的切換視圖接入主視窗（先求可用，佈局後續調整）。
  > 完成於 2026-07-08：`CanvasEditorWidget.set_entries()` 只渲染 `FrameEntry`（略過 `SubGroupEntry`/`LayerBlockEntry`，符合此階段範圍），依 entry 順序疊 zValue。新增 `_MaterialPixmapItem`：可選取、選取時繪製橘色（`#ff9d3d`）外框並蓋掉 Qt 預設虛線選取框，外框寬度用 cosmetic pen 保持縮放時視覺粗細一致。點空白處取消選取沿用 Qt `QGraphicsScene` 內建行為，無需額外程式碼。已接入 `MainWindow`：`create_middle_panel` 改為 `QTabWidget`（🌳 Tree / 🖼 Canvas 分頁），新增 `_refresh_canvas()` 在群組切換、entries 變更、輸出寬高變更時同步 canvas。新增 4 個測試（渲染位置/尺寸、略過非 FrameEntry、清空重繪、選取事件發射 `entry_selected` signal），並以無頭方式驗證 `MainWindow` 端到端整合（新增 entry 後 canvas 同步、調整寬度 spinbox 後 canvas 輸出範圍同步）。171→175 個測試全數通過。與樹狀編輯器的**雙向同步**（canvas 選取 → 樹上跟隨）留給 P1-3。

- [ ] **P1-3 拖曳移動與雙向同步**
  - 在 Canvas 上拖曳素材即時更新對應 entry 的 x/y offset。
  - 與現有 `GroupCompositionWidget` 樹狀編輯器雙向同步：樹上選取 → canvas 高亮；canvas 選取/移動 → 樹上跟隨與數值更新。

- [ ] **P1-4 精確操作工具**
  - 方向鍵微調（1px；Shift+方向鍵 10px）。
  - Snap to grid（可開關、格距可設定）。
  - 多選（框選/Ctrl+點選）與現有對齊按鈕（靠左、置中、靠右…）作用於多選物件。

- [ ] **P1-5 Onion Skin 疊影**
  - 在 Canvas 上以半透明方式疊加前一幀（紅色調）與後一幀（綠色調），透明度與前後幀數可調，可一鍵開關。
  - 逐幀切換時（前一幀/下一幀按鈕）canvas 即時更新。

- [ ] **P1-6 素材庫拖放新增**
  - 從素材庫（material library）直接拖放圖片到 Canvas 上，於放開位置新增 FrameEntry 至目前群組。
  - 拖曳過程顯示半透明預覽。

- [ ] **P1-7 時間軸整合**
  - Canvas 下方加入 frame scrubber（時間軸滑桿）：顯示總幀數、目前幀，可拖動跳轉。
  - 播放時 Canvas 即時逐幀更新（重用 `preview_widget` 的播放邏輯或抽出共用計時器）。

## Phase 2 — 進階功能

- [ ] **P2-1 Undo/Redo**
  - 以 `QUndoStack` 為 Composer 操作（新增/刪除 entry、移動、改 duration、改 offset）建立復原系統，Ctrl+Z / Ctrl+Y 快捷鍵。

- [ ] **P2-2 APNG / WebP 匯出**
  - 匯出面板新增格式選項：GIF（預設）、APNG、動畫 WebP（Pillow 原生支援）。
  - 依格式顯示對應選項（例如 WebP quality）。

- [ ] **P2-3 Template 縮圖預覽**
  - Template Manager 儲存範本時同時產生第一幀縮圖，選擇範本時顯示預覽。

- [ ] **P2-4 CLI 批次模式**
  - 新增 `python -m src.cli`（或 `run.py --batch`）：不開 GUI，以參數指定來源圖片、範本 JSON、輸出目錄，重用 `batch_processor.py` 邏輯，方便整合自動化管線。

---

## 進度記錄

（每次執行後由排程任務在此追加一行：日期、完成項目、commit hash）

- 2026-07-08：完成 P0-1（開發環境與測試健壯性），161 個測試全數通過。
- 2026-07-08：完成 P0-2（README 與程式碼同步），161 個測試全數通過。
- 2026-07-08：完成 P0-3（拆分 src/main.py），新增 src/main_window/ 7 個 mixin，main.py 2046→254 行，161 個測試全數通過。
- 2026-07-08：完成 P1-1（CanvasWidget 骨架），新增 src/widgets/canvas_editor.py + 10 個單元測試，171 個測試全數通過。尚未接入主視窗。
- 2026-07-08：完成 P1-2（素材渲染與點選），Canvas 接入 MainWindow（Tree/Canvas 分頁切換），175 個測試全數通過。
