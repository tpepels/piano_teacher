"""Source piece loader independent of Verovio page engraving."""
from __future__ import annotations
from dataclasses import replace
import math
from pathlib import Path
from ..music import Piece, load_midi

def _music21():
    try:
        from music21 import converter, chord, note, stream, tempo, meter, clef, key
    except ImportError as exc:
        raise RuntimeError("Sheet music requires music21: pip install -e '.[godot]'") from exc
    return converter, chord, note, stream, tempo, meter, clef, key


def import_piece(path: str | Path) -> tuple[Piece, object]:
    """Return matching scored note sequence and score for engraving.

    MIDI performance events come from Mido and are engraved later from the
    canonical Piece. MusicXML events and original notation come from music21.
    """
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    if path.suffix.lower() not in {".mid", ".midi", ".musicxml", ".xml", ".mxl"}:
        raise ValueError("Supported files: .mid, .midi, .musicxml, .xml, .mxl")
    # All MIDI lessons are engraved from the canonical imported Piece via
    # build_lesson_score, not from music21's loose MIDI transcription. Parsing
    # the raw MIDI a second time used to reject perfectly usable performances
    # with stray note-offs, grace placeholders or odd meter metadata.
    if path.suffix.lower() in {".mid", ".midi"}:
        return load_midi(path), None
    converter, chord, note, stream, tempo, meter, clef, key = _music21()
    from .musicxml import load_musicxml
    piece = load_musicxml(path, bpm=120)
    try:
        notation = converter.parse(str(path))
    except Exception as exc:
        raise ValueError(f"Cannot convert the source notation: {exc}") from exc
    if not isinstance(notation, stream.Score):
        wrapped = stream.Score()
        wrapped.insert(0, notation)
        notation = wrapped
    first_tempo = next(iter(notation.recurse().getElementsByClass(tempo.MetronomeMark)), None)
    bpm = first_tempo.getQuarterBPM() if first_tempo else 120
    if bpm is None or not math.isfinite(bpm) or bpm <= 0:
        raise ValueError("MusicXML tempo needs a positive numeric quarter-note BPM")
    return replace(piece, bpm=round(bpm)), notation


