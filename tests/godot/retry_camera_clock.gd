extends SceneTree

var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("FAIL:", label)

func _initialize() -> void:
    var Clock = load("res://visual_transport_clock.gd")
    check(Clock != null, "retry clock loads inside Godot project")
    if Clock == null:
        print("RETRY_CAMERA_FAILURES:", failures.size())
        quit(1)
        return
    var clock = Clock.new()
    var recovering := {
        "phase": "feedback", "revision": 1, "transport_id": 7,
        "visual_scroll_beat": 3.0, "transition_in_seconds": 5.0,
        "bpm": 60,
        "practice_preparation": {"phase": "reverse", "measure": {
            "start_beat": 0.0, "end_beat": 4.0, "duration_beats": 4.0}}
    }
    clock.accept(recovering, 1000, 1000)
    check(clock.retry_active, "feedback-phase auto-retry precomputes clock")
    check(absf(clock.visual_beat(1000)-3.0) < .001, "reverse starts at captured beat")
    check(absf(clock.visual_beat(1500)-1.5) < .001, "reverse speed is uniform")
    check(absf(clock.visual_beat(2000)) < .001, "reverse ends at rest start")
    check(absf(clock.visual_beat(3000)-1.0) < .001, "rest flows forward uniformly")
    check(absf(clock.visual_beat(5990)-3.99) < .001, "rest reaches first attack")
    check(absf(clock.visual_beat(6000)-4.0) < .001, "first attack has no jump")
    check(absf(clock.visual_beat(6016)-4.016) < .001, "first frame has fixed tempo")
    # Late HTTP snapshots with jitter never change the same deadline.
    recovering["visual_scroll_beat"] = 0.91
    recovering["transition_in_seconds"] = 2.9
    clock.accept(recovering, 3100, 3100)
    check(absf(clock.visual_beat(3100)-1.1) < .001, "poll jitter cannot shift rest clock")
    clock.accept({"phase": "playing", "revision": 1,
        "transport_id": 8, "running": true, "paused": false,
        "clock_beat": .1, "visual_offset_beats": 0.0, "play_from_beat": 4.0,
        "bpm": 60.0}, 6100, 6100)
    check(absf(clock.visual_beat(6100)-4.1) < .001, "playing keeps the retry clock")
    check(absf(clock.score_beat(6100)-.1) < .001, "score and retry camera use same epoch")
    check(absf(clock.retry_count_in_beat(6000)) < .001, "count-in shares the same downbeat")
    # Unrelated manual Play must not consume a stale recovery trajectory.
    clock.accept({"phase": "playing", "revision": 1,
        "transport_id": 42, "running": true, "paused": false,
        "clock_beat": 0.0, "bpm": 60.0}, 6200, 6200)
    check(not clock.retry_active, "unrelated transport releases previous retry clock")
    print("RETRY_CAMERA_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
