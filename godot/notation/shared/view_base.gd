extends Control
# Shared semantic score state, musical clock projection and density controls.
# The native production view and standalone timeline diagnostic share this
# time axis; their drawing implementations remain separate.
const Timeline := preload("res://notation/shared/timeline.gd")
const BACKGROUND := Color("#192F30")
const GRID := Color("#668982")
const FOREGROUND := Color("#E5F2EA")
const HIGHLIGHT := Color("#84EDD3")
const MUTED := Color("#819F9A")
const LEFT_TONE := Color("#9FB4DC")
const PLAYHEAD_FRACTION := .42

var timeline = Timeline.new()
var clock_beat := 0.0
var play_from_beat := 0.0
var count_in_beats := 0.0
var visual_scroll_beat := 0.0
var score_loop_enabled := false
var practice_timeline: Dictionary = {}
var practice_preparation: Dictionary = {}
var practice_contract_error := ""
var active_hand := "both"
var bpm := 60.0
var transport_id := -1
var running := false
var paused := false
var notice := "Waiting for /score/model"
var visible_onsets := 0

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    set_process(false)

func clear_score() -> void:
    var density: float = timeline.pixels_per_beat
    timeline = Timeline.new()
    timeline.set_density(density)
    notice = "Waiting for /score/model"
    visual_scroll_beat = 0.0
    practice_timeline.clear()
    practice_preparation.clear()
    practice_contract_error = ""
    queue_redraw()

func load_score(candidate: Dictionary) -> bool:
    if not timeline.load_model(candidate):
        notice = timeline.last_error
        queue_redraw()
        return false
    practice_timeline = candidate.get("practice_timeline",{}).duplicate(true)
    practice_preparation.clear()
    practice_contract_error = ""
    notice = ""
    queue_redraw()
    return true

func set_density(value: float) -> bool:
    if not timeline.set_density(value):
        notice = timeline.last_error
        queue_redraw()
        return false
    queue_redraw()
    return true

func set_density_from_env() -> bool:
    if not timeline.set_density_from_env():
        notice = timeline.last_error
        queue_redraw()
        return false
    return true

func _practice_timeline_error() -> String:
    if practice_timeline.get("schema","") != "piano-teacher-practice-timeline-v1" or \
            not practice_timeline.get("gap") is Dictionary:
        return "Missing semantic practice timeline"
    var silence: Dictionary = practice_timeline["gap"]
    var meter: Variant = silence.get("meter")
    if not meter is Array or meter.size()!=2 or float(meter[0])<=0.0 or float(meter[1])<=0.0:
        return "Invalid preparation meter"
    var duration: float = float(silence.get("duration_beats",NAN))
    var stride: float = float(practice_timeline.get("stride_beats",NAN))
    if not is_finite(duration) or not is_finite(stride) or duration<=0.0 or \
            absf(duration-float(meter[0])*4.0/float(meter[1]))>.00001 or \
            absf(float(practice_timeline.get("source_duration_beats",0.0))-timeline.duration_beats)>.00001 or \
            absf(stride-timeline.duration_beats-duration)>.00001 or \
            absf(float(silence.get("start_beat",-INF))-timeline.duration_beats)>.00001 or \
            absf(float(silence.get("end_beat",-INF))-stride)>.00001:
        return "Preparation duration differs from its full measure"
    var events: Variant = silence.get("events")
    if not events is Array or events.size()!=2:
        return "Preparation needs a rest on each piano staff"
    var staves: Dictionary = {}
    for event in events:
        if not event is Dictionary or event.get("kind")!="rest" or event.get("source_id")!=null or \
                event.get("is_attack")!=false or event.get("graded")!=false or event.get("full_measure")!=true or \
                absf(float(event.get("duration_beats",NAN))-duration)>.00001 or \
                event.get("staff") not in ["right","left"] or staves.has(event.get("staff")):
            return "Preparation rest must be ungraded and source-independent"
        staves[event["staff"]] = true
    return ""

func present(state: Dictionary, transport_beat: float, visual_beat: float = NAN) -> void:
    var next_clock: float = transport_beat
    var next_visual: float = visual_beat if is_finite(visual_beat) else transport_beat + float(state.get("play_from_beat", 0.0))
    var next_loop: bool = bool(state.get("score_loop_enabled", false))
    var next_preparation: Dictionary = state["practice_preparation"].duplicate(true) if state.get("practice_preparation") is Dictionary else {}
    var contract_error := ""
    if next_loop:
        contract_error = _practice_timeline_error()
        if contract_error.is_empty() and state.get("practice_timeline",practice_timeline) != practice_timeline:
            contract_error = "Practice timeline differs from the loaded score"
        elif contract_error.is_empty() and absf(float(state.get("visual_gap_beats",practice_timeline["gap"]["duration_beats"]))-float(practice_timeline["gap"]["duration_beats"]))>.00001:
            contract_error = "Practice pause differs from its engraved measure"
    var next_from: float = float(state.get("play_from_beat", 0.0))
    var next_count: float = maxf(0.0, float(state.get("count_in_beats", 0.0)))
    var next_hand: String = str(state.get("hand", "both"))
    var next_bpm: float = maxf(1.0, float(state.get("bpm", 60.0)))
    var next_transport: int = int(state.get("transport_id", -1))
    var next_running: bool = bool(state.get("running", false))
    var next_paused: bool = bool(state.get("paused", false))
    if (absf(clock_beat-next_clock) > .00001 or
        absf(visual_scroll_beat-next_visual) > .00001 or score_loop_enabled != next_loop or
        practice_preparation != next_preparation or practice_contract_error != contract_error or
        absf(play_from_beat-next_from) > .00001 or
        absf(count_in_beats-next_count) > .00001 or
        active_hand != next_hand or absf(bpm-next_bpm) > .001 or
        transport_id != next_transport or running != next_running or
        paused != next_paused):
        clock_beat = next_clock
        visual_scroll_beat = next_visual
        score_loop_enabled = next_loop
        practice_preparation = next_preparation
        practice_contract_error = contract_error
        play_from_beat = next_from
        count_in_beats = next_count
        active_hand = next_hand
        bpm = next_bpm
        transport_id = next_transport
        running = next_running
        paused = next_paused
        queue_redraw()

