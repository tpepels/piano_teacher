"""Player-facing note judgments use the same recorded take live and at finish."""
from dataclasses import replace

import mido
import pytest

from piano_teacher.application.midi_ingress import MidiIngress, MidiInputFacts
from piano_teacher.exercise_contracts import TempoMap, TempoSegment
from piano_teacher.feedback_events import FeedbackEventLog
from piano_teacher.live_feedback import live_assessment
from piano_teacher.live_input_view import LiveInputView
from piano_teacher.music import Note, Phrase
from piano_teacher.practice import Recorder, evaluate
from piano_teacher.timed_assessment import assess_timed_window


def note(source, pitch=60, start=0, end=1, hand="right"):
    return Note(start, end, pitch, 0, 0, hand, source)


def phrase(*notes, start=0, end=4):
    return Phrase(1, 1, 1, start, end, tuple(notes))


class NoteTake:
    """Feed already admitted musical timestamps to production MIDI consumers."""

    def __init__(self, source, *, bpm=60, hand="right", from_beat=0, tempo=None):
        self.facts = MidiInputFacts(
            fingerprint="piece-a", score_revision=3, stage_key="window-1:right",
            phrase=source, hand=hand, bpm=bpm, mode="practice", running=True,
            paused=False, from_beat=from_beat, run_at=100,
            transport_id=7, tempo_map=tempo, can_pause=True)
        self.identity = {"piece_fingerprint": "piece-a", "revision": 3,
                         "transport_id": 7, "mode": "practice", "graded": True,
                         "release_advisory": True}
        self.recorder = Recorder()
        self.events = FeedbackEventLog()
        self.live = LiveInputView()
        self.ingress = MidiIngress(None, None, None, self.live, None, self.events)

    def receive(self, pitch, at, *, down=True, velocity=None):
        message = mido.Message("note_on" if down else "note_off", note=pitch,
                               velocity=(80 if down else 0) if velocity is None else velocity)
        self.ingress.deliver(
            message, facts=self.facts, received_at=100+at, corrected_at=100+at,
            musical_at=at, recorder=self.recorder, teaching=None,
            feedback_take=self.identity)

    def preview(self, at):
        return live_assessment(
            self.facts.phrase, self.facts.hand, self.facts.bpm,
            self.recorder.presses, from_beat=self.facts.from_beat,
            elapsed_seconds=at, tempo=self.facts.tempo_map)

    def finish(self):
        if self.facts.tempo_map is not None:
            return assess_timed_window(
                self.facts.phrase, self.facts.hand, self.facts.tempo_map,
                self.recorder.presses, from_beat=self.facts.from_beat)
        return evaluate(self.facts.phrase, self.facts.hand, self.facts.bpm,
                        self.recorder.presses)


@pytest.mark.parametrize("bpm,tolerance", [(40, .375), (120, .150), (240, .150)])
@pytest.mark.parametrize("direction", [-1, 1], ids=["early", "late"])
def test_onsets_accept_150ms_or_a_local_sixteenth(bpm, tolerance, direction):
    # Late assignment has an exclusive 200 ms cap, even at slow tempo.
    from piano_teacher.lesson_settings import SETTINGS
    limit = tolerance if direction < 0 else min(tolerance, SETTINGS.grading_max_late_attack_seconds)
    for drift, accepted in [(limit-.001, True), (limit+.001, False)]:
        take = NoteTake(phrase(note("target", start=2, end=3)), bpm=bpm)
        onset = 2*60/bpm + direction*drift
        take.receive(60, onset)
        take.receive(60, onset+60/bpm, down=False)
        result = take.finish()
        entry = result.notes[0]
        assert result.flow_passed is accepted
        assert entry.observation.onset_tolerance == pytest.approx(tolerance)
        outside_match = direction > 0 and drift >= SETTINGS.grading_max_late_attack_seconds
        assert entry.observation.timing_error == (
            None if accepted or outside_match else "early" if direction < 0 else "late")
        if outside_match:
            assert entry.status == "missed" and entry.observation.actual_onset is None
        live = take.preview(max(onset, 2*60/bpm))
        assert [(n.note.source_id, n.observation.timing_error) for n in live.notes] == [
            ("target", entry.observation.timing_error)]


