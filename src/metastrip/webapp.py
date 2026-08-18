"""Local web UI for metastrip: drag-and-drop inspect + one-click clean copy.

Default: 127.0.0.1 only — nothing leaves the machine.
--lan: also listen on the local network so phones on the same Wi-Fi can use it
       (visit /phone on the PC for a QR code to scan).

Start with:  python -m metastrip.webapp   (or the metastrip-web script)
"""
from __future__ import annotations

import argparse
import io
import ipaddress
import shutil
import socket
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, request, send_file
from PIL import Image, ImageDraw

from .core import inspect_file
from .strip import strip_file

HOST, PORT = "127.0.0.1", 8377
TMP = Path(tempfile.gettempdir()) / "metastrip-web"
JOB_MAX_AGE = 24 * 3600
MAX_UPLOAD = 200 * 1024 * 1024  # generous for big PDFs/RAWs, still bounded

# runtime state set by main()
STATE = {"lan": False, "port": PORT}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD


def _is_trusted_host(host_header: str) -> bool:
    """Allow localhost and IP-literal hosts; reject DNS names.

    Blocks DNS-rebinding (a malicious page on attacker.example resolving to
    127.0.0.1 still arrives with the attacker's name in the Host header)
    while keeping localhost and LAN-by-IP access (--lan / phone QR) working.
    """
    if not host_header:
        return False
    host = host_header.strip()
    if host.startswith("["):  # bracketed IPv6, e.g. [::1]:8377
        host = host[1 : host.find("]")]
    else:
        host = host.rsplit(":", 1)[0]
    if host.lower() == "localhost":
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


@app.before_request
def _reject_untrusted_requests():
    if not _is_trusted_host(request.host):
        abort(403)
    if request.method == "POST":
        # Browsers send Origin on cross-origin POSTs; a mismatch means a
        # foreign web page is blind-POSTing at this server (CSRF).
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            abort(403)


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # no traffic sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _purge_old_jobs() -> None:
    if not TMP.exists():
        return
    cutoff = time.time() - JOB_MAX_AGE
    for job in TMP.iterdir():
        try:
            if job.is_dir() and job.stat().st_mtime < cutoff:
                shutil.rmtree(job, ignore_errors=True)
        except OSError:
            pass


def _job_dir(job_id: str) -> Path:
    if not (len(job_id) == 32 and job_id.isalnum()):  # uuid4 hex only
        raise ValueError("bad job id")
    return TMP / job_id


def _safe_name(filename: str) -> str:
    name = Path(filename or "upload").name
    return "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "upload"


@app.get("/")
def index() -> Response:
    return Response(INDEX_HTML, mimetype="text/html")


