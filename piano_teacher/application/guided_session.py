"""Own untimed source fragments, teaching-controller lifetime and hints.

The application supplies immutable source selections and sampled MIDI facts.
It keeps revision/transport transitions and durable learner writes. This owner
retains neither a LearningPlan nor an engine, lock, store or callback.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..exercise_generator import ExerciseVariant
from .guided_fragment import select_guided_fragment
from ..music import Phrase, source_note_id
from ..teaching import TeachingConfig, TeachingController


@dataclass(frozen=True)
class GuidedFragment:
    variant: ExerciseVariant
    start_beat: float
    end_beat: float
    phrase: Phrase

    @property
    def beat_range(self) -> tuple[float, float]:
        return self.start_beat, self.end_beat


def select_fragment(variant: ExerciseVariant, boundaries: tuple[float, ...],
                    *, from_beat: float) -> GuidedFragment:
    """Validate before canceling a live session; skip only empty guided ideas."""
    phrase = variant.phrase
    choice = select_guided_fragment(phrase, boundaries, from_beat)
    first, last = choice.first_index, choice.end_index
    start, end = choice.start, choice.end
    absolute_start, absolute_end = phrase.start+start, phrase.start+end
    display = Phrase(phrase.number, phrase.first_bar+first, phrase.first_bar+last-1,
        absolute_start, absolute_end,
        tuple(note for note in phrase.notes
              if absolute_start-1e-7 <= note.start < absolute_end-1e-7))
    return GuidedFragment(variant, start, end, display)


class GuidedSession:
    def __init__(self):
        self.controller: TeachingController | None = None
        self.fragment: GuidedFragment | None = None
        self.persistent_hints = False
        self.prepared = False
        self.return_context: tuple[str, float] | None = None
        self._stage_key = ""

    def stop(self) -> None:
        # Retain the controller's physical held-key history until a mode change.
        if self.controller is not None:
            self.controller.stop()
        self.prepared = False
        self.return_context = None

    def clear_selection(self) -> None:
        """Leave untimed teaching; an accepted rhythm return remains available."""
        self.controller = None
        self.fragment = None
        self._stage_key = ""

    def bind(self, fragment: GuidedFragment, *, stage_key: str, revision: int,
             now: float, connected: bool, recovery: bool = False) -> None:
        self.fragment = fragment
        self._stage_key = stage_key
        self.prepared = False
        self.return_context = (stage_key, fragment.start_beat) if recovery else None
        if self.controller is None:
            self.controller = TeachingController(TeachingConfig(persistent_hints=self.persistent_hints))
        self.controller.bind(stage_key=stage_key, revision=revision,
            variant=fragment.variant, fragment_start=fragment.start_beat,
            fragment_end=fragment.end_beat, now=now, connected=connected)

    def advance(self, *, connected: bool, now: float) -> None:
        """Tick untimed note recognition with explicit MIDI-connection facts."""
        if self.controller is None:
            return
        self.controller.set_connected(connected, now=now)
        self.controller.tick(now=now)

    def commit_completed_preparation(
        self, *, learning: bool, remediation_active: bool,
        fingerprint: str, stage_key: str,
        current_unit, record_preparation,
    ) -> bool:
        """Record one completed idea; do not award timed practice mastery.

        Callbacks resolve the current source unit and save a completion only
        after the controller confirms it. Never accesses the engine or store.
        """
        if (self.prepared or remediation_active or not learning
                or self.controller is None):
            return False
        from time import monotonic
        snapshot = self.controller.snapshot(now=monotonic())
        if not snapshot["completed"]:
            return False
        record_preparation(
            fingerprint=fingerprint, stage_key=stage_key,
            unit=current_unit(), assisted_count=snapshot["assisted_count"])
        self.prepared = True
        return True

    def set_hints(self, enabled: bool, *, now: float) -> None:
        self.persistent_hints = bool(enabled)
        if self.controller is not None:
            self.controller.set_hints(self.persistent_hints, now=now)

    def marks(self, snapshot: dict, layout: dict) -> list[dict]:
        if self.fragment is None:
            return []
        variant, phrase = self.fragment.variant, self.fragment.phrase
        source = {f"{self._stage_key}:{index}": note
                  for index, note in zip(variant.source_indices, variant.notes)}
        glyphs = {glyph["id"]: glyph for glyph in layout.get("notes", [])}
        local_indices = {id(note): index for index, note in enumerate(phrase.notes)}
        settled = {entry["id"]: entry for entry in snapshot.get("note_feedback", [])}
        for entry in snapshot.get("expected_notes", []):
            if settled.get(entry["id"], {}).get("status") != "wrong":
                settled[entry["id"]] = {**entry, "status": "expected"}
        marks = []
        for identifier, entry in settled.items():
            note = source.get(identifier)
            if note is None:
                continue
            local_index = local_indices.get(id(note))
            if local_index is None:
                continue
            canonical_id = source_note_id(note, local_index)
            glyph = glyphs.get(layout.get("attack_map", {}).get(canonical_id))
            if (glyph is not None and glyph.get("is_attack")
                    and glyph.get("pitch") == note.pitch and glyph.get("hand") == note.hand):
                marks.append({**glyph, "target_id": identifier, "status": entry["status"],
                              "hint_used": bool(entry.get("hint_used", False))})
        return marks
