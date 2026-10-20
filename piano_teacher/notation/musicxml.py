"""Shared source MusicXML barline interpretation, with no renderer dependency."""
from __future__ import annotations

from xml.etree import ElementTree as ET

BARLINE_STYLES = frozenset({
    "regular", "light-light", "light-heavy", "heavy-light",
    "heavy-heavy", "heavy", "none", "dashed", "dotted", "tick", "short",
})


def parse_barline(tag: ET.Element) -> tuple[str, dict]:
    """Parse explicit MusicXML barlines for both import and semantic models."""
    location = tag.get("location", "right")
    if location not in {"left", "right"}:
        raise ValueError(f"Unsupported MusicXML barline location: {location}")
    if tag.find("ending") is not None:
        raise ValueError("Volta endings require full Verovio notation")
    repeat = tag.find("repeat")
    direction = repeat.get("direction", "") if repeat is not None else ""
    if direction not in {"", "forward", "backward"}:
        raise ValueError(f"Unknown MusicXML repeat direction: {direction}")
    style = (tag.findtext("bar-style") or "").strip()
    if not style:
        style = ("heavy-light" if direction == "forward" else
                 "light-heavy" if direction == "backward" else "regular")
    if style not in BARLINE_STYLES:
        raise ValueError(f"Unsupported MusicXML barline style: {style}")
    return location, {"style": style, "repeat": direction}
