"""Real default-generator regressions for mastered stage retention and restore."""
from pathlib import Path

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_generators import lesson_hands
from piano_teacher.music import load_midi
from piano_teacher.progress_repository import ProgressRepository
from piano_teacher.practice import Assessment, NoteAssessment
from piano_teacher.server import PracticeEngine


MIDI = (Path(__file__).resolve().parents[1] / "midi" /
        "J_S_Bach_-_Invention_No_1_(BWV_772).midi")


def _plan():
    plan = LearningPlan(load_midi(MIDI), exercise_strategy="coda-fukuda-midi")
    plan.set_hand("right")
    return plan


def _master_scaffolds(plan):
    """Earn each earlier stage through three full-target accepted takes."""
    mastered = []
    while plan.active_variant.level != "original":
        stage, key = plan.active_stage, plan.identity
        plan.set_bpm(plan.target_bpm)
        for attempt in range(3):
            plan.apply_result(correct=len(stage.variant.notes),
                              total=len(stage.variant.notes))
            assert (key in plan.mastered) == (attempt == 2)
        mastered.append((key, stage))
    return tuple(mastered)


def _visible(plan):
    return {plan._stage_key(ex, hand, stage.variant): stage
            for ex in plan.exercises for hand in lesson_hands(ex)
            for stage in plan.lesson_definition.stages(ex, hand)}


@pytest.mark.parametrize("active", ["original", "mastered-scaffold"])
def test_feedback_keeps_exact_mastered_stages_and_adapts_unmastered_work(active):
    plan = _plan()
    mastered = _master_scaffolds(plan)
    assert len(mastered) == 3
    exercise = plan.exercise
    original = plan.stages[-1]
    if active == "mastered-scaffold":
        plan.variant_index = 0
    plan.set_bpm(83)
    plan.streak = 1
    cursor = (plan.identity, plan.bpm, plan.streak)
    tempos = dict(plan.stage_tempos)
    credit = set(plan.transferable_tempos)
    initial_keys = set(_visible(plan))
    ids = [n.source_id for n in original.variant.notes][2:4]
    for status in ("late", "short", "late"):
        assert plan.refresh_from_feedback(dict.fromkeys(ids, status),
                                          prefer_repair=False)
        visible = _visible(plan)
        assert all(visible.get(key) == stage for key, stage in mastered)
        assert plan.lesson_steps_mastered == len(mastered)
        assert (plan.identity, plan.bpm, plan.streak) == cursor
        assert all(plan.stage_tempos[key] == value for key, value in tempos.items())
        assert plan.transferable_tempos == credit
        stages = plan.lesson_definition.stages(exercise, "right")
        keys = [plan._stage_key(exercise, "right", s.variant) for s in stages]
        assert len(keys) == len(set(keys))
        assert [key for key in keys if key in plan.mastered] == [
            key for key, _ in mastered]
        assert stages[-1] == original
        assert any(key not in initial_keys for key in keys)
        assert plan.exercises[-1].phrase.notes == plan.piece.notes
        unchanged = plan.lesson_definition
        assert not plan.refresh_from_feedback(dict.fromkeys(ids, status),
                                              prefer_repair=False)
        assert plan.lesson_definition is unchanged


