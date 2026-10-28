extends SceneTree
const ReviewStrip := preload("res://performance_review_strip.gd")

func _initialize() -> void:
    var strip: VBoxContainer = ReviewStrip.new()
    root.add_child(strip)
    call_deferred("_check", strip)

func _check(strip: VBoxContainer) -> void:
    var failures := 0
    strip.call("present", {})
    if strip.visible:
        failures += 1
    var summary := {"accuracy_percent":75.0, "correct":3, "total":4,
        "missed":1, "wrong":0, "early":1, "late":1, "short":0, "long":1,
        "extra_notes":2, "weakest_bars":[{"first_bar":2}]}
    strip.call("present", summary)
    var label: Label = strip.get("summary_label")
    var button: Button = strip.get("review_button")
    if not strip.visible or label == null or label.text.find("3/4 notes") < 0:
        failures += 1
    if label == null or label.text.find("3 timing/duration") < 0:
        failures += 1
    if button == null or not button.visible or button.disabled:
        failures += 1
    var received: Array = []
    strip.connect("review_requested",func(value: Dictionary): received.append(value))
    if button != null:
        button.pressed.emit()
    if received.size() != 1 or received[0] != summary:
        failures += 1
    summary["weakest_bars"].clear()
    if received.size() == 1 and received[0]["weakest_bars"].is_empty():
        failures += 1
    strip.call("present", {"total":4,"weakest_bars":[]})
    if not strip.visible or button.visible or not button.disabled:
        failures += 1
    strip.call("present", {})
    if strip.visible:
        failures += 1
    print("PERFORMANCE_REVIEW_STRIP_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
