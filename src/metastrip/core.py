"""Dispatch: route a file to the right inspector based on sniffed type."""
from __future__ import annotations

from pathlib import Path

from . import detect
from .images import HEIF_AVAILABLE, inspect_image
from .models import MetadataReport
from .pdfs import inspect_pdf

IMAGE_TYPES = {detect.JPEG, detect.PNG, detect.TIFF, detect.WEBP, detect.HEIC}


def inspect_file(path: Path) -> MetadataReport:
    filetype = detect.sniff(path)

    if filetype == detect.PDF:
        return inspect_pdf(path)

    if filetype in IMAGE_TYPES:
        if filetype == detect.HEIC and not HEIF_AVAILABLE:
            report = MetadataReport(path=path, filetype=filetype)
            report.error = "HEIC needs the pillow-heif package (pip install pillow-heif)"
            return report
        report = inspect_image(path, filetype)
        if filetype == detect.WEBP:
            report.notes.append("WEBP support is preliminary.")
        return report

    report = MetadataReport(path=path, filetype=filetype)
    report.error = "unsupported or unrecognized file type (by content sniffing)"
    return report
