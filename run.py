#!/usr/bin/env python
"""
GIF Maker - Quick Launch Script

使用方式：
    python run.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.main import main

if __name__ == '__main__':
    print("=" * 60)
    print("GIF Maker - Animation Editor")
    print("=" * 60)
    print("Starting application...")
    print()
    
    try:
        main()
    except ImportError as e:
        print("error: missing necessary dependencies")
        print(f"details: {e}")
        print()
        print("please run the following command to install dependencies:")
        print("    pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print("error: program startup failed")
        print(f"details: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

