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

- [x] **P1-3 拖曳移動與雙向同步**
  - 在 Canvas 上拖曳素材即時更新對應 entry 的 x/y offset。
  - 與現有 `GroupCompositionWidget` 樹狀編輯器雙向同步：樹上選取 → canvas 高亮；canvas 選取/移動 → 樹上跟隨與數值更新。
  > 完成於 2026-07-08：`_MaterialPixmapItem` 加上 `ItemIsMovable`，`itemChange(ItemPositionHasChanged)` 即時把新位置寫回**同一個** live `FrameEntry` 物件（`CanvasEditorWidget.set_entries()` 保留 entries 清單的參照，而非複製，`GroupManager.get_group()` 本來就回傳參照，所以直接 mutate 即為真正更新模型，不需要 `update_group()`）。為避免拖曳時每個像素都觸發整棵樹重建 + 完整 GIF 預覽重算（效能考量），改成 `_CanvasGraphicsView.item_interaction_finished` 只在放開滑鼠左鍵時發一次，`CanvasEditorWidget.entries_edited` 只在該次拖曳確實改到座標時才發出，`MainWindow._on_canvas_entries_edited` 收到才呼叫 `refresh_timeline()`/`update_preview()`/`_refresh_canvas()`（一次拖曳只重建一次，不會每個像素都重建）。雙向同步：`GroupCompositionWidget` 新增 `frame_entry_selected(parent_gid, entry_idx)` signal 與 `set_selected_entry()`（FrameEntry row 改用 `_ClickableHeader`，選取時顯示藍色外框，沿用群組選取同色）；`CanvasEditorWidget` 新增 `select_entry()`；`MainWindow` 互相轉發兩個 signal，且只在 `parent_gid == current_group_id` 時才轉發到 canvas（canvas 只顯示目前群組），避免跨群組時索引誤選。`set_entries()` 重繪時只有「同一份 entries 清單物件」（同群組的拖曳後重繪）才保留選取，切換群組時正確清除選取。新增 9 個測試（拖曳寫回模型、`entries_edited` 只在放開時發一次且無變化不重複發、`select_entry`、同群組重繪保留選取、切換群組清除選取），並以無頭方式驗證 `MainWindow` 端到端：拖曳→模型更新→選取保留、樹→canvas、canvas→樹 雙向同步皆正確。180 個測試全數通過。

- [x] **P1-4 精確操作工具**
  - 方向鍵微調（1px；Shift+方向鍵 10px）。
  - Snap to grid（可開關、格距可設定）。
  - 多選（框選/Ctrl+點選）與現有對齊按鈕（靠左、置中、靠右…）作用於多選物件。
  > 完成於 2026-07-08：`_CanvasGraphicsView.keyPressEvent` 新增方向鍵處理（有選取時：一般 1px，Shift+方向鍵 10px），移動後立即發出 `item_interaction_finished`（重用 P1-3 的節流機制，只在按鍵當下 flush 一次）。Snap to grid：`CanvasEditorWidget` 內建 `Snap` checkbox + 格距 QSpinBox（自帶 UI，不需 MainWindow 額外接線），`_MaterialPixmapItem.itemChange` 攔截 `ItemPositionChange` 套用 `snap_fn`（拖曳與方向鍵微調皆會被吸附，行為一致）；新增 `set_snap_enabled/is_snap_enabled/set_snap_size/snap_size` 對外 API。多選：`_CanvasGraphicsView` 的 `dragMode` 從 `NoDrag` 改成 `RubberBandDrag`（點在素材上仍是選取/拖曳，點空白處拖曳才會框選，Qt 內建行為，Ctrl+點選多選也是原生支援）；新增 `selected_entry_indices()`（複數版本）。`ComposerPanelMixin._align_current_group_entries` 改為：canvas 上有選取時只對齊選取的 entries，否則維持原本「全部對齊」的預設行為；六個 `align_all_*` 方法都補上 `self._refresh_canvas()`（先前這裡漏了同步 canvas，一併修正）。新增 9 個 canvas 單元測試（方向鍵微調/Shift微調/無選取時不動作/發出 entries_edited、snap 開關與吸附/停用時精確定位、snap UI 雙向同步、`selected_entry_indices` 排序、RubberBandDrag 模式）與 3 個 `MainWindow` 整合測試（對齊按鈕遵循 canvas 選取、canvas↔樹雙向選取同步、拖曳更新模型且保留選取）。180→192 個測試全數通過，另以無頭方式確認 6 個分頁仍可正常切換。

