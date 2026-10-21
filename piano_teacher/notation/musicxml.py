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
    ending_element = tag.find("ending")
    ending = None
    if ending_element is not None:
        number = (ending_element.get("number") or "").strip()
        kind = (ending_element.get("type") or "").strip()
        if (not number or len(number) > 16 or
                any(c not in "0123456789, -." for c in number) or
                kind not in {"start", "stop", "discontinue"}):
            raise ValueError("Unsupported MusicXML volta ending declaration")
        ending = {"number": number, "type": kind}
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
    result = {"style": style, "repeat": direction}
    if ending is not None:
        result["ending"] = ending
    return location, result
