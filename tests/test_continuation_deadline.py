"""One graded deadline per automatic continuation (R1 F1: P1/M1/P2/P3/M2).

Godot passes the offscreen reading horizon with Start
(continuous_horizon_beats) and, for a manual Retry, the lead of the world
position it reserved (presentation_lead_seconds). The engine must decide
each next take's run_at once, announce exactly that value as
score_queue_next while the rest runs, and start the take with it. Before
the fix the engine added the reading horizon a second time when the take
started, so the graded beat trailed the admitted ink by (horizon - rest)
beats, and clean repeats were announced only after they had started.
"""
from __future__ import annotations

import pytest

from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.practice import PlayedNote
from piano_teacher.server import PracticeEngine

HORIZON = 9.5  # beats; larger than the 4-beat written rest, as in the app
BPM = 80


@pytest.fixture
def engine(tmp_path, monkeypatch):
    from piano_teacher import server
    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    created = []

    def create(*, connected=True, piece_bpm=BPM):
        notes = (Note(0.0, 1.0, 60, 0, 0, "right", "n0"),
                 Note(4.0, 5.0, 62, 0, 0, "right", "n1"))
        piece = Piece("Continuation", piece_bpm, notes,
                      (Phrase(1, 1, 2, 0, 8, notes),),
                      bar_boundaries=(0, 4, 8), time_signatures=((0, 4, 4),))
        app = PracticeEngine(tmp_path / str(len(created)), enable_midi=False)
        created.append(app)
        app.plan = LearningPlan(piece, consolidate=True)
        app.fingerprint = "continuation-fixture"
        app.plan.set_bpm(piece_bpm)
        app.plan.bpm = BPM  # practising below the target tempo
        if connected:
            app.midi.port = object()

        def no_engraving():
            raise ValueError("Deadline tests omit engraving feedback")

        monkeypatch.setattr(app, "engraving", no_engraving)
        return app, now

    yield create
    for app in created:
        app.db.close()


def play_clean(app):
    phrase = app.plan.active_phrase
    spb = 60.0 / app.plan.bpm
    app.recorder.presses = [
        PlayedNote(n.pitch, (n.start - phrase.start) * spb,
                   (n.end - phrase.start) * spb - .02)
        for n in phrase.notes]


def finish_take(app, now):
    phrase = app.plan.active_phrase
    end_at = app.visual_transport.run_at + (phrase.end - phrase.start) * 60 / app.plan.bpm
    now[0] = end_at + .21
    return end_at, app.state()


def start_with_horizon(app):
    app.control("start", continuous_horizon_beats=HORIZON)
    assert app.running


def test_clean_repeat_is_announced_during_rest_and_starts_at_that_deadline(engine):
    app, now = engine()
    start_with_horizon(app)
    play_clean(app)
    end_at, rest = finish_take(app, now)
    assert rest["phase"] == "feedback" and rest["take_result"]["clean"]
    plan = rest.get("score_queue_next")
    # Announced while the rest runs, early enough to admit the ink offscreen.
    assert plan is not None
    expected = end_at + HORIZON * 60 / BPM
    assert plan["deadline_at_ms"] == pytest.approx(expected * 1000)
    assert plan["source_from_beat"] == 0
    assert plan["transport_id"] == app.transport_id + 1
    assert plan["count_in_beats"] == 4
    now[0] = expected + .01
    started = app.state()
    assert started["running"] and started["transport_id"] == plan["transport_id"]
    # No second reading lead: graded run_at IS the announced deadline.
    assert app.visual_transport.run_at == pytest.approx(expected)
    assert started["score_queue_next"]["plan_id"] == plan["plan_id"]


def test_tempo_step_after_clean_take_keeps_the_announced_deadline(engine):
    app, now = engine(piece_bpm=2*BPM)
    start_with_horizon(app)
    bpm = app.plan.bpm
    play_clean(app)
    _, rest = finish_take(app, now)
    deadline = rest["score_queue_next"]["deadline_at_ms"] / 1000
    now[0] = deadline + .01
    started = app.state()
    assert started["bpm"] > bpm  # the automatic tempo step happened at settlement
    assert app.visual_transport.run_at == pytest.approx(deadline)


