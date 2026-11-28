"""Real pieces from the owner's library, played through the whole engine.

Owner request 2026-11-25: no breaks, error messages or interruptions on real
music, and no way to fool the grading with wrong notes, key clusters,
playing in the count-in or holding keys down. The fixtures are public-domain
works (MIDI and MusicXML, with pickups, chords, ties and 3/8). Set
PIANO_TEACHER_LIBRARY to a music folder to run the same checks on every
piece in it.
"""
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent/"fixtures"/"pieces"
FORMATS = {".mid", ".midi", ".mxl", ".musicxml", ".xml"}


def _pieces():
    found = sorted(FIXTURES.iterdir())
    library = os.environ.get("PIANO_TEACHER_LIBRARY")
    if library:
        found += sorted(p for p in Path(library).expanduser().iterdir()
                        if p.suffix.lower() in FORMATS)
    return found


PIECES = _pieces()
IDS = [p.stem[:40] for p in PIECES]
# A few contrasting pieces for the more expensive cheating checks.
SAMPLE = [FIXTURES/name for name in (
    "bach-invention-1.midi", "fur-elise.mxl", "gymnopedie-1.midi", "traumerei.mxl")]
SAMPLE_IDS = [p.stem for p in SAMPLE]


def open_piece(practice_session, source):
    session = practice_session(source=source.resolve())
    state = session.snapshot()
    assert state["playback_timeline"]["state"] != "failed", state["playback_timeline"]
    return session


def tempo(session):
    session.finish_listen()
    session.finish_free()
    state = session.ready_score()
    assert state["mode"] == "practice" and state["running"], state
    assert state["flow"]["step"] == "tempo"
    session.ask("score.bundle")
    return state


def notes(session):
    return session.ask("score.bundle")["model"]["notes"]


def perform(session, state, events):
    """Send (seconds after the downbeat, pitch, on) and finish the take."""
    start = state["playback_timeline"]["current"]["deadline_ms"]/1000
    for after, pitch, on in sorted(events, key=lambda e: (e[0], not e[2])):
        session.clock.at = max(session.clock.at, start+after)
        session.engine.midi.port.send(pitch, on)
    source = session.ask("score.bundle")["model"]
    floor, beat = state["play_from_beat"], 60/state["bpm"]
    sounding = source["practice_timeline"]["sounding_duration_beats"]
    session.clock.at = max(session.clock.at, start+(sounding-floor)*beat+.001)
    for _ in range(5):
        session.tick(.02)
    return session.snapshot()


def score_events(session, state, *, pitch=lambda n: [n["midi_pitch"]], shift=0.0, held=.9):
    floor, beat = state["play_from_beat"], 60/state["bpm"]
    events = []
    for note in notes(session):
        if note["onset_beats"] < floor:
            continue   # resumed mid-window: earlier notes are not in this take
        at = (note["onset_beats"]-floor)*beat+shift
        for p in pitch(note):
            events += [(at, p, True), (at+note["duration_beats"]*beat*held, p, False)]
    return events


def graded(session, transport):
    return [e["status"] for e in session.ask("feedback.events")["events"]
            if e.get("final") and e.get("transport_id") == transport]


def assert_failed_and_repeated(before, after):
    assert after["running"] and after["transport_id"] == before["transport_id"]+1, after["feedback"]
    assert after["bpm"] == before["bpm"]
    # Zero-credit takes preserve the previous streak; a recorded failure
    # breaks it. Neither may increase mastery or streak.
    assert after["streak"] in (0,before["streak"])
    assert after["flow"]["message_kind"] == "again"
    assert after["lesson_steps_mastered"] == before["lesson_steps_mastered"]


