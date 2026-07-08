"""GIF Maker - Animation Editor

A powerful GIF animation editor for game developers and animators.
"""

__version__ = '1.0.0'
__author__ = 'Aaron Cheng'

from . import core
from . import i18n
from . import settings

try:
    from . import widgets
except ImportError:
    # PyQt6 not installed — fine for headless uses (e.g. `python -m src.cli`)
    # that only need src.core, not the GUI.
    widgets = None

__all__ = ['core', 'widgets', 'i18n', 'settings']

