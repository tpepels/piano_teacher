"""Reject discrepancies between the required lesson and engraved noteheads."""
from __future__ import annotations
from .music import Phrase


def missing_engraved_notes(phrase: Phrase, layout: dict, hand: str) -> list[tuple[int,float]]:
    notes=[(n.pitch,n.start-phrase.start) for n in phrase.notes
           if hand == "both" or n.hand == hand]
    glyphs=list(layout.get("notes", []))
    used=set()
    missing=[]
    for pitch,beat in notes:
        candidates=[(abs(float(g["beat"])-beat),i) for i,g in enumerate(glyphs)
                    if i not in used and g.get("pitch")==pitch
                    and abs(float(g["beat"])-beat)<=.125]
        if candidates:
            _,i=min(candidates)
            used.add(i)
        else:
            missing.append((pitch,round(beat,5)))
    return missing


def require_lesson_alignment(phrase: Phrase, layout: dict, hand: str) -> None:
    missing=missing_engraved_notes(phrase,layout,hand)
    if missing:
        example=", ".join(f"{pitch}@{beat:g}" for pitch,beat in missing[:4])
        raise ValueError(
            f"Generated lesson engraving omitted {len(missing)} required note(s) "
            f"(MIDI pitch@beat: {example}). This lesson cannot be scored accurately.")
