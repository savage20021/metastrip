from metastrip import detect


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_jpeg_magic(tmp_path):
    p = _write(tmp_path, "photo.dat", b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    assert detect.sniff(p) == detect.JPEG


def test_png_magic(tmp_path):
    p = _write(tmp_path, "img.jpg", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    # extension lies; content wins
    assert detect.sniff(p) == detect.PNG


def test_tiff_both_endians(tmp_path):
    assert detect.sniff(_write(tmp_path, "a", b"II*\x00" + b"\x00" * 32)) == detect.TIFF
    assert detect.sniff(_write(tmp_path, "b", b"MM\x00*" + b"\x00" * 32)) == detect.TIFF


def test_pdf_magic(tmp_path):
    p = _write(tmp_path, "doc", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    assert detect.sniff(p) == detect.PDF


def test_heic_magic(tmp_path):
    p = _write(tmp_path, "pic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 24)
    assert detect.sniff(p) == detect.HEIC


def test_unknown_and_tiny(tmp_path):
    assert detect.sniff(_write(tmp_path, "x", b"hello world")) == detect.UNKNOWN
    assert detect.sniff(_write(tmp_path, "y", b"\xff")) == detect.UNKNOWN
