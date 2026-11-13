extends RefCounted
## Command lifecycle, queued transport intent and provisional score reservation.
## Explicit presentation/clock/request owners only; no Main reference.
const CommandRequestState := preload("res://command_request_state.gd")
const CommandSuccessPolicy := preload("res://command_success_policy.gd")
const StreamAdmission := preload("res://score_stream_admission.gd")
const CountInCueTimeline := preload("res://countin_cue_timeline.gd")
signal succeeded(decision: Dictionary, opened: Variant, code: int, body: PackedByteArray, started_ms: int)
signal learning_accepted(operation: String, values: Dictionary)
signal library_requested(piece: String, resume_saved: bool)
signal refresh_requested
signal fingering_changed(message: String)
signal score_error_cleared
var state = CommandRequestState.new()
var request_token := 0
var last_published_control_started_ms := -1
var last_state: Dictionary = {}
var practice_view
var settings_view
var metronome_frame
var score_flow
var visual_transport_clock
var action_request
var command_failure_presenter
var fingering_save_error := ""
var _pending_stream_renderer

func configure(practice, settings, metronome, flow, clock, request, failure_presenter) -> void:
    practice_view = practice
    settings_view = settings
    metronome_frame = metronome
    score_flow = flow
    visual_transport_clock = clock
    action_request = request
    command_failure_presenter = failure_presenter

func _transport_beat_at(at_ms: int) -> float:
    return visual_transport_clock.score_beat(at_ms) if visual_transport_clock.matches(last_state) else float(last_state.get("clock_beat",0.0))

func _decode_json(body: PackedByteArray) -> Variant:
    if body.is_empty():
        return null
    var document := JSON.new()
    return document.data if document.parse(body.get_string_from_utf8()) == OK else null

func _command_failure(code: int, body: PackedByteArray) -> String:
    var response = _decode_json(body)
    return str(response.get("error","Command failed (status %d)" % code)) if response is Dictionary else "Embedded practice engine unavailable (status %d)" % code

func _flush_transport_action() -> void:
    var action: String = state.take_transport()
    if not action.is_empty():
        request_action({"action":action},last_state)

func _cancel_pending_stream_arm() -> void:
    if _pending_stream_renderer != null and is_instance_valid(_pending_stream_renderer):
        _pending_stream_renderer.cancel_stream_arm()
    _pending_stream_renderer = null

func tick(_now_ms: int) -> void:
    # Request deadlines and causal completion filtering belong to InProcessRequest.
    pass

