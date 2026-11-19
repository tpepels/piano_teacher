extends RefCounted
## Single owner of accepted backend state and the poll/control ordering gate.
## Polls submitted before an acknowledged command cannot overwrite the
## newer transport, even after the command's pending state has cleared.
## Presentation is published only after the source picker permits adoption.
var current: Dictionary = {}
var tick_ms := 0
var pending := false
var request_started_ms := 0

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
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())         if not body.is_empty() else null
    if not parsed is Dictionary:
        return {}
    var received_ms: int = Time.get_ticks_msec()
    var started_ms: int = request_started_ms         if sample_started_ms < 0 else sample_started_ms
    return {"state":parsed,"received_ms":received_ms,
        "tick_ms":int((started_ms+received_ms)/2.0)}

func publish(state: Dictionary, sample_tick_ms: int) -> void:
    current = state
    tick_ms = sample_tick_ms
