extends SceneTree
const Projector := preload("res://notation/native/retained_note_projection.gd")

func _initialize() -> void:
    var failures := 0
    var notes: Array = [
        {"event_id":"a","source_id":"source-a","position":Vector2(0,20)},
        {"event_id":"repeat","source_id":"source-r","position":Vector2(100,30)},
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
            instances[0]["instance_id"]!="7:repeat" or \
            instances[0]["position"]!=Vector2(15,30) or \
            heads.get("repeat")!=Vector2(25,30):
        failures += 1
    if notes!=original:
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
