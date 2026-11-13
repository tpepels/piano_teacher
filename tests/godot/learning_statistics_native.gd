extends SceneTree
## Actual embedded worker + Main Settings reachability, with canonical evidence.
var app: Control
var failure := ""
var phase := "initialization"
var fixture_started := 0

func _initialize() -> void:
    fixture_started = Time.get_ticks_msec()
    call_deferred("run")

func _process(_delta: float) -> bool:
    if Time.get_ticks_msec()-fixture_started > 30000:
        print("LEARNING_STATISTICS_NATIVE_FAILED phase=", phase)
        if app != null:
            print(app.settings_view.statistics_view.report_label.text.left(500))
        quit(1)
    return false

func wait_for(predicate: Callable, label: String) -> bool:
    var deadline := Time.get_ticks_msec()+20000
    while not predicate.call():
        if Time.get_ticks_msec() > deadline:
            failure = "timeout: " + label
            return false
        await process_frame
    return true

func run() -> void:
    app = load("res://main.gd").new()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    app._navigate("settings")
    if not await wait_for(func() -> bool: return not app.learning_status_pending and not app.preferences.is_empty(), "learning status"):
        print("LEARNING_STATISTICS_NATIVE_FAILED ", failure)
        quit(1)
        return
    var view = app.settings_view.statistics_view
    phase = "first report"
    view.visible = true
    view.refresh_button.pressed.emit()
    if not await wait_for(func() -> bool: return view.report_label.text.contains("recorded takes"), "real statistics report"):
        print("LEARNING_STATISTICS_NATIVE_FAILED ", failure, " ", view.report_label.text)
        quit(1)
        return
    assert(view.report_label.text.contains("250 recorded takes"))
    assert(not view.next_button.disabled)
    view.next_button.pressed.emit()
    phase = "next page"
    assert(await wait_for(func() -> bool: return not view.refresh_button.disabled, "second page"))
    assert(view.page_label.text.contains("Page 2"))
    assert(not view.previous_button.disabled)
    view.previous_button.pressed.emit()
    phase = "previous page"
    assert(await wait_for(func() -> bool: return not view.refresh_button.disabled, "previous page"))
    assert(view.page_label.text.contains("Page 1"))
    # The same command boundary performs a maximum-size report on the native
    # read-only worker while musical snapshots continue on the command worker.
    var stats: Node = app._new_request(func(_code: int, _body: PackedByteArray): pass)
    var complete := [false]
    var count := [0]
    stats.request_completed.connect(func(code: int, body: PackedByteArray):
        var report: Variant = JSON.parse_string(body.get_string_from_utf8())
        if code != 0:
            print("NATIVE_STATISTICS_COMMAND_ERROR ", body.get_string_from_utf8().left(500))
        complete[0] = code == 0 and report is Dictionary and int(report.get("schema_version", 0)) == 2
        count[0] = int(report.get("attempts", {}).get("count", 0)) if report is Dictionary else 0)
    var started := Time.get_ticks_msec()
    phase = "maximum native report"
    stats.request("learning.statistics", {"version": 1, "limit": 1000})
    var state_request: Node = app._new_request(func(_code: int, _body: PackedByteArray): pass)
    # A mutable array carries callback completion through GDScript captures.
    var answered := [0]
    state_request.request_completed.connect(func(code: int, _body: PackedByteArray):
        if code == 0:
            answered[0] += 1)
    while not complete[0] and Time.get_ticks_msec()-started < 10000:
        state_request.request("state.snapshot")
        await process_frame
    var elapsed := Time.get_ticks_msec()-started
    assert(complete[0] and count[0] == 1000, "maximum native report")
    assert(answered[0] > 0, "musical worker answered during report")
    view.scope_picker.select(1)
    phase = "current-piece report"
    view.scope_picker.item_selected.emit(1)
    assert(await wait_for(func() -> bool: return not view.refresh_button.disabled, "current-piece report"))
    assert(view.report_label.text.contains("250 recorded takes"))
    # Clear local evidence through the authorized UI action, then verify empty
    # state via the exact same native request/view path.
    app.settings_view.learner_history_delete_requested.emit()
    phase = "delete learner"
    assert(await wait_for(func() -> bool: return not app.command_state.pending, "delete learner"))
    assert(await wait_for(func() -> bool: return not app.learning_status_pending, "fresh learner identity"))
    view.scope_picker.select(0)
    phase = "empty report"
    view.scope_picker.item_selected.emit(0)
    assert(await wait_for(func() -> bool: return not view.refresh_button.disabled, "empty report"))
    assert(view.report_label.text.contains("No recorded takes"))
    print("LEARNING_STATISTICS_NATIVE_OK elapsed_ms=%d snapshots=%d selected=%d pages=true empty=true" % [elapsed, answered[0], count[0]])
    app.free()
    quit(0)
