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

    # Both processes run on this machine's monotonic clock. Repeated HTTP
    # sampling error must never change BPM between authoritative transitions.
    for tempo in [40.0, 80.0, 120.0]:
        var fixed = load("res://visual_transport_clock.gd").new()
        var snapshot := {"revision": 8, "transport_id": 12, "bpm": tempo,
            "running": true, "paused": false, "clock_beat": -3.0}
        fixed.accept(snapshot, base_ms, base_ms)
        for tick in range(1, 501):
            var at: int = base_ms + tick * 20
            if tick % 8 == 0:
                # Persistent sampling bias used to engage a 2% tempo slew.
                snapshot.clock_beat = -3.0 + (tick * .020 + .065) * tempo / 60.0
                fixed.accept(snapshot, at, at)
            var expected: float = -3.0 + tick * .020 * tempo / 60.0
            check(absf(fixed.now(at) - expected) < .000001,
                "HTTP sampling error cannot change nominal BPM at %.0f BPM" % tempo)

    # The downbeat has no special animation and cannot change tempo.
    var stamped = load("res://visual_transport_clock.gd").new()
    var idle := {"revision":0, "transport_id":0, "bpm":80.0,
        "running":false, "paused":false, "clock_beat":0.0,
        "clock_sampled_at_ms":500000.0}
    stamped.accept(idle, base_ms, base_ms)
    var first := {"revision":1, "transport_id":1, "bpm":80.0,
        "running":true, "paused":false, "clock_beat":-3.0,
        "clock_sampled_at_ms":500100.0}
    # The first active HTTP midpoint is biased by 65ms. Its explicit backend
    # timestamp, calibrated while idle, still identifies the correct origin.
    stamped.accept(first, base_ms + 165, base_ms + 200)
    check(absf(stamped.now(base_ms + 200) - (-3.0 + .1*80.0/60.0)) < .000001,
        "Backend sample timestamp removes first-active-snapshot phase bias")
    check(absf(stamped.now(base_ms + 3200) - (-3.0 + 3.1*80.0/60.0)) < .000001,
        "Timestamped projection stays at exact BPM through the first onset")

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
    # Shaped clock must cross a tempo boundary without assuming one BPM.
    var shaped = load("res://visual_transport_clock.gd").new()
    var shaped_state := {
        "revision": 50, "transport_id": 52, "bpm": 60.0,
        "running": true, "paused": false,
        "clock_beat": 0.0, "clock_elapsed_seconds": 0.0,
        "tempo_segments": [
            {"start_beat":0.0, "end_beat":2.0, "bpm":48.0, "start_seconds":0.0},
            {"start_beat":2.0, "end_beat":4.0, "bpm":60.0, "start_seconds":2.5},
        ]
    }
    shaped.accept(shaped_state, base_ms, base_ms)
    check(absf(shaped.now(base_ms+2500)-2.0) < .00001,
        "Two-phase clock must reach second segment exactly at its boundary")
    check(absf(shaped.now(base_ms+3500)-3.0) < .00001,
        "Two-phase clock must use the target tempo after the boundary")
    check(absf(shaped.now(base_ms+4500)-4.0) < .00001,
        "Shaped score and MIDI deadlines must agree on phrase duration")
    shaped_state.running = false
    shaped_state.paused = true
    shaped_state.clock_beat = 4.0
    shaped_state.clock_elapsed_seconds = 4.5
    shaped.accept(shaped_state, base_ms+4500, base_ms+4500)
    check(absf(shaped.now(base_ms+5500)-4.0) < .00001,
        "Pausing a shaped clock must freeze its position")

    var partial = load("res://visual_transport_clock.gd").new()
    var partial_state := {
        "revision": 61, "transport_id": 62, "bpm": 60.0,
        "running": true, "paused": false,
        "play_from_beat": 4.0, "clock_beat": 0.0,
        "clock_elapsed_seconds": 0.0,
        "tempo_segments": [
            {"start_beat":0.0, "end_beat":4.0, "bpm":48.0, "start_seconds":0.0},
            {"start_beat":4.0, "end_beat":12.0, "bpm":60.0, "start_seconds":5.0},
        ]
    }
    partial.accept(partial_state, base_ms, base_ms)
    check(absf(partial.now(base_ms+5000)-4.0) < .00001,
        "Partial shaped seek must reach its tempo transition at local beat 4")
    check(absf(partial.now(base_ms+6000)-5.0) < .00001,
        "Partial shaped retry must continue at the second segment's BPM")
    print("VISUAL_TRANSPORT_CLOCK_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
