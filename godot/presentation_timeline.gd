extends RefCounted
const TempoTimeline := preload("res://tempo_timeline.gd")
## Canonical, versioned world-position timeline. Every rate change is an
## immutable monotonic epoch. Projection is a pure function of this ledger
## and a timestamp: it never repays historical tempo errors or moves ink.
##
## Future epochs are replaceable only while their start is strictly after
## the sampled/painted frontier. Already exposed history stays immutable.
var version := 0
var epochs: Array[Dictionary] = []
var last_ms := -1
var last_world := 0.0
var hold_world := INF
var active_segment := ""

func reset() -> void:
    epochs.clear()
    last_ms = -1
    last_world = 0.0
    hold_world = INF
    active_segment = ""
    version += 1

func initialized() -> bool:
    return not epochs.is_empty()

func current_rate() -> float:
    if epochs.is_empty():
        return 40.0
    return _rate_at(float(last_ms))

func initialize(at_ms: int, bpm: float = 40.0) -> void:
    if not epochs.is_empty():
        return
    if not is_finite(bpm) or bpm <= 0.0:
        return
    epochs.append({"at_ms":float(at_ms),"world":0.0,
        "bpm":clampf(bpm,1.0,400.0),"segment":"initial"})
    last_ms = at_ms
    version += 1

func _raw(at_ms: float) -> float:
    if epochs.is_empty():
        return 0.0
    var selected: Dictionary = epochs[0]
    for epoch in epochs:
        if float(epoch["at_ms"]) > at_ms:
            break
        selected = epoch
    return float(selected["world"]) + (at_ms-float(selected["at_ms"])) * \
        float(selected["bpm"])/60000.0

func project(at_ms: int) -> float:
    if epochs.is_empty():
        return 0.0
    var future := maxf(float(last_ms),float(at_ms))
    var value: float = _raw(future)
    if is_finite(hold_world):
        value = minf(value,hold_world)
    return maxf(last_world,value)

func sample(at_ms: int) -> float:
    if epochs.is_empty():
        initialize(at_ms)
    if at_ms >= last_ms:
        last_world = project(at_ms)
        last_ms = at_ms
    return last_world

func _rebase_future() -> void:
    for i in range(1,epochs.size()):
        var before: Dictionary = epochs[i-1]
        var after: Dictionary = epochs[i]
        if bool(after.get("locked_origin",false)):
            continue
        after["world"] = float(before["world"]) + \
            (float(after["at_ms"])-float(before["at_ms"])) * \
            float(before["bpm"])/60000.0

func _install(at_ms: float, next_bpm: float, segment: String) -> void:
    if not is_finite(at_ms) or not is_finite(next_bpm) or next_bpm <= 0.0:
        return
    var stamped := maxf(float(last_ms),at_ms)
    var first := 0
    while first < epochs.size() and float(epochs[first]["at_ms"]) < stamped:
        first += 1
    if first < epochs.size() and absf(float(epochs[first]["at_ms"])-stamped) < .001:
        epochs[first] = {"at_ms":stamped,"world":0.0,
            "bpm":clampf(next_bpm,1.0,400.0),"segment":segment}
    else:
        epochs.insert(first,{"at_ms":stamped,"world":0.0,
            "bpm":clampf(next_bpm,1.0,400.0),"segment":segment})
    if first == 0:
        epochs[0]["world"] = last_world
    _rebase_future()
    version += 1

func set_rate(at_ms: int, bpm: float) -> void:
    if epochs.is_empty():
        initialize(at_ms,bpm)
        return
    sample(at_ms)
    var active_rate := _rate_at(float(at_ms))
    if absf(active_rate-bpm) < .0001:
        return
    # A deliberate lesson/Free rate change supersedes all unexposed
    # speculative future rate epochs, never an already-painted epoch.
    _trim_after(float(at_ms))
    _install(float(at_ms),bpm,"lesson")

func _rate_at(at_ms: float) -> float:
    var rate := float(epochs[0]["bpm"]) if not epochs.is_empty() else 40.0
    for epoch in epochs:
        if float(epoch["at_ms"]) > at_ms:
            break
        rate = float(epoch["bpm"])
    return rate

func _trim_after(frontier: float) -> void:
    while not epochs.is_empty() and float(epochs[-1]["at_ms"]) > frontier:
        epochs.pop_back()

