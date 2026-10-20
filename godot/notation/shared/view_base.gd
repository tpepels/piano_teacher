extends Control
# Phase B diagnostic display. NOT a notation renderer: circles/bars visualize
# source note attacks and durations while validating the new time axis.
# It runs above the legacy score only when explicitly enabled. Phase C will
# consume the same ScoreTimeline with real notation glyphs.
const Timeline := preload("res://score_timeline.gd")
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
    queue_redraw()

func load_score(candidate: Dictionary) -> bool:
    if not timeline.load_model(candidate):
        notice = timeline.last_error
        queue_redraw()
        return false
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

func present(state: Dictionary, transport_beat: float) -> void:
    var next_clock: float = transport_beat
    var next_from: float = float(state.get("play_from_beat", 0.0))
    var next_count: float = maxf(0.0, float(state.get("count_in_beats", 0.0)))
    var next_hand: String = str(state.get("hand", "both"))
    var next_bpm: float = maxf(1.0, float(state.get("bpm", 60.0)))
    var next_transport: int = int(state.get("transport_id", -1))
    var next_running: bool = bool(state.get("running", false))
    var next_paused: bool = bool(state.get("paused", false))
    if (absf(clock_beat-next_clock) > .00001 or
        absf(play_from_beat-next_from) > .00001 or
        absf(count_in_beats-next_count) > .00001 or
        active_hand != next_hand or absf(bpm-next_bpm) > .001 or
        transport_id != next_transport or running != next_running or
        paused != next_paused):
        clock_beat = next_clock
        play_from_beat = next_from
        count_in_beats = next_count
        active_hand = next_hand
        bpm = next_bpm
        transport_id = next_transport
        running = next_running
        paused = next_paused
        queue_redraw()

