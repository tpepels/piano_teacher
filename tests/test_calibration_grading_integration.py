"""Five-round calibration must change real MIDI callback and take assessment.

No simulated grading results: imported .mid notes, real PracticeEngine MIDI
callback, Recorder, timing policies and completed-take assessment are used.
Only the monotonic clock and connected MIDI device are deterministic.
"""
from __future__ import annotations

import mido
import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.library import ScoreLibrary
from piano_teacher.music import load_midi
from piano_teacher.server import PracticeEngine


DELAY = .18
PITCHES = (64, 65, 67, 69)


def _midi_source(path):
    """One real 4/4 MIDI measure: four separate half-beat notes."""
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    track.extend((
        mido.MetaMessage("track_name", name="Right Hand", time=0),
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
    ))
    for index, pitch in enumerate(PITCHES):
        track.append(mido.Message("note_on", note=pitch, velocity=90,
                                  time=0 if index == 0 else 240))
        track.append(mido.Message("note_off", note=pitch, velocity=0, time=240))
    track.append(mido.MetaMessage("end_of_track", time=240))
    midi.tracks.append(track)
    midi.save(path)
    piece = load_midi(path)
    assert len(piece.notes) == 4
    assert [n.pitch for n in piece.notes] == list(PITCHES)
    assert piece.bpm == 120
    assert piece.bar_boundaries == (0, 4) or piece.bar_boundaries == [0, 4]
    assert all(n.source_id.startswith("midi-t") for n in piece.notes)
    return piece


def _send(engine, now, timestamp, *, pitch, on):
    now[0] = timestamp
    engine._receive(mido.Message("note_on" if on else "note_off",
                                 note=pitch, velocity=90 if on else 0))


def _perform_real_practice(engine, piece, now, *, wrong_first_pitch=False):
    engine.plan = LearningPlan(
        piece, exercise_strategy="source-progression", consolidate=True)
    # A one-measure source-progression course has only a learn exercise.
    # Its terminal original stage still uses the complete imported score.
    engine.plan.index = len(engine.plan.exercises) - 1
    engine.plan.variant_index = len(engine.plan.variants) - 1
    engine.plan.set_bpm(120)
    assert engine.plan.hand in ("right", "both")
    assert [note.source_id for note in engine.plan.active_phrase.notes] == [
        note.source_id for note in piece.notes]

    engine.start(mode="practice")
    assert engine.running and engine.auto and not engine.preview_only
    run_at = engine.visual_transport.run_at
    observed_onsets = []
    observed_live = []
    for index, note in enumerate(engine.plan.active_phrase.notes):
        expected_onset = (note.start-engine.plan.active_phrase.start) * .5
        expected_release = (note.end-engine.plan.active_phrase.start) * .5
        pitch = note.pitch + 1 if wrong_first_pitch and index == 0 else note.pitch
        _send(engine, now, run_at + expected_onset + DELAY, pitch=pitch, on=True)
        observed_live.append(engine.live_events.after(0)[-1])
        observed_onsets.append(engine.recorder.presses[-1].onset)
        _send(engine, now, run_at + expected_release + DELAY, pitch=pitch, on=False)

    # Actual transport settlement and real grading after the authored bar.
    now[0] = run_at + 4 * .5 + .21
    engine._update()
    result = engine.pending_result
    assert result is not None, "The real practice completion must grade the take"
    assert [assessment.note.source_id for assessment in result.notes] == [
        note.source_id for note in piece.notes]
    return result, observed_live, observed_onsets


def test_measured_offset_changes_real_practice_grading_after_relaunch(
        tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    piece = _midi_source(tmp_path / "timing.mid")
    home = tmp_path / "app"

    engine = PracticeEngine(home, enable_midi=False)
    engine.midi.port = object()  # Connected device only, no hardware needed.
    try:
        # Exercise the real calibration command and the same callback that
        # later reaches the practice recorder. One bad round plus one bad tap.
        engine.control("calibration_start")
        cal = engine.midi_calibration
        assert cal.active and cal.rounds == 5
        for round_index in range(cal.rounds):
            for tap in range(cal.ticks):
                extra = .09 if round_index == 2 else 0.0
                if (round_index, tap) == (4, 3):
                    extra += .09
                at = (cal.start_at +
                      (cal.count_in + round_index * cal.ticks + tap) * cal.period
                      + DELAY + extra)
                _send(engine, now, at, pitch=72, on=True)
                _send(engine, now, at + .05, pitch=72, on=False)
        now[0] = cal.start_at + cal.total_beats * cal.period + .01
        result = cal.snapshot(now[0])["result"]
        assert result["reliable"] and result["estimate_ms"] == 180
        assert result["discarded_rounds"] == 1
        assert result["discarded_taps"] == 1
        assert engine.library.settings["midi_offset_ms"] == 0
        assert engine.recorder is None  # calibration did not grade anything

        # Negative control: identical physical delay WITHOUT Apply is late.
        before, raw_events, raw_onsets = _perform_real_practice(
            engine, piece, now)
        assert all(entry.status == "late" for entry in before.notes)
        assert not before.clean and not before.passed
        assert [event["status"] for event in raw_events] == ["late"] * 4
        assert raw_onsets == pytest.approx(
            [0.18, 0.68, 1.18, 1.68], abs=.001)

        engine.control("stop")
        engine.control("calibration_apply")
        assert engine.library.settings["midi_offset_ms"] == 180
        assert ScoreLibrary(home / "config").settings["midi_offset_ms"] == 180
    finally:
        engine.db.close()

    # Reopen the same app to ensure the correction is persisted AND read
    # by the live input callback, rather than only held by calibration state.
    restarted = PracticeEngine(home, enable_midi=False)
    restarted.midi.port = object()
    try:
        assert restarted.library.settings["midi_offset_ms"] == 180
        now[0] += 20
        after, corrected_events, corrected_onsets = _perform_real_practice(
            restarted, piece, now)
        assert after.clean and after.passed
        assert [entry.status for entry in after.notes] == ["correct"] * 4
        assert [event["status"] for event in corrected_events] == ["on_time"] * 4
        assert corrected_onsets == pytest.approx([0, .5, 1, 1.5], abs=.001)
    finally:
        restarted.db.close()


def test_calibration_cannot_hide_wrong_pitch_in_real_practice(
        tmp_path, monkeypatch):
    now = [100.]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    piece = _midi_source(tmp_path / "pitch.mid")
    engine = PracticeEngine(tmp_path / "engine", enable_midi=False)
    engine.midi.port = object()
    try:
        # Use the same persisted correction mechanism as Apply; only the
        # estimation procedure is isolated in the preceding integration test.
        engine.library.update(midi_offset_ms=180)
        result, _, _ = _perform_real_practice(
            engine, piece, now, wrong_first_pitch=True)
        assert not result.passed
        assert result.notes[0].status == "wrong"
        assert [entry.status for entry in result.notes[1:]] == ["correct"] * 3
    finally:
        engine.db.close()
