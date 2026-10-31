extends RefCounted
## Publish an accepted immutable backend snapshot to the visual subsystems.
## Network sequencing and stale-response rejection remain in Main.
## Never reconstruct musical time or grade MIDI input here.

static func present(app, parsed: Dictionary, sample_started_ms: int) -> void:
    app.last_state = parsed
    app._present_fingering_status(parsed.get("fingering",{}))
    app.lesson_view.present_context(parsed, app.action_pending)
    app.settings_view.present_calibration(
        parsed.get("midi_calibration", {}), int(parsed.get("midi_offset_ms", 0)))
    app.lesson_session.update_context(parsed, Time.get_ticks_msec())
    app._update_visual_frame_rate(parsed)
    app._clear_assessed_effects_in_ungraded_mode(parsed)
    # Low-latency local polling only while playing from a connected piano.
    # The backend remains authoritative; Godot never guesses note scoring.
    if app.state_poll_timer != null:
        var live_rate := (app.current_screen == "practice"
            and not str(parsed.get("device", "")).is_empty())
        # Note-on cues arrive via loopback datagrams within the next frame;
        # full-state projections can now poll slightly less often.
        var interval := 0.08 if live_rate else 0.15
        if absf(app.state_poll_timer.wait_time - interval) > 0.001:
            app.state_poll_timer.wait_time = interval
    app.settings_view.present_practice(parsed, app.current_screen == "settings")
    # The backend sampled the clock during this round trip. Estimate
    # that sample at the midpoint so music never waits for the poll interval.
    var started_ms: int = app.state_request_started_ms if sample_started_ms < 0 else sample_started_ms
    var received_ms: int = Time.get_ticks_msec()
    app.last_state_tick = int((started_ms + received_ms) / 2.0)
    app.visual_transport_clock.accept(parsed, app.last_state_tick, received_ms)
    if app.demo_player != null and bool(parsed.get("loaded",false)):
        app.demo_player.synchronize(parsed, app._transport_beat_now())
    # ScoreAssetSession owns revision invalidation and the score_ready handshake.
    app.score_session.update_context(parsed, received_ms)
    app.practice_view.present(parsed, app._native_score_ready(), app.action_pending,
        app.demo_player != null and bool(app.demo_player.get("audio_error")))
    if not bool(parsed.get("loaded",false)):
        app._refresh_score_status()
        return
    var phase: String = str(parsed.get("phase","ready"))
    if app.phase0_smoke_mode and phase != app.phase0_last_phase:
        app.phase0_last_phase = phase
        print("PHASE0_PHASE:",phase)
    app.score_effects.marks = []
    for marker in parsed.get("feedback_marks", []):
        app.score_effects.marks.append(marker)
    app._consume_live_piano_hits(parsed)

    app.practice_view.present_busy(app.action_pending)
    app.practice_view.consider_piano_start(sample_started_ms < 0, app.current_screen == "practice")
    app._refresh_score_status()
