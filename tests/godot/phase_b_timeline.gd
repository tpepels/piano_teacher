extends SceneTree
# Phase B acceptance: time-space geometry is independent of Verovio and BPM.
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("PHASE_B_FAIL: ", message)

func near(a: float, b: float, tolerance: float = .001) -> bool:
    return absf(a-b) <= tolerance

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Timeline = load("res://notation/shared/timeline.gd")
    var Clock = load("res://visual_transport_clock.gd")
    var Preview = load("res://notation/diagnostics/timeline_preview.gd")
    var scores := {
        "schema":"piano-teacher-score-model-v1", "beat_unit":"quarter",
        "revision":11, "duration_beats":7.0, "active_hand":"right",
        "measures":[
            {"number":5, "start_beat":0.0, "end_beat":3.0,
                "meter":[3,4], "clefs":{}, "keys":{}},
            {"number":6, "start_beat":3.0, "end_beat":7.0,
                "meter":[4,4], "clefs":{}, "keys":{}}],
        "notes":[
            {"id":"a", "onset_beats":0.0, "duration_beats":1.0,
                "midi_pitch":72, "hand":"right"},
            {"id":"b", "onset_beats":.25, "duration_beats":.25,
                "midi_pitch":75, "hand":"right"},
            {"id":"c", "onset_beats":1.0, "duration_beats":2.0,
                "midi_pitch":48, "hand":"left"},
            {"id":"d", "onset_beats":4.0, "duration_beats":.5,
                "midi_pitch":67, "hand":"right"}]}
    var timeline = Timeline.new()
    check(timeline.load_model(scores), "Accept independent score JSON")
    check(timeline.revision == 11, "Track authoritative score revision")
    check(timeline.measures.size() == 2, "Retain mixed measure boundaries")
    check(not timeline.set_density(0.0) and not timeline.set_density(INF),
        "Never silently accept nonphysical scroll density")
    check(timeline.set_density(100.0), "Tunable horizontal scale")
    check(near(timeline.x_at_beat(.25) - timeline.x_at_beat(0), 25.0),
        "Sixteenth note is separated by exactly 1/4 beat * px/beat")
    check(near(timeline.x_at_beat(3.0), 300.0),
        "Measure boundary is at exact musical coordinates")
    var playhead := 420.0
    var seek := 3.0
    var count_in := 2.5
    # Lead-in from -2.5 to 0 is one continuous time axis, even after seek.
    check(near(timeline.count_in_start(seek, count_in), .5),
        "Negative count-in is relative to the chosen starting measure")
    for clock_beat in [-2.5, -1.5, -.5, 0.0, .25, 1.0]:
        var screen: float = timeline.screen_x(seek, clock_beat,
            playhead, seek)
        check(near(screen, playhead-clock_beat*100.0),
            "No jump or timing change at count-in downbeat: %f" % clock_beat)
    check(near(timeline.screen_x(4.0, 1.0, playhead, seek), playhead),
        "A note after a seek crosses the fixed playhead at its original beat")
    var trial: Array = [40.0, 80.0, 120.0]
    for tempo in trial:
        var clock = Clock.new()
        var state := {"revision":11, "transport_id":7, "bpm":tempo,
            "running":true, "paused":false, "clock_beat":-2.5}
        var initial := 100000
        clock.accept(state, initial, initial)
        var previous_x: float = timeline.screen_x(4.0, clock.now(initial),
            playhead, 3.0)
        for tick in range(1, 301):
            var time_ms: int = initial + tick * 20
            if tick % 7 == 0:
                var sampled: int = time_ms-80 if tick % 14 == 0 else time_ms-10
                state["clock_beat"] = -2.5 + float(sampled-initial)*tempo/60000.0
                clock.accept(state, sampled, time_ms)
            var visible_x: float = timeline.screen_x(4.0,
                clock.now(time_ms), playhead, 3.0)
            var displacement: float = previous_x-visible_x
            var expected: float = timeline.pixels_per_second(tempo)*.020
            check(near(displacement, expected, .0008),
                "Fixed visual speed at %.0f BPM, frame %d" % [tempo,tick])
            previous_x = visible_x
        var stop_state: Dictionary = state.duplicate()
        stop_state["paused"] = true
        stop_state["running"] = false
        stop_state["clock_beat"] = clock.now(initial+6000)
        clock.accept(stop_state, initial+6000, initial+6000)
        var freeze_x: float = timeline.screen_x(4.0, clock.now(initial+6000),
            playhead, 3.0)
        check(near(timeline.screen_x(4.0, clock.now(initial+8500), playhead, 3.0),
            freeze_x), "Pause freezes the same pixels at %.0f BPM" % tempo)
    var prototype = Preview.new()
    get_root().add_child(prototype)
    prototype.size = Vector2(1150, 330)
    check(prototype.load_score(scores), "Preview consumes semantic contract")
    check(prototype.set_density(100.0), "Preview density configurable")
    prototype.present({"bpm":80, "running":true, "paused":false,
        "count_in_beats":2.5, "play_from_beat":3.0,
        "transport_id":7, "hand":"right"}, -2.5)
    check(near(prototype.timeline.screen_x(3.0,
        prototype.clock_beat, 1150.0 * .42, prototype.play_from_beat),
        1150.0*.42+250.0), "Prototype pre-roll uses the same timeline")
    check(prototype.timeline.model["schema"] == scores["schema"],
        "No SVG/PNG import in timeline preview")
    prototype.clear_score()
    check(not prototype.timeline.has_score(), "Score change clears stale note markers")
    var invalid: Dictionary = scores.duplicate(true)
    invalid["notes"][1]["id"] = "a"
    check(not timeline.load_model(invalid), "Reject duplicated source attack")
    check(timeline.revision == 11, "Invalid score may not replace valid data")
    print("PHASE_B_TIMELINE_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
