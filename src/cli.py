"""Command-line batch GIF processor — no GUI required.

Reuses src.core.batch_processor.BatchProcessor, so behavior matches the
Batch Processor tab in the GUI exactly. Intended for scripting/automation
pipelines that need to turn a folder of images into GIFs using a saved
composition template, without launching PyQt6 at all.

Usage:
    python -m src.cli --images img1.png img2.png --template template.json --output-dir out/
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .core.batch_processor import BatchProcessor
from .core.template_manager import TemplateManager


def _parse_positions(raw: Optional[List[str]]) -> Optional[List[Tuple[int, int]]]:
    if not raw:
        return None
    positions = []
    for item in raw:
        try:
            row_str, col_str = item.split(",")
            positions.append((int(row_str), int(col_str)))
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"Invalid position '{item}' — expected format 'row,col' (e.g. 0,0)"
            )
    return positions


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description=(
            "Batch-convert images into GIFs using a saved composition template, "
            "without opening the GUI."
        ),
    )
    parser.add_argument("--images", nargs="+", required=True, metavar="PATH",
                         help="One or more source image files to process")
    parser.add_argument("--template", required=True, metavar="PATH",
                         help="Path to a template JSON file (exported from the Template Manager)")
    parser.add_argument("--output-dir", metavar="DIR",
                         help="Directory to write output GIFs into (default: alongside each source image)")
    parser.add_argument("--split-mode", choices=["grid", "size"], default="grid",
                         help="Tile-splitting mode (default: grid)")
    parser.add_argument("--split-rows", type=int, default=1, help="Grid rows (split-mode=grid)")
    parser.add_argument("--split-cols", type=int, default=1, help="Grid columns (split-mode=grid)")
    parser.add_argument("--tile-width", type=int, default=64, help="Tile width in px (split-mode=size)")
    parser.add_argument("--tile-height", type=int, default=64, help="Tile height in px (split-mode=size)")
    parser.add_argument("--color-count", type=int, default=256, help="GIF palette size (default: 256)")
    parser.add_argument("--output-width", type=int, default=None, help="Override output GIF width")
    parser.add_argument("--output-height", type=int, default=None, help="Override output GIF height")
    parser.add_argument("--positions", nargs="+", metavar="ROW,COL", default=None,
                         help="Only use these tile positions, e.g. --positions 0,0 0,1")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    template_path = Path(args.template)
    if not template_path.exists():
        print(f"Error: template file not found: {template_path}", file=sys.stderr)
        return 1
    try:
        template = TemplateManager.load_template_from_file(str(template_path))
        TemplateManager.validate_template(template)
    except Exception as e:
        print(f"Error: invalid template '{template_path}': {e}", file=sys.stderr)
        return 1

    missing = [p for p in args.images if not Path(p).exists()]
    if missing:
        for p in missing:
            print(f"Error: image file not found: {p}", file=sys.stderr)
        return 1

    try:
        positions = _parse_positions(args.positions)
    except argparse.ArgumentTypeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    processor = BatchProcessor()
    processor.set_progress_callback(lambda current, total, message: print(f"[{current}/{total}] {message}"))

    successful, failed = processor.process_batch(
        image_paths=args.images,
        template=template,
        split_mode=args.split_mode,
        split_rows=args.split_rows,
        split_cols=args.split_cols,
        tile_width=args.tile_width,
        tile_height=args.tile_height,
        color_count=args.color_count,
        output_directory=args.output_dir,
        selected_positions=positions,
        output_width=args.output_width,
        output_height=args.output_height,
    )

    print(f"\nDone: {len(successful)} succeeded, {len(failed)} failed.")
    for path, err in failed:
        print(f"  FAILED {path}: {err}", file=sys.stderr)

    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
