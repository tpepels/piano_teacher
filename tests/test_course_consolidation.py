"""Courses shorten repetitive work without throwing away source material or progress."""
from collections import Counter
import sqlite3

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine


def course_piece(bars=24, *, difficult_bar=None, both=True):
    notes = []
    for bar in range(bars):
        if difficult_bar == bar + 1:
            for eighth in range(8):
                for pitch in (60, 64, 67):
                    start = bar * 4 + eighth / 2
                    notes.append(Note(start, start + .4, pitch, 0, 0, "right"))
        else:
            for beat in range(4):
                start = bar * 4 + beat
                notes.append(Note(start, start + .8, 60 + beat, 0, 0, "right"))
        if both:
            notes.append(Note(bar * 4, bar * 4 + 3.5, 48, 1, 0, "left"))
    notes.sort(key=lambda n: (n.start, n.pitch, n.hand))
    phrases = tuple(Phrase(i // 2 + 1, i + 1, min(i + 2, bars), i * 4, min(i + 2, bars) * 4,
                           tuple(n for n in notes if i * 4 <= n.start < min(i + 2, bars) * 4))
                    for i in range(0, bars, 2))
    return Piece("Course", 120, tuple(notes), phrases, bar_boundaries=tuple(i * 4 for i in range(bars + 1)))


def test_manageable_passages_are_grouped_and_source_notes_are_not_lost():
    piece = course_piece()
    plan = LearningPlan(piece)
    learn = [e for e in plan.exercises if e.kind == "learn"]
    assert [(e.phrase.first_bar, e.phrase.last_bar) for e in learn] == [(1, 8), (9, 16), (17, 24)]
    assert Counter(n for e in learn for n in e.phrase.notes) == Counter(piece.notes)
    assert len(plan.lesson_steps) < 20
    assert [step.hand for step in plan.lesson_steps[:3]] == ["right", "left", "both"]
    assert plan.exercises[-1].kind == "perform"
    assert [(e.phrase.first_bar, e.phrase.last_bar) for e in plan.exercises if e.kind == "connect"] == [(7, 10), (15, 18)]
    assert plan.exercises[-1].phrase.notes == piece.notes
    assert all(s.level == "original" for s in plan.lesson_steps if s.kind != "learn" or s.hand == "both")


def test_difficult_material_stays_in_two_bar_exercises_with_progressive_variants():
    plan = LearningPlan(course_piece(12, difficult_bar=5))
    difficult = next(e for e in plan.exercises if e.kind == "learn" and e.phrase.first_bar <= 5 <= e.phrase.last_bar)
    assert (difficult.phrase.first_bar, difficult.phrase.last_bar) == (5, 6)
    steps = [s for s in plan.lesson_steps if s.exercise_index == plan.exercises.index(difficult) and s.hand == "right"]
    assert [s.level for s in steps] == ["skeleton", "outline", "original"]


def test_single_hand_is_not_repeated_as_a_both_hand_lesson():
    plan = LearningPlan(course_piece(8, both=False))
    assert plan.hands == ("right",)
    assert [s.hand for s in plan.lesson_steps if s.kind == "learn"] == ["right"]


def test_selected_target_survives_hand_and_passage_changes():
    plan = LearningPlan(course_piece(16))
    plan.set_bpm(30)
    plan.set_hand("left")
    assert plan.target_bpm == 30 and plan.bpm <= 30
    plan.select(1)
    assert plan.target_bpm == 30 and plan.bpm <= 30


def test_consolidated_stage_still_needs_three_clean_target_speed_full_plays():
    plan = LearningPlan(course_piece(8))
    plan.set_bpm(80)
    identity = plan.identity
    count = len(plan.active_phrase.notes)
    for _ in range(2):
        plan.apply_result(correct=count, total=count)
        assert plan.identity == identity and not plan.mastered
    plan.apply_result(correct=count - 1, total=count)
    assert plan.streak == 0
    for _ in range(3):
        plan.apply_result(correct=count, total=count)
    assert plan.identity != identity and plan.mastered[identity] == 80
    assert plan.target_bpm == 80


