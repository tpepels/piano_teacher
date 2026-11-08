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

static func counting(beat: float, beats_per_bar: int,
        count_in_beats: float = 0.0) -> bool:
    # Owner decision 2026-11-08: one count-in only, in the bar before the
    # start. A longer presentation lead before it is silent. count_in_beats
    # is the engine's (capped) count-in; 0 means one whole bar.
    var window: float = count_in_beats if count_in_beats > 0.0 else \
        float(maxi(1,beats_per_bar))
    return beat < 0.0 and beat >= -window-.00001

func observe(token: String, beat: float, beats_per_bar: int,
        count_in_beats: float = 0.0) -> Dictionary:
    if token.is_empty() or not is_finite(beat) or beats_per_bar <= 0:
        return {}
    var tick := floori(beat + .00001)
    if token != _token:
        _token = token
        _last_tick = -2147483648
    if beat < 0.0 and not counting(beat,beats_per_bar,count_in_beats):
        # Silent lead before the count-in bar: no syllable, no click, and
        # the tick is not consumed.
        return {}
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
