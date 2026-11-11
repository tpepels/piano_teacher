"""Immediate physical MIDI display events. Never grants note credit or mastery.

Key-down and key-up feedback is provisional: final pitch, onset and release
scoring still belongs to practice.evaluate and the authoritative musical clock.
``receive`` returns one unsequenced event; the engine stamps it with its take
identity and publishes it through the single acknowledged FeedbackEventLog.
A key-up is bound to the same source note as its key-down (FIFO per pitch, as
in the Recorder), so an early release can be shown as soon as it happens.
"""
from __future__ import annotations

from collections import deque
from bisect import bisect_left, bisect_right

from .music import Phrase, source_note_id
from .exercise_contracts import TempoMap
from .grading_tolerance import onset_tolerance, duration_tolerance
from .lesson_settings import SETTINGS


class LiveInputView:
    def __init__(self) -> None:
        self.held: dict[int, int] = {}
        # Recent key-downs for the on-screen keyboard only (not score ink).
        self.recent: deque[dict] = deque(maxlen=32)
        self.used: set[int] = set()
        # Per pitch, FIFO of (source_id, attack_at, expected_seconds,
        # seconds_per_beat) for presses that are still down. ``attack_at`` is
        # on the engine's musical clock (see ``receive``). Unmatched presses
        # hold a None source so release pairing stays FIFO.
        self._down: dict[int, deque[tuple[str | None, float, float, float]]] = {}
        self._indexed_phrase: Phrase | None = None
        self._onset_beats: list[float] = []
        self._ordered_notes: list[tuple[int, object]] = []

    def prepare(self, phrase: Phrase) -> None:
        """Build the MIDI attack index before the performance starts.

        A physical MIDI callback should not sort an entire score or scan
        thousands of unrelated noteheads on each keystroke.
        """
        if self._indexed_phrase is phrase:
            return
        self._indexed_phrase = phrase
        ordered = sorted(enumerate(phrase.notes),
                         key=lambda item: (item[1].start, item[0]))
        self._ordered_notes = ordered
        self._onset_beats = [note.start - phrase.start for _, note in ordered]

    def reset_attempt(self) -> None:
        # Keys still held from an earlier take never release into this one.
        self.used.clear()
        self.recent.clear()
        self._down.clear()

    def clear_device(self) -> None:
        self.held.clear()
        self.reset_attempt()

    def receive(
        self, *, pitch: int, is_on: bool, now: float, phrase: Phrase | None,
        hand: str, bpm: float, from_beat: float, run_at: float,
        running: bool, paused: bool, preview: bool, mode: str,
        transport_id: int, tempo_map: TempoMap | None = None,
        at: float | None = None,
    ) -> dict | None:
        """``now`` is the corrected wall time of the key event; ``at`` is the
        same instant on the engine's graded musical clock in seconds since
        ``run_at``, the value the Recorder receives. It stands still from
        Pause until grading resumes, so held time across a pause matches the
        settled grade. Without it, ``now - run_at`` is used (no pause).
        """
        if not 0 <= pitch <= 127:
            return None
        if at is None:
            at = now - run_at
        if not is_on:
            remaining = self.held.get(pitch, 0) - 1
            if remaining > 0:
                self.held[pitch] = remaining
            else:
                self.held.pop(pitch, None)
            return self._release(pitch, now, at, running=running, paused=paused,
                                 transport_id=transport_id)

        self.held[pitch] = self.held.get(pitch, 0) + 1
        status = "heard"
        source = ""
        # A mistyped pitch is located against a real expected staff note on
        # this beat, not against a guessed page coordinate. The transient
        # visual marker never consumes an expected note or awards credit.
        reference_source = ""
        matched_hold: tuple[float, float] | None = None
        if running and not paused and mode in ("practice", "perform"):
            if at < 0:
                status = "count_in"
            elif preview:
                status = "heard"
            elif phrase is not None and bpm > 0:
                # Match only plausible attacks. This onset preview cannot claim
                # correctness of duration or override final assessment.
                origin = tempo_map.seconds_at(from_beat) if tempo_map else 0.0

                def expected(note):
                    beat = note.start - phrase.start
                    if tempo_map is not None:
                        return (tempo_map.seconds_at(beat) - origin,
                                60.0 / tempo_map.bpm_at(beat))
                    return ((beat - from_beat) * 60.0 / bpm, 60.0 / bpm)

                def held_seconds(note):
                    # Identical to practice.evaluate's expected duration.
                    attack = note.start - phrase.start
                    release = min(note.end, phrase.end) - phrase.start
                    if tempo_map is not None:
                        return tempo_map.seconds_at(release) - tempo_map.seconds_at(attack)
                    return (release - attack) * 60.0 / bpm

                candidates = []
                nearby = []
                self.prepare(phrase)
                beat = (tempo_map.beat_at(origin + at) if tempo_map is not None
                        else from_beat + at * bpm / 60.0)
                # All matching windows are under ~2 beats at allowed tempos.
                # A buffer handles tempo changes at the boundary.
                search_radius = max(2.0, 0.5 * max(
                    bpm, tempo_map.bpm_at(beat) if tempo_map is not None else bpm)/60.0)
                left = bisect_left(self._onset_beats, beat - search_radius)
                right = bisect_right(self._onset_beats, beat + search_radius)
                for index, note in self._ordered_notes[left:right]:
                    if ((hand != "both" and note.hand != hand) or
                            note.start - phrase.start < from_beat - 1e-7):
                        continue
                    expected_at, seconds_per_beat = expected(note)
                    distance = abs(at - expected_at)
                    if distance <= onset_tolerance(seconds_per_beat):
                        nearby.append((distance, abs(pitch - note.pitch),
                                       index, note))
                    if (index not in self.used and note.pitch == pitch and
                            distance <= max(SETTINGS.grading_match_window_min_seconds,
                                            SETTINGS.grading_match_window_beats * seconds_per_beat)):
                        candidates.append((distance, index, note, expected_at))
                if candidates:
                    _, index, note, expected_at = min(
                        candidates, key=lambda entry: (entry[0], entry[1]))
                    self.used.add(index)
                    source = source_note_id(note, index)
                    drift = at - expected_at
                    spb = expected(note)[1]
                    status = ("on_time" if abs(drift) <= onset_tolerance(
                        spb) else "early" if drift < 0 else "late")
                    matched_hold = (held_seconds(note), spb)
                else:
                    status = "unexpected"
                    # Only exact source attacks can receive provisional
                    # correctness; wrong pitches may reference nearby ink.
                    if nearby:
                        _, _, index, reference = min(
                            nearby, key=lambda entry: entry[:3])
                        reference_source = source_note_id(reference, index)

        self._down.setdefault(pitch, deque()).append(
            (source or None, at, *(matched_hold or (0.0, 0.0))))
        event = {
            "kind": "attack", "pitch": pitch, "status": status,
            "source_id": source, "reference_source_id": reference_source,
            "transport_id": transport_id, "received_at": now,
        }
        self.recent.append(event)
        return dict(event)

    def _release(self, pitch: int, now: float, at: float, *, running: bool, paused: bool,
                 transport_id: int) -> dict | None:
        """Bind a key-up to its source note and classify the observed hold.

        Uses the grader's own duration tolerance, so the provisional verdict
        agrees with practice.evaluate for the same press. Settled assessment
        still overrides it; this never changes grading.
        """
        pending = self._down.get(pitch)
        if not pending:
            return None
        source, attack_at, expected, spb = pending.popleft()
        if not pending:
            self._down.pop(pitch, None)
        if source is None or not running or paused:
            return None
        held = max(0.0, at - attack_at)
        slack = duration_tolerance(expected, spb)
        release = ("short" if held < expected - slack else
                   "long" if held > expected + slack else "on_time")
        return {"kind": "release", "pitch": pitch, "source_id": source,
                "release": release, "held_seconds": held,
                "expected_seconds": expected, "transport_id": transport_id,
                "received_at": now}

    def snapshot(
        self, *, now: float, phrase: Phrase | None, hand: str,
        beat: float, playing: bool,
    ) -> dict:
        # Bounded key-down history keeps brief taps visible on the keyboard
        # even when the key was released before the next state poll. Score
        # feedback never reads this; it consumes the FeedbackEventLog.
        events = [
            {k: v for k, v in event.items() if k not in ("received_at", "kind")}
            | {"age": max(0.0, now - event["received_at"])}
            for event in self.recent
            if 0 <= now - event["received_at"] <= 1.2
        ]
        expected: list[int] = []
        if playing and phrase is not None:
            active = [
                note for note in phrase.notes
                if (hand == "both" or note.hand == hand)
                and note.start - phrase.start >= beat - 0.25
            ]
            if active:
                first = min(note.start for note in active)
                expected = sorted({
                    note.pitch for note in active
                    if abs(note.start - first) <= 0.015
                })
        return {
            "midi_held_pitches": sorted(self.held),
            "midi_recent_keys": events,
            "midi_next_pitches": expected,
        }
