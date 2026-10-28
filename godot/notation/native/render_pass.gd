extends RefCounted
## One ephemeral source-copy paint pass. No canvas, view, axis or score is retained.
## Context supplies only the named presentation values below. Histories are read
## by the visibility policy; source/transport mutation and loop orchestration stay
## with the caller. The caller increments visible_symbols/scanned_events while
## visiting source events; beam_layout sets visible_beam_groups.
const Design := preload("res://practice_theme.gd")
const SourceVisibility := preload("res://notation/native/source_visibility.gd")
const PLAYHEAD_FRACTION := .42

var clock: float
var playhead_x: float
var gap: float
var play_from_beat: float
var active_hand: String
var score_loop_enabled: bool
var pass_index: int
var pass_start: float
var preparation_history: Dictionary
var current_preparation: Dictionary
var visual_scroll_beat: float
var drawn_noteheads: Dictionary = {}
var pass_noteheads: Dictionary = {}
var drawn_note_instances: Array = []
var visible_symbols := 0
var scanned_events := 0
var visible_beam_groups := 0

func _init(context: Dictionary = {}) -> void:
    clock = float(context.get("clock",0.0))
    playhead_x = float(context.get("playhead_x",0.0))
    gap = float(context.get("gap",0.0))
    play_from_beat = float(context.get("play_from_beat",0.0))
    active_hand = str(context.get("active_hand","both"))
    score_loop_enabled = bool(context.get("score_loop_enabled",false))
    pass_index = int(context.get("pass_index",0))
    pass_start = float(context.get("pass_start",0.0))
    preparation_history = context.get("preparation_history",{})
    current_preparation = context.get("current_preparation",
        preparation_history.get(pass_start,{}) if score_loop_enabled else {})
    visual_scroll_beat = float(context.get("visual_scroll_beat",0.0))

func screen_x(axis, beat: float) -> float:
    return axis.screen_x(beat,clock,playhead_x,play_from_beat)

func event_visible(event: Dictionary) -> bool:
    return SourceVisibility.event_visible(event,pass_start,score_loop_enabled,preparation_history)

func span_visible(first: Dictionary, last: Dictionary) -> bool:
    return SourceVisibility.span_visible(first,last,pass_start,score_loop_enabled,preparation_history)

static func intervals_overlap(first: Dictionary, second: Dictionary) -> bool:
    return SourceVisibility.intervals_overlap(first,second)

func ink(hand: String) -> Color:
    var selected: bool = active_hand == "both" or active_hand == hand
    return Design.SCORE_INK if selected else Color(Design.STAFF_MUTED,.46)

func event_ink(score_layout, event: Dictionary) -> Color:
    return ink(score_layout.performing_hand(event))

func record_notehead(event: Dictionary, point: Vector2, viewport_width: float) -> void:
    var id: String = str(event["id"])
    pass_noteheads[id] = point
    drawn_note_instances.append({"event_id":id,"source_id":event.get("source_id"),
        "pass_index":pass_index,"instance_id":"%d:%s" % [pass_index,id],"position":point})
    if not drawn_noteheads.has(id) or absf(point.x-viewport_width*PLAYHEAD_FRACTION)<absf(drawn_noteheads[id].x-viewport_width*PLAYHEAD_FRACTION):
        drawn_noteheads[id] = point
