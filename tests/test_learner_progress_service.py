"""Source-bound learner queries and persistence without a practice engine."""
import gc
import importlib
import json
import sqlite3
import weakref

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.learner_state import LearnerStateStore
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import NoteAssessment


FINGERPRINT = "imported-source-a"
FIRST = dict(first_bar=1, last_bar=2, start_beat=0.0, end_beat=8.0,
             source_indices=[0, 2], required_notes=2)
SECOND = dict(first_bar=3, last_bar=4, start_beat=8.0, end_beat=16.0,
              source_indices=[4, 6], required_notes=2)
THIRD = dict(first_bar=5, last_bar=6, start_beat=16.0, end_beat=24.0,
             source_indices=[8, 10], required_notes=2)
EMPTY = dict(resume_unit=None, completed_units=[], trouble_units=[],
             skip_status="active", skip_reason="")


def make_plan():
    notes = tuple(Note(float(bar*4), float(bar*4+1), pitch+bar, 0, 0, hand,
                       f"source-{bar}-{hand}")
                  for bar in range(8) for hand, pitch in (("right", 60), ("left", 48)))
    phrase = Phrase(1, 1, 8, 0.0, 32.0, notes)
    return LearningPlan(Piece("Learner service", 100, notes, (phrase,),
        bar_boundaries=tuple(float(i*4) for i in range(9)),
        time_signatures=((0.0, 4, 4),)), consolidate=True)


@pytest.fixture
def store(tmp_path):
    db = sqlite3.connect(tmp_path/"learner.sqlite3")
    try:
        yield LearnerStateStore(db)
    finally:
        db.close()


@pytest.fixture
def service(store):
    try:
        module = importlib.import_module("piano_teacher.application.learner_progress")
    except ModuleNotFoundError as exc:
        pytest.fail(f"Independent learner progress owner is missing: {exc.name}")
    return module.LearnerProgress(store)


@pytest.mark.parametrize("bound, fingerprint", [(False, FINGERPRINT), (True, ""),
                                                (True, FINGERPRINT)])
def test_missing_plan_fingerprint_or_unknown_stage_has_fresh_unsaved_defaults(
        service, store, bound, fingerprint):
    plan = make_plan() if bound else None
    saved = service.saved(plan, fingerprint=fingerprint, stage_key="unknown-stage")
    assert saved == EMPTY
    saved["completed_units"].append(FIRST)
    assert service.saved(plan, fingerprint=fingerprint, stage_key="unknown-stage") == EMPTY
    assert store.db.execute("SELECT count(*) FROM learner_stages").fetchone()[0] == 0


def test_saved_state_isolated_by_fingerprint_stage_and_returned_value(service, store):
    plan = make_plan()
    key = plan.identity
    store.complete_unit(FINGERPRINT, key, FIRST, assisted=True)
    store.save_resume(FINGERPRINT, key, SECOND)
    store.mark_skipped(FINGERPRINT, key, reason="  Try fuller notes  ", status="placed")
    saved = service.saved(plan, fingerprint=FINGERPRINT)
    assert saved == dict(resume_unit=SECOND, completed_units=[FIRST], trouble_units=[],
                         skip_status="placed", skip_reason="Try fuller notes")
    saved["resume_unit"]["source_indices"].clear()
    assert service.saved(plan, fingerprint=FINGERPRINT)["resume_unit"] == SECOND
    assert service.saved(plan, fingerprint="another-import") == EMPTY
    assert service.saved(plan, fingerprint=FINGERPRINT, stage_key="") == service.saved(
        plan, fingerprint=FINGERPRINT)  # Empty keys retain the current-stage fallback.


@pytest.mark.parametrize("mode, current_range, expected", [
    ("learn", (8.0, 16.0), SECOND), ("practice", (8.0, 16.0), None),
    ("learn", None, None), ("learn", (8.0, 15.0), None),
    ("learn", (8.000001, 16.0), None),
])
def test_current_unit_requires_exact_source_range_and_learn_mode(
        service, mode, current_range, expected):
    assert service.guided_unit(make_plan(), mode=mode, guided_range=current_range) == expected
    assert service.guided_unit(None, mode=mode, guided_range=current_range) is None


