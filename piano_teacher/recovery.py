"""Two-measure, boundary-aligned failure detection for MIDI-led practice.

Work in original exercise beats so restarts and tempo changes do not cause
errors to drift. A wrong pitch replaces a miss rather than counting twice.
"""
from __future__ import annotations
from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from .measure_grid import chunk_start_at_end
from .music import Phrase
from .optional_notes import relative_optional_notes
from .practice import PlayedNote, evaluate


@dataclass(frozen=True)
class RecoveryDecision:
    end_beat: float
    restart_beat: float
    errors: int
    wrong: int
    missed: int


def check_rolling_two_bar_window(phrase: Phrase, hand: str, bpm: int,
                                 played: list[PlayedNote], *, from_beat: float,
                                 end_beat: float, grid: tuple[float, ...],
                                 threshold: int = 5,
                                 optional_notes: tuple[dict, ...] = ()) -> RecoveryDecision | None:
    """Detect a rolling threshold, then retry the just-completed source chunk.

    Only a threshold reached in this chunk can trigger. Assessment is bounded
    to this chunk and its preceding two measures; earlier attempts and future
    notes cannot enter the window. Source-measure fractions handle mixed meter
    without treating every bar as the first bar's number of quarter beats.
    Error totals describe the rolling window; beat bounds identify the
    canonical retry idea, whose own error total can be smaller.
    Optional grace beats use the original phrase's origin and are rebased to
    the assessed segment, independently of the take's recording start.
    """
    if threshold <= 0:
        raise ValueError("A positive error threshold is required")
    chunk_start = chunk_start_at_end(grid, end_beat)
    chunk_index = grid.index(chunk_start)
    start = max(from_beat, grid[max(0, chunk_index - 2)])
    if end_beat <= start:
        return None
    selected = tuple(note for note in phrase.notes
                     if phrase.start + start - 1e-7 <= note.start < phrase.start + end_beat - 1e-7
                     and (hand == "both" or note.hand == hand))
    if len(selected) < threshold:
        return None
    seconds = 60.0 / bpm
    offset = (start - from_beat) * seconds
    relative = [PlayedNote(note.pitch, note.onset - offset,
                           note.release - offset if note.release is not None else None)
                for note in played
                if offset - .15 <= note.onset < (end_beat - from_beat) * seconds + .15]
    segment = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                     phrase.start + start, phrase.start + end_beat, selected)
    assessed = evaluate(segment, hand, bpm, relative,
                        optional_notes=relative_optional_notes(optional_notes, start))

    def measure_position(beat: float) -> float:
        index = min(len(grid) - 2, max(0, bisect_right(grid, beat) - 1))
        return index + (beat - grid[index]) / (grid[index + 1] - grid[index])

    window = deque()
    wrong = missed = 0
    best = None
    for entry in sorted(assessed.notes, key=lambda item: item.note.start):
        if entry.status not in ("wrong", "missed"):
            continue
        beat = entry.note.start - phrase.start
        position = measure_position(beat)
        while window and position - window[0][0] >= 2 - 1e-7:
            _, previous = window.popleft()
            wrong -= previous == "wrong"
            missed -= previous == "missed"
        window.append((position, entry.status))
        wrong += entry.status == "wrong"
        missed += entry.status == "missed"
        if (beat >= chunk_start - 1e-7 and len(window) >= threshold
                and (best is None or len(window) >= best.errors)):
            best = RecoveryDecision(end_beat, max(from_beat, chunk_start), len(window), wrong, missed)
    return best


def check_two_bar_window(phrase: Phrase, hand: str, bpm: int,
                         played: list[PlayedNote], *,
                         from_beat: float, end_beat: float,
                         beats_per_bar: float, threshold: int = 5,
                         window_start_beat: float | None = None,
                         optional_notes: tuple[dict, ...] = ()) -> RecoveryDecision | None:
    """Return a rewind after five wrong/missed notes, or None.

    played timestamps begin at from_beat within the excerpt. The window
    is aligned to its ending two-bar boundary. evaluate() prevents
    counting one bad chord pitch as both wrong and missed. Optional grace
    beats are relative to the original phrase and rebased to this window.
    """
    if threshold <= 0 or beats_per_bar <= 0:
        raise ValueError("A positive error threshold and bar duration are required")
    end_beat = min(end_beat, phrase.end - phrase.start)
    # The source MIDI's bar grid is authoritative for changing meters.
    # The old fixed-length fallback remains for legacy synthetic fixtures.
    start_beat = max(from_beat, window_start_beat if window_start_beat is not None
                     else end_beat - 2 * beats_per_bar)
    if end_beat <= start_beat:
        return None
    selected = tuple(n for n in phrase.notes
                     if phrase.start + start_beat - 1e-7 <= n.start < phrase.start + end_beat - 1e-7
                     and (hand == "both" or n.hand == hand))
    if len(selected) < threshold:
        return None
    seconds = 60.0 / bpm
    window_seconds = (start_beat - from_beat) * seconds
    relative = [PlayedNote(n.pitch, n.onset - window_seconds,
                           n.release - window_seconds if n.release is not None else None)
                for n in played if window_seconds - .15 <= n.onset < (end_beat - from_beat) * seconds + .15]
    segment = Phrase(phrase.number, phrase.first_bar, phrase.last_bar,
                     phrase.start + start_beat, phrase.start + end_beat, selected)
    assessed = evaluate(segment, hand, bpm, relative,
                        optional_notes=relative_optional_notes(optional_notes, start_beat))
    missed = sum(n.status == "missed" for n in assessed.notes)
    wrong = sum(n.status == "wrong" for n in assessed.notes)
    errors = missed + wrong
    return RecoveryDecision(end_beat, start_beat, errors, wrong, missed) if errors >= threshold else None
