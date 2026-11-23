extends RefCounted
const Spacing := preload("res://notation/shared/spacing_policy.gd")
const TempoTimeline := preload("res://tempo_timeline.gd")
# Phase B: one semantic quarter-beat axis, independent of Verovio geometry.
# The backend transport/VisualTransportClock supplies clock_beat. This class
# never owns a timer, tempo, renderer, MIDI grading, or interpolation curve.
const SCHEMA := "piano-teacher-score-model-v1"
const DEFAULT_PIXELS_PER_BEAT := Spacing.DEFAULT_PIXELS_PER_BEAT
const MIN_PIXELS_PER_BEAT := 24.0
const MAX_PIXELS_PER_BEAT := 480.0
# Automatic source fitting is separate from the user preference range.
# Imported tuplets can contain genuine .00625-quarter-beat note segments.
const MAX_SCORE_PIXELS_PER_BEAT := 8192.0

var pixels_per_beat := DEFAULT_PIXELS_PER_BEAT
var model: Dictionary = {}
var notes: Array = []
var measures: Array = []
var duration_beats := 0.0
var sounding_duration_beats := 0.0
var display_measures: Array = []
var display_start_beat := 0.0
var display_end_beat := 0.0
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


func set_score_density(requested: float) -> bool:
    if not is_finite(requested) or requested < MIN_PIXELS_PER_BEAT \
            or requested > MAX_SCORE_PIXELS_PER_BEAT:
        last_error = "Automatic score density must be between 24 and 8192"
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
    var extent: Dictionary = candidate.get("display_extent",{})
    var display_first: float = float(extent.get("start_beat",0.0))
    var sounding: float = float(candidate.get("sounding_duration_beats",length))
    var display_last: float = float(extent.get("end_beat",maxf(length,sounding)))
    if not is_finite(display_first) or not is_finite(display_last) or \
            not is_finite(sounding) or display_first > 0.0 or display_last < sounding or sounding < length:
        last_error = "Invalid display or sounding extent"
        return false
    var seen: Dictionary = {}
    for note in candidate.get("display_notes",new_notes):
        if not note is Dictionary:
            last_error = "Invalid semantic note"
            return false
        var ident: String = str(note.get("id", ""))
        var onset: float = float(note.get("onset_beats", -INF))
        var duration: float = float(note.get("duration_beats", -INF))
        if ident.is_empty() or seen.has(ident) or not is_finite(onset) \
                or not is_finite(duration) or onset+duration <= display_first \
                or duration <= 0.0 or onset >= display_last + .0001:
            last_error = "Invalid source note ID, onset or duration"
            return false
        seen[ident] = note
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
    var performance_ids: Dictionary = {}
    for note in new_notes:
        if not note is Dictionary or not seen.has(str(note.get("id",""))) or \
                note != seen[str(note.get("id",""))]:
            last_error = "Performance note differs from its authentic display source"
            return false
        performance_ids[str(note["id"])] = note
    for active_id in candidate.get("active_note_ids",[]):
        var active_note: Dictionary = performance_ids.get(str(active_id),{})
        if active_note.is_empty() or float(active_note["onset_beats"]) < 0.0 or \
                float(active_note["onset_beats"]) >= length or \
                float(active_note["onset_beats"])+float(active_note["duration_beats"]) > sounding+.0001:
            last_error = "Active source identity is missing from display envelope"
            return false
    var display_grid: Array = candidate.get("display_measures",new_measures)
    var display_previous: float = display_first
    for measure in display_grid:
        if not measure is Dictionary or absf(float(measure.get("start_beat",INF))-display_previous) > .0001:
            last_error = "Display measure grid is not contiguous"
            return false
        display_previous = float(measure.get("end_beat",-INF))
    if display_previous < length-.0001 or display_previous > display_last+.0001:
        last_error = "Display grid lost the authored window"
        return false
    model = candidate.duplicate(true)
    notes = model["notes"]
    measures = model["measures"]
    duration_beats = length
    sounding_duration_beats = sounding
    display_measures = model.get("display_measures",measures)
    display_start_beat = display_first
    display_end_beat = display_last
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

# One canonical, linear beat-to-screen projection for score ink and stage
# markers. The camera and onsets use the same quarter-beat coordinates; tempo
# is only the derivative of world_beat, not a position distortion.
static func project_world_beat(beat: float, world_beat: float,
        playhead_x: float, density: float) -> float:
    return playhead_x + (beat-world_beat)*density

# playhead_x is fixed in pixels relative to the score viewport; no per-note
# camera corrections or special zero-beat tween are ever allowed.
func screen_x(event_beat: float, clock_beat: float, playhead_x: float,
        play_from_beat: float = 0.0) -> float:
    return project_world_beat(event_beat,
        musical_beat(clock_beat,play_from_beat),playhead_x,pixels_per_beat)

func pixels_per_second(bpm: float) -> float:
    return pixels_per_beat * TempoTimeline.beats_from_seconds(1.0,bpm)

func set_density_from_env() -> bool:
    var raw: String = OS.get_environment("PIANO_TEACHER_PIXELS_PER_BEAT")
    if raw.is_empty():
        return true
    if not raw.is_valid_float():
        last_error = "PIANO_TEACHER_PIXELS_PER_BEAT is not numeric"
        return false
    return set_density(raw.to_float())
