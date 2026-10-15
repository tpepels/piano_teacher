"""Reject discrepancies between the required lesson and engraved noteheads."""
from __future__ import annotations
import math
from .music import Phrase, source_note_id


def _strict_missing(phrase: Phrase, layout: dict, hand: str):
    expected = {source_note_id(note,index): note for index,note in enumerate(phrase.notes)}
    if len(expected) != len(phrase.notes):
        raise ValueError('Required source-note identity is duplicated')
    glyphs = layout.get('notes', [])
    by_id = {glyph.get('id'): glyph for glyph in glyphs}
    if len(by_id) != len(glyphs):
        raise ValueError('Engraved attack/glyph identity is duplicated')
    attacks = layout.get('attack_map', {})
    actual = {}
    for glyph in glyphs:
        source = glyph.get('source_id')
        if source not in expected:
            raise ValueError('Engraved source identity is not a required note')
        note = expected[source]
        if glyph.get('pitch') != note.pitch or glyph.get('hand') != note.hand:
            raise ValueError('Engraved attack pitch/hand does not match its source identity')
        if (not all(isinstance(glyph.get(axis), (int,float)) and math.isfinite(glyph[axis])
                    and 0 <= glyph[axis] <= 1 for axis in ('x','y'))
                or type(glyph.get('page')) is not int or not 0 <= glyph['page'] < layout.get('pages',0)):
            raise ValueError('Source identity has no valid real engraved location')
        if abs(glyph.get('source_beat', float('inf'))-(note.start-phrase.start)) > 1e-10:
            raise ValueError('Engraved attack mapping has changed its precise source onset')
        if glyph.get('is_attack'):
            if source in actual or glyph.get('segment_index') != 0:
                raise ValueError('Duplicate engraved attack for required source identity')
            actual[source] = glyph['id']
        elif glyph.get('segment_index',0) <= 0:
            raise ValueError('A source attack has been relabelled as a continuation')
    if attacks != actual:
        raise ValueError('Engraved attack mapping disagrees with actual source glyphs')
    continuations = layout.get('continuation_map', {})
    for source, identifiers in continuations.items():
        if source not in attacks or any(identifier not in by_id or by_id[identifier].get('is_attack')
                                       or by_id[identifier].get('source_id') != source for identifier in identifiers):
            raise ValueError('Tied continuation has no matching original source attack')
    return [(note.pitch, round(note.start-phrase.start,5)) for source,note in expected.items()
            if (hand == 'both' or note.hand == hand) and source not in attacks]


def missing_engraved_notes(phrase: Phrase, layout: dict, hand: str) -> list[tuple[int,float]]:
    if layout.get('mapping_schema') == 'source-note-v1':
        return _strict_missing(phrase,layout,hand)
    if any(note.source_id for note in phrase.notes):
        raise ValueError('Canonical source notes require explicit engraved identity mapping')
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
        first_pitch=missing[0][0]
        available=sorted(round(float(g["beat"]),3) for g in layout.get("notes", [])
                         if g.get("pitch")==first_pitch)
        raise ValueError(
            f"Generated lesson engraving omitted {len(missing)} required note(s) "
            f"(MIDI pitch@beat: {example}; engraved pitch {first_pitch} "
            f"appears at beats {available[:24]}, total mapped glyphs "
            f"{len(layout.get('notes', []))}). This lesson cannot be scored accurately.")
