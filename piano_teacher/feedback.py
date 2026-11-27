"""Translate assessed notes into facts in canonical source coordinates."""
from __future__ import annotations

from .music import Phrase, note_name, source_note_id
from .practice import Assessment, note_dimensions
from typing import Callable
from .application.musical_scheduler import SCHEDULER


def project_assessment(assessment: Assessment, phrase: Phrase, bpm: float, *,
                       played_from_beat: float = 0.0,
                       elapsed_to_beat: Callable[[float], float] | None = None) -> dict:
    """Project grades by source identity; the renderer owns glyph placement."""
    # Hand-built fixtures may omit a source ID; their deterministic source
    # index is still authoritative, never a guessed pitch/onset match.
    anonymous_identity = {}
    anonymous_value = {}
    for index, note in enumerate(phrase.notes):
        if not note.source_id:
            source = source_note_id(note, index)
            anonymous_identity[id(note)] = source
            anonymous_value.setdefault(note, source)
    result = []
    unmapped = 0
    for entry in assessment.notes:
        beat = entry.note.start - phrase.start
        source = entry.note.source_id
        if not source:
            source = anonymous_identity.get(id(entry.note))
            if source is None:
                source = anonymous_value.get(entry.note)
        if source is None:
            unmapped += 1
            continue
        observation = entry.observation
        held = (observation is not None and observation.unreleased
                and observation.actual_onset is not None)
        result.append({
            "status": entry.status,
            # Pitch, onset and release are independent observations. A key
            # still held past its release is "unreleased", never "short".
            "dimensions": note_dimensions(entry),
            "pitch": entry.note.pitch,
            "source_id": source,
            "beat": beat,
            # Attempt-seconds deadline until which a still-held key is within
            # the grader's own hold tolerance. Live display only (see
            # PracticeEngine._live_feedback); grading never reads it.
            **({"hold_tolerance_until":
                observation.actual_onset + (observation.expected_release
                    - observation.expected_onset) + observation.duration_tolerance}
               if held else {}),
        })
    # Extra attacks carry their played beat and pitch for presentation.
    for played in assessment.unmatched_played:
        beat = (elapsed_to_beat(played.onset) if elapsed_to_beat is not None
                else played_from_beat + SCHEDULER.seconds_beats(played.onset,bpm))
        if beat < 0 or beat > phrase.sounding_end - phrase.start:
            unmapped += 1
            continue
        result.append({
            "status": "extra",
            "pitch": played.pitch, "label": note_name(played.pitch),
            "beat": beat, "estimated": True,
        })
    return {"marks": result, "unmapped": unmapped}
