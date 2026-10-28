"""Bounded source-directed registration and actual head-pixel ownership.

Glyphs are supplied from the independent reference font; current PNG ink and
staff rails establish geometry. Source-declared chords and compatible unisons
keep their existing separate policies. No proof coordinator or native asset
module participates in registration.
"""
import math
import re

from .pixel_context import clef_at, ledger_context_rows
from .pixel_proof import expected_y
from .raster_matching import _joint_candidates, glyph_search_components, match_glyphs_joint

HEAD_MINIMUM = .79
PITCH_TOLERANCE_STEPS = .42


def source_chord_groups(notes):
    """Only actual source <chord/> declarations permit common feature ink."""
    groups, previous = [], None
    for note in notes:
        key = (note['part_index'], note['index'], note['staff'], note['voice'], note['beat'])
        if note['chord'] and previous == key:
            groups[-1].append(note)
        else:
            groups.append([note])
        previous = key
    return groups


def _shared_unison_directions(notes):
    """Only compatible independent unison leaders may own one common head.

    Explicit source stems remain authoritative; otherwise the first source
    voice is conventionally up and the second down. No renderer metadata is
    involved, and same-direction or differently written heads cannot share.
    """
    if len(notes)!=2 or any(n['chord'] for n in notes) or notes[0]['voice']==notes[1]['voice']:
        return {}
    fields=('part_index','index','staff','beat','spelling','note_type','dots','duration')
    if any(notes[0][key]!=notes[1][key] for key in fields):
        return {}
    ordered=sorted(notes,key=lambda n:tuple(int(p) if p.isdigit() else p
                   for p in re.split(r'(\d+)',n['voice'])))
    if any(n.get('beams') and not n.get('stem') for n in ordered):
        return {}
    directions={n['source']['id']:n.get('stem') or ('up' if i==0 else 'down')
                for i,n in enumerate(ordered)}
    return directions if set(directions.values())=={'up','down'} else {}


def register_noteheads(pixels, staves, written, notes, glyphs, *, occlusion_columns=()):
    requests, heads, errors = [], {}, {}
    displaced=set()
    for group in source_chord_groups(notes):
        if len(group)>1:
            staff=staves[group[0]['staff']]
            ys=[expected_y(staff,n['spelling'],clef_at(written,n['index'],n['staff'])) for n in group]
            if any(0<abs(a-b)<=1.05*staff.gap for i,a in enumerate(ys) for b in ys[:i]):
                displaced.update(n['source']['id'] for n in group)
    for i,note in enumerate(notes):
        staff=staves.get(note['staff'])
        if staff is None:
            continue
        for other in notes[:i]:
            if (note['part_index'],note['staff'],note['beat'])!=(other['part_index'],other['staff'],other['beat']) or note['voice']==other['voice']:
                continue
            clef=clef_at(written,note['index'],note['staff'])
            if abs(expected_y(staff,note['spelling'],clef)-expected_y(staff,other['spelling'],clef))<=.51*staff.gap:
                # Source polyphony bounds the search, while current-image
                # family, pitch and exclusive pixel ownership still prove it.
                for group in source_chord_groups(notes):
                    if any(n is note or n is other for n in group):
                        displaced.update(n['source']['id'] for n in group)
    ledgers={staff:ledger_context_rows(pixels,rail,written,
        [n for n in notes if n['staff']==staff]) for staff,rail in staves.items()}
    for note in notes:
        sid = note['source']['id']
        try:
            staff = staves[note['staff']]
            y = expected_y(staff, note['spelling'],
                          clef_at(written, note['index'], note['staff']))
            name = ('head_whole' if note['note_type'] == 'whole' else
                    'head_half' if note['note_type'] == 'half' else 'head_black')
            r = math.floor(PITCH_TOLERANCE_STEPS * staff.gap / 2)
            horizontal=math.ceil(1.5*staff.gap) if sid in displaced else 3
            requests.append(dict(note=note, glyph=glyphs[name], gap=staff.gap,
                                 origin_y=y, dxs=range(-horizontal,horizontal+1), dys=range(-r, r+1),
                                 alternatives=tuple((kind,glyphs[kind]) for kind in ('head_black','head_half','head_whole') if kind!=name),
                                 occlusion_columns=occlusion_columns,
                                 background_rows=ledgers[note['staff']] if name!='head_black' else ()))
        except (KeyError, ValueError, AssertionError, TypeError) as exc:
            errors[sid] = str(exc)
    origin = round(pixels.shape[1] * .42)
    for indices in glyph_search_components(requests, dys=range(0, 1)):
        group = [requests[i] for i in indices]
        registration = {}
        shared = {}
        if len(group) == 1:
            candidates = _joint_candidates(pixels, group[0], origin, range(0, 1), HEAD_MINIMUM)
            assigned = candidates[:1] or None
        else:
            assigned = match_glyphs_joint(pixels, group, origin, dys=range(0, 1),
                                         minimum=HEAD_MINIMUM, diagnostics=registration)
            if assigned is None and not registration.get('exhausted'):
                shared=_shared_unison_directions([r['note'] for r in group])
                if shared:
                    # A legitimate common head must itself register at the
                    # source clock. An erased displaced head cannot borrow a
                    # surviving off-centre contour through this fallback.
                    common=dict(group[0],dxs=range(-3,4))
                    candidates=_joint_candidates(pixels,common,origin,range(0,1),HEAD_MINIMUM)
                    if candidates:
                        assigned=[candidates[0]]*len(group)
        for i, request in enumerate(group):
            sid = request['note']['source']['id']
            if assigned is None:
                errors[sid] = ('Current-image notehead registration resource limit exhausted; no ownership verified'
                    if registration.get('exhausted') else
                    'Current-image notehead lacks a unique bounded .79 contour assignment')
                continue
            row = assigned[i]
            b, gap = request['glyph']['bounds'], request['gap']
            width, height = max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250))
            heads[sid] = dict(x=row['x'] + b[2]*gap/500,
                              y=row['y'] - b[1]*gap/250,
                              bbox=[row['x'], row['y'], row['x']+width, row['y']+height],
                              score=row['score'], support=row['support'], gap=gap)
            if shared:
                heads[sid].update(shared_source_ids=sorted(shared),shared_stem_direction=shared[sid])
    return heads, errors