def test_legacy_progress_maps_by_original_span_without_awarding_larger_mastery(tmp_path):
    # Legacy index 3 means learn bars 5-6, not new course exercise index 3.
    with sqlite3.connect(tmp_path / "progress.db") as db:
        db.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER, variant_index INTEGER)")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", ("legacy", 3, "left", 30, 2, 70, 0))
        db.execute("CREATE TABLE mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY (fingerprint, exercise))")
        db.execute("INSERT INTO mastery VALUES (?,?,?)", ("legacy", "learn:1-2:right:original", 70))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(course_piece(16))
        engine.fingerprint = "legacy"
        engine._restore()
        plan = engine.plan
        assert (plan.exercise.phrase.first_bar, plan.exercise.phrase.last_bar) == (1, 8)
        assert plan.hand == "left" and plan.target_bpm == 70 and plan.bpm == 30
        assert plan.streak == 0
        assert plan.lesson_steps_mastered == 0
        engine._save()
        assert engine.db.execute("SELECT exercise FROM mastery WHERE fingerprint=?", ("legacy",)).fetchall() == [("learn:1-2:right:original",)]
        row = engine.db.execute("SELECT route_version,step_key FROM sessions WHERE fingerprint=?", ("legacy",)).fetchone()
        assert row == (plan.route_version, plan.identity)
    finally:
        engine.db.close()


def test_new_course_resumes_exact_stage_and_streak(tmp_path):
    first = PracticeEngine(tmp_path, enable_midi=False)
    first.plan = LearningPlan(course_piece(16))
    first.plan.select(1)
    first.plan.set_bpm(75)
    first.plan.streak = 2
    first.fingerprint = "modern"
    first._save()
    expected = first.plan.identity
    first.db.close()
    second = PracticeEngine(tmp_path, enable_midi=False)
    try:
        second.plan = LearningPlan(course_piece(16))
        second.fingerprint = "modern"
        second._restore()
        assert second.plan.identity == expected
        assert second.plan.streak == 2 and second.plan.target_bpm == 75
    finally:
        second.db.close()


