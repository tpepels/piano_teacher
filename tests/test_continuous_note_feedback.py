"""The engine publishes note feedback continuously through one acknowledged log.

These run the real PracticeEngine, Recorder, live assessment, Verovio layout and
final grading. Only the monotonic clock is controlled. No state snapshot is
requested during playback: publication must not depend on UI polling.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine

PITCHES = (60, 62, 64, 65)


@pytest.fixture
def engine(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    notes = tuple(Note(float(i), float(i + 1), pitch, 0, 0, "right", f"n{i}")
                  for i, pitch in enumerate(PITCHES))
    piece = Piece("Continuous", 80, notes, (Phrase(1, 1, 1, 0, 4, notes),),
                  bar_boundaries=(0, 4))
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.plan = LearningPlan(piece, exercise_strategy="source-progression")
    engine.fingerprint = "continuous-fixture"
    engine.midi.port = SimpleNamespace(closed=False)
    engine.start()
    engine.engraving()  # the real source-note-v1 layout used for note identity
    assert engine.plan.bpm == 40 and engine.running and not engine.preview_only
    engine.now = now
    yield engine
    engine.db.close()


def _at(engine, offset):
    engine.now[0] = engine.visual_transport.run_at + offset
    engine.advance_clock()


def _key(engine, offset, pitch, down):
    engine.now[0] = engine.visual_transport.run_at + offset
    engine._receive(SimpleNamespace(type="note_on" if down else "note_off",
                                    note=pitch, velocity=80 if down else 0,
                                    channel=0))
    engine.advance_clock()


def _events(engine, kind=None):
    return [event for event in engine.feedback_events.pending()
            if kind is None or event["kind"] == kind]


def _assessed(engine):
    latest = {}
    for event in _events(engine, "assessment"):
        latest[event["source_id"]] = event
    return latest


def _perform(engine):
    """n0 clean, n1 omitted, n2 early AND released early, n3 released early."""
    spb = 1.5
    _key(engine, 0.0, 60, True)
    _key(engine, spb, 60, False)
    for tick in (1.7, 2.0, 2.3, 2.5):
        _at(engine, tick)
    _key(engine, 2 * spb - .45, 64, True)    # early beyond the 0.3 s onset tolerance
    _key(engine, 2 * spb - .25, 64, False)   # held 0.2 s of 1.5 s: early release
    _key(engine, 3 * spb, 65, True)
    _key(engine, 3 * spb + .3, 65, False)


def test_settled_and_missed_notes_publish_during_playback_without_polling(engine):
    spb = 1.5
    _key(engine, 0.0, 60, True)
    _key(engine, spb, 60, False)
    assert not _assessed(engine), "n0 cannot settle before its release grace"
    for tick in (1.7, 2.0, 2.3, 2.6):
        _at(engine, tick)
    published = _assessed(engine)
    assert published["n0"]["status"] == "correct"
    assert published["n0"]["dimensions"] == {
        "pitch": "correct", "onset": "on_time", "release": "on_time"}
    # n1 was never played; its miss is visible while the take is running.
    assert published["n1"]["status"] == "missed"
    assert published["n1"]["dimensions"]["pitch"] == "missed"
    assert engine.running and engine.pending_result is None
    # Further clock ticks do not republish unchanged grades.
    count = len(_events(engine, "assessment"))
    for tick in (2.7, 2.8, 2.9):
        _at(engine, tick)
    assert len(_events(engine, "assessment")) == count


def test_release_event_is_immediate_and_source_bound(engine):
    _key(engine, 4.5, 65, True)
    before = {event["source_id"] for event in _events(engine, "assessment")}
    _key(engine, 4.8, 65, False)
    release = _events(engine, "release")[-1]
    assert release["source_id"] == "n3" and release["release"] == "short"
    assert "n3" not in before and "n3" not in _assessed(engine), (
        "the early release is shown before n3 can settle")


def test_combined_onset_and_release_errors_keep_both_dimensions(engine):
    _perform(engine)
    for tick in (5.0, 5.5, 6.0, 6.2):
        _at(engine, tick)
    published = _assessed(engine)
    # Grading status is unchanged: onset error takes precedence in Python.
    assert published["n2"]["status"] == "early"
    assert published["n2"]["dimensions"] == {
        "pitch": "correct", "onset": "early", "release": "short"}
    assert published["n3"]["status"] == "short"
    assert published["n3"]["dimensions"]["release"] == "short"


def test_published_grades_equal_final_assessment_and_state_take(engine):
    _perform(engine)
    offset = 5.0
    while engine.running and offset < 12:
        _at(engine, offset)
        offset += .1
    assert engine.pending_result is not None or not engine.running
    final = {entry.note.source_id: entry.status
             for entry in engine.pending_result.notes}
    published = _assessed(engine)
    assert {key: event["status"] for key, event in published.items()} == final
    state = engine.state()
    state_take = (state["piece_fingerprint"], state["revision"], state["mode"])
    transports = {event["transport_id"] for event in _events(engine)}
    assert len(transports) == 1
    for event in _events(engine):
        assert (event["piece_fingerprint"], event["revision"], event["mode"]) == state_take
        assert event["graded"] is True
    # One sequence space, strictly increasing across all three event kinds.
    sequences = [event["sequence"] for event in _events(engine)]
    assert sequences == sorted(sequences) and len(set(sequences)) == len(sequences)
    assert {event["kind"] for event in _events(engine)} == {
        "attack", "release", "assessment"}


def test_preview_takes_publish_ungraded_identity_and_no_assessment(engine):
    engine.midi.port = None
    engine.start()
    assert engine.preview_only
    _key(engine, 0.0, 60, True)
    _key(engine, 1.5, 60, False)
    for tick in (1.7, 2.0, 2.6):
        _at(engine, tick)
    attacks = [event for event in _events(engine, "attack")
               if event["transport_id"] == engine.transport_id]
    assert attacks and all(event["graded"] is False for event in attacks)
    assert not [event for event in _events(engine, "assessment")
                if event["transport_id"] == engine.transport_id]


def test_held_legato_note_is_pending_within_tolerance_then_unreleased(engine):
    # n0 lasts 1.5 s; the grader's hold tolerance is 1.125 s at this tempo.
    _key(engine, 0.0, 60, True)
    for tick in (1.7, 2.0, 2.5):
        _at(engine, tick)
    held = _assessed(engine)["n0"]
    assert held["dimensions"] == {
        "pitch": "correct", "onset": "on_time", "release": None}, (
        "a key held within tolerance has no release verdict yet (shown as hit)")
    assert held["status"] == "short", "grading status is untouched"
    _at(engine, 2.8)  # beyond expected duration plus the tolerance
    held = _assessed(engine)["n0"]
    assert held["dimensions"]["release"] == "unreleased"
    assert held["status"] == "short"


def test_marks_do_not_outlive_a_graded_running_take(engine):
    _key(engine, 0.0, 60, True)
    _at(engine, 2.8)
    assert engine.live_assessment.latest_marks
    engine.running = False
    engine._publish_live_assessment()
    assert engine.live_assessment.latest_marks == []


def test_publication_failure_does_not_pause_the_take(engine, monkeypatch, caplog):
    def boom():
        raise TypeError("display failure")
    monkeypatch.setattr(engine, "_live_feedback", lambda elapsed: boom())
    engine.now[0] = engine.visual_transport.run_at + 1.0
    feedback = engine.feedback
    engine._update()
    assert not engine.visual_transport.paused and engine.feedback == feedback
    assert "Live assessment publication failed" in caplog.text
