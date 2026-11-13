"""The selected teacher owns effects, including a valid nondefault choice."""
from dataclasses import replace
import pytest
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece


def plan():
    notes = tuple(Note(float(i), float(i)+.5, 60+i, 0, 0, "right") for i in range(8))
    return LearningPlan(Piece("authority", 120, notes, (Phrase(1, 1, 2, 0., 8., notes),)))


def test_exact_progress_install_does_not_select_or_award_a_second_time():
    p = plan()
    assert callable(getattr(p, "teaching_progress", None)), "immutable progress capture is missing"
    before = p.teaching_progress()
    chosen = replace(before, bpm=67, streak=0)
    p.apply_teaching_progress(chosen, definition=p.lesson_definition, expected=before)
    assert p.bpm == 67 and p.teaching_progress() == chosen
    with pytest.raises(ValueError, match="progress"):
        p.apply_teaching_progress(chosen, definition=p.lesson_definition, expected=before)


def test_every_builtin_generator_implements_teaching_authority():
    from piano_teacher.lesson_generators import (SourceLessonGenerator, CodaLessonGenerator,
        FukudaMidiLessonGenerator, ComposedLessonGenerator, AdaptiveComposedLessonGenerator,
        CodaFukudaMidiLessonGenerator)
    for cls in (SourceLessonGenerator, CodaLessonGenerator, FukudaMidiLessonGenerator,
                ComposedLessonGenerator, AdaptiveComposedLessonGenerator, CodaFukudaMidiLessonGenerator):
        assert callable(getattr(cls, "decide_teaching", None)), cls.__name__


def test_full_result_honors_injected_tempo_once_across_failed_save(tmp_path, monkeypatch):
    from test_assessment_atomicity import _engine, _pending
    engine = _engine(tmp_path)
    try:
        result = _pending(engine, "correct")
        teacher = engine.plan.lesson_generator
        method = type(teacher).decide_teaching
        calls = []
        def decide(self, event, state):
            calls.append(event)
            decision = method(self, event, state)
            if event.kind == "full_result":
                after = replace(decision.progress_after, bpm=73)
                return replace(decision, progress_after=after,
                    next_exposure=replace(decision.next_exposure, bpm=73))
            return decision
        monkeypatch.setattr(type(teacher), "decide_teaching", decide)
        p = engine.plan
        before_bpm = p.bpm
        engine._finish_full_passage(result, p.active_phrase.end-p.active_phrase.start, 4., engine.now())
        assert len(calls) == 1, "selected generator must decide the real full result"
        pending = engine.attempt_settlement.pending
        assert p.bpm == before_bpm, "next tempo must not mutate progress before settlement"
        save = engine.progress.save
        def fail(*args, **kwargs):
            save(*args, **kwargs)
            raise OSError("fault after save")
        monkeypatch.setattr(engine.progress, "save", fail)
        with pytest.raises(OSError, match="fault after save"):
            engine._commit_pending()
        assert engine.plan is p and engine.pending_result is result
        assert engine.attempt_settlement.pending is pending
        assert p.bpm == before_bpm
        monkeypatch.setattr(engine.progress, "save", save)
        engine._commit_pending()
        assert p.bpm == 73 and len(calls) == 1
    finally:
        engine.db.close()


def test_decision_validator_rejects_bool_bpm_and_unearned_mastery():
    from piano_teacher.teaching_decisions import (TeachingState, TeachingBinding, TeachingRouteFacts,
        TeachingEvent, validate_teaching_decision)
    from piano_teacher.application.mistake_responses import resolve_mistake_policy
    from piano_teacher.diagnosis_policies import LearnerSnapshot
    p = plan()
    state = TeachingState(1, TeachingBinding("run", "session", "piece", p.identity, 0, 0, 0, 0),
        p.course_state(), resolve_mistake_policy("adaptive"), (), LearnerSnapshot(p.identity, ()), None,
        TeachingRouteFacts(performed_bpm=p.bpm))
    event = TeachingEvent(1, "manual", "manual", action="start")
    decision = p.lesson_generator.decide_teaching(event, state)
    validate_teaching_decision(decision, event=event, state=state)
    with pytest.raises(ValueError, match="BPM"):
        validate_teaching_decision(replace(decision, progress_after=replace(decision.progress_after, bpm=True)), event=event, state=state)
    with pytest.raises(ValueError, match="mastery"):
        validate_teaching_decision(replace(decision, progress_after=replace(decision.progress_after,
            mastered=((p.identity, 120),))), event=event, state=state)


