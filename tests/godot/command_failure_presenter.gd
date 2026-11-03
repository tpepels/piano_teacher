extends SceneTree
const Presenter := preload("res://command_failure_presenter.gd")

class Library:
    extends RefCounted
    var open_status := ""
    var request_error := ""
    func present_open_status(message: String, _error: bool = false) -> void:
        open_status = message
    func present_request_error(message: String) -> void:
        request_error = message

class Practice:
    extends RefCounted
    var message := ""
    func present_message(value: String) -> void:
        message = value

class Settings:
    extends RefCounted
    var message := ""
    func present_message(value: String) -> void:
        message = value

class Home:
    extends RefCounted
    var message := ""
    func present_operation_error(value: String) -> void:
        message = value

func _initialize() -> void:
    var failures := 0
    var lib := Library.new()
    var practice := Practice.new()
    var settings := Settings.new()
    var home := Home.new()
    var presenter = Presenter.new(lib,practice,settings,home)
    presenter.present("missing","library.open",false)
    if lib.open_status!="Cannot open score: missing" or \
            not lib.request_error.is_empty():
        failures += 1
    presenter.present("queue failed","practice.command",true)
    if lib.open_status!="Cannot open selected music: queue failed" or \
            not lib.request_error.is_empty():
        failures += 1
    presenter.present("device error","midi.device.select",false)
    if lib.request_error!="device error" or practice.message!="device error" or \
            settings.message!="device error" or home.message!="device error":
        failures += 1
    print("COMMAND_FAILURE_PRESENTER_FAILURES:",failures)
    quit(0 if failures==0 else 1)
