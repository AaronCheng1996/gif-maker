# GIF Maker - Animation Material Editor

A powerful GIF animation editor designed for game developers and animators, allowing you to manage and play materials like a game engine.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

## ✨ Core Features

### 🎯 Implemented Features

1. **Material Management System**
   - ✅ Load single images as materials
   - ✅ Load GIFs and automatically extract frames
   - ✅ Batch load multiple images
   - ✅ Material preview with thumbnails and management (add, remove, clear)
   - ✅ Multi-selection support (Ctrl+click, Shift+click, drag selection)

2. **Image Splitting Tool (Tile Splitter)**
   - ✅ Split by grid count (e.g., 4x4 grid)
   - ✅ Split by tile size (e.g., 32x32 pixels)
   - ✅ Automatically add split tiles to material library
   - ✅ Perfect for processing game sprite sheets

3. **Timeline Editor**
   - ✅ Drag-and-drop frame ordering
   - ✅ Add, delete, duplicate frames
   - ✅ Customize duration for each frame (delay)
   - ✅ Batch set duration for all frames
   - ✅ Display total frame count and total duration

4. **Sequence Editing Features**
   - ✅ Free frame sequence arrangement
   - ✅ Repeat selected frames functionality
   - ✅ Reverse selected frames functionality
   - ✅ Multi-selection support for batch operations

5. **Real-time Preview**
   - ✅ Real-time GIF animation playback preview
   - ✅ Playback controls (play/pause/stop/previous frame/next frame)
   - ✅ Display current frame info and duration

6. **GIF Export**
   - ✅ Custom output size
   - ✅ Set loop count (0 = infinite loop)
   - ✅ Transparent background support
   - ✅ Automatic GIF file size optimization

7. **Graphical User Interface (GUI)**
   - ✅ Modern interface based on PyQt6
   - ✅ Three-column layout: Material Management | Timeline | Preview
   - ✅ Tabbed tool panel
   - ✅ Resizable split panels

## 🚀 Quick Start

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

## 📖 User Guide

### Basic Workflow

1. **Load Materials**
   - Click "Load Image" to load a single image
   - Or use "Load GIF" to load and extract GIF frames
   - Or use "Load Multiple Images" to batch load
   - Select multiple materials with Ctrl+click or Shift+click

2. **Split Sprite Sheet (Optional)**
   - Switch to "Tile Splitter" tab
   - Load the image to split
   - Choose splitting method (grid count or tile size)
   - Click split button, tiles will automatically be added to material library

3. **Edit Timeline**
   - Select one or more materials from the list
   - Click "Add to Timeline" to add to timeline
   - Drag frames to reorder
   - Select multiple frames with Ctrl+click or Shift+click
   - Adjust frame duration for selected frames

4. **Preview and Adjust**
   - Set output size and loop count
   - Enable "Transparent Background" if needed
   - Click "Update Preview" to view effects
   - Use playback controls to test animation

5. **Export GIF**
   - Click "Export GIF" to save file

### Advanced Features

#### Repeat Selected Frames

Select one or more frames and repeat them multiple times:
- Select frames: Frame 1, Frame 2, Frame 3
- Set repeat count to 3
- Result: Original frames followed by 2 more copies of the selected frames

#### Reverse Selected Frames

Select a range of frames and reverse their order:
- Original: Frame 1 → Frame 2 → Frame 3 → Frame 4
- Select Frame 2 to Frame 4 and reverse
- Result: Frame 1 → Frame 4 → Frame 3 → Frame 2

This is useful for creating back-and-forth animations or correcting frame order.

## 📁 Project Structure

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

## 🎨 Core Architecture

### MaterialManager
- Manages all imported materials
- Supports images, GIF frames, split tiles
- Provides CRUD interfaces for materials

### SequenceEditor
- Manages frame sequences
- Supports adding, deleting, moving, copying frames
- Handles frame duration
- Supports sequence operations (repeat, reverse, etc.)

### GifBuilder
- Composes materials and sequences into GIFs
- Handles output size, background, looping
- Optimizes GIF files

### UI Components
- **PreviewWidget**: Real-time preview and playback controls
- **TimelineWidget**: Draggable timeline editing
- **TileEditorWidget**: Image splitting tool

## 🔧 Tech Stack

- **Python 3.8+**
- **PyQt6**: Modern GUI framework
- **Pillow (PIL)**: Image processing and GIF operations

## 📝 Known Limitations

1. **Performance Optimization**
   - May be slow when processing large quantities of high-resolution materials
   - High memory usage when previewing large GIFs

2. **Feature Limitations**
   - Cannot edit individual frames (crop, rotate, filters, etc.)
   - No audio support (GIF format doesn't support audio)

## 🚧 Unfinished/Extensible Features

### High Priority

1. **Image Editing Features**
   - [ ] Material rotation, flip, crop
   - [ ] Adjust brightness, contrast, saturation
   - [ ] Add text and layer overlay

2. **Timeline Enhancements**
   - [ ] Multi-layer timeline
   - [ ] Keyframe easing
   - [ ] Transition effects between frames
   - [ ] Timeline zoom and scroll

3. **Export Options**
   - [ ] Export as PNG sequence
   - [ ] Export as video format (MP4, WebM)
   - [ ] Custom compression quality
   - [ ] Batch export multiple GIFs

4. **Project Management**
   - [ ] Save/load project files
   - [ ] Undo/redo functionality
   - [ ] Recent files list

### Medium Priority

5. **UI/UX Improvements**
   - [ ] Material library grid view
   - [ ] Drag materials directly to timeline
   - [ ] Keyboard shortcuts support
   - [ ] Dark mode theme
   - [ ] Customizable workspace layout

6. **Advanced Animation Features**
   - [ ] Onion skin display
   - [ ] Frame interpolation
   - [ ] Variable speed playback
   - [ ] Loop A-B section

7. **Batch Processing Tools**
   - [ ] Batch split multiple sprite sheets
   - [ ] Batch convert image formats
   - [ ] Batch resize

### Low Priority

8. **Collaboration and Sharing**
   - [ ] Export project as template
   - [ ] Online material library integration
   - [ ] Export as CSS Sprite
   - [ ] Generate sprite sheet

9. **Performance Optimization**
   - [ ] Multi-threading/async loading
   - [ ] Material caching mechanism
   - [ ] GPU acceleration (if needed)
   - [ ] Large file handling optimization

10. **Developer Features**
    - [ ] Command-line interface (CLI)
    - [ ] Python API for script calls
    - [ ] Plugin system
    - [ ] Unit tests and integration tests

## 🎯 Use Cases

### Game Development
- Process game character animation sprite sheets
- Create UI animation effects
- Make skill effect animations
- Quick animation prototype testing

### Pixel Art
- Edit pixel art animations
- Adjust frame timing and playback speed
- Create looping background animations

### GIF Creation
- Make emotes and stickers
- Edit and optimize GIF animations
- Create promotional animation materials

## 🤝 Contributing

Issues and Pull Requests are welcome!

### Development Guidelines
1. Follow PEP 8 code style
2. Use meaningful commit messages
3. Add necessary comments and documentation
4. Test new features before submitting

## 📄 License

MIT License - See LICENSE file for details

## 📮 Contact

For questions or suggestions, please contact via Issues.

---

**Enjoy creating animations! 🎨✨**