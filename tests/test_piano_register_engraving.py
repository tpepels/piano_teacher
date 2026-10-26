"""Display registers never change the source keys, hands or grading voices."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.importing.pieces import import_piece
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model

ROOT=Path(__file__).resolve().parents[1]
PEACE=ROOT/'midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi'
CLEFS={'right':{'sign':'G','line':2,'octave_change':0},
       'left':{'sign':'F','line':4,'octave_change':0}}


@pytest.fixture(scope='module')
def peace():
    return import_piece(PEACE)[0]


def test_raw_midi_ticks_and_generated_voice_partition_keep_every_source_attack(peace):
    import mido
    midi=mido.MidiFile(PEACE)
    assert midi.ticks_per_beat==480
    tick=0;attacks=[]
    for index,message in enumerate(midi.tracks[0]):
        tick+=message.time
        if message.type=='note_on' and message.velocity>0 and tick in (240,1200):
            attacks.append((f'midi-t0-e{index}',tick,message.note,message.channel))
    assert [(tick,pitch,channel) for _,tick,pitch,channel in attacks]==[
        (240,36,1),(240,60,1),(240,64,1),(240,67,1),
        (1200,43,1),(1200,60,1),(1200,62,1),(1200,65,1),(1200,67,1)]
    plan=LearningPlan(peace);plan.select_step(3)
    score=build_lesson_score(plan.active_phrase,boundaries=peace.bar_boundaries,
        time_signatures=peace.time_signatures,default_clefs=infer_piece_clefs(peace.notes))
    model=build_score_model(score,boundaries=peace.bar_boundaries)
    printed={e['source_id']:e for e in model['notation_events']
             if e['kind']=='note' and e['is_attack']}
    source={n['id']:n for n in model['notes']}
    for sid,tick,pitch,channel in attacks:
        assert (printed[sid]['beat'],printed[sid]['midi_pitch'],printed[sid]['hand'])==(
            tick/480,pitch,'right')
        assert (source[sid]['channel'],source[sid]['voice'],source[sid]['hand'])==(
            channel,'midi-t0-c1','right')


@pytest.mark.parametrize('step',(2,3,7,9,10))
def test_real_peace_remote_bass_uses_bass_staff_without_changing_performing_hand(peace,step):
    plan=LearningPlan(peace);plan.select_step(step)
    phrase=plan.active_phrase
    before=deepcopy(phrase)
    score=build_lesson_score(phrase,boundaries=peace.bar_boundaries,
        time_signatures=peace.time_signatures,default_clefs=infer_piece_clefs(peace.notes))
    model=build_score_model(score,boundaries=peace.bar_boundaries,hand=plan.hand)
    assert phrase==before
    sources={n.source_id:n for n in phrase.notes}
    for note in model['notes']:
        source=sources[note['id']]
        assert (note['midi_pitch'],note['hand'],note['voice'],note['track'],note['channel'])==(
            source.pitch,source.hand,source.voice,source.track,source.channel)
        assert note['onset_beats']==pytest.approx(source.start-phrase.start)
        assert note['duration_beats']==pytest.approx(min(source.end,phrase.end)-source.start)
    bass=[e for e in model['notation_events'] if e['kind']=='note'
          and sources[e['source_id']].hand=='right' and e['midi_pitch']<=43]
    assert bass
    assert all(e['staff']=='left' for e in bass), 'Remote RH bass was left in a huge treble-staff chord'
    assert all(e['hand']=='right' for e in bass)
    for event in bass:
        simultaneous=[e for e in model['notation_events'] if e['kind']=='note'
                      and e['beat']==event['beat'] and e['staff']=='right'
                      and sources[e['source_id']].hand=='right']
        assert simultaneous
        assert all(e['hand']=='right' for e in simultaneous)
    assert set(model['active_note_ids'])=={n.source_id for n in phrase.notes
                                         if plan.hand in ('both',n.hand)}


def _synthetic(pitches,hand='right',*,end=2):
    notes=tuple(Note(0,end,p,0,0,hand,f'key-{p}','one-source-voice') for p in pitches)
    phrase=Phrase(1,1,1,0,end,notes)
    score=build_lesson_score(phrase,boundaries=(0,end),time_signatures=((0,4,4),),default_clefs=CLEFS)
    return score,build_score_model(score,boundaries=(0,end))


@pytest.mark.parametrize('pitches',((60,64,67),(48,55,60),(60,61,64),(48,60)))
def test_ordinary_or_ledger_bounded_chords_keep_their_written_staff_and_shared_stem(pitches):
    _,model=_synthetic(pitches)
    events=[e for e in model['notation_events'] if e['kind']=='note']
    assert {e['staff'] for e in events}=={'right'}
    assert len({e['voice'] for e in events})==1
    assert sum(not e['chord'] for e in events)==1


def test_mirrored_remote_high_cluster_uses_treble_but_keeps_left_hand():
    _,model=_synthetic((36,40,43,84),'left')
    events=[e for e in model['notation_events'] if e['kind']=='note']
    high=next(e for e in events if e['midi_pitch']==84)
    assert (high['staff'],high['hand'])==('right','left')
    assert all(e['staff']=='left' for e in events if e['midi_pitch']<60)


def test_register_choice_is_preserved_through_tied_measure_segments():
    notes=tuple(Note(0,8,p,0,0,'right',f'tie-{p}','same-voice') for p in (36,60,64,67))
    phrase=Phrase(1,1,2,0,8,notes)
    score=build_lesson_score(phrase,boundaries=(0,4,8),time_signatures=((0,4,4),),default_clefs=CLEFS)
    model=build_score_model(score,boundaries=(0,4,8))
    low=[e for e in model['notation_events'] if e['source_id']=='tie-36']
    assert len(low)==2 and {e['staff'] for e in low}=={'left'}
    assert sum(e['is_attack'] for e in low)==1
    assert low[0]['tie_start'] and low[1]['tie_stop']
    assert all(e['hand']=='right' for e in low)


def test_mutating_source_hand_in_binding_is_rejected_even_on_a_different_display_staff():
    score,_=_synthetic((36,60,64,67))
    bindings=deepcopy(score.note_bindings)
    low=next(b for b in bindings.values() if b['pitch']==36)
    low['hand']='left'
    corrupted=replace(score,note_bindings=bindings)
    with pytest.raises(ValueError,match='hand|Hand'):
        build_score_model(corrupted,boundaries=(0,2))


def test_full_verovio_preserves_remote_note_source_identity_hand_pitch_and_clock():
    from piano_teacher.score import render_layout
    score,model=_synthetic((36,60,64,67))
    reference=render_layout(score,1,1,'right',total_beats=2,continuous=True)
    low=next(n for n in reference.layout['notes'] if n['source_id']=='key-36')
    assert (low['pitch'],low['hand'],low['source_beat'])==(36,'right',0)
    assert {n['source_id'] for n in reference.layout['notes']}=={n['id'] for n in model['notes']}


def test_reference_dimming_uses_performing_hand_in_a_mixed_display_staff():
    from piano_teacher.score import _fade_inactive_staff
    svg='''<svg xmlns="http://www.w3.org/2000/svg"><g class="system"><g class="measure">
    <g class="staff" id="upper"/><g class="staff" id="lower"><path id="rail"/>
    <g class="layer" id="resident"><g class="note" id="left-key"/></g>
    <g class="layer" id="transferred"><g class="note" id="right-key"/></g>
    </g></g></g></svg>'''
    bindings={'left-key':{'hand':'left'},'right-key':{'hand':'right','notation_staff':'left'}}
    root=ET.fromstring(_fade_inactive_staff(svg,'right',note_bindings=bindings))
    nodes={n.get('id'):n for n in root.iter() if n.get('id')}
    assert nodes['lower'].get('opacity') is None
    assert nodes['resident'].get('opacity')=='0.48'
    assert nodes['transferred'].get('opacity') is None
    assert nodes['rail'].get('opacity')=='0.48'


def test_authored_wide_chord_staff_and_voice_are_preserved(tmp_path):
    notes=''.join('<note>'+('<chord/>' if i else '')+
        f'<pitch><step>{step}</step><octave>{octave}</octave></pitch>'
        '<duration>8</duration><voice>1</voice><type>half</type></note>'
        for i,(step,octave) in enumerate((('C',2),('C',4),('E',4),('G',4))))
    xml=f'''<score-partwise version="4.0"><part-list>
    <score-part id="RH"><part-name>Right hand</part-name></score-part>
    <score-part id="LH"><part-name>Left hand</part-name></score-part></part-list>
    <part id="RH"><measure number="1"><attributes><divisions>4</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef>
    </attributes>{notes}<note><rest/><duration>8</duration><voice>1</voice><type>half</type></note>
    </measure></part><part id="LH"><measure number="1"><attributes><divisions>4</divisions>
    <time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>F</sign><line>4</line></clef>
    </attributes><note><rest measure="yes"/><duration>16</duration><voice>1</voice></note>
    </measure></part></score-partwise>'''
    path=tmp_path/'authored.musicxml';path.write_text(xml)
    piece,_=import_piece(path)
    score=build_lesson_score(piece.phrases[0],boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures,clef_changes=piece.clef_changes,
        source_musicxml=piece.source_musicxml)
    model=build_score_model(score,boundaries=piece.bar_boundaries)
    events=[e for e in model['notation_events'] if e['kind']=='note']
    assert {e['staff'] for e in events}=={'right'}
    assert {e['hand'] for e in events}=={'right'}
    assert len({e['voice'] for e in events})==1
    assert sum(not e['chord'] for e in events)==1


def test_transferred_rh_half_and_resident_lh_quarter_keep_separate_notation_voices(peace):
    plan=LearningPlan(peace);plan.select_step(7)
    score=build_lesson_score(plan.active_phrase,boundaries=peace.bar_boundaries,
        time_signatures=peace.time_signatures,default_clefs=infer_piece_clefs(peace.notes))
    model=build_score_model(score,boundaries=peace.bar_boundaries)
    unison=[e for e in model['notation_events'] if e['kind']=='note'
            and e['beat']==.5 and e['midi_pitch']==36]
    assert len(unison)==2
    assert {e['staff'] for e in unison}=={'left'}
    assert {e['hand'] for e in unison}=={'right','left'}
    assert {e['note_type'] for e in unison}=={'half','quarter'}
    assert len({e['voice'] for e in unison})==2
    assert len({e['source_id'] for e in unison})==2


@pytest.mark.parametrize('shared,selected,opacity',(
    (False,'right',1.),(False,'left',.48),(True,'right',1.),(True,'left',1.)))
def test_real_reference_ledger_opacity_follows_the_transferred_note(shared,selected,opacity):
    from piano_teacher.score import render_layout
    notes=tuple(Note(0,2,p,0,0,'right',f'r-{p}','r') for p in (36,60,64,67))
    notes+=(Note(0,1 if shared else 2,36 if shared else 48,1,0,'left','l-key','l'),)
    phrase=Phrase(1,1,1,0,4,notes)
    score=build_lesson_score(phrase,boundaries=(0,4),time_signatures=((0,4,4),),default_clefs=CLEFS)
    reference=render_layout(score,1,1,selected,total_beats=4,continuous=True)
    root=ET.fromstring(reference.pages[0])
    parents={child:parent for parent in root.iter() for child in parent}
    staff=[n for n in root.iter() if n.get('class')=='staff'][1]
    rules=[path for g in staff.iter() if g.get('class')=='ledgerLines below' for path in g]
    assert len(rules)==2
    for path in rules:
        effective=1.
        node=path
        while node is not None:
            effective*=float(node.get('opacity','1'))
            node=parents.get(node)
        assert effective==opacity,'Ledger ownership followed the display staff instead of its source note'
