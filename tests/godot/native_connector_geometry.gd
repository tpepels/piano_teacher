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
    score.prepare_event_positions(20.0)
    var connector := Connectors.new(score)
    var failures := 0
    if not score.prepared_event_y.has("first") or \
            score.prepared_step(first,20.0) != 0 or \
            absf(score.event_y(first,20.0)-220.0)>.000001:
        failures += 1
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
    # Prepared tie masks translate without any texture readback.
    connector.prepared_ties["first|last"] = {
        "direction":"up","rect":Rect2(98,180,55,15)}
    var shifted_tie: Dictionary = connector.prepared_tie(first,last,42.0)
    if shifted_tie["rect"] != Rect2(140,180,55,15) or shifted_tie["direction"] != "up":
        failures += 1
    # Prepared beam members use canonical source X, not the previous frame's
    # camera X. This path must work with no atlas image or chord calculation.
    score.beam_stem_up_by_note["first"] = true
    score.beam_groups = [[first,last]]
    var canonical: Dictionary = {"art_key":"first|last", "up":true,
        "members":[
            {"id":"first","x":0.0,"head_x":0.0,"tip_y":120.0},
            {"id":"last","x":96.0,"head_x":96.0,"tip_y":125.0}
        ],"source_stem_offsets":[],"anchor_y":100.0,"staff":"right",
        "hand":"right"}
    connector.prepared_beams["first|last"] = canonical
    var projected: Dictionary = connector.beam_layout(
        20.0,1.0,150.0,score.cached_head_offsets,0.0,score.beam_groups)
    var group: Dictionary = projected["groups"][0]
    if absf(float(group["members"][0]["x"])-54.0)>.000001 or \
            absf(float(group["members"][1]["x"])-150.0)>.000001 or \
            absf(float(projected["stems"]["first"]["x"])-54.0)>.000001:
        failures += 1
    if canonical["members"][0]["x"]!=0.0:
        failures += 1  # Moving the camera must not mutate the cached source.
    connector.flag_clearances["obsolete"] = 2.0
    connector.clear_cache()
    if not connector.flag_clearances.is_empty() or \
            not connector.prepared_ties.is_empty() or \
            not connector.prepared_beams.is_empty():
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
