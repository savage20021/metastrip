"""metastrip CLI entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, detect
from .core import inspect_file
from .output import console, render_batch, render_json, render_report, render_strip
from .strip import StripResult, strip_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metastrip",
        description="Inspect and strip privacy-sensitive metadata from images and documents.",
    )
    parser.add_argument("path", type=Path, help="file or directory to inspect")
    parser.add_argument("--clean", action="store_true",
                        help="write a metadata-free copy (never overwrites the original)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit JSON instead of human-readable output")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="output path for --clean; a directory in batch mode "
                             "(default: <name>.clean.<ext> beside the original)")
    parser.add_argument("-r", "--recursive", action="store_true",
                        help="in batch mode, descend into subdirectories")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _payload(report, strip_result: StripResult | None) -> dict:
    data = report.to_dict()
    if strip_result:
        data["strip"] = strip_result.to_dict()
    return data


def run_single(path: Path, args) -> int:
    report = inspect_file(path)
    strip_result = None
    if args.clean and not report.error:
        strip_result = strip_file(path, out=args.output, before=report)

    if args.as_json:
        render_json([_payload(report, strip_result)])
    else:
        render_report(report)
        if strip_result:
            render_strip(strip_result)
    if report.error or (strip_result and strip_result.error):
        return 1
    return 0


def run_batch(directory: Path, args) -> int:
    pattern = directory.rglob("*") if args.recursive else directory.iterdir()
    candidates = sorted(p for p in pattern if p.is_file())
    # don't re-process our own output files
    candidates = [p for p in candidates if ".clean" not in p.suffixes]

    out_dir = None
    if args.clean and args.output:
        out_dir = args.output
        out_dir.mkdir(parents=True, exist_ok=True)

    reports, strips, skipped = [], {}, 0
    for f in candidates:
        if detect.sniff(f) == detect.UNKNOWN:
            skipped += 1
            continue
        report = inspect_file(f)
        reports.append(report)
        if args.clean and not report.error:
            out = (out_dir / f.name) if out_dir else None
            strips[f] = strip_file(f, out=out, before=report)

    if args.as_json:
        render_json([_payload(r, strips.get(r.path)) for r in reports])
    else:
        render_batch(reports, strips, skipped)
    return 0 if reports else 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path: Path = args.path

    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        return 2
    if path.is_dir():
        return run_batch(path, args)
    return run_single(path, args)


if __name__ == "__main__":
    sys.exit(main())
