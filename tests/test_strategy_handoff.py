"""Saved progress resumes a course safely across course-version changes.

(Switching between strategies was removed with the other strategies; only
the default adaptive Coda + Fukuda course is selectable.)
"""
import mido

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
