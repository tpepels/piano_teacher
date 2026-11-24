extends SceneTree
## Real production main.tscn + embedded Python + actual native notation,
## with a TEST-ONLY mido input port at the hardware boundary. No fake
## state machine, renderer, assessment, shortcut, or transport owner.
const MAX_MS := 200000
var app
var begun_ms := 0
var phase_ms := 0
var last_heartbeat_ms := 0
var phase := "boot"
var udp := PacketPeerUDP.new()
var first_pitch := -1
var initial_transport := -1
var first_midi_input := -1
var free_hold_world := NAN
var free_hold_since_ms := -1
var wrong_free_world := NAN
var wrong_free_at_ms := -1
var paused_world := NAN
var paused_at_ms := -1
var paused_target := -1
var tempo_paused_at_ms := -1
var tempo_paused_world := NAN
var tempo_paused_generation := -1
var stopped_at_ms := -1
var failed_take_seen := false
var played_first := false
var played_second := false
# Continuity invariant (owner report 2026-11-24): the staff may never jump.
var continuity_world := NAN
var continuity_ms := -1
var continuity_violation := ""
var ink_shown_since := -1
# Beat of the fixture's second note: 3.0 in the 4/4 fixture, 1.0 in 2/4.
var second_beat: float = float(OS.get_environment("PIANO_TEST_SECOND_BEAT")) \
    if not OS.get_environment("PIANO_TEST_SECOND_BEAT").is_empty() else 3.0

func _initialize() -> void:
    call_deferred("_boot")


func _boot() -> void:
    begun_ms = Time.get_ticks_msec()
    root.size = Vector2i(1280,800)
    var port: int = int(OS.get_environment("PIANO_TEST_FAKE_MIDI_PORT"))
    if port <= 0 or udp.connect_to_host("127.0.0.1",port) != OK:
        _fail("Synthetic hardware-edge MIDI port not configured")
        return
    var scene: PackedScene = load("res://main.tscn")
    if scene == null:
        _fail("Production scene cannot load")
        return
    app = scene.instantiate()
    root.add_child(app)
    _advance("connect")


func _advance(next: String) -> void:
    phase = next
    phase_ms = Time.get_ticks_msec()
    print("FULL_SCENE_MIDI_STEP:",next)


func _send(pitch: int, on: bool) -> void:
    var message := JSON.stringify({
        "type":"note_on" if on else "note_off","pitch":pitch})
    if udp.put_packet(message.to_utf8_buffer()) != OK:
        _fail("Cannot send synthetic input through the MIDI device port")


func _strike(pitch: int) -> void:
    _send(pitch,true)
    _send(pitch,false)


func _fail(message: String) -> void:
    var witness: Dictionary = app.current_state() if is_instance_valid(app) else {}
    printerr("FULL_SCENE_MIDI_FAILED:",phase,": ",message," state=",
        JSON.stringify({
            "mode":witness.get("mode"),"phase":witness.get("phase"),
            "flow":witness.get("flow"),"revision":witness.get("revision"),
            "hand":witness.get("hand"),"bpm":witness.get("bpm"),
            "first_bar":witness.get("first_bar"),
            "last_bar":witness.get("last_bar"),
            "transport_id":witness.get("transport_id"),
            "input_count":witness.get("midi_input_count"),
            "paused":witness.get("paused"),
            "teaching":witness.get("teaching"),
            "score_error":app.score_error if is_instance_valid(app) else ""}))
    quit(1)


func _press_primary() -> bool:
    if app.command_coordinator.state.pending:
        return false
    if app.practice_view.start_button.disabled:
        _fail("The main Pause/Resume button is disabled in a playable state")
        return false
    app.practice_view.start_button.pressed.emit()
    return true


func _check_continuity(renderer, state: Dictionary, now_ms: int, step: String) -> String:
    # Between two painted frames the staff moves forward by at most what
    # the fastest current tempo covers in that time (plus frame slack).
    # A visible jump forward or backward is a defect in every phase.
    var world: float = float(renderer.stream_world_beat)
    if not is_finite(world):
        return ""
    if is_finite(continuity_world) and continuity_ms >= 0:
        var dt: float = maxf(0.0, float(now_ms-continuity_ms)/1000.0)
        var bpm: float = maxf(float(state.get("bpm",0.0)), float(state.get("target_bpm",0.0)))
        var allowed: float = maxf(bpm, 60.0)*1.25/60.0*dt + .06
        var moved: float = world-continuity_world
        if moved > allowed or moved < -.002:
            return ("Staff jumped %.3f beats in %.0f ms (allowed %.3f) phase=%s step=%s mode=%s" % [
                moved, dt*1000.0, allowed, phase, step, str(state.get("mode",""))])
    continuity_world = world
    continuity_ms = now_ms
    return ""