def test_preview_of_consolidated_material_cannot_award_mastery(tmp_path, monkeypatch):
    from piano_teacher import server
    now = [10.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(course_piece(8))
    try:
        engine.start()
        assert engine.state()["preview_only"]
        now[0] = engine.run_at + engine.state()["duration"] + 1
        assert not engine.state()["running"]
        assert not engine.plan.mastered and engine.plan.streak == 0
    finally:
        engine.db.close()


def test_consolidation_never_crosses_gaps_or_meter_changes():
    piece = course_piece(16)
    piece = Piece(piece.title, piece.bpm, piece.notes,
                  (piece.phrases[0], *piece.phrases[2:]),
                  bar_boundaries=piece.bar_boundaries, time_signatures=((0, 4, 4), (32, 3, 4)))
    plan = LearningPlan(piece)
    spans = [(e.phrase.first_bar, e.phrase.last_bar) for e in plan.exercises if e.kind == "learn"]
    assert spans == [(1, 2), (5, 8), (9, 16)]
    assert not any(e.kind == "connect" and e.phrase.first_bar <= 3 <= e.phrase.last_bar for e in plan.exercises)


def test_changed_required_notes_do_not_reuse_a_saved_clean_streak(tmp_path):
    first = PracticeEngine(tmp_path, enable_midi=False)
    original = course_piece(8)
    first.plan = LearningPlan(original)
    first.plan.streak = 2
    first.fingerprint = "same-fingerprint-test"
    first._save()
    first.db.close()
    changed = tuple(Note(n.start, n.end, n.pitch + (1 if i == 1 else 0), n.track, n.channel, n.hand)
                    for i, n in enumerate(original.notes))
    ph = Phrase(1, 1, 8, 0, 32, changed)
    second = PracticeEngine(tmp_path, enable_midi=False)
    try:
        second.plan = LearningPlan(Piece(original.title, original.bpm, changed, (ph,)))
        second.fingerprint = "same-fingerprint-test"
        second._restore()
        assert second.plan.streak == 0
    finally:
        second.db.close()


def test_tiny_outline_increment_does_not_require_three_more_full_repetitions():
    notes = tuple(Note(i, i + .8, 60 + i, 0, 0, "right") for i in range(8)) + (
        Note(0, .8, 72, 0, 0, "right"), Note(0, .8, 76, 0, 0, "right"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    plan = LearningPlan(Piece("Small chord detail", 100, notes, (phrase,)))
    assert [v.level for v in plan.variants] == ["skeleton", "original"]
    assert set(plan.variants[-1].notes) == set(notes)


def test_complete_song_includes_initial_rests_and_sustained_final_measures():
    notes = (Note(8, 9, 60, 0, 0, "right"), Note(16, 30, 64, 0, 0, "right"))
    piece = Piece("Long ending", 100, notes,
                  (Phrase(1, 3, 4, 8, 16, notes[:1]), Phrase(2, 5, 6, 16, 24, notes[1:])),
                  bar_boundaries=tuple(range(0, 33, 4)))
    plan = LearningPlan(piece)
    final = plan.exercises[-1]
    assert final.kind == "perform"
    assert (final.phrase.first_bar, final.phrase.last_bar, final.phrase.start, final.phrase.end) == (1, 8, 0, 32)
    assert final.phrase.notes == piece.notes
    plan.select(len(plan.exercises) - 1)
    assert plan.active_variant.level == "original" and plan.active_phrase.end >= max(n.end for n in notes)


def test_legacy_full_song_streak_is_reset_when_sustained_ending_is_restored(tmp_path):
    notes = (Note(0, 1, 60, 0, 0, "right"), Note(8, 24, 64, 0, 0, "right"))
    piece = Piece("Held end", 100, notes,
                  (Phrase(1, 1, 2, 0, 8, notes[:1]), Phrase(2, 3, 4, 8, 16, notes[1:])),
                  bar_boundaries=tuple(range(0, 25, 4)))
    with sqlite3.connect(tmp_path / "progress.db") as db:
        db.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER, variant_index INTEGER)")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", ("ending", 3, "both", 100, 2, 100, 0))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece)
        engine.fingerprint = "ending"
        engine._restore()
        assert engine.plan.exercise.kind == "perform"
        assert engine.plan.active_phrase.end == 24
        assert engine.plan.streak == 0
    finally:
        engine.db.close()


def test_legacy_identical_stage_keeps_real_mastery_and_clean_streak(tmp_path):
    piece = course_piece(2)
    with sqlite3.connect(tmp_path / "progress.db") as db:
        db.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER, target_bpm INTEGER, variant_index INTEGER)")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?)", ("exact", 0, "right", 90, 2, 90, 0))
        db.execute("CREATE TABLE mastery (fingerprint TEXT, exercise TEXT, bpm INTEGER, PRIMARY KEY (fingerprint, exercise))")
        db.execute("INSERT INTO mastery VALUES (?,?,?)", ("exact", "learn:1-2:left:original", 90))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(piece)
        engine.fingerprint = "exact"
        engine._restore()
        assert engine.plan.hand == "right" and engine.plan.streak == 2
        assert engine.plan.lesson_steps_mastered == 1
        assert engine.plan.mastered["learn:1-2:left:original"] == 90
    finally:
        engine.db.close()


def test_bad_legacy_hand_does_not_crash_course_restoration(tmp_path):
    with sqlite3.connect(tmp_path / "progress.db") as db:
        db.execute("CREATE TABLE sessions (fingerprint TEXT PRIMARY KEY, exercise INTEGER, hand TEXT, bpm INTEGER, streak INTEGER)")
        db.execute("INSERT INTO sessions VALUES (?,?,?,?,?)", ("bad-hand", 0, "unavailable", 40, 2))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(course_piece(8))
        engine.fingerprint = "bad-hand"
        engine._restore()
        assert engine.plan.hand in engine.plan.hands
        assert engine.plan.streak == 0
    finally:
        engine.db.close()
