"""EXIF GPS parsing: rational DMS + hemisphere refs -> signed decimal degrees."""
from __future__ import annotations

from typing import Optional, Sequence


def _to_float(value) -> float:
    """Coerce an EXIF rational to float. Accepts Pillow IFDRational,
    (numerator, denominator) tuples, and plain numbers."""
    if isinstance(value, tuple) and len(value) == 2:
        num, den = value
        if den == 0:
            raise ValueError("zero denominator in EXIF rational")
        return num / den
    return float(value)  # IFDRational and int/float both support this


def dms_to_decimal(dms: Sequence, ref: str | bytes | None) -> float:
    """Convert (degrees, minutes, seconds) rationals + 'N'/'S'/'E'/'W' ref
    into signed decimal degrees."""
    parts = [_to_float(v) for v in dms]
    while len(parts) < 3:
        parts.append(0.0)
    deg, minutes, seconds = parts[:3]
    decimal = deg + minutes / 60.0 + seconds / 3600.0
    if isinstance(ref, bytes):
        ref = ref.decode("ascii", "replace")
    if ref and ref.strip().upper() in ("S", "W"):
        decimal = -decimal
    return decimal


def parse_gps_ifd(gps_ifd: dict) -> Optional[dict]:
    """Extract decimal lat/long (and altitude, timestamp if present) from a GPS IFD
    keyed by numeric EXIF tags. Returns None if no usable coordinates."""
    # GPS IFD tag ids
    LAT_REF, LAT, LON_REF, LON = 1, 2, 3, 4
    ALT_REF, ALT = 5, 6
    TIME, DATE = 7, 29

    if LAT not in gps_ifd or LON not in gps_ifd:
        return None
    try:
        lat = dms_to_decimal(gps_ifd[LAT], gps_ifd.get(LAT_REF))
        lon = dms_to_decimal(gps_ifd[LON], gps_ifd.get(LON_REF))
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    result = {
        "latitude": round(lat, 7),
        "longitude": round(lon, 7),
        "maps_url": f"https://maps.google.com/?q={lat:.7f},{lon:.7f}",
    }

    if ALT in gps_ifd:
        try:
            alt = _to_float(gps_ifd[ALT])
            below = gps_ifd.get(ALT_REF) in (1, b"\x01")
            result["altitude_m"] = round(-alt if below else alt, 2)
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    date = gps_ifd.get(DATE)
    time = gps_ifd.get(TIME)
    if date or time:
        stamp = ""
        if date:
            stamp = date.decode("ascii", "replace") if isinstance(date, bytes) else str(date)
        if time:
            try:
                h, m, s = (_to_float(v) for v in time)
                stamp = f"{stamp} {int(h):02d}:{int(m):02d}:{s:05.2f} UTC".strip()
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        result["gps_timestamp"] = stamp
    return result