@app.get("/manifest.json")
def manifest():
    return jsonify({
        "name": "MetaStrip", "short_name": "MetaStrip",
        "start_url": "/", "display": "standalone",
        "background_color": "#0f1218", "theme_color": "#0f1218",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


_ICON_CACHE: dict[int, bytes] = {}


def _icon_png(size: int) -> bytes:
    if size not in _ICON_CACHE:
        img = Image.new("RGBA", (size, size), (15, 18, 24, 255))
        d = ImageDraw.Draw(img)
        c, r, r2 = size / 2, size * 0.30, size * 0.11
        d.ellipse((c - r, c - r, c + r, c + r),
                  outline=(94, 234, 212, 255), width=max(2, size // 14))
        d.ellipse((c - r2, c - r2, c + r2, c + r2), fill=(94, 234, 212, 255))
        buf = io.BytesIO()
        img.save(buf, "png")
        _ICON_CACHE[size] = buf.getvalue()
    return _ICON_CACHE[size]


@app.get("/icon-192.png")
def icon_192():
    return Response(_icon_png(192), mimetype="image/png")


@app.get("/icon-512.png")
def icon_512():
    return Response(_icon_png(512), mimetype="image/png")


@app.get("/qr.png")
def qr_png():
    import qrcode
    url = f"http://{_lan_ip()}:{STATE['port']}"
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png")


@app.get("/phone")
def phone() -> Response:
    url = f"http://{_lan_ip()}:{STATE['port']}"
    if STATE["lan"]:
        body = f"""
        <h1>Open on your phone</h1>
        <p class="sub">Phone and PC must be on the same Wi-Fi network.</p>
        <img src="/qr.png" alt="QR code" class="qr">
        <p class="url">{url}</p>
        <ol>
          <li>Scan the QR code with your phone camera (or type the address).</li>
          <li>If it doesn't load, Windows Firewall is blocking it — when Windows
              asked to allow Python network access, choose <b>Allow</b>
              (for private networks).</li>
          <li>On the page, tap the browser menu → <b>Add to Home Screen</b> to
              install it like an app.</li>
        </ol>
        <p class="sub">Anyone on this Wi-Fi can reach this page while LAN mode is
        running — close the window to stop it.</p>"""
    else:
        body = """
        <h1>Phone access is off</h1>
        <p class="sub">The server is currently bound to 127.0.0.1 (this PC only).</p>
        <p>To use MetaStrip from your phone, close this server and start it with
        <b>MetaStrip-Phone.bat</b> (or <code>metastrip-web --lan</code>), then
        revisit this page for a QR code.</p>"""
    html = f"""<!doctype html><html><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>MetaStrip on your phone</title><style>
    body{{background:#0f1218;color:#dde3ee;font:15px/1.6 "Segoe UI",system-ui,sans-serif;
         max-width:520px;margin:0 auto;padding:40px 20px;text-align:center}}
    h1{{font-size:20px}} .sub{{color:#8892a6;font-size:13px}}
    .qr{{background:#fff;padding:12px;border-radius:12px;margin:18px 0;width:240px}}
    .url{{font-size:18px;color:#5eead4;font-weight:600}}
    ol{{text-align:left;color:#aab3c5;font-size:14px}}
    a{{color:#5eead4}} code{{background:#171c26;padding:2px 6px;border-radius:4px}}
    </style></head><body>{body}<p><a href="/">← back to MetaStrip</a></p></body></html>"""
    return Response(html, mimetype="text/html")


@app.post("/api/upload")
def api_upload():
    _purge_old_jobs()
    file = request.files.get("file")
    if file is None:
        return jsonify({"error": "no file"}), 400
    job_id = uuid.uuid4().hex
    job = _job_dir(job_id)
    job.mkdir(parents=True)
    path = job / _safe_name(file.filename)
    file.save(path)
    report = inspect_file(path)
    return jsonify({"id": job_id, "name": path.name, "report": report.to_dict()})


@app.post("/api/clean/<job_id>")
def api_clean(job_id: str):
    try:
        job = _job_dir(job_id)
    except ValueError:
        return jsonify({"error": "bad id"}), 400
    sources = [p for p in job.iterdir() if p.is_file() and ".clean" not in p.suffixes] \
        if job.exists() else []
    if not sources:
        return jsonify({"error": "unknown or expired job"}), 404
    src = sources[0]
    result = strip_file(src)
    if result.error:
        return jsonify({"error": result.error}), 422
    return jsonify({
        "removed": result.removed,
        "notes": result.notes,
        "download": f"/api/download/{job_id}",
        "filename": result.output.name,
    })


@app.get("/api/download/<job_id>")
def api_download(job_id: str):
    try:
        job = _job_dir(job_id)
    except ValueError:
        return jsonify({"error": "bad id"}), 400
    cleaned = [p for p in job.iterdir() if ".clean" in p.suffixes] if job.exists() else []
    if not cleaned:
        return jsonify({"error": "nothing cleaned for this job"}), 404
    return send_file(cleaned[0], as_attachment=True, download_name=cleaned[0].name)


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0f1218">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icon-192.png">
<link rel="apple-touch-icon" href="/icon-192.png">
<title>metastrip</title>
<style>
  :root {
    --bg: #0f1218; --panel: #171c26; --panel2: #1d2432; --line: #2a3347;
    --text: #dde3ee; --dim: #8892a6; --accent: #5eead4;
    --red: #f87171; --yellow: #fbbf24; --green: #4ade80;
  }
  * { box-sizing: border-box; margin: 0; }
  body { background: var(--bg); color: var(--text);
         font: 15px/1.5 "Segoe UI", system-ui, sans-serif; padding: 32px 16px; }
  .wrap { max-width: 860px; margin: 0 auto; }
  h1 { font-size: 22px; letter-spacing: .5px; }
  h1 span { color: var(--accent); }
  .sub { color: var(--dim); margin: 4px 0 24px; font-size: 13px; }
  #drop { border: 2px dashed var(--line); border-radius: 14px; padding: 44px 20px;
          text-align: center; color: var(--dim); cursor: pointer;
          transition: border-color .15s, background .15s; }
  #drop.hover, #drop:hover { border-color: var(--accent); background: var(--panel);
          color: var(--text); }
  #drop b { color: var(--accent); }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
          margin-top: 18px; padding: 18px 20px; }
  .card h2 { font-size: 15px; display: flex; align-items: center; gap: 10px;
             flex-wrap: wrap; }
  .badge { font-size: 11px; padding: 2px 8px; border-radius: 20px;
           background: var(--panel2); color: var(--dim); border: 1px solid var(--line);
           text-transform: uppercase; letter-spacing: 1px; }
  .badge.gps { background: #3b1219; color: var(--red); border-color: #7f1d1d; }
  .badge.ident { background: #332508; color: var(--yellow); border-color: #78500f; }
  .badge.clean { background: #0c2b1a; color: var(--green); border-color: #14532d; }
  table.privacy { margin: 12px 0 4px; border-collapse: collapse; width: 100%; }
  table.privacy td { padding: 3px 14px 3px 0; vertical-align: top; font-size: 14px; }
  table.privacy td:first-child { color: var(--dim); white-space: nowrap; width: 170px; }
  .gpsval, .gpsval a { color: var(--red); }
  .err { color: var(--red); margin-top: 8px; }
  .row { display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap; align-items: center; }
  button { background: var(--panel2); color: var(--text); border: 1px solid var(--line);
           border-radius: 8px; padding: 7px 16px; font-size: 13px; cursor: pointer; }
  button:hover { border-color: var(--accent); }
  button.primary { background: var(--accent); color: #06281f; border: none; font-weight: 600; }
  button.primary:hover { filter: brightness(1.1); }
  button:disabled { opacity: .5; cursor: default; }
  details { margin-top: 12px; }
  summary { color: var(--dim); cursor: pointer; font-size: 13px; }
  .section { margin: 10px 0; }
  .section h3 { font-size: 12px; color: var(--accent); text-transform: uppercase;
                letter-spacing: 1px; margin-bottom: 4px; }
  .section table { border-collapse: collapse; width: 100%; }
  .section td { padding: 2px 14px 2px 0; font-size: 13px; vertical-align: top;
                border-bottom: 1px solid #1c2330; word-break: break-word; }
  .section td:first-child { color: var(--dim); white-space: nowrap; width: 210px; }
  .result { margin-top: 12px; padding: 10px 14px; border-radius: 8px;
            background: #0c2b1a; border: 1px solid #14532d; font-size: 13px; }
  .result .warn { color: var(--yellow); }
  .note { color: var(--dim); font-size: 12px; }
  footer { color: var(--dim); font-size: 12px; margin-top: 30px; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <h1>metastrip <span>▪</span> photo &amp; document metadata</h1>
  <p class="sub">Everything runs locally on 127.0.0.1 — files never leave this machine.</p>
  <div id="drop">Drop files here or <b>click to browse</b><br>
    <span style="font-size:12px">JPEG · PNG · TIFF · HEIC · PDF</span></div>
  <input type="file" id="picker" multiple hidden>
  <div id="cards"></div>
  <footer>metastrip — inspect &amp; strip EXIF / IPTC / XMP / PDF metadata ·
    <a href="/phone" style="color:var(--accent)">📱 use on your phone</a></footer>
</div>
<script>
const drop = document.getElementById('drop');
const picker = document.getElementById('picker');
const cards = document.getElementById('cards');

drop.onclick = () => picker.click();
picker.onchange = () => { handle(picker.files); picker.value = ''; };
['dragover','dragenter'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.add('hover'); }));
['dragleave','drop'].forEach(e => drop.addEventListener(e, ev => {
  ev.preventDefault(); drop.classList.remove('hover'); }));
drop.addEventListener('drop', ev => handle(ev.dataTransfer.files));

function esc(s) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }

async function handle(files) {
  for (const f of files) {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `<h2>${esc(f.name)} <span class="badge">scanning…</span></h2>`;
    cards.prepend(card);
    const form = new FormData();
    form.append('file', f);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form });
      const data = await res.json();
      render(card, data);
    } catch (err) {
      card.innerHTML = `<h2>${esc(f.name)}</h2><div class="err">Upload failed: ${esc(String(err))}</div>`;
    }
  }
}

function render(card, data) {
  const r = data.report, p = r.privacy || {};
  const hasIdent = p.device_make || p.device_model || p.software || p.author ||
    Object.keys(p.timestamps || {}).length || Object.keys(p.serial_numbers || {}).length;
  let badge;
  if (r.error) badge = '<span class="badge">error</span>';
  else if (p.gps) badge = '<span class="badge gps">GPS location</span>';
  else if (hasIdent) badge = '<span class="badge ident">identifying data</span>';
  else badge = '<span class="badge clean">no sensitive data</span>';

  let html = `<h2>${esc(data.name)} <span class="badge">${esc(r.filetype)}</span> ${badge}</h2>`;

  if (r.error) {
    html += `<div class="err">${esc(r.error)}</div>`;
    card.innerHTML = html;
    return;
  }

  let rows = '';
  if (p.gps) {
    rows += `<tr><td>GPS location</td><td class="gpsval">${p.gps.latitude}, ${p.gps.longitude}` +
      (p.gps.altitude_m != null ? ` (alt ${p.gps.altitude_m} m)` : '') +
      ` — <a href="${esc(p.gps.maps_url)}" target="_blank" rel="noopener">open map</a></td></tr>`;
  }
  const dev = [p.device_make, p.device_model].filter(Boolean).join(' ');
  if (dev) rows += `<tr><td>Device</td><td>${esc(dev)}</td></tr>`;
  if (p.software) rows += `<tr><td>Software</td><td>${esc(p.software)}</td></tr>`;
  if (p.author) rows += `<tr><td>Author</td><td>${esc(p.author)}</td></tr>`;
  for (const [k, v] of Object.entries(p.serial_numbers || {}))
    rows += `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`;
  for (const [k, v] of Object.entries(p.timestamps || {}))
    rows += `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`;
  if (rows) html += `<table class="privacy">${rows}</table>`;
  else html += `<p class="note" style="margin-top:10px">No privacy-sensitive fields detected.</p>`;

  const sections = Object.entries(r.sections || {});
  if (sections.length) {
    html += `<details><summary>Full metadata (${sections.length} section${sections.length > 1 ? 's' : ''})</summary>`;
    for (const [name, fields] of sections) {
      html += `<div class="section"><h3>${esc(name)}</h3><table>`;
      for (const [k, v] of Object.entries(fields))
        html += `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`;
      html += `</table></div>`;
    }
    html += `</details>`;
  }
  (r.notes || []).forEach(n => { html += `<p class="note">${esc(n)}</p>`; });

  html += `<div class="row"><button class="primary" data-clean>Clean &amp; download</button>
           <span class="note">writes a metadata-free copy — the uploaded original is untouched</span></div>
           <div data-result></div>`;
  card.innerHTML = html;

  card.querySelector('[data-clean]').onclick = async (ev) => {
    const btn = ev.target;
    btn.disabled = true; btn.textContent = 'Cleaning…';
    try {
      const res = await fetch(`/api/clean/${data.id}`, { method: 'POST' });
      const out = await res.json();
      const box = card.querySelector('[data-result]');
      if (out.error) {
        box.innerHTML = `<div class="err">${esc(out.error)}</div>`;
        btn.textContent = 'Clean & download'; btn.disabled = false;
        return;
      }
      let msg = `<div class="result">✔ Clean copy ready: <b>${esc(out.filename)}</b>`;
      if (out.removed.length) msg += `<br>Removed: ${out.removed.map(esc).join(', ')}`;
      out.notes.forEach(n => {
        msg += `<br><span class="${n.startsWith('warning') ? 'warn' : 'note'}">${esc(n)}</span>`;
      });
      msg += `</div>`;
      box.innerHTML = msg;
      btn.textContent = 'Downloaded ✔';
      window.location.href = out.download;
    } catch (err) {
      card.querySelector('[data-result]').innerHTML = `<div class="err">${esc(String(err))}</div>`;
      btn.textContent = 'Clean & download'; btn.disabled = false;
    }
  };
}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="metastrip-web")
    ap.add_argument("--lan", action="store_true",
                    help="also listen on the local network so phones on the same "
                         "Wi-Fi can connect (see /phone for a QR code)")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)

    STATE["lan"] = args.lan
    STATE["port"] = args.port
    TMP.mkdir(parents=True, exist_ok=True)

    host = "0.0.0.0" if args.lan else HOST
    print(f"metastrip web UI -> http://127.0.0.1:{args.port}")
    if args.lan:
        print(f"phone (same Wi-Fi) -> http://{_lan_ip()}:{args.port}")
        print(f"QR code            -> http://127.0.0.1:{args.port}/phone")
        print("note: anyone on this network can reach the app while it runs")
    try:
        app.run(host=host, port=args.port, threaded=True)
    except OSError as exc:
        if getattr(exc, "errno", None) in (10048, 98):  # port in use (win/linux)
            print(f"\nERROR: port {args.port} is already in use — MetaStrip is "
                  "probably already running.\nClose the other MetaStrip window "
                  f"(or run with --port {args.port + 1}) and try again.")
            raise SystemExit(1)
        raise


if __name__ == "__main__":
    main()
