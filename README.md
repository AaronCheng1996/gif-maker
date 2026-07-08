# GIF Maker

A GIF animation editor for game developers and animators. Compose frame sequences from sprite sheets, apply templates, and export GIFs.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

---

## Architecture

The editor is built around a group-led composition model. Materials are the raw building blocks; everything else is structured through Composition Groups.

```
Materials
    |
Composition Groups  (FrameEntry / SubGroupEntry / LayerBlockEntry)
    |
GIF Export
```

### Composition Groups

A `CompositionGroup` holds an ordered list of entries. Three entry types are supported:

- `FrameEntry` — a single material placed at (x, y) with an optional duration
- `SubGroupEntry` — a reference to another group, played back with a loop count and offset
- `LayerBlockEntry` — multiple timelines composited frame-by-frame (multi-layer)

Groups can be nested via `SubGroupEntry`, enabling reusable animation clips inside larger sequences.

---

## Features

### Material Management

- Load single images (PNG, JPG, BMP)
- Load GIFs and extract all frames as individual materials
- Batch-load multiple images at once
- Thumbnail preview in list view or grid (icon) view — toggle with the button in the library header
- Sort materials by name or dimensions
- Multi-select with Ctrl/Shift-click
- Export selected or all materials as PNG files
- Tile Splitter: split sprite sheets by grid count or fixed tile size, select which positions to keep, and send tiles directly to the material library

### Group Composition

- Visual tree editor (`GroupCompositionWidget`) shows the group hierarchy
- Add materials to the currently selected group, create a new merged group, or create one group per material
- Set per-entry duration and x/y offset
- Nest groups inside other groups via SubGroupEntry with individual loop count and offset
- Multi-layer composition via LayerBlockEntry (composite several timelines at each frame)
- Collapse and expand entries inline

### Preview

- Real-time animated preview of the currently selected group
- Playback controls: play, pause, stop, previous frame, next frame
- Toggle between single-frame and full animation preview
- Full-screen preview page (click preview or use the expand button)
- Configurable background color (preview-only, does not affect export)

### GIF Export

- Custom output width and height
- Loop count (0 = infinite)
- Transparent background option
- Color palette: 256, 128, 64, 32, or 16 colors
- Chroma key (green-screen): analyze the first frame to pick a color to make transparent

### Auto Layout

All operations apply to the currently selected group.

- Auto Fit Size: set output dimensions to the largest material in the group
- Alignment buttons: Left, Center Horizontal, Right, Top, Middle Vertical, Bottom

### Template Manager

- Save the current group composition as a named template
- Apply a saved template to the current material library
- Import and export templates as JSON files
- Templates store frame sequences, offsets, group references, and encoding settings

### Batch Processor

- Select multiple source images and a template
- Configure tile-split settings (grid or size)
- Process all images in one pass: split, apply template, export GIF
- Progress bar and per-file status reporting

### GIF Optimizer

- Reduce GIF file size with lossy compression (requires gifsicle)
- Adjustable lossy value (0-200); higher value = smaller file at lower quality
- Batch optimize multiple GIF files in one step
- If gifsicle is not on PATH, optimization silently falls back to a Pillow-based
  re-save (palette quantization + `optimize=True`) — the feature keeps working,
  producing a smaller file, just without gifsicle's true lossy compression

### Video to GIF

- Convert video and animated-image files (mp4, mov, avi, mkv, webm, flv, wmv, m4v, ts, 3gp, mts, webp, gif, apng) to optimized GIFs
- Batch conversion: add multiple files, convert one or all
- Adjustable output FPS, width, start/end trim range, palette size (32-256 colors), and dithering algorithm (bayer, floyd_steinberg, sierra2, none)
- Two-pass ffmpeg palette-generation pipeline for high-quality output, with an optional gifsicle lossy post-pass
- Side-by-side source/output live preview with debounced re-encoding as settings change
- Requires ffmpeg — see "External Tool Dependencies" below

### Clip to GIF

- Single-video workflow: open one file, drag a dual-handle range slider to pick the clip, export
- Visual time-range slider with tick marks, scrub bar, and a static frame preview synced to the scrub position
- "Find Smart Loop" analyzes candidate start/end frame pairs (pixel, edge, and motion-delta similarity) to automatically trim the clip into a seamless loop
- Manual, cancellable preview generation (does not auto-regenerate on every settings change)
- Same FPS / width / color / dither / gifsicle-lossy options as Video to GIF
- Requires ffmpeg — see "External Tool Dependencies" below

### Settings and Language

- Settings dialog (menu bar → Settings) currently exposes interface language selection
- Supports English and Traditional Chinese (繁體中文); the choice is persisted to `~/.gif_maker/settings.json` and reloaded on next launch
- Changing the language shows a prompt that a restart is needed to fully apply the change

---

## External Tool Dependencies

Some features shell out to external command-line tools that are **not** bundled with the app and are **not** listed in `requirements.txt` (they are not Python packages):

