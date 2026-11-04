"""Accepted timed takes earn mastery; preparation and partial takes do not.

These finite MIDI performances use the real importer, MIDI callback, grader,
settlement, LearningPlan and SQLite writes. Only the monotonic clock and the
physical MIDI connection are supplied by the test.
"""
from __future__ import annotations

import hashlib
import json

import mido
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi
from piano_teacher.practice import Assessment
from piano_teacher.progress_repository import ProgressRepository
from piano_teacher.server import PracticeEngine


@pytest.fixture
def practice_factory(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: clock[0])
    engines = []

    def create(attacks=((0, (60,)), (1, (62,)), (2, (64,)), (3, (65,)))):
        source = tmp_path / f"acceptance-{len(engines)}.mid"
        midi = mido.MidiFile(ticks_per_beat=480)
        track = mido.MidiTrack()
        midi.tracks.append(track)
        track.append(mido.MetaMessage("track_name", name="Right hand"))
        track.append(mido.MetaMessage("set_tempo", tempo=1_000_000))
        track.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
        events = []
        for beat, pitches in attacks:
            for pitch in pitches:
                events.extend(((int(beat * 480), True, pitch),
                               (int((beat + .25) * 480), False, pitch)))
        previous = 0
        for tick, down, pitch in sorted(events):
            track.append(mido.Message("note_on" if down else "note_off",
                                      note=pitch, velocity=80 if down else 0,
                                      time=tick - previous))
            previous = tick
        track.append(mido.MetaMessage("end_of_track", time=1920 - previous))
        midi.save(source)

        engine = PracticeEngine(tmp_path / f"app-{len(engines)}", enable_midi=False)
        engines.append(engine)
        engine.plan = LearningPlan(load_midi(source), exercise_strategy="source-progression")
        engine.plan.variant_index = len(engine.plan.variants) - 1
        engine.plan.set_bpm(60)
        engine.fingerprint = hashlib.sha256(source.read_bytes()).hexdigest()
        engine.set_preferences(mistake_response_strategy="finish-then-review")
        engine.midi.port = object()
        engine.midi.device = "Deterministic test piano"
        assert engine.plan.active_variant.level == "original"
        assert engine.plan.hand == "right"
        return engine, clock

    yield create
    for engine in engines:
        engine.listen.cancel()
        engine.db.close()


def _play(engine, clock, *, late=(), wrong=(), missed=(), extra=False, from_beat=0.0):
    """Replay actual keys at 60 BPM, then settle and commit a completed take."""
    engine.start(from_beat=from_beat)
    origin = engine.visual_transport.run_at
    phrase = engine.plan.active_phrase
    events = []
    for index, note in enumerate(phrase.notes):
        beat = note.start - phrase.start
        if beat < from_beat or index in missed:
            continue
        pitch = 90 if index in wrong else note.pitch
        delay = .25 if index in late else 0.0
        events.extend(((beat - from_beat + delay, True, pitch),
                       (note.end - phrase.start - from_beat + delay, False, pitch)))
    if extra:
        events.extend(((3.5 - from_beat, True, 94), (3.75 - from_beat, False, 94)))
    for seconds, down, pitch in sorted(events):
        clock[0] = origin + seconds
        engine._receive(mido.Message("note_on" if down else "note_off",
                                     note=pitch, velocity=80 if down else 0))
    clock[0] = origin + phrase.end - phrase.start - from_beat + .21
    engine._update()
    result = engine.pending_result
    engine._commit_pending()
    return result


def _accepted_warning(engine, clock):
    result = _play(engine, clock, late=(1,))
    assert isinstance(result, Assessment)
    assert result.passed and not result.clean
    assert "Accepted pass" in engine.next_action
    return result


def test_three_full_target_tempo_warning_takes_award_durable_mastery(practice_factory):
    # Replacing passed with clean in the commit path must fail this contract.
    engine, clock = practice_factory()
    stage = engine.plan.identity
    for expected_streak in (1, 2):
        _accepted_warning(engine, clock)
        assert engine.plan.streak == expected_streak
        assert not engine.plan.mastered
        assert engine.db.execute("SELECT streak FROM strategy_sessions").fetchone() == (
            expected_streak,)
    _accepted_warning(engine, clock)

    assert engine.plan.mastered[stage] == 60
    assert engine.db.execute("SELECT exercise,bpm FROM mastery").fetchall() == [(stage, 60)]
    history = engine.db.execute(
        "SELECT bpm,statuses_json,extra_notes FROM learning_assessments ORDER BY id").fetchall()
    assert [(bpm, json.loads(statuses), extras) for bpm, statuses, extras in history] == [
        (60.0, ["correct", "late", "correct", "correct"], 0),
    ] * 3
    restored = LearningPlan(engine.plan.piece, exercise_strategy="source-progression")
    reopened = ProgressRepository(engine._data_dir / "progress.db")
    try:
        reopened.restore(restored, engine.fingerprint)
    finally:
        reopened.close()
    assert restored.mastered[stage] == 60


