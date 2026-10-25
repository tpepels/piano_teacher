"""Exercise the installed production model, not a substitute test provider."""
from dataclasses import replace
import json

import pytest

from piano_teacher.music import Note, Piece
from piano_teacher.fingering import FingeringService, LumikeyProvider, project_model


def piece(notes):
    return Piece('Fingering regression', 120, tuple(notes), ())


def test_real_models_both_hands_and_playable_chords():
    source = piece([Note(0, 1, p, i//3, 0, hand='left' if i<3 else 'right',
                         source_id=f'n{i}') for i,p in enumerate((48,52,55,60,64,67))])
    result = LumikeyProvider().predict(source, {})
    assert set(result) == {f'n{i}' for i in range(6)}
    assert all(1 <= a.finger <= 5 for a in result.values())
    assert len({result[f'n{i}'].finger for i in range(3)}) == 3
    assert len({result[f'n{i}'].finger for i in range(3,6)}) == 3
    assert result['n0'].finger > result['n1'].finger > result['n2'].finger
    assert result['n3'].finger < result['n4'].finger < result['n5'].finger


def test_fixed_lookahead_and_overlap_do_not_reuse_held_finger():
    source = piece([Note(0,2,60,0,0,source_id='held'),
                    Note(1,2,64,0,0,source_id='fixed'),
                    Note(1,2,67,0,0,source_id='chord')])
    result = LumikeyProvider().predict(source, {'fixed':3})
    assert result['fixed'].finger == 3
    assert result['held'].finger != 3
    assert len({a.finger for a in result.values()}) == 3


@pytest.mark.parametrize('hand', ['right','left'])
def test_chord_reserves_available_slots_around_a_held_finger(hand):
    source=piece([Note(0,2,84,0,0,hand=hand,source_id='held'),
                  *(Note(1,2,p,0,0,hand=hand,source_id=str(p)) for p in (60,64,67,70))])
    result=LumikeyProvider().predict(source,{'held':3})
    assert all(p.finger is not None for p in result.values())
    assert len({p.finger for p in result.values()})==5
    chord=[result[str(p)].finger for p in (60,64,67,70)]
    assert chord==sorted(chord,reverse=hand=='left')


def test_model_choice_cannot_strand_later_chord_tones():
    # A retained Peace Piece voicing: the imported RH track includes this
    # wide register. This checks finger capacity, not an assumed hand span.
    source=piece([Note(0,1.54167,71,0,0,source_id='held'),
                  *(Note(.5,2.5,p,0,0,source_id=str(p)) for p in (36,60,64,67))])
    result=LumikeyProvider().predict(source,{'held':5})
    assert [result[str(p)].finger for p in (36,60,64,67)]==[1,2,3,4]


def test_impossible_chord_is_unknown_not_fabricated():
    source = piece([Note(0,1,60+i,0,0,source_id=str(i)) for i in range(6)])
    result = LumikeyProvider().predict(source, {})
    assert all(a.finger is None and a.reason for a in result.values())


def test_equal_pitch_distinct_source_voices_remain_distinct():
    source = piece([Note(0,2,60,0,0,source_id='v1',voice='1'),
                    Note(0,1,60,0,0,source_id='v2',voice='2'),
                    Note(1,2,60,0,0,source_id='repeat')])
    result = LumikeyProvider().predict(source, {})
    assert set(result) == {'v1','v2','repeat'}
    assert all(a.finger is not None for a in result.values())


@pytest.mark.parametrize('reverse', [False, True])
def test_fixed_shared_key_is_independent_of_source_order(reverse):
    unisons=[Note(0,2,60,0,0,source_id='auto'),Note(0,1,60,0,0,source_id='fixed')]
    source=piece([*(reversed(unisons) if reverse else unisons),
                  Note(0,1,64,0,0,source_id='e'),Note(0,1,67,0,0,source_id='g')])
    result=LumikeyProvider().predict(source,{'fixed':3})
    assert result['auto'].finger==result['fixed'].finger==3
    assert not result['fixed'].reason


def test_persistence_priority_projection_and_no_reinference(tmp_path):
    source = replace(piece([Note(0,2,60,0,0,source_id='xml-p0-m0-e1'),
                            Note(1,2,64,0,0,source_id='xml-p0-m0-e2')]),
                     source_musicxml='''<score-partwise><part><measure><attributes/>
                       <note><pitch><step>C</step><octave>4</octave></pitch><notations><technical><fingering>2</fingering></technical></notations></note>
                       <note><pitch><step>E</step><octave>4</octave></pitch></note></measure></part></score-partwise>''')
    service = FingeringService(tmp_path)
    plan = service.prepare(source, 'abc')
    assert plan.assignments['xml-p0-m0-e1'].finger == 2
    assert plan.assignments['xml-p0-m0-e1'].origin == 'authored'
    plan = service.correct(source,'abc','xml-p0-m0-e1',4)
    assert plan.assignments['xml-p0-m0-e1'].finger == 4
    assert plan.assignments['xml-p0-m0-e1'].authored == 2
    assert plan.assignments['xml-p0-m0-e1'].manual == 4
    restarted = FingeringService(tmp_path, provider=LumikeyProvider(node='/missing/node'))
    assert restarted.prepare(source,'abc') == plan  # actual cache, missing runtime cannot infer
    model={'notation_events':[{'source_id':'xml-p0-m0-e1','is_attack':True},
                              {'source_id':'xml-p0-m0-e1','is_attack':False}]}
    projected=project_model(model,plan)
    assert projected['notation_events'][0]['fingering']['finger']==4
    assert 'fingering' not in projected['notation_events'][1]
    assert 'fingering' not in model['notation_events'][0]
    cleared=service.correct(source,'abc','xml-p0-m0-e1',None)
    assert cleared.assignments['xml-p0-m0-e1'].finger==2