def test_snapshot_counts_only_current_bindings_and_projects_after_the_current_idea(service, store):
    plan = make_plan()
    store.complete_unit(FINGERPRINT, plan.identity, FIRST, assisted=True)
    corrupt = dict(THIRD, source_indices=[999], required_notes=1)
    store.complete_unit(FINGERPRINT, plan.identity, corrupt)
    store.save_resume(FINGERPRINT, plan.identity, SECOND)
    expected = dict(resume_unit=SECOND, completed_units=[FIRST, corrupt], trouble_units=[],
        skip_status="active", skip_reason="", course_guided=True, prepared_units=1,
        total_units=4, current_unit=SECOND, next_unit=THIRD, unit_number=2)
    before = (plan.identity, plan.bpm, plan.streak, dict(plan.mastered))
    actual = service.snapshot(plan, fingerprint=FINGERPRINT, mode="learn",
                              guided_range=(8.0, 16.0), course_guided=True)
    assert json.dumps(actual) == json.dumps(expected)
    assert (plan.identity, plan.bpm, plan.streak, plan.mastered) == before
    assert service.saved(plan, fingerprint=FINGERPRINT)["resume_unit"] == SECOND


def test_completed_preparation_can_resume_an_old_idea_without_awarding_timed_mastery(service, store):
    plan = make_plan()
    fourth = dict(first_bar=7, last_bar=8, start_beat=24.0, end_beat=32.0,
                  source_indices=[12, 14], required_notes=2)
    for unit in (FIRST, SECOND, THIRD, fourth):
        store.complete_unit(FINGERPRINT, plan.identity, unit)
    all_done = service.snapshot(plan, fingerprint=FINGERPRINT, mode="practice",
                                guided_range=None, course_guided=False)
    assert all_done["prepared_units"] == all_done["total_units"] == 4
    assert all_done["current_unit"] is all_done["next_unit"] is None
    assert all_done["unit_number"] == 0 and not all_done["course_guided"]
    store.save_resume(FINGERPRINT, plan.identity, SECOND)
    resumed = service.snapshot(plan, fingerprint=FINGERPRINT, mode="practice",
                               guided_range=None, course_guided=True)
    assert resumed["next_unit"] == SECOND
    assert not plan.mastered and plan.streak == 0


def test_trouble_queries_keep_history_but_publish_only_current_source_bindings(service, store):
    plan = make_plan()
    key = plan.identity
    store.record_trouble(FINGERPRINT, "obsolete-stage", FIRST, errors=5, pitches=[60])
    store.record_trouble(FINGERPRINT, key, dict(FIRST, source_indices=[999], required_notes=1),
                         errors=5, pitches=[60])
    store.record_trouble(FINGERPRINT, key, SECOND, errors=6, pitches=[62])
    store.record_trouble("another-import", key, THIRD, errors=7, pitches=[64])
    expected = dict(stage_key=key, **SECOND, failures=1, errors=6, pitches=[62], resolved=False)
    assert service.valid_trouble_spots(plan, fingerprint=FINGERPRINT) == [expected]
    assert service.valid_trouble_spots(plan, fingerprint=FINGERPRINT, stage_key="unknown") == []
    projected = service.snapshot(plan, fingerprint=FINGERPRINT, mode="practice",
                                 guided_range=None, course_guided=False)
    assert projected["trouble_units"] == [{k: v for k, v in expected.items() if k != "stage_key"}]
    assert len(store.trouble_for_piece(FINGERPRINT)) == 3
    store.resolve_trouble(FINGERPRINT, key, SECOND)
    assert service.valid_trouble_spots(plan, fingerprint=FINGERPRINT) == []
    assert service.valid_trouble_spots(None, fingerprint=FINGERPRINT) == []
    assert service.valid_trouble_spots(plan, fingerprint="") == []


def test_trouble_queries_restore_canonical_labels_without_rewriting_saved_evidence(service, store):
    plan = make_plan()
    store.record_trouble(FINGERPRINT, plan.identity, SECOND, errors=2, pitches=[62])
    corrupted = dict(SECOND, first_bar=99, last_bar=99, required_notes=99)
    with store.db:
        store.db.execute("UPDATE learner_units SET unit=?", (json.dumps(corrupted),))
    spot, = service.valid_trouble_spots(plan, fingerprint=FINGERPRINT)
    assert {k: spot[k] for k in SECOND} == SECOND
    assert store.trouble_for_piece(FINGERPRINT)[0]["first_bar"] == 99