def test_failed_take_repeat_starts_at_the_announced_preparation_deadline(engine):
    app, now = engine()
    start_with_horizon(app)
    _, recovering = finish_take(app, now)  # silent take: nothing played
    assert recovering["phase"] in ("feedback", "recovering")
    plan = recovering["score_queue_next"]
    assert plan["deadline_at_ms"] == pytest.approx(
        recovering["visual_preparation_schedule"]["deadline_at_ms"])
    deadline = plan["deadline_at_ms"] / 1000
    # The preparation deadline already includes the reading horizon once.
    rest = recovering["practice_preparation"]["measure"]["duration_beats"]
    prepare_at = recovering["visual_preparation_schedule"]["prepare_at_ms"] / 1000
    assert deadline == pytest.approx(
        prepare_at + max(rest, HORIZON) * 60 / app.plan.bpm)
    now[0] = deadline + .01
    started = app.state()
    assert started["running"]
    # Before the fix the continue route added (horizon - rest) again here.
    assert app.visual_transport.run_at == pytest.approx(deadline)
    assert started["transport_id"] == plan["transport_id"]
    assert started["score_queue_next"]["plan_id"] == plan["plan_id"]


def test_manual_retry_runs_at_the_renderer_reserved_world_deadline(engine):
    app, now = engine()
    start_with_horizon(app)
    now[0] = app.visual_transport.run_at + 1.0
    lead = 7.25  # seconds to the world position Godot reserved for the retry
    pressed = now[0]
    app.control("restart", presentation_lead_seconds=lead,
                continuous_horizon_beats=HORIZON)
    preparing = app.state()
    plan = preparing["score_queue_next"]
    assert plan["deadline_at_ms"] == pytest.approx((pressed + lead) * 1000)
    now[0] = pressed + lead + .01
    started = app.state()
    assert started["running"]
    assert app.visual_transport.run_at == pytest.approx(pressed + lead)


def test_preview_repeat_is_announced_and_starts_unchanged(engine):
    app, now = engine(connected=False)
    start_with_horizon(app)
    _, gap = finish_take(app, now)
    plan = gap["score_queue_next"]
    assert gap["phase"] == "preview_gap"
    deadline = plan["deadline_at_ms"] / 1000
    now[0] = deadline + .01
    started = app.state()
    assert started["running"]
    assert app.visual_transport.run_at == pytest.approx(deadline)
    assert started["score_queue_next"]["plan_id"] == plan["plan_id"]


@pytest.mark.parametrize("renderer_lead", [0.0, 11.0])
def test_resume_in_rest_reannounces_a_deadline_its_ink_can_still_meet(engine, renderer_lead):
    app, now = engine()
    start_with_horizon(app)
    play_clean(app)
    _, rest = finish_take(app, now)
    before = rest["score_queue_next"]
    deadline = before["deadline_at_ms"] / 1000
    app.control("pause")
    assert "score_queue_next" not in app.state()
    now[0] += 12.0
    resumed_at = now[0]
    # Godot reports where fresh ink can still be admitted offscreen (the old
    # copy may have scrolled into view while paused).
    app.control("resume", continuous_horizon_beats=HORIZON,
                presentation_lead_seconds=renderer_lead)
    plan = app.state()["score_queue_next"]
    expected = max(deadline + 12.0, resumed_at + renderer_lead,
                   resumed_at + HORIZON * 60 / BPM)
    assert plan["deadline_at_ms"] / 1000 == pytest.approx(expected)
    assert plan["plan_id"] != before["plan_id"], "fresh ink, not the old copy"
    now[0] = expected + .01
    app.state()
    assert app.running
    assert app.visual_transport.run_at == pytest.approx(expected)