@pytest.mark.parametrize("performance,warning_attacks,error_status,extras", [
    ({"late": (0, 1)}, 2, "late", 0),
    ({"late": (0, 1, 2)}, 3, "late", 0),
    ({"wrong": (1,)}, 0, "wrong", 0),
    ({"missed": (1,)}, 0, "missed", 0),
    ({"extra": True}, 0, None, 1),
], ids=("exactly-half-amber", "majority-amber", "wrong-pitch", "missed-note", "extra-note"))
def test_rejected_full_take_breaks_accepted_streak(
        practice_factory, performance, warning_attacks, error_status, extras):
    # Allowing half amber, ignoring red/extra notes, or keeping a failed
    # streak would let the rejected third take or its successor award mastery.
    engine, clock = practice_factory()
    stage = engine.plan.identity
    _accepted_warning(engine, clock)
    _accepted_warning(engine, clock)
    assert engine.plan.streak == 2

    result = _play(engine, clock, **performance)
    assert isinstance(result, Assessment)
    assert not result.passed and not result.clean
    assert result.yellow_attacks == warning_attacks
    assert result.extra_notes == extras
    if error_status:
        assert any(note.status == error_status for note in result.notes)
    assert engine.plan.streak == 0
    assert engine.plan.identity == stage and not engine.plan.mastered
    assert engine.db.execute("SELECT streak FROM strategy_sessions").fetchone() == (0,)
    assert engine.db.execute("SELECT count(*) FROM mastery").fetchone() == (0,)

    _accepted_warning(engine, clock)
    assert engine.plan.streak == 1 and not engine.plan.mastered


@pytest.mark.parametrize("attacks,late,passed,total,amber,precise", [
    (((0, (60, 64, 67)), (1, (62,)), (2, (65,)), (3, (69,))),
     (0, 1, 2), True, 4, 1, 3),
    (((0, (60, 64, 67)), (1, (62,))), (3,), False, 2, 1, 3),
], ids=("warning-chord-shares-one-attack", "correct-chord-cannot-dilute-half-amber"))
def test_chord_noteheads_use_distinct_onsets_for_acceptance(
        practice_factory, attacks, late, passed, total, amber, precise):
    # Counting printed heads in either numerator or denominator reverses
    # these deliberately different chord-heavy outcomes.
    engine, clock = practice_factory(attacks)
    result = _play(engine, clock, late=late)
    assert isinstance(result, Assessment)
    assert result.total_attacks == total and result.yellow_attacks == amber
    assert result.correct == precise
    assert result.passed is passed and not result.clean
    assert engine.plan.streak == (1 if passed else 0)
    assert not engine.plan.mastered


def test_clean_partial_retry_cannot_supply_third_full_mastery_pass(practice_factory):
    # Routing a partial completion through full settlement must fail here.
    engine, clock = practice_factory()
    _accepted_warning(engine, clock)
    _accepted_warning(engine, clock)
    stage = engine.plan.identity

    assert _play(engine, clock, from_beat=2.0) is None
    assert engine.performance_summary["correct"] == 2
    assert engine.performance_summary["total"] == 2
    assert engine.plan.identity == stage and engine.plan.streak == 2
    assert engine.pending_result is None and not engine.plan.mastered
    assert engine.db.execute("SELECT count(*) FROM learning_assessments").fetchone() == (3,)
    assert engine.db.execute(
        "SELECT count(*) FROM learning_assessments WHERE mastery_eligible=1").fetchone() == (2,)
    assert engine.db.execute(
        "SELECT clean,passed,mastery_eligible FROM learning_assessments ORDER BY id DESC LIMIT 1"
    ).fetchone() == (1, 1, 0)
    assert engine.db.execute("SELECT count(*) FROM mastery").fetchone() == (0,)


def test_guided_completion_cannot_supply_third_full_mastery_pass(practice_factory):
    # Giving untimed guided preparation accepted-take credit must fail here.
    engine, clock = practice_factory()
    _accepted_warning(engine, clock)
    _accepted_warning(engine, clock)
    stage = engine.plan.identity
    engine.control("learn")
    engine.geometry()
    engine.control("score_ready", revision=engine.score_revision)
    for pitch in (60, 62, 64, 65):
        clock[0] += 5
        engine._receive(mido.Message("note_on", note=pitch, velocity=80))
        engine._receive(mido.Message("note_off", note=pitch, velocity=0))

    state = engine.state()
    assert state["phase"] == "guided_complete"
    assert state["teaching"]["completed"]
    assert not state["teaching"]["mastery_eligible"]
    assert len(engine.learner_store.read(engine.fingerprint, stage)["completed_units"]) == 1
    assert engine.plan.identity == stage and engine.plan.streak == 2
    assert engine.pending_result is None and not engine.plan.mastered
    assert engine.db.execute("SELECT count(*) FROM learning_assessments").fetchone() == (2,)
    assert engine.db.execute("SELECT count(*) FROM mastery").fetchone() == (0,)
