extends RefCounted
## Present failed command results to their affected screens. Request ordering,
## pending operations, and transport actions remain owned by Main.
var library_view
var practice_view
var settings_view
var home_view
var sight_reading_view

func _init(library, practice, settings, home, reading = null) -> void:
    library_view = library
    practice_view = practice
    settings_view = settings
    home_view = home
    sight_reading_view = reading

func present(message: String, path: String, queued_library_failed: bool) -> void:
    if path == "sight_reading.start" and sight_reading_view != null:
        sight_reading_view.present_message(message)
        return
    if path == "library.open":
        library_view.present_open_status("Cannot open score: " + message, true)
    elif queued_library_failed:
        library_view.present_open_status(
            "Cannot open selected music: " + message, true)
    practice_view.present_message(message)
    settings_view.present_message(message)
    if path != "library.open" and not queued_library_failed:
        library_view.present_request_error(message)
    home_view.present_operation_error(message)
