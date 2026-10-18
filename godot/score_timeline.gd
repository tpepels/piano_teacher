extends RefCounted
# Phase B: one semantic quarter-beat axis, independent of Verovio geometry.
# The backend transport/VisualTransportClock supplies clock_beat. This class
# never owns a timer, tempo, renderer, MIDI grading, or interpolation curve.
const SCHEMA := "piano-teacher-score-model-v1"
const DEFAULT_PIXELS_PER_BEAT := 96.0
const MIN_PIXELS_PER_BEAT := 24.0
const MAX_PIXELS_PER_BEAT := 480.0

var pixels_per_beat := DEFAULT_PIXELS_PER_BEAT
var model: Dictionary = {}
var notes: Array = []
var measures: Array = []
var duration_beats := 0.0
var revision := -1
var last_error := ""

func set_density(requested: float) -> bool:
    if not is_finite(requested) or requested < MIN_PIXELS_PER_BEAT \
            or requested > MAX_PIXELS_PER_BEAT:
        last_error = "Pixels per beat must be between 24 and 480"
        return false
    pixels_per_beat = requested
    last_error = ""
    return true

func load_model(candidate: Dictionary) -> bool:
    if str(candidate.get("schema", "")) != SCHEMA \
            or str(candidate.get("beat_unit", "")) != "quarter":
        last_error = "Unknown semantic score schema or beat unit"
        return false
    var length: float = float(candidate.get("duration_beats", 0.0))
    var new_notes: Array = candidate.get("notes", [])
    var new_measures: Array = candidate.get("measures", [])
    if not is_finite(length) or length <= 0.0 or new_measures.is_empty():
        last_error = "Missing exercise or invalid duration"
        return false
    var seen: Dictionary = {}
    for note in new_notes:
        if not note is Dictionary:
            last_error = "Invalid semantic note"
            return false
        var ident: String = str(note.get("id", ""))
        var onset: float = float(note.get("onset_beats", -INF))
        var duration: float = float(note.get("duration_beats", -INF))
        if ident.is_empty() or seen.has(ident) or not is_finite(onset) \
                or not is_finite(duration) or onset < 0.0 \
                or duration <= 0.0 or onset + duration > length + .0001:
            last_error = "Invalid source note ID, onset or duration"
            return false
        seen[ident] = true
    var previous := 0.0
    for measure in new_measures:
        if not measure is Dictionary:
            last_error = "Invalid measure"
            return false
        var first: float = float(measure.get("start_beat", -INF))
        var last: float = float(measure.get("end_beat", -INF))
        if not is_finite(first) or not is_finite(last) \
                or absf(first - previous) > .0001 or last <= first:
            last_error = "Measure boundaries are not contiguous"
            return false
        previous = last
    if absf(previous - length) > .0001:
        last_error = "Measure grid does not match exercise duration"
        return false
    model = candidate.duplicate(true)
    notes = model["notes"]
    measures = model["measures"]
    duration_beats = length
    revision = int(candidate.get("revision", -1))
    last_error = ""
    return true

func has_score() -> bool:
    return not model.is_empty()

# Positions are always in the SAME coordinate system, even at negative beats.
func x_at_beat(beat: float) -> float:
    return beat * pixels_per_beat

# Backend state.clock_beat is relative to start/seek, including negative
# count-in. play_from_beat is an offset from the beginning of this exercise.
func musical_beat(clock_beat: float, play_from_beat: float = 0.0) -> float:
    return play_from_beat + clock_beat

func camera_x(clock_beat: float, play_from_beat: float = 0.0) -> float:
    return x_at_beat(musical_beat(clock_beat, play_from_beat))

# playhead_x is fixed in pixels relative to the score viewport; no per-note
# camera corrections or special zero-beat tween are ever allowed.
func screen_x(event_beat: float, clock_beat: float, playhead_x: float,
        play_from_beat: float = 0.0) -> float:
    return playhead_x + x_at_beat(event_beat) - camera_x(
        clock_beat, play_from_beat)

func pixels_per_second(bpm: float) -> float:
    return pixels_per_beat * bpm / 60.0

func count_in_start(play_from_beat: float, count_in_beats: float) -> float:
    return play_from_beat - count_in_beats

func set_density_from_env() -> bool:
    var raw: String = OS.get_environment("PIANO_TEACHER_PIXELS_PER_BEAT")
    if raw.is_empty():
        return true
    if not raw.is_valid_float():
        last_error = "PIANO_TEACHER_PIXELS_PER_BEAT is not numeric"
        return false
    return set_density(raw.to_float())
