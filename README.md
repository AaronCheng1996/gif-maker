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
- Clear a group with one button: it empties the group without deleting it, says what is
  about to go, warns when the group is referenced from more than one place (they share the
  same contents), and is undoable

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

### Batch Export

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

### Spine Export

Turns the usual "open a viewer, export MP4, convert it to GIF, repeat for every
animation" routine into: open the model, select the animations, click once.

- Load a Spine skeleton and see **every animation listed with its duration and frame count**; pick a skin if the model has several
- **Multi-select animations (Ctrl/Shift-click, or Select All) and export them all in one run** — files are named `<model>_<animation>.<ext>` into a folder you choose, with per-animation progress
- Scrubbable preview with playback
- Export options: fps, scale, transparent background, loop count, plus palette size and "Crop to animation" for the built-in engine

Two interchangeable export engines:

| | **SpineViewerCLI** (preferred) | **Built-in** |
|---|---|---|
| Spine versions | 2.1 – 4.2, `.json` and binary `.skel` | 4.x `.json` only |
| Renderer | Official Spine runtimes | This app's pure-Python runtime |
| Formats | GIF, APNG, WebP, MP4, MOV, WebM, MKV, PNG frames | GIF |
| Requires | [SpineViewer](https://github.com/ww-rm/SpineViewer/releases) on disk | nothing |

[SpineViewerCLI](https://github.com/ww-rm/SpineViewer) is auto-detected on PATH and in
common install folders; otherwise use "Locate SpineViewerCLI…" once and the path is
remembered. It bundles its own ffmpeg and writes GIF directly via `palettegen`/`paletteuse`,
so **no intermediate MP4 is produced at all** — fewer steps and better quality than
round-tripping through video. When it isn't installed the tab falls back to the built-in
renderer automatically.

The built-in runtime (`src/core/spine/`, numpy + Pillow only, no PyQt6) covers atlas parsing,
bone hierarchies with all `inherit` modes, weighted-mesh skinning, IK and transform
constraints, Bezier keyframe curves, clipping attachments, and multiply/additive/screen blend
modes. It is CPU-bound — roughly 0.4s per frame at 500px wide for a ~5000-triangle skeleton —
so prefer SpineViewerCLI for long animations at large scales.

The preview is rendered by whichever engine will do the export. Under SpineViewerCLI, picking
an animation kicks off a single `-f Frames` run that writes preview-sized PNGs into a temp
folder as it renders: the first frame appears about a second in, the rest fill in behind it
faster than they play back, and after that scrubbing and playback are just file reads — around
8ms a frame instead of the built-in renderer's 337ms. Frames stay on disk for as long as the
model is open, so flicking back to an animation you already looked at is instant. They are
rendered to fit the space the preview panel actually has — capped at 900px, and quantised so
that dragging a window edge does not throw away a rendered animation — and the displayed
frame is scaled up as well as down, so the image fills the panel instead of sitting small in
the middle of it. It also
means the preview shows exactly what the export will contain. The built-in renderer is the
fallback, used when it is the selected engine or when the CLI cannot render the model.

Models often carry layers you do not want in the output — a drop shadow, a mask that renders
as a visible blob, a background, an artist's signature. The **Slots** list under the animations
shows every slot in the model with a tick box; unticking one leaves it out of both the preview
and the export (`--disable-slots` under the CLI, skipped in the draw loop under the built-in
renderer). There is a filter box because models routinely have a hundred-plus slots, and
hiding a background also tightens the canvas, since the framing is computed from what is
actually drawn. An unticked slot always stays visible in the list, whatever the filter says,
so a hidden layer can never get lost behind a stale search.

**Premultiplied alpha** is ticked automatically from the atlas's own `pma` flag. It matters
more than it sounds: a premultiplied page stores colour already multiplied by alpha, so
rendering it as straight alpha multiplies through a second time and every partly transparent
texel comes out darkened by alpha squared. That is what black fringes around hair, soft edges
and mask attachments actually are — on one real model it dropped the mean brightness of
semi-transparent pixels from 94 to 21 out of 255. Both engines honour the flag (`--pma` for
the CLI, skipping the second multiply in the built-in draw loop), and the checkbox is there to
override a model that declares it wrongly.

### GIF to Video

Re-encodes a finished GIF as H.264 or VP9 to make it smaller. A GIF holds 256 colours per frame
and compresses each frame on its own; the same animation as H.264 typically lands three to eight
times smaller while still looking like the GIF it came from. Measured on a 7.5 MB, 134-frame GIF:
2.8 MB at the "High" preset, 1.9 MB at "Balanced", 1.2 MB at "Small".

**H.264 has no alpha channel**, and animations exported from Spine are routinely a third
transparent, so that transparency has to become some colour on the way to MP4. The tab makes that
decision visible rather than surprising: the file list marks which entries carry transparency, and
the preview shows the selected frame already composited onto the chosen background. Where the
transparency has to survive, the VP9/WebM option keeps it — roughly half the saving, still
smaller than the GIF.

Files keep the size they already have unless you say otherwise, and when a width limit is
set it is a **cap, not a target** — anything already narrower is left alone rather than
being enlarged into blur. A one-line summary above the Convert button states the whole
recipe (format, quality, sizing, background, destination), and each row shows the size it
will come out at, including the even-number rounding that 4:2:0 forces.

Worth knowing before reaching for this: **a transcode is capped by its source.** Against the
frames a Spine model actually rendered, a GIF scores 17.2 dB PSNR and so does every video made
from it, however many bits it is given; encoding those same frames straight to H.264 reaches
35.4 dB at the same file size. So this tab is the right tool for a GIF you already have — if the
animation is still in Spine, the Spine Export tab writes MP4 directly and does it far better.

### Join

Plays several clips one after another as a single file. Still not an editor &mdash; no tracks, no
transitions, no effects &mdash; but two things a join needs constantly earned their room.

**The library is separate from the timeline.** Adding a file and using a file are different acts,
so there is one list of material and a second list of uses. A clip can therefore appear on the
timeline more than once &mdash; an intro reused as an outro, one shot cut into before and after
&mdash; which a single list of paths cannot express at all. Double-click or drag from the library
to place a segment; forgetting material leaves segments already placed alone.

**Segments carry their own in and out points.** Most clips need their head and tail taken off
before they will join cleanly, and doing that in another tool first turns a one-step job into
three. Trimming is per use rather than per file, so the same material can be cut differently in
each place it appears. Trimmed segments seek before decoding, so taking four seconds out of an
hour-long capture reads four seconds of it.

The trim is a **filmstrip**, not a pair of numbers. What is actually being asked &mdash; does this
clip start after the slate, does it end before the camera swings away &mdash; is a question about
pictures, so the control is the pictures: the clip laid end to end, the kept span at full
brightness, the discarded head and tail dimmed, a handle on each boundary and a playhead. The spin
boxes are still there, because pictures are bad at exact numbers.

**Preview plays the whole join** before anything is written, and plays every frame of it. The
obvious implementation &mdash; flipping through the frames the filmstrip is already drawn from
&mdash; is far too sparse to watch, because those are sampled across each whole source: a
minute-long clip lands at two frames a second. Holding a real frame rate in memory is not an option
either, since ten seconds of 480&times;360 comes to about 160 MB.

So the preview is the join itself, built small and fast &mdash; 640px wide, ultrafast, crf 30
&mdash; and played as a file. A twelve-second join renders in under half a second and comes out at
the real 25fps rather than the strip's 12. It runs the same pipeline the export does, so it is a
true check on order, trims, framing and padding; only encoding quality at full size is left for the
real file to show. An unchanged timeline replays the file already built rather than rendering it
again. Where QtMultimedia is missing, the tab falls back to flipping through the sampled frames.

**Match the previous segment** searches the incoming clip for the frame that follows the outgoing
one most cleanly, and starts there. Closeness is three measurements rather than one, because three
different things go wrong at a cut: colour catches a change of scene, edges survive a slow exposure
drift that would swamp a pixel difference, and comparing each frame with its own neighbour catches
the case where two frames match perfectly but one is mid-pan and the other is a standstill. The
result is reported in words &mdash; seamless, close, or no good match &mdash; because the score only
means anything against the thresholds it was calibrated on.

The rest is what happens when the parts do not match, because ffmpeg's concat filter refuses
inputs that disagree on size, pixel format or sample aspect, and a sequence built from a GIF, a
phone clip and a screen capture agrees on none of them:

- **Size** is padded, never stretched. A clip of a different shape is fitted inside the output
  frame and the remainder filled &mdash; scaling a 4:3 clip into a 16:9 slot to make the numbers
  line up distorts everyone in it. The frame is taken from the first segment by default, or sized
  to hold the largest.
- **Sample aspect** is forced to 1:1 on every part, because one file claiming non-square pixels
  plays the whole join back squashed even when the stored dimensions are right.
- **Timestamps** are rebased to zero per segment. concat expects every input to start at zero, and
  a slice taken from the middle of a file otherwise arrives carrying the timestamps it had there.
- **Frame rate** levels up rather than down by default, so the smoothest clip keeps its motion
  instead of being decimated to match the worst one.
- **Sound** survives only if every clip has some, and is resampled to a common format because
  concat refuses mismatched audio just as it refuses mismatched video. Joining a silent clip to
  one with audio drifts out of sync from that seam onwards, so it is all or nothing and the
  summary says which happened.

Output is MP4 (H.264) or GIF, and both are laid over a solid colour. Transparent padding looked
tempting for GIF, but GIF resolves a transparent pixel by showing whatever was underneath it, so
the bars beside a portrait clip filled with the previous clip's background instead of going blank.

The preview shows the scrubbed frame inside the frame the join will produce, bars and all, and
says whether the playhead is inside the trim.

### Crop

Trims finished animations to a rectangle. Because the preview here *is* the file,
what you see is exactly what gets written — no render step, no guessing at framing.

- Add GIF/APNG/WebP **or video** files and drag a rectangle over the real frames, with playback to check the crop across the whole animation
- Video is decoded through ffmpeg for the preview, sampled at 10fps for up to 12 seconds; because the rectangle is stored as fractions of the frame, a sampled preview places it just as precisely as the full file would, and the pixel readout still reflects the video's true size
- The region is also editable as exact X/Y/width/height pixel values, kept in sync with the rectangle
- Across a batch the rectangle keeps its **pixel size**, not its proportions, so files of different frame sizes still come out identical — while each file remembers where its own rectangle sits, so one can be nudged without disturbing the rest (untick "Same size for every file" to let sizes vary too)
- Writes `<name>_cropped.gif` beside each source by default; optionally into a chosen folder, or overwriting the originals after a confirmation

The pixel fields commit when you leave them rather than on every keystroke: with
per-keystroke updates, replacing 200 with 1000 passed through 1000200, got clamped
to the frame, and landed on neither number.

### Image Merge

- Simple standalone tool (independent of the Composer's material library and group model): load several images and export them as one flattened PNG
- Positions images visually on the same Godot-style canvas used by the Composer (zoom/pan, drag-to-move, snap-to-grid, multi-select all reused as-is)
- Newly loaded images are staggered by 20px so overlapping ones are still individually grabbable
- "Auto Fit Size" sets the output canvas to the bounding box of all placed images
- Export composites images bottom-to-top (later-loaded = drawn on top) into a single PNG, honoring the Transparent BG setting

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
Batch Export tab — no PyQt6 import required:

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
    cropping.py                 Crops animation files to a rectangle (Pillow, or ffmpeg for video)
    concat.py                   Joins timeline segments end to end; trims, then normalises size, aspect and rate
    seam.py                     Finds the frame that follows another most cleanly (colour, edges, motion)
    spine/                      Self-contained Spine 4.x runtime (numpy + Pillow, no PyQt6)
      atlas.py                  Texture atlas parser (4.1 bounds/offsets and legacy formats)
      skeleton.py               Bones, slots, skins, world transforms, update cache
      attachments.py            Region/mesh/linked-mesh/clipping attachments, weighted skinning
      animation.py              Timelines and Bezier/stepped/linear curve evaluation
      constraints.py            One- and two-bone IK, transform constraints
      renderer.py               Textured-triangle software rasterizer -> PIL image
      loader.py                 Loads skeleton + atlas + pages into a SpineProject
      cli_backend.py            Drives SpineViewerCLI (detect, query, export)
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
    spine_to_gif_widget.py      Spine Export tool UI (animation list, preview, export)
    crop_gif_widget.py          Crop tool UI (file list, frame preview, batch crop)
    crop_overlay.py             Preview label with a draggable crop rectangle
    video_concat_widget.py      Join tool UI (library, timeline, filmstrip trim, preview playback)
    trim_bar.py                 Filmstrip with draggable in/out handles and a playhead
    image_merge_widget.py       Image Merge tool UI (stack images, flatten to PNG)
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
