from piano_teacher.application import score_artifacts
from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.score import EngravedScore, _pitches_from_verovio
from piano_teacher.server import PracticeEngine
from piano_teacher.practice import PlayedNote
import time
import json


def piece():
    note=Note(0,1,60,0,0,'right')
    return Piece('Test',100,(note,),(Phrase(1,1,2,0,2,(note,)),))


def test_score_feedback_waits_until_displayed_before_curriculum_advance(tmp_path,monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    e=PracticeEngine(tmp_path,enable_midi=False)
    e.plan=LearningPlan(piece())
    e.fingerprint='feedback-case'
    layout={'pages':1,'beats':2,'anchors':[{'beat':0,'x':.25,'top':.1,'bottom':.9,'page':0,'system':'s'}],
            'notes':[{'id':'n0','pitch':60,'beat':0,'page':0,'system':'s','x':.25,'y':.4}]}
    monkeypatch.setattr(score_artifacts,'render_layout',lambda *a,**k:EngravedScore(('<svg/>',),layout))
    e.score=object()
    # Only a connected MIDI piano can produce graded performance feedback.
    e.midi_port = object()
    e.control('start')
    e.run_at=time.monotonic()-5
    first=e.state()
    assert first['phase']=='feedback'
    assert first['revision']==0
    assert first['feedback_marks'][0]['status']=='missed'
    assert e.pending_result is not None
    assert first["take_result"]["clean"] is False
    assert first["take_result"]["total"] == 1
    assert e.plan.failures==0
    deadline = e.next_at
    now[0] = deadline-.01
    second=e.state()
    # Keep the completed score readable throughout feedback, then automatically
    # retry imported Practice without changing the curriculum or mastery.
    assert second['phase']=='feedback'
    assert second['feedback_marks'][0]['status']=='missed'
    assert second['performance_summary']['missed']==1
    assert e.plan.failures==0
    now[0] = deadline+.01
    restarted=e.state()
    assert restarted['phase']=='playing'
    assert restarted['count_in_beats'] == 0 and restarted['awaiting_score_revision'] is None
    assert restarted['feedback_marks']==[]
    assert restarted['take_result'] is None
    assert e.plan.failures==1
    assert not e.plan.mastered and e.plan.index == 0 and e.plan.streak == 0
    e.db.close()


def test_verovio_pitch_extraction_uses_midi_values_not_svg_height():
    class Toolkit:
        def renderToMIDI(self): return 'base64-midi'
        def getMIDIValuesForElement(self,id):
            return json.dumps({'pitch': 61 if id=='c_sharp' else 60})
    assert _pitches_from_verovio(Toolkit(), [{'on':['c_sharp','c_nat']}]) == {'c_sharp':61,'c_nat':60}