def test_queries_borrow_the_current_plan_and_never_retain_or_reselect_it(service):
    plan = make_plan()
    assert service.guided_unit(plan, mode="learn", guided_range=(0.0, 8.0)) == FIRST
    plan.select_step(2)
    assert plan.hand == "left"
    assert service.guided_unit(plan, mode="learn", guided_range=(0.0, 8.0))["source_indices"] == [1, 3]
    service.snapshot(plan, fingerprint=FINGERPRINT, mode="learn",
                     guided_range=(0.0, 8.0), course_guided=True)
    reference = weakref.ref(plan)
    del plan
    gc.collect()
    assert reference() is None


def test_lesson_overview_preserves_step_skip_and_mastery_values(service, store):
    plan = make_plan()
    first, second, third = plan.lesson_steps
    plan.mastered[first.key] = 100
    store.mark_skipped(FINGERPRINT, second.key, reason="Try both hands", status="placed")
    store.mark_skipped(FINGERPRINT, third.key, reason="Return later")
    overview = service.lesson_overview(plan, fingerprint=FINGERPRINT)
    assert {k: v for k, v in overview.items() if k != "steps"} == dict(
        trouble_spots=[], route_version=3, piece_fingerprint=FINGERPRINT,
        current_step=1, total_steps=3, completed_steps=1)
    assert overview["steps"] == [dict(number=i+1, exercise=1, hand=hand, level="original",
        key=step.key, kind="learn", first_bar=1, last_bar=8, required_notes=count,
        completed=i == 0, skip_status=status, skip_reason=reason)
        for i, (step, hand, count, status, reason) in enumerate((
            (first, "right", 8, "active", ""), (second, "left", 8, "placed", "Try both hands"),
            (third, "both", 16, "skipped", "Return later")))]
    unsaved = service.lesson_overview(plan, fingerprint="")
    assert all(step["skip_status"] == "active" for step in unsaved["steps"])
    assert unsaved["completed_steps"] == 1
    assert plan.identity == first.key and plan.streak == 0
    with pytest.raises(ValueError, match="Open a piece first"):
        service.lesson_overview(None, fingerprint=FINGERPRINT)


def test_saved_trouble_filters_assessed_source_pitches_to_the_half_open_unit(service, store):
    plan = make_plan()
    assessed = (
        NoteAssessment(Note(107.999, 108.0, 60, 0, 0), "missed"),
        NoteAssessment(Note(108.0, 109.0, 61, 0, 0), "wrong", played_pitch=99),
        NoteAssessment(Note(109.0, 110.0, 62, 0, 0), "correct"),
        NoteAssessment(Note(115.999, 116.0, 63, 0, 0), "late"),
        NoteAssessment(Note(116.0, 117.0, 64, 0, 0), "missed"),
    )
    service.record_saved_trouble(plan, fingerprint=FINGERPRINT, phrase_start=100.0,
        assessed_notes=assessed, start=8.0, end=16.0, errors=4)
    assert service.saved(plan, fingerprint=FINGERPRINT) == dict(
        resume_unit=SECOND, completed_units=[], trouble_units=[dict(
            **SECOND, failures=1, errors=4, pitches=[61, 63], resolved=False)],
        skip_status="active", skip_reason="")
    assert plan.streak == 0 and not plan.mastered
    assert store.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
        ("learner_stages",), ("learner_units",)]


@pytest.mark.parametrize("fingerprint, start, end", [("", 0.0, 8.0),
                                                   (FINGERPRINT, 0.0, 4.0),
                                                   (FINGERPRINT, 99.0, 100.0)])
def test_unbound_or_noncanonical_trouble_cannot_write_a_resume_cursor(
        service, store, fingerprint, start, end):
    service.record_saved_trouble(make_plan(), fingerprint=fingerprint, phrase_start=0.0,
        assessed_notes=(), start=start, end=end, errors=5)
    assert store.db.execute("SELECT count(*) FROM learner_stages").fetchone()[0] == 0
    assert store.db.execute("SELECT count(*) FROM learner_units").fetchone()[0] == 0


def test_store_validation_still_rejects_invalid_settled_errors_before_saving_resume(service, store):
    plan = make_plan()
    with pytest.raises(ValueError, match="positive number of settled errors"):
        service.record_saved_trouble(plan, fingerprint=FINGERPRINT, phrase_start=0.0,
            assessed_notes=(), start=0.0, end=8.0, errors=0)
    assert store.read(FINGERPRINT, plan.identity) == EMPTY
