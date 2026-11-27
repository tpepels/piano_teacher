"""Tempo-map-aware live feedback and bounded grading.

All matching uses *seconds*, while note identity and measure windows remain
anchored to the original source phrase. No per-frame state is retained here.
This adapter deliberately reuses the normal scorer and feedback projector.
"""
from __future__ import annotations

from typing import Sequence

from .exercise_contracts import TempoMap
from .assessment_clock import expected_note_seconds as expected_seconds
from .feedback import project_assessment
from .live_feedback import live_assessment
from .music import Phrase
from .practice import Assessment, PlayedNote, evaluate


def assess_timed_window(phrase: Phrase, hand: str, tempo: TempoMap,
                        played: Sequence[PlayedNote], *, from_beat: float = 0.0,
                        start_beat: float | None = None,
                        end_beat: float | None = None,
                        grade_note_holds: bool = False) -> Assessment:
    """Grade a selected source interval against the piecewise clock.

    Original Note objects reach the grader and feedback mapper unchanged,
    including source IDs. No mastered stage is changed here.
    """
    end = (phrase.sounding_end - phrase.start if end_beat is None else end_beat)
    start = from_beat if start_beat is None else max(start_beat, from_beat)
    if not 0 <= from_beat <= start < end <= tempo.duration_beats + 1e-7:
        raise ValueError("Invalid tempo-mapped source interval")
    notes = tuple(n for n in phrase.notes
                  if (hand == "both" or n.hand == hand)
                  and phrase.start + start-1e-7 <= n.start < phrase.start + end-1e-7)
    selected = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                      phrase.start + start, phrase.start + end, notes)
    times = expected_seconds(phrase, tempo, from_beat)
    since = tempo.seconds_at(start) - tempo.seconds_at(from_beat)
    until = tempo.seconds_at(end) - tempo.seconds_at(from_beat)
    # Full assessed takes must retain every recorded extra key, including
    # one pressed after the last expected note. Only recovery windows
    # restrict played events to an adjacent interval.
    full_take = (abs(start-from_beat) <= 1e-7
                 and abs(end-(phrase.sounding_end-phrase.start)) <= 1e-7)
    scoped = (list(played) if full_take else
              [note for note in played
               if since-.15 <= note.onset < until+.15])
    return evaluate(selected, hand, 60, scoped, expected_seconds=times,
                    grade_note_holds=grade_note_holds)


def timed_live_marks(phrase: Phrase, hand: str, tempo: TempoMap,
                     played: Sequence[PlayedNote], *, from_beat: float,
                     elapsed_seconds: float, grade_note_holds: bool = False) -> list[dict]:
    """Project the same canonical observation stream using the tempo map."""
    result = live_assessment(
        phrase, hand, 60, list(played), from_beat=from_beat,
        elapsed_seconds=elapsed_seconds, tempo=tempo,
        grade_note_holds=grade_note_holds)
    return project_assessment(result, phrase, 60)["marks"]
