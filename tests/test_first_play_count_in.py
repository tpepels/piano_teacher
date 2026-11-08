"""One count-in bar and a short start (owner decision, 2026-11-08).

Owner: "There should always only be a single ichi ni .. countdown, never
more. Only the bar before the start of the exercise." and "the notes should
appear closer to the playhead, so the wait is about one bar."

The presentation lead the renderer reserves stays the graded deadline
(``run_at``); only the count-in no longer grows with it.
"""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_timing import lead_in_beats
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]
GODOT = shutil.which("godot") or shutil.which("godot4")


def piece(bpm=60):
    notes = (Note(0, 1, 60, 0, 0, 'right'), Note(2, 3, 64, 0, 0, 'right'),
             Note(4, 5, 65, 0, 0, 'right'), Note(6, 7, 67, 0, 0, 'right'))
    return Piece('Count-in exercise', bpm, notes, (Phrase(1, 2, 2, 0, 8, notes),))


@pytest.fixture
def engine(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, 'monotonic', lambda: now[0])
    e = PracticeEngine(tmp_path, enable_midi=False)
    e.plan = LearningPlan(piece())
    e.plan.bpm = 60
    e.fingerprint = "first-play-count-in"
    try:
        yield e, now
    finally:
        e.db.close()


def test_ready_state_publishes_the_one_bar_count_in_play_will_use(engine):
    e, now = engine
    published = e.state()["next_count_in_beats"]
    assert published == pytest.approx(4.0)  # 60 BPM, 4/4: one whole bar
    e.start(presentation_lead_seconds=published*60/e.plan.bpm)
    assert e.count_in_beats == pytest.approx(published)
    # The renderer's reserved lead is the graded deadline, exactly.
    assert e.visual_transport.run_at == pytest.approx(now[0] + 4.0)


def test_start_with_long_presentation_lead_keeps_one_bar_count_in(engine):
    e, now = engine
    e.start(presentation_lead_seconds=13.0)
    assert e.visual_transport.run_at == pytest.approx(now[0] + 13.0)
    assert e.count_in_beats == pytest.approx(lead_in_beats(4.0, 60))
    assert e.state()["count_in_beats"] == pytest.approx(4.0)
    assert e.state()["phase"] == "count_in"


def test_slow_tempo_count_in_is_capped_and_published(engine):
    e, now = engine
    e.plan.bpm = 31
    capped = lead_in_beats(4.0, 31)
    assert capped < 4.0
    assert e.state()["next_count_in_beats"] == pytest.approx(capped)
    e.start(presentation_lead_seconds=20.0)
    assert e.count_in_beats == pytest.approx(capped)
    assert e.visual_transport.run_at == pytest.approx(now[0] + 20.0)


def test_resume_with_long_presentation_lead_keeps_one_bar_count_in(engine):
    e, now = engine
    e.start(presentation_lead_seconds=4.0)
    now[0] = e.visual_transport.run_at + 1.5
    e.control("pause")
    now[0] += 30.0
    assert e.state()["next_count_in_beats"] == pytest.approx(4.0)
    e.control("resume", presentation_lead_seconds=11.0)
    assert e._resume_grading_after == pytest.approx(now[0] + 11.0)
    assert e.count_in_beats == pytest.approx(4.0)
    assert e.state()["count_in_beats"] == pytest.approx(4.0)


def test_resume_lead_of_one_count_in_bar_is_the_graded_deadline(engine):
    e, now = engine
    e.plan.bpm = 40
    e.start(presentation_lead_seconds=lead_in_beats(4.0, 40)*60/40)
    now[0] = e.visual_transport.run_at + 1.0
    e.control("pause")
    now[0] += 20.0
    count_in = e.state()["next_count_in_beats"]
    assert count_in == pytest.approx(lead_in_beats(4.0, 40))
    lead = count_in*60/40
    e.control("resume", presentation_lead_seconds=lead)
    # No hidden four-beat minimum on top of the renderer's reservation.
    assert e._resume_grading_after == pytest.approx(now[0] + lead)
    assert e.count_in_beats == pytest.approx(count_in)


def test_unplayed_count_in_resume_with_long_lead_keeps_one_bar(engine):
    e, now = engine
    e.start(presentation_lead_seconds=4.0)
    now[0] = e.visual_transport.run_at - 2.0
    e.control("pause")
    now[0] += 5.0
    e.control("resume", presentation_lead_seconds=12.0, reuse_pending_score=True)
    assert e.visual_transport.run_at == pytest.approx(now[0] + 12.0)
    assert e.count_in_beats == pytest.approx(4.0)


@pytest.mark.skipif(GODOT is None, reason="Godot 4 is not installed")
def test_first_play_places_opening_one_count_in_bar_ahead(tmp_path):
    from test_recovery_motion import make_midi_fixture

    make_midi_fixture(tmp_path, "chords", "both", bpm=60)
    env = os.environ.copy()
    env["XDG_DATA_HOME"] = str(tmp_path / "data")
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    result = subprocess.run(
        [GODOT, "--headless", "--path", str(ROOT / "godot"), "--script",
         str(ROOT / "tests/godot/first_play_count_in.gd"), "--", str(tmp_path)],
        capture_output=True, text=True, timeout=60, env=env)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "SCRIPT ERROR" not in output, output
    assert "FIRST_PLAY_COUNT_IN_FAILURES:0" in output, output
