extends Control
# Presentation only. Python owns assessment; the native compositor owns every
# notehead position. This layer never uses legacy page coordinates or grades.
const Design := preload("res://practice_theme.gd")
const ScoreView := preload("res://notation/shared/view_base.gd")
const GlowField := preload("res://mint_glow_field.gd")
const MAX_PULSES := 24
# Only confirmed assessment states persist for the current transport take.
# Provisional MIDI onsets are brief pulses and never count as graded success.
const ASSESSED := ["correct", "missed", "wrong", "extra", "early", "late",
    "short", "long", "assisted"]
var score: Control
var score_revision := -1
var source_to_id: Dictionary = {}
var head_glyphs: Dictionary = {}
var markers: Dictionary = {}
var settled_markers: Dictionary = {}
var marker_transport_id := -1
var previous_phase := ""
var pulses: Array = []
var last_sequence := 0
var moving := false
var acknowledged_until_ms := 0
var acknowledged_sequence := 0
var note_glow: ColorRect

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    set_process(false)

func _ready() -> void:
    note_glow = GlowField.new()
    note_glow.name = "NoteReactionBloom"
    note_glow.show_behind_parent = true
    note_glow.configure(2,1.52,Design.MINT)
    note_glow.visible = false
    add_child(note_glow)


func bind_score(renderer: Control, revision: int) -> void:
    if is_instance_valid(score) and score.draw.is_connected(_score_repainted):
        score.draw.disconnect(_score_repainted)
    score = renderer
    score.draw.connect(_score_repainted)
    score_revision = revision
    source_to_id.clear()
    head_glyphs.clear()
    markers.clear()
    settled_markers.clear()
    marker_transport_id = -1
    previous_phase = ""
    pulses.clear()
    acknowledged_until_ms = 0
    acknowledged_sequence = 0
    if note_glow != null:
        note_glow.visible = false
    for event in renderer.layout.ordered_events:
        var id := str(event.get("id", ""))
        if id.is_empty() or str(event.get("kind","note")) != "note":
            continue
        var note_type := str(event.get("note_type", "quarter"))
        head_glyphs[id] = ("head_whole" if note_type == "whole" else
            "head_half" if note_type == "half" else "head_black")
        if bool(event.get("is_attack", false)) and event.get("source_id") != null:
            source_to_id[str(event.source_id)] = id
    queue_redraw()

func _score_repainted() -> void:
    # A paused seek or resize can move noteheads without changing assessed
    # markers. Follow actual compositor redraws rather than idle HTTP polls.
    if not markers.is_empty() or not pulses.is_empty():
        queue_redraw()

func accept_live_event(event: Dictionary, state: Dictionary) -> void:
    # Called on the next Godot frame after a physical note-on, bypassing
    # heavyweight /state polling. This is an acknowledgement, not a grade.
    var sequence := int(event.get("sequence", 0))
    if sequence <= last_sequence or not is_instance_valid(score):
        return
    last_sequence = sequence
    if (bool(state.get("preview_only", false)) or
            str(state.get("phase", "")) != "playing" or
            str(state.get("mode", "")) == "listen" or
            int(state.get("revision", -2)) != score_revision or
            int(event.get("transport_id", -1)) != int(state.get("transport_id", -2))):
        return
    var status := str(event.get("status", ""))
    if status != "on_time":
        return
    acknowledged_sequence = sequence
    acknowledged_until_ms = Time.get_ticks_msec() + 230
    var id := str(source_to_id.get(str(event.get("source_id", "")), ""))
    if not id.is_empty():
        pulses.append({"id": id, "status": "on_time", "until": acknowledged_until_ms})
        if pulses.size() > MAX_PULSES:
            pulses.pop_front()
    set_process(true)
    queue_redraw()

func present(state: Dictionary) -> void:
    var ungraded: bool = bool(state.get("preview_only", false)) or \
        str(state.get("mode", "")) == "listen"
    var previous_markers: Dictionary = markers
    var previous_moving: bool = moving
    var had_pulses: bool = not pulses.is_empty()
    var phase := str(state.get("phase",""))
    var transport := int(state.get("transport_id",-1))
    if transport != marker_transport_id or (
            phase == "ready" and previous_phase in
            ["feedback","recovering","review","performance_complete"]):
        settled_markers.clear()
    marker_transport_id = transport
    previous_phase = phase
    markers = {}
    if ungraded or int(state.get("revision", -2)) != score_revision:
        settled_markers.clear()
        for event in state.get("midi_visual_events", []):
            last_sequence = maxi(last_sequence, int(event.get("sequence", 0)))
        pulses.clear()
        acknowledged_until_ms = 0
        moving = false
        set_process(false)
        if not previous_markers.is_empty() or had_pulses:
            queue_redraw()
        return
    for mark in state.get("feedback_marks", []):
        var id: String = str(mark.get("note_id", mark.get("id", "")))
        if id.is_empty():
            id = str(source_to_id.get(str(mark.get("source_id", "")), ""))
        var status := str(mark.get("status",""))
        if not id.is_empty() and not bool(mark.get("estimated", false)) and                 status in ASSESSED:
            settled_markers[id] = status
    # Live state publishes a sliding assessment window. Keep already assessed
    # colors while that same take scrolls; transport/revision changes clear it.
    markers = settled_markers.duplicate()
    moving = bool(state.get("running", false)) and not bool(state.get("paused", false))
    var now: int = Time.get_ticks_msec()
    var fresh_pulse := false
    for event in state.get("midi_visual_events", []):
        var sequence: int = int(event.get("sequence", 0))
        if sequence <= last_sequence:
            continue
        last_sequence = sequence
        if not moving or str(state.get("phase", "")) != "playing" or \
                int(event.get("transport_id", -1)) != int(state.get("transport_id", -2)):
            continue
        var age: float = float(event.get("age", 99.0))
        var status: String = str(event.get("status", ""))
        if age > .25 or status not in ["on_time", "early", "late", "unexpected"]:
            continue
        var source: String = str(event.get("reference_source_id", "")) if status == "unexpected" \
            else str(event.get("source_id", ""))
        var id: String = str(source_to_id.get(source, ""))
        if id.is_empty():
            continue
        pulses.append({"id":id, "status":status, "until":now+maxi(1,320-int(age*1000))})
        fresh_pulse = true
        if pulses.size() > MAX_PULSES:
            pulses.pop_front()
    set_process((moving and not markers.is_empty()) or not pulses.is_empty() or acknowledged_until_ms > now)
    # HTTP timestamps and consumed MIDI sequences keep changing while idle;
    # only changed ink or a moving score needs another feedback repaint.
    if markers != previous_markers or moving != previous_moving or fresh_pulse:
        queue_redraw()

