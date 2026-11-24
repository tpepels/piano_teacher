"""Deterministic, hardware-independent note and rhythm assessment."""
from __future__ import annotations

from collections import defaultdict, deque
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field, replace
from typing import Callable, Literal
from .music import Note, Phrase
from .lesson_settings import SETTINGS
from .grading_tolerance import onset_tolerance, duration_tolerance
from .application.musical_scheduler import SCHEDULER


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


def note_dimensions(entry: NoteAssessment) -> dict[str, str | None]:
    """Independent pitch, onset and release observations for one graded note.

    ``status`` combines onset, then optional release assessment, into
    one verdict that drives pass/fail and progression.
    The display needs all three: a note can be both early and released early.

    pitch:   ``correct`` | ``wrong`` | ``missed``
    onset:   ``on_time`` | ``early`` | ``late`` | None (no matched attack)
    release: ``on_time`` | ``short`` | ``long`` | ``unreleased`` | None
    """
    if entry.status in ("missed", "wrong"):
        return {"pitch": entry.status, "onset": None, "release": None}
    observation = entry.observation
    if observation is None:
        # Evaluators without measurements still name the dimension they judged.
        return {"pitch": "correct",
                "onset": entry.status if entry.status in ("early", "late") else "on_time",
                "release": entry.status if entry.status in ("short", "long") else
                           None if entry.status in ("early", "late") else "on_time"}
    release = ("unreleased" if observation.unreleased else
               observation.hold_error or "on_time")
    return {"pitch": "correct", "onset": observation.timing_error or "on_time",
            "release": release}


@dataclass(frozen=True)
class Assessment:
    notes: tuple[NoteAssessment, ...]
    extra_notes: int
    unmatched_played: tuple[PlayedNote, ...] = ()

    def __post_init__(self):
        object.__setattr__(self,"notes",tuple(self.notes))
        object.__setattr__(self,"unmatched_played",tuple(self.unmatched_played))

    @property
    def correct(self) -> int:
        return sum(n.status == "correct" for n in self.notes)


    @property
    def timing_quality(self) -> float:
        """1 when every attack is centred, 0 at the edge of its window."""
        ratios = [min(1.0, abs(n.observation.onset_residual)/n.observation.onset_tolerance)
                  for n in self.notes if n.observation is not None
                  and n.observation.onset_residual is not None
                  and n.observation.onset_tolerance > 0]
        return 1.0-sum(ratios)/len(ratios) if ratios else 0.0

    @property
    def attacks(self) -> int:
        """Distinct attack times in the graded notes (a chord is one)."""
        return len({round(n.note.start, 4) for n in self.notes})

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
    def flow_passed(self) -> bool:
        """Practice flow: wrong, missed and extra notes fail; timing fails
        only when an attack is clearly off, i.e. outside the onset tolerance
        (150 ms or a sixteenth at the local tempo) shown in red. Key-release
        timing fails a take only when hold grading is enabled."""
        if not self.notes or self.extra_notes:
            return False
        for entry in self.notes:
            if entry.status in ("missed", "wrong", "early", "late", "short", "long"):
                return False
        return True

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
             expected_seconds: Callable[[Note], tuple[float, float, float]] | None = None,
             observation_window: tuple[float, float] | None = None,
             grade_note_holds: bool = False) -> Assessment:
    """Score pitch, start timing, and held duration independently.

    Matching uses the nearest unused same-pitch onset in a generous window;
    onset tolerance determines correctness; release tolerance counts only when enabled.
    """
    if bpm <= 0:
        raise ValueError("Practice BPM must be positive")
    seconds_per_beat = SCHEDULER.seconds_per_beat(bpm)
    expected = [n for n in phrase.notes if hand == "both" or n.hand == hand]
    unused = set(range(len(played)))
    assessments: list[NoteAssessment] = []
    timing = []
    for note in expected:
        if expected_seconds is None:
            start = (note.start - phrase.start) * seconds_per_beat
            duration = (note.end - note.start) * seconds_per_beat
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
    by_pitch = defaultdict(list)
    for index, event in enumerate(played):
        by_pitch[event.pitch].append((event.onset, index))
    for attacks in by_pitch.values():
        attacks.sort()
    for note_index, (note, (start, _, _, local_spb)) in enumerate(zip(expected, timing)):
        window = max(SETTINGS.grading_match_window_min_seconds,
                     SETTINGS.grading_match_window_beats * local_spb)
        attacks = by_pitch[note.pitch]
        first = bisect_left(attacks, (start-window, -1))
        last = bisect_right(attacks, (start+window, len(played)))
        pairs.extend((abs(onset - start), note_index, event_index)
                     for onset, event_index in attacks[first:last])
    matched = {}
    for _, note_index, event_index in sorted(pairs):
        if note_index not in matched and event_index in unused:
            matched[note_index] = event_index
            unused.remove(event_index)

    # Reserve wrong-pitch presses after all exact-pitch matches, for every
    # source attack even when the caller requests only bounded observations.
    # This is the same assignment for live projection and full settlement.
    for note_index, note in enumerate(expected):
        if not unused:
            break
        if note_index in matched:
            continue
        start, _, _, spb = timing[note_index]
        candidates = [(abs(played[j].onset-start),j) for j in unused
                      if abs(played[j].onset-start) <= onset_tolerance(spb)]
        if candidates:
            _, index = min(candidates)
            unused.remove(index)
            matched[note_index] = index

    for note_index, note in enumerate(expected):
        if observation_window is not None and not (
                observation_window[0] <= timing[note_index][0] <= observation_window[1]):
            continue
        if note_index not in matched:
            assessments.append(NoteAssessment(note, "missed", observation=observation_for(note_index)))
            continue
        observation = observation_for(note_index, matched[note_index])
        hold_grade = (("long" if observation.unreleased else observation.hold_error)
                      if grade_note_holds else None)
        status = ("wrong" if observation.pitch_error else observation.timing_error or
                  hold_grade or "correct")
        assessments.append(NoteAssessment(note, status,
            observation.actual_pitch if observation.pitch_error else None, observation))
    leftovers = tuple(played[i] for i in sorted(unused))
    return Assessment(tuple(assessments), len(leftovers), leftovers)


class Recorder:
    """Collect note events, including overlapping presses of the same pitch."""

    def __init__(self) -> None:
        self.presses: list[PlayedNote] = []
        self.active: dict[int, deque[int]] = defaultdict(deque)

    def add(self, pitch: int, is_on: bool, at_seconds: float) -> PlayedNote | None:
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
            return self.presses[index]
        elif self.active[pitch]:
            index = self.active[pitch].popleft()
            press = self.presses[index]
            self.presses[index] = replace(press, release=at_seconds)
            return self.presses[index]
