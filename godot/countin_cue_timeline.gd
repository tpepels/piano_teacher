extends RefCounted
## Sole preparation-cue deduplicator, driven by an authoritative sampled
## musical beat. No timers, app state access, or audio device access.
## Normal Play, Resume, and automatic Retry all use this same epoch protocol.
var _token := ""
var _last_tick := -2147483648

func reset() -> void:
    _token = ""
    _last_tick = -2147483648

func hold(token: String, beat: float) -> void:
    # Pause suppresses a replay of a beat already heard; the visual clock
    # continues independently while grading remains frozen.
    if token.is_empty() or not is_finite(beat):
        reset()
        return
    _token = token
    _last_tick = floori(beat + .00001)

func observe(token: String, beat: float, beats_per_bar: int) -> Dictionary:
    if token.is_empty() or not is_finite(beat) or beats_per_bar <= 0:
        return {}
    var tick := floori(beat + .00001)
    if token != _token:
        _token = token
        _last_tick = -2147483648
    if tick <= _last_tick:
        # Repeated state polls, a stale delayed snapshot, or an uneven
        # render frame must never speak the same beat twice.
        return {}
    _last_tick = tick
    var meter: int = maxi(1,beats_per_bar)
    return {"tick":tick,"beat":beat,"count_in":tick < 0,
        "syllable":posmod(tick,meter)+1,
        "accent":posmod(tick,meter) == 0,
        "token":token}
