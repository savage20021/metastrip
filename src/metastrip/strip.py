"""Metadata stripping. Always writes to a new file — originals are never touched.

Methods per type:
- JPEG: segment-level filter. Drops Exif/XMP APP1, Photoshop/IPTC APP13, and
  COM comment segments while copying the compressed image data verbatim —
  fully lossless, pixels untouched. (This supersedes piexif.remove(), which
  only handles the Exif APP1.) JFIF APP0 and ICC APP2 are kept.
- PNG: re-saved with Pillow (lossless format), metadata chunks not carried over.
- TIFF: re-saved with Pillow using LZW (lossless); original tag soup dropped.
- WEBP/HEIC: re-saved, which re-encodes pixels (lossy) — noted in the result.
- PDF: /Info dict and /Metadata XMP stream removed via pikepdf, content untouched.

Verification: after writing, the output is re-inspected and the removed
sections are reported as the diff between before and after.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
from PIL import Image

from . import detect
from .core import inspect_file
from .models import MetadataReport

_JPEG_KEEP_NOTE = "kept: JFIF header, ICC color profile (not identifying)"


@dataclass
class StripResult:
    source: Path
    output: Path | None
    removed: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "source": str(self.source),
            "output": str(self.output) if self.output else None,
            "removed": self.removed,
            "notes": self.notes,
            "error": self.error,
        }


def default_output(path: Path) -> Path:
    return path.with_name(path.stem + ".clean" + path.suffix)


def strip_file(path: Path, out: Path | None = None,
               before: MetadataReport | None = None) -> StripResult:
    """Write a metadata-free copy of `path`. Pass a pre-computed inspection
    report as `before` to avoid re-reading."""
    before = before or inspect_file(path)
    result = StripResult(source=path, output=None)

    if before.error:
        result.error = f"cannot strip: {before.error}"
        return result

    out = out or default_output(path)
    if out.resolve() == path.resolve():
        result.error = "refusing to overwrite the original file"
        return result
    result.output = out

    try:
        if before.filetype == detect.JPEG:
            _strip_jpeg(path, out)
            result.notes.append("lossless (compressed pixel data copied verbatim)")
            result.notes.append(_JPEG_KEEP_NOTE)
        elif before.filetype == detect.PDF:
            _strip_pdf(path, out)
            result.notes.append("page content untouched")
        elif before.filetype in (detect.PNG, detect.TIFF, detect.WEBP, detect.HEIC):
            _strip_pillow(path, out, before.filetype, result.notes)
        else:
            result.error = f"stripping not supported for {before.filetype}"
            result.output = None
            return result
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        if out.exists():
            out.unlink(missing_ok=True)
        result.output = None
        return result

    after = inspect_file(out)
    result.removed = [s for s in before.sections if s not in after.sections]
    for name in before.sections:
        if name in after.sections and after.sections[name]:
            result.notes.append(f"warning: '{name}' still present in output")

    if not before.sections:
        result.notes.append("original had no metadata to remove")

    orientation = before.sections.get("EXIF: Image (0th IFD)", {}).get("Orientation")
    if orientation and orientation != "1":
        result.notes.append(
            f"warning: EXIF Orientation={orientation} removed — "
            "viewers may show the image rotated"
        )
    return result


# --- JPEG: lossless segment filter -----------------------------------------

_DROP_APP1_PREFIXES = (
    b"Exif\x00",
    b"http://ns.adobe.com/xap/1.0/\x00",           # XMP
    b"http://ns.adobe.com/xmp/extension/\x00",     # extended XMP
)


def _strip_jpeg(src: Path, dst: Path) -> None:
    data = src.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG (missing SOI marker)")

    out = bytearray(b"\xff\xd8")
    i = 2
    n = len(data)
    while i < n - 1:
        if data[i] != 0xFF:
            raise ValueError(f"malformed JPEG segment at offset {i}")
        # skip fill bytes
        while i < n - 1 and data[i + 1] == 0xFF:
            i += 1
        marker = data[i + 1]
        if marker == 0xD9:  # EOI
            out += data[i:i + 2]
            break
        if marker == 0xDA:  # SOS: entropy-coded data follows — copy the rest
            out += data[i:]
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:  # standalone markers
            out += data[i:i + 2]
            i += 2
            continue
        length = int.from_bytes(data[i + 2:i + 4], "big")
        segment = data[i:i + 2 + length]
        payload = data[i + 4:i + 2 + length]
        drop = False
        if marker == 0xE1 and payload.startswith(_DROP_APP1_PREFIXES):
            drop = True
        elif marker == 0xED and payload.startswith(b"Photoshop 3.0\x00"):
            drop = True  # IPTC lives here
        elif marker == 0xFE:  # COM comment
            drop = True
        if not drop:
            out += segment
        i += 2 + length

    dst.write_bytes(bytes(out))


# --- PNG / TIFF / WEBP / HEIC: Pillow re-save --------------------------------

def _strip_pillow(src: Path, dst: Path, filetype: str, notes: list[str]) -> None:
    save_format = {detect.PNG: "png", detect.TIFF: "tiff",
                   detect.WEBP: "webp", detect.HEIC: "heif"}[filetype]
    with Image.open(src) as img:
        img.load()
        # some Pillow savers copy these from info if present — remove explicitly
        for key in ("exif", "xmp", "XML:com.adobe.xmp", "comment", "photoshop"):
            img.info.pop(key, None)
        # TIFF save preserves IPTC/Photoshop/XMP tags from the source tag_v2
        for attr in ("tag_v2", "tag"):
            try:
                delattr(img, attr)
            except AttributeError:
                pass

        kwargs: dict = {}
        icc = img.info.get("icc_profile")
        if icc:
            kwargs["icc_profile"] = icc
            notes.append("kept: ICC color profile (not identifying)")

        if filetype == detect.TIFF:
            kwargs["compression"] = "tiff_lzw"
            notes.append("re-saved with LZW (lossless); multi-page TIFFs keep first page only")
        elif filetype == detect.PNG:
            notes.append("re-saved (PNG is lossless)")
        else:
            kwargs["quality"] = 90
            notes.append("re-encoded at quality 90 — pixel data is NOT bit-identical (lossy format)")

        img.save(dst, save_format, **kwargs)


# --- PDF ---------------------------------------------------------------------

def _strip_pdf(src: Path, dst: Path) -> None:
    with pikepdf.open(src) as pdf:
        if "/Info" in pdf.trailer:
            del pdf.trailer["/Info"]
        if "/Metadata" in pdf.Root:
            del pdf.Root["/Metadata"]
        # per-page and per-object XMP streams are rare but possible
        for page in pdf.pages:
            if "/Metadata" in page:
                del page["/Metadata"]
        pdf.save(dst)
