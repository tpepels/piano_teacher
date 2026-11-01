extends RefCounted
## Accepted command view effects only. Never owns request callbacks, transport
## sequencing, lesson selection, or screen navigation.
var library_view
var practice_view
var settings_view
var lesson_session

func _init(library, practice, settings, lesson) -> void:
    library_view = library
    practice_view = practice
    settings_view = settings
    lesson_session = lesson

func present_accepted(decision: Dictionary) -> void:
    if bool(decision.get("invalidate_lesson", false)):
        lesson_session.invalidate()
    match str(decision.get("kind", "")):
        "library_open":
            library_view.present_open_status("")
        "settings":
            settings_view.present_message("Settings saved")

func present_source_picker(opened: Dictionary) -> void:
    practice_view.show_source_picker(opened)
