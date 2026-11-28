extends SceneTree
const VisualCapture := preload("res://tests/visual_capture.gd")
const ScoreView := preload("res://notation/shared/view_base.gd")
const Admission := preload("res://score_stream_admission.gd")
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
var countin_audio_first_ms := -1
var start_requested := false
var pause_requested := false
var pause_seen := false
var resume_requested := false
var initial_transport := -1
var ready_visible_since_ms := -1
var paused_sample_ms := -1
var paused_world_beat := NAN
var paused_pass_serial := -1
var ready_source_floor := 0.0
var ready_pass_serial := -1
var ready_take_owner := -1
var ready_world_origin := NAN
var ready_world_beat := NAN
var ready_first_expiry_world := NAN
var resumed_sample_ms := -1
var resumed_world_beat := NAN
var resumed_pass_serial := -1

var _finishing := false
var _visual_capture = VisualCapture.new()

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
    _visual_capture.start(app,root)
    _visual_capture.step = "fixture"
    if not is_instance_valid(app) or app.score_session == null:
        _fail("Production scene did not initialize the score session")
        return
    print("PHASE6_PRODUCTION_SCENE_STARTED")

func _finish(code: int) -> void:
    if _finishing:
        return
    _finishing = true
    if not _visual_capture.finish():
        code = 1
    if is_instance_valid(app):
        app._shutdown_and_quit(code)
    else:
        quit(code)

