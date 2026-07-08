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
  main.py                       Application entry point and main window
  core/
    image_loader.py             Image loading, GIF extraction, tile splitting
    material_group.py           MaterialGroup (legacy animation clip)
    composition_group.py        CompositionGroup, FrameEntry, SubGroupEntry, LayerBlockEntry
    group_manager.py            Collection of CompositionGroups
    layer_timeline.py           LayerTimelineEditor (multi-track layer model)
    gif_builder.py              GIF composition and rendering
    gif_optimizer.py            Lossy GIF compression via gifsicle
    template_manager.py         Template serialization and application
    batch_processor.py          Batch processing pipeline
  widgets/
    theme.py                    Global dark theme and color palette
    group_composition_widget.py Group tree editor (main composition UI)
    preview_widget.py           Animated preview
    preview_page_widget.py      Full-screen preview page
    tile_editor.py              Sprite sheet splitting tool
    batch_processor_widget.py   Batch processor UI
    gif_optimizer_widget.py     GIF optimizer UI
    group_editor_dialog.py      Group creation/edit dialog
    group_selector_dialog.py    Group picker dialog
    material_selector_dialog.py Material picker dialog
```

---

## License

MIT License. See `LICENSE` for details.

## Contact

Open an issue for questions or suggestions.
