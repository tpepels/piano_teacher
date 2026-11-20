"""MIDI-only source importer for the embedded desktop application.

MusicXML is generated internally as an engraving artifact; it is never
accepted as a user-supplied source score. Every practice exercise uses the
canonical imported MIDI attacks, note releases and source measure grid.
"""
from __future__ import annotations

from pathlib import Path

from ..music import Piece, load_midi


def import_piece(path: str | Path) -> tuple[Piece, None]:
    """Load one MIDI source; return no external page/notation owner."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"No file found: {path}")
    if path.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Only MIDI files (.mid, .midi) can be imported")
    return load_midi(path), None
