"""Actual backend preview, assessment and retry snapshots drive native PNGs."""
from copy import deepcopy
import json
from pathlib import Path

import mido
import numpy as np
from PIL import Image
import pytest

from continuous_repeat_pixel_helpers import notation_ink
from piano_teacher.notation.reference_font import feature_glyphs
from piano_teacher.notation.pixel_proof import detect_staff_lines
from piano_teacher.notation.symbol_pixel_proof import _match_glyph
from test_continuous_repeat_pixels import ALA, ROOT, build_repeat_fixture, repeat_originals
from test_native_fingering import _godot, _run_godot


def _perform(engine, now, until=None):
    events=[]
    phrase=engine.plan.active_phrase
    for note in phrase.notes:
        if note.hand!=engine.plan.hand and engine.plan.hand!='both':
            continue
        if until is not None and note.start-phrase.start>=until:
            continue
        events.extend(((note.start-phrase.start,note.pitch,True),(note.end-phrase.start,note.pitch,False)))
    for beat,pitch,down in sorted(events):
        now[0]=engine.run_at+beat*60/engine.plan.bpm
        engine._receive(mido.Message('note_on' if down else 'note_off',
                                     note=pitch,velocity=80 if down else 0))


@pytest.fixture(scope='module',params=[(flow,bpm) for flow in
    ('preview','clean','failure','local-recovery','manual') for bpm in (40,80,120)],
    ids=lambda value:f'{value[0]}-{value[1]}')
