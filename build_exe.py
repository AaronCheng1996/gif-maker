import PyInstaller.__main__
import sys
import os

PyInstaller.__main__.run([
    'run.py',
    '--name=GIF-Maker',
    '--windowed',
    '--onefile',
    '--icon=NONE',
    '--add-data=src;src',
    '--hidden-import=PIL._tkinter_finder',
    '--collect-all=PIL',
    '--collect-all=PyQt6',
    '--noconfirm',
])

