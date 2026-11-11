"""F2/C2: grading after Pause/Resume equals grading of the same unpaused take.

Rule (R1 F2): the graded musical timeline stands still from the Pause moment
until grading resumes after Resume's reading lead. A key held across the pause
is measured on that timeline (the paused interval and the lead are excluded).
A key released while paused, or during the ungraded resume lead, counts as
released at the pause moment. The Recorder (settled grade) and the live input
view (immediate release verdict) read one shared clock, so they never disagree
about a note whose evidence did not change.
"""
from types import SimpleNamespace

import pytest

from piano_teacher import server
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece, source_note_id
from piano_teacher.practice import evaluate, note_dimensions
from piano_teacher.server import PracticeEngine

# 40 BPM: 1.5 s per beat.
NOTES = (
    Note(0, 2, 60, 0, 0, "right"),  # A1: held across the pause, released after it
    Note(0, 1, 62, 0, 0, "right"),  # B1: released while paused, exactly at its end
    Note(0, 8, 64, 0, 0, "right"),  # D:  released during the resume lead (short)
    Note(0, 8, 67, 0, 0, "right"),  # G:  released while paused, well before its end
    Note(2, 3, 65, 0, 0, "right"),  # E:  played wholly after Resume
    Note(3, 4, 62, 0, 0, "right"),  # B2: same pitch as B1 (FIFO cascade)
    Note(4, 5, 60, 0, 0, "right"),  # A2: same pitch as A1
    Note(5, 6, 64, 0, 0, "right"),  # D2: same pitch as D
    Note(5, 6, 67, 0, 0, "right"),  # G2: same pitch as G
)
PHRASE = Phrase(1, 1, 2, 0, 8, NOTES)
PAUSE_AT = 1.5  # musical seconds (beat 1)
PAUSE_SECONDS = 10.0
READING_LEAD = 7.5

# (musical seconds, pitch, on). Releases at PAUSE_AT happen in the pause or
# lead in the paused take; the unpaused reference plays them at PAUSE_AT.
PERFORMANCE = [
    (0.0, 60, True), (0.0, 62, True), (0.0, 64, True), (0.0, 67, True),
    (3.0, 60, False), (3.0, 65, True), (4.5, 65, False),
    (4.5, 62, True), (6.0, 62, False),
    (6.0, 60, True), (7.5, 60, False),
    (7.5, 64, True), (7.5, 67, True), (9.0, 64, False), (9.0, 67, False),
]
DURING_PAUSE = [(62, False), (67, False)]
DURING_LEAD = [(64, False)]


@pytest.fixture
def make_engine(tmp_path, monkeypatch):
    t = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: t[0])
    # Grade the source chords as written (no simplified learning variant).
    monkeypatch.setattr(LearningPlan, "active_phrase", property(lambda _plan: PHRASE))
    engines = []

    def build(name):
        e = PracticeEngine(tmp_path / name, enable_midi=False)
        e.plan = LearningPlan(Piece("Pause grading", 40, NOTES, (PHRASE,)))
        e.fingerprint = f"pause-release-{name}"
        e.midi.port = object()  # a connected keyboard: a graded take
        published = []
        original = e.feedback_events.publish

        def capture(event, *a, **k):
            published.append(event)
            return original(event, *a, **k)

        e.feedback_events.publish = capture
        engines.append(e)
        return e, published

    try:
        yield build, t
    finally:
        for e in engines:
            e.db.close()


def send(e, pitch, on):
    e._receive(SimpleNamespace(type="note_on" if on else "note_off",
                               note=pitch, velocity=90 if on else 0))


def settled(e):
    graded = evaluate(PHRASE, "both", 40, list(e.recorder.presses))
    return [note_dimensions(entry) for entry in graded.notes]


def live_releases(published):
    return {event["source_id"]: event["release"] for event in published
            if event.get("kind") == "release"}


def play_unpaused(build, t):
    e, published = build("reference")
    e.start()
    run_at = e.visual_transport.run_at
    for at, pitch, on in sorted(
            PERFORMANCE + [(PAUSE_AT, p, on) for p, on in DURING_PAUSE + DURING_LEAD],
            key=lambda item: (item[0], item[2])):
        t[0] = run_at + at
        send(e, pitch, on)
    return e, published


def play_paused(build, t, lead=READING_LEAD):
    e, published = build(f"paused-{lead}")
    e.start()
    run_at = e.visual_transport.run_at
    before = [ev for ev in PERFORMANCE if ev[0] < PAUSE_AT]
    after = [ev for ev in PERFORMANCE if ev[0] >= PAUSE_AT]
    for at, pitch, on in before:
        t[0] = run_at + at
        send(e, pitch, on)
    t[0] = run_at + PAUSE_AT
    e.control("pause")
    for pitch, on in DURING_PAUSE:
        t[0] += 1.0
        send(e, pitch, on)
    t[0] = run_at + PAUSE_AT + PAUSE_SECONDS
    e.control("resume", presentation_lead_seconds=lead)
    # A renderer's reading lead, or the direct-MIDI count-in bar.
    assert e._resume_grading_after == pytest.approx(t[0] + (lead or 6.0))
    for pitch, on in DURING_LEAD:
        t[0] += 2.0
        send(e, pitch, on)
    resumed = e.visual_transport.run_at
    for at, pitch, on in sorted(after, key=lambda item: (item[0], item[2])):
        t[0] = resumed + at
        assert t[0] >= e._resume_grading_after
        send(e, pitch, on)
    return e, published


LEADS = pytest.mark.parametrize("lead", (READING_LEAD, 0.0))


@LEADS
def test_settled_grade_after_pause_equals_unpaused_take(make_engine, lead):
    build, t = make_engine
    reference, _ = play_unpaused(build, t)
    paused, _ = play_paused(build, t, lead)
    expected = settled(reference)
    assert settled(paused) == expected
    # The rule's concrete grades: releases in the pause/lead count at the
    # pause moment; a key held across the pause excludes the paused time.
    releases = [dims["release"] for dims in expected]
    assert releases == ["on_time", "on_time", "short", "short",
                        "on_time", "on_time", "on_time", "on_time", "on_time"]
    by_pitch = {}
    for press in paused.recorder.presses:
        by_pitch.setdefault(press.pitch, []).append((press.onset, press.release))
    assert by_pitch[62] == [pytest.approx((0.0, PAUSE_AT)), pytest.approx((4.5, 6.0))]
    assert by_pitch[64][0] == pytest.approx((0.0, PAUSE_AT))
    assert by_pitch[60][0] == pytest.approx((0.0, 3.0))


@LEADS
def test_live_release_verdict_never_contradicts_settled_grade_after_pause(make_engine, lead):
    build, t = make_engine
    paused, published = play_paused(build, t, lead)
    live = live_releases(published)
    # A1 (held across the pause), D (released in the lead) and every note
    # played after Resume received an immediate release verdict.
    assert len(live) >= 6
    graded = evaluate(PHRASE, "both", 40, list(paused.recorder.presses))
    for entry in graded.notes:
        source = source_note_id(entry.note, NOTES.index(entry.note))
        if source in live:
            assert live[source] == note_dimensions(entry)["release"], source
    reference_build = live_releases(play_unpaused(build, t)[1])
    for source, verdict in live.items():
        assert reference_build.get(source) == verdict, source
