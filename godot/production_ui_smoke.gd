extends SceneTree
const ScoreView := preload("res://notation/shared/view_base.gd")
## Actual production scene -> embedded Python -> MIDI -> Verovio -> retained
## notation -> practice transport. No synthetic score-session doubles.
const DEFAULT_FIXTURE := "phase6_native_fixture.mid"
var fixture_name := DEFAULT_FIXTURE
var expected_fingerprint := ""
const MAX_MS := 95000

var app
var begun_ms := 0
var requested := false
var ready_seen := false
var transport_seen := false
var start_requested := false
var pause_requested := false
var pause_seen := false
var resume_requested := false
var initial_transport := -1
var ready_visible_since_ms := -1
var paused_sample_ms := -1
var paused_world_beat := NAN
var paused_pass_serial := -1
var ready_pass_serial := -1
var ready_world_origin := NAN
var ready_world_beat := NAN
var resumed_sample_ms := -1
var resumed_world_beat := NAN
var resumed_pass_serial := -1

func _initialize() -> void:
    call_deferred("_boot")

func _boot() -> void:
    var arguments: PackedStringArray = OS.get_cmdline_user_args()
    if not arguments.is_empty():
        fixture_name = arguments[0]
    if arguments.size() >= 2:
        expected_fingerprint = arguments[1]
    begun_ms = Time.get_ticks_msec()
    root.size = Vector2i(1280,800)
    var scene: PackedScene = load("res://main.tscn")
    if scene == null:
        _fail("Cannot load production main.tscn")
        return
    app = scene.instantiate()
    root.add_child(app)
    if not is_instance_valid(app) or app.score_session == null:
        _fail("Production scene did not initialize the score session")
        return
    print("PHASE6_PRODUCTION_SCENE_STARTED")

func _first_visible_head(renderer) -> String:
    # Paint metadata is produced by the actual retained notehead compositor.
    # Ignore copies outside the viewport and all non-note overlays.
    var window: Rect2 = Rect2(Vector2.ZERO,renderer.size)
    for identifier in renderer.drawn_noteheads:
        var point: Vector2 = renderer.drawn_noteheads[identifier]
        if window.has_point(point):
            return str(identifier)
    return ""