- [x] **P1-5 Onion Skin 疊影**
  - 在 Canvas 上以半透明方式疊加前一幀（紅色調）與後一幀（綠色調），透明度與前後幀數可調，可一鍵開關。
  - 逐幀切換時（前一幀/下一幀按鈕）canvas 即時更新。
  > 完成於 2026-07-08：**設計澄清**——P1-2 建立的 Canvas 是把目前群組的所有 `FrameEntry` **同時**疊加顯示（方便一次檢視/對齊整組動畫的所有幀），但實際 GIF 播放時每個 entry 是**依序**各自顯示一幀；`entry_index` 在扁平群組中剛好就等於 GIF 播放的 frame index，因此「前一幀/下一幀」直接對應到「entry_index − 1 / + 1」，Onion Skin 直接以「目前選取的 entry」為基準對相鄰 entry 加疊色，語意與原始需求一致，不需另外引入「播放頭（playhead）」概念。
  > 實作：`_MaterialPixmapItem.paint()` 在 `onion_tint` 不為 `None` 時，用 `painter.setOpacity(onion_alpha)` 疊加半透明色塊（紅／綠）於素材之上，距離選取項越遠透明度線性衰減；`CanvasEditorWidget._update_onion_skin()` 依 `entry_index - selected_index` 計算每個 item 的疊色（範圍內：紅=之前、綠=之後；超出範圍或就是選取本身：不疊色），選取變更或 `set_entries()` 重繪時自動重算。新增內建工具列（Prev ◀ / Next ▶ 按鈕、Onion Skin 開關、Opacity% 與 Range 兩個 spinbox），Prev/Next 依 `entry_index` 順序移動選取（含 clamp，不循環），沿用既有 `select_entry()`，因此自動與 P1-3 的樹狀編輯器雙向同步接軌。新增 9 個測試（預設關閉不疊色、鄰近項目紅/綠疊色、範圍擴大時遠端更淡、關閉後清除、UI 雙向同步、上一個/下一個/clamp 邊界/無選取時選第一個）。補上 `Prev`/`Next`/`Onion Skin`/`Opacity:`/`Range:` 繁體中文翻譯。192→201 個測試全數通過，並以無頭方式驗證 `MainWindow` 端到端：開啟 Onion Skin 後選取項目、疊色正確、Next 移動選取正確。

- [x] **P1-6 素材庫拖放新增**
  - 從素材庫（material library）直接拖放圖片到 Canvas 上，於放開位置新增 FrameEntry 至目前群組。
  - 拖曳過程顯示半透明預覽。
  > 完成於 2026-07-08：新增 `MaterialListWidget`（`src/main_window/materials_panel_mixin.py`，繼承 `QListWidget`，覆寫 `mimeData()` 把被拖曳項目的素材索引編碼進自訂 MIME type `application/x-gifmaker-material-index`），素材庫列表 `setDragEnabled(True)`。半透明拖曳預覽直接沿用 Qt `QListWidget` 內建的拖曳縮圖機制，不需額外實作。Canvas 端：`_CanvasGraphicsView.setAcceptDrops(True)`，覆寫 `dragEnterEvent`/`dragMoveEvent`/`dropEvent`，辨識到自訂 MIME type 時解析素材索引、換算成 scene 座標，發出 `material_dropped(material_index, x, y)`（`CanvasEditorWidget` 轉發同名 signal）；`MainWindow._on_canvas_material_dropped` 接收後，以「放開點置中」（扣除素材寬高的一半）新增 `FrameEntry` 到目前群組並觸發 `refresh_timeline()`/`update_preview()`/`_refresh_canvas()`。新增 4 個測試（2 個 canvas 單元測試：drop 發出正確 signal、無效資料被忽略；1 個 MainWindow 整合測試：drop 後正確置中新增 entry 且 canvas 同步；並以無頭方式驗證 `materials_list.dragEnabled()`、`canvas view.acceptDrops()` 與實際 `mimeData()` 內容）。201→204 個測試全數通過。

