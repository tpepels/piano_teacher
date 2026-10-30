"""Tempo-map-aware live feedback, bounded grading and rolling recovery.

All matching uses *seconds*, while note identity and measure windows remain
anchored to the original source phrase. No per-frame state is retained here.
This adapter deliberately reuses the normal scorer and feedback projector.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from typing import Sequence

from .exercise_contracts import TempoMap
from .assessment_clock import expected_note_seconds as expected_seconds
from .feedback import project_assessment
from .lesson_settings import SETTINGS
from .measure_grid import chunk_start_at_end
from .music import Phrase
from .practice import Assessment, NoteAssessment, PlayedNote, evaluate
from .recovery import RecoveryDecision


def assess_timed_window(phrase: Phrase, hand: str, tempo: TempoMap,
                        played: Sequence[PlayedNote], *, from_beat: float = 0.0,
                        start_beat: float | None = None,
                        end_beat: float | None = None) -> Assessment:
    """Grade a selected source interval against the piecewise clock.

    Original Note objects reach the grader and feedback mapper unchanged,
    including source IDs. No mastered stage is changed here.
    """
    end = (phrase.end - phrase.start if end_beat is None else end_beat)
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
                 and abs(end-(phrase.end-phrase.start)) <= 1e-7)
    scoped = (list(played) if full_take else
              [note for note in played
               if since-.15 <= note.onset < until+.15])
    return evaluate(selected, hand, 60, scoped, expected_seconds=times)


def timed_live_marks(phrase: Phrase, hand: str, tempo: TempoMap,
                     played: Sequence[PlayedNote], *, from_beat: float,
                     elapsed_seconds: float, grid: Sequence[float],
                     layout: dict) -> list[dict]:
    """Show settled/expired notes at their original engraved noteheads."""
    if elapsed_seconds < 0:
        return []
    elapsed = tempo.seconds_at(from_beat) + elapsed_seconds
    now_beat = min(tempo.duration_beats, tempo.beat_at(elapsed))
    active = max(0, min(len(grid)-2, bisect_right(grid, now_beat)-1))
    window_start = max(from_beat, grid[max(0, active-2)])
    times = expected_seconds(phrase, tempo, from_beat)
    settled = []
    pending = []
    for note in phrase.notes:
        local = note.start - phrase.start
        if ((hand != "both" and note.hand != hand) or
                not window_start-1e-7 <= local <= now_beat+1e-7):
            continue
        onset, release, local_spb = times(note)
        if release + .12 <= elapsed_seconds + 1e-7:
            settled.append(note)
        elif onset + max(SETTINGS.grading_match_window_min_seconds,
                          SETTINGS.grading_match_window_beats * local_spb) <= elapsed_seconds + 1e-7:
            pending.append(note)
    marks = []
    if settled:
        # A bounded view may contain notes released in the preceding bar.
        # Their timestamps retain the same run-at origin as the real take.
        eligible = [n for n in played if n.onset >=
                    tempo.seconds_at(window_start)-tempo.seconds_at(from_beat)-.15
                    and n.onset <= elapsed_seconds+.12]
        selected = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                          phrase.start+window_start, phrase.end, tuple(settled))
        result = evaluate(selected, hand, 60, eligible,
                          expected_seconds=times)
        marks.extend(project_assessment(
            Assessment(result.notes, 0), phrase, 60, layout)["marks"])
    if pending:
        # Detect onset-only misses without marking a held note 'short' while
        # it is still being played. Distinct chord pitches remain distinct.
        missed = []
        unused = set(range(len(played)))
        for note in pending:
            onset, _, spb = times(note)
            window = max(SETTINGS.grading_match_window_min_seconds,
                         SETTINGS.grading_match_window_beats * spb)
            matches = [(abs(played[i].onset-onset), i) for i in unused
                       if played[i].pitch == note.pitch
                       and abs(played[i].onset-onset) <= window]
            if matches:
                unused.remove(min(matches)[1])
            else:
                missed.append(NoteAssessment(note, "missed"))
        if missed:
            ids = {mark.get("source_id") for mark in marks}
            projected = project_assessment(
                Assessment(tuple(missed), 0), phrase, 60, layout)["marks"]
            marks.extend(mark for mark in projected
                         if mark.get("source_id") not in ids)
    return marks


def timed_rolling_recovery(phrase: Phrase, hand: str, tempo: TempoMap,
                           played: Sequence[PlayedNote], *, from_beat: float,
                           end_beat: float, grid: tuple[float, ...],
                           threshold: int = 5) -> RecoveryDecision | None:
    """Original two-measure sliding error rule, scored in warped seconds."""
    if threshold <= 0:
        raise ValueError("A positive failure threshold is required")
    chunk = chunk_start_at_end(grid, end_beat)
    index = grid.index(chunk)
    start = max(from_beat, grid[max(0, index-2)])
    selected = [n for n in phrase.notes
                if (hand == "both" or n.hand == hand)
                and phrase.start+start-1e-7 <= n.start < phrase.start+end_beat-1e-7]
    if len(selected) < threshold:
        return None
    assessed = assess_timed_window(
        phrase, hand, tempo, played, from_beat=from_beat,
        start_beat=start, end_beat=end_beat)

    def location(beat: float) -> float:
        bar = min(len(grid)-2, max(0, bisect_right(grid, beat)-1))
        return bar + (beat-grid[bar])/(grid[bar+1]-grid[bar])

    window = deque()
    wrong = missed = 0
    best = None
    for entry in sorted(assessed.notes, key=lambda item: item.note.start):
        if entry.status not in ("wrong", "missed"):
            continue
        beat = entry.note.start - phrase.start
        position = location(beat)
        while window and position-window[0][0] >= 2-1e-7:
            _, prior = window.popleft()
            wrong -= prior == "wrong"
            missed -= prior == "missed"
        window.append((position, entry.status))
        wrong += entry.status == "wrong"
        missed += entry.status == "missed"
        if beat >= chunk-1e-7 and len(window) >= threshold and (
                best is None or len(window) >= best.errors):
            best = RecoveryDecision(end_beat, max(from_beat, chunk),
                                    len(window), wrong, missed)
    return best
