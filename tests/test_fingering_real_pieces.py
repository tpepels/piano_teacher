"""Complete real MIDI inference and every source-subset learning variant.

These deliberately use the installed production provider and original files.
No expensive notation corpus capture is performed.
"""
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import time

import pytest

from piano_teacher.fingering import FingeringService, LumikeyProvider, project_model
from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan

ROOT = Path(__file__).resolve().parents[1]
PIECES = [
    'Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi',
    'Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi',
    'Peace_Piece_-_Bill_Evans_(Piano_Solo).midi',
]


@pytest.mark.parametrize('name', PIECES)
def test_complete_real_piece_and_all_lesson_variants(name, tmp_path):
    path = ROOT/'midi'/name
    piece,_ = import_piece(path)
    signature = sha256(path.read_bytes()).hexdigest()
    started = time.monotonic()
    plan = FingeringService(tmp_path).prepare(piece,signature)
    elapsed = time.monotonic()-started
    print(f'\n{name}: {len(piece.notes)} original notes, {plan.summary()}, {elapsed:.2f}s')
    assert plan.status in ('ready','partial'), plan.error
    assert len(plan.assignments)==len(piece.notes)
    # This export assigns six to ten concurrent distinct keys to its RH
    # track. Rejecting impossible fingers is required, not an inference error.
    overfull=any(len({q.pitch for q in piece.notes if q.hand==n.hand
                      and q.start<=n.start+1e-7 and q.end>n.start+1e-7})>5
                 for n in piece.notes) if 'Evans' in name else False
    if overfull:
        assert plan.status=='partial'
        assert plan.summary()['assigned']>0
        assert all(a.reason for a in plan.assignments.values() if a.finger is None)
    else:
        assert plan.summary()['assigned']==len(piece.notes)
    assert {a.hand for a in plan.assignments.values()}=={'left','right'}
    # All distinct held keys must have distinct known automatic fingers.
    for hand in ('left','right'):
        held=[]
        for n in sorted((n for n in piece.notes if n.hand==hand),key=lambda n:(n.start,n.pitch)):
            held=[old for old in held if old.end>n.start+1e-7]
            a=plan.assignments[n.source_id]
            if a.finger is not None:
                assert all(old.pitch==n.pitch or plan.assignments[old.source_id].finger!=a.finger for old in held)
                held.append(n)
    # A fresh process/service with deliberately unavailable Node must reuse
    # the original plan, proving restart and absence of hidden reinference.
    cached=FingeringService(tmp_path,provider=LumikeyProvider(node='/unavailable/node')).prepare(piece,signature)
    assert cached==plan
    learning=LearningPlan(replace(piece,fingering_plan=plan))
    covered=set()
    stages=0
    for ex in learning.exercises:
        for hand in ('right','left','both'):
            for variant in learning._stage_variants(ex,hand):
                events=[{'source_id':n.source_id,'is_attack':True} for n in variant.notes]
                projected=project_model({'notation_events':events},plan)
                for event in projected['notation_events']:
                    sid=event['source_id']
                    covered.add(sid)
                    finger=plan.assignments[sid].finger
                    assert event.get('fingering',{}).get('finger')==finger
                stages+=1
    assert covered==set(plan.assignments)
    print(f'{stages} hand/variant projections, all {len(covered)} original source identities covered')
