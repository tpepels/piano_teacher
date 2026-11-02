"""Complete MIDI-only Coda/Fukuda teaching journey, selection and resumption."""
from collections import Counter
from pathlib import Path

import mido
import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi


def make_piece(path: Path, *, sustain: bool = False) -> None:
    """Six dense original bars in two hands, including mistakes in chords."""
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for hand in ("Right Hand", "Left Hand"):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage(
            "track_name", name=hand, time=0))
        track.append(mido.MetaMessage(
            "time_signature", numerator=4, denominator=4, time=0))
        events = []
        for bar in range(6):
            for attack in range(8):
                tick = bar * 1920 + attack * 240
                pitch = (60 + (attack % 5) if hand == "Right Hand"
                         else 41 + attack % 3)
                length = 240
                if sustain and hand == "Right Hand" and bar == 1 and attack == 7:
                    length = 720  # Long note from bar 2 into bar 3.
                events.extend(((tick, True, pitch),
                               (tick + length, False, pitch)))
        if hand == "Right Hand":
            for pitch in (48, 55, 67, 72):
                events.extend(((0, True, pitch), (240, False, pitch)))
        last = 0
        for tick, on, pitch in sorted(events, key=lambda x:(x[0], x[1])):
            track.append(mido.Message(
                "note_on" if on else "note_off", note=pitch,
                velocity=80 if on else 0, time=tick-last))
            last = tick
        track.append(mido.MetaMessage("end_of_track", time=11520-last))
        midi.tracks.append(track)
    midi.save(path)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "adaptive.mid"
    make_piece(path)
    return load_midi(path)