def test_runtime_failure_never_fabricates(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    plan=FingeringService(tmp_path,provider=LumikeyProvider(node='/missing/node')).prepare(source,'broken')
    assert plan.status == 'unavailable'
    assert plan.assignments['n'].finger is None
    assert plan.summary()['error']
    # A transient failure must not poison the durable successful cache.
    recovered=FingeringService(tmp_path).prepare(source,'broken')
    assert recovered.assignments['n'].finger in range(1,6)


def test_bad_correction_and_changed_source_do_not_reuse_stale_plan(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    service=FingeringService(tmp_path)
    plan=service.prepare(source,'one')
    for value in (0,6,True,'3'):
        with pytest.raises(ValueError): service.correct(source,'one','n',value)
    with pytest.raises(ValueError): service.correct(source,'one','unknown',2)
    changed=replace(source,notes=(replace(source.notes[0],pitch=62),))
    other=service.prepare(changed,'two')
    assert other.source_fingerprint=='two'
    assert other.config != plan.config  # exact original notes/BPM form the input digest


def test_corrupted_store_recovers_and_preserves_overrides(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    service=FingeringService(tmp_path)
    service.correct(source,'one','n',4)
    for path in tmp_path.glob('*/plan-*.json'): path.write_text('{broken')
    plan=service.prepare(source,'one')
    assert plan.assignments['n'].finger==4
    assert plan.assignments['n'].origin=='manual'


def test_ambiguous_authored_substitution_is_preserved_not_guessed(tmp_path):
    source=replace(piece([Note(0,1,60,0,0,source_id='xml-p0-m0-e0')]),
        source_musicxml='<score-partwise><part><measure><note><pitch><step>C</step><octave>4</octave></pitch><notations><technical>'
                        '<fingering substitution="yes">2</fingering>'
                        '</technical></notations></note></measure></part></score-partwise>')
    service=FingeringService(tmp_path)
    a=service.prepare(source,'xml').assignments['xml-p0-m0-e0']
    assert a.finger is None
    assert a.authored_text==('2 [substitution]',)
    assert service.correct(source,'xml',a.source_id,3).assignments[a.source_id].finger==3


def test_conflicting_fixed_fingers_remain_authoritative_and_reported(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='a'),Note(0,1,64,0,0,source_id='b')])
    provider=LumikeyProvider()
    result=provider.predict(source,{'a':2,'b':2})
    assert result['a'].finger==result['b'].finger==2
    assert result['a'].reason and result['b'].reason


def test_wrong_json_type_in_derived_cache_is_a_cache_miss(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    service=FingeringService(tmp_path)
    expected=service.prepare(source,'one')
    for path in tmp_path.glob('*/plan-*.json'): path.write_text('[]')
    assert service.prepare(source,'one')==expected


@pytest.mark.parametrize('corruption', ['manual', 'list', 'null'])
def test_derived_cache_cannot_override_fixed_or_crash_on_nested_corruption(tmp_path,corruption):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    service=FingeringService(tmp_path)
    expected=service.correct(source,'one','n',4)
    path=next(tmp_path.glob('*/plan-*.json'))
    value=json.loads(path.read_text())
    if corruption=='manual': value['assignments']['n']['finger']=1
    else: value['assignments']=[] if corruption=='list' else None
    path.write_text(json.dumps(value))
    assert service.prepare(source,'one')==expected


def test_corrupt_plan_with_missing_runtime_keeps_durable_manual_finger(tmp_path):
    source=piece([Note(0,1,60,0,0,source_id='n')])
    FingeringService(tmp_path).correct(source,'one','n',4)
    path=next(tmp_path.glob('*/plan-*.json'))
    value=json.loads(path.read_text())
    value['assignments']['n']['finger']=1
    path.write_text(json.dumps(value))
    plan=FingeringService(tmp_path,provider=LumikeyProvider(node='/missing/node')).prepare(source,'one')
    assert plan.status=='unavailable'
    assert plan.assignments['n'].finger==4


def test_primary_authored_finger_remains_fixed_with_retained_substitution(tmp_path):
    source=replace(piece([Note(0,1,60,0,0,source_id='xml-p0-m0-e0')]),
        source_musicxml='<score-partwise><part><measure><note><pitch><step>C</step><octave>4</octave></pitch>'
        '<notations><technical><fingering>1</fingering><fingering substitution="yes">3</fingering>'
        '</technical></notations></note></measure></part></score-partwise>')
    plan=FingeringService(tmp_path).prepare(source,'substitution')
    a=plan.assignments['xml-p0-m0-e0']
    assert a.finger==a.authored==1
    assert a.authored_text==('1','3 [substitution]')
    assert plan.summary()['review']==1 and a.reason
