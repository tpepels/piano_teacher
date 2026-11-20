"""One source-measure rolling-recovery decision and a fixed-tempo adapter.

All note judgments come from the canonical practice.evaluate scorer; the
pure reducer determines only whether those existing judgments cross the
two-measure failure threshold. Mapped and fixed clocks use the same reducer.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from typing import Sequence

from .measure_grid import chunk_start_at_end
from .music import Phrase
from .practice import Assessment, PlayedNote, evaluate
from .application.musical_scheduler import SCHEDULER


@dataclass(frozen=True)
class RecoveryDecision:
    end_beat: float
    restart_beat: float
    errors: int
    wrong: int
    missed: int


def rolling_recovery_verdict(assessment: Assessment, phrase: Phrase, *,
                             grid: Sequence[float], from_beat: float,
                             end_beat: float, threshold: int = 5,
                             warmup: bool = False) -> RecoveryDecision | None:
    """Apply one failure rule to an already evaluated source interval.

    Normal practice uses the last two authored measures in a rolling window.
    Warm-up retries use the current completed chunk, matching its deliberately
    narrower source scope. No note is graded or reassigned here.
    """
    if threshold <= 0:
        raise ValueError("A positive failure threshold is required")
    chunk = chunk_start_at_end(grid, end_beat)
    if warmup:
        wrong = sum(n.status == "wrong" for n in assessment.notes)
        missed = sum(n.status == "missed" for n in assessment.notes)
        return (RecoveryDecision(end_beat, max(from_beat, chunk),
                                 wrong+missed, wrong, missed)
                if wrong+missed >= threshold else None)

    def measure_position(beat: float) -> float:
        index = min(len(grid)-2, max(0, bisect_right(grid, beat)-1))
        return index + (beat-grid[index])/(grid[index+1]-grid[index])

    window = deque()
    wrong = missed = 0
    best = None
    for entry in sorted(assessment.notes, key=lambda note: note.note.start):
        if entry.status not in ("wrong", "missed"):
            continue
        beat = entry.note.start - phrase.start
        position = measure_position(beat)
        while window and position-window[0][0] >= 2-1e-7:
            _, previous = window.popleft()
            wrong -= previous == "wrong"
            missed -= previous == "missed"
        window.append((position, entry.status))
        wrong += entry.status == "wrong"
        missed += entry.status == "missed"
        if beat >= chunk-1e-7 and len(window) >= threshold and (
                best is None or len(window) >= best.errors):
            best = RecoveryDecision(end_beat, max(from_beat, chunk),
                                    len(window), wrong, missed)
    return best


def fixed_rolling_recovery(phrase: Phrase, hand: str, bpm: float,
                           played: Sequence[PlayedNote], *, from_beat: float,
                           end_beat: float, grid: tuple[float, ...],
                           threshold: int = 5, warmup: bool = False,
                           grade_note_holds: bool = False
                           ) -> RecoveryDecision | None:
    """Convert fixed-BPM recorded seconds into the shared evaluated window."""
    if threshold <= 0:
        raise ValueError("A positive failure threshold is required")
    if warmup:
        end_beat = min(end_beat, phrase.end-phrase.start)
    chunk = chunk_start_at_end(grid, end_beat)
    index = grid.index(chunk)
    start = max(from_beat, chunk if warmup else grid[max(0,index-2)])
    if end_beat <= start:
        return None
    selected = tuple(note for note in phrase.notes
                     if phrase.start+start-1e-7 <= note.start
                     < phrase.start+end_beat-1e-7
                     and (hand == "both" or note.hand == hand))
    if len(selected) < threshold:
        return None
    seconds = SCHEDULER.seconds_per_beat(bpm)
    offset = (start-from_beat)*seconds
    relative = [
        PlayedNote(note.pitch, note.onset-offset,
                   note.release-offset if note.release is not None else None)
        for note in played
        if offset-.15 <= note.onset < (end_beat-from_beat)*seconds+.15
    ]
    interval = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                      phrase.start+start, phrase.start+end_beat, selected)
    assessed = evaluate(interval, hand, bpm, relative,
                        grade_note_holds=grade_note_holds)
    return rolling_recovery_verdict(
        assessed, phrase, grid=grid, from_beat=from_beat,
        end_beat=end_beat, threshold=threshold, warmup=warmup)