func request_action(command: Dictionary, presentation_facts: Dictionary) -> void:
    last_state = presentation_facts
    var requested: String = str(command.get("action", ""))
    var previous_action: String = state.control_action
    if not state.action_requested(requested):
        # Busy operations still show their current action; Pause/Stop queues.
        practice_view.begin_action(requested, previous_action)
        return
    practice_view.begin_action(requested)
    if not requested in ["start","restart","resume"]:
        metronome_frame.cancel_reserved_count_in()
    var rest_phase: bool = not bool(last_state.get("running",false)) and \
        str(last_state.get("pause_context",last_state.get("phase",""))) in [
            "feedback","recovering","preview_gap"]
    if requested == "resume" and rest_phase and \
            str(last_state.get("mode","practice")) == "practice" and \
            practice_view.stage.renderer != null:
        # Resume in the rest between takes: there is no paused take to
        # reserve. Report where the announced next take's source can still
        # be admitted offscreen; the engine re-announces its deadline no
        # earlier than that (the axis kept moving during the pause).
        var rest_at_ms: int = Time.get_ticks_msec()
        var rest_now: float = score_flow.project(rest_at_ms)
        var rest_renderer = practice_view.stage.renderer
        command = command.duplicate(true)
        # The announced copy may already be on the staff (it opens one bar
        # ahead on the empty strip): while still ahead of the playhead the
        # take keeps it, like Resume of a paused take, re-timed to reach the
        # playhead where it now is. Otherwise report where fresh ink fits.
        var copy_onset: float = rest_renderer.announced_copy_onset(rest_now)
        # Godot alone decides the reuse (I3): the copy keeps its count-in
        # only with at least one count-in PULSE (a dotted quarter in
        # compound meters) at the announced tempo, plus the engine's
        # published snapshot latency, still ahead; otherwise a fresh copy.
        var plan: Dictionary = last_state.get("score_queue_next",{}) \
            if last_state.get("score_queue_next") is Dictionary else {}
        var plan_bpm: float = maxf(1.0,float(plan.get("bpm",
            last_state.get("bpm",score_flow.bpm))))
        var pulse: float = CountInCueTimeline.pulse_beats(plan.get(
            "count_in_meter",last_state.get("count_in_meter")))
        var rest_bpm: float = float(last_state.get("bpm",score_flow.bpm))
        if is_finite(copy_onset) and StreamAdmission.lead_seconds(copy_onset,
                rest_now,rest_bpm) < pulse*60.0/plan_bpm+float(
                    last_state.get("short_rest_latency_seconds",0.0)):
            copy_onset = NAN
        if is_finite(copy_onset):
            command["presentation_lead_seconds"] = StreamAdmission.lead_seconds(
                copy_onset,rest_now,float(last_state.get("bpm",score_flow.bpm)))
            command["reuse_announced_score"] = true
        else:
            var earliest: float = rest_renderer.earliest_continuation_world(
                rest_now,0.0,float(last_state.get("next_count_in_beats",0.0)))
            if is_finite(earliest):
                command["presentation_lead_seconds"] = StreamAdmission.lead_seconds(
                    earliest,rest_now,float(last_state.get("bpm",score_flow.bpm)))
        command.merge(rest_renderer.short_rest_geometry(),true)
        if command.has("presentation_lead_seconds") and \
                visual_transport_clock.has_backend_offset:
            command["presentation_deadline_ms"] = float(rest_at_ms) + \
                float(command["presentation_lead_seconds"])*1000.0 - \
                visual_transport_clock.backend_offset_ms
        command["continuous_horizon_beats"] = StreamAdmission.automatic_horizon(
            float(practice_view.stage.renderer.practice_timeline.get(
                "gap",{}).get("duration_beats",0.0)),
            practice_view.stage.renderer._stream_right_beats(),
            practice_view.stage.renderer._stream_header_beats(0.0))
        request_command("practice.command", command)
        return
    if requested in ["start","restart","resume"] and \
            str(last_state.get("mode","practice")) in ["practice","perform"] and \
            practice_view.stage.renderer != null:
        # The user's action reserves the next musical deadline beyond all
        # notes still moving on the visual bar. The engine, not the GUI,
        # applies this lead to MIDI grading and count-in.
        var reserved_at_ms: int = Time.get_ticks_msec()
        var visual_now: float = score_flow.project(reserved_at_ms)
        var renderer = practice_view.stage.renderer
        var opening: float = maxf(0.0,float(last_state.get("play_from_beat",0.0)))
        if requested == "resume":
            opening = maxf(opening,opening+_transport_beat_at(Time.get_ticks_msec()))
        # One preflighted transaction plans the maximal retractable suffix,
        # verifies a future admission, then commits it with one graded deadline.
        # Failure cannot mutate the online queue before a valid plan exists.
        # The engine publishes the one count-in bar this action gets; on an
        # empty strip the opening is placed exactly that far ahead.
        # Play/Resume open one count-in bar plus the engine's published
        # snapshot latency ahead (I5): the first syllable then falls after
        # this frame's reservation work, and the count-in bar itself still
        # ends exactly at the take's first beat.
        var count_in_slot: float = float(last_state.get("next_count_in_beats",0.0))
        if requested in ["start","resume"] and count_in_slot > 0.0:
            count_in_slot += float(last_state.get("short_rest_latency_seconds",0.0))* \
                float(last_state.get("bpm",score_flow.bpm))/60.0
        var reserved: Dictionary = renderer.reserve_transport_action(
            requested,visual_now,opening,count_in_slot)
        if reserved.is_empty():
            state.abort_action()
            practice_view.finish_action()
            practice_view.present_message(
                "Score reservation failed · see SCORE_TRANSPORT diagnostic")
            return
        _pending_stream_renderer = renderer
        command = command.duplicate(true)
        # World beats to seconds at the rate the axis moves at AFTER this
        # command: Play's count-in and Retry's rest run at the selected BPM
        # (a tempo-mapped take, e.g. a slowdown stage, ran at its own rate
        # until now); a mid-take Resume continues inside the take's map.
        var lead_bpm: float = StreamAdmission.command_lead_bpm(requested,
            score_flow.bpm,float(last_state.get("bpm",score_flow.bpm)))
        command["presentation_lead_seconds"] = StreamAdmission.lead_seconds(
            float(reserved["start_world"]),visual_now,lead_bpm)
        if visual_transport_clock.has_backend_offset:
            # The reserved deadline itself (backend clock): the engine
            # measures the lead when it processes the command.
            command["presentation_deadline_ms"] = float(reserved_at_ms) + \
                float(command["presentation_lead_seconds"])*1000.0 - \
                visual_transport_clock.backend_offset_ms
        if requested == "resume":
            command["reuse_pending_score"] = bool(
                reserved.get("reused_unplayed_count_in",false))
        # Godot knows this deadline now: speak its count-in from it, on
        # every beat, before the engine's state confirms the take (M4).
        if not bool(reserved.get("reused_unplayed_count_in",false)):
            metronome_frame.reserve_count_in(float(reserved_at_ms)+
                float(command["presentation_lead_seconds"])*1000.0,
                float(last_state.get("bpm",score_flow.bpm)),
                # One count-in bar: next_count_in_beats IS that bar (an idle
                # snapshot's count_in_bar_beats can still be a default).
                float(last_state.get("next_count_in_beats",0.0)),
                last_state.get("next_count_in_meter",
                    last_state.get("count_in_meter")),
                float(last_state.get("next_count_in_beats",0.0)),requested)
        var written_rest: float = float(renderer.practice_timeline.get(
            "gap",{}).get("duration_beats",0.0))
        command["continuous_horizon_beats"] = StreamAdmission.automatic_horizon(
            written_rest,renderer._stream_right_beats(),
            renderer._stream_header_beats(0.0))
        command.merge(renderer.short_rest_geometry(),true)
    request_command("practice.command", command)


