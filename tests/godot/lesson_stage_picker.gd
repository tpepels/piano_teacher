extends SceneTree
const Picker := preload("res://practice_step_selector.gd")
var failures := 0

func check(ok: bool, reason: String) -> void:
    if not ok:
        failures += 1
        push_error("LESSON_STAGE_PICKER_FAILURE: "+reason)

func _initialize() -> void:
    call_deferred("_run")

func _run() -> void:
    var picker := Picker.new()
    root.add_child(picker)
    picker.present_context({"loaded":true,"piece_fingerprint":"score-a",
        "lesson_step":1},false)
    picker.present_overview({"piece_fingerprint":"score-a", "steps":[
        {"number":1,"first_bar":1,"last_bar":2,"hand":"right",
         "level":"fukuda-midi-chord-outer","stage_family":"Fukuda",
         "stage_label":"Outer chord notes","stage_change":"5/8 source notes"},
        {"number":2,"first_bar":1,"last_bar":2,"hand":"right",
         "level":"coda-slowdown-x2","stage_family":"Coda",
         "stage_label":"Slowed playback","stage_change":"tempo adjustment"}]})
    check(picker.picker.item_count == 2, "Both genuine MIDI stages are listed")
    check(picker.picker.get_item_text(0).contains("Fukuda: Outer chord notes"),
        "The menu must identify the actual source reduction")
    check(picker.picker.get_item_text(1).contains("Coda: Slowed playback"),
        "The menu must identify the authored slowdown")
    check(picker.picker.get_item_tooltip(0).contains("5/8 source notes"),
        "The source-note change is inspectable")
    check(picker.picker.text.contains("Outer chord notes"),
        "The selected stage remains identified")
    picker.present_context({"loaded":true,"piece_fingerprint":"score-a",
        "lesson_step":2},false)
    check(picker.picker.text.contains("Slowed playback"),
        "The selected label follows the active lesson step")
    print("LESSON_STAGE_PICKER_FAILURES:",failures)
    picker.queue_free()
    quit(0 if failures == 0 else 1)