def transport_capture(request,repeat_originals,tmp_path_factory):
    from piano_teacher import server
    from piano_teacher.learning import Exercise,LearningPlan
    from piano_teacher.music import Phrase
    from scripts.check_native_verovio_overlay import AuditCase

    flow,bpm=request.param
    tmp_path=tmp_path_factory.mktemp(f'transport-{flow}-{bpm}')
    monkeypatch=pytest.MonkeyPatch()
    original,plan=repeat_originals
    first,last=(29,32) if flow=='local-recovery' else (30,30)
    engine=server.PracticeEngine(tmp_path/'backend',enable_midi=False)
    # The fixture chooses the complete real excerpt as one learning unit;
    # production plan, transport, MIDI callbacks and grading remain unchanged.
    source_start,source_end=original.bar_boundaries[first-1],original.bar_boundaries[last]
    notes=tuple(note for note in original.notes if source_start<=note.start<source_end)
    phrase=Phrase(1,first,last,source_start,source_end,notes)
    engine.plan=LearningPlan(original,consolidate=True)
    engine.plan.exercises=(Exercise('learn',phrase,'actual-repeat-excerpt'),)
    engine.plan.set_hand('left')
    engine.plan.variant_index=len(engine.plan.variants)-1
    engine.plan.target_bpm=240
    engine.plan.bpm=bpm
    rate=bpm/60
    data=build_repeat_fixture(AuditCase(flow,ALA,first,last,'left'),piece=original,plan=plan,
                              phrase=engine.plan.active_phrase)
    xml=tmp_path/'source.musicxml';xml.write_text(data['xml'])
    now=[100.0]
    monkeypatch.setattr(server.time,'monotonic',lambda:now[0])
    engine._piano_connected=lambda:flow in ('clean','failure','local-recovery')
    try:
        assert engine._source_model()['practice_timeline']==data['model']['practice_timeline']
        fields=('id','onset_beats','duration_beats','midi_pitch','hand')
        assert [tuple(n[key] for key in fields) for n in engine._source_model()['notes']] == [
            tuple(n[key] for key in fields) for n in data['model']['notes']]
        engine.start()
        revision=engine.score_revision
        duration=data['model']['duration_beats']
        samples=[]
        def sample(name):
            state=deepcopy(engine.state())
            samples.append({'name':name,'clock':state['visual_scroll_beat'],'state':state})
            assert state['revision']==revision
            return state
        if flow=='manual':
            now[0]=engine.run_at+1/rate
            engine.control('restart')
        elif flow in ('clean','local-recovery'):
            _perform(engine,now,6.0 if flow=='local-recovery' else None)
            now[0]=engine.run_at+duration/rate+.21
            engine.state()
        elif flow=='failure':
            now[0]=engine.run_at+duration/rate+.03
            engine.state()
        else:
            now[0]=engine.run_at+duration/rate+.21
            engine.state()
        if flow in ('preview','clean'):
            assert engine._preview_loop_pending if flow=='preview' else engine.pending_result.clean
            midpoint=engine.run_at+(duration+data['gap_beats']/2)/rate
            start=duration;end=duration+data['gap_beats']
        else:
            target=6.0 if flow=='local-recovery' else 0.0
            assert engine.practice_preparation['source_from_beat']==target
            assert engine.pending_rewind==target
            for tag,fraction in [('reverse-before',.25),('reverse',.5),('reverse-after',.75)]:
                now[0]=engine._visual_rewind_at+engine._visual_rewind_seconds*fraction
                reverse=sample(tag)
                assert reverse['visual_scroll_speed']<0
                assert reverse['practice_preparation']['source_from_beat']==target
            measure=engine.practice_preparation['measure']
            start,end=measure['start_beat'],measure['end_beat']
            midpoint=engine._preparation_at+measure['duration_beats']*30/engine.plan.bpm
        rest_frames=[]
        for index,delta in enumerate((-.125,0,.125)):
            now[0]=midpoint+delta*60/engine.plan.bpm
            state=sample('silence-'+str(index))
            rest_frames.append(samples[-1])
            assert not state['running']
            assert state['scoring_available']==(flow in ('clean','failure','local-recovery'))
            assert start<state['visual_scroll_beat']<end
            if index==1:
                engine.control('pause')
                paused=sample('paused')
                now[0]+=17
                held=sample('paused-later')
                assert held['visual_scroll_beat']==pytest.approx(paused['visual_scroll_beat'],abs=1e-12)
                engine.control('resume')
                unpaused=sample('unpaused')
                assert unpaused['visual_scroll_beat']==pytest.approx(paused['visual_scroll_beat'],abs=1e-12)
                midpoint+=17
        deadline=engine.next_at
        now[0]=deadline
        resumed=sample('resumed')
        assert resumed['running'] and resumed['count_in_beats']==0
        assert resumed['visual_scroll_beat']==pytest.approx(end)
        now[0]=deadline+.125*60/engine.plan.bpm
        sample('replayed')
        if flow=='clean':
            # A clean pass below target advances tempo and begins a fresh
            # target-tempo streak; mastery still requires consecutive passes.
            assert engine.plan.streak==0 and engine.plan.bpm>bpm
            assert not engine.plan.mastered
        data['repeat_frames']=samples
        data['state']={'practice_timeline':data['model']['practice_timeline']}
        data['transport_window']={'start_beat':start,'end_beat':end,'flow':flow,'bpm':bpm}
        payload=tmp_path/'fixture.json';payload.write_text(json.dumps(data))
    finally:
        monkeypatch.undo()
        engine.db.close()
    result=_run_godot([*_godot(),'--path',str(ROOT/'godot'),'--rendering-method','gl_compatibility',
        '--audio-driver','Dummy','--script',str(ROOT/'tests/godot/continuous_repeat_capture.gd'),
        '--',str(payload),str(tmp_path)],timeout=90)
    (tmp_path/'godot.log').write_text(result.stdout+result.stderr)
    assert result.returncode==0 and 'SCRIPT ERROR' not in result.stdout+result.stderr,result.stdout+result.stderr
    return tmp_path,data,json.loads((tmp_path/'repeat-report.json').read_text())


