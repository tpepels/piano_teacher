extends Node2D
## Status ink of ONE retained source strip, drawn as a child of that strip.
##
## It shares the strip's transform and its StreamPassWindow clip, so colored
## heads move with the source ink, are clipped exactly where the strip is
## clipped and never appear detached from it. It draws only from the
## immutable head records the strip compiled (no score scan, no queue copy)
## and repaints only when the take bound to the strip, that take's ledger
## revision, visibility or the strip's compilation changes -- never per frame.
const GhostNotePainter := preload("res://notation/native/ghost_note_painter.gd")
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
var _ghost_layer: Node2D
var _ghosts: Array = []

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

    _ghost_layer = Node2D.new()
    _ghost_layer.name = "ActualWrongPitches"
    _ghost_layer.draw.connect(_paint_ghosts)
    add_child(_ghost_layer)

func sync(take: String, source, visible_ink: bool,
        physical_source_bounds: Vector2 = Vector2(NAN,NAN)) -> void:
    var revision: int = -1
    if source != null and is_instance_valid(source):
        revision = int(source.take_revision(take))
    else:
        source = null
    if not is_finite(physical_source_bounds.x):
        physical_source_bounds.x = segment.source_floor
    if not is_finite(physical_source_bounds.y):
        physical_source_bounds.y = segment.source_ceiling
    var signature: Array = [take,revision,visible_ink,physical_source_bounds,
        int(segment.compile_generation),
        source.get_instance_id() if source != null else 0]
    if signature == _signature:
        # The short-lived actual-pitch layer fades per frame. Authored note
        # status buffers still repaint only on ledger/compile changes.
        if not _ghosts.is_empty():
            _ghost_layer.queue_redraw()
        return
    _signature = signature
    take_key = take
    _source = source
    _visible = visible_ink
    _colored.clear()
    _ghosts.clear()
    if _visible and _source != null and not take.is_empty():
        var statuses: Dictionary = _source.statuses_for_take(take)
        var by_event: Dictionary = segment.instances_by_event
        for id in statuses:
            for instance in by_event.get(id,[]):
                _colored.append({"instance":instance,"status":statuses[id]})
        for ghost in _source.ghosts_for_take(take):
            var at: float = float(ghost["beat"])
            # The existing physical window owns ghost ink too, including
            # its measured header lead. Never clamp a played beat to zero
            # or enlarge a source strip just to reveal an early wrong key.
            if at >= physical_source_bounds.x and at < physical_source_bounds.y:
                _ghosts.append(ghost)
    _ghost_layer.queue_redraw()
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
    if _colored.is_empty() or segment.painter == null:
        return
    var glyphs = segment.painter.glyphs
    for entry in _colored:
        Ink.paint(layer,glyphs,entry["instance"],str(entry["status"]),pass_name)

func _paint_ghosts() -> void:
    if segment.painter == null:
        return
    for ghost in _ghosts:
        GhostNotePainter.paint(_ghost_layer,segment.painter,ghost)
