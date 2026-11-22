extends RefCounted
## Single owner of accepted backend state and the poll/control ordering gate.
## Polls submitted before an acknowledged command cannot overwrite the
## newer transport, even after the command's pending state has cleared.
## Presentation is published only after the source picker permits adoption.
signal published(state: Dictionary)
var current: Dictionary = {}
var tick_ms := 0
var pending := false
var request_started_ms := 0
var _last_contract_error := ""
const Reply := preload("res://inprocess_request.gd")
const StateContract := preload("res://state_contract.gd")
var _commands
var _practice
var _presentation
var _presenter
var _statistics
var _logger
var _navigation
var _input
var _lessons

func configure(commands, practice, presentation, presenter, statistics,
        logger, navigation, input_session, lessons) -> void:
    _commands = commands
    _practice = practice
    _presentation = presentation
    _presenter = presenter
    _statistics = statistics
    _logger = logger
    _navigation = navigation
    _input = input_session
    _lessons = lessons

func receive(code: int, body: PackedByteArray, sample_started_ms: int = -1) -> void:
    var accepted: Dictionary = accept(code,body,sample_started_ms,
        _commands.state.started_ms,_commands.last_published_control_started_ms)
    if accepted.has("error_code"):
        _practice.present_message(Reply.failure_message(code,body))
        return
    if accepted.has("contract_error"):
        _reject_contract(str(accepted["contract_error"]))
        return
    if not accepted.has("state"):
        # Intentionally discarded stale polls have no payload. They must
        # not overwrite the newer acknowledged command's accepted state.
        return
    var parsed: Dictionary = accepted["state"]
    var violations: Array[String] = StateContract.problems(parsed)
    if not violations.is_empty():
        # The previously accepted source remains untouched. Unknown or
        # incomplete backend snapshots never reach presentation, physical
        # admission, input policy or the published controls.
        _logger.check_contract(parsed)
        _reject_contract("; ".join(violations))
        return
    _last_contract_error = ""
    var received_ms: int = int(accepted["received_ms"])
    _statistics.update_context(str(parsed.get("piece_fingerprint","")))
    var assets = _presentation.score_session
    _logger.record_transition(parsed,received_ms,request_started_ms,
        assets.is_ready(),assets.layout_pending,
        _presentation.frame_diagnostics)
    if _practice.is_source_picker_open():
        _input.suppress_midi_start(int(parsed.get("midi_input_count",0)))
        return
    # Only a published snapshot can drive commands and presentation.
    # Both poll and acknowledged-control responses pass this same gate.
    publish(parsed,int(accepted["tick_ms"]))
    published.emit(parsed)
    _commands.last_state = parsed
    _navigation.update_frame_rate(parsed)
    # The accepted-state boundary, not a render pass, owns the source-bound
    # lesson-overview request lifecycle.
    _lessons.update_context(parsed,received_ms)
    _presentation.accept(parsed,tick_ms,received_ms)
    _presenter.present(parsed,_navigation.current_screen,_commands.state.pending,
        assets.is_ready(),_commands.fingering_save_error,
        _presentation.demo_player != null and bool(_presentation.demo_player.get("audio_error")),
        _presentation.smoke)
    # Input policy consumes the accepted source snapshot AFTER presentation,
    # never from inside PracticeScreen.render or a stale pre-command poll.
    _input.observe_midi_state(parsed,sample_started_ms < 0,
        _navigation.current_screen,_commands.state.pending,assets.is_ready())
    _presentation.refresh_status()
    _logger.record(parsed,received_ms,_practice.stage.renderer,
        _practice.stage.keyboard.visible,_presentation.guided.world,
        _presentation.score_flow.hold_world)

func _reject_contract(detail: String) -> void:
    if detail != _last_contract_error:
        _last_contract_error = detail
        push_error("STATE_CONTRACT_REJECTED: " + detail)
    # Malformed replies must disable UI actions just as malformed objects do.
    # An accepted source and its physical notation remain untouched.
    _practice.present_busy(true)
    _practice.present_message(
        "Invalid practice state; waiting for an authoritative update",true)


func begin_request(now_ms: int) -> void:
    if pending:
        push_error("STATE_INBOX: duplicate outstanding state request")
        return
    pending = true
    request_started_ms = now_ms

func accept(code: int, body: PackedByteArray, sample_started_ms: int,
        command_started_ms: int, published_command_started_ms: int) -> Dictionary:
    if sample_started_ms < 0:
        pending = false
        if (command_started_ms > 0 and
                request_started_ms <= command_started_ms) or (
                published_command_started_ms >= 0 and
                request_started_ms <= published_command_started_ms):
            # An old READY/pause poll cannot reintroduce obsolete ink or
            # count-in after a newer admitted command.
            return {}
    if code != 0:
        return {"error_code":code}
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8()) \
        if not body.is_empty() else null
    if not parsed is Dictionary:
        return {"contract_error":"Backend snapshot is not a JSON object"}
    var received_ms: int = Time.get_ticks_msec()
    var started_ms: int = request_started_ms \
        if sample_started_ms < 0 else sample_started_ms
    return {"state":parsed,"received_ms":received_ms,
        "tick_ms":int((started_ms+received_ms)/2.0)}

func publish(state: Dictionary, sample_tick_ms: int) -> void:
    current = state
    tick_ms = sample_tick_ms
