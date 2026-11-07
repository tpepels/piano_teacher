extends Node2D
## Status ink of ONE retained source strip, drawn as a child of that strip.
##
## It shares the strip's transform and its StreamPassWindow clip, so colored
## heads move with the source ink, are clipped exactly where the strip is
## clipped and never appear detached from it. It draws only from the
## immutable head records the strip compiled (no score scan, no queue copy)
## and repaints only when the take bound to the strip, that take's ledger
## revision, visibility or the strip's compilation changes -- never per frame.
const Ink := preload("res://note_status_ink.gd")

var segment: Node2D
var take_key := ""
var painted_instances := 0
# Number of status-ink pass repaints; scrolling must never increase it.
var paint_count := 0
var _source = null
var _visible := true
var _signature: Array = []
var _colored: Array = [] # [{instance, status}]
var _passes: Dictionary = {}

func _init(owner_segment: Node2D) -> void:
    segment = owner_segment
    name = "NoteStatusInk"
    for pass_name in Ink.PASSES:
        var layer := Node2D.new()
        layer.name = "NoteStatus_" + pass_name
        layer.material = Ink.material_for(pass_name)
        layer.draw.connect(_paint.bind(layer,pass_name))
        add_child(layer)
        _passes[pass_name] = layer

func sync(take: String, source, visible_ink: bool) -> void:
    var revision: int = -1
    if source != null and is_instance_valid(source):
        revision = int(source.take_revision(take))
    else:
        source = null
    var signature: Array = [take,revision,visible_ink,
        int(segment.compile_generation),
        source.get_instance_id() if source != null else 0]
    if signature == _signature:
        return
    _signature = signature
    take_key = take
    _source = source
    _visible = visible_ink
    _colored.clear()
    if _visible and _source != null and not take.is_empty():
        var statuses: Dictionary = _source.statuses_for_take(take)
        var by_event: Dictionary = segment.instances_by_event
        for id in statuses:
            for instance in by_event.get(id,[]):
                _colored.append({"instance":instance,"status":statuses[id]})
    painted_instances = _colored.size()
    for layer in _passes.values():
        layer.queue_redraw()

func status_of_instance(instance_id: String) -> String:
    for entry in _colored:
        if str(entry["instance"].get("instance_id","")) == instance_id:
            return str(entry["status"])
    return "unplayed"

func _paint(layer: Node2D, pass_name: String) -> void:
    paint_count += 1
    if _colored.is_empty() or segment.owner_view == null:
        return
    var glyphs = segment.owner_view.glyphs
    for entry in _colored:
        Ink.paint(layer,glyphs,entry["instance"],str(entry["status"]),pass_name)
