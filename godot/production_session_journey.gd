extends SceneTree
## Phase 6: actual Godot scene, embedded Python, and an authored real score.
## Exercise the player-visible journey with controls, not EngineCommands fakes.
## Runs against a saved copy of midi/Moonlight_Sonata_I.midi in an isolated home.
const MAX_MS := 170000
const EXPECTED_PIECE := "Moonlight_Sonata_I.midi"
const Admission := preload("res://score_stream_admission.gd")
var app
var started_ms := 0
var phase_ms := 0
var phase := "startup"
var initial_revision := -1
var initial_stage_key := ""
var practice_requested := false
var initial_transport := -1
var restarted_transport := -1
var paused_ms := 0
var paused_clock := NAN
var paused_serial := -1
var retry_world_start := NAN
var paused_head_id := ""
var paused_head_x := NAN
var retry_countdown_seen := false
var retry_audio_seen := false
var retry_audio_at_request := -1
var retry_rest_seen := false
var resumed_bpm := 0.0
var selected_bpm := 0.0
var selected_revision := -1

var _finishing := false

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
    var state: Dictionary = app.current_state() if app != null else {}
    var witness := {"phase":state.get("phase"),
        "running":state.get("running"),"revision":state.get("revision"),
        "transport_id":state.get("transport_id"),
        "play_from_beat":state.get("play_from_beat"),
        "clock_beat":state.get("clock_beat"),
        "bpm":state.get("bpm")}
    if app != null and app.practice_view != null:
        var renderer = app.practice_view.stage.renderer
        var passages: Array = []
        for item in renderer.diagnostic_stream_snapshot():
            passages.append({"serial":item.get("serial"),
                "take":item.get("take_key"),"kind":item.get("kind"),
                "origin":item.get("world_origin"),
                "floor":item.get("source_floor"),
                "pending":item.get("pending"),"armed":item.get("armed")})
        witness["stream"] = {"world":renderer.stream_world_beat,
            "live":renderer.stream_owner_status().get("live_serial",-1),
            "armed":renderer.stream_owner_status().get("armed_serial",-1),
            "last_take":renderer.stream_owner_status().get("last_take",""),
            "passes":passages}
        witness["projection"] = {
            "flow_hold":app.score_flow.hold_world,
            "flow_rate":app.score_flow.bpm,
            "flow_world":app.score_flow.project(Time.get_ticks_msec()),
            "world_sample":app.score_flow.beat,
            "last_ms":app.score_flow.last_ms,
            "intent":state.get("playback_intent"),
            "placed_segment":app.score_admission.placed_segment,
            "reservation_problem":app.score_admission.last_problem()
        }
    printerr("PHASE6_REAL_SCORE_FAILED: ", phase, ": ", message,
        " witness=", JSON.stringify(witness))
    _finish(1)

func _ready_score() -> bool:
    if app.score_session == null or not app.score_session.is_ready():
        return false
    var view = app.practice_view.stage.renderer
    if not view.native_ready or not view.visible or not view.retained_ready():
        return false
    if int(app.current_state().get("revision",-1)) != app.score_session.rendered_revision:
        return false
    # There is no alternate legacy/native renderer selector. Practice,
    # Listen and the preloaded stage use the same retained world-time view.
    return view.retained_ready()

func _press(button: Button, action: String) -> bool:
    if app.command_coordinator.state.pending:
        return false
    if button.disabled:
        _fail(action+" button disabled despite ready score")
        return false
    button.pressed.emit()
    return true

func _finish(code: int) -> void:
    if _finishing:
        return
    _finishing = true
    if is_instance_valid(app):
        app._shutdown_and_quit(code)
    else:
        quit(code)