@pytest.mark.parametrize("active", ["original", "mastered-scaffold"])
def test_reopen_recovers_mastered_catalog_definitions_before_filtering_credit(tmp_path, active):
    plan = _plan()
    mastered = _master_scaffolds(plan)
    if active == "mastered-scaffold":
        plan.variant_index = 0
    active_key = plan.identity
    plan.set_bpm(83)
    plan.streak = 1
    ids = [n.source_id for n in plan.stages[-1].variant.notes][2:4]
    repo = ProgressRepository(tmp_path / "progress.db")
    try:
        repo.save(plan, "bach")
        unknowns = (mastered[0][0].replace("course:3:", "course:999:"),
                    mastered[0][0].rsplit(":", 1)[0] + ":unknown-content")
        for unknown in unknowns:
            repo.db.execute("INSERT INTO mastery VALUES (?,?,?)", ("bach", unknown, 120))
            repo.db.execute("INSERT INTO stage_tempos VALUES (?,?,?)", ("bach", unknown, 120))
            repo.db.execute("INSERT INTO repeat_tempo_credit VALUES (?,?)", ("bach", unknown))
        repo.db.commit()
        reopened = LearningPlan(plan.piece, exercise_strategy="coda-fukuda-midi",
                                feedback=dict.fromkeys(ids, "late"))
        assert any(key not in _visible(reopened) for key, _ in mastered)
        repo.restore(reopened, "bach")
        visible = _visible(reopened)
        assert all(visible.get(key) == stage for key, stage in mastered)
        assert reopened.mastered == plan.mastered
        assert reopened.stage_tempos == plan.stage_tempos
        assert reopened.transferable_tempos == plan.transferable_tempos
        assert (reopened.identity, reopened.bpm, reopened.streak) == (active_key, 83, 1)
        for unknown in unknowns:
            assert unknown not in visible
            assert repo.db.execute("SELECT bpm FROM mastery WHERE exercise=?",
                                   (unknown,)).fetchone() == (120,)
        definition = reopened.lesson_definition
        repo.restore(reopened, "bach")
        assert reopened.lesson_definition == definition
        assert len(reopened.lesson_steps) == len({s.key for s in reopened.lesson_steps})
    finally:
        repo.close()


@pytest.mark.parametrize("scope", ["passage", "whole-piece"])
@pytest.mark.parametrize("status", ["late", "short", "wrong", "correct"])
def test_real_generator_take_end_decision_is_pure_and_never_publishes_stale_score(
        tmp_path, monkeypatch, scope, status):
    from piano_teacher import server

    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    app = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        app.set_preferences(exercise_strategy="coda-fukuda-midi")
        app.load(str(MIDI))
        p = app.plan
        if scope == "whole-piece":
            p.select(len(p.exercises) - 1)
        else:
            p.set_hand("right")
            _master_scaffolds(p)
        p.variant_index = len(p.variants) - 1
        mastered = dict(p.mastered)
        definitions = {key: stage for key, stage in _visible(p).items()
                       if key in mastered}
        for repeat in range(2):
            # Repeat the same original evidence after settlement has stored it.
            p.variant_index = len(p.variants) - 1
            p.bpm = 83  # Below target, so settlement cannot advance by mastery.
            p.streak = 0
            app.midi.port = object()
            app.control("start", continuous_horizon_beats=9.5)
            notes = p.active_variant.notes
            result = Assessment(tuple(NoteAssessment(
                note, status if i in (2, 3) else "correct")
                for i, note in enumerate(notes)), 0)
            assert result.passed == (status != "wrong")
            identity, revision = p.identity, app.score_revision
            before = {key: value.copy() if isinstance(value, (dict, list, set))
                      else value for key, value in vars(p).items()}
            evidence = app.fukuda_mistakes.evidence(app.fingerprint)
            pending = app._prepare_teaching("full_result",result)
            assert vars(p) == before
            assert app.fukuda_mistakes.evidence(app.fingerprint) == evidence
            chosen = pending.decision
            from dataclasses import replace
            selected = replace(pending.state.course,definition=chosen.definition_after,progress=chosen.progress_after)
            decided = selected.key != identity
            if repeat and status != "wrong":
                assert decided is False
            beats = p.active_phrase.end - p.active_phrase.start
            duration = beats * 60 / p.bpm
            now[0] = app.visual_transport.run_at + duration + .21
            app.measurement.seal(app.recorder.presses, state="completed",
                                 reason="full_passage", result=result, eligible=False)
            app._finish_full_passage(result, beats, duration, now[0])
            if decided or chosen.remediation is not None:
                assert app.visual_transport.announced_continuation is None
            else:
                assert app.visual_transport.announced_continuation is not None
            app._commit_pending()
            if decided is False:
                assert p.identity == identity
            if status == "wrong":
                assert p.identity != identity
                assert app.score_revision > revision
            else:
                assert p.identity == identity
                assert app.score_revision == revision
            assert p.mastered == mastered
            assert all(_visible(p)[key] == stage for key, stage in definitions.items())
            app.control("stop")
    finally:
        app.close()
