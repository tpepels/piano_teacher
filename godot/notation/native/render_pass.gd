extends RefCounted
## One ephemeral, canonical source-paint pass. Retained ink is compiled once
## per source revision. Scrolling, repetition and the graded source deadline
## cannot alter these geometry or notehead commands.
const Design := preload("res://practice_theme.gd")
const PLAYHEAD_FRACTION := .33
var clock: float
var playhead_x: float
var gap: float
var play_from_beat: float
var active_hand: String
var focused_staff: String
var pass_index: int
var pass_start: float
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
    focused_staff = str(context.get("focused_staff",""))
    pass_index = int(context.get("pass_index",0))
    pass_start = float(context.get("pass_start",0.0))
    visual_scroll_beat = float(context.get("visual_scroll_beat",0.0))

func screen_x(axis, beat: float) -> float:
    return axis.screen_x(beat,clock,playhead_x,play_from_beat)

func event_visible(_event: Dictionary) -> bool:
    return true

func span_visible(_first: Dictionary, _last: Dictionary) -> bool:
    return true

static func intervals_overlap(first: Dictionary, second: Dictionary) -> bool:
    return float(first["start_beat"]) < float(second["end_beat"])-.00001 and \
        float(second["start_beat"]) < float(first["end_beat"])-.00001

func ink(hand: String) -> Color:
    if not focused_staff.is_empty() and hand != focused_staff:
        return Color.TRANSPARENT
    var selected: bool = active_hand == "both" or active_hand == hand
    return Design.SCORE_INK if selected else Color(Design.STAFF_MUTED,.46)

func event_ink(score_layout, event: Dictionary) -> Color:
    return ink(score_layout.performing_hand(event))

func record_notehead(event: Dictionary, point: Vector2, viewport_width: float) -> void:
    var id: String = str(event["id"])
    pass_noteheads[id] = point
    drawn_note_instances.append({"event_id":id,"source_id":event.get("source_id"),
        "pass_index":pass_index,"instance_id":"%d:%s" % [pass_index,id],"position":point})
    if not drawn_noteheads.has(id) or \
            absf(point.x-viewport_width*PLAYHEAD_FRACTION) < \
            absf(drawn_noteheads[id].x-viewport_width*PLAYHEAD_FRACTION):
        drawn_noteheads[id] = point
