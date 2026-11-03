"""Switching installed lesson strategies must respect the new course's stages.

First selection transfers only the source location. An explicitly saved
strategy session can resume its own stage, but a foreign course's exercise
index, hand and variant are never reused as new stage selectors.
"""
import mido

from piano_teacher.application.strategy_session import restored_strategy_plan
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi


def _piece(tmp_path):
    path = tmp_path / "handoff.mid"
    midi = mido.MidiFile(type=1, ticks_per_beat=480)
    for name, root, first in (("Right Hand", 64, 0),
                              ("Left Hand", 43, 2)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        track.append(mido.MetaMessage("time_signature",
                                      numerator=4, denominator=4, time=0))
        events = []
        for bar in range(first, first + 2):
            for beat in (0, 1, 2, 3):
                start = (bar * 4 + beat) * 480
                pitch = root + beat % 3
                events += [(start, 1, pitch), (start+240, 0, pitch)]
            if bar == first:
                for extra in (root + 4, root + 7):
                    start = bar * 4 * 480
                    events += [(start, 1, extra), (start+240, 0, extra)]
        tick = 0
        for at, on, pitch in sorted(events, key=lambda entry: (entry[0], entry[1])):
            track.append(mido.Message("note_on" if on else "note_off",
                                      note=pitch, velocity=80 if on else 0,
                                      time=at-tick))
            tick = at
        track.append(mido.MetaMessage("end_of_track",time=4*4*480-tick))
        midi.tracks.append(track)
    midi.save(path)
    return load_midi(path)


class _Progress:
    def __init__(self, saved=False, target=None):
        self.saved = saved
        self.target = target
        self.restored = False
        self.restore_session = None

    def has_strategy_session(self, fingerprint, profile):
        return self.saved

    def restore(self, plan, fingerprint, *, restore_session=True):
        self.restored = True
        self.restore_session = restore_session
        if self.saved and restore_session and self.target is not None:
            plan.restore_location(**self.target)


def _settings(strategy):
    return {"exercise_strategy":strategy,"timing_strategy":"original-timing",
            "tempo_strategy":"constant-tempo"}


def test_switching_from_whole_piece_left_hand_to_right_only_passage(tmp_path):
    piece = _piece(tmp_path)
    prior = LearningPlan(piece, exercise_strategy="fukuda-midi")
    prior.set_hand("left")
    assert prior.hand == "left"
    assert prior.exercise.phrase.last_bar > 2
    fresh = _Progress()
    updated = restored_strategy_plan(
        prior, settings=_settings("coda-fukuda-midi"),
        progress=fresh, fingerprint="same-midi", warmup=False)
    assert fresh.restored and fresh.restore_session is False
    assert updated.lesson_generator.name == "coda-fukuda-midi"
    assert updated.exercise.kind == "learn"
    assert updated.exercise.phrase.first_bar == 1
    assert updated.exercise.phrase.last_bar <= 2
    assert updated.hand == "right"
    assert updated.variant_index == 0
    assert updated.active_stage is updated.stages[0]
    assert updated.piece is piece


def test_new_combined_selection_uses_its_own_first_transformation(tmp_path):
    piece = _piece(tmp_path)
    old = LearningPlan(piece, exercise_strategy="coda-midi")
    old.set_hand("right")
    old.variant_index = len(old.variants)-1
    old.bpm = 24
    result = restored_strategy_plan(
        old, settings=_settings("coda-fukuda-midi"),
        progress=_Progress(), fingerprint="same-midi", warmup=False)
    assert result.exercise.kind == "learn"
    assert result.hand == "right"
    assert result.variant_index == 0
    assert result.active_stage is result.stages[0]
    assert result.active_variant.level.startswith("fukuda-midi-")
    assert result.streak == 0
    assert result.piece is old.piece


def test_existing_saved_combined_selection_is_not_reset(tmp_path):
    piece = _piece(tmp_path)
    old = LearningPlan(piece, exercise_strategy="coda-midi")
    saved = _Progress(saved=True, target={
        "kind":"learn","first_bar":3,"last_bar":4,
        "hand":"left","level":"original"})
    result = restored_strategy_plan(
        old, settings=_settings("coda-fukuda-midi"),
        progress=saved, fingerprint="same-midi", warmup=False)
    assert saved.restore_session is True
    assert result.exercise.kind == "learn"
    assert result.active_phrase.first_bar == 3
    assert result.hand == "left"
    assert result.active_variant.level == "original"


def test_old_course_version_resumes_source_location_without_stale_bpm_or_credit(tmp_path):
    from piano_teacher.progress_repository import ProgressRepository
    piece = _piece(tmp_path)
    repo = ProgressRepository(tmp_path / "migration.sqlite")
    try:
        before = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
        before.bpm = min(before.target_bpm, before.start_bpm + 25)
        before.streak = 2
        old_bpm = before.bpm
        old_key = before.identity
        repo.save(before, "source-midi")
        # Model a saved course v2 that has been superseded by v3, including
        # its separate per-stage BPM record. No reset/delete is allowed.
        obsolete = old_key.replace("course:3:", "course:2:", 1)
        assert obsolete != old_key
        for table in ("sessions", "strategy_sessions"):
            repo.db.execute(
                f"UPDATE {table} SET step_key=? WHERE fingerprint=?",
                (obsolete, "source-midi"))
        repo.db.execute(
            "UPDATE stage_tempos SET stage_key=? WHERE fingerprint=?",
            (obsolete, "source-midi"))
        repo.db.execute("INSERT OR REPLACE INTO mastery VALUES (?,?,?)",
                        ("source-midi", obsolete, old_bpm))
        repo.db.commit()
        after = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
        repo.restore(after, "source-midi")
        assert after.active_phrase.first_bar == before.active_phrase.first_bar
        assert after.bpm == after.start_bpm
        assert after.bpm != old_bpm
        assert after.streak == 0
        assert after.identity not in after.stage_tempos
        assert after.identity not in after.mastered
        assert after.target_bpm == before.target_bpm
    finally:
        repo.close()


def test_exact_saved_course_keeps_its_independent_stage_bpm_and_streak(tmp_path):
    from piano_teacher.progress_repository import ProgressRepository
    piece = _piece(tmp_path)
    repo = ProgressRepository(tmp_path / "exact.sqlite")
    try:
        original = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
        original.bpm = min(original.target_bpm, original.start_bpm + 15)
        original.streak = 2
        repo.save(original, "source-midi")
        restored = LearningPlan(piece, exercise_strategy="coda-fukuda-midi")
        repo.restore(restored, "source-midi")
        assert restored.identity == original.identity
        assert restored.bpm == original.bpm
        assert restored.streak == original.streak
        assert restored.stage_tempos[restored.identity] == original.bpm
    finally:
        repo.close()
