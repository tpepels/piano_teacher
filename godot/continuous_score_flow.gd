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

func sample(at_ms: int, selected_bpm: float = NAN) -> float:
    if not initialized:
        initialized = true
        last_ms = at_ms
    elif at_ms > last_ms:
        beat += float(at_ms-last_ms) * bpm / 60000.0
        last_ms = at_ms
    # Apply a tempo change only AFTER integrating the elapsed time. Never
    # re-anchor the score when its target BPM changes or the backend pauses.
    if is_finite(selected_bpm) and selected_bpm > 0.0:
        bpm = clampf(selected_bpm,1.0,400.0)
    return beat

func project(at_ms: int) -> float:
    return beat + float(maxi(0,at_ms-last_ms)) * bpm / 60000.0 if initialized else 0.0

func reset() -> void:
    # Called only when the application closes or an explicit test sets up a
    # new process, never by lesson changes or Play/Pause/Retry actions.
    initialized = false
    beat = 0.0
    last_ms = -1
