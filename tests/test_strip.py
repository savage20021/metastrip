"""Strip mode: outputs must carry no identifying metadata, originals untouched."""
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from make_fixtures import make_all  # noqa: E402

from metastrip.core import inspect_file  # noqa: E402
from metastrip.strip import default_output, strip_file  # noqa: E402


@pytest.fixture()
def fixtures(tmp_path):
    return make_all(tmp_path)


@pytest.mark.parametrize("name", ["gps", "device_only", "png", "tiff", "pdf"])
def test_strip_removes_all_privacy_data(fixtures, name):
    src = fixtures[name]
    original_bytes = src.read_bytes()

    result = strip_file(src)
    assert result.error is None, result.error
    assert result.output == default_output(src)
    assert result.output.exists()
    assert result.removed, "expected at least one metadata section removed"

    # original untouched
    assert src.read_bytes() == original_bytes

    after = inspect_file(result.output)
    assert after.error is None
    assert not after.privacy.any_present(), after.to_dict()["privacy"]
    assert not after.sections, list(after.sections)


def test_strip_jpeg_is_lossless(fixtures):
    src = fixtures["gps"]
    result = strip_file(src)
    assert result.error is None
    with Image.open(src) as a, Image.open(result.output) as b:
        assert a.tobytes() == b.tobytes()


def test_strip_bare_jpeg_notes_nothing_to_remove(fixtures):
    result = strip_file(fixtures["bare"])
    assert result.error is None
    assert result.removed == []
    assert any("no metadata" in n for n in result.notes)


def test_strip_refuses_overwriting_original(fixtures):
    src = fixtures["gps"]
    result = strip_file(src, out=src)
    assert result.error is not None
    assert "refusing" in result.error


def test_strip_explicit_output_path(fixtures, tmp_path):
    out = tmp_path / "sub" / "cleaned.jpg"
    out.parent.mkdir()
    result = strip_file(fixtures["gps"], out=out)
    assert result.error is None
    assert result.output == out and out.exists()
