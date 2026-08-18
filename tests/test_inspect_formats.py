"""PNG, TIFF, and PDF inspection against synthetic fixtures."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from make_fixtures import EIFFEL_LAT, EIFFEL_LON, make_all  # noqa: E402

from metastrip.core import inspect_file  # noqa: E402


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    return make_all(tmp_path_factory.mktemp("data"))


def test_png_gps_and_text_chunks(fixtures):
    report = inspect_file(fixtures["png"])
    assert report.error is None
    assert report.filetype == "png"

    gps = report.privacy.gps
    assert gps is not None
    assert gps["latitude"] == pytest.approx(EIFFEL_LAT, abs=1e-4)
    assert gps["longitude"] == pytest.approx(EIFFEL_LON, abs=1e-4)

    assert "PNG text chunks" in report.sections
    assert report.privacy.author == "Jane Fixture"
    assert report.privacy.software == "metastrip-fixture 1.0"
    assert report.privacy.timestamps.get("Creation Time") == "2026-08-01T14:30:00"


def test_tiff_device_tags(fixtures):
    report = inspect_file(fixtures["tiff"])
    assert report.error is None
    assert report.filetype == "tiff"
    p = report.privacy
    assert p.device_make == "TestCam Industries"
    assert p.device_model == "TC-500 Scanner"
    assert p.software == "metastrip-fixture 1.0"
    assert p.author == "Jane Fixture"
    assert p.timestamps.get("Modified (DateTime)") == "2026:08:01 14:30:00"


def test_pdf_docinfo_and_xmp(fixtures):
    report = inspect_file(fixtures["pdf"])
    assert report.error is None
    assert report.filetype == "pdf"

    assert "PDF: Document info" in report.sections
    assert "XMP" in report.sections

    p = report.privacy
    assert p.author == "Jane Fixture"
    assert "metastrip-fixture 1.0" in p.software
    assert p.timestamps.get("Created") == "2026-08-01 14:30:00 +10:00"
    assert report.sections["XMP"].get("dc:creator") == "Jane Fixture"
