"""Command-line batch GIF processor — no GUI required.

Reuses src.core.batch_processor.BatchProcessor, so behavior matches the
Batch Processor tab in the GUI exactly. Intended for scripting/automation
pipelines that need to turn a folder of images into GIFs using a saved
composition template, without launching PyQt6 at all.

Usage:
    python -m src.cli --images img1.png img2.png --template template.json --output-dir out/
    python -m src.cli --frames Images/ --unit-pattern "(?P<unit>dh\\d+)_" \\
                      --template template.json --output-dir out/
"""
import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from .core.batch_processor import BatchProcessor
from .core.frame_set import FrameSetError, scan_frame_folder
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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--images", nargs="+", metavar="PATH",
                        help="One or more sprite sheets to split and process")
    source.add_argument("--frames", metavar="DIR",
                        help="A folder of exported frames; one GIF per unit "
                             "(see --unit-pattern)")
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
    parser.add_argument("--unit-pattern", metavar="REGEX", default=None,
                         help=(
                             "How --frames file names divide into outputs: a regex "
                             "anchored at the start of the name, read for a group "
                             r"called 'unit', e.g. (?P<unit>s?dh\d+(?:_sleep)?)_ . "
                             "Files it does not match are skipped. Omit it to treat "
                             "the whole folder as one output."
                         ))
    parser.add_argument("--recursive", action="store_true",
                         help="Search --frames sub-folders too")
    parser.add_argument("--dry-run", action="store_true",
                         help="With --frames, list the units that would be built "
                              "and stop")
    return parser


def _run_frame_folder(args, template) -> int:
    folder = Path(args.frames)
    if not folder.is_dir():
        print(f"Error: not a folder: {folder}", file=sys.stderr)
        return 1

    try:
        scan = scan_frame_folder(str(folder), args.unit_pattern,
                                 recursive=args.recursive)
    except FrameSetError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(f"{folder}: {scan.summary()}")
    if not scan.units:
        print("Error: nothing to build — check --unit-pattern", file=sys.stderr)
        return 1

    if args.dry_run:
        for unit in scan.units:
            print(f"  {unit.unit}  ({len(unit)} frames)  "
                  f"{unit.paths[0].name} … {unit.paths[-1].name}")
        return 0

    if args.output_dir:
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)

    processor = BatchProcessor()
    processor.set_progress_callback(
        lambda current, total, message: print(f"[{current}/{total}] {message}"))

    successful, failed = processor.process_frame_folder(
        folder=str(folder),
        pattern=args.unit_pattern,
        template=template,
        color_count=args.color_count,
        output_directory=args.output_dir,
        output_width=args.output_width,
        output_height=args.output_height,
        recursive=args.recursive,
    )

    print(f"\nDone: {len(successful)} succeeded, {len(failed)} failed.")
    for unit, err in failed:
        print(f"  FAILED {unit}: {err}", file=sys.stderr)
    return 0 if not failed else 2


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

    if args.frames:
        return _run_frame_folder(args, template)

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
