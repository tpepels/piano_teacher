"""Opening source measures uses the real lesson course and musical grid."""
from __future__ import annotations

import mido
import pytest
from piano_teacher.server import PracticeEngine


def _file(path):
    midi = mido.MidiFile(ticks_per_beat=480)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    meta.append(mido.MetaMessage("set_tempo", tempo=600000, time=0))
    midi.tracks.append(meta)
    # Deliberately include silent measure 1. Measures 2-10 have a low and
    # a high attack, so all user-selectable positions are source-based.
    for hand, pitch in (("Right Hand", 67), ("Left Hand", 48)):
        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=hand, time=0))
        absolute = 0
        for bar in range(2, 11):
            start = (bar - 1) * 4 * 480
            track.append(mido.Message("note_on", note=pitch, velocity=75, time=start - absolute))
            absolute = start
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=480))
            absolute += 480
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi.tracks.append(track)
    midi.save(path)
    return path


def _engine(tmp_path):
    engine = PracticeEngine(tmp_path / "data", enable_midi=False)
    engine.load(str(_file(tmp_path / "long_piece.mid")))
    return engine


def test_open_at_source_measure_starts_guided_notes_in_selected_bar(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.control("open_at", bar=7, mode="learn")
        state = engine.state()
        assert state["mode"] == "learn"
        assert state["piece_last_bar"] >= 10
        assert engine.display_phrase().first_bar == 7
        assert engine.plan.active_phrase.first_bar <= 7 <= engine.plan.active_phrase.last_bar
        assert engine.guided_range[0] == engine.plan.piece.bar_boundaries[6] - engine.plan.active_phrase.start
    finally:
        engine.db.close()


def test_practice_starts_exact_selected_bar_only_after_start(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.control("open_at", bar=6, mode="practice")
        state = engine.state()
        assert state["mode"] == "practice"
        assert state["phase"] == "ready"
        assert not state["running"]
        assert engine.awaiting_score_revision is None
        assert state["selected_start_bar"] == 6
        assert state["hand_stages"]  # Feedback includes the visible curriculum path.
        engine.start()
        state = engine.state()
        assert state["phase"] == "count_in"
        assert state["selected_start_bar"] == 6
        assert engine.play_from_beat > 0
        assert state["preview_only"]  # No connected Kawai is required.
    finally:
        engine.db.close()


@pytest.mark.parametrize("bar,mode", [
    (0, "practice"), (999, "learn"), (1.2, "learn"),
    (True, "practice"), ("5", "learn"), (5, "listen")
])
def test_invalid_location_is_rejected_without_changing_course(tmp_path, bar, mode):
    engine = _engine(tmp_path)
    try:
        before = (engine.plan.index, engine.plan.identity, engine.score_revision)
        with pytest.raises(ValueError):
            engine.control("open_at", bar=bar, mode=mode)
        assert (engine.plan.index, engine.plan.identity, engine.score_revision) == before
    finally:
        engine.db.close()


def test_silent_first_measure_moves_to_first_playable_course_section(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.control("open_at", bar=1, mode="learn")
        assert engine.display_phrase().first_bar == 2
        assert engine.state()["selected_start_bar"] == 2
    finally:
        engine.db.close()


def test_manual_passage_change_resets_the_opening_measure(tmp_path):
    engine = _engine(tmp_path)
    try:
        engine.control("open_at", bar=6, mode="practice")
        assert engine.open_from_beat > 0
        engine.control("previous")
        assert engine.open_from_beat == 0
        assert engine.state()["selected_start_bar"] == engine.plan.active_phrase.first_bar
    finally:
        engine.db.close()