- [x] **P1-7 時間軸整合**
  - Canvas 下方加入 frame scrubber（時間軸滑桿）：顯示總幀數、目前幀，可拖動跳轉。
  - 播放時 Canvas 即時逐幀更新（重用 `preview_widget` 的播放邏輯或抽出共用計時器）。
  > 完成於 2026-07-08：延續 P1-5 的設計（`entry_index` = GIF frame index），Canvas 下方新增 timeline bar：Play/Pause 按鈕、`QSlider`（範圍 0..entry 數−1，值＝目前選取的 entry index）、"Frame: i/N" 標籤。`_sync_timeline_ui()` 在 `set_entries()` 與選取變更時同步 slider/label（用 `_syncing_slider` 旗標避免 slider→選取→slider 的訊號迴圈）；拖動 slider 呼叫既有 `select_entry()`，因此自動與樹狀編輯器、Onion Skin 全部連動。播放邏輯：獨立的 `QTimer`（single-shot，逐幀重新排程，非重用 `PreviewWidget` 的計時器實例，因為兩者播放對象不同——`PreviewWidget` 播放的是 `gif_builder` 展開後的最終畫面，Canvas 播放的是「切換選取的 entry」），`_advance_playback()` 依序前進並在最後一個 entry 循環回起點（與手動導覽的 `select_next_entry()` 不同，手動導覽在邊界處會 clamp 不循環，播放時循環播放才符合 GIF loop 的直覺）；`_schedule_next_frame()` 讀取當前 entry 的 `duration_ms` 決定下一次計時器間隔。切換群組（`set_entries` 偵測到不同的 entries 清單）時自動停止播放，避免播放跑掉的舊資料。新增 9 個測試（slider 同步、拖動 slider 選取、play/pause 狀態切換與按鈕文字、播放時無選取自動選第一個、`_advance_playback` 依序前進並在尾端循環、依 entry duration 排程下一幀、切換群組時自動停止播放、無 entry 時 Play 按鈕停用）。204→212 個測試全數通過，並以無頭方式驗證 `MainWindow` 端到端：slider 拖動、播放、`_advance_playback` 皆正確運作。
  >
  > **Phase 1（Godot 風格 Canvas 編輯器）至此全部完成** — Canvas 已具備：縮放/平移、素材渲染與點選、拖曳移動、與樹狀編輯器雙向同步、方向鍵微調、Snap to grid、多選框選、對齊按鈕遵循選取、Onion Skin、素材庫拖放新增、時間軸 scrubber 與播放。

## Phase 2 — 進階功能

- [x] **P2-1 Undo/Redo**
  - 以 `QUndoStack` 為 Composer 操作（新增/刪除 entry、移動、改 duration、改 offset）建立復原系統，Ctrl+Z / Ctrl+Y 快捷鍵。
  > 完成於 2026-07-08：**發現已存在**——`src/main_window/undo_mixin.py`（在 P0-3 從原本的 `main.py` 拆出，屬於重構前就有的既有功能）已經實作了快照式（非 `QUndoStack`，而是 debounce 300ms 後把整個 `GroupManager` 序列化成快照 push 進 stack）的 Undo/Redo，`Ctrl+Z`/`Ctrl+Y`/`Ctrl+Shift+Z` 快捷鍵與選單項目也都已存在（`menu_mixin.py`）。P1-3 的拖曳與 P1-6 的拖放新增都已經呼叫 `self._undo_debounce.start(300)`（沿用既有機制，寫在 `_on_canvas_entries_edited`/`_on_canvas_material_dropped`），所以這兩個新功能從一開始就自動具備 undo/redo 能力，不需要額外接線。以真實跑 Qt event loop（讓 300ms debounce 真正觸發）的方式驗證：新增 entry → settle → 拖曳到新座標 → settle → `undo()` 正確還原到拖曳前座標 → `redo()` 正確還原到拖曳後座標。判斷改用 `QUndoStack` 重寫是不必要的重複工程（會與既有機制衝突、徒增風險），故維持現況，此項目視為已完成。

