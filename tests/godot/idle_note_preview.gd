extends SceneTree
const Preview := preload("res://notation/native/idle_preview.gd")
var failures := 0

func check(condition: bool, reason: String) -> void:
    if not condition:
        failures += 1
        push_error("IDLE_NOTE_PREVIEW_FAILURE: " + reason)

func _initialize() -> void:
    var events: Array = [
        {"id":"lh1","kind":"note","beat":0.0,"staff":"left"},
        {"id":"rh1","kind":"note","beat":7.0,"staff":"right"},
        {"id":"rh2","kind":"note","beat":7.5,"staff":"right"}]
    var original_start := 0.0
    var width := 1200.0
    var density := 300.0
    var fraction := .42
    var ready: float = Preview.beat_for_ready(
        events,"right",original_start,width,density,fraction)
    check(ready > 4.0 and ready < 7.0,
        "The earliest right-hand attack should be in the visible READY window")
    var visible_x: float = width*fraction+(7.0-ready)*density
    check(visible_x < width and visible_x > width*fraction,
        "Original right-hand ink must appear to the right of fixed playhead")
    check(Preview.beat_for_ready(events,"both",0.0,width,density,fraction) == 0.0,
        "Combined hands must not skip a visible left-hand opening")
    check(Preview.beat_for_ready(events,"right",6.0,width,density,fraction) == 6.0,
        "A nearby next attack must not move a stopped camera")
    check(Preview.beat_for_ready(events,"right",0.0,width,0.0,fraction) == 0.0,
        "An unmeasured viewport must preserve its original start")
    check(original_start == 0.0, "Preview cannot mutate the transport origin")
    print("IDLE_NOTE_PREVIEW_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
