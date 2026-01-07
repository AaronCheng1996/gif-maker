# GIF Maker - Animation Material Editor

A powerful GIF animation editor designed for game developers and animators, allowing you to manage and play materials like a game engine.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## Architecture

The editor uses a layered architecture for flexible animation composition:

```
Materials (素材)
    ↓
Material Groups (動畫片段)
    ↓
Layer Timeline (圖層合成)
    ↓
GIF Output
```

### Material Groups

Material Groups are reusable animation clips that combine multiple materials with playback settings:
- **Materials**: A sequence of material indices (e.g., [1, 2, 3, 4])
- **Frame Duration**: Playback speed for each frame (e.g., 100ms)
- **Loop Count**: Number of times to repeat the sequence (e.g., 3)

**Example**: A walk cycle with frames [1,2,3,4] played at 100ms per frame, looped 3 times, produces 12 total frames.

**Three Ways to Add Materials:**
1. **Add to Existing Group**: Select materials and add them to an existing group
2. **Add as New Group (Merge)**: Create a single new group from selected materials
3. **Add Each as Group**: Create separate groups for each selected material

### Layer Timeline

The Layer Timeline system enables multi-layer composition:
- **Multiple Layer Tracks**: Stack multiple animation layers
- **Per-Frame Placement**: Position materials or groups at specific coordinates
- **Single Timebase**: One main timeline controls frame duration for all layers
- **Bottom-to-Top Rendering**: Layers composite from bottom to top

### Implemented Features

1. **Material Management System**
   - Load single images as materials
   - Load GIFs and automatically extract frames
   - Batch load multiple images
   - Material preview with thumbnails and management (add, remove, clear)
   - Multi-selection support (Ctrl+click, Shift+click, drag selection)
   - Export materials as PNG files (selected or all)
   - **Create Material Groups** from selected materials

2. **Material Groups**
   - Create animation clips from material sequences
   - Configure frame duration and loop count
   - Preview total frame count and duration
   - Use groups in layer timeline like regular materials
   - **Three Ways to Add Materials:**
     - Add to existing group
     - Add as new group (merge selected materials)
     - Add each material as separate group
   - **Batch Operations:**
     - Remove multiple materials from a group at once
     - Multi-selection support (Ctrl+click, Shift+click)
   - **Group Management in Timeline:**
     - Expand/collapse groups to view materials
     - Right-click menu for edit, duplicate, remove
     - Double-click to toggle expansion
     - Visual indicators for missing materials

3. **Image Splitting Tool (Tile Splitter)**
   - Split by grid count (e.g., 4x4 grid)
   - Split by tile size (e.g., 32x32 pixels)
   - Batch split multiple images with same settings
   - Pre-select positions to keep before splitting
   - Position selector grid for easy tile selection
   - Automatically add selected tiles to material library
   - Perfect for processing game sprite sheets

4. **Layer Timeline Editor**
   - Multiple layer tracks for composition
   - Drag-and-drop frame ordering
   - Add, delete, duplicate frames
   - Customize duration for each frame (delay)
   - Batch set duration for all frames
   - Display total frame count and total duration
   - Assign materials or groups to specific layer positions

5. **Sequence Editing Features**
   - Free frame sequence arrangement
   - Repeat selected frames functionality
   - Reverse selected frames functionality
   - Multi-selection support for batch operations

6. **Real-time Preview**
   - Real-time GIF animation playback preview
   - Playback controls (play/pause/stop/previous frame/next frame)
   - Display current frame info and duration

7. **GIF Export**
   - Custom output size
   - Set loop count (0 = infinite loop)
   - Transparent background support
   - Color palette selection (256, 128, 64, 32, 16 colors)
   - Automatic file size optimization

8. **Material Export**
   - Export selected materials as PNG files
   - Export all materials at once
   - Automatic filename sanitization

9. **Timeline Template System**
   - Export current layer timeline as reusable template
   - Save frame sequences, layer positions, groups, and settings
   - Import template and apply to different materials
   - Perfect for creating similar animations with different tile sets
   - Choose between "Use First N" or "Use Selected" materials when importing
   - Version 3.0 format with Material Group support
   - **Smart Material Handling:**
     - Auto-filter out-of-range materials when applying templates
     - Display warnings for missing materials
     - Templates adapt to available material library size
   - **Simplified Settings:**
     - Only stores encoding settings (transparent_bg, color_count)
     - Output size auto-detected from materials
     - Loop count set per-export, not stored in template

10. **Graphical User Interface (GUI)**
    - Modern interface based on PyQt6
    - Three-column layout: Material Management | Layer Timeline | Preview
    - Tabbed tool panel
    - Resizable split panels

11. **Auto Layout Features**
    - **Auto Fit Size**: Automatically calculate and set output size to fit all materials
    - **6 Alignment Buttons**: Quickly align all frames/materials
      - Left, Center Horizontal, Right
      - Top, Middle Vertical, Bottom
    - **Material Groups Support**: Works seamlessly with both unified and independent offset modes
    - Batch alignment across all layer tracks and frames

12. **Group Offset Modes**
    - **Unified Mode** (default): Group moves as a single unit, all materials share same position
    - **Independent Mode**: Each material in group can have individual offset positions
    - **Visual Indicators**: 🔒 for unified mode, 🔓 for independent mode in timeline
    - **Flexible Positioning**: Choose mode when creating/editing groups

