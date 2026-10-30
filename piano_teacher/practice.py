"""Deterministic, hardware-independent note and rhythm assessment."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Callable, Literal
from .music import Note, Phrase, Piece
from .lesson_settings import SETTINGS


@dataclass(frozen=True)
class PlayedNote:
    pitch: int
    onset: float  # seconds relative to passage start
    release: float | None


@dataclass(frozen=True)
class NoteAssessment:
    note: Note
    status: Literal["correct", "early", "late", "short", "long", "missed", "wrong"]
    played_pitch: int | None = None  # Actual incorrect key, only for wrong-pitch matches


@dataclass(frozen=True)
class Assessment:
    notes: tuple[NoteAssessment, ...]
    extra_notes: int
    unmatched_played: tuple[PlayedNote, ...] = ()

    @property
    def correct(self) -> int:
        return sum(n.status == "correct" for n in self.notes)

    @property
    def clean(self) -> bool:
        return bool(self.notes) and self.correct == len(self.notes) and self.extra_notes == 0

    @property
    def summary(self) -> str:
        if self.clean:
            return f"Clean · {self.correct}/{len(self.notes)} notes"
        counts = defaultdict(int)
        for entry in self.notes:
            if entry.status != "correct":
                counts[entry.status] += 1
        if self.extra_notes:
            counts["extra"] = self.extra_notes
        details = ", ".join(f"{k}: {v}" for k, v in counts.items())
        return f"{self.correct}/{len(self.notes)} correct · {details}"


def evaluate(phrase: Phrase, hand: str, bpm: float, played: list[PlayedNote], *,
             expected_seconds: Callable[[Note], tuple[float, float, float]] | None = None) -> Assessment:
    """Score pitch, start timing, and held duration independently.

    Matching uses the nearest unused same-pitch onset in a generous window;
    the stricter onset/release tolerances decide whether it was correct.
    """
    seconds_per_beat = 60.0 / bpm
    expected = [n for n in phrase.notes if hand == "both" or n.hand == hand]
    unused = set(range(len(played)))
    assessments: list[NoteAssessment] = []
    onset_tolerance = SETTINGS.grading_onset_tolerance_seconds
    for note in expected:
        if expected_seconds is None:
            start = (note.start - phrase.start) * seconds_per_beat
            duration = (min(note.end, phrase.end) - note.start) * seconds_per_beat
            local_seconds_per_beat = seconds_per_beat
        else:
            start, release, local_seconds_per_beat = expected_seconds(note)
            duration = release - start
        search_window = max(SETTINGS.grading_match_window_min_seconds,
                            SETTINGS.grading_match_window_beats * local_seconds_per_beat)
        options = [(abs(played[i].onset - start), i) for i in unused
                   if played[i].pitch == note.pitch and abs(played[i].onset - start) <= search_window]
        if not options:
            assessments.append(NoteAssessment(note, "missed"))
            continue
        _, index = min(options)
        unused.remove(index)
        event = played[index]
        drift = event.onset - start
        if drift < -onset_tolerance:
            status = "early"
        elif drift > onset_tolerance:
            status = "late"
        elif event.release is None:
            status = "short"  # key never released
        else:
            actual = max(0, event.release - event.onset)
            tolerance = max(SETTINGS.grading_duration_floor_seconds,
                            duration * SETTINGS.grading_duration_tolerance_fraction)
            if actual < duration - tolerance:
                status = "short"
            elif actual > duration + tolerance:
                status = "long"
            else:
                status = "correct"
        assessments.append(NoteAssessment(note, status))
    # Reclassify a missing pitch as 'wrong' only when an as-yet-unmatched
    # played note started at the expected beat. This avoids counting an
    # incorrect chord note as both 'missed' and 'extra'. Exact-pitch matching
    # is completed first so a wrong note cannot steal another correct note.
    for i, entry in enumerate(assessments):
        if entry.status != "missed":
            continue
        expected_onset = ((entry.note.start - phrase.start) * seconds_per_beat
                          if expected_seconds is None else expected_seconds(entry.note)[0])
        candidates = [(abs(played[j].onset - expected_onset), j)
                      for j in unused
                      if abs(played[j].onset - expected_onset) <= onset_tolerance]
        if candidates:
            _, index = min(candidates)
            unused.remove(index)
            assessments[i] = NoteAssessment(entry.note, "wrong", played[index].pitch)
    leftovers = tuple(played[i] for i in sorted(unused))
    return Assessment(tuple(assessments), len(leftovers), leftovers)


class Recorder:
    """Collect note events, including overlapping presses of the same pitch."""

    def __init__(self) -> None:
        self.presses: list[PlayedNote] = []
        self.active: dict[int, deque[int]] = defaultdict(deque)

    def add(self, pitch: int, is_on: bool, at_seconds: float) -> None:
        if at_seconds < -0.08:
            return  # ignore count-in notes
        if is_on:
            self.active[pitch].append(len(self.presses))
            self.presses.append(PlayedNote(pitch, at_seconds, None))
        elif self.active[pitch]:
            index = self.active[pitch].popleft()
            press = self.presses[index]
            self.presses[index] = PlayedNote(press.pitch, press.onset, at_seconds)


class Curriculum:
    """Right -> left -> both; two clean plays per tempo before progressing."""

    def __init__(self, piece: Piece) -> None:
        self.piece = piece
        self.phrase_index = 0
        self.phase_index = 0
        self.clean_streak = 0
        self.start_bpm = min(piece.bpm, max(30, min(72, round(piece.bpm * 0.6))))
        self.bpm = self.start_bpm
        self._skip_empty()

    @property
    def phrase(self) -> Phrase:
        return self.piece.phrases[self.phrase_index]

    @property
    def phases(self) -> list[str]:
        hands = {n.hand for n in self.phrase.notes}
        return [hand for hand in ("right", "left", "both")
                if hand == "both" or hand in hands]

    @property
    def hand(self) -> str:
        return self.phases[self.phase_index]

    def _skip_empty(self) -> None:
        if not self.piece.phrases:
            raise ValueError("No practice phrases were found")
        self.phase_index = min(self.phase_index, len(self.phases) - 1)

    def jump(self, offset: int) -> None:
        self.phrase_index = max(0, min(len(self.piece.phrases) - 1, self.phrase_index + offset))
        self.phase_index = 0
        self.bpm = self.start_bpm
        self.clean_streak = 0
        self._skip_empty()

    def completed(self, result: Assessment) -> str:
        if not result.clean:
            self.clean_streak = 0
            return "Repeat this passage"
        self.clean_streak += 1
        if self.clean_streak < 2:
            return "Once more at this tempo"
        self.clean_streak = 0
        if self.bpm < self.piece.bpm:
            self.bpm = min(self.piece.bpm, max(self.bpm + 4, round(self.bpm * 1.12)))
            return f"Tempo increased to {self.bpm} BPM"
        if self.phase_index + 1 < len(self.phases):
            self.phase_index += 1
            self.bpm = self.start_bpm
            return f"Now practice {self.hand} hand"
        if self.phrase_index + 1 < len(self.piece.phrases):
            self.phrase_index += 1
            self.phase_index = 0
            self.bpm = self.start_bpm
            return "Next passage"
        return "Piece complete - all passages passed"