- **FFmpeg** — required for the Video to GIF and Clip to GIF tools (video decoding, frame extraction, and the two-pass palette GIF encoder). Detected via `shutil.which("ffmpeg")`, with a Windows-only fallback that also reads the User/System `PATH` from the registry so a `winget install` done after app launch is picked up without an app restart (`src/core/video_to_gif.py`: `find_ffmpeg()`, `is_ffmpeg_available()`).
  - **If ffmpeg is missing:** both tool tabs detect this at startup and show a red status hint ("ffmpeg not found — conversion unavailable") with a "How to Install FFmpeg…" button (platform-specific instructions: winget on Windows, Homebrew on macOS, apt/dnf/pacman on Linux) and a "Refresh Detection" button. The Convert/Export/Generate Preview/Find Smart Loop buttons are disabled until ffmpeg is detected. No crash occurs; the rest of the app is unaffected.
- **gifsicle** — optional, used by the GIF Optimizer for true lossy compression, and optionally as a post-pass lossy step in Video to GIF / Clip to GIF. Detected via `shutil.which("gifsicle")` (`src/core/gif_optimizer.py`: `is_gifsicle_available()`).
  - **If gifsicle is missing:** the GIF Optimizer automatically falls back to a Pillow-based re-save (adaptive palette quantization + `optimize=True`) instead of failing — smaller output than the original, but not as small as true gifsicle lossy compression (`src/core/gif_optimizer.py`: `optimize_gif_lossy()`). In Video to GIF / Clip to GIF, the optional gifsicle post-pass is simply skipped (`if lossy > 0 and shutil.which("gifsicle")`) and the ffmpeg-only GIF is kept.

---

## Quick Start

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the application:

```bash
python run.py
```

Build a standalone Windows executable:

```bash
pip install pyinstaller
python build_exe.py
```

The executable is created at `dist/GIF-Maker.exe`. See `build_instructions.md` for details.

---

## Batch CLI (no GUI)

For scripting/automation pipelines, `src/cli.py` reuses the same `BatchProcessor` as the
Batch Processor tab — no PyQt6 import required:

```bash
python -m src.cli --images sheet1.png sheet2.png --template my_template.json --output-dir out/
```

Run `python -m src.cli --help` for all options (split mode/grid size, tile positions, color
count, output size overrides). Exit code is `0` on full success, `1` for bad arguments/missing
files, `2` if one or more images failed to process.

---

## Testing

Install dev dependencies and run the test suite:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

For a coverage report:

```bash
pip install pytest-cov
python -m pytest --cov=src --cov-report=term-missing
```

---

## Project Structure

```
src/
  main.py                       Application entry point and MainWindow shell (tabs, init)
  cli.py                        Headless batch CLI (python -m src.cli) — no PyQt6 required
  i18n.py                       Minimal i18n module (English / Traditional Chinese), tr()
  settings.py                   Persistent app settings, stored as JSON in ~/.gif_maker/settings.json
  main_window/                  MainWindow logic, split into mixins by responsibility
    materials_panel_mixin.py    Material library panel: load/list/export, drag source for canvas drop
    composer_panel_mixin.py     Composer middle/right panels, Canvas<->Tree sync, chroma key, auto layout
    template_mixin.py           Template save/apply/import/export, thumbnails, auto-save
    menu_mixin.py                Menu bar, shortcuts, recent files
    export_mixin.py             GIF/APNG/WebP export, batch export, spritesheet export
    undo_mixin.py                Snapshot-based undo/redo
    status_mixin.py              Status bar helpers
  core/
    utils.py                    Small PIL helpers: ensure_rgba, resize_image, create_background, paste_center, validate_image_file
    image_loader.py             Image loading, GIF extraction, tile splitting
    material_group.py           MaterialGroup (legacy animation clip)
    composition_group.py        CompositionGroup, FrameEntry, SubGroupEntry, LayerBlockEntry
    group_manager.py            Collection of CompositionGroups
    sequence_editor.py          SequenceEditor / Frame — simple ordered frame sequence with per-frame duration
    layer_system.py             Layer / LayeredFrame / LayerCompositor — per-layer position, crop, scale, opacity
    layer_timeline.py           LayerTimelineEditor (multi-track layer model)
    gif_builder.py              GIF/APNG/WebP composition and rendering
    gif_optimizer.py            Lossy GIF compression via gifsicle (falls back to Pillow re-save if gifsicle is absent)
    video_to_gif.py             FFmpeg-based video/animated-image → GIF conversion, ffmpeg detection & install-instructions helper
    template_manager.py         Template serialization and application
    batch_processor.py          Batch processing pipeline (reused by cli.py)
  widgets/
    theme.py                    Global dark theme and color palette
    canvas_editor.py             Godot-style Composer canvas: zoom/pan, drag-to-move, snap, onion skin, timeline
    group_composition_widget.py Group tree editor (main composition UI)
    preview_widget.py           Animated preview
    preview_page_widget.py      Full-screen preview page
    tile_editor.py              Sprite sheet splitting tool
    batch_processor_widget.py   Batch processor UI
    gif_optimizer_widget.py     GIF optimizer UI
    video_to_gif_widget.py      Video to GIF tool UI (multi-file batch conversion)
    clip_to_gif_widget.py       Clip to GIF tool UI (single-video visual range selector, Smart Loop)
    settings_dialog.py          Settings dialog (language selection)
    group_editor_dialog.py      Group creation/edit dialog
    group_selector_dialog.py    Group picker dialog
    material_selector_dialog.py Material picker dialog
```

---

## License

MIT License. See `LICENSE` for details.

## Contact

Open an issue for questions or suggestions.
