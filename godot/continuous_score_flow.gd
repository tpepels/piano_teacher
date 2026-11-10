extends RefCounted
## One endless, forward-only presentation axis for the Practice canvas.
##
## Backend transport, MIDI assessment and Listen scheduling do not read this.
## Audio and notation retain source identities; this axis only places already
## engraved copies on an infinite moving staff. All screens and transitions
## share it: Ready, Play, Pause, Retry and lesson handoff cannot rewind it.
var beat := 0.0
var last_ms := -1
var bpm := 40.0
var initialized := false
# Beats still owed after a retroactive switch to a slower rate.
var _slow_debt := 0.0

func sample(at_ms: int, selected_bpm: float = NAN) -> float:
    if not initialized:
        initialized = true
        last_ms = at_ms
    elif at_ms > last_ms:
        var step: float = float(at_ms-last_ms) * bpm / 60000.0
        # Repay at most half of each step: the axis slows, never stops.
        var paid: float = minf(_slow_debt,step*0.5)
        _slow_debt -= paid
        beat += step-paid
        last_ms = at_ms
    # Apply a tempo change only AFTER integrating the elapsed time. Never
    # re-anchor the score when its target BPM changes or the backend pauses.
    if is_finite(selected_bpm) and selected_bpm > 0.0:
        bpm = clampf(selected_bpm,1.0,400.0)
    return beat

func switch_rate_at(at_ms: float, next_bpm: float) -> void:
    # The engine changed tempo exactly at at_ms (a new take's graded run_at,
    # e.g. the automatic tempo step settled at a repeat's deadline), but this
    # frame clock only sees it with the next snapshot. Account the elapsed
    # time since at_ms at the new rate so the world keeps matching the graded
    # transport. Never seek back: a slower rate is paid by moving slower.
    if not initialized or not is_finite(at_ms) or not is_finite(next_bpm) or \
            next_bpm <= 0.0 or at_ms >= float(last_ms):
        return
    var correction: float = (float(last_ms)-at_ms)*(next_bpm-bpm)/60000.0
    if correction >= 0.0:
        beat += correction
    else:
        _slow_debt += -correction
    bpm = clampf(next_bpm,1.0,400.0)

func project(at_ms: int) -> float:
    if not initialized:
        return 0.0
    var step: float = float(maxi(0,at_ms-last_ms)) * bpm / 60000.0
    return beat + step - minf(_slow_debt,step*0.5)

func project_authored_future(at_ms: int, sampled_ms: int,
        source_beat: float, nominal_bpm: float,
        authored_segments: Array) -> float:
    # At the future engine-authored deadline, predict this SAME forward
    # world axis through original source tempo changes. A constant-BPM
    # projection incorrectly places copies whenever a tempo-map boundary
    # lies between the sampled state and the retry deadline.
    # Only snapshots from a currently playing source supply tempo segments.
    # Feedback/paused preparation continues at the selected rest BPM.
    var local_world: float = project(sampled_ms)
    var delta_seconds: float = maxf(0.0,float(at_ms-sampled_ms)/1000.0)
    if delta_seconds <= 0.0 or authored_segments.is_empty() or \
            not is_finite(source_beat) or not is_finite(nominal_bpm) or \
            nominal_bpm <= 0.0:
        return local_world + delta_seconds*bpm/60.0
    var timing = preload("res://tempo_timeline.gd")
    var before: float = timing.seconds_at_beat(
        source_beat,nominal_bpm,authored_segments)
    var after: float = timing.beat_at_seconds(
        before+delta_seconds,nominal_bpm,authored_segments)
    return local_world+maxf(0.0,after-source_beat)


func reset() -> void:
    # Called only when the application closes or an explicit test sets up a
    # new process, never by lesson changes or Play/Pause/Retry actions.
    initialized = false
    _slow_debt = 0.0
    beat = 0.0
    last_ms = -1
