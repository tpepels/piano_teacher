extends Control
# Presentation only. Python owns assessment; the native compositor owns every
# notehead position. This layer never uses legacy page coordinates or grades.
const Design := preload("res://practice_theme.gd")
const MAX_PULSES := 24
var score: Control
var score_revision := -1
var source_to_id: Dictionary = {}
var markers: Dictionary = {}
var pulses: Array = []
var last_sequence := 0
var moving := false

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    set_process(false)

func bind_score(renderer: Control, revision: int) -> void:
    score = renderer
    score_revision = revision
    source_to_id.clear()
    markers.clear()
    pulses.clear()
    for event in renderer.ordered_events:
        if bool(event.get("is_attack", false)) and event.get("source_id") != null:
            source_to_id[str(event.source_id)] = str(event.id)
    queue_redraw()

func present(state: Dictionary) -> void:
    var ungraded: bool = bool(state.get("preview_only", false)) or \
        str(state.get("mode", "")) == "listen"
    markers.clear()
    if ungraded or int(state.get("revision", -2)) != score_revision:
        for event in state.get("midi_visual_events", []):
            last_sequence = maxi(last_sequence, int(event.get("sequence", 0)))
        pulses.clear()
        moving = false
        set_process(false)
        queue_redraw()
        return
    for mark in state.get("feedback_marks", []):
        var id: String = str(mark.get("note_id", mark.get("id", "")))
        if id.is_empty():
            id = str(source_to_id.get(str(mark.get("source_id", "")), ""))
        if not id.is_empty() and not bool(mark.get("estimated", false)):
            markers[id] = str(mark.get("status", ""))
    moving = bool(state.get("running", false)) and not bool(state.get("paused", false))
    var now: int = Time.get_ticks_msec()
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
        if pulses.size() > MAX_PULSES:
            pulses.pop_front()
    set_process((moving and not markers.is_empty()) or not pulses.is_empty())
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
    if (not moving or markers.is_empty()) and pulses.is_empty():
        set_process(false)

func _tone(status: String) -> Color:
    if status in ["correct", "on_time"]:
        return Design.MINT
    return Design.AMBER if status in ["early", "late", "expected", "assisted", "short", "long"] else Design.CORAL

func _draw() -> void:
    if not is_instance_valid(score) or not score.is_visible_in_tree():
        return
    var gap: float = score._gap()
    # Bound work to the compositor's visible window, even on long lessons.
    for id in score.drawn_noteheads:
        if not markers.has(id):
            continue
        var p: Vector2 = note_position(id)
        if p == Vector2.INF or p.x < 36.0:
            continue
        var status: String = markers[id]
        draw_arc(p, gap*.84, 0, TAU, 28, Color(_tone(status),.85), 1.8, true)
        if status in ["missed", "wrong", "extra"]:
            draw_circle(p+Vector2(gap,-gap),2.4,Design.CORAL)
    var now := Time.get_ticks_msec()
    for pulse in pulses:
        var p: Vector2 = note_position(str(pulse.id))
        if p == Vector2.INF or p.x < 36.0:
            continue
        var life: float = clampf(float(int(pulse.until)-now)/320.0,0.0,1.0)
        var tone: Color = _tone(str(pulse.status))
        draw_arc(p,gap*(.85+(1.0-life)*.45),0,TAU,28,Color(tone,life*.8),2,true)
        for ray in range(6):
            var direction := Vector2.RIGHT.rotated(float(ray)*TAU/6.0)
            var start: Vector2 = p+direction*gap*(1.1+(1.0-life)*.9)
            draw_line(start,start+direction*life*3.0,Color(tone,life*.55),1.3,true)
