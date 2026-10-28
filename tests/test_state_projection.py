"""Public practice-state projections must remain independent of engine state."""
from copy import deepcopy
import pytest
from piano_teacher.state_projection import hand_stage_rows, guided_learning_fields
from piano_teacher import state_projection as projection


@pytest.fixture
def snapshots():
    return projection


def test_unloaded_session_projects_activity_without_lesson_or_transport(snapshots):
    snapshot = snapshots.SessionSnapshot(
        mode="practice", feedback="Open music", device="USB Piano", revision=3,
        transport_id=7, activity=snapshots.ActivitySnapshot(
            sampled_at=100, midi_now=101, midi_input_at=99,
            midi_input_count=4, midi_input_note=60,
            midi_display={"midi_held_pitches": [60], "midi_visual_events": [],
                          "midi_next_pitches": []}))
    state = snapshots.project_session_state(snapshot)
    assert state["loaded"] is False and state["running"] is False
    assert state["paused"] is False and state["clock_beat"] == 0
    assert state["clock_sampled_at_ms"] == 100000
    assert state["midi_input_age"] == 2 and state["midi_input_count"] == 4
    assert state["midi_held_pitches"] == [60]
    assert state["device"] == "USB Piano" and state["transport_id"] == 7
    assert state["revision"] == 3 and state["feedback"] == "Open music"
    assert "phase" not in state and "bpm" not in state


def _timed_snapshot(snapshots, **timing):
    return snapshots.SessionSnapshot(
        mode="practice", feedback="Play", device="USB Piano", revision=4,
        transport_id=9, phase="playing",
        activity=snapshots.ActivitySnapshot(sampled_at=100),
        lesson=snapshots.LessonSnapshot(
            title="Mixed meter", kind="learn", first_bar=5, last_bar=7,
            measure_boundaries=(0, 3, 7, 10), exercise_index=1, exercise_count=4,
            duration_beats=10,
            level="original", level_number=2, level_count=2, required_notes=6,
            hand="right", hands=("right", "both"),
            lesson_steps=((1, "right", "r"), (1, "both", "b")),
            mastered=("r",), lesson_step=3, lesson_steps_mastered=1,
            fingerprint="source", piece_last_bar=12,
            tempo=snapshots.TempoSnapshot(
                bpm=120, original_bpm=140, target_bpm=140, start_bpm=40,
                rungs=(40, 90, 140))),
        timing=snapshots.TimingSnapshot(**{
            "sampled_at": 102, "now": 102, "run_at": 100,
            "running": True, "play_from_beat": 3,
            "visual_motion": (21, 2, 27), "visual_offset_beats": 14,
            "visual_gap_beats": 4, "scoring_available": True,
            "practice_timeline": {"gap": {"duration_beats": 4}},
            **timing}))


def test_loaded_session_projects_source_grid_clock_and_lesson_facts(snapshots):
    state = snapshots.project_session_state(_timed_snapshot(snapshots))
    assert state["clock_sampled_at_ms"] == 102000
    assert state["clock_beat"] == 4 and state["beat"] == 7
    assert state["current_bar"] == 7 and state["selected_start_bar"] == 5
    assert state["measure_boundaries"] == [0, 3, 7, 10]
    assert state["progress"] == pytest.approx(.7) and state["duration"] == 5
    assert state["visual_scroll_beat"] == 21 and state["visual_scroll_speed"] == 2
    assert state["visual_target_beat"] == 27 and state["score_loop_enabled"]
    assert state["exercise"] == 2 and state["lesson_step"] == 3
    assert state["hand_stages"] == [
        {"hand": "right", "active": True, "complete": True, "locked": False, "available": True},
        {"hand": "both", "active": False, "complete": False, "locked": False, "available": True}]
    assert state["tempo_rungs"] == [40, 90, 140]
    assert state["bpm"] == 120 and state["scoring_available"]


@pytest.mark.parametrize(("phase", "paused", "context", "expected_marks", "unmapped"), [
    ("playing", False, None, "live", 0),
    ("feedback", False, None, "settled", 2),
    ("recovering", False, None, "settled", 2),
    ("performance_complete", False, None, "settled", 2),
    ("review", False, None, "settled", 0),
    ("paused", True, "feedback", "settled", 2),
    ("paused", True, "playing", "live", 0),
])
def test_feedback_selection_preserves_phase_and_paused_context(
        snapshots, phase, paused, context, expected_marks, unmapped):
    from dataclasses import replace
    snapshot = _timed_snapshot(snapshots, paused=paused,
        feedback_marks=[{"status": "settled"}],
        live_marks=[{"status": "wrong", "pitch": 64, "beat": 2, "source_id": "n1"}],
        feedback_unmapped=2)
    snapshot = replace(snapshot, phase=phase,
        activity=replace(snapshot.activity, pause_context=context))
    state = snapshots.project_session_state(snapshot)
    assert state["feedback_marks"][0]["status"] == ("wrong" if expected_marks == "live" else "settled")
    assert state["feedback_unmapped"] == unmapped
    assert state["feedback"] == ("Paused" if paused else "Play")
    assert state["live_note_feedback"] == {
        "status": "wrong", "pitch": 64, "name": "E4", "count": 1, "source_id": "n1"}


