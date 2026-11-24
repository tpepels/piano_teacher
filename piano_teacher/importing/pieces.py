"""Source importer for the embedded desktop application.

MIDI (.mid, .midi) is read directly. MusicXML (.musicxml, .xml, .mxl) is
converted to the same performance timeline first, so practice, grading,
fingering and saved progress always use one canonical source model.
"""
from __future__ import annotations

import tempfile
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
    Repeats are played as written (not expanded). Authored fingerings are
    not carried over; automatic fingering applies as for MIDI.
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
        return load_midi(converted)
