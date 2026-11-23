"""Keyboard display and projection of canonical grader observations.

Recorder alone pairs releases; evaluate alone assigns and judges source notes.
This view retains only physical held keys and recent keyboard display events.
"""
from __future__ import annotations

from collections import deque

from .exercise_contracts import TempoMap
from .music import Phrase
from .practice import NoteAssessment, note_dimensions
from .application.musical_scheduler import SCHEDULER


class LiveInputView:
    def __init__(self) -> None:
        self.held: dict[int, int] = {}
        self.recent: deque[dict] = deque(maxlen=32)

    def reset_attempt(self) -> None:
        self.recent.clear()

    def clear_device(self) -> None:
        self.held.clear()
        self.reset_attempt()

    def receive(
        self, *, pitch: int, is_on: bool, now: float, phrase: Phrase | None,
        hand: str, bpm: float, from_beat: float, run_at: float,
        running: bool, paused: bool, mode: str,
        transport_id: int, tempo_map: TempoMap | None = None,
        at: float | None = None, judgement: NoteAssessment | None = None,
    ) -> dict | None:
        if not 0 <= pitch <= 127:
            return None
        at = now - run_at if at is None else at
        if is_on:
            self.held[pitch] = self.held.get(pitch, 0) + 1
        else:
            remaining = self.held.get(pitch, 0) - 1
            if remaining > 0:
                self.held[pitch] = remaining
            else:
                self.held.pop(pitch, None)
        graded = running and not paused and mode in ("practice", "perform")
        observation = judgement.observation if judgement is not None and graded else None
        if not is_on:
            if observation is None or observation.pitch_error or observation.actual_release is None:
                return None
            return {"kind": "release", "pitch": pitch,
                    "source_id": judgement.note.source_id,
                    "release": note_dimensions(judgement)["release"],
                    "held_seconds": max(0., observation.actual_release-observation.actual_onset),
                    "expected_seconds": observation.expected_release-observation.expected_onset,
                    "transport_id": transport_id, "received_at": now}
        status, source, reference = "heard", "", ""
        if running and not paused and mode in ("practice", "perform"):
            if at < 0 and judgement is None:
                status = "count_in"
            else:
                status = "unexpected"
                if observation is not None:
                    if observation.pitch_error:
                        reference = judgement.note.source_id
                    else:
                        source = judgement.note.source_id
                        status = observation.timing_error or "on_time"
        origin = tempo_map.seconds_at(from_beat) if tempo_map is not None else 0.
        beat = (tempo_map.beat_at(origin + at) if tempo_map is not None
                else from_beat + SCHEDULER.seconds_beats(at, bpm))
        event = {"kind": "attack", "pitch": pitch, "status": status,
                 "source_id": source, "reference_source_id": reference,
                 "played_source_beat": beat,
                 "staff": (judgement.note.hand if judgement is not None else
                           hand if hand in ("right", "left") else
                           "right" if pitch >= 60 else "left"),
                 "transport_id": transport_id, "received_at": now}
        self.recent.append(event)
        return dict(event)

    def snapshot(self, *, now: float, phrase: Phrase | None, hand: str,
                 beat: float, playing: bool) -> dict:
        events = [{k: v for k, v in event.items() if k not in ("received_at", "kind")}
                  | {"age": max(0., now-event["received_at"])}
                  for event in self.recent if 0 <= now-event["received_at"] <= 1.2]
        expected: list[int] = []
        if playing and phrase is not None:
            active = [note for note in phrase.notes
                      if (hand == "both" or note.hand == hand)
                      and note.start-phrase.start >= beat-.25]
            if active:
                first = min(note.start for note in active)
                expected = sorted({note.pitch for note in active if abs(note.start-first) <= .015})
        return {"midi_held_pitches": sorted(self.held),
                "midi_recent_keys": events, "midi_next_pitches": expected}