def test_bounded_review_and_count_in_use_attempt_clock_without_visual_offset(snapshots):
    from dataclasses import replace
    snapshot = _timed_snapshot(snapshots, review_end_beat=7)
    state = snapshots.project_session_state(snapshot)
    assert state["duration"] == 2 and state["progress"] == 1
    before_start = replace(snapshot, phase="count_in", timing=replace(
        snapshot.timing, now=99, sampled_at=99))
    state = snapshots.project_session_state(before_start)
    assert state["clock_beat"] == -2 and state["beat"] == 3
    assert state["countdown"] == 1 and state["progress"] == 0


def test_activity_expiry_and_transition_use_their_captured_clocks(snapshots):
    from dataclasses import replace
    snapshot = _timed_snapshot(snapshots)
    snapshot = replace(snapshot, activity=snapshots.ActivitySnapshot(
        sampled_at=100, transition_now=104, notice_now=109,
        next_at=106, pending_transition=True, review_pending=True,
        retry_range={"first_bar": 5}, recovery_notice={"kind": "slowdown", "expires_at": 110}))
    state = snapshots.project_session_state(snapshot)
    assert state["transition_in_seconds"] == 2
    assert state["recovery_notice"] == {"kind": "slowdown"}
    assert state["review_range"] == {"first_bar": 5}
    expired = replace(snapshot, activity=replace(snapshot.activity, notice_now=110))
    assert snapshots.project_session_state(expired)["recovery_notice"] is None


def test_snapshot_copies_and_freezes_nested_values_and_each_response_is_independent(snapshots):
    from dataclasses import FrozenInstanceError, replace
    learner = {"completed_units": [{"source_indices": [2]}]}
    snapshot = replace(_timed_snapshot(snapshots), activity=snapshots.ActivitySnapshot(
        learner=learner, demo={"source_ids": ["source-2"]}))
    learner["completed_units"][0]["source_indices"].append(3)
    with pytest.raises(FrozenInstanceError):
        snapshot.mode = "perform"
    with pytest.raises(TypeError):
        snapshot.activity.learner["completed_units"][0]["source_indices"][0] = 9
    first = snapshots.project_session_state(snapshot)
    first["learner"]["completed_units"][0]["source_indices"].append(8)
    first["practice_timeline"]["gap"]["duration_beats"] = 99
    second = snapshots.project_session_state(snapshot)
    assert second["learner"]["completed_units"] == [{"source_indices": [2]}]
    assert second["practice_timeline"]["gap"]["duration_beats"] == 4
    assert second["demo"]["source_ids"] == ["source-2"]
    with pytest.raises(TypeError, match="snapshot"):
        snapshots.ActivitySnapshot(learner={"session": object()})


def test_guided_projection_overrides_timed_fields_using_only_captured_values(snapshots):
    from dataclasses import replace
    snapshot = replace(_timed_snapshot(snapshots), mode="learn",
        guided=snapshots.GuidedSnapshot(
            teaching={"phase": "guided_wait", "target_index": 1, "target_count": 2,
                      "expected_notes": [{"label": "C4"}]},
            fragment={"first_bar": 6, "last_bar": 7, "start_beat": 3, "end_beat": 10},
            phase="guided_wait", required_notes=3, duration_beats=7,
            feedback_marks=[{"target_id": "stage:2", "status": "expected"}]))
    state = snapshots.project_session_state(snapshot)
    assert state["phase"] == "guided_wait" and state["running"] is False
    assert state["clock_beat"] == 0 and state["progress"] == .5
    assert state["first_bar"] == 6 and state["required_notes"] == 3
    assert state["feedback"] == "Good. Next: C4."
    assert state["teaching"]["session_id"] == 9
    assert state["feedback_marks"] == [{"target_id": "stage:2", "status": "expected"}]


@pytest.mark.parametrize(("changes", "mode", "now", "expected"), [
    ({"paused": True, "running": True}, "practice", 101, "paused"),
    ({"teaching_phase": "guided_wait", "awaiting_score": True}, "learn", 101, "loading"),
    ({"teaching_phase": "guided_wait"}, "learn", 101, "guided_wait"),
    ({"running": True, "run_at": 102}, "practice", 101, "count_in"),
    ({"running": True, "run_at": 102}, "practice", 102, "playing"),
    ({"performance_complete": True, "pending_result": True}, "perform", 101, "performance_complete"),
    ({"preview_loop_pending": True, "pending_result": True}, "practice", 101, "preview_gap"),
    ({"review_complete": True, "performance_complete": True}, "practice", 101, "review"),
    ({"pending_result": True, "awaiting_score": True}, "practice", 101, "feedback"),
    ({"awaiting_score": True, "pending_rewind": True}, "practice", 101, "loading"),
    ({"pending_rewind": True}, "practice", 101, "recovering"),
    ({}, "practice", 101, "ready"),
])
def test_phase_precedence_is_independent_of_session_objects(snapshots, changes, mode, now, expected):
    assert snapshots.project_phase(snapshots.PhaseSnapshot(**changes), mode=mode, now=now) == expected


