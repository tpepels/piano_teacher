"""Bound source flag, absent-flag, accidental, and augmentation-dot ink.

Source groups constrain ownership; current registered heads and shafts supply
positions. Temporary contour support stays in the caller's per-frame session.
"""
from copy import deepcopy
from functools import lru_cache
import math

import numpy as np

from .feature_contract import ACCIDENTALS, FLAG_COUNTS, GLYPH_MINIMUM, feature_result
from .glyph_evidence import measure_glyph_family
from .head_registration import HEAD_MINIMUM
from .pixel_context import clef_at
from .pixel_ink import rasterize_outline
from .pixel_proof import expected_y
from .raster_matching import match_glyph, _joint_candidates
from .reference_font import feature_glyphs


@lru_cache(maxsize=128)
def flag_origin_offset(name: str, gap: float) -> float:
    """Recover the attachment origin when flag ink prolongs the stem column.

    Downward 32nd and shorter Leipzig flags continue below their SMuFL
    origin. The bottom of visible continuous ink is therefore not the flag
    attachment. Read that continuation from the independent external mask.
    """
    glyph = feature_glyphs()[name]
    b = glyph['bounds']
    mask = rasterize_outline(glyph['svg'], max(1, round(b[2]*gap/250)), max(1, round(b[3]*gap/250)))
    origin_x = round(-b[0]*gap/250)
    ys = np.nonzero(mask[:, max(0, origin_x-1):min(mask.shape[1], origin_x+2)])[0]
    if not len(ys):
        return 0.
    top, bottom = float(ys.min())+b[1]*gap/250, float(ys.max())+b[1]*gap/250
    return -min(0., top) if '_up_' in name else -max(0., bottom)


def measure_flag_absence(pixels, glyphs, heads, stem, associated_dots=None):
    """A quarter needs a visible, empty flag attachment, not a missing match.

    Read the attachment from the measured stem. Inspect both external flag
    families at that endpoint and require clear ink beside the stem, toward
    the outermost head of the source-declared common stem group. The entire
    chord has one attachment, not a separate search past each inner head.
    Unclassified/neighboring ink or clipping cannot prove absence.
    This is bounded attachment evidence, not a global extra-symbol check.
    """
    if stem['status'] != 'verified' or not heads or any(h is None for h in heads):
        return feature_result('unverified', 'Flag absence requires the independently registered head and stem')
    s, gap = stem['evidence'], heads[0]['gap']
    if len(heads) != len(s['shared_source_ids']) or any(abs(h['gap']-gap) > 1e-6 for h in heads):
        return feature_result('unverified', 'Every source common-stem head must have the same measured scale')
    boxes = [h['bbox'] for h in heads]
    head_box = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes)]
    names = tuple(f'flag_{d}_{c}' for d in ('up', 'down') for c in range(1, 6))
    if any(name not in glyphs for name in names):
        return feature_result('unsupported', 'External flag family is incomplete')
    scores = {name: match_glyph(pixels, glyphs[name], gap,
                  s['x']+(glyphs[name]['bounds'][0]+glyphs[name]['bounds'][2]/2)*gap/250,
                  s['tip_y']+flag_origin_offset(name, gap), centered=True,
                  dxs=range(-2, 3), dys=range(-2, 3)) for name in names}
    # Both Leipzig flag directions put their off-shaft contour to the right
    # of the SMuFL origin. Stem direction changes the vertical range only.
    left, right = s['bbox'][2]+1, math.ceil(s['x']+1.6*gap)
    if s['direction'] == 'up':
        top, bottom = s['tip_y']-2, min(math.ceil(s['tip_y']+2.5*gap), head_box[1]-1)
    else:
        top, bottom = max(math.floor(s['tip_y']-2.5*gap), head_box[3]+1), s['tip_y']+3
    evidence = dict(expected_count=0, direction=s['direction'], stem_bbox=s['bbox'],
                    group_id=s['group_id'], shared_source_ids=s['shared_source_ids'],
                    head_bbox=head_box, head_bboxes=boxes, staff_gap=gap,
                    frame_size=[pixels.shape[1], pixels.shape[0]],
                    bbox=[left, top, right, bottom], family_scores=scores,
                    glyph_minimum=GLYPH_MINIMUM)
    if not (0 <= left < right <= pixels.shape[1] and 0 <= top < bottom <= pixels.shape[0]):
        return feature_result('unverified', 'Quarter flag attachment is clipped or inseparable from its head', **evidence)
    remaining=pixels[top:bottom,left:right].copy()
    raw=int(remaining.sum())
    associated=[]
    for sid,dots in (associated_dots or {}).items():
        if dots.get('status')!='verified' or not dots.get('_support'):
            continue
        changed=0
        for pixel in dots['_support']:
            y,x=divmod(pixel,pixels.shape[1])
            if top<=y<bottom and left<=x<right and remaining[y-top,x-left]:
                remaining[y-top,x-left]=False
                changed+=1
        if changed:
            associated.append(dict(source_id=sid,measurement=deepcopy(dots['evidence']),excluded_pixels=changed))
    ink=int(remaining.sum())
    evidence.update(bright_pixels=ink,raw_bright_pixels=raw,associated_dots=associated,
                    sampled_pixels=(right-left)*(bottom-top))
    if max(scores.values()) >= GLYPH_MINIMUM:
        return feature_result('mismatch', 'Quarter has an external-font flag contour at its measured stem endpoint', **evidence)
    if ink:
        return feature_result('unverified', 'Ink beside the quarter stem prevents independent flag absence', **evidence)
    return feature_result('verified', 'Visible quarter attachment is empty and every external flag contour is below threshold', **evidence)


