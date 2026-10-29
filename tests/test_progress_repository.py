"""Persistence is owned by a repository, not PracticeEngine."""
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.progress_repository import ProgressRepository
from piano_teacher.server import PracticeEngine


def _plan():
    notes = (Note(0, 1, 60, 0, 0, "right"),
             Note(1, 2, 62, 0, 0, "right"))
    return LearningPlan(Piece("Repository", 100, notes,
                             (Phrase(1, 1, 2, 0, 8, notes),)))


def test_repository_persists_stage_tempo_and_mastery(tmp_path):
    path = tmp_path / "progress.db"
    first = ProgressRepository(path)
    plan = _plan()
    plan.set_bpm(70)
    plan.mastered["learn:1-2:right"] = 100
    first.save(plan, "first")
    first.close()
    second = ProgressRepository(path)
    restored = _plan()
    second.restore(restored, "first")
    assert restored.bpm == 70
    assert restored.mastered["learn:1-2:right"] == 100
    second.close()


def test_existing_original_mastery_and_tempo_survive_new_section_levels(tmp_path):
    from piano_teacher.musical_groups import MusicalGroup, MusicalGrouping
    from piano_teacher.grouped_variants import group_variants

    notes = tuple(Note(i*.25, (i+1)*.25, 60+i, 0, 0,
                       "right", f"id-{i}", voice="v") for i in range(16))
    phrase = Phrase(1, 1, 1, 0., 4., notes)
    empty = group_variants(phrase, "right", (), 8)
    assert empty
    grouping = tuple([("beam", tuple(frozenset({i}) for i in range(j,j+4)))
                      for j in range(0,16,4)] +
                     [("slur", tuple(frozenset({i}) for i in range(16)))])
    variants = group_variants(phrase, "right", grouping, 8)
    assert variants[-1][0] == "original"
    assert variants[-1][1] == tuple(range(16))
    assert any(level.startswith("section-") for level,_ in variants)
    # The original stage uses exactly the same note events and stable key
    # formulation, so existing mastery/tempo belongs to that same music.
    from piano_teacher.exercise_generator import ExerciseVariant
    from piano_teacher.learning import Exercise
    ex = Exercise("learn", phrase, "learn:1-1")
    old = ExerciseVariant("original", phrase, tuple(range(16)))
    new = ExerciseVariant("original", phrase, variants[-1][1])
    from piano_teacher.learning import LearningPlan
    assert LearningPlan._stage_key(ex, "right", old) == LearningPlan._stage_key(
        ex, "right", new)


def test_reset_scopes_all_tables_to_selected_fingerprint(tmp_path):
    repo = ProgressRepository(tmp_path / "progress.db")
    a = _plan()
    b = _plan()
    a.set_bpm(65)
    b.set_bpm(80)
    repo.save(a, "a")
    repo.save(b, "b")
    repo.reset_piece("a")
    assert repo.db.execute(
        "SELECT COUNT(*) FROM sessions WHERE fingerprint='a'").fetchone()[0] == 0
    assert repo.db.execute(
        "SELECT COUNT(*) FROM sessions WHERE fingerprint='b'").fetchone()[0] == 1
    remaining = _plan()
    repo.restore(remaining, "b")
    assert remaining.bpm == 80
    repo.close()


def test_engine_uses_repository_connection_and_preserves_legacy_db_api(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        assert engine.db is engine.progress.db
        assert engine.learner_store is engine.progress.learner_store
        engine.plan = _plan()
        engine.fingerprint = "engine"
        engine.plan.set_bpm(75)
        engine._save()
        other = _plan()
        engine.progress.restore(other, "engine")
        assert other.bpm == 75
    finally:
        engine.db.close()
