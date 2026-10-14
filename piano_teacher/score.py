"""MusicXML/MIDI to a common performance model and engraved sheet music."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path

from .music import Note, Piece, _bar_boundaries, _phrases, load_midi


def _music21():
    try:
        from music21 import converter, chord, note, stream, tempo, meter, clef, key
    except ImportError as exc:
        raise RuntimeError("Sheet music requires music21: pip install -e '.[godot]'") from exc
    return converter, chord, note, stream, tempo, meter, clef, key


def import_piece(path: str | Path) -> tuple[Piece, object]:
    """Return matching scored note sequence and score for engraving.

    MIDI performance events come from Mido; music21 is used for notation.
    MusicXML events are read from the notation directly.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    if path.suffix.lower() not in {".mid", ".midi", ".musicxml", ".xml", ".mxl"}:
        raise ValueError("Supported files: .mid, .midi, .musicxml, .xml, .mxl")
    converter, chord, note, stream, tempo, meter, clef, key = _music21()
    notation = converter.parse(str(path))
    if not isinstance(notation, stream.Score):
        wrapped = stream.Score()
        wrapped.insert(0, notation)
        notation = wrapped
    if path.suffix.lower() in {".mid", ".midi"}:
        piece = load_midi(path)
        return piece, notation
    parts = list(notation.parts)
    if not parts:
        parts = [notation]
    ranking = []
    for part in parts:
        pitches = [p.midi for item in part.flatten().notes for p in (item.pitches if isinstance(item, chord.Chord) else [item.pitch])]
        ranking.append(sum(pitches) / len(pitches) if pitches else 60)
    low_part = min(range(len(parts)), key=lambda i: ranking[i]) if len(parts) > 1 else -1
    events: list[Note] = []
    tied: dict[tuple[int, int], int] = {}
    for index, part in enumerate(parts):
        hand = "left" if index == low_part else "right"
        for item in part.recurse().notes:
            start = float(item.getOffsetInHierarchy(notation))
            length = float(item.duration.quarterLength)
            members = item.notes if isinstance(item, chord.Chord) else [item]
            for member in members:
                pitch = member.pitch.midi
                identifier = (index, pitch)
                tie_type = member.tie.type if member.tie is not None else None
                if tie_type in ("continue", "stop") and identifier in tied:
                    previous = tied[identifier]
                    events[previous] = replace(events[previous], end=start + length)
                else:
                    events.append(Note(start, start + length, pitch, index, 0, hand))
                if tie_type in ("start", "continue"):
                    tied[identifier] = len(events) - 1 if tie_type == "start" or identifier not in tied else tied[identifier]
                else:
                    tied.pop(identifier, None)
    if not events:
        raise ValueError("The score has no playable notes")
    signatures = [(float(t.getOffsetInHierarchy(notation)), t.numerator, t.denominator)
                  for t in notation.recurse().getElementsByClass(meter.TimeSignature)]
    first_tempo = next(iter(notation.recurse().getElementsByClass(tempo.MetronomeMark)), None)
    bpm = round(first_tempo.getQuarterBPM()) if first_tempo else 120
    events.sort(key=lambda e: (e.start, e.pitch, e.track))
    boundaries = _bar_boundaries(max(n.end for n in events), signatures)
    phrases = _phrases(events, boundaries, 2)
    return Piece(path.stem, bpm, tuple(events), phrases), notation


def render_measures(notation: object, first: int, last: int, hand: str = "both") -> str:
    """Engrave a selected score range as an actual SVG score via Verovio."""
    try:
        import verovio
        from music21 import stream, clef, key
        from music21.musicxml.m21ToXml import GeneralObjectExporter
    except ImportError as exc:
        raise RuntimeError("Engraving requires verovio and music21: pip install -e '.[godot]'") from exc
    sc = copy.deepcopy(notation)
    if not list(sc.recurse().getElementsByClass(stream.Measure)):
        sc.makeMeasures(inPlace=True)
    out = stream.Score()
    parts = list(sc.parts) or [sc]
    for index, part in enumerate(parts):
        p = stream.Part()
        p.id = part.id
        measures = list(part.getElementsByClass(stream.Measure))
        selected = [m for m in measures if first <= int(m.number) <= last]
        if not selected:
            continue
        for i, measure in enumerate(selected):
            copied = copy.deepcopy(measure)
            if i == 0:
                original = measure
                for element_type in (clef.Clef, key.KeySignature):
                    if not list(copied.getElementsByClass(element_type)):
                        context = original.getContextByClass(element_type)
                        if context is not None:
                            copied.insert(0, copy.deepcopy(context))
            if hand != "both" and len(parts) >= 2:
                # For ordinary two-part piano MusicXML: top is right, bottom is left.
                inactive = (hand == "right" and index == len(parts) - 1) or (hand == "left" and index == 0)
                if inactive:
                    for item in copied.recurse().notes:
                        item.style.color = "#BFC5C1"
            p.append(copied)
        out.append(p)
    if not list(out.parts):
        raise ValueError(f"No notation found for measures {first}-{last}")
    xml = GeneralObjectExporter(out).parse().decode("utf-8")
    toolkit = verovio.toolkit()
    toolkit.setOptions(json.dumps({"inputFrom": "xml", "scale": 48, "pageWidth": 1750,
                                   "pageHeight": 1100, "adjustPageHeight": True,
                                   "breaks": "auto", "svgViewBox": True,
                                   "svgFontType": "embedded"}))
    if not toolkit.loadData(xml):
        raise ValueError("Verovio could not engrave this passage")
    svg = toolkit.renderToSVG(1)
    if not svg or "<svg" not in svg:
        raise ValueError("Verovio returned no SVG score")
    return svg