def test_rolling_and_focused_entries_consult_selected_authority(tmp_path, monkeypatch):
    from test_assessment_atomicity import _engine
    from piano_teacher.recovery import RecoveryDecision
    engine = _engine(tmp_path)
    try:
        engine.midi.port = object()
        engine.start()
        calls = []
        teacher = type(engine.plan.lesson_generator)
        original = teacher.decide_teaching
        def stop_rolling(self, event, state):
            calls.append(event.kind)
            decision = original(self, event, state)
            if event.kind == "rolling_result":
                return replace(decision, response=replace(decision.response, action="continue"),
                    progress_after=state.progress, continuation="continue",
                    next_exposure=replace(decision.next_exposure, bpm=state.progress.bpm))
            return decision
        monkeypatch.setattr(teacher, "decide_teaching", stop_rolling)
        phrase = engine.plan.active_phrase
        grid = engine.attempt_progression.grid_for(phrase, engine.plan.piece.bar_boundaries)
        import inspect
        fields = inspect.signature(RecoveryDecision).parameters
        assert fields  # the authentic detector supplies the production value below
        from piano_teacher.recovery import check_rolling_two_bar_window
        detected = check_rolling_two_bar_window(phrase, engine.plan.hand, engine.plan.bpm, [],
            from_beat=0., end_beat=grid[-1], grid=grid, threshold=1)
        assert detected is not None
        engine._apply_rolling_recovery(detected, phrase, grid, grid[-1], engine.now())
        assert calls == ["rolling_result"], "rolling callback bypassed selected authority"
        engine.review_end_beat = grid[-1]
        engine._complete_attempt(phrase, grid[-1], grid[-1], 4., engine.now())
        assert calls == ["rolling_result", "focused_result"]
        assert not engine.plan.mastered
    finally:
        engine.db.close()


@pytest.mark.parametrize("action,values", [("tempo_up", {}), ("tempo_down", {}), ("tempo", {"bpm":90}),
    ("hand", {"hand":"right"}), ("select_step", {"number":1}), ("next", {}), ("previous", {}),
    ("hints", {"enabled":True}), ("stop", {}), ("practice", {}), ("listen", {}), ("start", {})])
def test_manual_command_uses_selected_generator_once(tmp_path, monkeypatch, action, values):
    from test_assessment_atomicity import _engine
    engine = _engine(tmp_path)
    try:
        cls = type(engine.plan.lesson_generator)
        method = cls.decide_teaching
        calls = []
        def decide(self, event, state):
            calls.append(event)
            return method(self, event, state)
        monkeypatch.setattr(cls, "decide_teaching", decide)
        engine.control(action, **values)
        assert len(calls) == 1 and calls[0].kind == "manual"
    finally:
        engine.db.close()


def test_focused_continuation_honors_selected_range_without_second_teacher(tmp_path, monkeypatch):
    from test_assessment_atomicity import _engine
    engine = _engine(tmp_path)
    try:
        engine.midi.port = object()
        engine.start()
        engine.visual_transport.play_from_beat = 4.
        calls = []
        cls = type(engine.plan.lesson_generator)
        original = cls.decide_teaching
        def choose(self,event,state):
            calls.append(event.kind)
            decision = original(self,event,state)
            if event.kind == "focused_result":
                return replace(decision,next_exposure=replace(decision.next_exposure,from_beat=4.))
            return decision
        monkeypatch.setattr(cls,"decide_teaching",choose)
        phrase = engine.plan.active_phrase
        engine._complete_attempt(phrase,phrase.end-phrase.start,phrase.end-phrase.start,4.,engine.now())
        assert calls == ["focused_result"]
        assert engine.visual_transport.pending_rewind == 4.
        assert not engine.plan.mastered
    finally:
        engine.db.close()


@pytest.mark.parametrize("boundary",["decision","persist","source","install","save"])
def test_every_settlement_boundary_restores_sql_ram_and_same_pending(tmp_path,monkeypatch,boundary):
    from test_assessment_atomicity import _engine,_pending
    engine=_engine(tmp_path)
    try:
        result=_pending(engine,"missed")
        pending=engine._prepare_teaching("full_result",result)
        plan=engine.plan
        before_plan=plan.capture_teaching_state()
        def capture():
            state=engine.measurement.capture_state()
            state["guided"]=vars(state["guided"])
            return state
        before_capture=capture()
        before_sql=tuple(engine.db.iterdump())
        targets={"decision":(engine.measurement,"decision"),"persist":(engine.measurement,"persist"),
            "source":(engine.fukuda_mistakes,"observe"),"install":(plan,"apply_teaching_progress"),
            "save":(engine.progress,"save")}
        owner,name=targets[boundary]
        original=getattr(owner,name)
        calls=[]
        def fail(*args,**kwargs):
            calls.append(1)
            original(*args,**kwargs)
            raise OSError("after "+boundary)
        monkeypatch.setattr(owner,name,fail)
        with pytest.raises(OSError,match="after "):
            engine.attempt_settlement.settle(pending,plan=plan,binding=engine._teaching_binding(),now=engine.now())
        assert calls==[1]
        monkeypatch.delattr(owner,name)
        assert engine.plan is plan and engine.pending_result is result
        assert engine.attempt_settlement.pending is pending and pending.assessment is result
        assert plan.capture_teaching_state()==before_plan
        assert capture()==before_capture
        assert tuple(engine.db.iterdump())==before_sql
        receipt=engine.attempt_settlement.settle(pending,plan=plan,binding=engine._teaching_binding(),now=engine.now())
        assert engine.attempt_settlement.settle(pending,plan=plan,binding=engine._teaching_binding(),now=engine.now()) is receipt
        assert engine.db.execute("SELECT count(*) FROM learning_decisions").fetchone()[0]==1
    finally:
        engine.db.close()


