extends SceneTree

# Render-clock acceptance independent of HTTP, sound-card and live MIDI.
# The camera itself still uses the true engraved notehead coordinates.
var failures: Array[String] = []

func check(ok: bool, explanation: String) -> void:
    if not ok:
        failures.append(explanation)
        print("VISUAL_CLOCK_FAIL: ", explanation)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var clock = load("res://visual_transport_clock.gd").new()
    var base_ms := 100000
    var beat_rate := 68.0 / 60.0
    var state := {"revision": 3, "transport_id": 4, "bpm": 68.0,
        "running": true, "paused": false, "clock_beat": -3.0}
    clock.accept(state, base_ms, base_ms)
    var previous: float = clock.now(base_ms)
    var now_ms: int = base_ms
    for tick in range(1, 301):
        now_ms = base_ms + tick * 16
        if tick % 9 == 0:
            # Alternating 8-120 ms network delays; timestamped snapshots
            # must never push the score backward or cause a speed burst.
            var delay_ms: int = 120 if tick % 18 == 0 else 8
            var measured: int = now_ms - delay_ms
            state["clock_beat"] = -3.0 + float(measured - base_ms) * beat_rate / 1000.0
            clock.accept(state, measured, now_ms)
        var current: float = clock.now(now_ms)
        var observed_rate: float = (current - previous) / .016
        check(current >= previous, "Rendered music jumped backwards at frame %d" % tick)
        check(observed_rate >= beat_rate * 0.979 and observed_rate <= beat_rate * 1.021,
            "Rendered score accelerated outside 2% rate bound at frame %d" % tick)
        previous = current
    check(absf(previous - (-3.0 + 4.8 * beat_rate)) < .025,
        "A clean 68 BPM source clock should not noticeably drift")

    # Simulate *measurement* jitter as well as network latency. The previous
    # clock chased noisy readings at up to 6% different speeds. Musical
    # movement should not pump even when the observed timestamp is uncertain.
    state["clock_beat"] = -3.0
    var jitter_clock = load("res://visual_transport_clock.gd").new()
    jitter_clock.accept(state, base_ms, base_ms)
    var last_beat: float = jitter_clock.now(base_ms)
    for tick in range(1, 601):
        var at: int = base_ms + tick * 16
        if tick % 5 == 0:
            var measurement_ms: int = at - 24
            var noise_ms: int = (65 if tick % 15 == 0 else -50 if tick % 10 == 0 else 0)
            state["clock_beat"] = -3.0 + float(measurement_ms - base_ms + noise_ms) * beat_rate / 1000.0
            jitter_clock.accept(state, measurement_ms, at)
        var current: float = jitter_clock.now(at)
        var observed_rate: float = (current - last_beat) / .016
        check(observed_rate >= beat_rate * .979 and observed_rate <= beat_rate * 1.021,
            "Timestamp jitter changed the tempo beyond 2% at frame %d" % tick)
        check(current >= last_beat, "Timestamp jitter moved the score backwards")
        last_beat = current
    check(absf(last_beat - (-3.0 + 9.6 * beat_rate)) < .06,
        "Filtered jitter must still track real musical time within 60ms")

    # The downbeat has no special animation and cannot change tempo.
    var near_zero: float = clock.now(now_ms)
    check(near_zero > 0.0, "Count-in must cross the downbeat in source time")
    state["running"] = false
    state["paused"] = true
    state["clock_beat"] = near_zero
    clock.accept(state, now_ms, now_ms)
    var stopped: float = clock.now(now_ms)
    check(clock.now(now_ms + 3000) == stopped, "Pause must freeze musical time")
    state["running"] = true
    state["paused"] = false
    state["clock_beat"] = stopped
    clock.accept(state, now_ms + 3000, now_ms + 3000)
    check(clock.now(now_ms + 4000) > stopped + 1.1,
        "Resume must advance at the original tempo")
    state["transport_id"] = 5
    state["clock_beat"] = -2.5
    clock.accept(state, now_ms + 4100, now_ms + 4100)
    check(absf(clock.now(now_ms + 4100) + 2.5) < .0001,
        "Explicit Retry must reset to the new count-in without following the old attempt")
    state["bpm"] = 100.0
    state["clock_beat"] = -1.0
    clock.accept(state, now_ms + 4200, now_ms + 4200)
    check(absf(clock.now(now_ms + 4200) + 1.0) < .0001,
        "Explicit tempo change must reset the projection, not accelerate into it")
    check(clock.matches(state), "Clock must recognize the latest authoritative transport")
    print("VISUAL_TRANSPORT_CLOCK_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
