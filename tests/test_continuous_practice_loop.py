"""The visual loop is independent of the original MIDI grading attempt."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import time
import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.server import PracticeEngine
from piano_teacher.practice import PlayedNote, evaluate


def sample_piece() -> Piece:
    notes = (
        Note(0, 1, 60, 0, 0, "right", "first"),
        Note(4, 5, 62, 0, 0, "right", "second"),
    )
    return Piece("Loop example", 110, notes,
                 (Phrase(1, 1, 2, 0, 8, notes),),
                 bar_boundaries=(0, 4, 8))


def engine(tmp_path: Path) -> PracticeEngine:
    app = PracticeEngine(tmp_path, enable_midi=False)
    app.plan = LearningPlan(sample_piece())
    app.fingerprint = "score-loop-fixture"
    return app


def test_preview_continues_after_one_empty_measure_without_reloading(tmp_path):
    app = engine(tmp_path)
    try:
        app.start()
        assert app.preview_only
        first_revision = app.score_revision
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        # Simulate the end of one ungraded passage, one beat into its gap.
        app.run_at = time.monotonic() - (length + 1) * 60 / app.plan.bpm
        app._update()
        assert app._preview_loop_pending and not app.running
        position = app.state()
        assert length < position["visual_scroll_beat"] < length + app.visual_gap_beats
        assert position["visual_scroll_speed"] > 0
        app.next_at = time.monotonic() - .01
        app._update()
        assert app.running and app.preview_only
        assert app.visual_offset_beats == length + app.visual_gap_beats
        assert app.count_in_beats == 0.0
        assert app.score_revision == first_revision
        assert app.state()["score_loop_enabled"]
    finally:
        app.db.close()


def test_clean_auto_take_increases_bpm_without_reengraving(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        assert not app.preview_only and app.auto
        bpm, original_revision = app.plan.bpm, app.score_revision
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        app.running = False
        app.pending_result = SimpleNamespace(
            correct=2, notes=[object(), object()], extra_notes=0, clean=True)
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.plan.bpm > bpm
        assert app.score_revision == original_revision
        assert app.running and app.auto
        assert app.visual_offset_beats == length + app.visual_gap_beats
        assert app.count_in_beats == 0
        assert app.plan.streak == 0
    finally:
        app.db.close()


def test_failed_auto_take_moves_back_in_place_and_never_advances_repeat(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        length = app.plan.active_phrase.end - app.plan.active_phrase.start
        app.running = False
        app.pending_result = SimpleNamespace(
            correct=1, notes=[object(), object()], extra_notes=0, clean=False)
        app._retry_previous_pass = True
        app._visual_rewind_from = length
        app._visual_rewind_to = 0.0
        app._visual_rewind_at = time.monotonic() - .25
        app._visual_rewind_seconds = 1.0
        before = app.state()
        assert before["visual_scroll_speed"] < 0
        assert 0 < before["visual_scroll_beat"] < length
        revision = app.score_revision
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.visual_offset_beats == 0.0
        assert app.plan.bpm == app.plan.start_bpm
        assert app.score_revision == revision
        assert app.running
        assert not app._retry_previous_pass
    finally:
        app.db.close()


def test_backward_recovery_is_still_local_to_source_measure_grid(tmp_path):
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        app.running = False
        app.pending_rewind = 4.0
        app._visual_rewind_from = 8.0
        app._visual_rewind_to = 4.0
        app._visual_rewind_at = time.monotonic() - .25
        app._visual_rewind_seconds = 1.0
        app.next_at = time.monotonic() + 1
        progress = app.state()
        assert progress["visual_scroll_speed"] < 0
        assert 4 < progress["visual_scroll_beat"] < 8
        app.next_at = time.monotonic() - .1
        app._update()
        assert app.running
        assert app.play_from_beat == 4.0
        assert app.visual_offset_beats == 0
    finally:
        app.db.close()


def test_ready_and_preview_publish_source_independent_gap_descriptor(tmp_path):
    app = engine(tmp_path)
    try:
        model = app.semantic_score()
        ready = app.state()
        assert ready["practice_timeline"] == model["practice_timeline"]
        assert ready["practice_timeline"]["stride_beats"] == 12
        assert ready["visual_gap_beats"] == 4
        app.start()
        assert app.state()["practice_timeline"] == ready["practice_timeline"]
        assert len(model["notes"]) == 2
        assert all(not event["id"].startswith("practice:")
                   for event in model["notation_events"])
    finally:
        app.db.close()


def test_start_does_not_replace_source_engraving_at_slow_learning_bpm(tmp_path):
    app = engine(tmp_path)
    try:
        # Source engraving is immutable at 110 BPM while practice starts 40.
        app._layout_cache = object()
        app._layout_bpm = app.plan.piece.bpm
        assert app.plan.bpm != app._layout_bpm
        before = app.score_revision
        app.control("start")
        assert app.running
        assert app.count_in_beats > 0.0
        assert app.score_revision == before
        assert app.awaiting_score_revision is None
    finally:
        app.db.close()


def test_manual_tempo_changes_keep_native_notation_revision(tmp_path):
    app = engine(tmp_path)
    try:
        # Simulate an already rendered native score at its source tempo.
        native_layout = object()
        app._layout_cache = native_layout
        app._layout_bpm = app.plan.piece.bpm
        revision = app.score_revision
        app.control("tempo_down")
        assert app.plan.bpm == app.plan.start_bpm - 5
        assert app.score_revision == revision
        assert app._layout_cache is native_layout
        app.control("tempo_up")
        assert app.plan.bpm == app.plan.start_bpm
        assert app.score_revision == revision
        app.control("tempo", bpm=95)
        assert app.score_revision == revision
        app.control("start")
        assert app.running
        assert app.awaiting_score_revision is None
        assert app.score_revision == revision
    finally:
        app.db.close()


def test_paused_empty_measure_resumes_at_identical_visual_position(tmp_path, monkeypatch):
    from piano_teacher import server
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    app = engine(tmp_path)
    try:
        app.start()
        duration = app.plan.active_phrase.end - app.plan.active_phrase.start
        now[0] = app.run_at + (duration + 1) * 60 / app.plan.bpm
        before = app.state()
        assert app._preview_loop_pending
        assert before["phase"] == "preview_gap"
        assert before["visual_scroll_speed"] > 0
        position = before["visual_scroll_beat"]
        deadline = app.next_at
        app.control("pause")
        now[0] += 45
        assert app.state()["phase"] == "paused"
        assert app.state()["visual_scroll_beat"] == pytest.approx(position)
        app.control("resume")
        assert app.state()["visual_scroll_beat"] == pytest.approx(position)
        assert app.next_at == pytest.approx(deadline + 45)
        now[0] = app.next_at + .01
        after = app.state()
        assert after["running"]
        assert after["visual_scroll_beat"] == pytest.approx(duration + app.visual_gap_beats,
                                                              abs=.1)
    finally:
        app.db.close()


def test_paused_rewind_resumes_without_skipping_backward_frames(tmp_path, monkeypatch):
    from piano_teacher import server
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    app = engine(tmp_path)
    try:
        app._piano_connected = lambda: True
        app.start()
        app.running = False
        app.pending_rewind = 4.0
        app._visual_rewind_from = 8.0
        app._visual_rewind_to = 4.0
        app._visual_rewind_at = now[0]
        app._visual_rewind_seconds = 2.0
        app.next_at = now[0] + 2.0
        now[0] += .5
        before = app.state()
        assert before["phase"] == "recovering"
        assert before["visual_scroll_speed"] < 0
        position = before["visual_scroll_beat"]
        app.control("pause")
        now[0] += 20
        assert app.state()["visual_scroll_beat"] == pytest.approx(position)
        app.control("resume")
        assert app.state()["visual_scroll_beat"] == pytest.approx(position)
        now[0] += .25
        assert 4 < app.state()["visual_scroll_beat"] < position
        now[0] = app.next_at + .01
        after = app.state()
        assert after["phase"] == "playing"
        assert after["play_from_beat"] == 4.0
        assert after["visual_scroll_beat"] == pytest.approx(4.0, abs=.1)
    finally:
        app.db.close()


def test_open_at_measure_shows_selected_source_before_pressing_start(tmp_path):
    app = engine(tmp_path)
    try:
        app.control("open_at", bar=2, mode="practice")
        ready = app.state()
        assert ready["phase"] == "ready"
        assert ready["first_bar"] == 1
        assert ready["selected_start_bar"] == 2
        assert ready["play_from_beat"] == pytest.approx(4.0)
        app.control("start")
        playing = app.state()
        assert playing["play_from_beat"] == pytest.approx(4.0)
        assert playing["selected_start_bar"] == 2
    finally:
        app.db.close()


@pytest.fixture
def clocked_engine(tmp_path, monkeypatch):
    from piano_teacher import server
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    engines = []

    def create(*, grid=(0, 4, 8), meters=((0, 4, 4),), connected=False,
               dense=False, bpm=80):
        attacks = range(int(grid[-1])) if dense else grid[:-1]
        notes = tuple(Note(float(at), float(at)+.25, 60+i % 5, 0, 0,
                           "right", f"n{i}") for i, at in enumerate(attacks))
        piece = Piece("Timed loop", bpm, notes,
                      (Phrase(1, 1, len(grid)-1, 0, grid[-1], notes),),
                      bar_boundaries=grid, time_signatures=meters)
        app = PracticeEngine(tmp_path / str(len(engines)), enable_midi=False)
        engines.append(app)
        app.plan = LearningPlan(piece, consolidate=True)
        app.plan.set_bpm(bpm)
        if connected:
            app._piano_connected = lambda: True
        return app, now

    yield create
    for app in engines:
        app.db.close()


def record_clean(app):
    phrase = app.plan.active_phrase
    app.recorder.presses = [
        PlayedNote(note.pitch, (note.start-phrase.start-app.play_from_beat)*60/app.plan.bpm,
                   (note.end-phrase.start-app.play_from_beat)*60/app.plan.bpm)
        for note in phrase.notes if note.start >= phrase.start+app.play_from_beat]


def test_preview_uses_upcoming_meter_and_preserves_poll_overshoot(clocked_engine):
    app, now = clocked_engine(grid=(0, .5, 3.5, 4.5),
                              meters=((0, 3, 4), (3.5, 2, 4)))
    app.start()
    assert app.visual_gap_beats == 3
    revision = app.score_revision
    end_at = app.run_at + 4.5*60/80
    now[0] = end_at + .21
    app._update()
    assert app.next_at == pytest.approx(end_at + 3*60/80)
    deadline = app.next_at
    now[0] = deadline + .125
    state = app.state()
    assert app.run_at == pytest.approx(deadline)
    assert state["visual_scroll_beat"] == pytest.approx(7.5 + .125*80/60)
    assert state["count_in_beats"] == 0
    assert state["revision"] == revision


def test_partial_preview_gap_starts_at_source_end_then_repeats_from_zero(clocked_engine):
    app, now = clocked_engine()
    app.open_from_beat = 4
    app.start()
    end_at = app.run_at + 4*60/80
    now[0] = end_at + .3
    state = app.state()
    assert state["visual_scroll_beat"] == pytest.approx(8.4)
    assert app.next_at == pytest.approx(end_at + 4*60/80)
    now[0] = app.next_at + .1
    repeated = app.state()
    assert repeated["play_from_beat"] == 0
    assert repeated["visual_scroll_beat"] == pytest.approx(12 + .1*80/60)


def test_fast_clean_take_restarts_at_rest_end_without_feedback_hold(clocked_engine):
    app, now = clocked_engine(grid=(0, 1, 2), meters=((0, 1, 4),),
                              connected=True, bpm=240)
    app.start()
    record_clean(app)
    end_at = app.run_at + 2*60/240
    now[0] = end_at + .21
    app._update()
    assert app.pending_result.clean
    assert app.next_at == pytest.approx(end_at + .25)
    now[0] = end_at + .3
    state = app.state()
    assert state["running"] and state["count_in_beats"] == 0
    assert app.run_at == pytest.approx(end_at + .25)
    assert state["visual_scroll_beat"] == pytest.approx(3.2)


def test_failed_take_reverses_to_full_preparation_then_replays_same_pass(clocked_engine):
    app, now = clocked_engine(connected=True)
    app.start()
    revision = app.score_revision
    now[0] = app.run_at + 8*60/80 + .21
    state = app.state()
    prep = state["practice_preparation"]
    assert prep["pass_start_beat"] == 0 and prep["source_from_beat"] == 0
    assert (prep["measure"]["start_beat"], prep["measure"]["end_beat"]) == (-4, 0)
    assert prep["phase"] == "reverse"
    assert state["visual_scroll_speed"] < 0
    reverse_end = app._visual_rewind_at + app._visual_rewind_seconds
    now[0] = reverse_end
    prepared = app.state()
    assert prepared["practice_preparation"]["phase"] == "preparing"
    assert prepared["visual_scroll_beat"] == pytest.approx(-4)
    assert prepared["visual_scroll_speed"] == pytest.approx(80/60)
    assert not prepared["running"]
    now[0] = reverse_end + 3 + .1
    repeated = app.state()
    assert repeated["running"] and repeated["count_in_beats"] == 0
    assert repeated["visual_offset_beats"] == 0
    assert repeated["visual_scroll_beat"] == pytest.approx(.1*80/60)
    assert repeated["revision"] == revision
    assert not app._retry_previous_pass


def test_local_failure_prepares_in_target_meter_and_keeps_adaptive_escalation(clocked_engine):
    app, now = clocked_engine(grid=(0, 3, 6, 10, 14),
                              meters=((0, 3, 4), (6, 4, 4)),
                              connected=True, dense=True)
    app.start()
    record_clean(app)
    # First two bars succeed; miss the later canonical two-bar unit.
    app.recorder.presses = [note for note in app.recorder.presses if note.onset < 6*60/80]
    now[0] = app.run_at + 14*60/80 + .03
    first = app.state()
    assert first["recovery_beat"] == 6 and first["bpm"] == 72
    prep = first["practice_preparation"]["measure"]
    assert (prep["start_beat"], prep["end_beat"], prep["meter"]) == (2, 6, [4, 4])
    now[0] = app.next_at + .1
    retry = app.state()
    assert retry["running"] and retry["play_from_beat"] == 6
    assert retry["visual_offset_beats"] == 0 and retry["count_in_beats"] == 0
    now[0] = app.run_at + 8*60/72 + .03
    second = app.state()
    assert second["guided_recovery"] and second["recovery_beat"] == 6
    now[0] = app.next_at + .01
    guided = app.state()
    assert guided["mode"] == "learn" and guided["first_bar"] == 3
    assert guided["last_bar"] == 4


def test_manual_retry_preparation_pauses_and_resumes_without_skipping(clocked_engine):
    app, now = clocked_engine()
    app.start()
    app.visual_offset_beats = 12
    now[0] = app.run_at + 6*60/80
    revision = app.score_revision
    app.control("restart")
    state = app.state()
    assert not state["running"]
    assert state["practice_preparation"]["pass_start_beat"] == 12
    assert state["practice_preparation"]["measure"]["start_beat"] == 8
    assert state["visual_scroll_speed"] < 0
    now[0] = app._visual_rewind_at + app._visual_rewind_seconds + .75
    preparing = app.state()
    position = preparing["visual_scroll_beat"]
    deadline = app.next_at
    assert preparing["practice_preparation"]["phase"] == "preparing"
    app.control("pause")
    now[0] += 30
    assert app.state()["visual_scroll_beat"] == pytest.approx(position)
    app.control("resume")
    assert app.state()["visual_scroll_beat"] == pytest.approx(position)
    assert app.next_at == pytest.approx(deadline + 30)
    now[0] = app.next_at + .1
    repeated = app.state()
    assert repeated["visual_scroll_beat"] == pytest.approx(12 + .1*80/60)
    assert repeated["count_in_beats"] == 0 and repeated["revision"] == revision
    assert repeated["practice_preparation"]["phase"] == "complete"


def test_short_meter_rest_does_not_wait_for_longer_assessment_grace(clocked_engine):
    app, now = clocked_engine(grid=(0, .5, 1), meters=((0, 1, 8),),
                              connected=True, bpm=240)
    app.start()
    record_clean(app)
    deadline = app.run_at + 1.5*60/240
    now[0] = deadline + .01
    state = app.state()
    assert state["visual_offset_beats"] == 1.5
    assert state["visual_scroll_beat"] == pytest.approx(1.54)
    assert state["running"] and state["count_in_beats"] == 0
    assert app.run_at == pytest.approx(deadline)


def test_semantic_response_cannot_corrupt_cached_transport_contract(clocked_engine):
    app, _ = clocked_engine()
    response = app.semantic_score()
    response["practice_timeline"]["gap"]["duration_beats"] = 99
    response["practice_timeline"]["gap"]["meter"][0] = 99
    ready = app.state()
    assert ready["visual_gap_beats"] == 4
    assert ready["practice_timeline"]["gap"]["meter"] == [4, 4]


def test_clean_partial_take_prepares_whole_source_without_earning_mastery(clocked_engine):
    app, now = clocked_engine(connected=True)
    app.start(from_beat=4)
    record_clean(app)
    now[0] = app.run_at + 4*60/80 + .21
    finished = app.state()
    assert finished["recovery_beat"] == 0
    assert finished["practice_preparation"]["source_from_beat"] == 0
    assert finished["visual_scroll_speed"] < 0
    assert app.pending_result is None and not app.plan.mastered
    assert app.plan.streak == 0
    now[0] = app.next_at + .1
    whole = app.state()
    assert whole["play_from_beat"] == 0 and whole["count_in_beats"] == 0
    assert whole["visual_offset_beats"] == 0
    assert whole["visual_scroll_beat"] == pytest.approx(.1*80/60)


def test_tempo_changes_preserve_cached_gap_geometry(clocked_engine):
    app, _ = clocked_engine(grid=(0, 3, 4), meters=((0, 3, 4),))
    before = app.state()["practice_timeline"]
    cached = app._semantic_cache
    revision = app.score_revision
    app.control("tempo", bpm=120)
    after = app.state()
    assert after["practice_timeline"] == before
    assert after["revision"] == revision
    assert app._semantic_cache is cached


def test_semantic_cache_distinguishes_guided_fragments_at_same_revision(clocked_engine):
    app, _ = clocked_engine(grid=(0, 3, 6, 10, 14),
                            meters=((0, 3, 4), (6, 4, 4)), connected=True)
    whole = app.semantic_score()
    revision = app.score_revision
    app._begin_learn(from_beat=0, bump_revision=False)
    first = app.semantic_score()
    app._begin_learn(from_beat=6, bump_revision=False)
    second = app.semantic_score()
    assert whole["duration_beats"] == 14
    assert (first["first_bar"], first["last_bar"], first["duration_beats"]) == (1, 2, 6)
    assert (second["first_bar"], second["last_bar"], second["duration_beats"]) == (3, 4, 8)
    assert {note["id"] for note in first["notes"]} == {"n0", "n1"}
    assert {note["id"] for note in second["notes"]} == {"n2", "n3"}
    assert [note["onset_beats"] for note in second["notes"]] == [0, 4]
    assert first["practice_timeline"]["gap"]["meter"] == [3, 4]
    assert second["practice_timeline"]["gap"]["meter"] == [4, 4]
    assert second["practice_timeline"]["stride_beats"] == 12
    assert first["revision"] == second["revision"] == revision
    app._prepare_practice()
    restored = app.semantic_score()
    assert restored["practice_timeline"] == whole["practice_timeline"]
    assert len(restored["notes"]) == 4


@pytest.mark.parametrize("phase", ("reverse", "preparing"))
@pytest.mark.parametrize("paused", (False, True))
def test_manual_tempo_cancels_preparation_without_reengraving(clocked_engine, phase, paused):
    app, now = clocked_engine()
    app.start()
    now[0] = app.run_at + 6*60/80
    app.control("restart")
    deadline = app.next_at
    now[0] = (app._visual_rewind_at + .5 if phase == "reverse"
              else app._preparation_at + .5)
    before = app.state()
    assert before["practice_preparation"]["phase"] == phase
    if paused:
        app.control("pause")
        now[0] += 15
    cached = app._semantic_cache
    app.control("tempo", bpm=120)
    ready = app.state()
    assert ready["phase"] == "ready" and ready["bpm"] == 120
    assert not ready["running"] and not ready["paused"]
    assert ready["practice_preparation"] is None and ready["recovery_beat"] is None
    assert app.next_at == 0 and not app._preparation_pending
    assert ready["revision"] == before["revision"]
    assert ready["practice_timeline"] == before["practice_timeline"]
    assert app._semantic_cache is cached
    now[0] = deadline + 30
    assert app.state()["phase"] == "ready"


def test_preparation_survives_recovery_and_forward_continuation_until_stop(clocked_engine):
    app, now = clocked_engine()
    app.start()
    now[0] = app.run_at + 6*60/80
    app.control("restart")
    now[0] = app.next_at + .1
    replay = app.state()
    preparation = replay["practice_preparation"]
    assert preparation["phase"] == "complete"
    assert preparation["pass_start_beat"] == 0
    assert preparation["measure"]["start_beat"] == -4
    now[0] = app.run_at + 8*60/80 + .21
    app.state()
    now[0] = app.next_at + .1
    forward = app.state()
    assert forward["visual_offset_beats"] == 12
    assert forward["practice_preparation"] == preparation
    app.control("stop")
    assert app.state()["practice_preparation"] is None


@pytest.mark.parametrize("mode,perform_exercise,continuous", [
    ("practice", False, True),
    ("perform", False, False),
    ("practice", True, False),
])
def test_manual_retry_preparation_is_only_for_continuous_practice(
        clocked_engine, mode, perform_exercise, continuous):
    app, now = clocked_engine(grid=(0, 3, 6), meters=((0, 3, 4),))
    if perform_exercise:
        piece = app.plan.piece
        phrases = tuple(Phrase(i+1, i+1, i+1, start, end,
                               tuple(n for n in piece.notes if start <= n.start < end))
                        for i, (start, end) in enumerate(((0, 3), (3, 6))))
        app.plan = LearningPlan(replace(piece, phrases=phrases), consolidate=True)
        app.plan.select(next(i for i, exercise in enumerate(app.plan.exercises)
                             if exercise.kind == "perform"))
        app.plan.set_bpm(80)
    app.start(mode=mode)
    now[0] = app.run_at + .5
    revision = app.score_revision
    app.control("restart")
    state = app.state()
    assert state["mode"] == mode
    assert state["revision"] == revision
    assert state["score_loop_enabled"] is continuous
    if continuous:
        assert not state["running"] and state["count_in_beats"] == 0
        assert state["practice_preparation"]["measure"]["duration_beats"] == 3
        assert app.next_at == pytest.approx(now[0] + app.feedback_seconds + 3*60/80)
    else:
        assert state["running"] and state["count_in_beats"] == 3
        assert state["practice_preparation"] is None
        assert app.next_at == 0 and not app._preparation_pending
        assert app.run_at == pytest.approx(now[0] + 3*60/80)


MIDI_HANDOFFS = ("preview", "clean", "failed", "manual", "local")


@pytest.fixture
def midi_handoff(clocked_engine, monkeypatch):
    def prepare(kind):
        options = dict(connected=kind != "preview")
        if kind == "local":
            options.update(grid=(0, 3, 6, 10, 14),
                           meters=((0, 3, 4), (6, 4, 4)), dense=True)
        app, now = clocked_engine(**options)

        def no_render():
            raise ValueError("MIDI handoff tests intentionally omit engraving feedback")

        monkeypatch.setattr(app, "engraving", no_render)
        app.start()
        phrase = app.plan.active_phrase
        if kind == "manual":
            now[0] = app.run_at + 2
            app.control("restart")
        else:
            if kind in ("clean", "local"):
                record_clean(app)
                if kind == "local":
                    app.recorder.presses = [note for note in app.recorder.presses
                                           if note.onset < 6*60/80]
            now[0] = app.run_at + (phrase.end-phrase.start)*60/app.plan.bpm + .21
            app._update()
        assert not app.running and app.next_at > now[0]
        assert app.recorder is None or kind == "preview"  # Preview retains its old, ungraded take.
        if kind == "local":
            assert app.pending_rewind == 6 and app.plan.bpm == 72
        if kind == "preview":
            assert app._preview_loop_pending
            # A piano has connected since the previous silent preview.
            app._piano_connected = lambda: True
        target = app.pending_rewind if app.pending_rewind is not None else 0
        note = next(n for n in phrase.notes if n.start == phrase.start + target
                    and (app.plan.hand == "both" or n.hand == app.plan.hand))
        return app, now, app.next_at, note

    return prepare


def midi_note(pitch, *, is_on=True):
    return SimpleNamespace(type="note_on" if is_on else "note_off", channel=0,
                           note=pitch, velocity=90 if is_on else 0)


@pytest.mark.parametrize("kind", MIDI_HANDOFFS)
@pytest.mark.parametrize("overshoot", (0, .001))
def test_midi_deadline_handoff_retains_first_attack_release_and_feedback(
        midi_handoff, monkeypatch, kind, overshoot):
    app, now, deadline, note = midi_handoff(kind)
    transport = app.transport_id
    previous_recorder = app.recorder
    revision = app.score_revision
    app.hardware_probe.start("Review piano", now=now[0])
    probe_start = app.hardware_probe.started_at
    original_update = app._update
    calls = []

    def delayed_update():
        calls.append(now[0])
        original_update()
        now[0] += .04  # Persistence/transition work cannot re-timestamp this key.

    monkeypatch.setattr(app, "_update", delayed_update)
    now[0] = received_at = deadline + overshoot
    app._receive(midi_note(note.pitch))
    assert calls == [received_at]
    assert app.running and app.transport_id == transport + 1
    assert app.score_revision == revision and app.count_in_beats == 0
    assert app.run_at == pytest.approx(deadline)
    assert app.midi_input_at == received_at
    assert app.hardware_probe.events[-1]["at_s"] == pytest.approx(
        round(received_at-probe_start, 4))
    recorder = app.recorder
    assert recorder is not previous_recorder
    assert recorder.presses == [PlayedNote(note.pitch, pytest.approx(overshoot), None)]
    event = app.live_input.events[-1]
    assert event["received_at"] == received_at
    assert event["transport_id"] == app.transport_id
    assert event["source_id"] == note.source_id and event["status"] == "on_time"
    monkeypatch.setattr(app, "_update", original_update)
    # The first HTTP poll must retain the callback's recorder and held key.
    state = app.state()
    assert app.recorder is recorder and state["midi_notes"] == 1
    assert state["midi_held_pitches"] == [note.pitch]
    now[0] = received_at + (note.end-note.start)*60/app.plan.bpm
    app._receive(midi_note(note.pitch, is_on=False))
    assert recorder.presses[0].release == pytest.approx(now[0]-deadline)
    assert not app.live_input.held
    phrase = app.plan.active_phrase
    scored_phrase = replace(phrase, start=phrase.start+app.play_from_beat,
                            notes=tuple(n for n in phrase.notes
                                        if n.start >= phrase.start+app.play_from_beat))
    result = evaluate(scored_phrase, app.plan.hand, app.plan.bpm, recorder.presses)
    assert next(n.status for n in result.notes if n.note.source_id == note.source_id) == "correct"


@pytest.mark.parametrize("kind", MIDI_HANDOFFS)
def test_midi_during_preparation_is_ungraded_and_release_cannot_invent_attack(
        midi_handoff, monkeypatch, kind):
    app, now, deadline, note = midi_handoff(kind)
    transport = app.transport_id
    previous_recorder = app.recorder
    with monkeypatch.context() as patch:
        patch.setattr(app, "_update", lambda: pytest.fail("Input inside rest advanced transport"))
        now[0] = deadline - .001
        app._receive(midi_note(note.pitch))
        assert not app.running and app.recorder is previous_recorder
        assert previous_recorder is None or not previous_recorder.presses
        assert app.transport_id == transport and app.next_at == deadline
        assert app.live_input.events[-1]["status"] == "heard"
        assert not app.live_input.used
    now[0] = deadline
    app._receive(midi_note(note.pitch, is_on=False))
    assert app.running and app.run_at == pytest.approx(deadline)
    assert not app.recorder.presses and not app.live_input.held
    now[0] += .001
    app._receive(midi_note(note.pitch))
    assert len(app.recorder.presses) == 1
    assert app.live_input.events[-1]["status"] == "on_time"


@pytest.mark.parametrize("kind", MIDI_HANDOFFS)
def test_paused_midi_does_not_consume_handoff_and_resume_keeps_deadline(
        midi_handoff, monkeypatch, kind):
    app, now, deadline, note = midi_handoff(kind)
    now[0] = deadline - .25
    app.control("pause")
    transport = app.transport_id
    previous_recorder = app.recorder
    with monkeypatch.context() as patch:
        patch.setattr(app, "_update", lambda: pytest.fail("Paused input advanced transport"))
        now[0] += 30
        app._receive(midi_note(note.pitch))
        app._receive(midi_note(note.pitch, is_on=False))
        assert app.paused and not app.running and app.recorder is previous_recorder
        assert previous_recorder is None or not previous_recorder.presses
        assert app.next_at == deadline and app.transport_id == transport
        assert app.live_input.events[-1]["status"] == "heard"
    app.control("resume")
    assert app.next_at == pytest.approx(deadline + 30)
    now[0] = deadline + 30
    app._receive(midi_note(note.pitch))
    assert app.run_at == pytest.approx(deadline + 30)
    assert app.recorder.presses == [PlayedNote(note.pitch, 0, None)]
    assert app.live_input.events[-1]["status"] == "on_time"


def test_playing_and_non_note_midi_do_not_poll_transport(clocked_engine, monkeypatch):
    app, now = clocked_engine(connected=True)
    app.start()
    now[0] = app.run_at + .001
    with monkeypatch.context() as patch:
        patch.setattr(app, "_update", lambda: pytest.fail("Ordinary MIDI polled transport"))
        app._receive(midi_note(60))
        app._receive(midi_note(60, is_on=False))
        app._receive(SimpleNamespace(type="control_change", control=64, value=127, channel=0))
    app.control("restart")
    now[0] = app.next_at
    with monkeypatch.context() as patch:
        patch.setattr(app, "_update", lambda: pytest.fail("Non-note MIDI consumed handoff"))
        app._receive(SimpleNamespace(type="control_change", control=64, value=0, channel=0))
    assert not app.running and app.recorder is None


@pytest.mark.parametrize("preview", (False, True))
@pytest.mark.parametrize("overshoot", (0, .001))
def test_midi_settles_unpolled_source_before_next_attack(
        clocked_engine, monkeypatch, preview, overshoot):
    app, now = clocked_engine(grid=(0, .5, 1), meters=((0, 1, 8),),
                              connected=not preview, bpm=240)

    def no_render():
        raise ValueError("Unpolled MIDI handoff test omits engraving feedback")

    monkeypatch.setattr(app, "engraving", no_render)
    app.start()
    if not preview:
        record_clean(app)
    old_recorder = app.recorder
    old_presses = list(old_recorder.presses)
    transport = app.transport_id
    revision = app.score_revision
    phrase = app.plan.active_phrase
    deadline = app.run_at + (phrase.end-phrase.start)*60/app.plan.bpm \
        + app.visual_gap_beats*60/app.plan.bpm
    assert app.running and app.next_at == 0 and app.pending_result is None
    if preview:
        app._piano_connected = lambda: True
    now[0] = received_at = deadline + overshoot
    note = phrase.notes[0]
    app._receive(midi_note(note.pitch))
    assert app.run_at == pytest.approx(deadline)
    assert app.running and app.transport_id == transport + 1
    assert app.score_revision == revision and app.count_in_beats == 0
    assert app.plan.streak == (0 if preview else 1)
    assert old_recorder.presses == old_presses
    recorder = app.recorder
    assert recorder is not old_recorder
    assert recorder.presses == [PlayedNote(note.pitch, pytest.approx(overshoot), None)]
    assert app.midi_input_at == received_at
    event = app.live_input.events[-1]
    assert event["received_at"] == received_at
    assert event["status"] == "on_time" and event["source_id"] == note.source_id
    assert event["transport_id"] == app.transport_id
    now[0] += .02
    assert app.state()["midi_notes"] == 1
    assert app.recorder is recorder
    now[0] = received_at + (note.end-note.start)*60/app.plan.bpm
    app._receive(midi_note(note.pitch, is_on=False))
    assert recorder.presses[0].release == pytest.approx(now[0]-deadline)
    assert evaluate(phrase, app.plan.hand, app.plan.bpm, recorder.presses).notes[0].status == "correct"


def test_unpolled_source_keeps_predeadline_held_release_on_old_take(clocked_engine, monkeypatch):
    app, now = clocked_engine(grid=(0, .5, 1), meters=((0, 1, 8),),
                              connected=True, bpm=240)
    app.start()
    record_clean(app)
    recorder = app.recorder
    last = len(recorder.presses)-1
    held = recorder.presses[last]
    recorder.presses[last] = replace(held, release=None)
    recorder.active[held.pitch].append(last)
    run_at, transport = app.run_at, app.transport_id
    # Inside the short rest, while the last key from the old take is held.
    now[0] = run_at + 1*60/240 + .01
    monkeypatch.setattr(app, "_update", lambda: pytest.fail("Pre-deadline release settled transport"))
    app._receive(midi_note(held.pitch, is_on=False))
    assert app.recorder is recorder and app.transport_id == transport
    assert app.run_at == run_at and app.next_at == 0
    assert recorder.presses[last].release == pytest.approx(now[0]-run_at)


@pytest.mark.parametrize("excluded", ("perform", "review", "paused", "manual"))
def test_unpolled_source_does_not_advance_excluded_transport(
        clocked_engine, monkeypatch, excluded):
    app, now = clocked_engine(grid=(0, .5, 1), meters=((0, 1, 8),),
                              connected=True, bpm=240)
    app.start(mode="perform" if excluded == "perform" else "practice")
    record_clean(app)
    if excluded == "review":
        app.review_end_beat = .5
    elif excluded == "manual":
        app.auto = False
    elif excluded == "paused":
        app.control("pause")
    run_at, transport, recorder = app.run_at, app.transport_id, app.recorder
    now[0] = run_at + 1.5*60/240 + .001
    monkeypatch.setattr(app, "_update", lambda: pytest.fail("Excluded transport settled on MIDI"))
    app._receive(midi_note(60, is_on=False))
    assert app.run_at == run_at and app.transport_id == transport
    assert app.recorder is recorder and app.next_at == 0


@pytest.fixture
def peace_timing_engine(tmp_path, monkeypatch):
    """Real opening lesson, without loading a provider or launching a renderer."""
    from piano_teacher import server
    from piano_teacher.importing.pieces import import_piece
    path = Path(__file__).resolve().parents[1] / "midi/Peace_Piece_-_Bill_Evans_(Piano_Solo).midi"
    piece, _ = import_piece(path)
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    engines = []

    def create(hand, bpm=56, *, connected=False):
        app = PracticeEngine(tmp_path / str(len(engines)), enable_midi=False)
        engines.append(app)
        app.plan = LearningPlan(piece)
        app.plan.set_hand(hand)
        app.plan.set_bpm(bpm)
        if connected:
            app._piano_connected = lambda: True
        return app, now

    yield create
    for app in engines:
        app.db.close()


@pytest.mark.parametrize("hand", ("right", "left"))
@pytest.mark.parametrize("bpm", (30, 40, 56, 120))
def test_real_peace_preview_rest_is_four_beats_through_pause_and_next_copy(
        peace_timing_engine, hand, bpm):
    app, now = peace_timing_engine(hand, bpm)
    before = app.semantic_score()
    app.start()
    assert app.count_in_meter == [4, 4] and app.count_in_bar_beats == 4
    assert app.visual_gap_beats == 4
    source_end = app.run_at + 4.5*60/bpm
    now[0] = source_end + .21
    gap = app.state()
    assert gap["phase"] == "preview_gap"
    assert gap["practice_timeline"]["gap"]["meter"] == [4, 4]
    assert gap["practice_timeline"]["gap"]["source_meter"] == [1, 8]
    assert app.next_at == pytest.approx(source_end + 4*60/bpm)
    deadline = app.next_at
    now[0] = source_end + 2*60/bpm
    midpoint = app.state()
    assert midpoint["visual_scroll_beat"] == pytest.approx(6.5)
    app.control("pause")
    now[0] += 23
    assert app.state()["visual_scroll_beat"] == pytest.approx(6.5)
    app.control("resume")
    assert app.state()["visual_scroll_beat"] == pytest.approx(6.5)
    assert app.next_at == pytest.approx(deadline + 23)
    now[0] = deadline + 23 + .031
    repeated = app.state()
    assert repeated["running"] and repeated["count_in_beats"] == 0
    assert repeated["play_from_beat"] == 0
    assert repeated["visual_offset_beats"] == 8.5
    assert repeated["visual_scroll_beat"] == pytest.approx(8.5 + .031*bpm/60)
    assert repeated["revision"] == before["revision"]
    after = app.semantic_score()
    assert after["notes"] == before["notes"]
    assert after["notation_events"] == before["notation_events"]
    assert after["measures"] == before["measures"]
    assert after["measures"][0]["meter"] == [1, 8]
    assert app.plan.streak == 0 and not app.plan.mastered


@pytest.mark.parametrize("hand", ("right", "left"))
def test_real_peace_clean_repeat_uses_same_four_beat_rest_and_preserves_grading(
        peace_timing_engine, hand):
    app, now = peace_timing_engine(hand, connected=True)
    app.start()
    record_clean(app)
    source_end = app.run_at + 4.5*60/56
    now[0] = source_end + .21
    feedback = app.state()
    assert feedback["take_result"]["clean"]
    assert app.next_at == pytest.approx(source_end + 4*60/56)
    now[0] = app.next_at + .01
    repeated = app.state()
    assert repeated["running"] and repeated["count_in_beats"] == 0
    assert repeated["visual_scroll_beat"] == pytest.approx(8.5 + .01*56/60)
    assert repeated["streak"] == 1 and not app.plan.mastered
    assert repeated["revision"] == feedback["revision"]


@pytest.mark.parametrize("hand", ("right", "left"))
def test_real_peace_manual_retry_uses_same_preparation_meter_as_repeat(
        peace_timing_engine, hand):
    app, now = peace_timing_engine(hand)
    app.start()
    now[0] = app.run_at + 1
    app.control("restart")
    reversing = app.state()
    measure = reversing["practice_preparation"]["measure"]
    assert measure["duration_beats"] == 4
    assert measure["meter"] == [4, 4] and measure["source_meter"] == [1, 8]
    assert (measure["start_beat"], measure["end_beat"]) == (-4, 0)
    assert app.next_at == pytest.approx(app._preparation_at + 4*60/56)
    now[0] = app._preparation_at + 2*60/56
    preparing = app.state()
    assert preparing["practice_preparation"]["phase"] == "preparing"
    assert preparing["visual_scroll_beat"] == pytest.approx(-2)
    now[0] = app.next_at + .01
    repeated = app.state()
    assert repeated["running"] and repeated["count_in_beats"] == 0
    assert repeated["visual_scroll_beat"] == pytest.approx(.01*56/60)


def motion_sample(app, now, at):
    now[0] = at
    return app.state()


def assert_motion_rate(first, second, rate):
    seconds = (second["clock_sampled_at_ms"]-first["clock_sampled_at_ms"])/1000
    assert seconds > 0
    assert second["visual_scroll_beat"]-first["visual_scroll_beat"] == pytest.approx(rate*seconds)
    assert first["visual_scroll_speed"] == pytest.approx(rate)
    assert second["visual_scroll_speed"] == pytest.approx(rate)


@pytest.mark.parametrize("bpm", (40, 80, 120))
@pytest.mark.parametrize("grid,meters,length,stride", [
    ((0, .5, 4.5), ((0, 1, 8), (.5, 4, 4)), 4.5, 8.5),
    ((0, 3, 6), ((0, 3, 4),), 6, 9),
    ((0, 3, 7), ((0, 3, 4), (3, 4, 4)), 7, 10),
])
def test_forward_derivative_through_source_gap_and_repeat(
        clocked_engine, bpm, grid, meters, length, stride):
    app, now = clocked_engine(grid=grid, meters=meters, bpm=120)
    before = app.semantic_score()
    cached = app._source_model()
    source_notes = app.plan.active_phrase.notes
    app.control("tempo", bpm=bpm)
    app.start()
    run_at, rate = app.run_at, bpm/60
    samples = []
    for beat in (.25, .5, length-.125, length+.125, length+.5,
                 stride-.125, stride, stride+.125):
        sample = motion_sample(app, now, run_at+beat/rate)
        assert sample["visual_scroll_beat"] == pytest.approx(beat)
        samples.append(sample)
    for first, second in zip(samples, samples[1:]):
        assert_motion_rate(first, second, rate)
    assert samples[4]["phase"] == "preview_gap"
    assert samples[-1]["visual_offset_beats"] == stride
    assert app.run_at == pytest.approx(run_at+stride/rate)
    assert app._source_model() is cached
    assert app.semantic_score() == before
    assert app.plan.active_phrase.notes == source_notes


@pytest.mark.parametrize("bpm", (40, 80, 120))
@pytest.mark.parametrize("phase", (
    "count_in", "playing", "preview_gap", "clean_gap", "reverse", "preparing"))
def test_paused_derivative_is_zero_and_resume_preserves_motion(
        clocked_engine, monkeypatch, bpm, phase):
    app, now = clocked_engine(bpm=bpm, connected=phase == "clean_gap")

    def no_engraving():
        raise ValueError("Transport timing test omits engraving feedback")

    monkeypatch.setattr(app, "engraving", no_engraving)
    app.start()
    rate = bpm/60
    if phase == "clean_gap":
        record_clean(app)
    if phase in ("reverse", "preparing"):
        app.visual_offset_beats = 12
        now[0] = app.run_at+1/rate
        app.control("restart")
        if phase == "reverse":
            now[0] += app._visual_rewind_seconds/4
            rate = -5/app._visual_rewind_seconds  # Absolute beat 13 back to 8.
        else:
            now[0] = app._preparation_at+1/rate
    else:
        beat = -.25 if phase == "count_in" else (9 if "gap" in phase else 1)
        now[0] = app.run_at+beat/rate
    before = app.state()
    deadline = app.next_at
    app.control("pause")
    first = motion_sample(app, now, now[0]+10)
    second = motion_sample(app, now, now[0]+10)
    assert first["visual_scroll_beat"] == pytest.approx(before["visual_scroll_beat"])
    assert_motion_rate(first, second, 0)
    app.control("resume")
    resumed = app.state()
    assert resumed["visual_scroll_beat"] == pytest.approx(before["visual_scroll_beat"])
    assert resumed["visual_scroll_speed"] == pytest.approx(rate)
    if deadline:
        assert app.next_at == pytest.approx(deadline+20)
    following = motion_sample(app, now, now[0]+.05)
    assert_motion_rate(resumed, following, rate)


@pytest.mark.parametrize("bpm", (40, 80, 120))
def test_failed_recovery_derivative_preserves_same_copy_and_source_model(
        clocked_engine, monkeypatch, bpm):
    app, now = clocked_engine(bpm=bpm, connected=True)

    def no_engraving():
        raise ValueError("Transport timing test omits engraving feedback")

    monkeypatch.setattr(app, "engraving", no_engraving)
    before = app.semantic_score()
    cached = app._source_model()
    source_notes = app.plan.active_phrase.notes
    app.start()
    app.visual_offset_beats = 12
    rate = bpm/60
    failed = motion_sample(app, now, app.run_at+8/rate+.21)
    assert failed["take_result"]["clean"] is False
    measure = failed["practice_preparation"]["measure"]
    assert (measure["start_beat"], measure["end_beat"], measure["duration_beats"]) == (8, 12, 4)
    start, seconds = app._visual_rewind_at, app._visual_rewind_seconds
    first = motion_sample(app, now, start+seconds/4)
    second = motion_sample(app, now, start+seconds/2)
    reverse_rate = (8-(20+.21*rate))/seconds
    assert_motion_rate(first, second, reverse_rate)
    assert first["visual_scroll_beat"] == pytest.approx(20+.21*rate+reverse_rate*seconds/4)
    first = motion_sample(app, now, app._preparation_at)
    second = motion_sample(app, now, app._preparation_at+1/rate)
    assert first["visual_scroll_beat"] == pytest.approx(8)
    assert second["visual_scroll_beat"] == pytest.approx(9)
    assert_motion_rate(first, second, rate)
    deadline = app.next_at
    assert deadline == pytest.approx(app._preparation_at+4/rate)
    first = motion_sample(app, now, deadline-.01)
    second = motion_sample(app, now, deadline+.01)
    assert_motion_rate(first, second, rate)
    assert second["visual_scroll_beat"] == pytest.approx(12+.01*rate)
    assert second["visual_offset_beats"] == 12
    assert app.run_at == pytest.approx(deadline)
    assert app._source_model() is cached
    assert app.semantic_score() == before
    assert app.plan.active_phrase.notes == source_notes


@pytest.mark.parametrize("bpm", (40, 80, 120))
@pytest.mark.parametrize("adapt", (False, True))
def test_clean_handoff_derivative_preserves_deadline_and_source_model(
        clocked_engine, monkeypatch, bpm, adapt):
    app, now = clocked_engine(bpm=240 if adapt else bpm, connected=True)
    app.plan.bpm = bpm

    def no_engraving():
        raise ValueError("Transport timing test omits engraving feedback")

    monkeypatch.setattr(app, "engraving", no_engraving)
    before = app.semantic_score()
    cached = app._source_model()
    source_notes = app.plan.active_phrase.notes
    app.start()
    record_clean(app)
    recorder = app.recorder
    presses = list(recorder.presses)
    run_at, rate = app.run_at, bpm/60
    first = motion_sample(app, now, run_at+8/rate+.21)
    second = motion_sample(app, now, now[0]+.05)
    assert first["take_result"] == {"clean": True, "correct": 2, "total": 2}
    assert_motion_rate(first, second, rate)
    deadline = app.next_at
    assert deadline == pytest.approx(run_at+12/rate)
    last_gap = motion_sample(app, now, deadline-.01)
    opening = motion_sample(app, now, deadline)
    next_rate = opening["bpm"]/60
    assert (next_rate > rate) is adapt
    assert opening["visual_scroll_beat"] == pytest.approx(12)
    assert opening["visual_scroll_speed"] == pytest.approx(next_rate)
    assert last_gap["visual_scroll_beat"] == pytest.approx(12-.01*rate)
    following = motion_sample(app, now, deadline+.01)
    assert_motion_rate(opening, following, next_rate)
    assert following["visual_scroll_beat"] == pytest.approx(12+.01*next_rate)
    assert app.run_at == pytest.approx(deadline)
    assert app._source_model() is cached
    assert app.semantic_score() == before
    assert app.plan.active_phrase.notes == source_notes
    assert recorder.presses == presses  # Original attack/release seconds stay untouched.
    assert app.recorder is not recorder and not app.recorder.presses