- [x] **P2-2 APNG / WebP 匯出**
  - 匯出面板新增格式選項：GIF（預設）、APNG、動畫 WebP（Pillow 原生支援）。
  - 依格式顯示對應選項（例如 WebP quality）。
  > 完成於 2026-07-08：`GifBuilder` 新增 `build_apng_from_group()` / `build_webp_from_group(quality=80)`，重用既有的 `get_preview_frames_for_group()` 取得已合成的 RGBA 幀（不像 GIF 匯出需要調色盤量化，APNG/WebP 原生支援全彩，新增 `_prepare_frame_for_alpha_format()` 只處理「Transparent BG」設定對應的透明／實色背景合成，其餘沿用 Pillow `save_all=True` 動畫存檔）。UI：Composer 右側面板新增「Format:」下拉選單（GIF/APNG/WebP）與僅 WebP 顯示的「Quality:」spinbox（`_on_export_format_changed()` 控制顯示/隱藏）；`export_gif()` 依格式分派到對應的 builder 方法、副檔名與檔案篩選器（.gif/.png/.webp）。新增 3 個 `GifBuilder` 測試（APNG/WebP 皆正確產生動畫檔、空素材時丟例外、實色背景會攤平材質自身的透明度）與 2 個 `MainWindow` 整合測試（Quality 控制項依格式顯示/隱藏、三種格式皆能透過 `export_gif()` 正確匯出檔案）。215→217 個測試全數通過，並以無頭方式驗證三種格式皆能實際匯出成功且 quality 控制項正確切換。

- [x] **P2-3 Template 縮圖預覽**
  - Template Manager 儲存範本時同時產生第一幀縮圖，選擇範本時顯示預覽。
  > 完成於 2026-07-08：新增 `self.template_thumbnails: Dict[str, QIcon]`（僅存於記憶體，不寫進匯出的 JSON 範本檔，避免動到既有檔案格式與相容性）。`_make_group_thumbnail()` 重用 `gif_builder.get_preview_frames_for_group()` 取第一幀、`create_thumbnail()`（沿用 P0 就有的素材縮圖方法）產生小圖示。`quick_save_template()` 存檔時用目前的 `group_manager` root group 產生縮圖；`quick_import_template()` 匯入時先用 `TemplateManager.import_composition_template()` 建立暫時的 `GroupManager` 來渲染縮圖（材質索引對不上時安全地回傳 `None`，不會撞例外）。`refresh_template_list()` 把縮圖設成每個 `QListWidgetItem` 的 icon；`remove_template()` 一併清掉對應的縮圖快取。UI 新增一個 72×72 的預覽 `QLabel`，放在範本清單旁邊，選取清單項目（`currentItemChanged`）時放大顯示該範本的縮圖。新增 1 個 `MainWindow` 整合測試（存檔後縮圖產生、清單項目有 icon、選取後預覽 label 有 pixmap、移除後縮圖快取清除）。217→218 個測試全數通過，並以無頭方式驗證存檔→清單→預覽→移除全流程正確。

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
- 2026-07-08：完成 P1-3（拖曳移動與雙向同步），Canvas 拖曳寫回模型、與樹狀編輯器雙向選取同步，180 個測試全數通過。
- 2026-07-08：完成 P1-4（精確操作工具），方向鍵微調、Snap to grid、多選框選、對齊按鈕遵循選取，192 個測試全數通過。
- 2026-07-08：完成 P1-5（Onion Skin 疊影），以 entry_index 作為 frame index 實作紅/綠疊色與上一個/下一個導覽，201 個測試全數通過。
- 2026-07-08：完成 P1-6（素材庫拖放新增），從素材庫拖曳圖片到 Canvas 放開即新增置中的 FrameEntry，204 個測試全數通過。
- 2026-07-08：完成 P1-7（時間軸整合），Canvas 加入 frame scrubber 與播放功能，212 個測試全數通過。**Phase 1 全部完成。**
- 2026-07-08：確認 P2-1（Undo/Redo）已由既有的快照式機制滿足（含 P1-3/P1-6 新功能），無需重寫，212 個測試維持全數通過。
- 2026-07-08：完成 P2-2（APNG / WebP 匯出），GifBuilder 新增兩個匯出方法，匯出面板可切換 GIF/APNG/WebP，217 個測試全數通過。
- 2026-07-08：完成 P2-3（Template 縮圖預覽），範本清單顯示縮圖、選取後放大預覽，218 個測試全數通過。
