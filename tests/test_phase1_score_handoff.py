"""Count-in must wait for the matching native assets and semantic model."""
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
            clean=True
            passed=True
            extra_notes=0
            notes=[1]
        e.pending_result=Result()
        e.running=False
        e.visual_transport.next_at=now[0]-.1
        e.auto=True
        e.plan.hand_index=len(e.plan.hands)-1
        e.plan.bpm=e.plan.piece.bpm
        e.plan.streak=2
        # Continuous handoff: while the next stage's native ink is not yet
        # prepared and acknowledged the current score keeps scrolling. The
        # engine must neither swap the score revision (blanking the viewport)
        # nor start the next transport on an unmatched revision.
        revision=e.score_revision
        for _ in range(3):
            now[0]+=900
            state=e.state()
            assert state['phase']=='feedback'
            assert state['awaiting_score_revision'] is None
            assert state['transport_id']==previous
            assert e.score_revision==revision
        # An acknowledgement for ink that was never prepared is refused.
        import pytest
        with pytest.raises(ValueError):
            e.acknowledge_preloaded_stage(stage_key='unprepared', revision=revision+1)
        assert e.state()['transport_id']==previous
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

def test_frontend_ack_requires_matching_native_assets_and_model(tmp_path):
    # Delegate to the real production app regression: stale models, rejected
    # atlases/notation and matching score_ready, without a PNG sentinel.
    from test_native_production import test_native_production_readiness_and_failure_gate

    test_native_production_readiness_and_failure_gate(tmp_path, "default")
