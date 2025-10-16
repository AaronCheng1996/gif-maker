# GIF Maker - Animation Material Editor

A powerful GIF animation editor designed for game developers and animators, allowing you to manage and play materials like a game engine.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

### Implemented Features

1. **Material Management System**
   - Load single images as materials
   - Load GIFs and automatically extract frames
   - Batch load multiple images
- Material preview with thumbnails and management (add, remove, clear)
- Multi-selection support (Ctrl+click, Shift+click, drag selection)
- Export materials as PNG files (selected or all)

**NEW** - Multi-Layer Editing System
   - Switch between Simple Mode and Layered Mode
   - Create frames with multiple layers
   - Layer management: add, remove, reorder layers
   - Per-layer transformations: position, crop, scale, opacity
   - Layer visibility control
   - Automatic layer composition for preview and export

**NEW** - Advanced Image Manipulation
   - Crop layers to specific regions
   - Adjust layer position (X, Y coordinates)
   - Scale layers independently
   - Control layer opacity
   - Handle materials of different sizes with flexible positioning

2. **Image Splitting Tool (Tile Splitter)**
   - Split by grid count (e.g., 4x4 grid)
   - Split by tile size (e.g., 32x32 pixels)
   - Batch split multiple images with same settings
   - Pre-select positions to keep before splitting
   - Position selector grid for easy tile selection
   - Automatically add selected tiles to material library
   - Perfect for processing game sprite sheets

3. **Timeline Editor**
   - Drag-and-drop frame ordering
   - Add, delete, duplicate frames
   - Customize duration for each frame (delay)
   - Batch set duration for all frames
   - Display total frame count and total duration

4. **Sequence Editing Features**
   - Free frame sequence arrangement
   - Repeat selected frames functionality
   - Reverse selected frames functionality
   - Multi-selection support for batch operations

5. **Real-time Preview**
   - Real-time GIF animation playback preview
   - Playback controls (play/pause/stop/previous frame/next frame)
   - Display current frame info and duration

6. **GIF Export**
   - Custom output size
   - Set loop count (0 = infinite loop)
   - Transparent background support
   - Color palette selection (256, 128, 64, 32, 16 colors)
   - Automatic file size optimization

7. **Material Export**
   - Export selected materials as PNG files
   - Export all materials at once
   - Automatic filename sanitization

8. **Timeline Template System**
   - Export current timeline as reusable template
   - Save frame sequences, layer positions, and settings
   - Import template and apply to different materials
   - Perfect for creating similar animations with different tile sets
   - Choose between "Use First N" or "Use Selected" materials when importing

9. **Graphical User Interface (GUI)**
   - Modern interface based on PyQt6
   - Three-column layout: Material Management | Timeline | Preview
   - Tabbed tool panel
   - Resizable split panels

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
├─ main.py                    # Program entry point and main window
├─ core/                      # Core functionality modules
│  ├─ __init__.py
│  ├─ utils.py               # Common utility functions
│  ├─ image_loader.py        # Image loading, GIF extraction, splitting
│  ├─ sequence_editor.py     # Animation sequence editing
│  └─ gif_builder.py         # GIF composition and output
├─ widgets/                   # UI components
│  ├─ __init__.py
│  ├─ preview_widget.py      # Preview component
│  ├─ timeline_widget.py     # Timeline component
│  └─ tile_editor.py         # Splitting tool component
├─ ui/                        # UI resources (reserved)
│  └─ resources/
└─ assets/                    # Test materials (reserved)
   └─ samples/
```

## License

MIT License - See LICENSE file for details

## Contact

For questions or suggestions, please contact via Issues.

---