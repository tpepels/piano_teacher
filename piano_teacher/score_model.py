"""Compatibility imports; implementation lives in piano_teacher.notation.model."""
from .notation.model import (
    SCHEMA,
    HANDS,
    PART_HAND,
    _TOLERANCE,
    BARLINE_STYLES,
    parse_barline,
    _barline_data,
    ScoreNote,
    ScoreMeasure,
    ScoreSymbol,
    _int,
    _notes,
    _parse_notation,
    build_score_model,
)
