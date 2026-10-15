import mido
import pytest

from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def test_metronome_preference_persists_and_validates(tmp_path):
    library = ScoreLibrary(tmp_path)
    assert library.public_settings()["metronome"] is True
    library.update(metronome=False)
    assert ScoreLibrary(tmp_path).public_settings()["metronome"] is False
    with pytest.raises(ValueError):
        library.update(metronome="no")


def test_midi_activity_reports_real_input_outside_graded_practice(tmp_path, monkeypatch):
    from piano_teacher import server
    monkeypatch.setattr(server.time, "monotonic", lambda: 100.0)
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        assert engine.state()["midi_input_count"] == 0
        engine._receive(mido.Message("note_on", note=64, velocity=90))
        state = engine.state()
        assert state["midi_input_count"] == 1
        assert state["midi_input_note"] == 64
        assert state["midi_input_age"] == 0.0
        assert engine.recorder is None
        engine._receive(mido.Message("note_off", note=64))
        engine._receive(mido.Message("note_on", note=64, velocity=0))
        assert engine.state()["midi_input_count"] == 1
    finally:
        engine.db.close()
