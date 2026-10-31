extends SceneTree

# Render-clock acceptance independent of HTTP, sound-card and live MIDI.
# The camera itself still uses the true engraved notehead coordinates.
var failures: Array[String] = []
var failure_count := 0

func check(ok: bool, explanation: String) -> void:
    if not ok:
        failure_count += 1
        if failure_count <= 10:
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
            "Rendered score accelerated outside 2%% rate bound at frame %d" % tick)
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
            "Timestamp jitter changed the tempo beyond 2%% at frame %d" % tick)
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
    # The final rest leads into the next repeat at exactly 1 beat/second.
    # Simulate a backend state callback delayed by 220ms after the boundary.
    var continuous = load("res://visual_transport_clock.gd").new()
    var rest_state := {"revision": 8, "transport_id": 12,
        "phase": "feedback", "bpm": 60.0, "running": false,
        "paused": false, "auto": true, "preview_only": false,
        "visual_scroll_beat": 7.0, "visual_scroll_speed": 1.0,
        "visual_target_beat": 8.0, "visual_offset_beats": 0.0,
        "play_from_beat": 0.0, "clock_beat": 4.0}
    continuous.accept(rest_state, base_ms, base_ms)
    check(absf(continuous.visual_beat(base_ms + 1000) - 8.0) < .0001,
        "Automatic rest reaches the next attack at uniform velocity")
    check(absf(continuous.visual_beat(base_ms + 1220) - 8.22) < .0001,
        "Automatic rest must not freeze at end while awaiting the engine")
    var next_state := {"revision": 8, "transport_id": 13,
        "phase": "playing", "bpm": 60.0, "running": true,
        "paused": false, "visual_offset_beats": 8.0,
        "play_from_beat": 0.0, "clock_beat": 0.22}
    continuous.accept(next_state, base_ms + 1220, base_ms + 1220)
    check(absf(continuous.visual_beat(base_ms + 1220) - 8.22) < .0001,
        "Delayed next-take acknowledgement cannot jerk the score")
    check(absf(continuous.visual_beat(base_ms + 1236) - 8.236) < .0001,
        "First attack retains a constant score velocity")
    var manual = load("res://visual_transport_clock.gd").new()
    rest_state["auto"] = false
    manual.accept(rest_state, base_ms, base_ms)
    check(absf(manual.visual_beat(base_ms + 1220) - 8.0) < .0001,
        "Non-automatic feedback must remain stopped at its boundary")
    rest_state["auto"] = true
    rest_state["paused"] = true
    manual.accept(rest_state, base_ms + 1220, base_ms + 1220)
    check(not manual.idle_continues_through_gap,
        "Explicit pause disables automatic rest continuation")
    var preview = load("res://visual_transport_clock.gd").new()
    rest_state["paused"] = false
    rest_state["auto"] = false
    rest_state["preview_only"] = true
    rest_state["phase"] = "preview_gap"
    preview.accept(rest_state, base_ms, base_ms)
    check(preview.visual_beat(base_ms + 1220) > 8.2,
        "MIDI-free preview also keeps the visual rest moving")


    # The backend's scheduled run_at is immutable across a measure, its
    # following rest, and the next take. Even a stale state response after
    # the rest boundary must not reschedule the camera.
    var epoch_clock = load("res://visual_transport_clock.gd").new()
    var idle_epoch := {"revision": 8, "transport_id": 11,
        "phase": "ready", "bpm": 60.0, "running": false, "paused": false,
        "clock_sampled_at_ms": 999000.0, "visual_scroll_speed": 0.0}
    epoch_clock.accept(idle_epoch, base_ms - 1000, base_ms - 1000)
    var epoch_gap := {"revision": 8, "transport_id": 12,
        "phase": "feedback", "bpm": 60.0, "running": false,
        "paused": false, "auto": true, "preview_only": false,
        "visual_scroll_beat": 7.0, "visual_scroll_speed": 1.0,
        "visual_target_beat": 8.0, "visual_offset_beats": 0.0,
        "play_from_beat": 0.0, "clock_beat": 4.0,
        "clock_sampled_at_ms": 1000000.0, "visual_run_at_ms": 993000.0,
        "visual_tempo_segments":[]}
    epoch_clock.accept(epoch_gap, base_ms, base_ms)
    check(absf(epoch_clock.visual_beat(base_ms + 1000) - 8.0) < .000001,
        "Absolute MIDI epoch puts the next measure at the rest deadline")
    epoch_gap["clock_sampled_at_ms"] = 1000400.0
    epoch_gap["visual_scroll_beat"] = 7.4
    # Simulated queued response arrived 300ms after the state was sampled.
    epoch_clock.accept(epoch_gap, base_ms + 400, base_ms + 700)
    check(absf(epoch_clock.visual_beat(base_ms + 700) - 7.7) < .000001,
        "Queued state must not re-anchor automatic rest motion")
    check(absf(epoch_clock.visual_beat(base_ms + 1220) - 8.22) < .000001,
        "Visual time moves beyond the downbeat without Python acknowledgement")
    var epoch_play := {"revision": 8, "transport_id": 13,
        "phase": "playing", "bpm": 60.0, "running": true,
        "paused": false, "visual_offset_beats": 8.0,
        "play_from_beat": 0.0, "clock_beat": 0.22,
        "clock_sampled_at_ms": 1001220.0, "visual_run_at_ms": 1001000.0,
        "visual_tempo_segments":[]}
    epoch_clock.accept(epoch_play, base_ms + 1220, base_ms + 1220)
    check(absf(epoch_clock.visual_beat(base_ms + 1220) - 8.22) < .000001,
        "Next measure uses identical epoch and graphical position")
    check(absf(epoch_clock.score_beat(base_ms + 1236) - .236) < .000001,
        "MIDI beat and graphical beat remain one mapping after the rest")
    # A rest written within a measure does not affect the transport state.
    var inside = load("res://visual_transport_clock.gd").new()
    var internal := {"revision": 40, "transport_id": 42,
        "phase": "playing", "bpm": 60.0, "running": true,
        "paused": false, "play_from_beat": 0.0,
        "visual_offset_beats": 0.0, "clock_beat": 0.0,
        "visual_run_at_ms": 1000000.0, "visual_tempo_segments":[],
        "clock_sampled_at_ms": 1000000.0}
    inside.accept(internal, base_ms, base_ms)
    for quarter in range(1, 41):
        var at: int = base_ms + quarter * 250
        # Written events: note measure 1, whole rest, note measure 3.
        # The renderer does not provide the clock with note/rest events.
        check(absf(inside.visual_beat(at) - quarter * .25) < .000001,
            "Internal rest/bar boundary changed visual velocity at %d" % quarter)
        check(absf(inside.score_beat(at) - quarter * .25) < .000001,
            "Internal rest/bar boundary diverged from grading time at %d" % quarter)

    # Variable source tempo, then one full silent measure at practice BPM.
    # The same absolute run_at is retained even when the feedback snapshot
    # arrives after the source has ended.
    var shaped_rest_clock = load("res://visual_transport_clock.gd").new()
    var shaped_idle := {"revision": 21, "transport_id": 19,
        "phase": "ready", "running": false, "paused": false,
        "clock_sampled_at_ms": 1000000.0, "bpm": 80.0,
        "visual_scroll_speed": 0.0}
    shaped_rest_clock.accept(shaped_idle,base_ms,base_ms)
    var visual_map: Array = [
        {"start_beat":0.0, "end_beat":4.0, "bpm":64.0},
        {"start_beat":4.0, "end_beat":8.0, "bpm":80.0},
        {"start_beat":8.0, "end_beat":12.0, "bpm":80.0}
    ]
    var shaped_play := {"revision":21, "transport_id":20,
        "phase":"playing", "running":true, "paused":false,
        "bpm":80.0, "clock_beat":0.0, "clock_elapsed_seconds":0.0,
        "visual_offset_beats":0.0, "play_from_beat":0.0,
        "visual_run_at_ms":1000000.0,
        "clock_sampled_at_ms":1000000.0,
        "visual_tempo_segments":visual_map,
        "tempo_segments":visual_map.slice(0,2)}
    shaped_rest_clock.accept(shaped_play,base_ms,base_ms)
    check(absf(shaped_rest_clock.visual_beat(base_ms+3750)-4.0)<.000001,
        "Shaped source reaches the tempo change at the MIDI deadline")
    check(absf(shaped_rest_clock.visual_beat(base_ms+6750)-8.0)<.000001,
        "Shaped source arrives at the appended measure without stalling")
    var shaped_gap := shaped_play.duplicate(true)
    shaped_gap["phase"] = "preview_gap"
    shaped_gap["running"] = false
    shaped_gap["preview_only"] = true
    shaped_gap["visual_scroll_beat"] = 8.0+(.25*80.0/60.0)
    shaped_gap["visual_scroll_speed"] = 80.0/60.0
    shaped_gap["clock_sampled_at_ms"] = 1007000.0
    shaped_rest_clock.accept(shaped_gap,base_ms+7000,base_ms+7150)
    check(absf(shaped_rest_clock.visual_beat(base_ms+7150)-(
        8.0+(.40*80.0/60.0)))<.000001,
        "Delayed shaped-tempo feedback cannot reanchor the score")
    check(absf(shaped_rest_clock.visual_beat(base_ms+9750)-12.0)<.000001,
        "Variable-tempo rest finishes at the exact next downbeat")
    var shaped_next := shaped_play.duplicate(true)
    shaped_next["transport_id"] = 21
    shaped_next["visual_offset_beats"] = 12.0
    shaped_next["visual_run_at_ms"] = 1009750.0
    shaped_next["clock_sampled_at_ms"] = 1009850.0
    shaped_next["clock_beat"] = .1*64.0/60.0
    shaped_rest_clock.accept(shaped_next,base_ms+9850,base_ms+9850)
    check(absf(shaped_rest_clock.visual_beat(base_ms+9850)-(
        12.0+.1*64.0/60.0))<.000001,
        "Shaped-tempo next attempt preserves camera position")
    check(absf(shaped_rest_clock.score_beat(base_ms+9850)-
        .1*64.0/60.0)<.000001,
        "Grading clock and camera use the same tempo-mapped epoch")

    # Recovery has its own explicit scheduled reverse and forward intervals.
    # Every timestamp is an absolute backend monotonic epoch, regardless of
    # how late the first recovery state arrives.
    var recovery_clock = load("res://visual_transport_clock.gd").new()
    recovery_clock.accept(shaped_idle,base_ms,base_ms)
    var recovery_state := {"revision":31, "transport_id":40,
        "phase":"recovering", "running":false, "paused":false,
        "bpm":80.0,"auto":true,
        "clock_sampled_at_ms":1002000.0,
        "visual_run_at_ms":1000000.0,"visual_tempo_segments":[],
        "visual_scroll_beat":6.0,"visual_scroll_speed":-4.0,
        "visual_offset_beats":0.0,"play_from_beat":0.0,
        "practice_preparation":{"phase":"reverse","measure":{
            "start_beat":4.0,"end_beat":8.0}},
        "visual_preparation_schedule":{
            "reverse_at_ms":1001500.0,"prepare_at_ms":1002500.0,
            "deadline_at_ms":1005500.0,
            "from_beat":8.0,"to_beat":4.0}}
    recovery_clock.accept(recovery_state,base_ms+2000,base_ms+2200)
    check(recovery_clock.retry_active,
        "Absolute recovery schedule must be accepted without a new camera")
    check(absf(recovery_clock.visual_beat(base_ms+2200)-5.2)<.000001,
        "Delayed recovery snapshot does not shift rewind origin")
    check(absf(recovery_clock.visual_beat(base_ms+2500)-4.0)<.000001,
        "Rewind reaches the exact scheduled preparation onset")
    check(absf(recovery_clock.visual_beat(base_ms+4000)-6.0)<.000001,
        "Preparation rest advances at scheduled practice tempo")
    check(absf(recovery_clock.visual_beat(base_ms+5500)-8.0)<.000001,
        "Retry rest meets the MIDI deadline without a visual hold")
    var resumed_shaped := recovery_state.duplicate(true)
    resumed_shaped["transport_id"] = 41
    resumed_shaped["phase"] = "playing"
    resumed_shaped["running"] = true
    resumed_shaped["visual_offset_beats"] = 8.0
    resumed_shaped["visual_run_at_ms"] = 1005500.0
    resumed_shaped["clock_sampled_at_ms"] = 1006500.0
    resumed_shaped["clock_beat"] = 64.0/60.0
    resumed_shaped["visual_tempo_segments"] = visual_map
    resumed_shaped["tempo_segments"] = visual_map.slice(0,2)
    recovery_clock.accept(resumed_shaped,base_ms+6500,base_ms+6500)
    check(absf(recovery_clock.visual_beat(base_ms+6500)-(
        8.0+64.0/60.0))<.000001,
        "Recovery playback must switch from preparation BPM to source tempo")
    check(absf(recovery_clock.score_beat(base_ms+6500)-64.0/60.0)<.000001,
        "Recovery visual clock must match the new MIDI assessment clock")

    # Once music starts, later pause/feedback polling cannot re-calibrate
    # the monotonic epoch and shift an already scheduled retry.
    var frozen_epoch = load("res://visual_transport_clock.gd").new()
    var calibration_idle := {"revision":1,"transport_id":1,"bpm":80.0,
        "running":false,"paused":false,"phase":"ready",
        "clock_beat":0.0,"visual_scroll_speed":0.0,
        "clock_sampled_at_ms":1000000.0}
    frozen_epoch.accept(calibration_idle,base_ms,base_ms+80)
    var original_offset: float = frozen_epoch.backend_offset_ms
    var started := calibration_idle.duplicate(true)
    started["running"] = true
    started["transport_id"] = 2
    started["phase"] = "playing"
    started["visual_run_at_ms"] = 1000000.0
    started["visual_tempo_segments"] = []
    started["clock_sampled_at_ms"] = 1000100.0
    frozen_epoch.accept(started,base_ms+100,base_ms+100)
    var stopped_again := started.duplicate(true)
    stopped_again["running"] = false
    stopped_again["paused"] = true
    stopped_again["phase"] = "paused"
    stopped_again["clock_sampled_at_ms"] = 1000250.0
    stopped_again["visual_scroll_speed"] = 0.0
    frozen_epoch.accept(stopped_again,base_ms+200,base_ms+200)
    check(frozen_epoch.backend_offset_ms == original_offset,
        "Pause may not re-calibrate the clock epoch after music begins")

    print("VISUAL_TRANSPORT_CLOCK_FAILURES:", failure_count)
    quit(0 if failure_count == 0 else 1)