def measure_accidental(pixels,glyphs,head,required,group_heads,context):
    """A source accidental precedes its chord and stays at its head's Y.

    Chord columns can spread freely to the left. A confidently identified
    intervening head prevents borrowing an earlier note's accidental.
    """
    gap=head['gap']
    leftmost=min(h['bbox'][0] for h in group_heads)
    width=glyphs[ACCIDENTALS[required]]['bounds'][2]*gap/250
    origin=head['x']-1.15*gap
    left=leftmost-max(4.,len(group_heads)+1.)*gap
    right=leftmost-.12*gap
    radius=max(1,math.floor(.12*gap))
    part=measure_glyph_family(pixels,glyphs,tuple(dict.fromkeys(ACCIDENTALS.values())),ACCIDENTALS[required],
        gap,origin,head['y'],range(math.ceil(left+width/2-origin),math.floor(right-width/2-origin)+1),
        range(-radius,radius+1),detached=True)
    if part['status']!='verified':
        return part
    box=part['evidence']['bbox']
    competing=[]
    for name in ('head_black','head_half','head_whole'):
        b=glyphs[name]['bounds']
        half=b[2]*gap/500
        dxs=range(math.ceil(box[2]+half-head['x']),math.floor(leftmost-half-head['x'])+1)
        if not dxs:
            continue
        request=dict(glyph=glyphs[name],gap=gap,origin_y=head['y'],dxs=dxs,dys=range(-1,2),
            alternatives=tuple((kind,glyphs[kind]) for kind in ('head_black','head_half','head_whole') if kind!=name),
            background_rows=context if name!='head_black' else ())
        candidates=_joint_candidates(pixels,request,head['x'],range(-1,2),HEAD_MINIMUM)
        if candidates:
            row=candidates[0]
            competing.append(dict(glyph=name,score=round(row['score'],4),bbox=[row['x'],row['y'],
                row['x']+round(b[2]*gap/250),row['y']+round(b[3]*gap/250)]))
    if competing:
        return feature_result('ambiguous','Another measured head lies between this accidental and its source chord',
                       **part['evidence'],competing_heads=competing)
    part['evidence'].update(head_bbox=head['bbox'],staff_gap=gap,
        clearance_spaces=(leftmost-box[2])/gap,vertical_tolerance_spaces=.12)
    return part


def measure_dot(pixels, glyphs, head, count):
    if count > 2:
        return feature_result('unsupported', 'More than two augmentation dots needs a separate bounded assignment', expected_count=count)
    gap, used, dots = head['gap'], set(), []
    for i in range(count):
        result = measure_glyph_family(pixels, glyphs, ('augmentation_dot',), 'augmentation_dot', gap,
                         head['x']+(1.15+i*.65)*gap, head['y']-.24*gap,
                         range(-6, 7), range(-5, 6), detached=True)
        if result['status'] != 'verified':
            return feature_result(result['status'], result['reason'], expected_count=count,
                           identified_dots=dots, candidate=result['evidence'])
        support = result.pop('_support')
        if used.intersection(support):
            return feature_result('ambiguous', 'Two source dots cannot reuse the same connected ink', expected_count=count)
        used.update(support)
        dots.append(result['evidence'])
    boxes = [r['bbox'] for r in dots]
    result = feature_result('verified', 'Every source dot has a separate isolated external-font contour',
                     expected_count=count, dots=dots,
                     bbox=[min(b[0] for b in boxes), min(b[1] for b in boxes),
                           max(b[2] for b in boxes), max(b[3] for b in boxes)])
    result['_support'] = frozenset(used)
    return result


