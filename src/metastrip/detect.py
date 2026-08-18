"""File type detection by magic bytes (content sniffing, not extensions)."""
from __future__ import annotations

from pathlib import Path

# Detected type constants
JPEG = "jpeg"
PNG = "png"
TIFF = "tiff"
HEIC = "heic"
PDF = "pdf"
WEBP = "webp"
UNKNOWN = "unknown"


def sniff(path: Path) -> str:
    """Identify a file by its leading bytes. Returns one of the type constants."""
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return UNKNOWN

    if len(head) < 4:
        return UNKNOWN

    if head[:3] == b"\xff\xd8\xff":
        return JPEG
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return TIFF
    if head[:5] == b"%PDF-":
        return PDF
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    # HEIC/HEIF: ISO BMFF container — 'ftyp' box at offset 4 with heic/heix/mif1... brand
    if head[4:8] == b"ftyp" and head[8:12] in (
        b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1",
    ):
        return HEIC
    return UNKNOWN
