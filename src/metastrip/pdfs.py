"""PDF metadata inspection via pikepdf (document info dict + XMP).

Library note: pikepdf (qpdf-based, actively maintained) over pypdf — more
robust low-level access to the /Info dict and /Metadata stream, and lossless
saves for the strip stage.
"""
from __future__ import annotations

import re
from pathlib import Path

import pikepdf

from .images import _printable
from .models import MetadataReport

# pikepdf may yield XMP keys in Clark notation: '{namespace-uri}localname'
_XMP_NS = {
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://www.aiim.org/pdfa/ns/id/": "pdfaid",
}


def _friendly_key(key: str) -> str:
    if key.startswith("{"):
        ns, _, local = key[1:].partition("}")
        prefix = _XMP_NS.get(ns)
        return f"{prefix}:{local}" if prefix else local
    return key


_PDF_DATE = re.compile(
    r"D:(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?"
)


def _pdf_date(value: str) -> str:
    """'D:20250108045527+10'00'' -> '2025-01-08 04:55:27 +10:00' (best effort)."""
    m = _PDF_DATE.match(value.strip())
    if not m:
        return value
    y, mo, d, h, mi, s, tz_sign, tz_h, tz_m = m.groups()
    out = f"{y}-{mo or '01'}-{d or '01'}"
    if h:
        out += f" {h}:{mi or '00'}:{s or '00'}"
    if tz_sign == "Z":
        out += " UTC"
    elif tz_sign and tz_h:
        out += f" {tz_sign}{tz_h}:{tz_m or '00'}"
    return out


def inspect_pdf(path: Path) -> MetadataReport:
    report = MetadataReport(path=path, filetype="pdf")
    try:
        with pikepdf.open(path) as pdf:
            _read_docinfo(pdf, report)
            _read_xmp(pdf, report)
            report.notes.append(f"{len(pdf.pages)} page(s)")
    except Exception as exc:
        report.error = f"{type(exc).__name__}: {exc}"
        return report

    if not report.has_metadata():
        report.notes.append("No document info or XMP metadata found.")
    return report


def _read_docinfo(pdf: pikepdf.Pdf, report: MetadataReport) -> None:
    try:
        docinfo = dict(pdf.docinfo)
    except Exception:
        return
    if not docinfo:
        return

    section = {}
    for key, value in sorted(docinfo.items(), key=lambda kv: str(kv[0])):
        name = str(key).lstrip("/")
        text = str(value)
        if name in ("CreationDate", "ModDate"):
            text = _pdf_date(text)
        section[name] = _printable(text)
    report.sections["PDF: Document info"] = section

    p = report.privacy
    p.author = section.get("Author") or None
    software = [v for v in (section.get("Creator"), section.get("Producer")) if v]
    p.software = " / ".join(dict.fromkeys(software)) or None
    for label, key in (("Created", "CreationDate"), ("Modified", "ModDate")):
        if section.get(key):
            p.timestamps[label] = section[key]


def _read_xmp(pdf: pikepdf.Pdf, report: MetadataReport) -> None:
    try:
        meta = pdf.open_metadata()
        section = {}
        for key in meta:
            try:
                value = meta[key]
            except Exception:
                continue
            if isinstance(value, (list, tuple, set)):
                value = "; ".join(str(v) for v in value)
            section[_friendly_key(key)] = _printable(str(value))
    except Exception:
        return
    if not section:
        return
    report.sections["XMP"] = section

    p = report.privacy
    if not p.author:
        p.author = section.get("dc:creator") or None
    if not p.software:
        p.software = section.get("xmp:CreatorTool") or section.get("pdf:Producer") or None
    for label, key in (
        ("Created (XMP)", "xmp:CreateDate"),
        ("Modified (XMP)", "xmp:ModifyDate"),
    ):
        if section.get(key) and label.split(" ")[0] not in p.timestamps:
            p.timestamps[label] = section[key]
