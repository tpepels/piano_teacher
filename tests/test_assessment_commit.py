"""Settlement consumes chosen progress with original assessment evidence."""
from test_assessment_atomicity import _engine,_pending


def test_evidence_uses_performed_stage_and_bpm_before_install(tmp_path):
    engine = _engine(tmp_path)
    try:
        result = _pending(engine,"correct")
        stage,bpm=engine.plan.identity,engine.plan.bpm
        pending=engine._prepare_teaching("full_result",result)
        receipt=engine.attempt_settlement.settle(pending,plan=engine.plan,binding=engine._teaching_binding(),now=engine.now())
        assert receipt.previous_stage==stage and receipt.previous_bpm==bpm
        assert engine.db.execute("SELECT t.stage_key,a.bpm FROM learning_assessments a JOIN learning_attempts t USING(attempt_id)").fetchall()==[(stage,bpm)]
        assert receipt.accelerated and not receipt.stage_changed
        assert engine.plan.bpm>bpm
        assert engine.attempt_settlement.settle(pending,plan=engine.plan,binding=engine._teaching_binding(),now=engine.now()) is receipt
        assert engine.db.execute("SELECT count(*) FROM learning_assessments").fetchone()[0]==1
    finally:
        engine.db.close()