@pytest.mark.parametrize("bpm,tolerance", [(40, .375), (120, .150)])
def test_first_attack_can_arrive_early_and_count_in_keys_earn_no_credit(bpm, tolerance):
    accepted = NoteTake(phrase(note("first")), bpm=bpm)
    accepted.receive(60, -tolerance+.001)
    assert accepted.finish().flow_passed
    event = accepted.events.after(0)["events"][0]
    assert (event["status"], event["source_id"]) == ("on_time", "first")
    assert {key: event[key] for key in accepted.identity} == accepted.identity

    # Just outside the tolerance the press still belongs to the first note:
    # it is graded early and the take fails.
    early = NoteTake(phrase(note("first")), bpm=bpm)
    early.receive(60, -tolerance-.001)
    assert early.recorder.presses
    result = early.finish()
    assert not result.flow_passed
    assert [entry.status for entry in result.notes] == ["early"]

    # Further into the count-in it is no part of the take and earns nothing.
    from piano_teacher.grading_tolerance import match_window
    count_in = NoteTake(phrase(note("first")), bpm=bpm)
    count_in.receive(60, -match_window(60/bpm)-.001)
    assert not count_in.recorder.presses
    assert not count_in.finish().flow_passed
    # Direct delivery of an unadmitted attack creates no graded event.
    # The full dispatch path separately emits neutral warm-up ink.
    assert not count_in.events.after(0)["events"]


@pytest.mark.parametrize("release,status", [(.1, "short"), (2, "long"), (None, "long")])
def test_release_precision_is_recorded_but_does_not_fail_practice_flow(release, status):
    take = NoteTake(phrase(note("held", end=2)), bpm=120)
    take.receive(60, 0)
    if release is not None:
        take.receive(60, release, down=False)
    result = take.finish()
    entry = result.notes[0]
    assert result.flow_passed and result.clean and result.passed
    assert entry.status == "correct"
    assert entry.observation.actual_release == release
    assert entry.observation.unreleased is (release is None)
    assert entry.observation.hold_error == (None if release is None else status)
    strict = evaluate(take.facts.phrase, take.facts.hand, take.facts.bpm,
                      take.recorder.presses, grade_note_holds=True)
    assert strict.notes[0].status == status and not strict.flow_passed
    releases = [e for e in take.events.after(0)["events"] if e["kind"] == "release"]
    if release is None:
        assert not releases
        assert entry.observation.release_residual is None
        assert entry.observation.duration_residual is None
    else:
        assert [(e["source_id"], e["release"]) for e in releases] == [("held", status)]


def test_omitted_repeated_note_cannot_steal_the_next_attack_live_or_at_finish():
    take = NoteTake(phrase(note("first", end=.25),
                           note("second", start=.25, end=.5)))
    take.receive(60, .25)
    assert take.events.after(0)["events"][0]["source_id"] == "second"
    live = take.preview(.25)
    assert [(n.note.source_id, n.observation.actual_onset) for n in live.notes] == [
        ("first", None), ("second", .25)]
    take.receive(60, .5, down=False)
    result = take.finish()
    assert [(n.note.source_id, n.status) for n in result.notes] == [
        ("first", "missed"), ("second", "correct")]
    assert not result.flow_passed


def test_overlapping_repeated_keys_keep_their_actual_fifo_releases():
    take = NoteTake(phrase(note("first", end=.5),
                           note("second", start=.25, end=.75)))
    for at, down in [(0, True), (.25, True), (.5, False), (.75, False)]:
        take.receive(60, at, down=down)
    result = take.finish()
    assert result.flow_passed
    assert [(n.note.source_id, n.observation.actual_onset, n.observation.actual_release)
            for n in result.notes] == [("first", 0, .5), ("second", .25, .75)]
    assert all(n.observation.ambiguous_pairing for n in result.notes)
    releases = [e for e in take.events.after(0)["events"] if e["kind"] == "release"]
    assert [e["source_id"] for e in releases] == ["first", "second"]


def test_chord_wrong_keys_preserve_exact_pitch_credit_and_actual_pitch_ghosts():
    take = NoteTake(phrase(note("c", 60), note("e", 64), note("g", 67)))
    for pitch, at in [(61, 0), (64, .01), (68, .03)]:
        take.receive(pitch, at)
    attacks = take.events.after(0)["events"]
    assert [(e["pitch"], e["source_id"], e["reference_source_id"]) for e in attacks] == [
        (61, "", "c"), (64, "e", ""), (68, "", "g")]
    live = take.preview(.03)
    final = take.finish()
    assert [(n.note.source_id, n.observation.actual_pitch) for n in live.notes] == [
        ("c", 61), ("e", 64), ("g", 68)]
    assert [(n.note.source_id, n.observation.actual_pitch) for n in final.notes] == [
        ("c", 61), ("e", 64), ("g", 68)]
    assert not final.flow_passed and final.extra_notes == 0


