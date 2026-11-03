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
        ready_seen = true
        print("PHASE6_PRODUCTION_NOTATION_READY notes=",notes,
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
    if not resume_requested:
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
    print("PHASE6_PRODUCTION_UI_WORKFLOW_OK")
    quit(0)
    return true

func _fail(message: String) -> void:
    printerr("PHASE6_PRODUCTION_UI_FAILED: ",message)
    quit(1)
