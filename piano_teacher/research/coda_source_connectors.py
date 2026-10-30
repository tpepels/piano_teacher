"""Explicit MusicXML source arcs for Coda's experimental score matrix.

The original score owns every relationship. Linked notes keep source XML
identities, part/staff/voice scopes, spelled tie pitch, and selected-measure
positions. Partial windows and unknown marks fail closed for transformation
eligibility. This is NOT a reproduction of Coda's published MMR.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

from .coda_source_metadata import MatrixSourceElement


@dataclass(frozen=True)
class MatrixSourceConnector:
    kind: str
    part_index: int
    voice_id: str
    number: str
    pitch: tuple[str, str, str] | None
    start_source_id: str | None
    stop_source_id: str | None
    start_beat: float | None
    stop_beat: float | None
    issue: str | None = None

    def crosses(self, beat: float) -> bool:
        """An independent passage may not cut an arc or unknown continuation."""
        tol = 1e-7
        if self.issue not in (None, "unpaired-start", "unpaired-stop"):
            return True
        if self.start_beat is None:
            return self.stop_beat is None or self.stop_beat >= beat-tol
        if self.stop_beat is None:
            return self.start_beat < beat-tol
        return self.start_beat < beat-tol and self.stop_beat >= beat-tol


def _spelled_pitch(node: ET.Element) -> tuple[str, str, str] | None:
    pitch = node.find("{*}pitch")
    if pitch is None:
        return None
    step, octave = pitch.findtext("{*}step"), pitch.findtext("{*}octave")
    if not step or octave is None:
        return None
    return step, pitch.findtext("{*}alter", "0"), octave


def _connector_marks(node: ET.Element, kind: str) -> tuple[tuple[str, str], ...]:
    """Merge MusicXML playback <tie> and engraved <tied> declarations once."""
    marks = (node.findall("{*}notations/{*}slur") if kind == "slur" else
             node.findall("{*}tie")+node.findall("{*}notations/{*}tied"))
    normalized = {(mark.get("type", ""), mark.get("number", "1"))
                  for mark in marks}
    # A continuation may be both the incoming stop and next start.
    return tuple(sorted(normalized, key=lambda row: (
        0 if row[0] == "stop" else 1 if row[0] == "start" else 2,
        row[1], row[0])))


def link_source_connectors(
        elements: tuple[MatrixSourceElement, ...]
        ) -> tuple[MatrixSourceConnector, ...]:
    """Link authored source-only slur/tie arcs, retaining unresolved edges.

    A selected passage can start/end inside a larger written arc. A missing
    endpoint cannot be guessed from a nearby pitch or another voice. Missing
    halves are represented explicitly, never silently discarded.
    """
    opened: dict[tuple, MatrixSourceElement] = {}
    found: list[MatrixSourceConnector] = []
    for item in elements:
        if item.kind != "note":
            continue
        node = ET.fromstring(item.xml)
        if node.find("{*}rest") is not None:
            continue
        for kind in ("slur", "tie"):
            marks = _connector_marks(node, kind)
            if not marks:
                continue
            pitch = _spelled_pitch(node) if kind == "tie" else None
            for direction, number in marks:
                voice = item.voice_id or ""
                key = (kind, item.part_index, voice, number, pitch)
                def arc(start, stop, issue=None):
                    return MatrixSourceConnector(
                        kind, item.part_index, voice, number, pitch,
                        start.source_id if start is not None else None,
                        stop.source_id if stop is not None else None,
                        start.onset if start is not None else None,
                        stop.onset if stop is not None else None, issue)
                if not voice or (kind == "tie" and pitch is None):
                    found.append(arc(None, item, "missing-source-scope"))
                elif direction == "stop":
                    start = opened.pop(key, None)
                    found.append(arc(start, item,
                                     None if start is not None else "unpaired-stop"))
                elif direction == "start":
                    if key in opened:
                        found.append(arc(opened[key], None,
                                         "duplicate-source-start"))
                    opened[key] = item
                else:
                    found.append(arc(None, item, "unsupported-mark:"+direction))
    for (kind, part, voice, number, pitch), start in opened.items():
        found.append(MatrixSourceConnector(
            kind, part, voice, number, pitch, start.source_id, None,
            start.onset, None, "unpaired-start"))
    return tuple(sorted(found, key=lambda arc: (
        arc.part_index, arc.start_beat if arc.start_beat is not None
        else arc.stop_beat if arc.stop_beat is not None else -1,
        arc.kind, arc.voice_id, arc.number,
        arc.start_source_id or "", arc.stop_source_id or "")))


def protected_connector_source_ids(
        elements: tuple[MatrixSourceElement, ...],
        links: tuple[MatrixSourceConnector, ...]) -> frozenset[str]:
    """Protect interior voice notes too, not just the arc endpoints.

    Retiming an inner note moves an authored slur's middle attachment even
    when both explicit endpoint notes stay unchanged. Unmatched links keep
    all potentially affected source notes within the selected window.
    """
    protected: set[str] = set()
    for link in links:
        for item in elements:
            if (item.kind != "note" or item.is_rest
                    or item.part_index != link.part_index
                    or item.voice_id != link.voice_id):
                continue
            if (link.start_beat is not None
                    and item.onset < link.start_beat-1e-7):
                continue
            if (link.stop_beat is not None
                    and item.onset > link.stop_beat+1e-7):
                continue
            protected.add(item.source_id)
    return frozenset(protected)