def assert_follows_directly(session, before, after, source=None):
    """The next take's first note comes after the rest to the barline and one
    count-in bar: never a longer pause. Barlines are the piece's own (a
    window may hold a pickup or a change of meter)."""
    timeline = session.ask("score.bundle")["model"]["practice_timeline"]
    floor = before["play_from_beat"]
    sounding = timeline["sounding_duration_beats"]
    if source is not None:
        from piano_teacher.importing.pieces import import_piece
        bars = import_piece(source).bar_boundaries
        start = bars[before["first_bar"]-1]
        to_barline = next(b for b in bars if b >= start+sounding-1e-6)-start
    else:
        numerator, denominator = timeline["gap"]["meter"]
        bar = numerator*4/denominator
        to_barline = -(-sounding//bar)*bar
    count_in = after["playback_timeline"]["current"]["count_in_beats"]
    allowed = (to_barline-floor+count_in)*60/min(before["bpm"], after["bpm"])
    gap = (after["playback_timeline"]["current"]["deadline_ms"]
           - before["playback_timeline"]["current"]["deadline_ms"])/1000
    assert gap <= allowed+.05, (gap, allowed, before["bpm"], after["bpm"])


# --- Every piece opens and its first window runs without a break ---------

@pytest.mark.parametrize("source", PIECES, ids=IDS)
def test_a_real_piece_opens_and_practises_without_a_break(practice_session, source):
    session = open_piece(practice_session, source)
    state = tempo(session)
    assert notes(session), "the opening window has notes to play"
    clean = perform(session, state, score_events(session, state))
    assert clean["running"] and clean["transport_id"] == state["transport_id"]+1
    assert graded(session, state["transport_id"]) == ["correct"]*len(notes(session))
    if state["bpm"] == state["target_bpm"]:
        assert clean["bpm"] == state["bpm"] and clean["streak"] == 1
    else:
        assert clean["bpm"] > state["bpm"] and clean["flow"]["message_kind"] == "faster"
    assert_follows_directly(session, state, clean)
    wrong = perform(session, clean, score_events(session, clean,
        pitch=lambda n: [n["midi_pitch"]+1]))
    assert_failed_and_repeated(clean, wrong)
    assert wrong["playback_timeline"]["state"] != "failed"


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_a_real_window_is_mastered_with_every_take_following_directly(practice_session, source):
    session = open_piece(practice_session, source)
    state = tempo(session)
    first_window = (state["first_bar"], state["last_bar"], state["hand"])
    for _ in range(12):
        after = perform(session, state, score_events(session, state))
        if after["lesson_steps_mastered"] > state["lesson_steps_mastered"]:
            break
        assert after["running"] and after["streak"] >= state["streak"], after["feedback"]
        assert_follows_directly(session, state, after)
        state = after
    else:
        raise AssertionError("Clean takes never mastered the window")
    assert after["bpm"] == after["target_bpm"] or after["mode"] == "listen"
    if after["flow"]["step"] == "section_choice":
        assert (after["first_bar"], after["last_bar"], after["hand"]) == first_window
        after = session.command("section_next")
    assert (after["first_bar"], after["last_bar"], after["hand"]) != first_window
    assert after["mode"] == "listen" and after["playback_timeline"]["state"] != "failed"


# --- It cannot be fooled in Tempo -----------------------------------------

def _cluster(n):
    return [n["midi_pitch"]+d for d in (-2, -1, 0, 1, 2)]


CHEATS = {
    # A one-bar-early take, played entirely inside the count-in.
    "the whole window a bar early": lambda s, st: score_events(s, st,
        shift=-st["playback_timeline"]["current"]["count_in_beats"]*60/st["bpm"]),
    # Every right key, buried in a five-key cluster.
    "a cluster around every note": lambda s, st: score_events(s, st, pitch=_cluster),
    # Every right key, played as one chord on the downbeat.
    "every note at once on the downbeat": lambda s, st: [
        e for n in notes(s) for e in ((0.0, n["midi_pitch"], True), (.4, n["midi_pitch"], False))],
    # The notes of the window in reverse order, keeping the rhythm.
    "the right notes in reverse order": lambda s, st: [
        (at, pitch, on) for (at, _p, on), pitch in zip(
            score_events(s, st),
            [p for n in reversed(notes(s)) for p in (n["midi_pitch"],)*2])],
    # Every note held down from before the count-in through the take.
    "every key held from before the count-in": lambda s, st: [
        e for n in notes(s) for e in (
            (-st["playback_timeline"]["current"]["count_in_beats"]*60/st["bpm"]-1.0,
             n["midi_pitch"], True),
            ((n["onset_beats"]-st["play_from_beat"]+n["duration_beats"])*60/st["bpm"],
             n["midi_pitch"], False))],
    # Nothing but a glissando over the whole keyboard.
    "a glissando over every key": lambda s, st: [
        e for i, p in enumerate(range(21, 109)) for e in ((i*.03, p, True), (i*.03+.02, p, False))],
}


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
@pytest.mark.parametrize("cheat", list(CHEATS))
def test_tempo_cannot_be_fooled(practice_session, source, cheat):
    session = open_piece(practice_session, source)
    state = tempo(session)
    events = CHEATS[cheat](session, state)
    if cheat == "the right notes in reverse order" and \
            [n["midi_pitch"] for n in notes(session)] == [n["midi_pitch"] for n in reversed(notes(session))]:
        pytest.skip("this window reads the same backwards")
    after = perform(session, state, events)
    # Notes may be green where the right key was among the others, but
    # the take is not clean: extra keys fail it.
    assert_failed_and_repeated(state, after)


# --- It cannot be fooled in Free -------------------------------------------

def free(session):
    session.finish_listen()
    state = session.reach_free_target()
    assert state["mode"] == "learn" and state["teaching"]["expected_notes"], state
    return state


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_free_keys_before_the_target_arrives_earn_nothing(practice_session, source):
    session = open_piece(practice_session, source)
    session.finish_listen()
    state = session.snapshot()
    guided = state["playback_timeline"].get("guided")
    if not guided or guided["deadline_at_ms"]/1000 <= session.clock.at:
        pytest.skip("the first target is already at the playhead")
    for target in state["teaching"]["expected_notes"]:
        session.strike(target["pitch"])
    assert session.tick()["teaching"]["target_index"] == 0


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_free_every_key_at_once_finds_nothing(practice_session, source):
    session = open_piece(practice_session, source)
    state = free(session)
    for pitch in range(21, 109):
        session.key(pitch, after=0)
    for pitch in range(21, 109):
        session.key(pitch, False, after=0)
    after = session.tick()
    assert after["teaching"]["target_index"] == 0
    assert after["mode"] == "learn"


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_free_every_note_of_the_window_at_once_finds_only_the_first(practice_session, source):
    session = open_piece(practice_session, source)
    free(session)
    pitches = sorted({n["midi_pitch"] for n in notes(session)})
    if len(pitches) < 2:
        pytest.skip("one pitch only")
    for pitch in pitches:
        session.key(pitch, after=0)
    for pitch in pitches:
        session.key(pitch, False, after=0)
    after = session.tick()
    assert after["mode"] == "learn" and after["teaching"]["target_index"] <= 1


@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_free_a_wrong_key_waits_and_the_right_one_continues(practice_session, source):
    session = open_piece(practice_session, source)
    state = free(session)
    target = state["teaching"]["expected_notes"]
    wrong = max(t["pitch"] for t in target)+1
    session.strike(wrong)
    held = session.tick(20)
    assert held["teaching"]["target_index"] == 0
    assert held["teaching"]["hint_reason"] == "wrong_note"
    for t in target:
        session.key(t["pitch"])
    for t in target:
        session.key(t["pitch"], False)
    assert session.tick(.1)["teaching"]["target_index"] >= 1


# --- Pausing a real take never breaks it -----------------------------------

@pytest.mark.parametrize("source", SAMPLE, ids=SAMPLE_IDS)
def test_pause_mid_take_resumes_with_a_count_in_and_grades_cleanly(practice_session, source):
    session = open_piece(practice_session, source)
    state = tempo(session)
    session.clock.at = state["playback_timeline"]["current"]["deadline_ms"]/1000+.2
    session.tick()
    session.command("pause")
    session.tick(60)
    session.command("resume")
    resumed = session.ready_score()
    assert resumed["running"] and not resumed["paused"], resumed["feedback"]
    assert resumed["playback_timeline"]["state"] != "failed"
    current = resumed["playback_timeline"]["current"]
    assert current["deadline_ms"]/1000 > session.clock.at
    after = perform(session, resumed, score_events(session, resumed))
    assert after["running"] and after["playback_timeline"]["state"] != "failed"


# --- Windows across a change of meter -----------------------------------

@pytest.mark.parametrize("hand", ["right", "left"])
def test_a_window_across_a_change_of_meter_grades_and_follows_directly(practice_session, hand):
    """Moonlight II changes from 3/4 to 2/4: the window holding the change
    grades like any other and its repeat follows the real barlines."""
    from piano_teacher.importing.pieces import import_piece
    source = FIXTURES/"moonlight-2.mxl"
    piece = import_piece(source)
    change = piece.time_signatures[1][0]
    bar = piece.bar_boundaries.index(change)+1        # first bar in 2/4
    session = open_piece(practice_session, source)
    steps = session.ask("lesson.overview")["steps"]
    target = next(step for step in steps if step["hand"] == hand
                  and step["kind"] != "perform"
                  and (step["first_bar"], step["last_bar"]) == (bar-1, bar))
    session.command("select_step", number=target["number"])
    session.command("learn")
    state = tempo(session)
    clean = perform(session, state, score_events(session, state))
    assert graded(session, state["transport_id"]) == ["correct"]*len(
        [n for n in notes(session) if n["onset_beats"] >= state["play_from_beat"]])
    if state["bpm"] == state["target_bpm"]:
        assert clean["bpm"] == state["bpm"] and clean["streak"] == 1
    else:
        assert clean["bpm"] > state["bpm"]
    assert_follows_directly(session, state, clean, source)
    wrong = perform(session, clean, score_events(session, clean,
        pitch=lambda n: [n["midi_pitch"]+1]))
    assert_failed_and_repeated(clean, wrong)