def measure_chord_dots(pixels, glyphs, group, heads, rail, written):
    """Assign isolated dots to source chord tones in actual staff spaces.

    A displaced tone may share a column to the right of the full chord.
    Space tones retain their own space; line tones use an adjacent free
    space. A neighboring tone's dot cannot stand in for a missing one.
    """
    dotted=[n for n in group if n['dots']]
    output={}
    if any(n['source']['id'] not in heads for n in group):
        return {n['source']['id']:feature_result('unverified','All source chord heads must register before dot ownership') for n in dotted}
    gap=rail.gap
    positions={n['source']['id']:round((rail.bottom-expected_y(rail,n['spelling'],
        clef_at(written,n['index'],n['staff'])))*2/gap) for n in dotted}
    reserved={s for s in positions.values() if s%2}
    rightmost=max(heads[n['source']['id']]['x'] for n in group)
    choices={}
    for note in dotted:
        sid=note['source']['id']
        if note['dots']>4:
            output[sid]=feature_result('unsupported','More than four source dots needs another bounded assignment')
            continue
        head=heads[sid]
        step=positions[sid]
        targets=[step] if step%2 else [s for s in (step+1,step-1) if s not in reserved]
        if not targets:
            output[sid]=feature_result('unsupported','Dense chord dot lanes need an independent extended-space assignment')
            continue
        for index in range(note['dots']):
            options=[]
            for target in targets:
                part=measure_glyph_family(pixels,glyphs,('augmentation_dot',),'augmentation_dot',gap,
                    head['x']+(1.15+index*.65)*gap,rail.bottom-target*gap/2,
                    range(-round(.35*gap),round(rightmost-head['x']+.35*gap)+1),
                    range(-round(.28*gap),round(.28*gap)+1),detached=True)
                if part['status']=='verified' and not any(part['_support']==p['_support'] for p in options):
                    options.append(part)
            choices[sid,index]=options
    pending=[key for key,options in choices.items() if options]
    pending.sort(key=lambda key:len(choices[key]))
    visits=0
    def assign(index,used,found):
        nonlocal visits
        visits+=1
        if visits>10000:
            return None
        if index==len(pending):
            return found
        key=pending[index]
        for candidate in choices[key]:
            support=candidate['_support']
            if not used.intersection(support):
                result=assign(index+1,used|support,found | {key:candidate})
                if result is not None:
                    return result
        return None
    selected=assign(0,set(),{})
    for note in dotted:
        sid=note['source']['id']
        if sid in output:
            continue
        if selected is None or any((sid,i) not in selected for i in range(note['dots'])):
            output[sid]=feature_result('unverified','Every chord dot needs distinct isolated ink at its source staff space',expected_count=note['dots'])
            continue
        parts=[selected[sid,i] for i in range(note['dots'])]
        dots=[p['evidence'] for p in parts]
        boxes=[d['bbox'] for d in dots]
        output[sid]=feature_result('verified','Distinct external-font dots occupy source-compatible chord spaces',
            expected_count=note['dots'],dots=dots,
            bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)])
        output[sid]['_support']=frozenset().union(*(p['_support'] for p in parts))
    return output


def measure_flag(pixels, glyphs, head, stem, note_type):
    """Measure the full flag family at the independently attached stem tip."""
    s = stem['evidence']
    name = f"flag_{s['direction']}_{FLAG_COUNTS[note_type]}"
    return measure_glyph_family(pixels, glyphs,
        tuple(f'flag_{d}_{c}' for d in ('up', 'down') for c in range(1, 6)),
        name, head['gap'], s['x'], s['tip_y'],
        range(-2, 3), range(-2, 3), centered=False,
        y_offsets={f'flag_{d}_{c}': flag_origin_offset(f'flag_{d}_{c}', head['gap'])
                   for d in ('up', 'down') for c in range(1, 6)})