func _process(_delta: float) -> bool:
    if app == null or not is_instance_valid(app):
        return false
    if Time.get_ticks_msec()-begun_ms > MAX_MS:
        _fail("Native fake-MIDI journey timed out")
        return true
    if not app.score_error.is_empty():
        _fail("Native notation failed: "+app.score_error)
        return true
    var state: Dictionary = app.current_state()
    var now_ms: int = Time.get_ticks_msec()
    if now_ms-last_heartbeat_ms >= 5000:
        last_heartbeat_ms = now_ms
        var beat: Dictionary = {
            "phase":phase,"elapsed_ms":now_ms-begun_ms,
            "phase_elapsed_ms":now_ms-phase_ms,
            "native_started":app.native_started,
            "startup_checked":app.startup_last_music_checked,
            "loaded":bool(state.get("loaded",false)),
            "mode":state.get("mode"),"step":state.get("flow",{}).get("step"),
            "transport_id":state.get("transport_id"),
            "backend_phase":state.get("phase"),
            "paused":state.get("paused"),"running":state.get("running"),
            "command_pending":app.command_coordinator.state.pending,
            "score_ready":app.score_session.is_ready(),
            "admission_problem":app.score_admission.last_problem()}
        if phase == "free":
            # A stall waiting for the first Free target shows which
            # condition (guided world, held target, projection, painted
            # staff) never settled.
            beat["free_world"] = str(app.presentation_session.guided.world)
            beat["hold_world"] = str(app.presentation_session.score_flow.hold_world)
            beat["projected"] = str(app.presentation_session.score_flow.project(now_ms))
            beat["painted"] = str(app.practice_view.stage.renderer.stream_world_beat)
            var heartbeat_teaching: Variant = state.get("teaching")
            beat["targets"] = (heartbeat_teaching.get("expected_notes",[]).size()
                if heartbeat_teaching is Dictionary else -1)
        print("FULL_SCENE_MIDI_HEARTBEAT:", JSON.stringify(beat))
    if not app.native_started or not app.startup_last_music_checked or \
            not bool(state.get("loaded",false)):
        return false
    var step: String = str(state.get("flow",{}).get("step",""))
    var mode: String = str(state.get("mode",""))
    var renderer = app.practice_view.stage.renderer
    var continuity: String = _check_continuity(renderer, state, now_ms, step)
    if not continuity.is_empty():
        _fail(continuity)
        return true
    # The journey stays on one window: once its notes are drawn they may
    # never vanish (Free -> Tempo, Pause/Resume and repeats keep the ink).
    var ink: bool = renderer.native_ready and renderer.retained_ready() and \
        not renderer.timeline.notes.is_empty()
    if ink and ink_shown_since < 0 and phase not in ["boot","connect"]:
        ink_shown_since = now_ms
    if ink_shown_since >= 0 and not ink and phase not in ["stop_tempo","stopped_stable"]:
        _fail("Drawn notes vanished in phase %s (step %s, revision %s)" % [
            phase, step, str(state.get("revision",""))])
        return true
    match phase:
        "connect":
            if app.command_coordinator.state.pending or not app.score_session.is_ready() or \
                    state.get("device") != "CI Synthetic Keyboard":
                return false
            if (int(state.get("first_bar",0)) != 1 or
                    int(state.get("last_bar",0)) != 1 or
                    str(state.get("hand","")) != "right"):
                _fail("Opening the real scene selected the wrong practice window")
                return true
            if not renderer.native_ready or not renderer.retained_ready() or \
                    renderer.timeline.notes.is_empty():
                _fail("First practice score was not visibly compiled")
                return true
            # The ordinary persisted-device scan connected the fake input.
            # Do not issue a mid-Lesson device.select, which intentionally
            # stops an active musical attempt in the real application.
            _advance("free")
        "free":
            if state.get("device") != "CI Synthetic Keyboard" or \
                    step != "free" or mode != "learn" or \
                    not app.score_session.is_ready():
                return false
            var targets: Array = state.get("teaching",{}).get("expected_notes",[])
            if targets.is_empty():
                return false
            # The first authored Free source is admitted in the FUTURE
            # and travels to its fixed target before it becomes a held
            # practice prompt. Waiting for the actual printed target to
            # reach the playhead prevents a false failure that interprets
            # this authorized initial travel as progress from wrong MIDI.
            var free_owner = app.presentation_session.guided
            var source_flow = app.presentation_session.score_flow
            now_ms = Time.get_ticks_msec()
            if (not is_finite(free_owner.world) or
                    not is_finite(source_flow.hold_world) or
                    absf(source_flow.project(now_ms)-source_flow.hold_world) > .02):
                free_hold_since_ms = -1
                return false
            if free_hold_since_ms < 0:
                free_hold_since_ms = now_ms
                free_hold_world = renderer.stream_world_beat
                return false
            if (absf(renderer.stream_world_beat-free_hold_world) > .02):
                # Native score painting can still finish its frame after
                # the world timeline reaches the held target. Require a
                # stable displayed staff, not just a backend clock fact.
                free_hold_since_ms = -1
                return false
            if now_ms-free_hold_since_ms < 250:
                return false
            print("FULL_SCENE_FREE_TARGET_HELD world=",free_hold_world)
            first_pitch = int(targets[0]["pitch"])
            first_midi_input = int(state.get("midi_input_count",0))
            _strike(61)
            _advance("wrong_free")
        "wrong_free":
            var teaching: Dictionary = state.get("teaching",{})
            if str(teaching.get("hint_reason","")) != "wrong_note":
                return false
            if int(teaching.get("target_index",-1)) != 0 or \
                    int(state.get("midi_input_count",0)) <= first_midi_input:
                _fail("Wrong synthetic note gained Free credit or was not received")
                return true
            if wrong_free_at_ms < 0:
                # The backend already registered the wrong note, so
                # subsequent frames without MIDI must stay on its held
                # Free target. A target/error hint cannot start the bar.
                wrong_free_at_ms = Time.get_ticks_msec()
                wrong_free_world = renderer.stream_world_beat
                return false
            if Time.get_ticks_msec()-wrong_free_at_ms < 350:
                return false
            if absf(renderer.stream_world_beat-wrong_free_world) > .02:
                _fail("Wrong MIDI or silence advanced the stationary Free score")
                return true
            print("FULL_SCENE_FREE_WRONG_HOLD_OK world=",wrong_free_world)
            if _press_primary():
                _advance("pause_free")
        "pause_free":
            if not bool(state.get("paused",false)):
                return false
            if paused_at_ms < 0:
                paused_at_ms = Time.get_ticks_msec()
                paused_world = renderer.stream_world_beat
                paused_target = int(state.get("teaching",{}).get("target_index",-1))
                _strike(first_pitch)
                return false
            if Time.get_ticks_msec()-paused_at_ms < 380:
                return false
            if absf(renderer.stream_world_beat-paused_world) > 0.02 or \
                    int(state.get("teaching",{}).get("target_index",-1)) != paused_target:
                _fail("Pause did not freeze staff or prevent Free MIDI credit")
                return true
            if _press_primary():
                _advance("resume_free")
        "resume_free":
            if bool(state.get("paused",false)):
                return false
            _strike(first_pitch)
            _advance("first_free")
        "first_free":
            if int(state.get("teaching",{}).get("target_index",-1)) < 1:
                return false
            var targets: Array = state.get("teaching",{}).get("expected_notes",[])
            if targets.is_empty():
                return false
            _strike(int(targets[0]["pitch"]))
            _advance("tempo")
        "tempo":
            if step != "tempo" or mode != "practice" or \
                    not bool(state.get("running",false)):
                return false
            if int(state.get("first_bar",0)) != 1 or \
                    int(state.get("last_bar",0)) != 1 or \
                    int(state.get("bpm",0)) != 40:
                _fail("Free did not begin first measure Tempo at 50%")
                return true
            # The renderer may have pre-engraved a full piece, but the
            # physically admitted queue must contain ONLY the selected
            # one-bar practice source (plus sounding tails and rests).
            # No extra neighboring measure may enter as hidden context.
            var active_source: Dictionary = state.get("practice_timeline",{})
            var source_bound: float = maxf(
                float(active_source.get("source_duration_beats",NAN)),
                float(active_source.get("sounding_duration_beats",NAN)))
            if not is_finite(source_bound) or source_bound <= 0.0:
                _fail("Timed source has no authenticated practice-window duration")
                return true
            var actual_source_count := 0
            var active_take_strips := 0
            var active_key: String = "%s|%d|%d|%s" % [
                str(state.get("piece_fingerprint","")),
                int(state.get("revision",-1)),
                int(state.get("transport_id",-1)),
                str(state.get("mode","practice"))]
            for strip in renderer.diagnostic_stream_snapshot():
                if str(strip.get("kind","")) != "source":
                    continue
                actual_source_count += 1
                if str(strip.get("take_key","")) == active_key:
                    active_take_strips += 1
                if (float(strip.get("source_floor",-INF)) < -.0001 or
                        float(strip.get("source_ceiling",INF)) > source_bound+.0001):
                    _fail("Native score queue contains measures outside selected passage")
                    return true
            if actual_source_count == 0 or active_take_strips != 1:
                _fail("Timed one-bar take has missing or duplicate physically authorized ink")
                return true
            print("FULL_SCENE_SELECTED_WINDOW_OK duration=",source_bound,
                " admitted_sources=",actual_source_count,
                " bound_source_strips=",active_take_strips)
            initial_transport = int(state.get("transport_id",-1))
            if initial_transport <= 0:
                _fail("Tempo has no published transport identity")
                return true
            # Run a real timed Pause/Resume through the same primary button
            # and native immutable queue used by a physical player, before
            # any wrong MIDI can force a retry.
            if _press_primary():
                _advance("pause_tempo")
        "pause_tempo":
            if not bool(state.get("paused",false)):
                return false
            tempo_paused_world = renderer.stream_world_beat
            tempo_paused_generation = renderer.admission_queue_generation()
            tempo_paused_at_ms = Time.get_ticks_msec()
            _advance("paused_tempo")
        "paused_tempo":
            if Time.get_ticks_msec()-tempo_paused_at_ms < 420:
                return false
            if not bool(state.get("paused",false)) or \
                    int(state.get("transport_id",-1)) != initial_transport or \
                    absf(renderer.stream_world_beat-tempo_paused_world) > .02 or \
                    renderer.admission_queue_generation() != tempo_paused_generation:
                _fail("Timed Pause moved the staff, changed the take, or admitted new ink")
                return true
            print("FULL_SCENE_TEMPO_PAUSE_HELD:",tempo_paused_world)
            if _press_primary():
                _advance("resume_tempo")
        "resume_tempo":
            if bool(state.get("paused",false)) or \
                    not bool(state.get("running",false)):
                return false
            if int(state.get("transport_id",-1)) != initial_transport or \
                    int(state.get("first_bar",0)) != 1 or \
                    int(state.get("last_bar",0)) != 1:
                _fail("Timed Resume lost its attempt identity or selected window")
                return true
            print("FULL_SCENE_TEMPO_RESUME_OK transport=",initial_transport)
            _advance("wrong_tempo")
        "wrong_tempo":
            if int(state.get("transport_id",-1)) != initial_transport:
                _fail("Tempo advanced before receiving a failed MIDI input")
                return true
            if str(state.get("phase","")) != "playing" or \
                    float(state.get("clock_beat",-100.0)) < 0.2:
                return false
            _strike(61)
            _advance("repeat")
        "repeat":
            if int(state.get("transport_id",-1)) == initial_transport:
                return false
            if (int(state.get("transport_id",-1)) != initial_transport+1 or
                    step != "tempo" or int(state.get("bpm",0)) != 40 or
                    int(state.get("lesson_steps_mastered",0)) != 0):
                _fail("Wrong MIDI did not cause one failed same-tempo repeat")
                return true
            failed_take_seen = true
            _advance("second_failure")
        "second_failure":
            # A second failed take in a row at 50% returns to Free.
            if str(state.get("phase","")) != "playing" or \
                    float(state.get("clock_beat",-100.0)) < 0.2:
                return false
            _strike(61)
            _advance("free_again")
        "free_again":
            if mode != "learn" or step != "free":
                if int(state.get("transport_id",-1)) > initial_transport+1 and \
                        mode == "practice" and bool(state.get("running",false)):
                    _fail("Two failed takes at 50% did not return to Free")
                    return true
                return false
            if int(state.get("lesson_steps_mastered",0)) != 0 or \
                    bool(state.get("running",false)):
                _fail("Returning to Free granted credit or kept a take running")
                return true
            var again: Array = state.get("teaching",{}).get("expected_notes",[])
            var held: float = app.presentation_session.score_flow.hold_world
            if again.is_empty() or not is_finite(held) or \
                    absf(app.presentation_session.score_flow.project(now_ms)-held) > .02:
                free_hold_since_ms = -1
                return false
            # The target must rest at the playhead before a key counts.
            if free_hold_since_ms < 0:
                free_hold_since_ms = now_ms
                return false
            if now_ms-free_hold_since_ms < 400:
                return false
            print("FULL_SCENE_FREE_AFTER_TWO_FAILURES held=",held)
            _strike(int(again[0]["pitch"]))
            _advance("free_again_last")
        "free_again_last":
            if mode == "practice":
                _advance("tempo_again")
                return false
            var targets: Array = state.get("teaching",{}).get("expected_notes",[])
            if targets.is_empty():
                return false
            if int(state.get("teaching",{}).get("target_index",-1)) >= 1:
                _strike(int(targets[0]["pitch"]))
                _advance("tempo_again")
            elif now_ms-phase_ms > 600:
                # The first key may have come while the target was arriving.
                _strike(int(targets[0]["pitch"]))
                phase_ms = now_ms
        "tempo_again":
            if step != "tempo" or mode != "practice" or \
                    not bool(state.get("running",false)):
                return false
            if int(state.get("bpm",0)) != 40:
                _fail("Tempo after Free did not restart at 50%")
                return true
            # The clean and faster checks count takes from here.
            initial_transport = int(state.get("transport_id",-1))-1
            _advance("clean_repeat")
        "clean_repeat":
            if int(state.get("transport_id",-1)) <= initial_transport or \
                    str(state.get("phase","")) != "playing":
                return false
            var beat: float = float(state.get("clock_beat",-100.0))
            if not played_first and beat >= 0.0 and beat < 0.45:
                _strike(72)
                played_first = true
            if played_first and not played_second and beat >= second_beat and beat < second_beat+.45:
                _strike(79)
                played_second = true
            if played_second:
                _advance("faster")
        "faster":
            if int(state.get("transport_id",-1)) <= initial_transport+1:
                return false
            if (int(state.get("transport_id",-1)) != initial_transport+2 or
                    not failed_take_seen or not played_first or not played_second or
                    # A clean take is faster: the step grows with timing
                    # quality and shrinks with the window's attack count.
                    int(state.get("bpm",0)) <= 40 or int(state.get("bpm",0)) > 80 or
                    int(state.get("lesson_steps_mastered",0)) != 0):
                _fail("Two real MIDI attacks did not produce a clean faster repeat (above 40 BPM)")
                return true
            # Owner rule: a repeat comes from the right. Its notes were
            # drawn ahead and scrolled in; none popped onto the staff.
            if app.score_admission.repeats_from_the_right < 1:
                _fail("Automatic repeats did not scroll in from the right")
                return true
            # End an already accepted take through the production UI port.
            # Pending auto-continuations must be invalidated; no late score
            # status/reply may restart musical grading after Stop.
            app.send_action({"action":"ui_stop"})
            _advance("stop_tempo")
        "stop_tempo":
            if app.command_coordinator.state.pending or \
                    str(state.get("feedback","")) != "Stopped":
                return false
            if bool(state.get("running",false)) or bool(state.get("paused",false)) or \
                    state.get("playback_intent") is Dictionary:
                _fail("Stop left a running take or outstanding native admission")
                return true
            stopped_at_ms = Time.get_ticks_msec()
            _advance("stopped_stable")
        "stopped_stable":
            if bool(state.get("running",false)) or bool(state.get("paused",false)) or \
                    state.get("playback_intent") is Dictionary:
                _fail("Late native callback restarted playback after Stop")
                return true
            if Time.get_ticks_msec()-stopped_at_ms < 450:
                return false
            print("FULL_SCENE_MIDI_SUCCESS: wrong_free pause_free resume_free pause_tempo resume_tempo wrong_tempo auto_repeat second_failure free_again clean_tempo stop")
            quit(0)
    return false
