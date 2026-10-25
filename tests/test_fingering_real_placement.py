"""Focused actual-source native engraving; never a corpus audit."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image
import pytest

from piano_teacher.fingering import FingeringService, project_model
from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan
from scripts.check_native_verovio_overlay import AuditCase, fixture
from test_native_fingering import _godot, _rgb, _run_godot, _verify_numbers

ROOT=Path(__file__).resolve().parents[1]
HANON='Le_Pianiste_virtuose_-_Première_partie_(1-20)_-_C_L_Hanon.midi'
CHOPIN='Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi'
EVANS='Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
CASES=[('hanon-low',HANON,1,2),('hanon-rise',HANON,7,8),('hanon-fall',HANON,15,16),
       ('chopin-turn',CHOPIN,5,6),('chopin-flourish',CHOPIN,22,22),('evans-chords',EVANS,3,4),
       ('hanon-variant-skeleton',HANON,1,1),('hanon-variant-original',HANON,1,1)]


@pytest.fixture(scope='module')
def originals(tmp_path_factory):
    store=FingeringService(tmp_path_factory.mktemp('placement-plans'))
    result={}
    for name in (HANON,CHOPIN,EVANS):
        path=ROOT/'midi'/name
        piece,_=import_piece(path)
        plan=store.prepare(piece,sha256(path.read_bytes()).hexdigest())
        assert plan.status in ('ready','partial'),plan.error
        result[name]=(piece,plan)
    return result


@pytest.fixture(scope='module',params=CASES,ids=[c[0] for c in CASES])
def real_capture(request,originals,tmp_path_factory):
    label,name,first,last=request.param
    piece,plan=originals[name]
    case=AuditCase(label,str(ROOT/'midi'/name),first,last,'both')
    phrase=None
    if label.startswith('hanon-variant-'):
        learning=LearningPlan(piece)
        level=label.removeprefix('hanon-variant-')
        phrase=next(v.phrase for v in learning._stage_variants(learning.exercises[0],'right') if v.level==level)
    data,_=fixture(case,piece=piece,phrase=phrase)
    data['model']=project_model(data['model'],plan,source_musicxml=piece.source_musicxml)
    expected={e['id']:{'finger':e['fingering']['finger'],'hand':e['fingering']['hand'],
                      'source_id':e['source_id'],'beat':e['beat']}
              for e in data['model']['notation_events'] if 'fingering' in e}
    folder=tmp_path_factory.mktemp(label)
    # Pin before evidence to the previous completed production commit.
    # A shallow CI checkout need not contain this optional historical evidence.
    before=folder/'before-view.gd'
    historical=subprocess.run(['git','show','04da92b:godot/notation/native/view.gd'],cwd=ROOT,capture_output=True)
    if historical.returncode==0:
        before.write_bytes(historical.stdout)
        data['before_script']=str(before)
    payload=folder/'fixture.json';payload.write_text(json.dumps(data))
    (folder/'score.musicxml').write_text(data['xml'])
    command=[*_godot(),'--path',str(ROOT/'godot'),'--rendering-method','gl_compatibility',
        '--audio-driver','Dummy','--script',str(ROOT/'tests/godot/native_fingering_real_placement.gd'),
        '--',str(payload),str(folder)]
    result=_run_godot(command,timeout=90)
    (folder/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'SCRIPT ERROR' not in result.stderr
    return folder,data,expected,json.loads((folder/'report.json').read_text())


def test_real_piece_digits_own_their_source_notes_and_clear_canonical_ink(real_capture):
    folder,data,expected,report=real_capture
    for frame in report['frames']:
        assert not frame['placement_issues'],frame['placement_issues']
        assert frame['labels']
        _verify_numbers(folder,frame,len(frame['labels']))
        seen=set()
        for label in frame['labels']:
            atlas=_rgb(folder,label['reference']);width=atlas.shape[1]//5
            mask=atlas[:,(label['finger']-1)*width:label['finger']*width].max(axis=2)>100
            yy,xx=np.nonzero(mask);x,y,_,_=label['rect']
            center=np.array([np.floor(x)+(xx.min()+xx.max())/2,np.floor(y)+(yy.min()+yy.max())/2])
            delta=center-np.array(label['head'])
            assert np.linalg.norm(delta)<=frame['gap']*2.5,(label,delta)
            assert abs(delta[0])<=frame['gap']*2.1
            for event_id in label['event_ids']:
                assert event_id in expected
                assert label['finger']==expected[event_id]['finger']
                assert label['hand']==expected[event_id]['hand']
                assert event_id not in seen
                assert np.linalg.norm(np.array(label['head'])-np.array(frame['noteheads'][event_id]))<.02
                seen.add(event_id)
        # Every assigned attack whose own head is well inside this viewport
        # must be represented; continuations/unknowns cannot create digits.
        image=_rgb(folder,frame['base'])
        inside={identity for identity,point in frame['noteheads'].items() if identity in expected
                and frame['gap']*3<point[0]<image.shape[1]-frame['gap']*3
                and frame['gap']*3<point[1]<image.shape[0]-frame['gap']*3}
        assert inside<=seen
    a,b=report['frames']
    before={tuple(v['event_ids']):v for v in a['labels']}
    after={tuple(v['event_ids']):v for v in b['labels']}
    for identity in before.keys() & after.keys():
        assert after[identity]['rect'][0]-before[identity]['rect'][0]==pytest.approx(-report['density']*.25,abs=.02)
        assert after[identity]['rect'][1]==before[identity]['rect'][1]
    if folder.name.startswith('hanon-'):
        _verify_source_attachment_from_pixels(folder,data,report)


def _verify_source_attachment_from_pixels(folder,data,report):
    # Source XML pitches/identities, photographed rails, external reference
    # head contours and independently measured motion bind each digit to its
    # note. Renderer head coordinates and density are not inputs to this check.
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_head, _connector_shift
    written=read_written_score(data['xml'])
    notes={n['id']:n for n in written.symbols if n['kind']=='note' and n['visible']}
    pictures=[Image.open(folder/f['base']).convert('RGB') for f in report['frames']]
    motion=_connector_shift(*pictures)
    assert motion is not None
    density=motion['shift']/.25
    for clock,frame,picture in zip((.125,.375),report['frames'],pictures):
        for label in frame['labels']:
            atlas=_rgb(folder,label['reference']);width=atlas.shape[1]//5
            mask=atlas[:,(label['finger']-1)*width:label['finger']*width].max(axis=2)>100
            yy,xx=np.nonzero(mask)
            x,y,_,_=label['rect']
            center=np.array([np.floor(x)+(xx.min()+xx.max())/2,np.floor(y)+(yy.min()+yy.max())/2])
            for identity in label['event_ids']:
                note=notes[identity]
                origin=picture.width*.42+(float(note['beat'])-clock)*density
                head=_connector_head(picture,written,note,origin)
                assert head is not None,(identity,note['spelling'])
                assert np.linalg.norm(center-[head['x'],head['y']])<=head['gap']*2.5


def test_original_and_simplified_annotations_keep_the_same_full_piece_plan(originals,tmp_path_factory):
    piece,plan=originals[HANON]
    learning=LearningPlan(piece)
    ex=learning.exercises[0]
    variants=learning._stage_variants(ex,'right')
    assert {v.level for v in variants}>={'skeleton','original'}
    per_source={}
    for variant in variants:
        data,_=fixture(AuditCase('variant',str(ROOT/'midi'/HANON),ex.phrase.first_bar,ex.phrase.last_bar,'right'),
                       piece=piece,phrase=variant.phrase)
        projected=project_model(data['model'],plan)
        for event in projected['notation_events']:
            if 'fingering' in event:
                sid=event['source_id'];finger=event['fingering']['finger']
                assert per_source.setdefault(sid,finger)==finger==plan.assignments[sid].finger
