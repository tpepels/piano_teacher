extends RefCounted
## Accepted command view effects only. Never owns request callbacks, transport
## sequencing, lesson selection, or screen navigation.
var library_view
var practice_view
var settings_view

func _init(library, practice, settings) -> void:
    library_view = library
    practice_view = practice
    settings_view = settings

func present_accepted(decision: Dictionary) -> void:
    match str(decision.get("kind", "")):
        "library_open":
            library_view.present_open_status("")
        "settings":
            settings_view.present_message("Settings saved")

func present_source_picker(opened: Dictionary) -> void:
    practice_view.show_source_picker(opened)


func present_resume_choice(opened: Dictionary, allow_measure: bool) -> void:
    practice_view.show_resume_prompt(opened, allow_measure)

func present_import_warnings(opened: Variant) -> void:
    if not opened is Dictionary:
        return
    var messages := PackedStringArray(opened.get("import_warnings", []))
    var fingering: Variant = opened.get("fingering")
    if fingering is Dictionary and not str(fingering.get("error", "")).is_empty():
        messages.append(str(fingering["error"]))
    if not messages.is_empty():
        practice_view.present_import_warnings("\n".join(messages))
