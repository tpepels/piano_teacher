extends SceneTree

# Run: godot --headless --path godot --script res://../tests/godot/tempo_timeline.gd
var failures := 0

func check(condition: bool, detail: String) -> void:
    if not condition:
        failures += 1
        print("TEMPO_TIMELINE_FAILURE: ", detail)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var clock = load("res://tempo_timeline.gd")
    var segments: Array = [
        {"start_beat":0.0, "end_beat":2.0, "bpm":30.0, "start_seconds":0.0},
        {"start_beat":2.0, "end_beat":4.0, "bpm":60.0, "start_seconds":4.0},
        {"start_beat":4.0, "end_beat":6.0, "bpm":120.0, "start_seconds":6.0},
    ]
    for pair in [[0.0,0.0],[1.0,2.0],[2.0,4.0],[3.0,5.0],
                 [4.0,6.0],[5.0,6.5],[6.0,7.0]]:
        var beat: float = pair[0]
        var seconds: float = pair[1]
        check(absf(clock.seconds_at_beat(beat,60.0,segments)-seconds)<.000001,
            "Listen WAV target disagrees with shaped tempo at beat %.1f" % beat)
        check(absf(clock.beat_at_seconds(seconds,60.0,segments)-beat)<.000001,
            "Visual score beat disagrees with WAV time %.1f" % seconds)
    check(absf(clock.seconds_at_beat(-2.0,60.0,segments)+2.0)<.000001,
        "Count-in uses preparation BPM before shaped exercise begins")
    check(absf(clock.seconds_at_beat(3.0,60.0,[])-3.0)<.000001,
        "Unshaped Listen preserves fixed BPM behavior")
    # Backend partial retries send local-zero segments, not absolute beats.
    var partial: Array = [
        {"start_beat":0.0, "end_beat":2.0, "bpm":60.0},
        {"start_beat":2.0, "end_beat":4.0, "bpm":120.0},
    ]
    check(absf(clock.seconds_at_beat(3.0,60.0,partial)-2.5)<.000001,
        "Partial retry WAV target uses local tempo map")
    print("TEMPO_TIMELINE_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
