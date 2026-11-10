"""Actual MIDI grading drives durable recovery and returns to the full source."""
import hashlib
import json
import sqlite3

import mido
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.server import PracticeEngine


@pytest.fixture
def runtime(tmp_path, monkeypatch, request):
    now = [100.]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    source = tmp_path / "adaptive.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.extend([mido.MetaMessage("track_name", name="Right hand"),
                  mido.MetaMessage("set_tempo", tempo=1_000_000),
                  mido.MetaMessage("time_signature", numerator=4, denominator=4)])
    events = []
    for i in range(16):
        end = 9 if i == 3 and getattr(request, "param", None) == "sustained" else i+.25
        events.extend([(i*480, True, 60+i % 12), (int(end*480), False, 60+i % 12)])
    previous = 0
    for tick, down, pitch in sorted(events):
        track.append(mido.Message("note_on" if down else "note_off", note=pitch,
                                  velocity=80 if down else 0, time=tick-previous))
        previous = tick
    track.append(mido.MetaMessage("end_of_track", time=16*480-previous))
    midi.save(source)
    engine = PracticeEngine(tmp_path / "app", enable_midi=False)
    engine.plan = LearningPlan(load_midi(source), exercise_strategy="source-progression")
    engine.plan.select(len(engine.plan.exercises)-1)
    engine.plan.variant_index = len(engine.plan.variants)-1
    engine.plan.set_bpm(60)
    engine.fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
    engine.midi.port = object()
    engine.midi.device = "Replay piano"
    engine.set_preferences(mistake_response_strategy="evidence-adaptive")
    yield engine, now, source
    engine.listen.cancel()
    engine.db.close()


def take(engine, now, *, wrong=(4., 5., 6.), settle=True):
    if not engine.running:
        engine.start(from_beat=engine.open_from_beat)
    phrase = engine.plan.active_phrase
    start = engine.visual_transport.play_from_beat
    end = engine.review_end_beat or phrase.end-phrase.start
    origin, seconds = engine.visual_transport.run_at, 60/engine.plan.bpm
    events = []
    for note in phrase.notes:
        beat = note.start-phrase.start
        if start <= beat < end:
            pitch = 100 if beat in wrong else note.pitch
            events.extend([((beat-start)*seconds, True, pitch),
                           ((note.end-phrase.start-start)*seconds, False, pitch)])
    for offset, down, pitch in sorted(events):
        now[0] = origin+offset
        engine._receive(mido.Message("note_on" if down else "note_off", note=pitch, velocity=80 if down else 0))
    now[0] = origin+(end-start)*seconds+.21
    engine._update()
    # Settle on the existing rewind/rest deadline, without a second clock.
    if engine.pending_result is not None and settle:
        now[0] = max(now[0], engine.visual_transport.next_at+.01)
        engine._advance_pending_feedback(now[0])
    elif settle and engine.mode != "learn" and engine.visual_transport.next_at:
        now[0] = engine.visual_transport.next_at+.01
        engine._update()
    return json.loads(engine.db.execute("SELECT data_json FROM learning_decisions ORDER BY rowid DESC LIMIT 1").fetchone()[0])


def test_error_pattern_isolates_slows_guides_and_reintegrates_without_partial_mastery(runtime):
    engine, now, source = runtime
    original = source.read_bytes()
    initial_stage = engine.plan.identity
    actions = [take(engine, now)["selected"]["action"] for _ in range(6)]
    # 127c94ee: a second failure at the slower setting repeats in place; no
    # guided wait is entered automatically during perpetual score flow.
    assert actions == ["repeat", "isolate", "repeat", "slow", "repeat", "repeat"]
    assert engine.mode != "learn" and engine.plan.identity == initial_stage
    assert engine.plan.bpm == 54
    assert engine.plan.streak == 0 and not engine.plan.mastered
    recovered = []
    for _ in range(6):
        if engine.visual_transport.play_from_beat == 0 and engine.review_end_beat is None and engine.plan.bpm >= 60:
            break
        recovered.append(take(engine, now, wrong=())["selected"]["action"])
    assert "reintegrate" in recovered
    assert engine.visual_transport.play_from_beat == 0 and engine.review_end_beat is None
    assert engine.plan.bpm == 60
    assert not engine.plan.mastered
    assert source.read_bytes() == original
    assert engine.db.execute("SELECT COUNT(*) FROM learning_outcomes WHERE attempt_id IS NOT NULL").fetchone()[0] >= 6
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments WHERE mastery_eligible=1 AND passed=1").fetchone()[0] == 0
    stats = engine.learning_statistics(engine.fingerprint)
    assert stats["interventions"]["decisions"] >= 8
    assert stats["assessments"]["strict_clean"] >= 2


def test_first_rolling_failure_continues_without_sealing_or_rewinding(runtime):
    engine, now, _ = runtime
    engine.start()
    attempt = engine.measurement.attempt_id
    now[0] = engine.visual_transport.run_at+8.01
    engine._update()
    assert engine.running and engine.measurement.attempt_id == attempt
    assert engine.measurement.sealed is None
    assert engine.db.execute("SELECT COUNT(*) FROM learning_decisions").fetchone()[0] == 0
    assert engine.plan.bpm == 60


def test_manual_restart_discards_the_previous_selected_retry_before_clean_take(runtime):
    engine, now, _ = runtime
    take(engine, now)
    take(engine, now, settle=False)
    assert engine._policy_retry[1].action == "isolate"
    engine.control("restart")
    assert engine._policy_retry is None
    engine.start(from_beat=0.)
    take(engine, now, wrong=())
    assert engine.review_end_beat is None
    assert engine.visual_transport.play_from_beat == 0.
    assert engine.plan.streak == 1


def test_focused_decision_write_failure_pauses_and_retries_same_attempt_once(runtime):
    engine, now, _ = runtime
    take(engine, now)
    take(engine, now)
    attempt = engine.measurement.attempt_id
    assert engine.review_end_beat == 8
    engine.db.execute("""CREATE TRIGGER reject_focused_decision BEFORE INSERT ON learning_decisions
        BEGIN SELECT RAISE(ABORT, 'decision unavailable'); END""")
    with pytest.raises(sqlite3.DatabaseError, match="decision unavailable"):
        take(engine, now)
    assert engine.visual_transport.paused and engine.measurement.attempt_id == attempt
    assert engine.db.execute("SELECT state FROM learning_attempts WHERE attempt_id=?", (attempt,)).fetchone() == ("open",)
    captured = len(engine.recorder.presses)
    engine._receive(mido.Message("note_on", note=99, velocity=80))
    assert len(engine.recorder.presses) == captured
    engine.db.execute("DROP TRIGGER reject_focused_decision")
    engine.control("resume")
    engine._update()
    assert engine.db.execute("SELECT COUNT(*) FROM learning_assessments WHERE attempt_id=?", (attempt,)).fetchone() == (1,)
    assert engine.db.execute("SELECT COUNT(*) FROM learning_decisions WHERE attempt_id=?", (attempt,)).fetchone() == (1,)


@pytest.mark.parametrize("runtime", ["sustained"], indirect=True)
def test_isolated_source_range_expands_across_held_note_boundaries(runtime):
    engine, now, source = runtime
    original = source.read_bytes()
    take(engine, now)
    decision = take(engine, now)
    assert decision["selected"]["action"] == "isolate"
    assert decision["selected"]["restart_beat"] == 0.
    assert decision["selected"]["end_beat"] == 12.
    assert engine.visual_transport.play_from_beat == 0. and engine.review_end_beat == 12.
    assert source.read_bytes() == original
