"""Classify source attacks whose authored rhythmic semantics cannot be retimed.

Never replace an authored tie chain or tuplet with a generic dotted pair.
This guard is independent of the engraver and only reads original source XML.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET


def rhythm_protected_source_ids(source_musicxml: str) -> frozenset[str]:
    if not source_musicxml:
        return frozenset()
    root = ET.fromstring(source_musicxml)
    protected: set[str] = set()
    for pi, part in enumerate(root.findall(".//{*}part")):
        # Keyed by source voice, staff and notated pitch; the imported source
        # merges tie continuations into the preceding sounded attack.
        ties: dict[tuple[str, str, str, str, str], str] = {}
        for mi, measure in enumerate(part.findall("{*}measure")):
            for ordinal, note in enumerate(measure):
                if note.tag.rsplit("}", 1)[-1] != "note":
                    continue
                pitch = note.find("{*}pitch")
                if pitch is None:
                    continue
                sid = f"xml-p{pi}-m{mi}-e{ordinal}"
                key = (
                    note.findtext("{*}staff", "1"),
                    note.findtext("{*}voice", "1"),
                    pitch.findtext("{*}step", ""),
                    pitch.findtext("{*}alter", "0"),
                    pitch.findtext("{*}octave", ""),
                )
                tie_types = {mark.get("type") for mark in note.findall("{*}tie")}
                tie_types.update(mark.get("type") for mark in
                                 note.findall("{*}notations/{*}tied"))
                if "stop" in tie_types and key in ties:
                    protected.add(ties[key])
                if "start" in tie_types:
                    origin = ties.get(key, sid)
                    ties[key] = origin
                    protected.add(origin)
                elif "stop" in tie_types:
                    ties.pop(key, None)
                if (note.find("{*}time-modification") is not None or
                        note.findall("{*}notations/{*}tuplet")):
                    protected.add(ties.get(key, sid))
    return frozenset(protected)


def slur_endpoint_source_ids(source_musicxml: str) -> frozenset[str]:
    """Attacks whose authored slur anchors cannot be collapsed into a chord."""
    if not source_musicxml:
        return frozenset()
    source = ET.fromstring(source_musicxml)
    protected = set()
    for pi, part in enumerate(source.findall(".//{*}part")):
        for mi, measure in enumerate(part.findall("{*}measure")):
            for ordinal, node in enumerate(measure):
                if (node.tag.rsplit("}", 1)[-1] == "note"
                        and node.find("{*}pitch") is not None
                        and node.findall("{*}notations/{*}slur")):
                    protected.add(f"xml-p{pi}-m{mi}-e{ordinal}")
    return frozenset(protected)


def beamed_source_ids(source_musicxml: str) -> frozenset[str]:
    """Return note IDs with explicitly authored beam instructions.

    A chordification exercise must not quietly rewrite a written beam group
    as consecutive block chords while presenting it as preserved notation.
    """
    if not source_musicxml:
        return frozenset()
    root = ET.fromstring(source_musicxml)
    protected = set()
    for pi, part in enumerate(root.findall(".//{*}part")):
        for mi, measure in enumerate(part.findall("{*}measure")):
            for ordinal, node in enumerate(measure):
                if (node.tag.rsplit("}", 1)[-1] == "note"
                        and node.find("{*}pitch") is not None
                        and node.findall("{*}beam")):
                    protected.add(f"xml-p{pi}-m{mi}-e{ordinal}")
    return frozenset(protected)
