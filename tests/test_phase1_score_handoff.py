"""Count-in must wait until Godot has decoded the new score."""
from pathlib import Path
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher import server

def piece():
    notes=(Note(0, 1, 60, 0, 0, 'right'), Note(4, 5, 62, 0, 0, 'right'))
    return Piece('Handoff', 100, notes, (Phrase(0, 1, 2, 0, 4, (notes[0],)),
                                         Phrase(1, 3, 4, 4, 8, (notes[1],))))

def test_auto_advance_waits_for_correct_revision(tmp_path, monkeypatch):
    now=[200.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    e=PracticeEngine(tmp_path, enable_midi=False)
    e.plan=LearningPlan(piece())
    e.fingerprint='handoff'
    try:
        e.start()
        previous=e.transport_id
        class Result:
            correct=1
            extra_notes=0
            notes=[1]
        e.pending_result=Result()
        e.running=False
        e.next_at=now[0]-.1
        e.auto=True
        e.plan.hand_index=len(e.plan.hands)-1
        e.plan.bpm=e.plan.piece.bpm
        e.plan.streak=1
        state=e.state()
        assert state['phase']=='loading'
        assert state['exercise']==2
        revision=state['revision']
        assert state['awaiting_score_revision']==revision
        e.control('score_ready', revision=revision-1)
        assert e.state()['phase']=='loading'
        now[0]+=900
        assert e.state()['phase']=='loading'
        assert e.transport_id==previous
        e.control('score_ready', revision=revision)
        ready=e.state()
        assert ready['phase']=='count_in' and ready['running']
        assert ready['transport_id']==previous+1
        assert ready['awaiting_score_revision'] is None
    finally:
        e.db.close()

def test_stop_cancels_pending_render(tmp_path):
    e=PracticeEngine(tmp_path,enable_midi=False)
    try:
        e.awaiting_score_revision=7
        e.control('stop')
        e.control('score_ready',revision=7)
        assert e.awaiting_score_revision is None
        assert not e.running
    finally:
        e.db.close()

def test_frontend_ack_requires_current_png():
    gd=(Path(__file__).resolve().parents[1] / 'godot/main.gd').read_text()
    assert '"action": "score_ready", "revision": revision' in gd
    assert 'rendered_revision == revision and score_view.texture != null' in gd
