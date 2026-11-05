"""Physical MIDI endpoint shortcuts: capture, priority, and early consumption."""
import mido
import pytest

from piano_teacher.application.midi_key_shortcuts import MidiKeyShortcuts
from piano_teacher.library import ScoreLibrary
from piano_teacher.server import PracticeEngine


def pressed(pitch):
    return mido.Message("note_on", note=pitch, velocity=90)


def released(pitch):
    return mido.Message("note_off", note=pitch)


def test_keyboard_endpoints_are_learned_in_order_and_saved_by_device(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.midi.port = object()
    engine.midi.device = "88-key stage piano"
    try:
        engine.control("midi_range_start")
        assert engine.state()["midi_key_range"]["step"] == "lowest"
        engine._receive(pressed(21))
        assert engine.state()["midi_key_range"]["captured_low"] == 21
        assert engine.state()["midi_key_range"]["step"] == "highest"
        engine._receive(released(21))
        engine._receive(pressed(20))  # Invalid high key must not overwrite low.
        assert engine.state()["midi_key_range"]["step"] == "highest"
        engine._receive(released(20))
        engine._receive(pressed(108))
        status = engine.state()["midi_key_range"]
        assert status == {
            "device": "88-key stage piano", "configured": True,
            "low": 21, "high": 108, "active": False,
            "step": "", "captured_low": None,
        }
        assert engine.state()["midi_input_count"] == 0
        persisted = ScoreLibrary(tmp_path / "config").public_settings()
        assert persisted["midi_key_ranges"]["88-key stage piano"] == [21, 108]
    finally:
        engine.midi.port = None
        engine.close()


def test_end_keys_toggle_pause_and_resume_or_restart_without_entering_midi_activity(tmp_path):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    engine.midi.port = object()
    engine.midi.device = "portable piano"
    engine.midi_key_shortcuts.configure({"portable piano": [36, 96]})
    commands = []
    engine.control = lambda action, **kwargs: commands.append(action)
    try:
        engine.running = True
        engine._receive(pressed(36))
        engine._receive(pressed(36))  # Held repeat is still only one command.
        engine._receive(released(36))
        engine.visual_transport.paused = True
        engine._receive(pressed(36))
        engine._receive(released(36))
        engine._receive(pressed(96))
        engine._receive(released(96))
        assert commands == ["pause", "resume", "restart"]
        assert engine.midi.input_count == 0
        assert engine.recorder is None
        assert engine.live_input.held == {}
    finally:
        engine.midi.port = None
        engine.close()


def test_any_score_pitch_overrides_shortcut_even_if_far_ahead():
    shortcuts = MidiKeyShortcuts({"piano": [21, 108]})
    for pitch in (21, 108):
        # Only one attack several bars ahead is enough to disable the
        # shortcut for the entire current exercise, not just this beat.
        decision = shortcuts.accept(pressed(pitch), device="piano",
            exercise_pitches=frozenset({pitch, 60, 64}),
            can_pause=True, paused=False)
        assert not decision.consumed and not decision.action
        off = shortcuts.accept(released(pitch), device="piano",
            exercise_pitches=frozenset({pitch, 60, 64}),
            can_pause=True, paused=False)
        assert not off.consumed
    # An unsolicited release must not be consumed either.
    assert not shortcuts.accept(released(21),device="piano",
        exercise_pitches=frozenset(),can_pause=True,paused=False).consumed


def test_no_shortcut_without_learned_range_and_cancel_works():
    shortcuts = MidiKeyShortcuts()
    assert not shortcuts.accept(pressed(21),device="unknown",
        exercise_pitches=frozenset(),can_pause=True,paused=False).consumed
    shortcuts.begin_capture("unknown")
    assert shortcuts.accept(pressed(21),device="unknown",
        exercise_pitches=frozenset(),can_pause=False,paused=False).consumed
    shortcuts.cancel_capture()
    assert not shortcuts.status("unknown")["configured"]


def test_range_validation_rejects_invalid_or_reversed_midi_values(tmp_path):
    library = ScoreLibrary(tmp_path)
    for invalid in ({"piano":[108,21]}, {"piano":[21,21]},
                    {"piano":[0,128]}, {"piano":[True,100]},
                    {"piano":"C2-C7"}):
        with pytest.raises(ValueError):
            library.update(midi_key_ranges=invalid)
    assert library.public_settings()["midi_key_ranges"] == {}
