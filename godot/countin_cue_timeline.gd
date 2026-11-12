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
    var tick := floori(beat + .00001)
    if token == _token and tick < 0:
        # A count-in beat that was never observed (Pause landed just after its
        # boundary, before any frame spoke it) is still owed to Resume: only
        # beats actually observed count as heard, never the frozen one.
        return
    _token = token
    _last_tick = tick

func adopt(token: String) -> void:
    # The same countdown continues under another epoch token (a reserved
    # Play count-in handed to the engine's running transport): beats already
    # spoken stay spoken.
    if not token.is_empty():
        _token = token

func continues(token: String, beat: float) -> bool:
    # True when beat moves forward within the held epoch: a reused Resume
    # picks up the same countdown instead of starting a second one.
    return not token.is_empty() and token == _token and is_finite(beat) and \
        floori(beat + .00001) >= _last_tick

# Explicit "count one whole bar of the meter" (Retry preparation, whose
# engine count_in_beats is not published). 0 is a real count-in of zero.
const WHOLE_BAR := -1.0
# A Resume that CONTINUES a paused countdown speaks a cue only within this
# fraction of its beat (R1 M4). Every other count-in is driven from a
# deadline Godot knows in advance, so its cues are on their beats anyway.
const LATE_CUE_BEATS := 0.2

# Owner decision M3 (2026-11-11): compound meters count their main pulse,
# the dotted quarter, evenly across the one count-in bar: 6/8 "Ichi Ni",
# 9/8 "Ichi Ni San", 12/8 "Ichi Ni San Shi". Beats are quarter notes.
static func pulse_beats(meter: Variant) -> float:
    if meter is Array and meter.size() >= 2 and int(meter[1]) == 8 and \
            int(meter[0]) in [6,9,12]:
        return 1.5
    return 1.0

# A count-in reading (beat, bar, count_in) in pulse units: only the
# count-in before beat 0 is re-expressed; the take's own beats stay beats.
static func in_pulses(beat: float, bar_beats: float, count_in_beats: float,
        pulse: float) -> Array:
    if pulse == 1.0 or not is_finite(beat) or beat >= 0.0:
        return [beat,maxi(1,roundi(bar_beats)),count_in_beats]
    return [beat/pulse,maxi(1,roundi(bar_beats/pulse)),
        count_in_beats if count_in_beats == WHOLE_BAR else count_in_beats/pulse]

static func counting(beat: float, beats_per_bar: int,
        count_in_beats: float = WHOLE_BAR) -> bool:
    # Owner decision 2026-11-08: one count-in only, in the bar before the
    # start. A longer presentation lead before it is silent. count_in_beats
    # is the engine's count-in (0 for a loop continuation: nothing counts);
    # WHOLE_BAR counts one bar of beats_per_bar.
    var window: float = float(maxi(1,beats_per_bar)) \
        if count_in_beats == WHOLE_BAR else maxf(0.0,count_in_beats)
    return beat < 0.0 and beat >= -window-.00001

func observe(token: String, beat: float, beats_per_bar: int,
        count_in_beats: float = WHOLE_BAR, drop_late: bool = false) -> Dictionary:
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
    if drop_late and tick < 0 and beat - float(tick) > LATE_CUE_BEATS:
        # A continued Resume countdown first observing a beat well after it
        # began (R1 M4: "San" at -1.34 then "Shi" 0.53 s later) consumes it
        # silently: every spoken cue falls on its beat.
        return {}
    var meter: int = maxi(1,beats_per_bar)
    return {"tick":tick,"beat":beat,"count_in":tick < 0,
        "syllable":posmod(tick,meter)+1,
        "accent":posmod(tick,meter) == 0,
        "token":token}