func note_position(id: String) -> Vector2:
    if not is_instance_valid(score):
        return Vector2.INF
    return score.drawn_noteheads.get(id, Vector2.INF)

func _process(_delta: float) -> void:
    var now := Time.get_ticks_msec()
    for index in range(pulses.size()-1,-1,-1):
        if int(pulses[index].until) <= now:
            pulses.remove_at(index)
    queue_redraw()
    if (not moving or markers.is_empty()) and pulses.is_empty() and acknowledged_until_ms <= now:
        set_process(false)

func _tone(status: String) -> Color:
    if status in ["correct", "on_time"]:
        return Design.MINT
    return Design.AMBER if status in ["early", "late", "expected", "assisted", "short", "long"] else Design.CORAL

# Draw ONLY the authentic Verovio notehead mask, centered at the compositor's
# exact note position. The retained stems, beams, ledger lines, notehead
# geometry and sound timeline remain untouched.
func _paint_head(id: String, point: Vector2, gap: float,
        tone: Color, opacity: float) -> bool:
    if not head_glyphs.has(id):
        return false
    var atlas: Variant = score.get("glyphs")
    if atlas == null or not atlas.has_method("paint"):
        return false
    return bool(atlas.paint(self,str(head_glyphs[id]),point.x,point.y,
        gap,Color(tone,clampf(opacity,0.0,1.0)),true))


func _draw() -> void:
    if not is_instance_valid(score) or not score.is_visible_in_tree():
        if note_glow != null:
            note_glow.visible = false
        return
    var gap: float = score.staff_gap()
    var flare_position := Vector2.INF
    var flare_tone := Design.MINT
    # The fixed playhead itself acknowledges accepted MIDI attacks in mint.
    # The cue is immediate and provisional; held-duration grading is later.
    var ack_left: int = acknowledged_until_ms - Time.get_ticks_msec()
    if ack_left > 0:
        var life := clampf(float(ack_left)/230.0, 0.0, 1.0)
        var cursor_x := size.x * ScoreView.PLAYHEAD_FRACTION
        var line: Rect2 = score.playhead_region()
        draw_line(Vector2(cursor_x,line.position.y),
            Vector2(cursor_x,line.end.y),
            Color(Design.MINT, .85*life), 4.0, true)
        draw_circle(Vector2(cursor_x,line.position.y), 5.0+life*3.0,
            Color(Design.MINT, life))
    # Bound work to the compositor's visible window, even on long lessons.
    for id in score.drawn_noteheads:
        if not markers.has(id):
            continue
        var p: Vector2 = note_position(id)
        if p == Vector2.INF or p.x < 36.0:
            continue
        var status: String = markers[id]
        var tone := _tone(status)
        draw_arc(p,gap*1.08,0,TAU,40,Color(tone,.11),7.0,true)
        draw_arc(p,gap*.91,0,TAU,40,Color(tone,.67),1.4,true)
        _paint_head(str(id),p,gap,tone,.90 if moving else .76)
        if status in ["missed", "wrong", "extra"]:
            var badge := p+Vector2(gap,-gap)
            draw_line(badge-Vector2(2.5,2.5),badge+Vector2(2.5,2.5),tone,1.6,true)
            draw_line(badge+Vector2(-2.5,2.5),badge+Vector2(2.5,-2.5),tone,1.6,true)
    var now := Time.get_ticks_msec()
    for pulse in pulses:
        var p: Vector2 = note_position(str(pulse.id))
        if p == Vector2.INF or p.x < 36.0:
            continue
        var life: float = clampf(float(int(pulse.until)-now)/320.0,0.0,1.0)
        var tone: Color = _tone(str(pulse.status))
        # Light follows the exact glyph. A provisional live hit colors the
        # head briefly; a settled grade always takes precedence over it.
        for radius in [1.35,1.1]:
            draw_arc(p,gap*radius,0,TAU,40,Color(tone,life*.15),5.0,true)
        draw_arc(p,gap*.87,0,TAU,40,Color(tone,life*.95),2.0,true)
        if not markers.has(str(pulse.id)):
            _paint_head(str(pulse.id),p,gap,tone,life*.94)
        if life > .03:
            flare_position = p
            flare_tone = tone
    if note_glow != null:
        var light_on: bool = is_finite(flare_position.x)
        note_glow.visible = light_on
        if light_on:
            note_glow.position = flare_position-Vector2(43.0,35.0)
            note_glow.size = Vector2(86.0,70.0)
            note_glow.configure(2,1.52,flare_tone)
