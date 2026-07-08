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
  main.py                       應用程式進入點與主視窗
  core/
    image_loader.py             圖片載入、GIF 解幀、切割工具
    material_group.py           MaterialGroup（舊版動畫片段）
    composition_group.py        CompositionGroup 及各 Entry 型別
    group_manager.py            CompositionGroup 集合管理
    layer_timeline.py           多軌圖層時間軸模型
    gif_builder.py              GIF 合成與渲染
    gif_optimizer.py            gifsicle 有損 GIF 壓縮
    template_manager.py         範本序列化與套用
    batch_processor.py          批次處理流程
  widgets/
    theme.py                    全域深色主題與色盤
    group_composition_widget.py 群組樹狀編輯器（主要合成介面）
    preview_widget.py           動畫預覽
    preview_page_widget.py      全螢幕預覽頁面
    tile_editor.py              精靈圖切割工具
    batch_processor_widget.py   批次處理介面
    gif_optimizer_widget.py     GIF 最佳化介面
    group_editor_dialog.py      群組建立/編輯對話框
    group_selector_dialog.py    群組選取對話框
    material_selector_dialog.py 素材選取對話框
```

---

## 授權

MIT License，詳見 `LICENSE`。

## 聯絡方式

有問題或建議請開 Issue。
