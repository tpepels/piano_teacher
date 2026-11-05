extends RefCounted
## Presentation-only frame owner. No reference to Main or backend commands.
## Collaborators are injected once; each frame receives only immutable
## state, one sampled beat, and the already projected visual position.
const LivingScore := preload("res://living_score.gd")
const ScoreView := preload("res://notation/shared/view_base.gd")

var practice_view
var settings_view
var lesson_view
var lesson_session
var score_effects
var demo_player
var frame_meter
var busy_presented: Variant = null
var last_strike_transport := -1
var last_strike_beat := -INF
var last_sync_report_ms := 0
var last_lead_tick := -999
var last_cursor_tick := -1

func _init(practice, settings, lesson, session, effects, demo, meter) -> void:
    practice_view = practice
    settings_view = settings
    lesson_view = lesson
    lesson_session = session
    score_effects = effects
    demo_player = demo
    frame_meter = meter

func _visible_noteheads() -> int:
    var renderer = practice_view.stage.renderer
    if renderer == null or not renderer.is_visible_in_tree():
        return 0
    var viewport := Rect2(Vector2.ZERO,renderer.size)
    var visible := 0
    for position in renderer.drawn_noteheads.values():
        if viewport.has_point(position):
            visible += 1
    return visible

func advance(state: Dictionary, beat: float, visual_beat: float,
        ticks: int, delta: float, busy: bool, screen: String,
        score_ready: bool, source_groups: Array,
        frame_diagnostics: bool = false, listen_diagnostics: bool = false,
        smoke: bool = false) -> Array:
    if frame_diagnostics and screen == "practice":
        var frame_result: Dictionary = frame_meter.record_frame(delta)
        if not frame_result.is_empty():
            frame_result["native_visible_noteheads"] = _visible_noteheads()
            frame_result["native_scanned_events"] = practice_view.stage.renderer.frame_scanned_events
            frame_result["phase"] = str(state.get("phase",""))
            print("PHASE8D_FRAME_INTERVALS:",JSON.stringify(frame_result))
    if busy_presented != busy:
        busy_presented = busy
        settings_view.present_busy(busy)
        practice_view.present_busy(busy)
        lesson_view.present_busy(busy)
    lesson_session.ensure_current(ticks)

    var listening: bool = str(state.get("mode","")) == "listen"
    var moving: bool = bool(state.get("running",false)) and not bool(state.get("paused",false))
    if demo_player != null and listening and moving:
        if bool(demo_player.get("loaded")) and not bool(demo_player.get("started")):
            demo_player.synchronize(state,beat)
        demo_player.keep_synchronized(
            beat,maxf(1.0,float(state.get("bpm",60.0))),
            state.get("tempo_segments",[]))
        if listen_diagnostics and ticks-last_sync_report_ms >= 1000:
            last_sync_report_ms = ticks
            print("PHASE8B_LISTEN_SOFTWARE_SYNC:",JSON.stringify(demo_player.sync_report()))

    var stage = practice_view.stage
    if stage.renderer != null and bool(state.get("loaded",false)):
        stage.renderer.present_clock(beat,visual_beat -
            float(stage.renderer.runway_origin_beat))
        # Only the ink visibility and empty barline projection change.
        # The backend clock, source grade and note buffers remain untouched.
        stage.renderer.present_ambient(
            screen == "practice" and score_ready and
            str(state.get("phase","")) in ["ready","paused","guided_complete",
                "performance_complete"],ticks)
    if stage.effects != null and moving:
        stage.effects.sync_beat(
            beat,maxi(1,int(round(float(state.get("count_in_bar_beats",4))))),
            bool(state.get("preview_only",false)) or listening)

    if state.is_empty() or not moving or not score_ready:
        last_strike_transport = -1
        return []
    var musical_clock: float = float(state.get("play_from_beat",0.0))+beat
    var transport: int = int(state.get("transport_id",0))
    var crossed: Array = []
    if last_strike_transport == transport and \
            musical_clock >= last_strike_beat and \
            musical_clock-last_strike_beat <= .5 and \
            (bool(state.get("preview_only",false)) or listening):
        crossed = LivingScore.groups_crossed(source_groups,last_strike_beat,musical_clock)
    last_strike_transport = transport
    last_strike_beat = musical_clock

    if smoke:
        var tick: int = int(floor(beat*4.0))
        var playhead: float = stage.renderer.size.x*ScoreView.PLAYHEAD_FRACTION
        var content_x: float = -stage.renderer.clock_beat*stage.renderer.timeline.pixels_per_beat
        if beat < 0.0 and tick != last_lead_tick:
            last_lead_tick = tick
            print("PHASE0_LEAD_BEAT:",beat," CONTENT_X:",content_x,
                " CURSOR_X:",playhead," VISIBLE:",stage.renderer.visible)
        elif beat >= 0.0 and tick != last_cursor_tick:
            last_cursor_tick = tick
            print("PHASE0_VISIBLE_NOTES:",_visible_noteheads(),
                " PANEL_WIDTH:",stage.score_frame.size.x," CONTENT_X:",content_x)
            print("PHASE0_CURSOR_BEAT:",musical_clock," SCREEN_X:",playhead,
                " VISIBLE:",stage.renderer.visible," CONTENT_X:",content_x)
    return crossed
