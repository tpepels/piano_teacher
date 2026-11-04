"""Deterministic, hardware-independent note and rhythm assessment."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from typing import Callable, Literal
from .music import Note, Phrase
from .lesson_settings import SETTINGS
from .grading_tolerance import onset_tolerance, duration_tolerance


@dataclass(frozen=True)
class PlayedNote:
    pitch: int
    onset: float  # seconds relative to passage start
    release: float | None
    ambiguous_pairing: bool = field(default=False, compare=False)
    press_id: int | None = field(default=None, compare=False)


@dataclass(frozen=True)
class NoteObservation:
    """Measurements from the grader's own assignment, in attempt seconds.

    ``played_index`` is local to the evaluated list; ``press_id`` retains a
    recorder's identity when a bounded view filters that list. Missing keys
    and unreleased presses have no invented release or duration measurement.
    """
    played_index: int | None
    press_id: int | None
    expected_onset: float
    expected_release: float
    actual_pitch: int | None
    actual_onset: float | None
    actual_release: float | None
    local_seconds_per_beat: float
    onset_tolerance: float
    duration_tolerance: float
    onset_residual: float | None
    release_residual: float | None
    duration_residual: float | None
    pitch_error: bool
    timing_error: Literal["early", "late"] | None
    hold_error: Literal["short", "long"] | None
    unreleased: bool
    ambiguous_pairing: bool


@dataclass(frozen=True)
class NoteAssessment:
    note: Note
    status: Literal["correct", "early", "late", "short", "long", "missed", "wrong"]
    played_pitch: int | None = None  # Actual incorrect key, only for wrong-pitch matches
    observation: NoteObservation | None = None


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
    def yellow_attacks(self) -> int:
        """Distinct MIDI onsets with a timing/hold warning, not noteheads."""
        return len({round(entry.note.start, 6) for entry in self.notes
                    if entry.status in ("early", "late", "short", "long")})

    @property
    def total_attacks(self) -> int:
        return len({round(entry.note.start, 6) for entry in self.notes})

    @property
    def passed(self) -> bool:
        """Red is failure; amber is advisory below half the attacks."""
        if not self.notes or self.extra_notes:
            return False
        if any(note.status in ("missed", "wrong") for note in self.notes):
            return False
        return self.yellow_attacks * 2 < self.total_attacks

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
        prefix = "Accepted with warnings" if self.passed else "Retry"
        return f"{prefix} · {self.correct}/{len(self.notes)} precise · {details}"


def evaluate(phrase: Phrase, hand: str, bpm: float, played: list[PlayedNote], *,
             expected_seconds: Callable[[Note], tuple[float, float, float]] | None = None) -> Assessment:
    """Score pitch, start timing, and held duration independently.

    Matching uses the nearest unused same-pitch onset in a generous window;
    the stricter onset/release tolerances decide whether it was correct.
    """
    if bpm <= 0:
        raise ValueError("Practice BPM must be positive")
    seconds_per_beat = 60.0 / bpm
    expected = [n for n in phrase.notes if hand == "both" or n.hand == hand]
    unused = set(range(len(played)))
    assessments: list[NoteAssessment] = []
    timing = []
    for note in expected:
        if expected_seconds is None:
            start = (note.start - phrase.start) * seconds_per_beat
            duration = (min(note.end, phrase.end) - note.start) * seconds_per_beat
            release = start + duration
            local_spb = seconds_per_beat
        else:
            start, release, local_spb = expected_seconds(note)
            duration = release - start
        timing.append((start, release, duration, local_spb))

    def observation_for(note_index: int, played_index: int | None = None) -> NoteObservation:
        note = expected[note_index]
        start, release, duration, local_spb = timing[note_index]
        allowed = onset_tolerance(local_spb)
        hold_slack = duration_tolerance(duration, local_spb)
        event = played[played_index] if played_index is not None else None
        drift = None if event is None else event.onset - start
        timing_error = ("early" if drift is not None and drift < -allowed else
                        "late" if drift is not None and drift > allowed else None)
        hold_error = None
        release_residual = duration_residual = None
        if event is not None and event.release is not None:
            release_residual = event.release - release
            duration_residual = event.release - event.onset - duration
            actual = max(0, event.release - event.onset)
            if actual < duration - hold_slack:
                hold_error = "short"
            elif actual > duration + hold_slack:
                hold_error = "long"
        return NoteObservation(
            played_index=played_index,
            press_id=None if event is None else event.press_id,
            expected_onset=start, expected_release=release,
            actual_pitch=None if event is None else event.pitch,
            actual_onset=None if event is None else event.onset,
            actual_release=None if event is None else event.release,
            local_seconds_per_beat=local_spb,
            onset_tolerance=allowed, duration_tolerance=hold_slack,
            onset_residual=drift, release_residual=release_residual,
            duration_residual=duration_residual,
            pitch_error=event is not None and event.pitch != note.pitch,
            timing_error=timing_error, hold_error=hold_error,
            unreleased=event is not None and event.release is None,
            ambiguous_pairing=event is not None and event.ambiguous_pairing)

    # Closest-onset assignment first: an omitted repeated note must not steal
    # the correct press belonging to the next 16th of the same pitch.
    pairs = []
    for note_index, (note, (start, _, _, local_spb)) in enumerate(zip(expected, timing)):
        window = max(SETTINGS.grading_match_window_min_seconds,
                     SETTINGS.grading_match_window_beats * local_spb)
        pairs.extend((abs(event.onset - start), note_index, event_index)
                     for event_index, event in enumerate(played)
                     if event.pitch == note.pitch and abs(event.onset-start) <= window)
    matched = {}
    for _, note_index, event_index in sorted(pairs):
        if note_index not in matched and event_index in unused:
            matched[note_index] = event_index
            unused.remove(event_index)

    for note_index, note in enumerate(expected):
        if note_index not in matched:
            assessments.append(NoteAssessment(note, "missed", observation=observation_for(note_index)))
            continue
        observation = observation_for(note_index, matched[note_index])
        status = (observation.timing_error or
                  ("short" if observation.unreleased else observation.hold_error) or "correct")
        assessments.append(NoteAssessment(note, status, observation=observation))
    # Reclassify a missing pitch as 'wrong' only when an as-yet-unmatched
    # played note started at the expected beat. This avoids counting an
    # incorrect chord note as both 'missed' and 'extra'. Exact-pitch matching
    # is completed first so a wrong note cannot steal another correct note.
    for i, entry in enumerate(assessments):
        if entry.status != "missed":
            continue
        expected_onset = timing[i][0]
        candidates = [(abs(played[j].onset - expected_onset), j)
                      for j in unused
                      if abs(played[j].onset - expected_onset) <= onset_tolerance(timing[i][3])]
        if candidates:
            _, index = min(candidates)
            unused.remove(index)
            assessments[i] = NoteAssessment(entry.note, "wrong", played[index].pitch,
                                             observation_for(i, index))
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
            active = self.active[pitch]
            ambiguous = bool(active)
            # MIDI releases have pitch but no attack identity. Keep the
            # existing FIFO assignment and label every overlapping press.
            for index in active:
                self.presses[index] = replace(self.presses[index], ambiguous_pairing=True)
            index = len(self.presses)
            active.append(index)
            self.presses.append(PlayedNote(pitch, at_seconds, None,
                                           ambiguous_pairing=ambiguous, press_id=index))
        elif self.active[pitch]:
            index = self.active[pitch].popleft()
            press = self.presses[index]
            self.presses[index] = replace(press, release=at_seconds)
