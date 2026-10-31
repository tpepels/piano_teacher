extends RefCounted
## Presentation-only frame coordinator. The backend owns musical deadlines,
## MIDI scoring and transport time; this coordinator samples that clock once
## and distributes it to Listen, notation, effects and preview indications.
const LivingScore := preload("res://living_score.gd")

static func advance(app, delta: float) -> void:
    var transport_beat: float = app._transport_beat_now()
    # On-device frame intervals, opt-in only. delta is never fed back into
    # the backend tempo or score assessment; tests may call _process(0).
    if app.frame_diagnostics and app.current_screen == "practice":
        var frame_result: Dictionary = app.frame_meter.record_frame(delta)
        if not frame_result.is_empty():
            frame_result["native_visible_noteheads"] = app._visible_score_noteheads()
            frame_result["native_scanned_events"] = app.practice_view.stage.renderer.frame_scanned_events
            frame_result["phase"] = str(app.last_state.get("phase", ""))
            print("PHASE8D_FRAME_INTERVALS:", JSON.stringify(frame_result))
    # Animate short-lived hit pulses between state samples.
    var ticks: int = Time.get_ticks_msec()
    app.score_effects.prune_expired(ticks)
    app._read_live_midi()
    app.settings_view.present_busy(app.action_pending)
    app.practice_view.present_busy(app.action_pending)
    app.lesson_view.present_busy(app.action_pending)
    app.lesson_session.ensure_current(ticks)
    # Start Listen WAV on the actual negative-to-zero beat crossing at
    # frame rate, not on the next 150ms state poll. This preserves the
    # first note AND keeps its attack aligned with the engraved notehead.
    if app.demo_player != null and str(app.last_state.get("mode", "")) == "listen" \
            and bool(app.last_state.get("running", false)) \
            and not bool(app.last_state.get("paused", false)) \
            and bool(app.demo_player.get("loaded")) \
            and not bool(app.demo_player.get("started")):
        app.demo_player.synchronize(app.last_state, transport_beat)
    # Continuous Listen drift measurements are display/audio only and
    # never feed back into the MIDI grading or the Python transport.
    if app.demo_player != null and str(app.last_state.get("mode", "")) == "listen" \
            and bool(app.last_state.get("running", false)) \
            and not bool(app.last_state.get("paused", false)):
        app.demo_player.keep_synchronized(transport_beat,
            maxf(1.0, float(app.last_state.get("bpm", 60.0))),
            app.last_state.get("tempo_segments", []))
        if app.listen_sync_diagnostics and ticks - app.last_listen_sync_report_ms >= 1000:
            app.last_listen_sync_report_ms = ticks
            print("PHASE8B_LISTEN_SOFTWARE_SYNC:",
                JSON.stringify(app.demo_player.sync_report()))
    app._update_count_in()
    # Frame-accurate native projection uses the SAME clock as score and
    # count-in. No Verovio X positions or per-note speed correction.
    if app.practice_view.stage.renderer != null \
            and bool(app.last_state.get("loaded", false)):
        var score_clock: float = transport_beat
        app.practice_view.stage.renderer.present(app.last_state, score_clock,
            app._unrolled_score_beat(score_clock))
    # The stage's lighting follows exactly the musical beat used by the
    # moving Verovio notation. Preview/Listen use a neutral pulse; neither
    # this visual beat nor its glow can create grading events.
    if app.practice_view.stage.effects != null and bool(app.last_state.get("running", false)) \
            and not bool(app.last_state.get("paused", false)):
        app.practice_view.stage.effects.sync_beat(
            transport_beat,
            maxi(1, int(round(float(app.last_state.get("count_in_bar_beats", 4))))),
            bool(app.last_state.get("preview_only", false))
                or str(app.last_state.get("mode", "")) == "listen")
    # Source-event reactions still follow the backend clock. Native feedback
    # owns visible note cues and grading; no page-coordinate camera runs here.
    if app.last_state.is_empty() or not bool(app.last_state.get("running", false)) \
            or bool(app.last_state.get("paused", false)) or not app._native_score_ready():
        app.last_playhead_strike_transport = -1
        return
    var clock: float = transport_beat
    var musical_clock: float = float(app.last_state.get("play_from_beat", 0.0)) + clock
    var strike_transport: int = int(app.last_state.get("transport_id", 0))
    if app.last_playhead_strike_transport == strike_transport \
            and musical_clock >= app.last_playhead_strike_beat \
            and musical_clock - app.last_playhead_strike_beat <= .5:
        var onsets: Array = LivingScore.groups_crossed(
            app.living_chords, app.last_playhead_strike_beat, musical_clock)
        if not onsets.is_empty() and (bool(app.last_state.get("preview_only", false)) \
                or str(app.last_state.get("mode", "")) == "listen"):
            app._preview_note_arrivals(onsets)
    app.last_playhead_strike_transport = strike_transport
    app.last_playhead_strike_beat = musical_clock
    if app.phase0_smoke_mode:
        var tick: int = int(floor(clock * 4.0))
        var playhead: float = app.practice_view.stage.renderer.size.x * .42
        var content_x: float = -app.practice_view.stage.renderer.clock_beat * app.practice_view.stage.renderer.timeline.pixels_per_beat
        if clock < 0.0 and tick != app.phase0_last_lead_tick:
            app.phase0_last_lead_tick = tick
            print("PHASE0_LEAD_BEAT:", clock, " CONTENT_X:", content_x,
                " CURSOR_X:", playhead, " VISIBLE:", app.practice_view.stage.renderer.visible)
        elif clock >= 0.0 and tick != app.phase0_last_cursor_tick:
            app.phase0_last_cursor_tick = tick
            print("PHASE0_VISIBLE_NOTES:", app._visible_score_noteheads(),
                " PANEL_WIDTH:", app.practice_view.stage.score_frame.size.x, " CONTENT_X:", content_x)
            print("PHASE0_CURSOR_BEAT:", musical_clock, " SCREEN_X:", playhead,
                " VISIBLE:", app.practice_view.stage.renderer.visible, " CONTENT_X:", content_x)

