"""Source importer for the embedded desktop application.

MIDI (.mid, .midi) is read directly. MusicXML (.musicxml, .xml, .mxl) is
converted to the same performance timeline first, so practice, grading,
fingering and saved progress always use one canonical source model.
"""
from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from ..music import Piece, load_midi

MIDI_FORMATS = frozenset({".mid", ".midi"})
MUSICXML_FORMATS = frozenset({".musicxml", ".xml", ".mxl"})
SOURCE_FORMATS = MIDI_FORMATS | MUSICXML_FORMATS


def import_piece(path: str | Path) -> Piece:
    """Load one canonical source with no secondary notation owner."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    suffix = path.suffix.lower()
    if suffix in MUSICXML_FORMATS:
        return load_musicxml(path)
    if suffix not in MIDI_FORMATS:
        raise ValueError("Only MIDI (.mid, .midi) and MusicXML (.musicxml, .xml, .mxl) can be imported")
    return load_midi(path)


def load_musicxml(path: Path) -> Piece:
    """Written score -> MIDI timeline -> the canonical MIDI importer.

    Each staff becomes one MIDI track, so a grand staff keeps its two hands.
    Repeats are played as written (not expanded). Written fingers are kept
    as authored fingering (matched by onset and pitch; grace notes, which
    the timeline drops, keep none).
    """
    from music21 import converter
    from music21.midi.translate import streamToMidiFile
    try:
        score = converter.parse(str(path), format="musicxml")
    except Exception as exc:  # music21 raises many unrelated types
        raise ValueError(f"Cannot read MusicXML: {exc}") from exc
    midi = streamToMidiFile(score)
    with tempfile.TemporaryDirectory() as folder:
        converted = Path(folder) / f"{path.stem}.mid"
        midi.open(str(converted), "wb")
        try:
            midi.write()
        finally:
            midi.close()
        piece = load_midi(converted)
    return replace(piece, authored_fingerings=_authored_fingerings(score, piece))


def _authored_fingerings(score, piece: Piece) -> tuple[tuple[str, int], ...]:
    """Written fingers, matched to imported notes by onset and pitch."""
    from music21 import articulations
    written: dict[tuple[float, int], int] = {}
    for element in score.recurse().notes:
        fingers = [a for a in element.articulations if isinstance(a, articulations.Fingering)]
        if not fingers:
            continue
        onset = round(float(element.getOffsetInHierarchy(score)), 3)
        pitches = sorted(p.midi for p in element.pitches)
        if len(fingers) == 1 and len(pitches) > 1:
            fingers = fingers*len(pitches)
        for pitch, mark in zip(pitches, fingers):
            try:
                finger = int(mark.fingerNumber)
            except (TypeError, ValueError):
                continue
            if 1 <= finger <= 5:
                written[(onset, pitch)] = finger
    return tuple((note.source_id, written[key]) for note in piece.notes
                 if note.source_id and (key := (round(note.start, 3), note.pitch)) in written)
