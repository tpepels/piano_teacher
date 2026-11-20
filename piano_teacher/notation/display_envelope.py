"""Authentic display context around a selected performance window.

The envelope changes ink coverage only. Its origin is translated back to the
active phrase once, while the active grid and physical source identities stay
unchanged. Simplified exercises never acquire original notes as hidden work.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from bisect import bisect_left, bisect_right

from ..music import Phrase, Piece, source_note_id
from .practice_timeline import practice_timeline_descriptor


@dataclass(frozen=True)
class DisplayEnvelope:
    phrase: Phrase
    active: Phrase
    active_ids: frozenset[str]
    display_start: float | None = None

    @property
    def display_offset(self) -> float:
        start = self.phrase.start if self.display_start is None else self.display_start
        return start-self.active.start

    @property
    def offset(self) -> float:
        return self.phrase.start - self.active.start


def display_envelope(piece: Piece, active: Phrase, *, transformed: bool) -> DisplayEnvelope:
    active_ids = frozenset(source_note_id(note, i) for i, note in enumerate(active.notes))
    original = {note.source_id: note for note in piece.notes if note.source_id}
    authentic = (not transformed and all(note.source_id and
        original.get(note.source_id) == note for note in active.notes))
    grid = piece.bar_boundaries
    if not authentic or len(grid) < 2:
        if active.sounding_end <= active.end:
            return DisplayEnvelope(active, active, active_ids)
        # An announced transformation keeps only its own notes. Extending
        # notation for a selected release does not introduce original work.
        if grid:
            last = bisect_left(grid, active.sounding_end)
            if last >= len(grid):
                raise ValueError('Selected release exceeds the authored source grid')
            end = grid[last]
        else:
            length = (active.end-active.start)/(active.last_bar-active.first_bar+1)
            extra = int((active.sounding_end-active.end)/length)+1
            last = active.last_bar+extra
            end = active.end+extra*length
        phrase = Phrase(active.number, active.first_bar, last, active.start, end, active.notes)
        return DisplayEnvelope(phrase, active, active_ids)
    first = max(0, active.first_bar - 2)
    display_start = grid[first]
    carry_ins = [note for note in piece.notes
                 if note.start < display_start and note.end > display_start]
    if carry_ins:
        first = max(0, bisect_right(grid, min(note.start for note in carry_ins))-1)
    last = min(len(grid)-1, active.last_bar + 1)
    # A selected attack owns its release even beyond its authored last bar.
    last = max(last, min(len(grid)-1, bisect_left(grid, active.sounding_end)))
    notes = tuple(note for note in piece.notes
                  if grid[first] <= note.start < grid[last])
    phrase = Phrase(active.number, first+1, last, grid[first], grid[last], notes)
    return DisplayEnvelope(phrase, active, active_ids, display_start)


def project_display_model(model: dict, envelope: DisplayEnvelope, hand: str) -> dict:
    """Translate one complete notation model; retain a strict active selection."""
    model = deepcopy(model)
    shift = envelope.offset
    active = envelope.active
    duration = round(active.end-active.start, 8)
    sounding = round(active.sounding_end-active.start, 8)
    for measure in model['measures']:
        for key in ('start_beat', 'end_beat'):
            measure[key] = round(measure[key]+shift, 8)
    display_measures = [measure for measure in model['measures']
                        if measure['end_beat'] > envelope.display_offset+.000001]
    for measure in display_measures:
        measure['display_role'] = ('active' if active.first_bar <= measure['number'] <= active.last_bar else 'context')
    for note in model['notes']:
        note['onset_beats'] = round(note['onset_beats']+shift, 8)
    display_notes = [note for note in model['notes']
                     if note['onset_beats']+note['duration_beats'] > envelope.display_offset+.000001]
    performance_ids = {note['id'] for note in display_notes
        if note['id'] in envelope.active_ids and (hand == 'both' or note['hand'] == hand)}
    for collection in ('notation_events', 'expressions', 'grace_notes'):
        visible_events = []
        for event in model.get(collection, ()):
            for key in ('beat', 'start_beat', 'end_beat'):
                if key in event:
                    event[key] = round(event[key]+shift, 8)
            if event.get('beat', envelope.display_offset) < envelope.display_offset-.000001:
                continue
            visible_events.append(event)
            source = event.get('source_id')
            inside = (active.first_bar <= event['measure'] <= active.last_bar
                      if 'measure' in event else 0 <= event.get('beat', -1) < duration)
            event['display_role'] = ('active' if source in performance_ids else
                'inactive_hand' if inside else 'context')
            if source is None and inside:
                event['display_role'] = ('active' if hand == 'both' or
                    event.get('hand', event.get('staff')) == hand else 'inactive_hand')
        model[collection] = visible_events
    measures = [m for m in display_measures
                if active.first_bar <= m['number'] <= active.last_bar]
    if not measures or abs(measures[0]['start_beat']) > .0001 or abs(measures[-1]['end_beat']-duration) > .0001:
        raise ValueError('Display envelope lost the active authored measure grid')
    model.update(first_bar=active.first_bar, last_bar=active.last_bar,
        duration_beats=duration, authored_duration_beats=duration,
        sounding_duration_beats=sounding, active_hand=hand,
        active_note_ids=sorted(performance_ids), measures=measures,
        notes=[note for note in display_notes if note['id'] in envelope.active_ids],
        display_notes=display_notes,
        display_measures=display_measures,
        display_extent={'start_beat': round(envelope.display_offset, 8),
                        'end_beat': max(sounding, round(envelope.phrase.end-active.start, 8))},
        practice_timeline=practice_timeline_descriptor(measures, duration, ('right', 'left'),
            sounding_duration_beats=sounding))
    return model


def project_performance_layout(layout: dict, envelope: DisplayEnvelope) -> dict:
    """Keep grading's exact selection while native assets retain all page ink."""
    layout = deepcopy(layout)
    if envelope.phrase == envelope.active:
        return layout
    source_beats = {source_note_id(note,i): note.start-envelope.active.start
                    for i,note in enumerate(envelope.active.notes)}
    notes = []
    for glyph in layout.get('notes', ()):
        if glyph.get('source_id') not in envelope.active_ids:
            continue
        if 'beat' in glyph:
            glyph['beat'] += envelope.offset
        glyph['source_beat'] = source_beats[glyph['source_id']]
        notes.append(glyph)
    layout['notes'] = notes
    for key in ('attack_map', 'continuation_map'):
        layout[key] = {source: value for source, value in layout.get(key, {}).items()
                       if source in envelope.active_ids}
    return layout
