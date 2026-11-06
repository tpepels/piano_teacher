extends SceneTree
## Phase 6: actual Godot scene, embedded Python, and an authored real score.
## Exercise the player-visible journey with controls, not EngineCommands fakes.
## Runs against a saved copy of midi/Moonlight_Sonata_I.midi in an isolated home.
const MAX_MS := 170000
const EXPECTED_PIECE := "Moonlight_Sonata_I.midi"
var app
var started_ms := 0
var phase_ms := 0
var phase := "startup"
var initial_revision := -1
var initial_transport := -1
var restarted_transport := -1
var paused_ms := 0
var paused_clock := NAN
var paused_serial := -1
var retry_world_start := NAN
var paused_head_id := ""
var paused_head_x := NAN
var retry_reversed := false
var retry_prepared := false
var resumed_bpm := 0.0
var selected_bpm := 0.0
var selected_revision := -1

func _initialize() -> void:
    call_deferred("_boot")

func _boot() -> void:
    started_ms = Time.get_ticks_msec()
    phase_ms = started_ms
    root.size = Vector2i(1280,800)
    var scene: PackedScene = load("res://main.tscn")
    if scene == null:
        _fail("Production main scene cannot load")
        return
    app = scene.instantiate()
    root.add_child(app)
    if app.score_session == null:
        _fail("Production main scene has no score session")
        return
    print("PHASE6_REAL_SCORE_BOOTED")

func _advance(next: String) -> void:
    phase = next
    phase_ms = Time.get_ticks_msec()
    print("PHASE6_REAL_SCORE_STEP:",phase)

func _fail(message: String) -> void:
    var state: Dictionary = app.last_state if app != null else {}
    var prep: Variant = state.get("practice_preparation")
    var witness := {"phase":state.get("phase"),
        "running":state.get("running"),"revision":state.get("revision"),
        "transport_id":state.get("transport_id"),
        "play_from_beat":state.get("play_from_beat"),
        "clock_beat":state.get("clock_beat"),
        "bpm":state.get("bpm"),
        "preparation":prep.get("phase") if prep is Dictionary else null}
    if app != null and app.practice_view != null:
        var renderer = app.practice_view.stage.renderer
        var passages: Array = []
        for item in renderer.stream_passes:
            passages.append({"serial":item.get("serial"),
                "take":item.get("take_key"),"kind":item.get("kind"),
                "origin":item.get("world_origin"),
                "floor":item.get("source_floor"),
                "pending":item.get("pending"),"armed":item.get("armed")})
        witness["stream"] = {"world":renderer.stream_world_beat,
            "live":renderer._stream_live_serial,
            "armed":renderer._stream_armed_serial,
            "last_take":renderer._stream_last_take,
            "passes":passages}
    printerr("PHASE6_REAL_SCORE_FAILED: ", phase, ": ", message,
        " witness=", JSON.stringify(witness))
    quit(1)

func _visible_source_head() -> String:
    var view = app.practice_view.stage.renderer
    var bounds := Rect2(Vector2.ZERO, view.size)
    for identifier in view.drawn_noteheads:
        if bounds.has_point(view.drawn_noteheads[identifier]):
            return str(identifier)
    return ""

func _ready_score() -> bool:
    if app.score_session == null or not app.score_session.is_ready():
        return false
    var view = app.practice_view.stage.renderer
    if not view.native_ready or not view.visible or not view.retained_ready():
        return false
    if int(app.last_state.get("revision",-1)) != app.score_session.rendered_revision:
        return false
    # There is no alternate legacy/native renderer selector. Practice,
    # Listen and the preloaded stage use the same retained world-time view.
    return view.retained_ready()

func _press(button: Button, action: String) -> bool:
    if app.command_state.pending:
        return false
    if button.disabled:
        _fail(action+" button disabled despite ready score")
        return false
    button.pressed.emit()
    return true

