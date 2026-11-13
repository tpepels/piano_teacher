extends SceneTree

const Settings := preload("res://settings_screen.gd")
const Coordinator := preload("res://learning_statistics_coordinator.gd")

class Request extends Node:
    signal request_completed(code: int, body: PackedByteArray)
    var calls: Array = []
    var canceled := 0
    func request(operation: String, payload: Dictionary = {}) -> Error:
        calls.append([operation, payload])
        return OK
    func cancel_request() -> void:
        canceled += 1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var settings := Settings.new()
    root.add_child(settings)
    settings.size = Vector2(360, 640)
    var view = settings.statistics_view
    view.visible = true
    await process_frame
    for control in [view.scope_picker, view.refresh_button, view.previous_button, view.next_button]:
        assert(control.get_global_rect().end.x <= settings.get_global_rect().end.x+1, "statistics controls fit compact Settings")
    var request := Request.new()
    root.add_child(request)
    var owner := Coordinator.new()
    root.add_child(owner)
    owner.configure(request, view)
    owner.update_context("piece", "learner")
    view.refresh_button.pressed.emit()
    view.refresh_button.pressed.emit()
    assert(request.calls.size() == 1, "duplicate refresh must coalesce")
    var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
    request.request_completed.emit(0, JSON.stringify(report).to_utf8_buffer())
    assert(view.report_label.text.contains("1 recorded takes"))
    assert(view.report_label.text.contains("Pitch"))
    assert(view.report_label.text.contains("unknown"))
    view.scope_picker.select(1)
    view.scope_picker.item_selected.emit(1)
    assert(request.calls[-1][1]["fingerprint"] == "piece")
    owner.update_context("new-piece", "learner")
    assert(request.canceled > 0)
    request.request_completed.emit(0, JSON.stringify(report).to_utf8_buffer())
    assert(not view.report_label.text.contains("1 recorded takes"), "old-piece report rejected")
    view.refresh_button.pressed.emit()
    request.request_completed.emit(3, JSON.stringify({"error": "Try again"}).to_utf8_buffer())
    assert(view.report_label.text.contains("Try again"))
    view.refresh_button.pressed.emit()
    report["attempts"]["count"] = 0
    report["fingerprint"] = "new-piece"
    request.request_completed.emit(0, JSON.stringify(report).to_utf8_buffer())
    assert(view.report_label.text.contains("No recorded takes"))
    owner.invalidate()
    assert(view.report_label.text.contains("Refresh"))
    print("LEARNING_STATISTICS_UI_OK")
    quit(0)
