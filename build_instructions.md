# Building GIF Maker as an Executable

This guide explains how to build GIF Maker as a standalone Windows executable (.exe) file.

## Method 1: Using the Build Script (Recommended)

### Step 1: Install PyInstaller

```bash
pip install pyinstaller
```

### Step 2: Run the Build Script

Simply run:

```bash
python build_exe.py
```

The executable will be created in the `dist` folder as `GIF-Maker.exe`.

---

## Method 2: Manual PyInstaller Command

### Step 1: Install PyInstaller

```bash
pip install pyinstaller
```

### Step 2: Run PyInstaller

```bash
pyinstaller --name=GIF-Maker --windowed --onefile --icon=src/assets/icon.png --add-data="src;src" --hidden-import=PIL._tkinter_finder --collect-all=PIL --collect-all=PyQt6 --noconfirm run.py
```

**Command Explanation:**
- `--name=GIF-Maker`: Name of the output executable
- `--windowed`: No console window (for GUI apps)
- `--onefile`: Bundle everything into a single exe file
- `--icon=src/assets/icon.png`: Use the custom GIF icon
- `--add-data="src;src"`: Include the src directory
- `--hidden-import=PIL._tkinter_finder`: Include PIL dependencies
- `--collect-all=PIL`: Collect all PIL/Pillow files
- `--collect-all=PyQt6`: Collect all PyQt6 files
- `--noconfirm`: Overwrite output directory without asking

---

## Method 3: Using a .spec File (Advanced)

### Step 1: Generate a spec file

```bash
pyinstaller --name=GIF-Maker run.py
```

This creates `GIF-Maker.spec`. Edit it as needed.

### Step 2: Build from spec file

```bash
pyinstaller GIF-Maker.spec
```

---

## Output Location

After building, you'll find:
- `dist/GIF-Maker.exe` - Your standalone executable
- `build/` - Temporary build files (can be deleted)
- `GIF-Maker.spec` - Build configuration (keep for future builds)

---

## Distribution

The `GIF-Maker.exe` file in the `dist` folder is standalone and can be:
- Copied to any Windows computer
- Run without installing Python
- Distributed to users

**Note:** The first run might be slow as it extracts files. Subsequent runs will be faster.

---

## Troubleshooting

### Problem: "Failed to execute script"

**Solution:** Try building without `--onefile`:
```bash
pyinstaller --name=GIF-Maker --windowed --add-data="src;src" --collect-all=PIL --collect-all=PyQt6 run.py
```

This creates a folder with the exe and dependencies instead of a single file.

### Problem: Missing DLLs or modules

**Solution:** Add specific imports:
```bash
pyinstaller --name=GIF-Maker --windowed --onefile --icon=src/assets/icon.png --add-data="src;src" --hidden-import=PIL.Image --hidden-import=PyQt6.QtCore --hidden-import=PyQt6.QtWidgets --hidden-import=PyQt6.QtGui --collect-all=PIL --collect-all=PyQt6 run.py
```

### Problem: Antivirus flags the exe

**Solution:** This is normal for PyInstaller exes. You can:
- Add an exception in your antivirus
- Use code signing (requires a certificate)
- Build with `--debug` flag to see what's happening

### Problem: Exe is too large

**Solution:**
1. Use virtual environment to reduce dependencies
2. Exclude unnecessary packages:
```bash
pyinstaller --name=GIF-Maker --windowed --onefile --icon=src/assets/icon.png --add-data="src;src" --exclude-module=tkinter --exclude-module=matplotlib --collect-all=PIL --collect-all=PyQt6 run.py
```

---

## Optimizing Build Size

For a smaller executable:

```bash
pip install pyinstaller[encryption]
pyinstaller --name=GIF-Maker --windowed --onefile --icon=src/assets/icon.png --add-data="src;src" --collect-all=PIL --collect-all=PyQt6 --exclude-module=tkinter --exclude-module=matplotlib --strip --noupx run.py
```

---

## Creating an Installer (Optional)

After creating the exe, you can create a proper installer using:

### Option 1: Inno Setup (Free)
Download from: https://jrsoftware.org/isinfo.php

### Option 2: NSIS (Free)
Download from: https://nsis.sourceforge.io/

### Option 3: WiX Toolset (Free)
Download from: https://wixtoolset.org/

These tools can create professional installers with start menu shortcuts, uninstallers, etc.

---

## Quick Start

**Just want to build quickly?**

```bash
# Install PyInstaller
pip install pyinstaller

# Build
python build_exe.py

# Your exe is ready at: dist/GIF-Maker.exe
```

Done! 🎉

