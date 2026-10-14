"""Translate an assessment into score-relative annotations using Verovio IDs.

A feedback marker is never assigned an invented notehead coordinate. Unmatched
notes remain in the textual assessment and are reported separately.
"""
from __future__ import annotations

from .music import Phrase, note_name
from .practice import Assessment
from .score_geometry import locate_beat


def project_assessment(assessment: Assessment, phrase: Phrase, bpm: float, layout: dict, *, played_from_beat: float = 0.0) -> dict:
    """Return positioned note errors and leftover played notes for one attempt.

    Engraving matches require both pitch and onset, with a bounded tolerance
    for MIDI-to-notation quantization. Each glyph can be used only once, so
    repeated notes and unisons never get attached to the same notehead.
    """
    glyphs = list(layout.get("notes", []))
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
        if not options:
            unmapped += 1
            continue
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
            "beat": beat,
        })
    # The extra note has no notated notehead. Use the real beat-time x
    # coordinate, with an explicit estimated-position marker near the system.
    for played in assessment.unmatched_played:
        beat = played_from_beat + played.onset * bpm / 60
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
