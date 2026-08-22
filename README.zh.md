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
- 每個群組都有清空按鈕：只清內容、不刪群組，會先說明將移除哪些項目；若該群組被多處引用
  （它們共用同一份內容）會額外提醒，而且可以用 Ctrl+Z 復原

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

### Spine 轉 GIF（Spine to GIF）

把原本「開 viewer → 匯出 MP4 → 轉成 GIF → 下一個動畫再來一遍」的手動流程，
變成：開啟模型 → 勾選動畫 → 按一次。

- 載入 Spine 骨架後**列出所有動畫及其長度與幀數**；模型若有多個 skin 可自由切換
- **可複選動畫（Ctrl/Shift 點選，或「全選」）一次匯出全部** —— 自動命名為 `<模型>_<動畫>.<副檔名>` 存到指定資料夾，並顯示逐一進度
- 可拖曳時間軸的預覽 + 播放
- 匯出選項：fps、縮放、透明背景、循環次數；使用內建引擎時另有調色盤大小與「裁切至動畫範圍」

兩種可切換的匯出引擎：

| | **SpineViewerCLI**（優先） | **內建引擎** |
|---|---|---|
| Spine 版本 | 2.1 – 4.2，支援 `.json` 與二進位 `.skel` | 僅 4.x `.json` |
| 算圖 | 官方 Spine runtime | 本專案的純 Python runtime |
| 格式 | GIF、APNG、WebP、MP4、MOV、WebM、MKV、PNG 序列 | GIF |
| 需求 | 需要 [SpineViewer](https://github.com/ww-rm/SpineViewer/releases) | 無 |

[SpineViewerCLI](https://github.com/ww-rm/SpineViewer) 會自動從 PATH 與常見安裝路徑偵測；
找不到時按一次「Locate SpineViewerCLI…」指定即可，路徑會被記住。它自帶 ffmpeg，
並以 `palettegen`／`paletteuse` **直接輸出 GIF —— 完全不會產生中間的 MP4**，
步驟更少、品質也比繞道影片更好。未安裝時分頁會自動退回內建引擎。

內建 runtime（`src/core/spine/`，只依賴 numpy 與 Pillow，不依賴 PyQt6）涵蓋 atlas 解析、
骨骼階層（所有 `inherit` 繼承模式）、加權網格蒙皮、IK 與 transform 約束、貝茲曲線關鍵幀、
裁切遮罩，以及 multiply／additive／screen 混合模式。它是 CPU 密集運算——約 5000 三角形的
骨架在 500px 寬時每幀約 0.4 秒——因此長動畫配大尺寸建議改用 SpineViewerCLI。

預覽由「將要負責匯出的那個引擎」算圖。在 SpineViewerCLI 下，選取動畫會啟動單一次
`-f Frames`，一邊算一邊把預覽尺寸的 PNG 寫進暫存資料夾：約一秒後就看得到第一幀，
其餘影格以快過播放速度的節奏補上；之後拖曳與播放都只是讀檔——每幀約 8 毫秒，
而內建引擎是 337 毫秒。影格會在模型開啟期間留在磁碟上，因此切回看過的動畫是瞬間的。影格會依預覽面板實際可用的
空間決定算圖大小（上限 900px，並量化處理，避免拖動視窗邊緣就作廢整段算好的動畫），
顯示時也會放大而不只縮小，讓畫面填滿面板，而不是縮在正中央。
這也讓預覽所見即為匯出所得。內建引擎作為後備：選用它、或 CLI 無法算圖時才會啟用。

模型常常帶有你不想要的圖層——多餘的陰影、算成一團色塊的遮罩、背景、作者簽名。動畫列表下方的
**圖層（Slots）**清單列出模型的每個 slot 並附勾選框，取消勾選就會同時從預覽和匯出中拿掉
（CLI 用 `--disable-slots`，內建引擎則在繪製迴圈跳過）。因為模型動輒上百個 slot，清單附有
篩選框；而關掉背景還會讓畫布跟著縮緊，因為取景是依實際畫出來的內容計算的。已取消勾選的
圖層不論篩選條件為何都會保持可見，避免被過時的搜尋字串藏起來而找不回來。

**預乘 Alpha（Premultiplied alpha）**會依 atlas 自己的 `pma` 標記自動勾選。這比聽起來重要：
預乘的貼圖頁儲存的顏色已經乘過 alpha，若當成直式 alpha 算圖就會再乘一次，導致每個半透明
像素被 alpha 平方壓暗——頭髮、柔邊、遮罩附件周圍的**黑邊就是這樣來的**。在實際模型上，
半透明像素的平均亮度會從 94 掉到 21（滿值 255）。兩個引擎都會遵守這個標記（CLI 用 `--pma`，
內建引擎則在繪製迴圈跳過第二次相乘），勾選框則是留給標記錯誤的模型手動覆寫。

### GIF 轉影片（GIF to Video）

把做好的 GIF 重新編碼成 H.264 或 VP9 來縮小檔案。GIF 每幀只有 256 色且各自獨立壓縮，
換成 H.264 通常會小三到八倍，而且看起來仍和原本的 GIF 一樣。實測一個 7.5 MB、134 幀的 GIF：
「High」2.8 MB、「Balanced」1.9 MB、「Small」1.2 MB。

**H.264 沒有 alpha 通道**，而 Spine 匯出的動畫常有三分之一是透明的，那些透明處到了 MP4
一定得變成某個顏色。這個分頁讓這個決定是看得見的，而不是事後才發現：檔案清單會標出哪些
檔案含有透明，預覽也會先把選取的影格合成到你選的底色上。若透明必須保留，可以選 VP9/WebM，
縮小幅度約只有一半，但仍比 GIF 小。

**預設保持原始尺寸**；即使勾了寬度限制，那也是**上限而非目標**——比它窄的檔案會維持原樣，
不會被放大成模糊。轉檔按鈕上方有一行摘要，直接寫明格式、品質、尺寸、底色與輸出位置；
每個檔案列也會顯示它實際會輸出的尺寸，包含 4:2:0 強制偶數所造成的取整。

動手前值得知道的一點：**轉檔的品質被來源封頂。** 拿 Spine 實際算出的影格當基準，GIF 只有
17.2 dB PSNR，而任何從它轉出的影片也都停在那裡，給再多位元也一樣；同一批影格直接編成 H.264
在相同檔案大小下可以到 35.4 dB。所以這個分頁適合處理**你已經有的 GIF**——如果動畫還在 Spine，
Spine 轉 GIF 分頁可以直接輸出 MP4，效果好得多。

### 圖集還原（Atlas Unpack）

還原被遊戲存成**切格圖集**（diced atlas）的圖片。有些引擎會把每張圖切成格子、丟掉重複的格子，
再把剩下的打包成一張圖——同一個角色的四十張表情差分，成本因此和一張差不多。那張圖看起來像雜訊，
因為相鄰的格子來自圖中毫不相干的位置；要還原就必須有「哪個格子放哪裡」的對照表。

支援兩套系統，依你指向的東西自動判斷：

| | **Naninovel SpriteDicing** | **Utage `DicingTextures`** |
|---|---|---|
| 指向 | 解包工具輸出的資料夾 | 遊戲本身的 `.assets` 或 bundle |
| 對照表位置 | 每個 Sprite 的網格中，匯出的 `.json` 就夠 | ScriptableObject，解包工具通常不會匯出 |
| 需求 | 無 | [UnityPy](https://pypi.org/project/UnityPy/) |

匯出的 `.json` 只記錄圖集的數字 ID，而匯出的 PNG 完全沒有 ID，所以當一個資料夾裡有多張圖集時，
會拿一張樣本分別對每張圖集還原，挑接縫最不明顯的那個。

同一個量測也把關輸出：只有當格子邊界不比圖片本身的紋理更明顯時才會寫檔。配錯圖集不是細微差異
——在實際模型上會超出數十級——所以錯誤的還原會被回報而不是存下來。

### 裁切 GIF（Crop GIF）

把已完成的動畫裁成指定範圍。這裡的預覽**就是檔案本身**，所見即所得——不必等算圖，也不會有取景猜錯的問題。

- 加入 GIF／APNG／WebP **或影片**，直接在真實影格上拖出方框，並可播放確認整段動畫都在框內
- 影片的預覽透過 ffmpeg 解碼，以 10fps 取樣、最多 12 秒；由於裁切框是以畫面比例儲存，取樣預覽定位的精度和完整解碼相同，而像素數值仍然反映影片的真實尺寸
- 裁切範圍同時能以精確的 X／Y／寬／高像素值輸入，與方框雙向同步
- 清單中所有檔案套用同一個裁切框，適合處理同一個模型匯出的整批動畫
- 預設在來源旁輸出 `<檔名>_cropped.gif`；也可指定輸出資料夾，或在確認後直接覆蓋原檔

裁切框以比例儲存，因此尺寸不同的檔案會各自保留相同的**相對**範圍，而非固定像素尺寸。

### 圖片合併（Image Merge）

- 簡單的獨立小工具（與 Composer 的素材庫、群組模型完全獨立）：載入多張圖片，匯出成一張攤平的 PNG
- 使用與 Composer 相同的 Godot 風格畫布來擺放圖片（縮放/平移、拖曳移動、Snap to grid、多選框選全部沿用）
- 新載入的圖片會依序錯開 20px，避免完全重疊而無法個別抓取
- 「Auto Fit Size」會把輸出畫布尺寸設為所有已擺放圖片的邊界框
- 匯出時由下到上依序合成（越晚載入的疊在越上層），並遵循「Transparent BG」設定

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
    cropping.py                 將動畫檔裁切成指定範圍（Pillow，影片則用 ffmpeg）
    spine/                      自製的 Spine 4.x runtime（僅依賴 numpy + Pillow，不依賴 PyQt6）
      atlas.py                  貼圖圖集解析（4.1 的 bounds/offsets 格式與舊版格式）
      skeleton.py               骨骼、插槽、skin、世界變換、更新順序快取
      attachments.py            region／mesh／linkedmesh／clipping 附件與加權蒙皮
      animation.py              動畫時間軸與貝茲／stepped／線性曲線求值
      constraints.py            單骨與雙骨 IK、transform 約束
      renderer.py               三角形貼圖軟體光柵化器 → PIL 圖片
      loader.py                 載入骨架 + 圖集 + 貼圖頁成 SpineProject
      cli_backend.py            驅動 SpineViewerCLI（偵測、查詢、匯出）
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
    spine_to_gif_widget.py      Spine 轉 GIF 工具介面（動畫列表、預覽、匯出）
    crop_gif_widget.py          裁切 GIF 工具介面（檔案清單、影格預覽、批次裁切）
    crop_overlay.py             帶可拖曳裁切框的預覽元件
    image_merge_widget.py       圖片合併工具介面（堆疊圖片、攤平匯出 PNG）
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
