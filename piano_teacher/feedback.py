"""Translate an assessment into score-relative annotations using Verovio IDs.

A feedback marker is never assigned an invented notehead coordinate. Unmatched
notes remain in the textual assessment and are reported separately.
"""
from __future__ import annotations

from .music import Phrase, note_name, source_note_id
from .practice import Assessment
from typing import Callable
from .rendering.legacy.geometry import locate_beat


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
    elif any(entry.note.source_id for entry in assessment.notes):
        raise ValueError('Canonical source feedback requires explicit engraved identity mapping')
    by_id = {glyph.get('id'): glyph for glyph in glyphs}
    unused = set(range(len(glyphs)))
    result = []
    unmapped = 0
    for entry in assessment.notes:
        beat = entry.note.start - phrase.start
        options = [
            (abs(float(glyphs[i]["beat"]) - beat), i)
            for i in unused
            if glyphs[i].get("pitch") == entry.note.pitch
            and abs(float(glyphs[i]["beat"]) - beat) <= 0.125
        ]
        if strict:
            index = next((i for i,note in enumerate(phrase.notes) if note is entry.note),None)
            if index is None:
                index = next((i for i,note in enumerate(phrase.notes) if note == entry.note),None)
            source = source_note_id(entry.note,index) if index is not None else entry.note.source_id
            glyph = by_id.get(layout['attack_map'].get(source))
            if glyph is None:
                unmapped += 1
                continue
        elif not options:
            unmapped += 1
            continue
        else:
            _, index = min(options)
            unused.remove(index)
            glyph = glyphs[index]
        result.append({
            "status": entry.status,
            "page": int(glyph["page"]),
            "x": float(glyph["x"]),
            "y": float(glyph["y"]),
            "pitch": entry.note.pitch,
            "note_id": glyph["id"],
            **({'source_id':glyph['source_id']} if strict else {}),
            "beat": beat,
        })
    # The extra note has no notated notehead. Use the real beat-time x
    # coordinate, with an explicit estimated-position marker near the system.
    for played in assessment.unmatched_played:
        beat = (elapsed_to_beat(played.onset) if elapsed_to_beat is not None
                else played_from_beat + played.onset * bpm / 60)
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
