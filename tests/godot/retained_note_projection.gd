extends SceneTree
const Projector := preload("res://notation/native/retained_note_projection.gd")

func _initialize() -> void:
    var failures := 0
    var notes: Array = [
        {"event_id":"a","source_id":"source-a","position":Vector2(0,20)},
        {"event_id":"repeat","source_id":"source-r","position":Vector2(100,30)},
        {"event_id":"repeat","source_id":"source-r","position":Vector2(110,30)},
        {"event_id":"repeat","source_id":"source-r","position":Vector2(110,30)},
        {"event_id":"z","source_id":"source-z","position":Vector2(300,40)}]
    var original: Array = notes.duplicate(true)
    var instances: Array = []
    var heads: Dictionary = {}
    var count: int = Projector.append_visible(notes,-85.0,40.0,30.0,7,
        instances,heads)
    # Source 100/110 remain visible; source 300 and source 0 are outside
    # the 60px interaction margin.
    if count!=2 or instances.size()!=2 or \
            instances[0]["position"]!=Vector2(15,30) or \
            heads.get("repeat")!=Vector2(25,30) or \
            str(instances[0]["instance_id"]) == str(instances[1]["instance_id"]):
        failures += 1
    # Reprojecting the same scored source at a new world time keeps each
    # physical notehead identity constant, without duplicating glyphs.
    var later: Array = []
    var later_heads: Dictionary = {}
    count = Projector.append_visible(notes,-90.0,40.0,30.0,7,
        later,later_heads)
    if count!=2 or later.size()!=2 or \
            later[0]["instance_id"] != instances[0]["instance_id"] or \
            later[1]["instance_id"] != instances[1]["instance_id"]:
        failures += 1
    if notes!=original:
        failures += 1
    # Dynamic admission clips BOTH sides of a retained score, even when
    # the notehead itself is spatially visible in the viewport.
    var bounded_instances: Array = []
    var bounded_heads: Dictionary = {}
    count = Projector.append_visible(notes,-85.0,40.0,30.0,10,
        bounded_instances,bounded_heads,100.0,110.0)
    if count != 1 or bounded_instances.size()!=1 or \
            bounded_instances[0]["position"]!=Vector2(15,30):
        failures += 1
    count = Projector.append_visible(notes,-85.0,40.0,30.0,11,
        bounded_instances,bounded_heads,120.0,110.0)
    if count != 0 or bounded_instances.size()!=1:
        failures += 1
    count = Projector.append_visible(notes,-1200.0,40.0,30.0,8,
        instances,heads)
    if count!=0 or instances.size()!=2:
        failures += 1
    count = Projector.append_visible([],0.0,40.0,30.0,9,instances,heads)
    if count!=0 or instances.size()!=2:
        failures += 1
    print("RETAINED_NOTE_PROJECTION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