func _process(_delta: float) -> bool:
    if _finishing:
        return false
    if app == null or not is_instance_valid(app):
        return false
    if Time.get_ticks_msec() - begun_ms > MAX_MS:
        var state: Dictionary = app.current_state()
        var gateway = app.score_admission
        var renderer = app.practice_view.stage.renderer
        print("PHASE6_RESUME_DIAGNOSTIC:",JSON.stringify({
            "state_phase":state.get("phase"),"mode":state.get("mode"),
            "paused":state.get("paused"),"intent":state.get("playback_intent"),
            "flow_hold":app.score_flow.hold_world,"flow_rate":app.score_flow.bpm,
            "flow_world":app.score_flow.project(Time.get_ticks_msec()),
            "world_sample":app.score_flow.beat,"world_ms":app.score_flow.last_ms,
            "renderer_world":renderer.stream_world_beat,
            "placed_segment":gateway.placed_segment,
            "reservation_problem":gateway.last_problem()
        }))
        _fail("Production UI timed out phase=%s error=%s pending=%s" % [
            str(state.get("phase","missing")),
            str(app.score_error),str(app.command_coordinator.state.pending)])
        return false
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
        return false
    if not ready_seen:
        if not app.score_session.is_ready():
            return false
        if not expected_fingerprint.is_empty() and \
                str(app.current_state().get("piece_fingerprint","")) != expected_fingerprint:
            _fail("Loaded a different MIDI from the requested real score")
            return false
        var chrome = app.practice_view
        if fixture_name == DEFAULT_FIXTURE:
            var selected: Dictionary = app.current_state()
            if str(selected.get("flow",{}).get("step","")) != "listen" or \
                    int(selected.get("first_bar",0)) != 1 or \
                    int(selected.get("last_bar",0)) != 1:
                _fail("Fresh default course must open its first measure in Listen")
                return false
            print("PHASE6_DEFAULT_PRACTICE_FLOW_OK")
        var voice = app.get_node_or_null("CountInVoicePlayer")
        if voice == null or not voice.available():
            _fail("Production scene does not own four playable offline voice recordings")
            return false
        if not chrome.stage.count_in.voice_status().get("available",false):
            _fail("Visual countdown has not bound the persistent audio service")
            return false
        var renderer = chrome.stage.renderer
        var notes: int = renderer.timeline.notes.size()
        if not renderer.visible or notes <= 0 or not renderer.retained_ready():
            _fail("Published score has no visible native retained notation")
            return false
        if app.practice_view.stage.score_status_panel.visible:
            _fail("Ready score remains obscured by a preparation overlay")
            return false
        if int(app.score_session.rendered_revision) != int(app.current_state().get("revision",-1)):
            _fail("Rendered score and backend source revisions differ")
            return false
        if str(app.current_screen) != "practice" or \
                not bool(app.current_state().get("loaded",false)):
            _fail("Startup did not navigate to the loaded practice screen")
            return false
        # Before the first authorized Listen/Play, there is no executable
        # musical tempo. The published held directive must freeze the
        # displayed score, despite its pre-engraved source atlas. An older
        # authorized take may continue moving while its successor waits.
        if ready_visible_since_ms < 0:
            ready_visible_since_ms = Time.get_ticks_msec()
            ready_world_beat = renderer.stream_world_beat
            return false
        if Time.get_ticks_msec()-ready_visible_since_ms < 250:
            return false
        var playback: Variant = app.current_state().get("playback_timeline")
        var accepted: Variant = playback.get("current") if playback is Dictionary else null
        if (not bool(app.current_state().get("running",false))
                and not accepted is Dictionary
                and absf(renderer.stream_world_beat-ready_world_beat) > .02):
            _fail("Unadmitted score moved without an authorized musical epoch")
            return false
        # Practice Flow opens with Listen, which may already be authorized;
        # only ink shown before any authorized segment is a violation.
        var authorized: bool = bool(app.current_state().get("running",false)) \
            or accepted is Dictionary
        for item in renderer.diagnostic_stream_snapshot():
            if not authorized and str(item.get("kind","source")) == "source" and \
                    bool(item.get("ever_visible",false)):
                _fail("Pre-authorization score source appeared onscreen")
                return false
        var forward_beats: float = renderer.size.x*(
            1.0-ScoreView.PLAYHEAD_FRACTION)/renderer.timeline.pixels_per_beat
        if forward_beats < 2.0:
            _fail("Engraving leaves under two beats visible ahead of playhead")
            return false
        ready_seen = true
        print("PHASE6_PRODUCTION_NOTATION_READY notes=",notes,
            " visible_heads=",renderer.drawn_noteheads.size(),
            " forward_beats=",forward_beats,
            " revision=",app.score_session.rendered_revision)
        return false
    if not transport_seen:
        var renderer = app.practice_view.stage.renderer
        if not bool(app.current_state().get("running",false)):
            var awaiting: Variant = app.current_state().get("awaiting_score_revision",null)
            # Practice Flow opens with Listen automatically. Do not issue a
            # competing manual Start before its prepared audio/score is
            # authorized; for non-Listen routes, use the normal Play button.
            if str(app.current_state().get("mode","")) != "listen" and \
                    not start_requested and not app.command_coordinator.state.pending and \
                    awaiting == null and bool(app.current_state().get("loaded",false)):
                start_requested = true
                app.send_action({"action":"start"})
            return false
        if not str(app.current_state().get("phase","")) in ["count_in","playing"]:
            return false
        var active_key: String = "%s|%d|%d|%s" % [
            str(app.current_state().get("piece_fingerprint","")),
            int(app.current_state().get("revision",-1)),
            int(app.current_state().get("transport_id",-1)),
            str(app.current_state().get("mode","practice"))]
        if ready_pass_serial < 0:
            # The first legitimate source can be bound only after physical
            # score admission and the backend ACK. Inspect that source's
            # immutable admission time, not a speculative READY placeholder.
            for item in renderer.diagnostic_stream_snapshot():
                if str(item.get("kind","source")) != "source" or \
                        str(item.get("take_key","")) != active_key or \
                        bool(item.get("pending",false)):
                    continue
                var density: float = float(item.get("admitted_density",NAN))
                var gap: float = float(item.get("admitted_staff_gap",NAN))
                var admitted_world: float = float(item.get("admitted_world",NAN))
                var playhead: float = float(item.get("admitted_playhead_x",NAN))
                var viewport_width: float = float(item.get("admitted_viewport_width",NAN))
                if not (is_finite(density) and density > 0.0 and \
                        is_finite(gap) and is_finite(admitted_world) and \
                        is_finite(playhead) and is_finite(viewport_width)):
                    _fail("Authorized source has no immutable admission witness")
                    return false
                var bounds: Vector2 = Admission.clip_bounds(
                    item,density,gap,renderer.timeline.duration_beats)
                var first_pixel: float = playhead + \
                    (float(item["world_origin"])-admitted_world)*density + bounds.x
                if first_pixel <= viewport_width and \
                        not bool(item.get("admitted_on_empty_strip",false)):
                    _fail("Authorized source was admitted inside the viewport")
                    return false
                ready_pass_serial = int(item["serial"])
                ready_take_owner = int(item.get("take_owner",ready_pass_serial))
                ready_world_origin = float(item["world_origin"])
                ready_source_floor = float(item.get("source_floor",0.0))
                ready_first_expiry_world = ready_world_origin + \
                    bounds.y/density + \
                    renderer.size.x*ScoreView.PLAYHEAD_FRACTION/density
                break
            if ready_pass_serial < 0:
                return false
        # This is the actual embedded Python transport, not a mocked
        # countdown: the same negative musical beat must reach the root
        # audio player before we accept the Play transition.
        var voice = app.get_node_or_null("CountInVoicePlayer")
        if str(app.current_state().get("phase","")) == "count_in" and \
                app.transport_beat_now() < -0.01:
            # Speech is opt-in; default Practice Flow uses a click and
            # visible number. A valid count-in must schedule at least one
            # real bundled voice or generated click from its single audio
            # owner. Dummy audio output cannot certify physical speakers.
            var audible_cues: int = int(voice.spoken_cues_total) + \
                int(app.countin_audio.click_cues_total)
            if audible_cues <= 0:
                if countin_audio_first_ms < 0:
                    countin_audio_first_ms = Time.get_ticks_msec()
                if Time.get_ticks_msec()-countin_audio_first_ms < 900:
                    return false
                _fail("Production countdown had no voice or click cue")
                return false
        initial_transport = int(app.current_state().get("transport_id",-1))
        var original_survived := false
        # The authorized take owns the original immutable source position.
        # No speculative READY copy is promoted or silently repositioned.
        for item in renderer.diagnostic_stream_snapshot():
            if int(item["serial"]) == ready_pass_serial:
                original_survived = is_equal_approx(
                    float(item["world_origin"]),ready_world_origin)
        if not original_survived:
            var diagnostic: Array = []
            for item in renderer.diagnostic_stream_snapshot():
                diagnostic.append({
                    "serial":int(item.get("serial",-1)),
                    "kind":str(item.get("kind","")),
                    "take_key":str(item.get("take_key","")),
                    "pending":bool(item.get("pending",false)),
                    "armed":bool(item.get("armed",false)),
                    "origin":float(item.get("world_origin",NAN)),
                    "floor":float(item.get("source_floor",NAN))
                })
            printerr("PHASE6_PLAY_STREAM_DIAGNOSTIC:",JSON.stringify({
                "ready_serial":ready_pass_serial,
                "ready_take_owner":ready_take_owner,
                "ready_origin":ready_world_origin,
                "world_beat":renderer.stream_world_beat,
                "state_phase":app.current_state().get("phase"),
                "original_survived":original_survived,
                "passes":diagnostic
            }))
            _fail("Play shifted its existing world origin or admitted notes onscreen")
            return false
        transport_seen = true
        print("PHASE6_PRODUCTION_TRANSPORT_STARTED transport=",initial_transport)
        return false
    if not pause_requested:
        if app.command_coordinator.state.pending:
            return false
        pause_requested = true
        app.send_action({"action":"pause"})
        return false
    if not pause_seen:
        if not bool(app.current_state().get("paused",false)):
            return false
        pause_seen = true
        print("PHASE6_PRODUCTION_PAUSE_OK")
        return false
    var renderer = app.practice_view.stage.renderer
    if not resume_requested:
        if paused_sample_ms < 0:
            paused_sample_ms = Time.get_ticks_msec()
            paused_world_beat = renderer.stream_world_beat
            paused_pass_serial = renderer.admission_queue_generation()
            return false
        if Time.get_ticks_msec()-paused_sample_ms < 400:
            return false
        # Pause holds the same immutable source/world position. No new
        # measure may be admitted and the visible staff must be stationary.
        if absf(renderer.stream_world_beat-paused_world_beat) > .01:
            _fail("Paused staff moved after the acknowledged Pause")
            return false
        if renderer.admission_queue_generation() != paused_pass_serial:
            _fail("Pause spawned another exercise instead of letting previous notes leave")
            return false
        var paused_original_preserved := false
        for item in renderer.diagnostic_stream_snapshot():
            if str(item.get("kind","source")) == "source" and \
                    int(item.get("take_owner",item["serial"])) == ready_take_owner:
                paused_original_preserved = paused_original_preserved or \
                    is_equal_approx(float(item["world_origin"]),ready_world_origin)
        if not paused_original_preserved and \
                renderer.stream_world_beat < ready_first_expiry_world:
            _fail("Pause withdrew the current unexpired source before Resume")
            return false
        if app.command_coordinator.state.pending:
            return false
        resume_requested = true
        app.send_action({"action":"resume"})
        return false
    if bool(app.current_state().get("paused",false)) or \
            not bool(app.current_state().get("running",false)):
        return false
    if int(app.current_state().get("transport_id",-1)) != initial_transport:
        _fail("Resume unexpectedly restarted the graded transport")
        return false
    if resumed_sample_ms < 0:
        resumed_sample_ms = Time.get_ticks_msec()
        resumed_world_beat = renderer.stream_world_beat
        resumed_pass_serial = renderer.admission_queue_generation()
        return false
    if Time.get_ticks_msec()-resumed_sample_ms < 450:
        return false
    var beat_advance: float = renderer.stream_world_beat-resumed_world_beat
    if beat_advance <= .04:
        _fail("Resume froze or reset the continuously moving staff")
        return false
    # After Resume, the staff must CONTINUE moving. A source inserted
    # outside the right edge may legitimately cross INTO the viewport in the
    # next 450 ms. Checking its current x coordinate would reject correct
    # scrolling. Verify the immutable admission location instead.
    var original_present := false
    var original_unchanged := true
    var copies := 0
    var future_only_at_enqueue := true
    var has_transport_binding := false
    var active_key: String = "%s|%d|%d|%s" % [
        str(app.current_state().get("piece_fingerprint","")),
        int(app.current_state().get("revision",-1)),
        initial_transport,str(app.current_state().get("mode","practice"))]
    var diagnostics: Array = []
    for item in renderer.diagnostic_stream_snapshot():
        if str(item.get("kind","source")) != "source":
            continue
        var serial: int = int(item["serial"])
        var take_owner: int = int(item.get("take_owner",serial))
        if take_owner == ready_take_owner:
            original_present = true
            original_unchanged = original_unchanged and \
                is_equal_approx(float(item["world_origin"]),ready_world_origin)
        if str(item.get("take_key","")) == active_key and \
                not bool(item.get("pending",false)):
            has_transport_binding = true
        if serial > paused_pass_serial:
            copies += 1
            var density_at_enqueue: float = float(item.get(
                "admitted_density",NAN))
            var gap_at_enqueue: float = float(item.get(
                "admitted_staff_gap",NAN))
            var world_at_enqueue: float = float(item.get(
                "admitted_world",NAN))
            var playhead_at_enqueue: float = float(item.get(
                "admitted_playhead_x",NAN))
            var viewport_at_enqueue: float = float(item.get(
                "admitted_viewport_width",NAN))
            var admitted_outside: bool = false
            if is_finite(density_at_enqueue) and \
                    is_finite(gap_at_enqueue) and \
                    is_finite(world_at_enqueue) and \
                    is_finite(playhead_at_enqueue) and \
                    is_finite(viewport_at_enqueue) and density_at_enqueue > 0:
                var bounds: Vector2 = Admission.clip_bounds(
                    item,density_at_enqueue,gap_at_enqueue,
                    renderer.timeline.duration_beats)
                var earliest_x: float = playhead_at_enqueue + \
                    (float(item["world_origin"])-world_at_enqueue)*density_at_enqueue + \
                    bounds.x
                # Inside the viewport only onto an empty strip, which the
                # queue verified at enqueue (owner decision 2026-11-08).
                admitted_outside = earliest_x > viewport_at_enqueue or \
                    bool(item.get("admitted_on_empty_strip",false))
            future_only_at_enqueue = future_only_at_enqueue and admitted_outside
        diagnostics.append({
            "serial":serial,"take_owner":take_owner,
            "kind":str(item.get("kind","")),
            "key":str(item.get("take_key","")),
            "origin":float(item.get("world_origin",NAN)),
            "floor":float(item.get("source_floor",NAN)),
            "admitted_world":float(item.get("admitted_world",NAN)),
            "pending":bool(item.get("pending",false)),
            "visible":bool(item.get("ever_visible",false))})
    # The head may disappear only after its last printed pixel has left
    # the viewport. An exposed remainder of the same logical take keeps
    # the original musical placement; no new take can silently replace it.
    # A take paused in its count-in never sounded: Resume gives it a fresh
    # full count-in bar, so its unplayed notes make way for the new copy.
    var original_legitimately_retired: bool = \
        not original_present and (
            renderer.stream_world_beat >= ready_first_expiry_world-.00001 or
            ready_world_origin+ready_source_floor > paused_world_beat+.00001)
    if not original_unchanged or \
            not (original_present or original_legitimately_retired) or \
            not future_only_at_enqueue or not has_transport_binding:
        printerr("PHASE6_RESUME_STREAM_DIAGNOSTIC:",JSON.stringify({
            "world":renderer.stream_world_beat,
            "original_origin":ready_world_origin,
            "original_take_owner":ready_take_owner,
            "first_strip_expiry":ready_first_expiry_world,
            "original_present":original_present,
            "original_unchanged":original_unchanged,
            "original_retired_safely":original_legitimately_retired,
            "future_only_at_enqueue":future_only_at_enqueue,
            "new_source_strips":copies,
            "has_transport_binding":has_transport_binding,
            "expected_transport":active_key,
            "passes":diagnostics}))
        _fail("Resume changed committed notation, lost a live take, " +
            "or admitted new notes within the viewport")
        return false
    if not is_finite(renderer.timeline.pixels_per_beat) or \
            renderer.timeline.pixels_per_beat <= 0.0:
        _fail("Score horizontal density is invalid")
        return false
    if not renderer.retained_ready():
        _fail("Resume lost the already engraved source notation")
        return false
    print("PHASE6_PRODUCTION_CONTINUOUS_FLOW_OK beat_delta=",beat_advance,
        " admitted_before=",paused_pass_serial,
        " admitted_after=",renderer.admission_queue_generation(),
        " new_source_strips=",copies,
        " selected_bpm=",app.current_state().get("bpm"))
    print("PHASE6_PRODUCTION_UI_WORKFLOW_OK")
    _finish(0)
    return false

func _fail(message: String) -> void:
    printerr("PHASE6_PRODUCTION_UI_FAILED: ",message)
    _finish(1)
