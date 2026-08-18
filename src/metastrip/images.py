"""Image metadata inspection via Pillow (EXIF, IPTC, XMP).

Library note: Pillow is used for *reading* — its ExifTags/getexif API is
actively maintained and handles JPEG and TIFF alike. piexif (stable but
dormant since 2019) is kept for the strip stage, where it can remove EXIF
from JPEGs losslessly without re-encoding pixel data.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, IptcImagePlugin
from PIL.ExifTags import GPSTAGS, IFD, TAGS

from .gps import parse_gps_ifd
from .models import MetadataReport, PrivacySummary

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False

_MAX_VALUE_LEN = 120

# Base-IFD / Exif-IFD tag ids used for the privacy summary
_TAG_MAKE = 0x010F
_TAG_MODEL = 0x0110
_TAG_SOFTWARE = 0x0131
_TAG_ARTIST = 0x013B
_TAG_DATETIME = 0x0132
_TAG_DT_ORIGINAL = 0x9003
_TAG_DT_DIGITIZED = 0x9004
_TAG_OWNER = 0xA430
_TAG_BODY_SERIAL = 0xA431
_TAG_LENS_SERIAL = 0xA435

_IPTC_NAMES = {
    (2, 5): "Object Name",
    (2, 25): "Keywords",
    (2, 55): "Date Created",
    (2, 60): "Time Created",
    (2, 80): "By-line (author)",
    (2, 85): "By-line Title",
    (2, 90): "City",
    (2, 92): "Sub-location",
    (2, 95): "Province/State",
    (2, 101): "Country",
    (2, 105): "Headline",
    (2, 110): "Credit",
    (2, 115): "Source",
    (2, 116): "Copyright Notice",
    (2, 120): "Caption/Abstract",
}


def _printable(value) -> str:
    """Render an EXIF value as a short human-readable string."""
    if isinstance(value, bytes):
        text = value.decode("ascii", "replace").replace("\x00", "").strip()
        if not text or text.count("�") > len(text) // 4:
            if len(value) <= 4:  # short flag/enum bytes (e.g. GPSAltitudeRef)
                return ", ".join(str(b) for b in value)
            return f"<{len(value)} bytes binary>"
        value = text
    elif isinstance(value, tuple):
        value = ", ".join(_printable(v) for v in value)
    else:
        value = str(value).strip()
    if len(value) > _MAX_VALUE_LEN:
        value = value[:_MAX_VALUE_LEN] + f"… (+{len(value) - _MAX_VALUE_LEN} chars)"
    return value


def _ifd_section(ifd: dict, tag_names: dict) -> dict[str, str]:
    section = {}
    for tag_id, value in sorted(ifd.items()):
        name = tag_names.get(tag_id, f"Unknown-0x{tag_id:04X}")
        section[name] = _printable(value)
    return section


def _flatten_xmp(node, prefix: str, out: dict[str, str], limit: int = 60) -> None:
    if len(out) >= limit:
        return
    if isinstance(node, dict):
        for key, val in node.items():
            _flatten_xmp(val, f"{prefix}.{key}" if prefix else str(key), out, limit)
    elif isinstance(node, (list, tuple)):
        for i, val in enumerate(node):
            _flatten_xmp(val, f"{prefix}[{i}]", out, limit)
    elif node is not None and str(node).strip():
        if len(out) < limit:
            out[prefix] = _printable(str(node))


def inspect_image(path: Path, filetype: str) -> MetadataReport:
    report = MetadataReport(path=path, filetype=filetype)
    try:
        with Image.open(path) as img:
            _read_exif(img, report)
            _read_iptc(img, report)
            _read_xmp(img, report)
            if filetype == "png":
                _read_png_text(img, report)
    except Exception as exc:  # corrupt file, truncated segments, etc.
        report.error = f"{type(exc).__name__}: {exc}"
    if not report.has_metadata() and not report.error:
        report.notes.append("No EXIF, IPTC, or XMP metadata found.")
    return report


# TIFF container plumbing (dimensions, strips, compression, resolution) — not
# metadata. Filtered from TIFF reports so only real metadata is surfaced.
_STRUCTURAL_TIFF_TAGS = frozenset({
    0x00FE, 0x00FF, 0x0100, 0x0101, 0x0102, 0x0103, 0x0106, 0x010A,
    0x0111, 0x0115, 0x0116, 0x0117, 0x011A, 0x011B, 0x011C, 0x0128,
    0x0129, 0x013D, 0x0140, 0x0142, 0x0143, 0x0144, 0x0145, 0x0152,
    0x0153, 0x015B, 0x0212, 0x0213, 0x0214, 0x8773,  # ICC profile
})


def _read_exif(img: Image.Image, report: MetadataReport) -> None:
    exif = img.getexif()
    if not exif:
        return

    base = dict(exif)
    # Pointer tags are rendered as their own sections, not raw offsets
    for pointer in (IFD.Exif.value, IFD.GPSInfo.value, IFD.Makernote.value):
        base.pop(pointer, None)
    if report.filetype == "tiff":
        base = {k: v for k, v in base.items() if k not in _STRUCTURAL_TIFF_TAGS}
    if base:
        report.sections["EXIF: Image (0th IFD)"] = _ifd_section(base, TAGS)

    exif_ifd = exif.get_ifd(IFD.Exif)
    if exif_ifd:
        report.sections["EXIF: Photo (Exif IFD)"] = _ifd_section(exif_ifd, TAGS)

    gps_ifd = exif.get_ifd(IFD.GPSInfo)
    if gps_ifd:
        report.sections["EXIF: GPS"] = _ifd_section(gps_ifd, GPSTAGS)

    p = report.privacy
    p.gps = parse_gps_ifd(gps_ifd) if gps_ifd else None
    p.device_make = _opt(base.get(_TAG_MAKE))
    p.device_model = _opt(base.get(_TAG_MODEL))
    p.software = _opt(base.get(_TAG_SOFTWARE))
    p.author = _opt(base.get(_TAG_ARTIST)) or _opt(exif_ifd.get(_TAG_OWNER))

    for label, value in (
        ("Modified (DateTime)", base.get(_TAG_DATETIME)),
        ("Taken (DateTimeOriginal)", exif_ifd.get(_TAG_DT_ORIGINAL)),
        ("Digitized (DateTimeDigitized)", exif_ifd.get(_TAG_DT_DIGITIZED)),
    ):
        if value:
            p.timestamps[label] = _printable(value)
    if p.gps and p.gps.get("gps_timestamp"):
        p.timestamps["GPS (UTC)"] = p.gps["gps_timestamp"]

    for label, tag in (("Body serial", _TAG_BODY_SERIAL), ("Lens serial", _TAG_LENS_SERIAL)):
        value = _opt(exif_ifd.get(tag))
        if value:
            p.serial_numbers[label] = value


def _opt(value) -> str | None:
    return _printable(value) if value else None


def _read_iptc(img: Image.Image, report: MetadataReport) -> None:
    try:
        iptc = IptcImagePlugin.getiptcinfo(img)
    except Exception:
        return
    if not iptc:
        return
    section = {}
    for key, value in sorted(iptc.items()):
        name = _IPTC_NAMES.get(key, f"IPTC {key[0]}:{key[1]}")
        if isinstance(value, list):
            section[name] = "; ".join(_printable(v) for v in value)
        else:
            section[name] = _printable(value)
    report.sections["IPTC"] = section
    author = section.get("By-line (author)")
    if author and not report.privacy.author:
        report.privacy.author = author


def _read_png_text(img: Image.Image, report: MetadataReport) -> None:
    """tEXt/zTXt/iTXt chunks. Standard keys carry author/software/timestamps."""
    text = getattr(img, "text", None)
    if not text:
        return
    section = {}
    for key, value in sorted(text.items()):
        if key == "XML:com.adobe.xmp":
            continue  # rendered as the XMP section
        section[key] = _printable(str(value))
    if not section:
        return
    report.sections["PNG text chunks"] = section

    p = report.privacy
    p.author = p.author or section.get("Author")
    p.software = p.software or section.get("Software")
    for label in ("Creation Time",):
        if section.get(label):
            p.timestamps.setdefault(label, section[label])


def _read_xmp(img: Image.Image, report: MetadataReport) -> None:
    raw = img.info.get("xmp") or img.info.get("XML:com.adobe.xmp")
    if not raw:
        return
    section: dict[str, str] = {}
    try:
        xmp = img.getxmp()  # needs defusedxml
        _flatten_xmp(xmp.get("xmpmeta", xmp), "", section)
    except Exception:
        pass
    if not section:
        size = len(raw) if isinstance(raw, (bytes, str)) else 0
        section["packet"] = f"XMP packet present ({size} bytes), could not parse"
    report.sections["XMP"] = section
