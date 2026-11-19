extends RefCounted
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
    return float(epochs[-1]["bpm"])

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

func authorize_source_epoch(deadline_ms: float, opening: float,
        nominal_bpm: float, authored_segments: Array,
        segment_id: String) -> void:
    if (segment_id.is_empty() or not is_finite(deadline_ms)
            or not is_finite(nominal_bpm) or nominal_bpm <= 0.0):
        return
    if epochs.is_empty():
        initialize(Time.get_ticks_msec(),nominal_bpm)
    if segment_id == active_segment:
        return
    var frontier: float = float(last_ms)
    if deadline_ms < frontier:
        # A delayed worker response cannot retroactively move a note that
        # has already passed the playhead. Preserve painted position and
        # apply its remaining tempo map at the current forward frontier.
        deadline_ms = frontier
    _trim_after(frontier)
    active_segment = segment_id
    var initial_rate: float = TempoTimeline.bpm_at_beat(
        opening,nominal_bpm,authored_segments)
    _install(deadline_ms,initial_rate,segment_id)
    var from_seconds: float = TempoTimeline.seconds_at_beat(
        opening,nominal_bpm,authored_segments)
    for entry in authored_segments:
        var offset: float = float(entry.get("start_beat",0.0))
        if offset <= opening + .000001:
            continue
        var mapped: float = TempoTimeline.seconds_at_beat(
            offset,nominal_bpm,authored_segments)-from_seconds
        if mapped > 0.0 and is_finite(mapped):
            _install(deadline_ms+mapped*1000.0,
                float(entry.get("bpm",nominal_bpm)),segment_id)

func set_hold(world: float, at_ms: int) -> void:
    sample(at_ms)
    var next_hold: float = world if is_finite(world) else INF
    if hold_world == next_hold:
        return
    var observed := last_world
    hold_world = next_hold
    _trim_after(float(at_ms))
    # New Free target or release resumes forward from the actual held
    # position at this instant, without catching up via a sudden jump.
    _install(float(at_ms),_rate_at(float(at_ms)),"guided")
    epochs[-1]["world"] = observed
    version += 1