def test_backend_preparation_is_visibly_engraved_and_next_source_stays_attached(transport_capture):
    folder,data,report=transport_capture
    window=data['transport_window']
    for frame in report['frames']:
        if not frame['name'].startswith('silence-'):
            continue
        image=Image.open(folder/frame['base']).convert('RGB')
        staves=detect_staff_lines(image);ink=notation_ink(image)
        top=round(staves['right'].lines[0]);bottom=round(staves['left'].lines[-1])
        rules=[]
        for beat in (window['start_beat'],window['end_beat']):
            anchor=image.width*.42+(beat-frame['clock'])*96
            columns=[x for x in range(round(anchor-2*staves['right'].gap),round(anchor)+1)
                     if ink[top:bottom+1,x].mean()>=.97]
            assert columns,'Backend scheduled silence lacks a full-grand-staff boundary'
            rules.append(float(np.mean(columns)))
        center=sum(rules)/2
        for staff in staves.values():
            score=_match_glyph(ink,feature_glyphs()['rest_whole'],staff.gap,center,staff.lines[1],
                centered=True,dxs=range(-2,3),dys=range(-2,3))
            assert score>=.80,'Backend preparation is not an authentic, centered whole-measure rest'
        assert frame['instances'],'Source instances disappeared during the real transport gap'


def test_backend_clock_steps_have_identical_pixel_velocity_inside_silence(transport_capture):
    from piano_teacher.notation.phase3_pixels import verify_translation_sequence
    folder,_,report=transport_capture
    frames=[frame for frame in report['frames'] if frame['name'].startswith('silence-')]
    images=[Image.open(folder/f['base']).convert('RGB') for f in frames]
    proof=verify_translation_sequence(*images)
    assert proof['passed'],proof
    assert proof['pixel_steps']==[12,12],proof


def test_pause_resume_inside_rest_preserves_exact_framebuffer(transport_capture):
    folder,_,report=transport_capture
    frames={frame['name']:frame for frame in report['frames']}
    reference=np.asarray(Image.open(folder/frames['silence-1']['base']))
    for name in ('paused','paused-later','unpaused'):
        assert np.array_equal(reference,np.asarray(Image.open(folder/frames[name]['base']))),name


def test_backend_phase_frames_keep_measure_widths_and_single_owned_boundaries(transport_capture):
    from piano_teacher.notation.measure_pixels import verify_measure_frame
    from test_measure_invariant_pixels import boundary_inventory
    folder, data, report = transport_capture
    window = data['transport_window']
    boundaries = {boundary['beat']:boundary for boundary in boundary_inventory(data,data['gap_beats'])
                  if not window['start_beat'] < boundary['beat'] < window['end_beat']}
    for beat in (window['start_beat'],window['end_beat']):
        boundaries[beat] = {'beat':beat}
    clearance = None
    measurements = []
    evidence = {}
    for frame in report['frames']:
        proof = verify_measure_frame(Image.open(folder/frame['base']).convert('RGB'),list(boundaries.values()),
            clock_beat=frame['clock'],density=96.0,clearance_px=clearance)
        assert proof['passed'],(data['transport_window']['flow'],frame['name'],proof['errors'])
        if clearance is None:
            clearance = proof['clearance_px']
        measurements.append({'frame':frame['name'],'clock':frame['clock'],
                             'widths':proof['widths'],'boundaries':proof['boundaries']})
        evidence[frame['name']] = proof
    (folder/'backend-measure-widths.json').write_text(json.dumps(measurements,indent=2))
    snapshots = {item['name']:item['state'] for item in data['repeat_frames']}
    pairs = [('silence-0','silence-1'),('unpaused','silence-2'),('resumed','replayed')]
    if 'reverse' in evidence:
        pairs += [('reverse-before','reverse'),('reverse','reverse-after')]
    motions = []
    for before,after in pairs:
        seconds=(snapshots[after]['clock_sampled_at_ms']-snapshots[before]['clock_sampled_at_ms'])/1000
        expected=96*snapshots[before]['visual_scroll_speed']*seconds
        left={row['beat']:row['observed_x'] for row in evidence[before]['boundaries']}
        right={row['beat']:row['observed_x'] for row in evidence[after]['boundaries']}
        common=sorted(left.keys() & right.keys())
        assert len(common)>=2
        steps=[left[beat]-right[beat] for beat in common]
        assert all(abs(step-expected)<=1.5 for step in steps),(before,after,steps,expected)
        motions.append({'from':before,'to':after,'seconds':seconds,
            'bpm':snapshots[before]['bpm'],'expected_px':expected,'observed_px':steps,
            'observed_px_per_second':[step/seconds for step in steps]})
    (folder/'backend-measure-motion.json').write_text(json.dumps(motions,indent=2))
