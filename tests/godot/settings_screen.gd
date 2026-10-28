extends SceneTree

const SettingsScreen := preload("res://settings_screen.gd")

func _initialize() -> void:
    var view := SettingsScreen.new()
    root.add_child(view)
    call_deferred("_check_view", view)

func _check_view(view: ScrollContainer) -> void:
    var failures := 0
    var grid: GridContainer = view.get("settings_grid")
    var directory: LineEdit = view.get("folder_edit")
    var tempo: SpinBox = view.get("tempo_setting")
    var volume: HSlider = view.get("listen_volume_slider")
    if grid == null or directory == null or tempo == null or volume == null:
        failures += 1
    else:
        if grid.get_child_count() != 4 or grid.columns != 1:
            failures += 1
        if tempo.min_value != 12 or tempo.max_value != 300:
            failures += 1
        if volume.min_value != -12 or volume.max_value != 12:
            failures += 1
    print("SETTINGS_SCREEN_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
