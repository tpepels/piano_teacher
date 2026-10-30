"""Immediate physical MIDI display events. Never grants note credit or mastery.

Key-down feedback is provisional: final pitch, onset and release scoring still
belongs to practice.evaluate and the authoritative musical clock.
"""
from __future__ import annotations

from collections import deque

from .music import Phrase, source_note_id
from .exercise_contracts import TempoMap


class LiveInputView:
    def __init__(self) -> None:
        self.held: dict[int, int] = {}
        self.events: deque[dict] = deque(maxlen=32)
        self.sequence = 0
        self.used: set[int] = set()

    def reset_attempt(self) -> None:
        self.used.clear()
        self.events.clear()

    def clear_device(self) -> None:
        self.held.clear()
        self.reset_attempt()

    def receive(
        self, *, pitch: int, is_on: bool, now: float, phrase: Phrase | None,
        hand: str, bpm: float, from_beat: float, run_at: float,
        running: bool, paused: bool, preview: bool, mode: str,
        transport_id: int, tempo_map: TempoMap | None = None,
    ) -> None:
        if not 0 <= pitch <= 127:
            return
        if not is_on:
            remaining = self.held.get(pitch, 0) - 1
            if remaining > 0:
                self.held[pitch] = remaining
            else:
                self.held.pop(pitch, None)
            return

        self.held[pitch] = self.held.get(pitch, 0) + 1
        status = "heard"
        source = ""
        # A mistyped pitch is located against a real expected staff note on
        # this beat, not against a guessed page coordinate. The transient
        # visual marker never consumes an expected note or awards credit.
        reference_source = ""
        if running and not paused and mode in ("practice", "perform"):
            if now < run_at:
                status = "count_in"
            elif preview:
                status = "heard"
            elif phrase is not None and bpm > 0:
                # Match only plausible attacks. This onset preview cannot claim
                # correctness of duration or override final assessment.
                at = now - run_at
                origin = tempo_map.seconds_at(from_beat) if tempo_map else 0.0

                def expected(note):
                    beat = note.start - phrase.start
                    if tempo_map is not None:
                        return (tempo_map.seconds_at(beat) - origin,
                                60.0 / tempo_map.bpm_at(beat))
                    return ((beat - from_beat) * 60.0 / bpm, 60.0 / bpm)

                candidates = []
                nearby = []
                for index, note in enumerate(phrase.notes):
                    if ((hand != "both" and note.hand != hand) or
                            note.start - phrase.start < from_beat - 1e-7):
                        continue
                    expected_at, seconds_per_beat = expected(note)
                    distance = abs(at - expected_at)
                    if distance <= .1:
                        nearby.append((distance, abs(pitch - note.pitch),
                                       index, note))
                    if (index not in self.used and note.pitch == pitch and
                            distance <= max(0.35, .65 * seconds_per_beat)):
                        candidates.append((distance, index, note, expected_at))
                if candidates:
                    _, index, note, expected_at = min(
                        candidates, key=lambda entry: (entry[0], entry[1]))
                    self.used.add(index)
                    source = source_note_id(note, index)
                    drift = at - expected_at
                    status = "on_time" if abs(drift) <= .1 else "early" if drift < 0 else "late"
                else:
                    status = "unexpected"
                    # Only exact source attacks can receive provisional
                    # correctness; wrong pitches may reference nearby ink.
                    if nearby:
                        _, _, index, reference = min(
                            nearby, key=lambda entry: entry[:3])
                        reference_source = source_note_id(reference, index)

        self.sequence += 1
        self.events.append({
            "sequence": self.sequence, "pitch": pitch, "status": status,
            "source_id": source, "reference_source_id": reference_source,
            "transport_id": transport_id, "received_at": now,
        })

    def snapshot(
        self, *, now: float, phrase: Phrase | None, hand: str,
        beat: float, playing: bool,
    ) -> dict:
        # Small bounded event history makes brief taps visible even when the key
        # has already been released before the next Godot HTTP poll.
        events = [
            {k: v for k, v in event.items() if k != "received_at"}
            | {"age": max(0.0, now - event["received_at"])}
            for event in self.events
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
            "midi_visual_events": events,
            "midi_next_pitches": expected,
        }