func request_command(operation: String, payload: Dictionary) -> void:
    if not state.begin(operation,Time.get_ticks_msec()):
        if operation == "practice.command":
            _cancel_pending_stream_arm()
            # No take starts: a reserved count-in must not be spoken (I2).
            metronome_frame.cancel_reserved_count_in()
        return
    request_token += 1
    practice_view.present_busy(true)
    settings_view.present_busy(true)
    var err: int = state.dispatch(action_request,operation,payload)
    if err != OK:
        if operation == "practice.command":
            _cancel_pending_stream_arm()
            # No take starts: a reserved count-in must not be spoken (I2).
            metronome_frame.cancel_reserved_count_in()
        practice_view.present_busy(false)
        settings_view.present_busy(false)
        if operation == "practice.command":
            practice_view.finish_action()
        var message := "Cannot reach practice engine (status %d)" % err
        if operation == "fingering.correct":
            fingering_save_error = message
            fingering_changed.emit(fingering_save_error)
        var queued_library_failed: bool = state.discard_library()
        command_failure_presenter.present(message,operation,queued_library_failed)
        _flush_transport_action()

func accept_response(token: int, code: int, body: PackedByteArray) -> void:
    # Only the active request may publish a success or error. A timed-out
    # callback or a canceled worker completion has no live command owner.
    if token != request_token or not state.pending:
        return
    var completed: Dictionary = state.finish()
    practice_view.present_busy(false)
    settings_view.present_busy(false)
    var operation: String = str(completed["operation"])
    if operation == "practice.command":
        practice_view.finish_action()
    var resume_saved: bool = bool(completed["resume_saved"])
    var completed_action: String = str(completed["action"])
    if code != 0:
        if operation == "practice.command":
            _cancel_pending_stream_arm()
            # No take starts: a reserved count-in must not be spoken (I2).
            metronome_frame.cancel_reserved_count_in()
        var message := _command_failure(code, body)
        if operation == "fingering.correct":
            fingering_save_error = message
            fingering_changed.emit(fingering_save_error)
        var queued_library_failed: bool = state.discard_library()
        command_failure_presenter.present(message,operation,queued_library_failed)
        _flush_transport_action()
        return
    var opened: Variant = _decode_json(body) if operation == "library.open" else null
    if operation in ["learning.export", "learning.delete_piece", "learning.delete_learner"]:
        var result = _decode_json(body)
        learning_accepted.emit(operation, result if result is Dictionary else {})
    var decision: Dictionary = CommandSuccessPolicy.decide(
        operation,completed_action,resume_saved,opened)
    if str(decision["kind"]) == "fingering":
        fingering_save_error = ""
    elif str(decision["kind"]) == "library_open":
        score_error_cleared.emit()
    if bool(decision.get("publish_state",false)):
        last_published_control_started_ms = maxi(
            last_published_control_started_ms,int(completed["started_ms"]))
    if operation == "practice.command" and \
            _pending_stream_renderer != null and \
            is_instance_valid(_pending_stream_renderer):
        # Commit the provisional source owner only after successful backend
        # acknowledgement, before the response publishes its transport ID.
        _pending_stream_renderer.acknowledge_stream_arm()
    if operation == "practice.command":
        metronome_frame.acknowledge_reserved_count_in(Time.get_ticks_msec())
    succeeded.emit(decision,opened,code,body,int(completed["started_ms"]))
    if operation == "practice.command":
        _pending_stream_renderer = null
    _flush_transport_action()
    refresh_requested.emit()
    var deferred_library: Dictionary = state.take_library()
    if not str(deferred_library["piece"]).is_empty():
        library_requested.emit(str(deferred_library["piece"]),bool(deferred_library["resume_saved"]))