## Quick Start

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run the Program

```bash
cd src
python main.py
```

Or from the root directory:

```bash
python run.py
```

### Build as Executable (Windows)

To create a standalone `.exe` file:

```bash
# Install PyInstaller
pip install pyinstaller

# Build the executable
python build_exe.py
```

The executable will be created at `dist/GIF-Maker.exe`.

For detailed instructions, see [build_instructions.md](build_instructions.md).

## Project Structure

```
src/
├─ main.py                      # Program entry point and main window
├─ core/                        # Core functionality modules
│  ├─ __init__.py
│  ├─ utils.py                 # Common utility functions
│  ├─ image_loader.py          # Image loading, GIF extraction, splitting
│  ├─ material_group.py        # Material Group (animation clips)
│  ├─ group_manager.py         # Group management
│  ├─ layer_timeline.py        # Layer timeline editor (renamed from multi_timeline)
│  ├─ sequence_editor.py       # Simple sequence editing
│  ├─ gif_builder.py           # GIF composition and output
│  └─ template_manager.py      # Template export/import
├─ widgets/                     # UI components
│  ├─ __init__.py
│  ├─ preview_widget.py        # Preview component
│  ├─ timeline_widget.py       # Timeline component
│  ├─ group_editor_dialog.py  # Group creation dialog
│  └─ tile_editor.py           # Splitting tool component
├─ ui/                          # UI resources (reserved)
│  └─ resources/
└─ assets/                      # Test materials (reserved)
   └─ samples/
```

## License

MIT License - See LICENSE file for details

## Contact

For questions or suggestions, please contact via Issues.

## Recent Changes

### Version 3.1 - Auto Layout, Group Offset Modes & Critical Fixes

**New Features:**
- **Auto Layout System** (功能自動排版系統):
  - Auto Fit Size: Automatically calculate output size to fit all materials and groups
  - 6 alignment buttons: Left, Center, Right, Top, Middle, Bottom
  - Works across all layer tracks and frames
  - Supports both Material Groups and individual materials
  - Smart calculation handles different material sizes

- **Group Offset Modes** (群組偏移模式):
  - **Unified Mode** (統一模式): Group moves as single unit (default)
  - **Independent Mode** (獨立模式): Each material in group has individual offset
  - **Internal Offsets Storage**: Independent offsets stored within MaterialGroup
  - **Visual Indicators**: 🔒 (unified) and 🔓 (independent) icons in timeline
  - Alignment functions respect and preserve group modes

**Critical Bug Fixes:**
- **Empty Group ZeroDivisionError Fix**: Prevents crash when groups have all materials filtered out
  - Added safety checks in gif_builder expansion and rendering logic
  - Gracefully skips empty groups during GIF generation
  - Common when loading templates with out-of-range material indices

- **Batch Processor Fix**: Corrected method signature handling
  - Fixed `apply_layer_timeline_template` returning 3 values (was incorrectly receiving 2)
  - Prevents settings dict being interpreted as GroupManager object
  - Resolves "all images showing fail" issue in batch processing

**Technical Improvements:**
- MaterialGroup now supports `material_offsets: Dict[int, Tuple[int, int]]` for independent mode
- New serialization format for independent offsets (only when `independent_offsets=True`)
- Backward compatible with templates created before v3.1
- Enhanced gif_builder rendering logic to apply material-specific offsets
- Comprehensive test coverage for all new features and fixes

**Tests Added:**
- 13 integration tests for Auto Layout features
- 3 unit tests for batch processor and template manager fixes
- 2 integration tests for empty group handling and independent offsets rendering

---

### Version 3.0 - Group System & Architecture Refactoring

**New Features:**
- **Material Groups**: Create reusable animation clips from material sequences
  - Three flexible ways to add materials to groups
  - Batch material removal with multi-selection support
  - Expandable/collapsible group view in timeline
  - Right-click context menu for group operations
  
- **Group Editor Dialog**: Configure frame duration and loop count for groups
  
- **Layer Timeline Integration**: Use groups alongside materials in layer tracks
  - Visual group expansion in timeline
  - Double-click to expand/collapse groups
  - Edit, duplicate, and remove groups from timeline

- **Smart Template System**:
  - Auto-filter out-of-range materials when applying templates
  - Clear visual warnings for missing materials
  - Templates adapt to different material library sizes
  - Simplified template format (only encoding settings, no output size/loop)

**Architecture Improvements:**
- Renamed `MultiTimelineEditor` to `LayerTimelineEditor` (more accurate naming)
- Renamed `Timeline` to `LayerTrack` (clarifies purpose as layer tracks)
- Renamed `TimelineFrame` to `LayerFrame` (consistent naming)
- Updated template format to v3.0 with group support
- Maintained backward compatibility with old template formats
- Fixed group expansion and rendering (proper loop handling)

**Bug Fixes:**
- Fixed single-material group duration not being applied correctly
- Fixed missing group display showing as empty frames
- Fixed material removal from groups ("Group not found" error)
- Fixed auto-sizing when applying templates
- Fixed timeline UserRole data type issues
- Fixed output size detection in preview (respects user settings)
- Improved missing material display with color-coded warnings

**Data Flow:**
```
Materials → Groups → LayerTimeline → GIF Output
```

---