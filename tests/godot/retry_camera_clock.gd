extends SceneTree
# Automatic retry on the one presentation clock: the reverse, the rest bar and
# the next MIDI deadline are absolute backend epochs (visual_preparation_schedule).
# Nothing is derived from a delayed "transition_in_seconds" snapshot.

var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("FAIL:" + label)

func near(actual: float, expected: float) -> bool:
    return absf(actual - expected) < .001

func _initialize() -> void:
    var Clock = load("res://visual_transport_clock.gd")
    check(Clock != null, "retry clock loads inside Godot project")
    if Clock == null:
        print("RETRY_CAMERA_FAILURES:", failures.size())
        quit(1)
        return
    var clock = Clock.new()
    # Local time = backend time + 1000 ms, calibrated on a stationary sample.
    clock.accept({"phase": "ready", "revision": 1, "transport_id": 6, "bpm": 60.0,
        "running": false, "paused": false, "clock_sampled_at_ms": 0.0}, 1000, 1000)
    var recovering := {
        "phase": "feedback", "revision": 1, "transport_id": 7, "bpm": 60.0,
        "running": false, "paused": false, "clock_sampled_at_ms": 0.0,
        "visual_scroll_beat": 3.0,
        "practice_preparation": {"phase": "reverse", "measure": {
            "start_beat": 0.0, "end_beat": 4.0, "duration_beats": 4.0}},
        "visual_preparation_schedule": {
            "reverse_at_ms": 0.0, "prepare_at_ms": 1000.0, "deadline_at_ms": 5000.0,
            "from_beat": 3.0, "to_beat": 0.0}}
    # Without the authored schedule there is no retry trajectory to invent.
    var unscheduled := recovering.duplicate(true)
    unscheduled.erase("visual_preparation_schedule")
    clock.accept(unscheduled, 1000, 1000)
    check(not clock.retry_active, "a recovery state without a backend schedule starts no retry clock")
    clock.accept(recovering, 1000, 1000)
    check(clock.retry_active, "feedback-phase auto-retry precomputes clock")
    check(near(clock.visual_beat(1000), 3.0), "reverse starts at captured beat")
    check(near(clock.visual_beat(1500), 1.5), "reverse speed is uniform")
    check(near(clock.visual_beat(2000), 0.0), "reverse ends at rest start")
    check(not clock.retry_preparing(1999) and clock.retry_preparing(2000),
        "preparation starts exactly at the scheduled epoch")
    check(near(clock.visual_beat(3000), 1.0), "rest flows forward uniformly")
    check(near(clock.visual_beat(5990), 3.99), "rest reaches first attack")
    check(near(clock.visual_beat(6000), 4.0), "first attack has no jump")
    check(near(clock.visual_beat(6016), 4.016), "first frame has fixed tempo")
    check(clock.retry_preparing(5999) and not clock.retry_preparing(6000),
        "preparation ends at the MIDI deadline")
    # A late, jittered poll of the same recovery cannot move its deadline.
    recovering["visual_scroll_beat"] = 0.91
    recovering["clock_sampled_at_ms"] = 2050.0
    clock.accept(recovering, 3100, 3180)
    check(near(clock.visual_beat(3100), 1.1), "poll jitter cannot shift rest clock")
    clock.accept({"phase": "playing", "revision": 1,
        "transport_id": 8, "running": true, "paused": false,
        "clock_beat": .1, "visual_offset_beats": 0.0, "play_from_beat": 4.0,
        "bpm": 60.0}, 6100, 6100)
    check(near(clock.visual_beat(6100), 4.1), "playing keeps the retry clock")
    check(near(clock.score_beat(6100), .1), "score and retry camera use same epoch")
    check(near(clock.retry_count_in_beat(6000), 0.0), "count-in shares the same downbeat")
    check(near(clock.retry_count_in_beat(5000), -1.0), "count-in counts down to the deadline at practice tempo")
    # Unrelated manual Play must not consume a stale recovery trajectory.
    clock.accept({"phase": "playing", "revision": 1,
        "transport_id": 42, "running": true, "paused": false,
        "clock_beat": 0.0, "bpm": 60.0}, 6200, 6200)
    check(not clock.retry_active, "unrelated transport releases previous retry clock")
    print("RETRY_CAMERA_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
