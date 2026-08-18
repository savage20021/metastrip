"""Batch directory mode via the CLI entry point."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from make_fixtures import make_all  # noqa: E402

from metastrip.cli import main  # noqa: E402


@pytest.fixture()
def data_dir(tmp_path):
    make_all(tmp_path)
    (tmp_path / "notes.txt").write_text("not an image")
    return tmp_path


def test_batch_inspect(data_dir, capsys):
    assert main([str(data_dir)]) == 0
    # rich wraps cell text at terminal width, so assert on the summary line
    out = capsys.readouterr().out
    assert "Scanned 6 file(s)" in out
    assert "2 with GPS" in out      # gps_full.jpg + gps_text.png
    assert "skipped" in out         # notes.txt


def test_batch_clean_writes_copies(data_dir):
    assert main([str(data_dir), "--clean"]) == 0
    assert (data_dir / "gps_full.clean.jpg").exists()
    assert (data_dir / "doc.clean.pdf").exists()
    # cleaned outputs are not re-processed on a second run
    assert main([str(data_dir), "--clean"]) == 0
    assert not (data_dir / "gps_full.clean.clean.jpg").exists()


def test_batch_clean_to_output_dir(data_dir, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("cleaned")
    assert main([str(data_dir), "--clean", "-o", str(out_dir)]) == 0
    assert (out_dir / "gps_full.jpg").exists()


def test_batch_json(data_dir, capsys):
    assert main([str(data_dir), "--json"]) == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    by_name = {Path(p["path"]).name: p for p in payload}
    assert by_name["gps_full.jpg"]["privacy"]["gps"]["latitude"] == pytest.approx(48.8584, abs=1e-4)


def test_empty_dir_returns_2(tmp_path):
    assert main([str(tmp_path)]) == 2