def test_unannounced_continuation_still_gets_a_full_offscreen_lead(engine):
    app, now = engine()
    start_with_horizon(app)
    play_clean(app)
    finish_take(app, now)
    # A policy that changes the source opening at settlement cannot reuse
    # the announced deadline; it gets the full horizon from now and counts
    # its last bar in itself.
    app.visual_transport.announced_continuation = None
    now[0] = app.visual_transport.next_at + .01
    pressed = now[0]
    app.state()
    assert app.running
    assert app.visual_transport.run_at >= pressed + HORIZON * 60 / BPM - 1e-6
    assert app.count_in_beats == 4


def test_renderer_binds_by_plan_identity_and_counts_in_before_announced_deadline():
    """Godot side: identity binding (no onset tolerance) and the count-in bar."""
    import shutil
    import subprocess
    from pathlib import Path
    godot = shutil.which("godot") or shutil.which("godot4")
    if not godot:
        pytest.skip("Godot unavailable")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [godot, "--headless", "--path", str(root / "godot"), "--audio-driver", "Dummy",
         "--script", str(root / "tests/godot/continuation_plan.gd")],
        capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    assert "CONTINUATION_PLAN_FAILURES:0" in output, output
    assert result.returncode == 0, output


def _rest_plans_then_start(app, now, *, step=0.25, limit=60.0):
    """Poll the rest like Godot does; return (announced plans, first running state)."""
    plans = []
    end = now[0] + limit
    while now[0] < end:
        state = app.state()
        if state.get("running") and state.get("transport_id") != _rest_plans_then_start.tid:
            return plans, state
        plan = state.get("score_queue_next")
        if plan is not None and not state.get("running"):
            plans.append(plan)
        now[0] += step
    raise AssertionError("no next take started")


@pytest.mark.parametrize("scenario", ["clean", "tempo_step", "failed", "retry"])
def test_an_announced_continuation_is_exactly_the_take_that_runs(engine, scenario):
    app, now = engine(piece_bpm=2 * BPM if scenario == "tempo_step" else BPM)
    start_with_horizon(app)
    _rest_plans_then_start.tid = app.transport_id
    if scenario == "retry":
        now[0] = app.visual_transport.run_at + 1.0
        app.control("restart", presentation_lead_seconds=7.0,
                    continuous_horizon_beats=HORIZON)
    else:
        if scenario != "failed":
            play_clean(app)
        finish_take(app, now)
    plans, started = _rest_plans_then_start(app, now)
    assert plans, "this continuation is predictable and must be announced"
    assert len({p["plan_id"] for p in plans}) == 1, "one announcement per rest"
    plan = plans[-1]
    assert started["transport_id"] == plan["transport_id"]
    assert started["play_from_beat"] == pytest.approx(plan["source_from_beat"])
    assert app.visual_transport.run_at * 1000 == pytest.approx(plan["deadline_at_ms"])
    assert started["bpm"] == pytest.approx(plan["bpm"])
    if scenario == "tempo_step":
        assert plan["bpm"] > BPM, "the count-in is announced at the stepped tempo"


@pytest.mark.parametrize("reason", ["mastery", "feedback_reengraving", "remediation"])
def test_a_take_whose_settlement_can_reroute_is_not_announced(engine, monkeypatch, reason):
    app, now = engine()
    if reason == "mastery":
        app.plan.bpm = app.plan.target_bpm
        from piano_teacher.lesson_settings import SETTINGS
        app.plan.streak = SETTINGS.clean_runs_to_master - 1
    elif reason == "feedback_reengraving":
        monkeypatch.setattr(type(app.plan), "accepts_performance_feedback",
                            property(lambda _plan: True))
    else:
        monkeypatch.setattr(app, "_decide_remediation", lambda result: setattr(
            app, "_decided_remediation", (app.plan.identity, "remedial section")))
    start_with_horizon(app)
    if reason != "remediation":
        play_clean(app)
    _, rest = finish_take(app, now)
    assert rest["phase"] in ("feedback", "recovering")
    assert "score_queue_next" not in rest
    assert app.visual_transport.announced_continuation is None
