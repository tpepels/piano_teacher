"""Interleaved tempo, navigation and persistence through the real lesson engine."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from http.server import ThreadingHTTPServer
import json
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mido import Message
import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.lesson_settings import SETTINGS
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote, evaluate
from piano_teacher.server import Handler, PracticeEngine


def _piece():
    # Distinct source passages prevent repetition credit from hiding a lost BPM.
    boundaries = tuple(float(bar * 4) for bar in range(7))
    notes = tuple(
        Note(bar * 4.0, bar * 4.0 + 1, pitch, 0, 0, "right", f"ux-{bar}")
        for bar, pitch in enumerate((60, 62, 65, 67, 69, 71))
    )
    phrases = tuple(
        Phrase(bar // 2 + 1, bar + 1, bar + 2,
               boundaries[bar], boundaries[bar + 2], notes[bar:bar + 2])
        for bar in (0, 2, 4)
    )
    # The automatic ladder has six/seven-BPM gaps, distinct from manual five.
    return Piece("Manual tempo UX", 113, notes, phrases,
                 bar_boundaries=boundaries)


@contextmanager
def _engine(data_dir):
    engine = PracticeEngine(data_dir, enable_midi=False)
    try:
        engine.plan = LearningPlan(_piece())
        engine.fingerprint = "manual-tempo-interleaved-ux"
        engine._restore()
        yield engine
    finally:
        engine.db.close()


def _assessment(engine, flaw=None):
    plan = engine.plan
    phrase = plan.active_phrase
    seconds = 60 / plan.bpm
    played = [PlayedNote(note.pitch, (note.start - phrase.start) * seconds,
                         (min(note.end, phrase.end) - phrase.start) * seconds)
              for note in plan.active_variant.notes]
    first = played[0]
    if flaw == "late":
        played[0] = replace(first, onset=first.onset + .101,
                            release=first.release + .101)
    elif flaw == "short":
        played[0] = replace(first, release=first.onset
                            + (first.release - first.onset) * .79)
    elif flaw == "wrong":
        played[0] = replace(first, pitch=first.pitch + 1)
    elif flaw == "extra":
        played.append(PlayedNote(90, first.onset + .25, first.onset + .5))
    else:
        assert flaw is None
    result = evaluate(phrase, plan.hand, plan.bpm, played)
    assert result.clean is (flaw is None)
    return result


def _commit_take(engine, flaw=None):
    # Enter at the feedback boundary: grade actual note events and run the
    # production commit/persistence path, without faking progression or a piano.
    engine.pending_result = _assessment(engine, flaw)
    engine._commit_pending()
    return engine.state()


def _assert_no_mastery(engine):
    assert engine.plan.mastered == {}
    assert engine.state()["lesson_steps_mastered"] == 0
    assert engine.lesson_overview()["completed_steps"] == 0
    assert engine.db.execute("SELECT COUNT(*) FROM mastery").fetchone()[0] == 0


def test_manual_buttons_interleave_with_clean_progression_navigation_and_reload(tmp_path):
    assert SETTINGS.manual_tempo_step_bpm == 5
    assert SETTINGS.clean_runs_to_master == 3
    with _engine(tmp_path) as engine:
        first = engine.plan.identity
        target = engine.plan.target_bpm
        rungs = engine.state()["tempo_rungs"]

        engine.control("tempo_down")
        assert engine.state()["bpm"] == 35
        assert _commit_take(engine)["bpm"] == 40
        engine.control("tempo_up")
        assert engine.state()["bpm"] == 45
        assert 45 not in rungs
        automatic = _commit_take(engine)
        first_bpm = min(bpm for bpm in rungs if bpm > 45)
        assert automatic["bpm"] == first_bpm
        assert automatic["streak"] == 0
        assert engine.plan.identity == first
        _assert_no_mastery(engine)

        # Navigate forward, edit a different stage, then return backwards.
        engine.control("select_step", number=2)
        second = engine.plan.identity
        assert second != first
        assert engine.state()["bpm"] == 40
        engine.control("tempo_up")
        engine.control("tempo_up")
        second_bpm = engine.state()["bpm"]
        assert second_bpm == 50
        engine.control("select_step", number=1)
        assert engine.state()["bpm"] == first_bpm
        engine.control("select_step", number=2)
        assert engine.state()["bpm"] == second_bpm
        assert engine.state()["target_bpm"] == target == 113
        _assert_no_mastery(engine)

    # Real SQLite reload must retain *both* stage tempos and current location.
    with _engine(tmp_path) as engine:
        assert engine.plan.identity == second
        assert engine.state()["bpm"] == second_bpm
        engine.control("previous")
        assert engine.plan.identity == first
        assert engine.state()["bpm"] == first_bpm
        engine.control("next")
        assert engine.plan.identity == second
        assert engine.state()["bpm"] == second_bpm
        engine.control("select_step", number=1)
        while engine.plan.bpm < target:
            before = engine.plan.bpm
            state = _commit_take(engine)
            assert state["bpm"] == min(bpm for bpm in rungs if bpm > before)
            assert state["streak"] == 0  # Reaching target is not a target-speed take.
            assert engine.plan.identity == first
            _assert_no_mastery(engine)

        assert _commit_take(engine)["streak"] == 1
        assert _commit_take(engine)["streak"] == 2
        engine.control("tempo_down")
        slower = engine.state()
        assert slower["bpm"] == target - 5
        assert slower["target_bpm"] == target
        assert slower["can_increase_tempo"] and slower["can_decrease_tempo"]
        assert slower["streak"] == 0
        engine.control("tempo_up")
        assert engine.state()["bpm"] == target
        assert engine.state()["streak"] == 0
        _assert_no_mastery(engine)

    with _engine(tmp_path) as engine:
        assert engine.plan.identity == first
        assert engine.state()["bpm"] == engine.state()["target_bpm"] == target
        assert engine.state()["streak"] == 0
        for expected in (1, 2):
            assert _commit_take(engine)["streak"] == expected
            assert engine.plan.identity == first
            _assert_no_mastery(engine)
        mastered = _commit_take(engine)
        assert engine.plan.mastered == {first: target}
        assert engine.plan.identity == second
        assert mastered["bpm"] == second_bpm
        assert mastered["streak"] == 0
        assert mastered["lesson_steps_mastered"] == 1

    with _engine(tmp_path) as engine:
        assert engine.plan.identity == second
        assert engine.plan.mastered == {first: target}
        assert engine.state()["bpm"] == second_bpm
        assert engine.lesson_overview()["completed_steps"] == 1


@pytest.mark.parametrize("flaw", ["late", "short", "wrong", "extra"])
def test_manual_target_speed_still_requires_strict_clean_consecutive_takes(tmp_path, flaw):
    assert SETTINGS.grading_onset_tolerance_seconds == .1
    assert SETTINGS.grading_duration_tolerance_fraction == .2
    with _engine(tmp_path) as engine:
        stage = engine.plan.identity
        while engine.plan.bpm < engine.plan.target_bpm:
            engine.control("tempo_up")
        assert engine.state()["streak"] == 0
        assert _commit_take(engine)["streak"] == 1
        assert _commit_take(engine)["streak"] == 2
        failed = _commit_take(engine, flaw)
        assert failed["streak"] == 0
        assert failed["bpm"] == failed["target_bpm"] == 113
        assert engine.plan.identity == stage
        _assert_no_mastery(engine)
        assert _commit_take(engine)["streak"] == 1
        assert engine.plan.identity == stage
        _assert_no_mastery(engine)


@pytest.mark.parametrize("action", ["tempo_down", "tempo_up", "select_step"])
@pytest.mark.parametrize("phase", ["count_in", "paused", "feedback"])
def test_manual_change_abandons_transport_and_uncommitted_take(tmp_path, action, phase):
    with _engine(tmp_path) as engine:
        engine.control("start")
        if phase == "paused":
            engine.control("pause")
        elif phase == "feedback":
            engine.control("stop")
            engine.pending_result = _assessment(engine)
            engine.auto = True
            engine.next_at = time.monotonic() + 60
        before = engine.state()
        assert before["phase"] == phase
        if phase == "feedback":
            assert before["take_result"]["clean"]
        engine.control(action, **({"number": 2} if action == "select_step" else {}))
        state = engine.state()
        expected_bpm = {"tempo_down": 35, "tempo_up": 45, "select_step": 40}[action]
        expected_step = 2 if action == "select_step" else 1
        assert state["bpm"] == expected_bpm
        assert state["lesson_step"] == expected_step
        assert state["target_bpm"] == 113
        assert state["phase"] == "ready"
        assert not state["running"] and not state["paused"] and not state["auto"]
        assert state["take_result"] is None
        assert state["awaiting_score_revision"] is None
        # Playback-only tempo changes reuse source notation. Changing to a
        # different lesson step must still request a new score revision.
        assert state["revision"] == (before["revision"] + 1
                                     if action == "select_step" else before["revision"])
        assert engine.pending_result is None and engine.recorder is None
        assert engine.next_at == 0
        # A delayed renderer acknowledgement must not restart the abandoned take.
        engine.control("score_ready", revision=before["revision"])
        assert engine.state()["phase"] == "ready"
        assert engine.state()["streak"] == 0
        _assert_no_mastery(engine)
    with _engine(tmp_path) as engine:
        assert engine.state()["bpm"] == expected_bpm
        assert engine.state()["lesson_step"] == expected_step
        assert engine.state()["streak"] == 0
        _assert_no_mastery(engine)


@pytest.mark.parametrize("action", ["tempo_down", "tempo_up"])
def test_manual_tempo_without_piano_remains_ungraded_preview(tmp_path, action):
    with _engine(tmp_path) as engine:
        engine.control(action)
        bpm, stage = engine.plan.bpm, engine.plan.identity
        engine.control("start")
        assert engine.state()["phase"] == "count_in"
        assert engine.preview_only
        # Real MIDI-shaped input during the count-in cannot become a scored note.
        engine._receive(Message("note_on", note=60, velocity=90))
        engine._receive(Message("note_off", note=60, velocity=0))
        assert engine.state()["midi_input_count"] == 1
        assert engine.state()["midi_notes"] == 0
        phrase = engine.plan.active_phrase
        engine.run_at = time.monotonic() - (phrase.end - phrase.start) * 60 / bpm - 1
        finished = engine.state()
        assert finished["phase"] == "ready"
        assert not finished["running"] and not finished["auto"]
        assert finished["take_result"] is None and finished["streak"] == 0
        assert finished["bpm"] == bpm and finished["target_bpm"] == 113
        assert engine.plan.identity == stage
        _assert_no_mastery(engine)


@contextmanager
def _http(engine):
    class LocalHandler(Handler):
        pass

    LocalHandler.engine = engine
    service = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = Thread(target=service.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{service.server_port}"

    def request(route, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(base + route, data=body,
                      headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            assert response.headers.get_content_type() == "application/json"
            return response.status, json.load(response)

    try:
        yield request
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=5)


def test_http_manual_buttons_respect_bounds_and_survive_invalid_selection(tmp_path):
    with _engine(tmp_path) as engine, _http(engine) as request:
        for payload in ({"action": "select_step", "number": number}
                        for number in (0, -1, len(engine.plan.lesson_steps) + 1,
                                       "not-a-step", None)):
            status, error = request("/control", payload)
            assert status == 400 and error["error"]
            assert request("/state")[1]["bpm"] == 40
        status, error = request("/control", {"action": "select_step"})
        assert status == 400 and error["error"]

        status, state = request("/control", {"action": "tempo_down"})
        assert status == 200 and state["bpm"] == 35
        assert state["manual_tempo_step_bpm"] == 5
        assert state["can_decrease_tempo"] and state["can_increase_tempo"]
        while state["bpm"] > SETTINGS.minimum_bpm:
            before = state["bpm"]
            status, state = request("/control", {"action": "tempo_down"})
            assert status == 200
            assert state["bpm"] == max(SETTINGS.minimum_bpm, before - 5)
        assert not state["can_decrease_tempo"] and state["can_increase_tempo"]
        assert request("/control", {"action": "tempo_down"})[1]["bpm"] == SETTINGS.minimum_bpm
        while state["bpm"] < state["target_bpm"]:
            before = state["bpm"]
            status, state = request("/control", {"action": "tempo_up"})
            assert status == 200
            assert state["bpm"] == min(state["target_bpm"], before + 5)
        assert state["target_bpm"] == 113
        assert not state["can_increase_tempo"] and state["can_decrease_tempo"]
        assert request("/control", {"action": "tempo_up"})[1]["bpm"] == 113
        assert request("/control", {"action": "tempo_down"})[1]["bpm"] == 108
        assert request("/lesson")[1]["completed_steps"] == 0
        assert state["lesson_step"] == 1 and state["streak"] == 0
        _assert_no_mastery(engine)


@pytest.mark.parametrize("action", ["tempo_down", "tempo_up", "select_step"])
def test_http_manual_controls_require_loaded_music(tmp_path, action):
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        with _http(engine) as request:
            status, error = request("/control", {"action": action, "number": 1})
            assert status == 400
            assert error == {"error": "Open a piece first"}
            status, state = request("/state")
            assert status == 200 and not state["loaded"] and not state["running"]
    finally:
        engine.db.close()


@pytest.mark.parametrize("number", [2.9, True, False],
                         ids=["fractional", "true", "false"])
def test_http_step_selection_requires_an_integer_not_lossy_coercion(tmp_path, number):
    with _engine(tmp_path) as engine, _http(engine) as request:
        status, _ = request("/control", {"action": "select_step", "number": number})
        assert status == 400
        state = request("/state")[1]
        assert state["lesson_step"] == 1 and state["bpm"] == 40
        _assert_no_mastery(engine)


@pytest.mark.parametrize("number", [2, 2.0, "2", " +2 ", "02"])
def test_http_step_selection_keeps_safe_integer_input_compatibility(tmp_path, number):
    # Keep legacy integer strings and whole floats (JSON clients may send 2.0).
    # These name exactly one stage; fractional values and booleans do not.
    with _engine(tmp_path) as engine, _http(engine) as request:
        request("/control", {"action": "tempo_down"})
        status, selected = request("/control", {"action": "select_step", "number": number})
        assert status == 200
        assert selected["lesson_step"] == 2 and selected["bpm"] == 40
        status, previous = request("/control", {"action": "select_step", "number": 1})
        assert status == 200
        assert previous["lesson_step"] == 1 and previous["bpm"] == 35
        _assert_no_mastery(engine)


@pytest.mark.parametrize("phase", ["count_in", "playing", "paused", "feedback", "loading"])
def test_http_invalid_stage_preserves_transport_and_pending_assessment(tmp_path, phase):
    with _engine(tmp_path) as engine, _http(engine) as request:
        engine.control("select_step", number=2)
        engine.control("tempo_down")
        engine.control("select_step", number=1)
        while engine.plan.bpm < engine.plan.target_bpm:
            engine.control("tempo_up")
        _commit_take(engine)
        assert _commit_take(engine)["streak"] == 2
        request("/control", {"action": "start"})
        if phase in ("playing", "paused"):
            engine.run_at = time.monotonic() - .25
            engine._receive(Message("note_on", note=60, velocity=90))
        if phase == "paused":
            request("/control", {"action": "pause"})
        elif phase == "feedback":
            engine.control("stop")
            engine.pending_result = _assessment(engine)
            engine.auto = True
            engine.next_at = time.monotonic() + 60
        elif phase == "loading":
            request("/control", {"action": "practice"})
        before = request("/state")[1]
        assert before["phase"] == phase
        recorder, pending = engine.recorder, engine.pending_result
        transport = (engine.run_at, engine.next_at, engine.paused_at,
                     engine._deferred_score_ack)
        stage_tempos = dict(engine.plan.stage_tempos)
        saved_progress = tuple(engine.db.iterdump())
        invalid = [{}, *({"number": value} for value in (
            0, -1, len(engine.plan.lesson_steps) + 1, 2.9, True, False, None,
            [], {}, "not-a-step", "2.0", "", float("nan"), float("inf"),
            -float("inf"), 10 ** 100,
        ))]
        for arguments in invalid:
            status, error = request("/control", {"action": "select_step", **arguments})
            assert status == 400 and error["error"], arguments
            after = request("/state")[1]
            for field in ("phase", "running", "paused", "auto", "transport_id", "revision",
                          "lesson_step", "bpm", "target_bpm", "streak", "take_result",
                          "feedback", "next_action", "pause_context", "awaiting_score_revision",
                          "count_in_beats", "play_from_beat", "recovery_beat"):
                assert after[field] == before[field], (arguments, field)
            assert engine.recorder is recorder
            assert engine.pending_result is pending
            assert (engine.run_at, engine.next_at, engine.paused_at,
                    engine._deferred_score_ack) == transport
            assert engine.plan.stage_tempos == stage_tempos
            assert tuple(engine.db.iterdump()) == saved_progress
        _assert_no_mastery(engine)