def test_initial_lessons_are_progressive_and_cover_original_attacks(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    learn = tuple(ex for ex in plan.exercises if ex.kind == "learn")
    assert len(learn) > 1
    assert learn[0].phrase.last_bar < len(source.bar_boundaries)-1
    assert all(ex.phrase.last_bar-ex.phrase.first_bar <= 1 for ex in learn)
    assert Counter(n.source_id for ex in learn for n in ex.phrase.notes) == (
        Counter(n.source_id for n in source.notes))
    assert all(plan.exercises[i].phrase.first_bar <=
               plan.exercises[i + 1].phrase.first_bar
               for i in range(len(plan.exercises) - 2)
               if plan.exercises[i].kind == "learn"
               and plan.exercises[i+1].kind == "learn")
    assert plan.exercises[-1].kind == "perform"
    assert plan.exercises[-1].phrase.notes == source.notes
    assert all(step.key.startswith("course:2:coda-fukuda-midi:")
               for step in plan.lesson_steps)


@pytest.mark.parametrize(("status", "expected"), [
    ("wrong", "fukuda-midi-"),
    ("missed", "fukuda-midi-"),
    ("late", "coda-dotted-"),
    ("early", "coda-dotted-"),
    ("short", "coda-slowdown-"),
    ("long", "coda-slowdown-"),
])
def test_error_family_selects_matching_strategy(source, status, expected):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    sid = next(n.source_id for n in source.notes
               if n.hand == "right" and n.start == 0)
    assert plan.refresh_from_feedback({sid: status})
    assert any(n.source_id == sid for n in plan.exercise.phrase.notes)
    assert any(s.variant.level.startswith(expected)
               for s in plan.stages)
    assert plan.stages[-1].variant.level == "original"
    assert all(n.source_id in {x.source_id for x in plan.exercise.phrase.notes}
               for stage in plan.stages for n in stage.variant.notes)


def test_feedback_preserves_unaffected_stage_mastery_tempo_and_streak(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    step = next(s for s in plan.lesson_steps
                if s.kind == "learn" and s.first_bar >= 3
                and s.level != "original")
    plan.select_step(plan.lesson_steps.index(step) + 1)
    key = plan.identity
    plan.mastered[key] = source.bpm
    plan.stage_tempos[key] = source.bpm
    plan.bpm = source.bpm
    plan.streak = 2
    sid = next(n.source_id for n in source.notes
               if n.start == 0 and n.hand == "right")
    assert plan.refresh_from_feedback({sid: "wrong"}, prefer_repair=False)
    assert plan.identity == key
    assert plan.mastered[key] == source.bpm
    assert plan.stage_tempos[key] == source.bpm
    assert plan.bpm == source.bpm
    assert plan.streak == 2
    assert plan.refresh_from_feedback({}, prefer_repair=False)
    assert plan.identity == key
    assert plan.streak == 2


def test_safe_passage_cut_never_truncates_long_midi_sustain(tmp_path):
    path = tmp_path / "crossing.mid"
    make_piece(path, sustain=True)
    piece = load_midi(path)
    plan = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
    learn = tuple(ex for ex in plan.exercises if ex.kind == "learn")
    assert Counter(n.source_id for ex in learn for n in ex.phrase.notes) == (
        Counter(n.source_id for n in piece.notes))
    assert all(n.end <= ex.phrase.end + 1e-7
               for ex in learn for n in ex.phrase.notes)
    assert any(ex.phrase.first_bar == 2 and ex.phrase.last_bar >= 3
               for ex in learn)


def test_complete_course_reaches_final_original_performance(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    steps = tuple(plan.lesson_steps)
    assert len(steps) >= 6
    # The progression requires target-speed mastery, not automatic award
    # merely from importing a piece or selecting the next lesson.
    for step in steps:
        assert step.key not in plan.mastered
        assert plan.identity == step.key
        plan.set_bpm(plan.target_bpm)
        for attempt in range(3):
            msg = plan.apply_result(
                correct=len(plan.active_variant.notes),
                total=len(plan.active_variant.notes),
                extras=0)
            if attempt < 2:
                assert "pass" in msg.lower()
        assert step.key in plan.mastered
    assert plan.exercise.kind == "perform"
    assert plan.active_variant.level == "original"
    assert plan.active_variant.notes == source.notes
    assert plan.lesson_steps_mastered == len(plan.lesson_steps)


def test_engine_original_errors_replan_and_resume_progress(tmp_path):
    from piano_teacher.server import PracticeEngine
    from piano_teacher.practice import Assessment, NoteAssessment
    path = tmp_path / "engine.mid"
    make_piece(path)
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="coda-fukuda-midi")
        engine.load(str(path))
        plan = engine.plan
        assert len(plan.exercises) > 3
        start_index = next(i for i, v in enumerate(plan.variants)
                           if v.level == "original")
        plan.variant_index = start_index
        starting = plan.identity
        before_revision = engine.score_revision
        source_notes = plan.active_variant.notes
        failure = Assessment(tuple(
            NoteAssessment(n, "wrong" if i == 0 else "correct")
            for i, n in enumerate(source_notes)), 0)
        engine.pending_result = failure
        engine._commit_pending()
        assert engine.score_revision > before_revision
        assert engine.plan.identity != starting
        assert engine.plan.stages[-1].variant.level == "original"
        assert engine.plan.active_variant.level.startswith("fukuda-midi-")
        id_ = source_notes[0].source_id
        assert engine.fukuda_mistakes.evidence(engine.fingerprint)[id_] == "wrong"
        engine._save()
        engine.load(str(path))
        assert engine.plan.lesson_generator.error_status
        assert engine.plan.identity != starting
        engine._reset_current_path(fingerprint=engine.fingerprint, confirm=True)
        assert engine.plan.lesson_generator.error_status == ()
        assert engine.plan.exercise.kind == "learn"
    finally:
        engine.listen.cancel()
        engine.db.close()


def test_repeated_identical_mistake_revisits_simplification(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    sid = next(n.source_id for n in source.notes
               if n.hand == "right" and n.start == 0)
    assert plan.refresh_from_feedback({sid: "wrong"})
    focused = plan.exercise.key
    original_index = next(i for i, s in enumerate(plan.stages)
                          if s.variant.level == "original")
    plan.variant_index = original_index
    assert plan.active_variant.level == "original"
    # The second failure is the same exact graded note; no new course
    # compilation or status change occurs, but practice must not stall.
    assert not plan.refresh_from_feedback({sid: "wrong"})
    catalog = plan.lesson_generator.catalog
    assert plan.revisit_source_errors(frozenset({sid}))
    assert plan.lesson_generator.catalog is catalog
    assert plan.exercise.key == focused
    assert plan.variant_index == 0
    assert plan.active_variant.level.startswith("fukuda-midi-")
    assert not plan.revisit_source_errors(frozenset({sid}))


def test_progressive_consolidation_joins_original_passages_in_order(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    from piano_teacher.lesson_generators import lesson_hands
    joins = [(i, ex) for i, ex in enumerate(plan.exercises)
             if ex.key.startswith("hybrid:join:")]
    assert joins, "Long courses must assemble learned passages, not jump to the finale"
    assert any(ex.key.startswith("hybrid:join:4:") for _, ex in joins)
    for idx, ex in joins:
        learning = [p for p in plan.exercises[:idx] if p.kind == "learn"
                    and ex.phrase.first_bar <= p.phrase.first_bar
                    and p.phrase.last_bar <= ex.phrase.last_bar]
        assert len(learning) >= 2
        assert all(ex.phrase.end >= n.end - 1e-7 for n in ex.phrase.notes)
        assert Counter(n.source_id for n in ex.phrase.notes) == Counter(
            n.source_id for p in learning for n in p.phrase.notes)
        assert set(lesson_hands(ex)) <= {"right", "left", "both"}
        assert len(plan.lesson_definition.stages(ex, lesson_hands(ex)[0])) == 1
        assert plan.lesson_definition.stages(ex, lesson_hands(ex)[0])[-1].variant.level == "original"
    assert plan.exercises[-1].kind == "perform"
    assert plan.exercises[-1].phrase.notes == source.notes


def test_current_failed_attack_selects_its_passage_over_older_stored_error(source):
    plan = LearningPlan(source, exercise_strategy="coda-fukuda-midi")
    old = next(n for n in source.notes if n.hand == "right" and n.start == 0)
    current = next(n for n in source.notes if n.hand == "right" and n.start >= 12)
    current_ex = next(ex for ex in plan.exercises
                      if ex.kind == "learn" and current in ex.phrase.notes)
    plan.select(next(i for i, ex in enumerate(plan.exercises)
                     if ex.key == current_ex.key))
    plan.set_hand("right")
    plan.variant_index = len(plan.variants) - 1
    # This error belongs to a different bar; the current selection survives.
    assert plan.refresh_from_feedback({old.source_id: "wrong"},
                                      prefer_repair=False)
    assert plan.exercise.key == current_ex.key
    assert plan.refresh_from_feedback(
        {old.source_id: "wrong", current.source_id: "late"},
        focus_ids=frozenset({current.source_id}))
    assert plan.exercise.key == current_ex.key
    assert plan.active_variant.level.startswith("coda-dotted-")
    with pytest.raises(ValueError, match="Focus"):
        plan.refresh_from_feedback(
            {old.source_id: "wrong"},
            focus_ids=frozenset({current.source_id}))


def test_accepted_amber_midi_take_does_not_restart_or_reengrave(tmp_path):
    from piano_teacher.server import PracticeEngine
    from piano_teacher.practice import Assessment, NoteAssessment
    path = tmp_path / "accepted.mid"
    make_piece(path)
    engine = PracticeEngine(tmp_path / "accepted-data", enable_midi=False)
    try:
        engine.set_preferences(exercise_strategy="coda-fukuda-midi")
        engine.load(str(path))
        p = engine.plan
        p.variant_index = len(p.variants) - 1
        original_key = p.identity
        notes = p.active_variant.notes
        result = Assessment(tuple(
            NoteAssessment(n, "late" if i == 0 else "correct")
            for i, n in enumerate(notes)), 0)
        assert result.passed and not result.clean
        revision = engine.score_revision
        engine.pending_result = result
        engine._commit_pending()
        assert engine.plan.identity == original_key
        assert engine.score_revision == revision
        assert engine.fukuda_mistakes.evidence(engine.fingerprint)[
            notes[0].source_id] == "late"
        assert engine.plan.streak <= 1
    finally:
        engine.listen.cancel()
        engine.db.close()
