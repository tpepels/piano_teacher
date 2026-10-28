extends SceneTree
const Layout := preload("res://notation/native/score_layout.gd")
const Connectors := preload("res://notation/native/connector_geometry.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")

func _initialize() -> void:
    var axis := Axis.new()
    var atlas := Glyphs.new()
    var measure := {"number":1,"clefs":{"right":{"sign":"G","line":2}}}
    axis.measures = [measure]
    var first := {"id":"first","kind":"note","staff":"right","measure":1,
        "beat":0.0,"note_type":"eighth","stem":"up","spelling":{"step":"E","octave":4}}
    var last := first.duplicate(true)
    last.merge({"id":"last","beat":1.0,"note_type":"quarter"},true)
    var score := Layout.new(axis,atlas)
    score.set_viewport(Vector2(1000,500))
    score.measure_by_number = {1:measure}
    score.ordered_events = [first,last]
    score.cached_head_offsets = {"first":-3.0,"last":4.0}
    var connector := Connectors.new(score)
    var failures := 0
    var place: Dictionary = connector.tie_placement(first,last,100,200,20)
    if place["x0"]!=97.0 or place["x1"]!=204.0 or place["y"]!=220.0 or not place["down"]:
        failures += 1
    if connector.tie_template_key(first,last,place,20)!="up":
        failures += 1
    place["down"] = false
    if connector.tie_template_key(first,last,place,20)!="start_eighth_above":
        failures += 1
    score.beamed_note_ids["first"] = true
    if connector.tie_template_key(first,last,place,20)!="down":
        failures += 1
    if not connector.tie_placement(first,last,100,103,20).is_empty():
        failures += 1
    connector.flag_clearances["obsolete"] = 2.0
    connector.clear_cache()
    if not connector.flag_clearances.is_empty():
        failures += 1
    # Replacing an owned geometry policy must preserve the current viewport.
    var view = load("res://notation/native/view.gd").new()
    view.size = Vector2(1000,500)
    var replacement := Layout.new(axis,atlas)
    replacement.measure_by_number = {1:measure}
    replacement.ordered_events = [first,last]
    view.layout = replacement
    var replaced: Dictionary = view.connector_geometry.tie_placement(first,last,100,200,20)
    if replaced["y"]!=220.0 or replacement.size!=view.size:
        failures += 1
    view.free()
    print("CONNECTOR_GEOMETRY_FAILURES:",failures)
    quit(0 if failures==0 else 1)