func _process(_delta: float) -> bool:
    if app == null or not is_instance_valid(app):
        return false
    var now := Time.get_ticks_msec()
    if now-started_ms > MAX_MS:
        _fail("Overall journey deadline exceeded")
        return true
    if now-phase_ms > (55000 if phase in ["startup","listen_load","listen_playback","stage_change"] else 35000):
        _fail("Phase deadline exceeded")
        return true
    if not app.score_error.is_empty():
        _fail("Native score failed to render: "+app.score_error)
        return true
    var state: Dictionary = app.last_state
    var view = app.practice_view.stage.renderer
    match phase:
        "startup":
            if not app.native_started or not app.startup_last_music_checked:
                return false
            if not bool(state.get("loaded",false)) or not _ready_score():
                return false
            if int(state.get("lesson_steps",0)) < 2:
                _fail("Real source generated fewer than two lesson steps")
                return true
            if app.current_screen != "practice" or                     app.practice_view.stage.score_status_panel.visible:
                _fail("Native score ready but still obscured by loading panel")
                return true
            initial_revision = int(state["revision"])
            if not bool(state.get("running",false)):
                if not _press(app.practice_view.start_button,"Play"):
                    return false
            print("PHASE6_REAL_SCORE_READY revision=",initial_revision,
                " notes=",view.timeline.notes.size(),
                " visible=",view.drawn_noteheads.size(),
                " density=",view.timeline.pixels_per_beat)
            _advance("initial_count_in")
        "initial_count_in":
            if not bool(state.get("running",false)) or                     str(state.get("phase","")) not in ["count_in","playing"]:
                return false
            initial_transport = int(state["transport_id"])
            if int(state["revision"]) != initial_revision:
                _fail("Play unexpectedly invalidated source score")
                return true
            _advance("pause")
        "pause":
            if not _press(app.practice_view.start_button,"Pause"):
                return false
            _advance("paused")
        "paused":
            if not bool(state.get("paused",false)):
                return false
            if paused_ms == 0:
                paused_ms = now
                paused_clock = view.stream_world_beat
                paused_serial = view._stream_serial
                return false
            if now-paused_ms < 350:
                return false
            if view.stream_world_beat <= paused_clock or view._stream_serial != paused_serial:
                _fail("Paused score stopped moving or admitted new notes")
                return true
            if not _press(app.practice_view.start_button,"Resume"):
                return false
            _advance("resumed")
        "resumed":
            if not bool(state.get("running",false)) or bool(state.get("paused",false)):
                return false
            if int(state.get("transport_id",-1)) != initial_transport:
                _fail("Resume created a new attempt instead of resuming")
                return true
            if not _press(app.practice_view.practice_retry_button,"Retry"):
                return false
            retry_world_start = view.stream_world_beat
            _advance("retry_reverse")
        "retry_reverse":
            var prep: Variant = state.get("practice_preparation")
            if prep is Dictionary and str(prep.get("phase",""))=="reverse":
                retry_reversed = true
                if view.stream_world_beat < retry_world_start:
                    _fail("Retry reversed the display rather than scheduling new ink")
                    return true
            if retry_reversed and prep is Dictionary and                     str(prep.get("phase",""))=="preparing":
                retry_prepared = true
                _advance("retry_rest")
        "retry_rest":
            if str(state.get("phase","")) in ["recovering","feedback"] and                     not bool(state.get("paused",false)):
                if view.stream_world_beat < retry_world_start:
                    _fail("Retry rest reversed the perpetual display")
                    return true
                if app.visual_transport_clock.retry_preparing(now) and                         not app.practice_view.stage.count_in.visible:
                    _fail("Retry rest has no visible count-in")
                    return true
            if not bool(state.get("running",false)):
                return false
            restarted_transport = int(state.get("transport_id",-1))
            if restarted_transport <= initial_transport or not retry_prepared or                     int(state.get("revision",-1)) != initial_revision:
                _fail("Retry changed the score or skipped the full rest")
                return true
            var reserved_match := false
            var wrong_side := false
            for item in view.stream_passes:
                if str(item.get("kind","source")) != "source":
                    continue
                var take_key: String = str(item.get("take_key",""))
                if take_key.contains("|%d|" % restarted_transport) and \
                        not bool(item.get("pending",false)):
                    reserved_match = true
                    # Real note ink must be attached to one immutable
                    # source position. A reused offscreen candidate is
                    # allowed; a new serial is not required on Retry.
                    wrong_side = wrong_side or \
                        float(item["world_origin"])+float(item["source_floor"]) < \
                        retry_world_start + 0.25
            if not _ready_score() or not reserved_match or wrong_side:
                _fail("Retry lacks a matched future-only source reservation " +
                    "ready=%s matching=%s early=%s serial=%d before=%d" % [
                    str(_ready_score()),str(reserved_match),str(wrong_side),
                    view._stream_serial,paused_serial])
                return true
            if not _press(app.practice_view.listen_button,"Listen"):
                return false
            _advance("listen_load")
        "listen_load":
            if str(state.get("mode","")) != "listen" or not _ready_score():
                return false
            if int(state.get("revision",-1)) <= initial_revision:
                _fail("Listen reused stale source revision")
                return true
            # A newly engraved Listen score can be ready before synthesis,
            # download, WAV decoding, and the audio-ready handshake complete.
            # The user needs an audible synchronized example, not a spinner.
            var demo: Dictionary = state.get("demo",{}) if state.get("demo") is Dictionary else {}
            if demo.has("error") or bool(app.demo_player.audio_error):
                _fail("Listen WAV preparation or decoding failed")
                return true
            if not bool(demo.get("audio_available",false)) or \
                    not bool(demo.get("ready",false)) or \
                    not bool(app.demo_player.loaded) or \
                    not bool(state.get("running",false)):
                return false
            _advance("listen_playback")
        "listen_playback":
            # Count-in can be several seconds before the WAV's first sample.
            if not bool(app.demo_player.started):
                return false
            if app.demo_player.player.stream == null:
                _fail("Listen entered playback without decoded PCM audio")
                return true
            if not _press(app.practice_view.listen_button,"Return to practice"):
                return false
            _advance("return_to_practice")
        "return_to_practice":
            if str(state.get("mode",""))!="practice" or not _ready_score() or                     bool(state.get("running",false)):
                return false
            if int(state.get("lesson_step",0)) != 1:
                _fail("Listen changed the selected lesson")
                return true
            if app.command_state.pending:
                return false
            app._send_action({"action":"select_step","number":2})
            _advance("stage_change")
        "stage_change":
            if app.command_state.pending or int(state.get("lesson_step",0)) != 2 or                     not _ready_score():
                return false
            selected_revision = int(state["revision"])
            if int(state["revision"]) <= initial_revision:
                _fail("Stage change did not prepare new notation")
                return true
            if not _press(app.practice_view.tempo_down_button,"-5 BPM"):
                return false
            selected_bpm = float(state["bpm"])
            _advance("tempo_change")
        "tempo_change":
            if app.command_state.pending or float(state.get("bpm",-1)) >= selected_bpm:
                return false
            if selected_bpm-float(state["bpm"]) != 5.0 or                     int(state.get("revision",-1)) != selected_revision or                     not _ready_score():
                _fail("Manual tempo change re-engraved score or changed more than 5 BPM")
                return true
            resumed_bpm = float(state["bpm"])
            app._open_library_piece(EXPECTED_PIECE,true)
            _advance("reopen")
        "reopen":
            if app.command_state.pending or not _ready_score():
                return false
            if int(state.get("lesson_step",-1)) != 2 or                     absf(float(state.get("bpm",-1))-resumed_bpm) > .001:
                _fail("Reopening lost the selected step or manual tempo")
                return true
            if app.practice_view.stage.score_status_panel.visible:
                _fail("Reopened score still shows preparation overlay")
                return true
            print("PHASE6_REAL_SCORE_JOURNEY_OK notes=",view.timeline.notes.size(),
                " revision=",state.get("revision"),
                " restarted_transport=",restarted_transport,
                " restored_step=",state.get("lesson_step"),
                " bpm=",resumed_bpm)
            quit(0)
            return true
    return false
