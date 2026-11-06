extends Control
## Status-tinted NOTE INK ONLY. Python owns assessments; NativeView owns the
## original Verovio drawing and immutable note locations. No standalone halo,
## rings, badges, particle emitters, extra camera, or grading logic lives here.
const Statuses := preload("res://note_status_registry.gd")
const NoteInk := preload("res://note_status_ink.gd")

var score: Control
var score_revision := -1
var source_to_id: Dictionary = {}
var head_glyphs: Dictionary = {}
var statuses := Statuses.new()
var markers: Dictionary = {} # read-only compatibility snapshot of active take
var last_sequence := 0
var _active_take := ""
var _suppress_graded_ink := false

func _init() -> void:
    mouse_filter = Control.MOUSE_FILTER_IGNORE
    focus_mode = Control.FOCUS_NONE
    set_process(false)

func bind_score(renderer: Control, revision: int) -> void:
    if is_instance_valid(score) and score.draw.is_connected(_score_repainted):
        score.draw.disconnect(_score_repainted)
    score = renderer
    score_revision = revision
    score.draw.connect(_score_repainted)
    source_to_id.clear()
    head_glyphs.clear()
    statuses.clear()
    markers.clear()
    last_sequence = 0
    _active_take = ""
    _suppress_graded_ink = false
    for event in renderer.layout.ordered_events:
        var id: String = str(event.get("id",""))
        if id.is_empty() or str(event.get("kind","note")) != "note":
            continue
        var note_type: String = str(event.get("note_type","quarter"))
        head_glyphs[id] = ("head_whole" if note_type == "whole" else
            "head_half" if note_type == "half" else "head_black")
        if bool(event.get("is_attack",false)) and event.get("source_id") != null:
            source_to_id[str(event["source_id"])] = id
    queue_redraw()

func _score_repainted() -> void:
    if not statuses.snapshot().is_empty() and not _suppress_graded_ink:
        queue_redraw()

func _event_id(source_id: String) -> String:
    return str(source_to_id.get(source_id,""))

func _accept_live(event: Dictionary, state: Dictionary) -> bool:
    if _suppress_graded_ink or score_revision != int(state.get("revision",-2)):
        return false
    if str(state.get("phase","")) != "playing" or \
            int(event.get("transport_id",-1)) != int(state.get("transport_id",-2)):
        return false
    var raw: String = str(event.get("status",""))
    if raw not in ["on_time","early","late"]:
        return false
    var source_id: String = str(event.get("source_id",""))
    var note_id: String = _event_id(source_id)
    if note_id.is_empty():
        return false
    var take: String = Statuses.take_key(state)
    return statuses.record(take,note_id,raw,false)

func accept_live_event(event: Dictionary, state: Dictionary) -> void:
    # Low-latency real MIDI arrival. This is provisional; settled marks from
    # the backend override it when grading (including release) is complete.
    var sequence: int = int(event.get("sequence",0))
    if sequence <= last_sequence or not is_instance_valid(score):
        return
    last_sequence = sequence
    _suppress_graded_ink = bool(state.get("preview_only",false)) or \
        str(state.get("mode","")) == "listen"
    if _accept_live(event,state):
        markers = (statuses.snapshot().get(Statuses.take_key(state),{})
            as Dictionary).duplicate()
        queue_redraw()

func present(state: Dictionary) -> void:
    if not is_instance_valid(score):
        return
    var suppress: bool = bool(state.get("preview_only",false)) or \
        str(state.get("mode","")) == "listen"
    var previous_suppress: bool = _suppress_graded_ink
    _suppress_graded_ink = suppress
    if int(state.get("revision",-2)) != score_revision or suppress:
        markers.clear()
        for event in state.get("midi_visual_events",[]):
            last_sequence = maxi(last_sequence,int(event.get("sequence",0)))
        if previous_suppress != suppress or not markers.is_empty():
            queue_redraw()
        return
    var take: String = Statuses.take_key(state)
    var previous_take: String = _active_take
    _active_take = take
    var changed := false
    # Only the authoritative assessment grades a note. Unmapped/estimated
    # events never invent an on-score identity.
    for mark in state.get("feedback_marks",[]):
        if not mark is Dictionary or bool(mark.get("estimated",false)):
            continue
        var id: String = str(mark.get("note_id",mark.get("id","")))
        if id.is_empty():
            id = _event_id(str(mark.get("source_id","")))
        if head_glyphs.has(id):
            changed = statuses.record(take,id,str(mark.get("status","")),
                true) or changed
    for event in state.get("midi_visual_events",[]):
        if not event is Dictionary:
            continue
        var sequence: int = int(event.get("sequence",0))
        if sequence <= last_sequence:
            continue
        last_sequence = sequence
        if float(event.get("age",99.0)) > .25:
            continue
        changed = _accept_live(event,state) or changed
    var physical_keys: Array = []
    if score.get("stream_passes") is Array:
        for strip in score.stream_passes:
            if str(strip.get("kind","source")) == "source":
                physical_keys.append(str(strip.get("take_key","")))
    statuses.prune(physical_keys,take)
    var next: Dictionary = statuses.snapshot().get(take,{})
    if changed or next != markers or previous_take != take or previous_suppress:
        markers = next.duplicate()
        queue_redraw()

func note_position(id: String) -> Vector2:
    if not is_instance_valid(score):
        return Vector2.INF
    return score.drawn_noteheads.get(id,Vector2.INF)

func status_for(take: String, note_id: String) -> String:
    return statuses.status(take,note_id)

func _draw() -> void:
    if _suppress_graded_ink or not is_instance_valid(score) or \
            not score.is_visible_in_tree():
        return
    var atlas: Variant = score.get("glyphs")
    if atlas == null or not atlas.has_method("paint"):
        return
    var gap: float = score.staff_gap()
    var take_by_strip: Dictionary = {}
    if score.get("stream_passes") is Array:
        for strip in score.stream_passes:
            if str(strip.get("kind","source")) == "source":
                take_by_strip[int(strip.get("serial",-1))] = str(
                    strip.get("take_key",""))
    # True physical instances are essential: if the same source note is on
    # the moving bar twice, only the graded take receives the colored head.
    # This does not recolor the next (unplayed) copy.
    var projected: Variant = score.get("drawn_note_instances")
    var physical: Array = projected if projected is Array else []
    if not physical.is_empty():
        for occurrence in physical:
            var id: String = str(occurrence.get("event_id",""))
            if not head_glyphs.has(id):
                continue
            var key: String = str(take_by_strip.get(
                int(occurrence.get("pass_index",-1)),""))
            var status: String = statuses.status(key,id)
            if status == Statuses.UNPLAYED:
                continue
            var p: Vector2 = occurrence.get("position",Vector2.INF)
            if not is_finite(p.x) or p.x < 0.0 or p.x > size.x:
                continue
            NoteInk.paint(self,atlas,str(head_glyphs[id]),p,gap,status)
        return
    # A bare score consumer may only expose nearest-note metadata; that
    # interface has exactly one logical copy. Production always uses the
    # physical-instance route above when notation is present.
    if not take_by_strip.is_empty():
        return
    for id in markers:
        if not head_glyphs.has(id):
            continue
        var p: Vector2 = note_position(str(id))
        if not is_finite(p.x) or p.x < 0.0 or p.x > size.x:
            continue
        NoteInk.paint(self,atlas,str(head_glyphs[id]),p,gap,
            statuses.status(_active_take,str(id)))