func _process(_delta: float) -> bool:
    if _finishing:
        return false
    if app == null or not is_instance_valid(app):
        return false
    var now := Time.get_ticks_msec()
    if now-started_ms > MAX_MS:
        _fail("Overall journey deadline exceeded")
        return false
    if now-phase_ms > (55000 if phase in ["startup","listen_load","listen_playback","stage_change"] else 35000):
        _fail("Phase deadline exceeded")
        return false
    if not app.score_error.is_empty():
        _fail("Native score failed to render: "+app.score_error)
        return false
    var state: Dictionary = app.current_state()
    var view = app.practice_view.stage.renderer
    match phase:
        "startup":
            if not app.native_started or not app.startup_last_music_checked:
                return false
            if not bool(state.get("loaded",false)) or not _ready_score():
                return false
            if int(state.get("lesson_steps",0)) < 2:
                _fail("Real source generated fewer than two lesson steps")
                return false
            if app.current_screen != "practice" or                     app.practice_view.stage.score_status_panel.visible:
                _fail("Native score ready but still obscured by loading panel")
                return false
            # Practice Flow opens with Listen. This journey exercises timed
            # Play/Pause/Retry, so choose Practice rhythm as a learner can.
            if str(state.get("mode","")) != "practice":
                if not practice_requested and not app.command_coordinator.state.pending:
                    app.send_action({"action":"practice"})
                    practice_requested = true
                return false
            initial_revision = int(state["revision"])
            initial_stage_key = str(state.get("stage_key",""))
            if not bool(state.get("running",false)):
                # An automatically scheduled take shows Pause while it is
                # admitted; press Play only when the projected action is Play.
                var primary: String = str(state.get("controls",{}).get(
                    "primary",{}).get("action",""))
                if primary not in ["start","resume","play"]:
                    return false
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
                return false
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
                paused_serial = view.admission_queue_generation()
                return false
            if now-paused_ms < 350:
                return false
            if absf(view.stream_world_beat-paused_clock) > .01:
                _fail("Paused score moved after Pause was acknowledged")
                return false
            if view.admission_queue_generation() != paused_serial:
                _fail("Pause admitted additional source notes")
                return false
            if not _press(app.practice_view.start_button,"Resume"):
                return false
            _advance("resumed")
        "resumed":
            if not bool(state.get("running",false)) or bool(state.get("paused",false)):
                return false
            if int(state.get("transport_id",-1)) != initial_transport:
                _fail("Resume created a new attempt instead of resuming")
                return false
            if not _press(app.practice_view.practice_retry_button,"Retry"):
                return false
            retry_world_start = view.stream_world_beat
            var voice = app.get_node_or_null("CountInVoicePlayer")
            retry_audio_at_request = int(app.countin_audio.click_cues_total) + \
                (int(voice.spoken_cues_total) if voice != null else 0)
            _advance("retry_wait")
        "retry_wait":
            # One immutable playback transition now owns Retry. The former
            # server-side reverse/preparing stages are not a second clock or
            # a prerequisite for admission. The world clock moves forward
            # while an authored rest and one final count-in precede new ink.
            if view.stream_world_beat+0.0001 < retry_world_start:
                _fail("Retry moved the perpetual score world backwards")
                return false
            for item in view.diagnostic_stream_snapshot():
                if str(item.get("kind","")) == "rest" and \
                        float(item.get("world_origin",-INF)) >= retry_world_start-5.0:
                    retry_rest_seen = true
            var transport: int = int(state.get("transport_id",-1))
            if transport <= initial_transport or not bool(state.get("running",false)):
                return false
            restarted_transport = transport
            if int(state.get("revision",-1)) != initial_revision:
                _fail("Retry re-engraved or replaced the selected source")
                return false
            var playback: Variant = state.get("playback_timeline")
            var current: Variant = (playback.get("current") if playback is Dictionary
                else null)
            if not current is Dictionary or \
                    int(current.get("transport_id",-1)) != restarted_transport:
                return false
            var count_plan: Variant = current.get("count_in_plan")
            if not count_plan is Dictionary or \
                    float(count_plan.get("beats",0.0)) <= 0.0:
                _fail("Retry lacks its single authorized count-in plan")
                return false
            if str(state.get("phase","")) == "count_in":
                retry_countdown_seen = retry_countdown_seen or \
                    app.practice_view.stage.count_in.visible
                var voice = app.get_node_or_null("CountInVoicePlayer")
                retry_audio_seen = retry_audio_seen or \
                    (int(app.countin_audio.click_cues_total) + \
                    (int(voice.spoken_cues_total) if voice != null else 0) > \
                    retry_audio_at_request)
                return false
            if str(state.get("phase","")) != "playing":
                return false
            # A second authorized attempt must not silently play without
            # a displayed final count-in or scheduled audible cue.
            if not retry_countdown_seen or not retry_audio_seen:
                _fail("Retry played without its single visible/audible count-in")
                return false
            var expected: String = "%s|%d|%d|practice" % [
                str(state.get("piece_fingerprint","")),
                initial_revision,restarted_transport]
            var reserved_match := false
            var wrong_side := false
            for item in view.diagnostic_stream_snapshot():
                if str(item.get("kind","source")) != "source" or \
                        str(item.get("take_key","")) != expected or \
                        bool(item.get("pending",false)):
                    continue
                reserved_match = true
                var source_at: float = float(item["world_origin"]) + \
                    float(item.get("source_floor",0.0))
                wrong_side = wrong_side or source_at <= retry_world_start+0.25
                var density: float = float(item.get("admitted_density",NAN))
                var gap: float = float(item.get("admitted_staff_gap",NAN))
                var world_at: float = float(item.get("admitted_world",NAN))
                var playhead: float = float(item.get("admitted_playhead_x",NAN))
                var viewport_width: float = float(item.get("admitted_viewport_width",NAN))
                if not (is_finite(density) and density > 0.0 and \
                        is_finite(gap) and is_finite(world_at) and \
                        is_finite(playhead) and is_finite(viewport_width)):
                    wrong_side = true
                    continue
                # The musical timeline places the retry ahead of the
                # playhead (it may appear on the visible staff).
                wrong_side = wrong_side or source_at <= world_at+.0001
                # A rest AFTER the retry source must never be mistaken for
                # its preceding gap. Locate the nearest genuine rest ending
                # at/before this source, which may itself already be moving.
                var prior_rest_end := -INF
                for rest in view.diagnostic_stream_snapshot():
                    if str(rest.get("kind","")) != "rest":
                        continue
                    var rest_end: float = float(rest.get("world_origin",0.0)) + \
                        float(rest.get("source_ceiling",0.0))
                    if rest_end <= source_at+0.001:
                        prior_rest_end = maxf(prior_rest_end,rest_end)
                wrong_side = wrong_side or prior_rest_end == -INF
            if not _ready_score() or not reserved_match or wrong_side or \
                    not retry_rest_seen:
                _fail("Retry lacks a bounded future source and full rest " + \
                    "ready=%s matched=%s early=%s rest=%s" % [
                    str(_ready_score()),str(reserved_match),
                    str(wrong_side),str(retry_rest_seen)])
                return false
            if not _press(app.practice_view.listen_button,"Listen"):
                return false
            _advance("listen_load")
        "listen_load":
            if str(state.get("mode","")) != "listen" or not _ready_score():
                return false
            # The revision identifies the drawn notes: Listen of the same
            # window keeps it (no clear/re-engrave); it must be this stage.
            if int(state.get("revision",-1)) < initial_revision or \
                    str(state.get("stage_key","")) != initial_stage_key:
                _fail("Listen is not on the practised window's score")
                return false
            # A newly engraved Listen score can be ready before synthesis,
            # download, WAV decoding, and the audio-ready handshake complete.
            # The user needs an audible synchronized example, not a spinner.
            var demo: Dictionary = state.get("demo",{}) if state.get("demo") is Dictionary else {}
            if demo.has("error") or bool(app.demo_player.audio_error):
                _fail("Listen WAV preparation or decoding failed")
                return false
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
                return false
            # Practice Flow leads from Listen into Free; the learner returns
            # to timed practice by choosing Practice rhythm.
            if app.command_coordinator.state.pending:
                return false
            app.send_action({"action":"practice"})
            _advance("return_to_practice")
        "return_to_practice":
            # The timeline starts the take at once (count-in); the next
            # step does not depend on it having started or not.
            if str(state.get("mode",""))!="practice" or not _ready_score():
                return false
            if int(state.get("lesson_step",0)) != 1:
                _fail("Listen changed the selected lesson")
                return false
            if app.command_coordinator.state.pending:
                return false
            app.send_action({"action":"select_step","number":2})
            _advance("stage_change")
        "stage_change":
            if app.command_coordinator.state.pending or int(state.get("lesson_step",0)) != 2 or                     not _ready_score():
                return false
            selected_revision = int(state["revision"])
            if int(state["revision"]) <= initial_revision:
                _fail("Stage change did not prepare new notation")
                return false
            # Slower is a Pause-sheet / shortcut gesture, resolved by Python.
            if app.command_coordinator.state.pending:
                return false
            if not bool(state.get("controls",{}).get("tempo_down",{}).get("enabled",false)):
                _fail("Slower unavailable despite ready score")
                return false
            app.send_action({"action":"ui_tempo_down"})
            selected_bpm = float(state["bpm"])
            _advance("tempo_change")
        "tempo_change":
            if app.command_coordinator.state.pending or float(state.get("bpm",-1)) >= selected_bpm:
                return false
            if selected_bpm-float(state["bpm"]) != 5.0 or                     int(state.get("revision",-1)) != selected_revision or                     not _ready_score():
                _fail("Manual tempo change re-engraved score or changed more than 5 BPM")
                return false
            resumed_bpm = float(state["bpm"])
            app.open_library_piece(EXPECTED_PIECE,true)
            _advance("reopen")
        "reopen":
            if app.command_coordinator.source_state.pending or not _ready_score():
                return false
            # docs/practice-flow.md: reopening returns to the same window
            # and hand at Free (untimed), not to the last manual tempo.
            if int(state.get("lesson_step",-1)) != 2 or \
                    str(state.get("mode","")) != "learn":
                _fail("Reopening did not return to the selected step at Free")
                return false
            if app.practice_view.stage.score_status_panel.visible:
                _fail("Reopened score still shows preparation overlay")
                return false
            print("PHASE6_REAL_SCORE_JOURNEY_OK notes=",view.timeline.notes.size(),
                " revision=",state.get("revision"),
                " restarted_transport=",restarted_transport,
                " restored_step=",state.get("lesson_step"),
                " bpm=",resumed_bpm)
            _finish(0)
            return false
    return false