def test_injected_different_source_is_prepared_and_started_without_redecision(tmp_path,monkeypatch):
    from test_seamless_stage_runway import _engine,_finish,Prepared
    from piano_teacher.teaching_course import manual_progress
    engine=_engine(tmp_path)
    try:
        cls=type(engine.plan.lesson_generator)
        original=cls.decide_teaching
        calls=[]
        def choose(self,event,state):
            calls.append(event.kind)
            decision=original(self,event,state)
            chosen=manual_progress(replace(state.course,progress=decision.progress_after),"select_step",number=3)
            return replace(decision,progress_after=chosen.progress,continuation="advance",
                next_exposure=replace(decision.next_exposure,stage_key=chosen.key,hand=chosen.hand,bpm=chosen.progress.bpm))
        monkeypatch.setattr(cls,"decide_teaching",choose)
        engine.future_score=Prepared(engine)
        at=_finish(engine)
        pending=engine.attempt_settlement.pending
        selection,number=engine._decided_stage_selection()
        assert number==3 and calls==["full_result"]
        assert engine.plan.lesson_step_number==1 and not engine.plan.mastered
        ack=engine.acknowledge_preloaded_stage(stage_key=selection.stage_key,revision=selection.revision)
        assert ack["accepted"]
        engine._advance_pending_feedback(max(at,engine.visual_transport.next_at),prepared_on_time=True)
        assert engine.plan.lesson_step_number==3 and engine.running
        assert engine.future_score.adoptions[-1].identity==selection.identity
        assert calls==["full_result"] and pending.receipt is not None
    finally:
        engine.db.close()


@pytest.mark.parametrize("mutation",["binding","progress","range","bool","nan","checkpoint"])
def test_invariant_rejections_precede_installation(mutation):
    from teaching_fixtures import teaching
    from piano_teacher.teaching_decisions import validate_teaching_decision
    p,event,state=teaching()
    decision=p.lesson_generator.decide_teaching(event,state)
    if mutation=="binding":
        decision=replace(decision,expected=replace(decision.expected,course_revision=1))
    elif mutation=="progress":
        decision=replace(decision,before_progress=replace(decision.before_progress,bpm=77))
    elif mutation=="range":
        decision=replace(decision,next_exposure=replace(decision.next_exposure,end_beat=.25))
    elif mutation in ("bool","nan"):
        decision=replace(decision,progress_after=replace(decision.progress_after,bpm=True if mutation=="bool" else float("nan")))
    else:
        decision=replace(decision,invalidate_failed_streak=True)
    before=p.capture_teaching_state()
    with pytest.raises(ValueError):
        validate_teaching_decision(decision,event=event,state=state)
    assert p.capture_teaching_state()==before


def test_prepared_renderer_cannot_autoplay_an_untimed_guided_exposure():
    from types import SimpleNamespace
    from piano_teacher.application.teaching_continuation import TeachingContinuation
    selected = SimpleNamespace(continuation="advance",
        next_exposure=SimpleNamespace(mode="learn"), response=None, remediation=None)
    effect = TeachingContinuation.after_settlement(
        selected, score_changed=True, prepared=True)
    assert effect.action == "guided"


@pytest.mark.parametrize("restart", [.5, 2., 2.+.00000001])
def test_teaching_source_safe_response_expands_held_notes_without_grid_index_crash(restart):
    """Partial start beats are legal; recovery must use source measure bounds."""
    from types import SimpleNamespace
    from piano_teacher.teaching_decisions import source_safe_response
    # First note is held across the selected start. The next source attack
    # begins before the requested end and continues beyond it.
    passage = Phrase(1, 1, 3, 0., 6., (
        Note(0., 3., 60, 0, 0, "right"),
        Note(3.5, 5.5, 64, 0, 0, "right"),
        Note(0., 6., 48, 0, 0, "left"),
    ))
    selected = SimpleNamespace(restart_beat=restart, end_beat=4., action="repair")
    repaired = source_safe_response(selected, phrase=passage, hand="right",
                                    grid=(0., 2., 4., 6.))
    assert repaired.restart_beat == 0.
    assert repaired.end_beat == 6.
    assert selected.restart_beat == restart and selected.end_beat == 4.


def test_teaching_source_safe_response_keeps_uninterrupted_fractional_source_range():
    from types import SimpleNamespace
    from piano_teacher.teaching_decisions import source_safe_response
    passage = Phrase(1, 1, 2, 0., 8., (Note(2., 3., 60, 0, 0, "right"),))
    response = SimpleNamespace(restart_beat=.5, end_beat=4., action="repair")
    observed = source_safe_response(response, phrase=passage, hand="right", grid=(0., 4., 8.))
    assert observed is not response and observed.restart_beat == .5 and observed.end_beat == 4.
