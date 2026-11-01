extends SceneTree
const Presenter := preload("res://command_success_presenter.gd")

class Library:
    extends RefCounted
    var open_calls := 0
    var last_open := "pending"
    func present_open_status(status: String) -> void:
        open_calls += 1
        last_open = status

class Practice:
    extends RefCounted
    var picker_calls := 0
    var selected: Dictionary = {}
    func show_source_picker(value: Dictionary) -> void:
        picker_calls += 1
        selected = value

class Settings:
    extends RefCounted
    var message := ""
    func present_message(value: String) -> void:
        message = value

class Lessons:
    extends RefCounted
    var invalidated := 0
    func invalidate() -> void:
        invalidated += 1

func _initialize() -> void:
    var failures := 0
    var library := Library.new()
    var practice := Practice.new()
    var settings := Settings.new()
    var lessons := Lessons.new()
    var presenter := Presenter.new(library,practice,settings,lessons)
    presenter.present_accepted({"kind":"control","invalidate_lesson":true})
    if lessons.invalidated != 1 or library.open_calls != 0:
        failures += 1
    presenter.present_accepted({"kind":"library_open"})
    presenter.present_source_picker({"title":"MIDI"})
    if library.last_open != "" or library.open_calls != 1 or \
            practice.picker_calls != 1 or practice.selected.get("title") != "MIDI":
        failures += 1
    presenter.present_accepted({"kind":"settings"})
    if settings.message != "Settings saved" or lessons.invalidated != 1:
        failures += 1
    presenter.present_accepted({"kind":"device"})
    if library.open_calls != 1 or practice.picker_calls != 1:
        failures += 1
    print("COMMAND_SUCCESS_PRESENTER_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