func physical_travel_ms_to(target_world: float, sampled_ms: int,
        source_beat: float, nominal_bpm: float,
        authored_segments: Array) -> float:
    # Pure inverse of the SAME displayed epochs and authored tempo map.
    # No speculative clock, trial timeline objects or binary-search frame
    # rounding. Source time and world position are distinct observations.
    if (epochs.is_empty() or not is_finite(target_world)
            or not is_finite(nominal_bpm) or nominal_bpm <= 0.0):
        return NAN
    var position: float = project(sampled_ms)
    if not is_finite(position):
        return NAN
    if target_world <= position:
        return 0.0
    if not is_finite(hold_world) and not active_segment.is_empty():
        # An already committed source has known, possibly changing tempo
        # epochs. Use those timestamps directly, never a possibly stale
        # source_beat from the last backend snapshot.
        var elapsed_ms := 0.0
        var cursor_ms := float(sampled_ms)
        var cursor_world := position
        var rate: float = _rate_at(cursor_ms)
        for epoch in epochs:
            var next_ms: float = float(epoch["at_ms"])
            if next_ms <= cursor_ms:
                continue
            var ahead: float = (next_ms-cursor_ms)*rate/60000.0
            if target_world <= cursor_world+ahead:
                return elapsed_ms+(target_world-cursor_world)*60000.0/rate
            cursor_world += ahead
            elapsed_ms += next_ms-cursor_ms
            cursor_ms = next_ms
            rate = float(epoch["bpm"])
        return elapsed_ms+(target_world-cursor_world)*60000.0/rate
    # No committed, unheld source determines this future. A frozen Pause,
    # Free target or newly loaded stage requires a *hypothetical* trajectory
    # from the held world and the current authenticated tempo map.
    if not is_finite(source_beat):
        return NAN
    var target_beat: float = source_beat+target_world-position
    if not is_finite(target_beat):
        return NAN
    var first_seconds: float = TempoTimeline.seconds_at_beat(
        source_beat,nominal_bpm,authored_segments)
    var last_seconds: float = TempoTimeline.seconds_at_beat(
        target_beat,nominal_bpm,authored_segments)
    var elapsed: float = (last_seconds-first_seconds)*1000.0
    return maxf(0.0,elapsed) if is_finite(elapsed) else NAN


func forecast_authored(at_ms: int, sampled_ms: int,
        source_beat: float, nominal_bpm: float,
        authored_segments: Array) -> float:
    # Physical admission may ask about a candidate BEFORE it has acquired
    # an authorized segment. Evaluate a hypothetical immutable copy of the
    # SAME epoch projector, without publishing rates or touching live ink.
    # On authorization these provisional epochs are committed exactly once.
    var origin: float = project(sampled_ms)
    if at_ms <= sampled_ms:
        return origin
    if not is_finite(source_beat) or not is_finite(nominal_bpm) or nominal_bpm <= 0.0:
        return NAN
    # A constant-tempo forecast must also be hypothetical. Calling
    # project() would obey a painted Pause/Free hold and return no future.
    var candidate = get_script().new()
    var starting_bpm: float = TempoTimeline.bpm_at_beat(
        source_beat,nominal_bpm,authored_segments)
    candidate.initialize(sampled_ms,starting_bpm)
    candidate.epochs[0]["world"] = origin
    candidate.last_world = origin
    var origin_seconds: float = TempoTimeline.seconds_at_beat(
        source_beat,nominal_bpm,authored_segments)
    for part in authored_segments:
        var start_beat: float = float(part.get("start_beat",0.0))
        if start_beat <= source_beat + .000001:
            continue
        var offset: float = TempoTimeline.seconds_at_beat(
            start_beat,nominal_bpm,authored_segments)-origin_seconds
        if offset > 0.0 and is_finite(offset):
            candidate._install(float(sampled_ms)+offset*1000.0,
                float(part.get("bpm",nominal_bpm)),"forecast")
    return candidate.project(at_ms)


func set_hold(world: float, at_ms: int) -> void:
    sample(at_ms)
    var next_hold: float = world if is_finite(world) else INF
    if hold_world == next_hold:
        return
    var observed := last_world
    # The backend can authorize a future Resume downbeat while Pause is
    # still painted. Releasing that hold must not erase its deadline/rate
    # epochs; an unconfirmed speculative segment is never preserved.
    var preserve_authorized: bool = is_finite(hold_world) and \
        not is_finite(next_hold) and not active_segment.is_empty()
    hold_world = next_hold
    var authorized_future: Array[Dictionary] = []
    if preserve_authorized:
        for epoch in epochs:
            if float(epoch["at_ms"]) > float(at_ms) and \
                    str(epoch.get("segment","")) == active_segment:
                authorized_future.append(epoch.duplicate(true))
    _trim_after(float(at_ms))
    # Resume begins from the actual frozen world. Future epochs retain
    # their authorized wall-clock timestamps and are spatially rebased.
    _install(float(at_ms),_rate_at(float(at_ms)),"guided")
    epochs[-1]["world"] = observed
    epochs[-1]["locked_origin"] = true
    if not authorized_future.is_empty():
        for epoch in authorized_future:
            epochs.append(epoch)
        _rebase_future()
    version += 1