def test_engine_updates_then_captures_and_projects_under_its_lock(tmp_path, monkeypatch):
    from piano_teacher import server
    from piano_teacher.learning import LearningPlan
    from piano_teacher.music import Note, Phrase, Piece

    now = [100.0]
    monkeypatch.setattr(server.time, "monotonic", lambda: now[0])
    engine = server.PracticeEngine(tmp_path, enable_midi=False)
    notes = (Note(0, 1, 60, 0, 0, "right", "source-1"),)
    engine.plan = LearningPlan(Piece("Poll handoff", 120, notes,
        (Phrase(1, 1, 2, 0, 8, notes),), bar_boundaries=(0, 4, 8)))
    engine.plan.set_bpm(120)
    captured = []

    def project(snapshot):
        assert engine.lock._is_owned()
        captured.append(snapshot)
        return projection.project_session_state(snapshot)

    monkeypatch.setattr(server, "project_session_state", project)
    try:
        engine.start()
        previous_transport = engine.transport_id
        now[0] = 110.0
        state = engine.state()
        # Source ends at 106, then its two-second rest ends at 108. The
        # poll must publish the next take and preserve its musical deadline.
        assert state["transport_id"] == previous_transport+1
        assert state["phase"] == "playing" and state["clock_beat"] == 4
        assert captured[0].timing.run_at == 108
        state["count_in_meter"][0] = 99
        assert engine.count_in_meter == [4, 4]
        engine.control("stop")
        now[0] = 999.0
        replay = projection.project_session_state(captured[0])
        assert replay["phase"] == "playing" and replay["clock_beat"] == 4
        assert replay["transport_id"] == previous_transport+1
    finally:
        engine.db.close()


def test_warmup_unlocking_is_ordered():
    options = dict(kind="warmup", exercise_index=0, current_hand="right",
        available_hands=("right", "left", "both"), builtin_warmup=True,
        lesson_steps=[(0,"right","r"),(0,"left","l"),(0,"both","b"),(1,"right","x")])
    assert [x["locked"] for x in hand_stage_rows(**options, mastered={})] == [False, True, True]
    assert [x["locked"] for x in hand_stage_rows(**options, mastered={"r"})] == [False, False, True]
    assert hand_stage_rows(**{**options, "kind":"perform"}, mastered={}) == []


@pytest.mark.parametrize(("phase","expected","action"), [
    ("loading","Preparing a short idea to learn",None),
    ("disconnected","No piano connected","Connect your piano in Settings"),
    ("guided_complete","You found every note.","Ready to add rhythm?"),
    ("paused","Paused — resume when you are ready.",None),
    ("guided_wait","Play C + E together.",None),
])
def test_guided_projection_contract(phase,expected,action):
    teaching={"feedback":"Original","expected_notes":[{"label":"C"},{"label":"E"}],
              "target_index":0,"target_count":3}
    original=deepcopy(teaching)
    fragment={"first_bar":5,"last_bar":6,"start_beat":12.0,"end_beat":20.0}
    fields=guided_learning_fields(teaching=teaching,fragment=fragment,session_id=42,
             has_more_units=False,returning=False,phase=phase,
             required_notes=7,duration_beats=8.0)
    assert expected in fields["feedback"]
    assert fields["teaching"]["fragment"] == fragment and fields["teaching"]["session_id"] == 42
    assert fields["first_bar"] == 5 and fields["required_notes"] == 7
    assert fields["clock_beat"] == 0.0 and not fields["running"]
    assert fields["paused"] == (phase == "paused") and teaching == original
    assert ("next_action" in fields) == (action is not None)
    if action: assert action in fields["next_action"]


def test_guided_retry_more_units_and_wrong_note_hints():
    common=dict(fragment={"first_bar":1,"last_bar":1,"start_beat":0,"end_beat":4},
                session_id=2,phase="guided_complete",required_notes=3,duration_beats=4.0)
    retry=guided_learning_fields(**common,teaching={},has_more_units=False,returning=True)
    assert retry["next_action"] == "Retry rhythm from these bars."
    more=guided_learning_fields(**common,teaching={},has_more_units=True,returning=False)
    assert more["next_action"] == "Choose Next idea to learn the next part of the passage."
    wait=guided_learning_fields(**{**common, "phase":"guided_wait"},
          teaching={"expected_notes":[{"label":"F"}],"hint_reason":"wrong_note"},
          has_more_units=False,returning=False)
    assert wait["feedback"] == "Find F on the keyboard below, then try again."
