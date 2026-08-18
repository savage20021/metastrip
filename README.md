# metastrip

CLI tool that inspects — and (soon) strips — privacy-sensitive metadata from
image and document files: EXIF, IPTC, XMP, and PDF info dictionaries.

## Status

| Feature | State |
|---|---|
| JPEG inspect (EXIF + GPS decode + IPTC + XMP) | ✅ |
| PNG inspect (text chunks + eXIf EXIF/GPS + XMP) | ✅ |
| TIFF inspect (baseline IFD, structural tags filtered) | ✅ |
| PDF inspect (info dict + XMP, dates decoded) | ✅ |
| HEIC inspect (via pillow-heif, same EXIF path) | ✅ untested on real files |
| Magic-byte file detection (JPEG/PNG/TIFF/HEIC/PDF/WebP) | ✅ |
| `--clean` strip — JPEG **lossless** (segment filter), PNG/TIFF lossless re-save, PDF /Info + XMP removal | ✅ |
| Batch directory mode + summary table (`-r` recursive, `-o` output dir) | ✅ |
| WEBP / HEIC strip (lossy re-encode, noted in output) | ⚠️ best-effort |

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

## Web app

Double-click **`MetaStrip.bat`** — it starts a local server and opens
http://127.0.0.1:8377 in your browser. Drag files (or folders of files) onto
the drop zone: each gets a card with a privacy badge (red = GPS, yellow =
identifying data, green = clean), a clickable map link, the full metadata
dump, and a **Clean &amp; download** button that saves a metadata-free copy.
Bound to 127.0.0.1 only — nothing leaves the machine.

```bash
# or from a terminal
metastrip-web
```

## Use it from your phone

Double-click **`MetaStrip-Phone.bat`** instead — it starts the server in LAN
mode and opens a page with a QR code. Scan it with your phone (same Wi-Fi as
the PC), and the full app works in the phone browser: pick photos, see the
privacy panel, download clean copies. Use your browser's *Add to Home Screen*
to install it like an app (PWA manifest + icons included).

Notes:
- The first time, Windows Firewall will ask to allow Python network access —
  choose **Allow** for private networks. (Or add a rule manually as admin:
  `netsh advfirewall firewall add rule name="MetaStrip" dir=in action=allow protocol=TCP localport=8377`.)
- In LAN mode anyone on your Wi-Fi can reach the app while it's running;
  close the window to stop it. Default mode (`MetaStrip.bat`) stays
  127.0.0.1-only.
- iPhone caveat: uploading from the Photos picker may re-encode the image and
  drop GPS before it ever reaches the app. To inspect the *real* file, share
  it to the Files app first and upload from there.
- Away from home Wi-Fi? Install Tailscale on the PC and phone and use the
  PC's Tailscale address — don't port-forward this app to the open internet.

## CLI usage

```bash
# Inspect a file (human-readable, rich tables)
metastrip photo.jpg

# JSON output
metastrip photo.jpg --json

# Write a metadata-free copy (photo.clean.jpg — original never touched)
metastrip photo.jpg --clean
metastrip photo.jpg --clean -o anonymous.jpg

# Batch: scan a directory, summary table of GPS/identifying data
metastrip C:\photos
metastrip C:\photos -r                      # recurse into subdirectories
metastrip C:\photos --clean -o C:\cleaned   # strip everything into a folder
```

JPEG stripping is **lossless**: a segment-level filter drops the Exif/XMP
APP1, Photoshop/IPTC APP13, and comment segments while copying the compressed
pixel data verbatim (JFIF header and ICC profile are kept — they carry no
identifying data). PNG/TIFF are re-saved losslessly; WEBP/HEIC require a lossy
re-encode, which the output warns about. PDFs get /Info and the XMP stream
removed with page content untouched. Every strip is verified by re-inspecting
the output, and the removed sections are listed. If an image relied on the
EXIF Orientation flag, the tool warns that viewers may show it rotated.

The privacy panel surfaces: GPS coordinates (decoded to signed decimal
lat/long with a clickable Google Maps link), device make/model, software,
author/artist, serial numbers, and all timestamps. Exit code is 0 on success,
1 if the file couldn't be read, 2 for usage errors.

## Library choices

- **Pillow** — all metadata *reading*. Its `getexif()`/`ExifTags` API is
  actively maintained, handles JPEG and TIFF uniformly, and parses IPTC and
  XMP too. Chosen over `piexif` for reading because piexif has been dormant
  since 2019.
- **piexif** — used only by the test fixture generator to *write* known EXIF.
  (JPEG stripping originally planned around `piexif.remove()`, but that only
  drops the Exif APP1; the built-in segment filter in `strip.py` also removes
  XMP, IPTC, and comments, still losslessly.)
- **pikepdf** — PDF info dict + XMP. Actively maintained, built on qpdf;
  chosen over pypdf for more robust low-level metadata and lossless saves.
- **pillow-heif** — registers a HEIF/HEIC opener so HEIC flows through the
  same Pillow EXIF path.
- **rich** — tables and console output.
- **defusedxml** — required by Pillow's `getxmp()` for safe XMP parsing.

## File type detection

Files are identified by magic bytes (`src/metastrip/detect.py`), never by
extension — a `.jpg` that is actually a PNG is treated as a PNG.

## GPS decoding

EXIF stores coordinates as three rationals (degrees, minutes, seconds) plus
hemisphere refs. `src/metastrip/gps.py` converts these to signed decimal
degrees (S/W → negative), validates the range, and builds a maps link.
Zero-denominator rationals and malformed IFDs are rejected rather than
crashing.

## Tests & fixtures

No real photos are committed. `tests/fixtures/make_fixtures.py` generates
synthetic JPEGs with known EXIF (an Eiffel Tower GPS fix, fake device/author/serial)
that the tests assert against:

```bash
pytest
```

To generate sample files for manual poking:

```bash
python tests/fixtures/make_fixtures.py
```
