extends SceneTree
## Actual production scene -> embedded Python -> MIDI -> Verovio -> retained
## notation -> practice transport. No synthetic score-session doubles.
const FIXTURE := "phase6_native_fixture.mid"
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
var paused_head_id := ""
var paused_head_x := NAN
var paused_visual_beat := NAN
var paused_density := NAN
var resumed_sample_ms := -1
var resumed_head_x := NAN
var resumed_visual_beat := NAN

func _initialize() -> void:
    call_deferred("_boot")

func _boot() -> void:
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
        print("PHASE6_PRODUCTION_LAST_PIECE_REQUESTED:",FIXTURE)
        return false
    if not app.score_error.is_empty():
        _fail("Production UI rejected native score: "+str(app.score_error))
        return true
    if not ready_seen:
        if not app.score_session.is_ready():
            return false
        var renderer = app.practice_view.stage.renderer
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
        # A model with several notes and a compiled atlas can still render
        # a blank viewport if positioning or the retained pool is broken.
        if _first_visible_head(renderer).is_empty():
            if ready_visible_since_ms < 0:
                ready_visible_since_ms = Time.get_ticks_msec()
            if Time.get_ticks_msec() - ready_visible_since_ms >= 3000:
                _fail("Published score has no actual notehead within the viewport")
                return true
            return false
        var forward_beats: float = renderer.size.x*.58 / renderer.timeline.pixels_per_beat
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
            # Compare the same painted source attack over real elapsed time.
            paused_head_id = _first_visible_head(renderer)
            if paused_head_id.is_empty():
                return false
            paused_sample_ms = Time.get_ticks_msec()
            paused_head_x = float(renderer.drawn_noteheads[paused_head_id].x)
            paused_visual_beat = renderer.visual_scroll_beat
            paused_density = renderer.timeline.pixels_per_beat
            return false
        if Time.get_ticks_msec() - paused_sample_ms < 350:
            return false
        if not renderer.drawn_noteheads.has(paused_head_id):
            _fail("Paused source attack disappeared from the visible score")
            return true
        if absf(float(renderer.drawn_noteheads[paused_head_id].x)-paused_head_x) > 1.5 or \
                absf(renderer.visual_scroll_beat-paused_visual_beat) > .001:
            _fail("Paused score moved despite the frozen musical clock")
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
        _fail("Pause/Resume unexpectedly restarted the graded transport")
        return true
    if resumed_sample_ms < 0:
        if not renderer.drawn_noteheads.has(paused_head_id):
            return false
        resumed_sample_ms = Time.get_ticks_msec()
        resumed_head_x = float(renderer.drawn_noteheads[paused_head_id].x)
        resumed_visual_beat = renderer.visual_scroll_beat
        return false
    var elapsed_ms: int = Time.get_ticks_msec()-resumed_sample_ms
    if elapsed_ms < 450:
        return false
    if not renderer.drawn_noteheads.has(paused_head_id):
        _fail("Source head vanished during initial resumed count-in")
        return true
    var beat_advance: float = renderer.visual_scroll_beat-resumed_visual_beat
    var head_advance: float = resumed_head_x-float(renderer.drawn_noteheads[paused_head_id].x)
    if absf(head_advance-beat_advance*paused_density) > 2.0:
        _fail("Notehead motion diverged from authoritative visual beat")
        return true
    var expected: float = elapsed_ms/60000.0*float(app.last_state.get("bpm",60.0))
    if str(app.last_state.get("phase","")) == "count_in" and \
            absf(beat_advance-expected) > .12:
        _fail("Count-in notation scroll speed does not match displayed BPM")
        return true
    if beat_advance <= 0.0 or absf(renderer.timeline.pixels_per_beat-paused_density) > .001:
        _fail("Resume froze or rescaled the score instead of moving it")
        return true
    print("PHASE6_PRODUCTION_FRAME_MOTION_OK beat_delta=",beat_advance,
        " head_delta_px=",head_advance," selected_bpm=",app.last_state.get("bpm"),
        " elapsed_ms=",elapsed_ms)
    print("PHASE6_PRODUCTION_UI_WORKFLOW_OK")
    quit(0)
    return true

func _fail(message: String) -> void:
    printerr("PHASE6_PRODUCTION_UI_FAILED: ",message)
    quit(1)
