"""Untimed, source-traceable guided note recognition.

The controller consumes backend MIDI events and exposes presentation state. It
has no transport, recorder, assessment, persistence, or UI dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass

from .exercise_generator import ExerciseVariant
from .music import note_name


@dataclass(frozen=True)
class TeachingConfig:
    chord_window_seconds: float = .25
    stall_seconds: float = 3.0
    persistent_hints: bool = False


class TeachingController:
    def __init__(self, config: TeachingConfig = TeachingConfig()):
        self.config = config
        self._phase = "ready"
        self._revision = 0
        self._targets: list[list[dict]] = []
        self._target_index = 0
        self._assisted_count = 0
        self._connected = False
        self._keys: set[tuple[int, int]] = set()
        self._blocked_keys: set[tuple[int, int]] = set()
        self._pressed_at: dict[tuple[int, int], float] = {}
        self._event_floor = 0.0
        self._paused_at = 0.0
        self._feedback: dict[str, dict] = {}
        self._candidates: dict[tuple[int, int], float] = {}
        self._persistent_hints = config.persistent_hints
        self._hint_reason = ""
        self._hint_used = False
        self._waiting_since = 0.0

    def bind(self, *, stage_key: str, revision: int, variant: ExerciseVariant,
             fragment_start: float, fragment_end: float, now: float,
             connected: bool):
        held = self._keys | self._blocked_keys if self._connected and connected else set()
        self._revision = revision
        self._targets = []
        attacks: dict[float, list[dict]] = {}
        for i, note in enumerate(variant.notes):
            local = note.start - variant.phrase.start
            if fragment_start - 1e-7 <= local < fragment_end - 1e-7:
                attacks.setdefault(round(local, 6), []).append({
                    "id": f"{stage_key}:{variant.source_indices[i]}",
                    "pitch": note.pitch, "label": note_name(note.pitch),
                    "beat": local - fragment_start, "source_beat": note.start,
                    "end_beat": note.end - variant.phrase.start - fragment_start,
                    "hand": note.hand,
                })
        self._targets = [attacks[beat] for beat in sorted(attacks)]
        self._target_index = 0
        self._assisted_count = 0
        self._connected = connected
        self._phase = "introducing" if connected else "disconnected"
        self._keys.clear()
        self._blocked_keys = held
        self._pressed_at = {key: at for key, at in self._pressed_at.items() if key in held}
        self._event_floor = now
        self._feedback.clear()
        self._candidates.clear()
        self._hint_reason = ""
        self._hint_used = False
        self._waiting_since = now

    def start(self, *, now: float):
        if self._connected and self._phase in ("introducing", "ready"):
            self._target_index = 0
            self._assisted_count = 0
            self._feedback.clear()
            self._candidates.clear()
            self._phase = "guided_wait" if self._targets else "guided_complete"
            self._waiting_since = now
            self._event_floor = now
            self._hint_reason = ""
            self._hint_used = self._persistent_hints

    def pause(self, *, now: float):
        if self._phase != "guided_wait":
            return
        self.tick(now=now)
        self._paused_at = now
        self._event_floor = now
        self._phase = "paused"
        self._blocked_keys.update(self._keys)
        self._keys.clear()
        self._candidates.clear()

    def resume(self, *, now: float):
        if self._phase == "paused" and self._connected:
            self._waiting_since += max(0.0, now - self._paused_at)
            self._event_floor = now
            self._phase = "guided_wait"

    def stop(self):
        self._phase = "ready" if self._connected else "disconnected"
        self._target_index = 0
        self._assisted_count = 0
        self._blocked_keys.update(self._keys)
        self._keys.clear()
        self._candidates.clear()
        self._feedback.clear()
        self._hint_reason = ""
        self._hint_used = False

    def set_connected(self, connected: bool, *, now: float):
        if bool(connected) == self._connected:
            return
        self._connected = bool(connected)
        self._phase = "ready" if connected else "disconnected"
        self._keys.clear()
        self._blocked_keys.clear()
        self._pressed_at.clear()
        self._candidates.clear()
        self._event_floor = now
        self._hint_reason = ""
        self._hint_used = False

    def receive(self, *, pitch: int, is_on: bool, channel: int = 0, at: float):
        if (not isinstance(pitch, int) or not 0 <= pitch <= 127
                or not isinstance(channel, int) or not 0 <= channel <= 15
                or channel == 9 or not self._connected):
            return
        key = channel, pitch
        if not is_on:
            # A callback may wait behind a transition lock. Its older release
            # still cleans up that physical press, but cannot release a newer one.
            pressed_at = self._pressed_at.get(key)
            if pressed_at is not None and at >= pressed_at:
                self._keys.discard(key)
                self._blocked_keys.discard(key)
                self._pressed_at.pop(key, None)
                self._candidates.pop(key, None)
            return
        if at < self._event_floor:
            return
        self._pressed_at.setdefault(key, at)
        if self._phase == "paused" or any(p == pitch for _, p in self._blocked_keys):
            self._blocked_keys.add(key)
            return
        fresh = not any(held_pitch == pitch for _, held_pitch in self._keys)
        self._keys.add(key)
        if not fresh or self._phase != "guided_wait":
            return
        self.tick(now=at)
        expected = self._targets[self._target_index]
        required = {note["pitch"] for note in expected}
        if pitch not in required:
            self._hint_reason = "wrong_note"
            self._hint_used = True
            for note in expected:
                self._feedback[note["id"]] = {
                    "id": note["id"], "pitch": pitch, "beat": note["beat"],
                    "status": "wrong", "hint_used": True,
                }
            return
        self._candidates[key] = at
        attacks = self._candidates.values()
        within_window = max(attacks) - min(attacks) <= self.config.chord_window_seconds + 1e-9
        if required <= {p for _, p in self._candidates} and within_window:
            for note in expected:
                self._feedback[note["id"]] = {
                    "id": note["id"], "pitch": note["pitch"], "beat": note["beat"],
                    "status": "assisted" if self._hint_used else "correct",
                    "hint_used": self._hint_used,
                }
            self._target_index += 1
            self._assisted_count += int(self._hint_used)
            self._candidates.clear()
            self._waiting_since = at
            self._hint_reason = ""
            self._hint_used = self._persistent_hints
            if self._target_index == len(self._targets):
                self._phase = "guided_complete"

    def set_hints(self, enabled: bool, *, now: float):
        self.tick(now=now)
        self._persistent_hints = bool(enabled)
        if enabled and self._phase == "guided_wait":
            self._hint_used = True

    def tick(self, *, now: float):
        if self._phase == "guided_wait" and now - self._waiting_since >= self.config.stall_seconds:
            if not self._hint_reason:
                self._hint_reason = "stall"
            self._hint_used = True
        self._candidates = {key: at for key, at in self._candidates.items()
                            if now - at <= self.config.chord_window_seconds + 1e-9}

    def snapshot(self, *, now: float) -> dict:
        self.tick(now=now)
        active_hint = self._phase == "guided_wait" and (self._persistent_hints or bool(self._hint_reason))
        return {
            "phase": self._phase, "revision": self._revision,
            "completed": self._phase == "guided_complete", "mastery_eligible": False,
            "assisted_count": self._assisted_count,
            "completion": ("assisted" if self._assisted_count else "unassisted")
                if self._phase == "guided_complete" else None,
            "target_index": self._target_index, "target_count": len(self._targets),
            "expected_notes": [dict(note) for note in self._targets[self._target_index]]
                if self._target_index < len(self._targets) else [],
            "heard_pitches": sorted({pitch for _, pitch in self._keys}),
            "hint_visible": active_hint,
            "hint_reason": (self._hint_reason or "persistent") if active_hint else "",
            "note_feedback": [dict(note) for note in self._feedback.values()],
        }
