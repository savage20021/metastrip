"""Generate synthetic test images with known EXIF metadata.

Run:  python tests/fixtures/make_fixtures.py
Writes into tests/fixtures/data/ (safe to regenerate; no real photos involved).
"""
from __future__ import annotations

from pathlib import Path

import piexif
import pikepdf
from PIL import Image
from PIL.PngImagePlugin import PngInfo

DATA_DIR = Path(__file__).parent / "data"

# Known ground truth used by the tests: Eiffel Tower, Paris
EIFFEL_LAT = 48.8584   # 48° 51' 30.24" N
EIFFEL_LON = 2.2945    # 2° 17' 40.20" E


def _dms_rationals(decimal: float) -> tuple:
    """Signed decimal degrees -> EXIF ((deg,1),(min,1),(sec*10000,10000))."""
    value = abs(decimal)
    deg = int(value)
    minutes_full = (value - deg) * 60
    minutes = int(minutes_full)
    seconds = round((minutes_full - minutes) * 60 * 10000)
    return ((deg, 1), (minutes, 1), (seconds, 10000))


def _base_image(color: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (64, 48), color)
    for x in range(64):  # simple gradient so files aren't byte-identical
        for y in range(48):
            img.putpixel((x, y), (color[0], (x * 4) % 256, (y * 5) % 256))
    return img


def make_gps_jpeg(path: Path) -> None:
    """JPEG with the full privacy gamut: GPS, device, software, author, timestamps."""
    exif = {
        "0th": {
            piexif.ImageIFD.Make: b"TestCam Industries",
            piexif.ImageIFD.Model: b"TC-9000 Mark II",
            piexif.ImageIFD.Software: b"metastrip-fixture 1.0",
            piexif.ImageIFD.Artist: b"Jane Fixture",
            piexif.ImageIFD.DateTime: b"2026:08:01 14:30:00",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2026:08:01 14:29:55",
            piexif.ExifIFD.DateTimeDigitized: b"2026:08:01 14:29:55",
            piexif.ExifIFD.BodySerialNumber: b"SN-1234567",
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: _dms_rationals(EIFFEL_LAT),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: _dms_rationals(EIFFEL_LON),
            piexif.GPSIFD.GPSAltitudeRef: 0,
            piexif.GPSIFD.GPSAltitude: (2750, 100),  # 27.5 m
            piexif.GPSIFD.GPSTimeStamp: ((4, 1), (29, 1), (55, 1)),
            piexif.GPSIFD.GPSDateStamp: b"2026:08:01",
        },
    }
    _base_image((200, 0, 0)).save(path, "jpeg", exif=piexif.dump(exif), quality=90)


def make_device_only_jpeg(path: Path) -> None:
    """JPEG with device/timestamp metadata but no GPS."""
    exif = {
        "0th": {
            piexif.ImageIFD.Make: b"TestCam Industries",
            piexif.ImageIFD.Model: b"TC-100",
            piexif.ImageIFD.DateTime: b"2026:07:15 09:00:00",
        },
    }
    _base_image((0, 120, 0)).save(path, "jpeg", exif=piexif.dump(exif), quality=90)


def make_bare_jpeg(path: Path) -> None:
    """JPEG with no EXIF at all."""
    _base_image((0, 0, 200)).save(path, "jpeg", quality=90)


def make_gps_png(path: Path) -> None:
    """PNG with text chunks (author/software) and an eXIf chunk carrying GPS."""
    info = PngInfo()
    info.add_text("Author", "Jane Fixture")
    info.add_text("Software", "metastrip-fixture 1.0")
    info.add_text("Creation Time", "2026-08-01T14:30:00")
    exif = piexif.dump({
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: _dms_rationals(EIFFEL_LAT),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: _dms_rationals(EIFFEL_LON),
        },
    })
    _base_image((150, 80, 0)).save(path, "png", pnginfo=info, exif=exif)


def make_tiff(path: Path) -> None:
    """TIFF with device/software/timestamp tags in its baseline IFD."""
    _base_image((80, 0, 150)).save(
        path, "tiff",
        tiffinfo={
            271: "TestCam Industries",       # Make
            272: "TC-500 Scanner",           # Model
            305: "metastrip-fixture 1.0",    # Software
            306: "2026:08:01 14:30:00",      # DateTime
            315: "Jane Fixture",             # Artist
        },
    )


def make_pdf(path: Path) -> None:
    """One-page PDF with a document info dict and XMP metadata."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        meta["dc:creator"] = ["Jane Fixture"]
        meta["xmp:CreatorTool"] = "metastrip-fixture 1.0"
        meta["xmp:CreateDate"] = "2026-08-01T14:30:00+10:00"
    pdf.docinfo["/Author"] = "Jane Fixture"
    pdf.docinfo["/Creator"] = "metastrip-fixture 1.0"
    pdf.docinfo["/Producer"] = "fixture-producer"
    pdf.docinfo["/CreationDate"] = "D:20260801143000+10'00'"
    pdf.save(path)


def make_all(data_dir: Path = DATA_DIR) -> dict[str, Path]:
    data_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "gps": data_dir / "gps_full.jpg",
        "device_only": data_dir / "device_only.jpg",
        "bare": data_dir / "bare.jpg",
        "png": data_dir / "gps_text.png",
        "tiff": data_dir / "device.tiff",
        "pdf": data_dir / "doc.pdf",
    }
    make_gps_jpeg(paths["gps"])
    make_device_only_jpeg(paths["device_only"])
    make_bare_jpeg(paths["bare"])
    make_gps_png(paths["png"])
    make_tiff(paths["tiff"])
    make_pdf(paths["pdf"])
    return paths


if __name__ == "__main__":
    for name, p in make_all().items():
        print(f"wrote {name}: {p}")