def test_future_heads_wait_and_a_miss_appears_only_after_the_matching_window():
    take = NoteTake(phrase(note("now", 60), note("future", 64, 4, 5), end=8))
    take.receive(61, 0)
    assert [(n.note.source_id, n.status) for n in take.preview(0).notes] == [("now", "wrong")]
    assert "future" not in {n.note.source_id for n in take.preview(4).notes}
    assert [(n.note.source_id, n.status) for n in take.preview(5).notes] == [
        ("now", "wrong"), ("future", "missed")]
    assert [(n.note.source_id, n.status) for n in take.finish().notes] == [
        ("now", "wrong"), ("future", "missed")]


@pytest.mark.parametrize("input_notes,status,extras", [
    ([], "missed", 0),
    ([(61, 0)], "wrong", 0),
    ([(60, 0), (70, 1)], "correct", 1),
])
def test_missing_wrong_and_extra_keys_each_fail_the_take(input_notes, status, extras):
    take = NoteTake(phrase(note("target")))
    for pitch, at in input_notes:
        take.receive(pitch, at)
    result = take.finish()
    assert not result.flow_passed
    assert result.notes[0].status == status and result.extra_notes == extras
    if extras:
        extra = take.events.after(0)["events"][-1]
        assert (extra["pitch"], extra["status"], extra["source_id"],
                extra["reference_source_id"]) == (70, "unexpected", "", "")


def test_source_release_beyond_the_window_barline_is_not_truncated():
    take = NoteTake(phrase(note("sustain", start=4, end=7), start=4, end=6), bpm=120)
    take.receive(60, 0)
    take.receive(60, 1.6, down=False)
    result = take.finish()
    observation = result.notes[0].observation
    assert result.flow_passed
    assert observation.expected_release == 1.5
    assert observation.actual_release == 1.6
    assert observation.release_residual == pytest.approx(.1)
    release = take.events.after(0)["events"][-1]
    assert (release["source_id"], release["held_seconds"], release["expected_seconds"]) == (
        "sustain", 1.6, 1.5)


def test_velocity_zero_note_on_is_a_release_of_the_same_source_press():
    take = NoteTake(phrase(note("target")))
    take.receive(60, 0)
    take.receive(60, 1, velocity=0)
    assert take.finish().flow_passed
    observation = take.finish().notes[0].observation
    assert (observation.actual_onset, observation.actual_release) == (0, 1)
    events = take.events.after(0)["events"]
    assert [(e["kind"], e["source_id"]) for e in events] == [
        ("attack", "target"), ("release", "target")]
    assert not take.live.held


def test_local_tempo_uses_the_authored_clock_for_live_and_final_observations():
    source = phrase(note("crossing", start=9, end=11),
                    note("slow", 62, 10, 12), start=8, end=12)
    tempo = TempoMap("shaped", (TempoSegment(0, 2, 120), TempoSegment(2, 4, 60)))
    take = NoteTake(source, bpm=120, from_beat=1, tempo=tempo)
    take.receive(60, .1)
    take.receive(62, .8)
    live = take.preview(.8)
    assert [(n.note.source_id, n.observation.timing_error) for n in live.notes] == [
        ("crossing", None), ("slow", None)]
    assert live.notes[1].status == "missed"
    take.receive(62, 1, down=False)
    take.receive(60, 1.6, down=False)
    result = take.finish()
    assert not result.flow_passed
    crossing, slow = [n.observation for n in result.notes]
    assert (crossing.expected_onset, crossing.expected_release, crossing.onset_tolerance) == (0, 1.5, .15)
    assert (slow.expected_onset, slow.expected_release, slow.onset_tolerance) == (.5, 2.5, .25)
    assert slow.actual_onset is None and slow.actual_release is None
    assert result.notes[1].status == "missed"


def test_listen_keys_are_heard_without_recording_or_performance_credit():
    take = NoteTake(phrase(note("target")))
    take.facts = replace(take.facts, mode="listen")
    take.identity = {**take.identity, "mode": "listen", "graded": False}
    take.receive(60, 0)
    take.receive(60, .5, down=False)
    assert not take.recorder.presses
    event = take.events.after(0)["events"][0]
    assert (event["status"], event["source_id"], event["graded"]) == ("heard", "", False)
