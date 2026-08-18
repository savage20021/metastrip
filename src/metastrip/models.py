"""Report structures shared by inspectors and output renderers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PrivacySummary:
    """The fields most likely to identify a person, device, or location."""
    gps: dict | None = None          # latitude, longitude, maps_url, altitude_m, gps_timestamp
    device_make: str | None = None
    device_model: str | None = None
    software: str | None = None
    author: str | None = None        # Artist / Author / Creator
    timestamps: dict[str, str] = field(default_factory=dict)
    serial_numbers: dict[str, str] = field(default_factory=dict)

    def any_present(self) -> bool:
        return bool(
            self.gps or self.device_make or self.device_model or self.software
            or self.author or self.timestamps or self.serial_numbers
        )


@dataclass
class MetadataReport:
    path: Path
    filetype: str
    # section name (e.g. "EXIF: GPS") -> {tag name: printable value}
    sections: dict[str, dict[str, str]] = field(default_factory=dict)
    privacy: PrivacySummary = field(default_factory=PrivacySummary)
    notes: list[str] = field(default_factory=list)
    error: str | None = None

    def has_metadata(self) -> bool:
        return bool(self.sections)

    def to_dict(self) -> dict:
        p = self.privacy
        return {
            "path": str(self.path),
            "filetype": self.filetype,
            "privacy": {
                "gps": p.gps,
                "device_make": p.device_make,
                "device_model": p.device_model,
                "software": p.software,
                "author": p.author,
                "timestamps": p.timestamps,
                "serial_numbers": p.serial_numbers,
            },
            "sections": self.sections,
            "notes": self.notes,
            "error": self.error,
        }
