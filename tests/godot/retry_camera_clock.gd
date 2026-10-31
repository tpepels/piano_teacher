extends SceneTree

var failures: Array[String] = []

func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        print("FAIL:", label)

func _initialize() -> void:
    var Clock = load("res://retry_camera_clock.gd")
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
    clock.accept(recovering, 1000)
    check(clock.active, "feedback-phase auto-retry precomputes clock")
    check(absf(clock.beat_at(1000)-3.0) < .001, "reverse starts at captured beat")
    check(absf(clock.beat_at(1500)-1.5) < .001, "reverse speed is uniform")
    check(absf(clock.beat_at(2000)) < .001, "reverse ends at rest start")
    check(absf(clock.beat_at(3000)-1.0) < .001, "rest flows forward uniformly")
    check(absf(clock.beat_at(5990)-3.99) < .001, "rest reaches first attack")
    check(absf(clock.beat_at(6000)-4.0) < .001, "first attack has no jump")
    check(absf(clock.beat_at(6016)-4.016) < .001, "first frame has fixed tempo")
    # Late HTTP snapshots with jitter never change the same deadline.
    recovering["visual_scroll_beat"] = 0.91
    recovering["transition_in_seconds"] = 2.9
    clock.accept(recovering, 3100)
    check(absf(clock.beat_at(3100)-1.1) < .001, "poll jitter cannot shift rest clock")
    clock.accept({"phase": "playing", "revision": 1, "transport_id": 8}, 6100)
    check(absf(clock.beat_at(6100)-4.1) < .001, "playing keeps the retry clock")
    # Unrelated manual Play must not consume a stale recovery trajectory.
    clock.accept({"phase": "playing", "revision": 1, "transport_id": 42}, 6200)
    check(not clock.active, "unrelated transport releases previous retry clock")
    print("RETRY_CAMERA_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
