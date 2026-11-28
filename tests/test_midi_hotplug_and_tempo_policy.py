"""Regression checks for physical discovery and the authoritative tempo reducer."""
from dataclasses import replace

from piano_teacher.application.midi_connection import MidiConnection
from piano_teacher.application.practice_flow import FlowState, Outcome, Step, take_graded
from session_inputs import InputClock, InputPort


class Backend:
    def __init__(self):
        self.names = ["Midi Through:Midi Through Port-0 14:0"]
        self.opened = []

    def get_input_names(self):
        return self.names

    def open_input(self, name, callback):
        port = InputPort(callback)
        self.opened.append(name)
        return port


def test_discovery_without_preference_and_reconnect_with_renumbered_alsa_port():
    clock, backend = InputClock(), Backend()
    midi = MidiConnection(clock=clock, backend=backend)
    callback = lambda message: None
    assert midi.scan_due("")
    assert midi.restore_preferred(midi.scan().names, "", callback=callback) is None
    clock.at += midi.SCAN_SECONDS
    backend.names.append("Kawai CA49:Kawai CA49 MIDI 24:0")
    assert midi.scan_due("")
    assert midi.restore_preferred(midi.scan().names, "", callback=callback).connected
    previous = midi.device
    port = midi.port
    backend.names[-1] = "Kawai CA49:Kawai CA49 MIDI 28:0"
    assert midi.scan().lost
    with midi.disconnected():
        pass
    assert port.closed
    assert midi.restore_preferred(midi.scan().names, previous, callback=callback) is None
    clock.at += midi.RETRY_SECONDS
    assert midi.restore_preferred(midi.scan().names, previous, callback=callback).connected
    assert midi.device == backend.names[-1]
    with midi.selecting("", callback=callback):
        pass
    clock.at += 10
    assert not midi.scan_due("")
    assert midi.restore_preferred(midi.scan().names, "", callback=callback) is None


def test_repeated_failure_requires_two_consecutive_passes_on_revisited_tempo():
    state = FlowState("stage", False, Step.TEMPO, 60, 100)
    state = take_graded(state, passed=False, accuracy_percent=60).state
    slower = take_graded(state, passed=False, accuracy_percent=60)
    assert slower.outcome is Outcome.SLOWER
    state = replace(slower.state, bpm=60)
    first = take_graded(state, passed=True)
    assert first.outcome is Outcome.AGAIN and first.state.bpm == 60
    ignored = take_graded(first.state, passed=False, accuracy_percent=0)
    assert ignored.state == first.state
    failed = take_graded(ignored.state, passed=False, accuracy_percent=75)
    again = take_graded(failed.state, passed=True)
    assert again.outcome is Outcome.AGAIN and again.state.bpm == 60
    assert take_graded(again.state, passed=True).outcome is Outcome.FASTER


def test_single_failure_and_target_mastery_rules_unchanged():
    state = FlowState("stage", False, Step.TEMPO, 60, 100)
    failed = take_graded(state, passed=False, accuracy_percent=75)
    assert take_graded(failed.state, passed=True).outcome is Outcome.FASTER
    target = replace(state, bpm=100)
    first = take_graded(target, passed=True)
    assert first.outcome is Outcome.CLEAN_ONCE
    assert take_graded(first.state, passed=True).outcome is Outcome.STAGE_DONE
