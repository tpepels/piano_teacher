"""Translate an assessment into score-relative annotations using Verovio IDs.

A feedback marker is never assigned an invented notehead coordinate. Unmatched
notes remain in the textual assessment and are reported separately.
"""
from __future__ import annotations

from .music import Phrase, note_name, source_note_id
from .practice import Assessment, note_dimensions
from typing import Callable
from .engraving.geometry import locate_beat
from .application.musical_scheduler import SCHEDULER


def project_assessment(assessment: Assessment, phrase: Phrase, bpm: float, layout: dict, *,
                       played_from_beat: float = 0.0,
                       elapsed_to_beat: Callable[[float], float] | None = None) -> dict:
    """Return positioned note errors and leftover played notes for one attempt.

    Production exercises map canonical source IDs directly to their attack
    glyphs. Anonymous hand-built legacy layouts retain a limited pitch/onset
    compatibility path; imported notes cannot enter that fallback.
    """
    glyphs = list(layout.get("notes", []))
    strict = layout.get('mapping_schema') == 'source-note-v1'
    if strict:
        from .lesson_validation import require_lesson_alignment
        require_lesson_alignment(phrase,layout,'both')
        by_id = {glyph.get('id'): glyph for glyph in glyphs}
        by_source = {source: by_id[identifier]
                     for source, identifier in layout['attack_map'].items()}
        # Canonical notes already carry their source ID. Only anonymous
        # callers need the phrase's stable fallback index, including a
        # value-equivalent copied Note accepted by the existing API.
        anonymous_identity = {}
        anonymous_value = {}
        for index, note in enumerate(phrase.notes):
            if not note.source_id:
                source = source_note_id(note, index)
                anonymous_identity[id(note)] = source
                anonymous_value.setdefault(note, source)
    elif any(entry.note.source_id for entry in assessment.notes):
        raise ValueError('Canonical source feedback requires explicit engraved identity mapping')
    unused = set() if strict else set(range(len(glyphs)))
    result = []
    unmapped = 0
    for entry in assessment.notes:
        beat = entry.note.start - phrase.start
        if strict:
            source = entry.note.source_id
            if not source:
                source = anonymous_identity.get(id(entry.note))
                if source is None:
                    source = anonymous_value.get(entry.note)
            glyph = by_source.get(source)
            if glyph is None:
                unmapped += 1
                continue
        else:
            options = [
                (abs(float(glyphs[i]["beat"]) - beat), i)
                for i in unused
                if glyphs[i].get("pitch") == entry.note.pitch
                and abs(float(glyphs[i]["beat"]) - beat) <= 0.125
            ]
            if not options:
                unmapped += 1
                continue
            _, index = min(options)
            unused.remove(index)
            glyph = glyphs[index]
        observation = entry.observation
        held = (observation is not None and observation.unreleased
                and observation.actual_onset is not None)
        result.append({
            "status": entry.status,
            # Pitch, onset and release are independent observations. A key
            # still held past its release is "unreleased", never "short".
            "dimensions": note_dimensions(entry),
            "page": int(glyph["page"]),
            "x": float(glyph["x"]),
            "y": float(glyph["y"]),
            "pitch": entry.note.pitch,
            "note_id": glyph["id"],
            **({'source_id':glyph['source_id']} if strict else {}),
            "beat": beat,
            # Attempt-seconds deadline until which a still-held key is within
            # the grader's own hold tolerance. Live display only (see
            # PracticeEngine._live_feedback); grading never reads it.
            **({"hold_tolerance_until":
                observation.actual_onset + (observation.expected_release
                    - observation.expected_onset) + observation.duration_tolerance}
               if held else {}),
        })
    # The extra note has no notated notehead. Use the real beat-time x
    # coordinate, with an explicit estimated-position marker near the system.
    for played in assessment.unmatched_played:
        beat = (elapsed_to_beat(played.onset) if elapsed_to_beat is not None
                else played_from_beat + SCHEDULER.seconds_beats(played.onset,bpm))
        if beat < 0 or beat > layout.get("beats", 0):
            unmapped += 1
            continue
        point = locate_beat(layout, beat)
        result.append({
            "status": "extra", "page": int(point["page"]),
            "x": float(point["x"]), "y": max(0.0, float(point["top"]) - 0.020),
            "pitch": played.pitch, "label": note_name(played.pitch),
            "beat": beat, "estimated": True,
        })
    return {"marks": result, "unmapped": unmapped}
