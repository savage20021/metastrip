import sys
from pathlib import Path

import pytest

# make the fixture generator importable
sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from make_fixtures import EIFFEL_LAT, EIFFEL_LON, make_all  # noqa: E402

from metastrip.cli import inspect_file  # noqa: E402


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    return make_all(tmp_path_factory.mktemp("data"))


def test_gps_jpeg_full_report(fixtures):
    report = inspect_file(fixtures["gps"])
    assert report.error is None
    assert report.filetype == "jpeg"

    gps = report.privacy.gps
    assert gps is not None
    assert gps["latitude"] == pytest.approx(EIFFEL_LAT, abs=1e-4)
    assert gps["longitude"] == pytest.approx(EIFFEL_LON, abs=1e-4)
    assert gps["maps_url"].startswith("https://maps.google.com/?q=48.8")
    assert gps["altitude_m"] == pytest.approx(27.5)

    p = report.privacy
    assert p.device_make == "TestCam Industries"
    assert p.device_model == "TC-9000 Mark II"
    assert p.software == "metastrip-fixture 1.0"
    assert p.author == "Jane Fixture"
    assert p.serial_numbers == {"Body serial": "SN-1234567"}
    assert p.timestamps["Taken (DateTimeOriginal)"] == "2026:08:01 14:29:55"

    assert "EXIF: GPS" in report.sections
    assert report.sections["EXIF: GPS"]["GPSLatitudeRef"] == "N"


def test_device_only_jpeg_has_no_gps(fixtures):
    report = inspect_file(fixtures["device_only"])
    assert report.error is None
    assert report.privacy.gps is None
    assert report.privacy.device_model == "TC-100"
    assert report.privacy.any_present()


def test_bare_jpeg_reports_no_metadata(fixtures):
    report = inspect_file(fixtures["bare"])
    assert report.error is None
    assert not report.privacy.any_present()
    assert any("No EXIF" in n for n in report.notes)


def test_unsupported_file_fails_gracefully(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("just text")
    report = inspect_file(p)
    assert report.error is not None
    assert "unsupported" in report.error
