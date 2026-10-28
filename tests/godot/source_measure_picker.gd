extends SceneTree

const SourceMeasurePicker := preload("res://source_measure_picker.gd")

func _initialize() -> void:
    var picker: Control = SourceMeasurePicker.new()
    root.add_child(picker)
    picker.size = Vector2(800, 600)
    picker.call("show_piece", {"title":"Test_Piece", "piece_last_bar":16,
        "selected_start_bar":5})
    var failures := 0
    if not picker.visible:
        failures += 1
    if picker.call("selected_bar") != 5:
        failures += 1
    if picker.call("selected_mode") != "learn":
        failures += 1
    if picker.call("is_mode_popup_open"):
        failures += 1
    var panel: PanelContainer = picker.get("panel")
    if panel == null or panel.size.x > 620 or panel.size.y > 570:
        failures += 1
    picker.call("resize_panel", Vector2(500, 400))
    if panel.size.x > 500 or panel.size.y > 400:
        failures += 1
    picker.hide()
    if picker.visible:
        failures += 1
    print("SOURCE_PICKER_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