func _process(_delta: float) -> bool:
    if app == null or not is_instance_valid(app):
        return false
    if Time.get_ticks_msec() - begun_ms > MAX_MS:
        _fail("Production UI timed out phase=%s error=%s pending=%s" % [
            str(app.last_state.get("phase","missing")),
            str(app.score_error),str(app.command_state.pending)])
        return true
    if not app.native_started:
        return false
    if not requested:
        if not app.startup_last_music_checked:
            return false
        requested = true
        print("PHASE6_PRODUCTION_LAST_PIECE_REQUESTED:",fixture_name)
        return false
    if not app.score_error.is_empty():
        _fail("Production UI rejected native score: "+str(app.score_error))
        return true
    if not ready_seen:
        if not app.score_session.is_ready():
            return false
        if not expected_fingerprint.is_empty() and \
                str(app.last_state.get("piece_fingerprint","")) != expected_fingerprint:
            _fail("Loaded a different MIDI from the requested real score")
            return true
        var chrome = app.practice_view
        # One bottom Play/Pause control. Only BPM and Settings occupy the
        # header, on the same row, even for long titles.
        if not (chrome.practice_navigation is HBoxContainer) or (
                absf(chrome.speed_label.get_global_rect().get_center().y
                    - chrome.practice_settings_button.get_global_rect().get_center().y) > 2.0):
            _fail("Practice BPM and Settings wrapped onto different rows")
            return true
        if chrome.practice_header.size.y > 56.0 or chrome.start_button.size.y > 60.0:
            _fail("Practice chrome is too tall and crowds out the score")
            return true
        if chrome.stage.fingering_status_label.get_parent() != chrome.details_panel:
            _fail("Fingering diagnostics still occupy the notation stage")
            return true
        var renderer = chrome.stage.renderer
        var notes: int = renderer.timeline.notes.size()
        if not renderer.visible or notes <= 0 or not renderer.retained_ready():
            _fail("Published score has no visible native retained notation")
            return true
        if app.practice_view.stage.score_status_panel.visible:
            _fail("Ready score remains obscured by a preparation overlay")
            return true
        if int(app.score_session.rendered_revision) != int(app.last_state.get("revision",-1)):
            _fail("Rendered score and backend source revisions differ")
            return true
        if str(app.current_screen) != "practice" or \
                not bool(app.last_state.get("loaded",false)):
            _fail("Startup did not navigate to the loaded practice screen")
            return true
        # READY must preposition authentic source notes OFFSCREEN before Play,
        # rather than using a transport callback to spawn source-local ink.
        # An empty candidate means the renderer has not run its first frame.
        if renderer.stream_passes.is_empty():
            return false
        var prepared: Dictionary = {}
        var pending_count := 0
        for item in renderer.stream_passes:
            if str(item.get("kind","source")) == "source" and \
                    str(item.get("take_key","")) == "prepared" and \
                    bool(item.get("pending",false)):
                prepared = item
                pending_count += 1
        if pending_count != 1:
            _fail("Ready must retain exactly one offscreen unplayed source")
            return true
        var density: float = renderer.timeline.pixels_per_beat
        var first_ink_x: float = renderer.size.x*ScoreView.PLAYHEAD_FRACTION + \
            (float(prepared["world_origin"])-renderer.stream_world_beat) * \
            density - 15.0*renderer.staff_gap()
        if first_ink_x <= renderer.size.x+12.0:
            _fail("Ready source was placed within the visible staff")
            return true
        if not renderer.drawn_noteheads.is_empty():
            _fail("Source noteheads appeared onscreen before offscreen travel")
            return true
        if ready_visible_since_ms < 0:
            ready_visible_since_ms = Time.get_ticks_msec()
            ready_world_beat = renderer.stream_world_beat
            ready_world_origin = float(prepared["world_origin"])
            ready_pass_serial = int(prepared["serial"])
            return false
        if Time.get_ticks_msec()-ready_visible_since_ms < 250:
            return false
        if renderer.stream_world_beat <= ready_world_beat or \
                int(prepared["serial"]) != ready_pass_serial or \
                float(prepared["world_origin"]) < ready_world_origin:
            _fail("Ready stopped, duplicated a score, or moved hidden ink backwards")
            return true
        # Repositioning a still-hidden READY reservation farther right is
        # required during long waits. The identity stays unchanged; Play
        # must bind the most recent offscreen world origin.
        ready_world_origin = float(prepared["world_origin"])
        var forward_beats: float = renderer.size.x*(1.0-ScoreView.PLAYHEAD_FRACTION) / renderer.timeline.pixels_per_beat
        if forward_beats < 2.0:
            _fail("Engraving leaves under two beats visible ahead of playhead")
            return true
        ready_seen = true
        print("PHASE6_PRODUCTION_NOTATION_READY notes=",notes,
            " visible_heads=",renderer.drawn_noteheads.size(),
            " forward_beats=",forward_beats,
            " revision=",app.score_session.rendered_revision)
        return false
    if not transport_seen:
        var renderer = app.practice_view.stage.renderer
        if not bool(app.last_state.get("running",false)):
            var awaiting: Variant = app.last_state.get("awaiting_score_revision",null)
            if not start_requested and not app.command_state.pending and \
                    awaiting == null and bool(app.last_state.get("loaded",false)):
                start_requested = true
                app._send_action({"action":"start"})
            return false
        if not str(app.last_state.get("phase","")) in ["count_in","playing"]:
            return false
        initial_transport = int(app.last_state.get("transport_id",-1))
        var original_survived := false
        var new_ink_offscreen := true
        for item in renderer.stream_passes:
            if int(item["serial"]) == ready_pass_serial:
                original_survived = is_equal_approx(
                    float(item["world_origin"]),ready_world_origin)
            elif int(item["serial"]) > ready_pass_serial and \
                    str(item.get("kind","source")) == "source":
                # Automatic successors can already be prepared during the
                # first graded frame, but NEVER inside the visible viewport.
                var leading: float = renderer._stream_header_beats(
                    float(item["source_floor"]))
                var onset: float = float(item["world_origin"])+ \
                    float(item["source_floor"])
                var left: float = renderer.size.x*ScoreView.PLAYHEAD_FRACTION + \
                    (onset-renderer.stream_world_beat-leading) * \
                    renderer.timeline.pixels_per_beat
                new_ink_offscreen = new_ink_offscreen and left > renderer.size.x
        if not original_survived or not new_ink_offscreen:
            _fail("Play shifted its existing world origin or admitted notes onscreen")
            return true
        transport_seen = true
        print("PHASE6_PRODUCTION_TRANSPORT_STARTED transport=",initial_transport)
        return false
    if not pause_requested:
        if app.command_state.pending:
            return false
        pause_requested = true
        app._send_action({"action":"pause"})
        return false
    if not pause_seen:
        if not bool(app.last_state.get("paused",false)):
            return false
        pause_seen = true
        print("PHASE6_PRODUCTION_PAUSE_OK")
        return false
    var renderer = app.practice_view.stage.renderer
    if not resume_requested:
        if paused_sample_ms < 0:
            paused_sample_ms = Time.get_ticks_msec()
            paused_world_beat = renderer.stream_world_beat
            paused_pass_serial = renderer._stream_serial
            return false
        if Time.get_ticks_msec()-paused_sample_ms < 400:
            return false
        if renderer.stream_world_beat <= paused_world_beat:
            _fail("Paused staff stopped scrolling")
            return true
        if renderer._stream_serial != paused_pass_serial:
            _fail("Pause spawned another exercise instead of letting previous notes leave")
            return true
        if app.command_state.pending:
            return false
        resume_requested = true
        app._send_action({"action":"resume"})
        return false
    if bool(app.last_state.get("paused",false)) or \
            not bool(app.last_state.get("running",false)):
        return false
    if int(app.last_state.get("transport_id",-1)) != initial_transport:
        _fail("Resume unexpectedly restarted the graded transport")
        return true
    if resumed_sample_ms < 0:
        resumed_sample_ms = Time.get_ticks_msec()
        resumed_world_beat = renderer.stream_world_beat
        resumed_pass_serial = renderer._stream_serial
        return false
    if Time.get_ticks_msec()-resumed_sample_ms < 450:
        return false
    var beat_advance: float = renderer.stream_world_beat-resumed_world_beat
    if beat_advance <= .04:
        _fail("Resume froze or reset the continuously moving staff")
        return true
    var reused_original := false
    var future_only := true
    var new_copy := false
    for item in renderer.stream_passes:
        if int(item["serial"]) == ready_pass_serial and \
                is_equal_approx(float(item["world_origin"]),ready_world_origin):
            reused_original = float(item["world_origin"]) + \
                float(item["source_floor"]) > renderer.stream_world_beat + 2.0
        if int(item["serial"]) > paused_pass_serial and \
                str(item.get("kind","source")) == "source":
            new_copy = true
            var ink_start: float = renderer.size.x*ScoreView.PLAYHEAD_FRACTION + \
                (float(item["world_origin"])+float(item["source_floor"])-
                renderer.stream_world_beat)*renderer.timeline.pixels_per_beat - \
                renderer._stream_header_beats(float(item["source_floor"]))* \
                renderer.timeline.pixels_per_beat
            future_only = future_only and ink_start > renderer.size.x
    if not (reused_original or new_copy and future_only):
        _fail("Resume moved the unplayed passage or inserted a copy onscreen")
        return true
    if not is_equal_approx(renderer.timeline.pixels_per_beat,
            renderer.configured_density) and renderer.timeline.pixels_per_beat < 1.0:
        _fail("Score horizontal density is invalid")
        return true
    if not renderer.retained_ready():
        _fail("Resume lost the already engraved source notation")
        return true
    print("PHASE6_PRODUCTION_CONTINUOUS_FLOW_OK beat_delta=",beat_advance,
        " admitted_before=",paused_pass_serial,
        " admitted_after=",renderer._stream_serial,
        " selected_bpm=",app.last_state.get("bpm"))
    print("PHASE6_PRODUCTION_UI_WORKFLOW_OK")
    quit(0)
    return true

func _fail(message: String) -> void:
    printerr("PHASE6_PRODUCTION_UI_FAILED: ",message)
    quit(1)
