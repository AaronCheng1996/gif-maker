#!/usr/bin/env python
"""
GIF Maker - Quick Launch Script

使用方式：
    python run.py

或直接双击运行此文件（如果 Python 已正确配置）
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
        print(f"错误：缺少必要的依赖库")
        print(f"详情：{e}")
        print()
        print("请运行以下命令安装依赖：")
        print("    pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"错误：程序启动失败")
        print(f"详情：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

