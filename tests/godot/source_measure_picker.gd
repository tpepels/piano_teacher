extends SceneTree

const SourceMeasurePicker := preload("res://source_measure_picker.gd")

func _initialize() -> void:
    var picker: Control = SourceMeasurePicker.new()
    root.add_child(picker)
    picker.size = Vector2(800, 600)
    # SceneTree._initialize runs before the first ready notification.
    # Defer interaction until the independently built Control is ready.
    call_deferred("_check_picker", picker)


func _check_picker(picker: Control) -> void:
    if picker.get("panel") == null:
        push_error("SourceMeasurePicker did not finish building its controls")
        print("SOURCE_PICKER_FAILURES:1")
        quit(1)
        return
    picker.size = Vector2(800, 600)
    picker.call("show_piece", {"title":"Test_Piece", "piece_last_bar":16,
        "selected_start_bar":5})
    var failures := 0
    var number: SpinBox = picker.get("measure")
    print("PICKER_RAW size=", picker.size, " value=", number.value,
        " edit_text=", number.get_line_edit().text,
        " focus=", picker.get_viewport().gui_get_focus_owner() == number.get_line_edit())
    print("PICKER_INITIAL visible=", picker.visible,
        " bar=", picker.call("selected_bar"),
        " mode=", picker.call("selected_mode"),
        " popup=", picker.call("is_mode_popup_open"))
    if not picker.visible:
        failures += 1
    if picker.call("selected_bar") != 5:
        failures += 1
    if picker.call("selected_mode") != "learn":
        failures += 1
    if picker.call("is_mode_popup_open"):
        failures += 1
    var panel: PanelContainer = picker.get("panel")
    print("PICKER_PANEL_INITIAL size=", panel.size if panel != null else Vector2(-1,-1))
    if panel == null or panel.size.x > 620 or panel.size.y > 570:
        failures += 1
    picker.call("resize_panel", Vector2(500, 400))
    print("PICKER_PANEL_RESIZED size=", panel.size)
    if panel.size.x > 500 or panel.size.y > 400:
        failures += 1
    picker.hide()
    if picker.visible:
        failures += 1
    print("SOURCE_PICKER_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
