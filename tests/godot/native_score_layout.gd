extends SceneTree
const Layout := preload("res://notation/native/score_layout.gd")
const Axis := preload("res://notation/shared/timeline.gd")
const Glyphs := preload("res://notation/native/glyphs.gd")

func _initialize() -> void:
    var axis := Axis.new()
    var atlas := Glyphs.new()
    var measure := {"number":1,"start_beat":0.0,"end_beat":4.0,
        "clefs":{"right":{"sign":"G","line":2},"left":{"sign":"F","line":4}}}
    var upper := {"id":"upper","kind":"note","staff":"right","hand":"left",
        "measure":1,"beat":0.0,"note_type":"quarter","voice":"1",
        "spelling":{"step":"E","octave":4,"alter":0}}
    var lower := {"id":"lower","kind":"note","staff":"left","hand":"right",
        "measure":1,"beat":0.0,"note_type":"half","voice":"1",
        "spelling":{"step":"G","octave":2,"alter":0}}
    axis.measures = [measure]
    axis.model = {"measures":[measure],"notation_events":[upper,lower]}
    var original := axis.model.duplicate(true)
    var layout := Layout.new(axis,atlas)
    layout.set_viewport(Vector2(1000,500))
    layout.rebuild_index()
    var failures := 0
    if layout.ordered_events.size()!=2:
        failures += 1
    if absf(layout.event_y(upper,20)-220.0)>.001 or absf(layout.event_y(lower,20)-385.0)>.001:
        failures += 1
    if layout.performing_hand(upper)!="left" or layout.display_staff(upper)!="right":
        failures += 1
    if layout.performing_hand(lower)!="right" or layout.display_staff(lower)!="left":
        failures += 1
    layout.cached_staff_gap = 17
    layout.cached_gap_height = 500
    layout.set_viewport(Vector2(1000,600))
    if absf(layout.event_y(upper,20)-256.0)>.001 or layout.cached_staff_gap>0:
        failures += 1
    layout.rest_lane_offsets["old"] = 2.0
    layout.clear()
    if not layout.ordered_events.is_empty() or not layout.rest_lane_offsets.is_empty():
        failures += 1
    if axis.model != original:
        failures += 1
    print("SCORE_LAYOUT_FAILURES:",failures)
    quit(0 if failures==0 else 1)
