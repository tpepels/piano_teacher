extends RefCounted
## Present an already accepted backend snapshot. No application root, HTTP
## request lifecycle, musical clock, or transport mutation is available here.
## All visual collaborators are injected once.

var practice_view
var settings_view
var lesson_view
var last_smoke_phase := ""

func _init(practice, settings, lesson) -> void:
    practice_view = practice
    settings_view = settings
    lesson_view = lesson

func present(parsed: Dictionary, screen: String, busy: bool,
        score_ready: bool, audio_error: bool,
        smoke: bool) -> void:
    settings_view.present_midi_key_range(
        parsed.get("midi_key_range",{}) if parsed.get("midi_key_range") is Dictionary else {})
    lesson_view.present_context(parsed,busy)
    settings_view.present_calibration(
        parsed.get("midi_calibration",{}),int(parsed.get("midi_offset_ms",0)))

    settings_view.present_practice(parsed,screen == "settings")
    practice_view.present(parsed,score_ready,busy,audio_error)

    if not bool(parsed.get("loaded",false)):
        return
    var phase: String = str(parsed.get("phase","ready"))
    if smoke and phase != last_smoke_phase:
        last_smoke_phase = phase
        print("PHASE0_PHASE:",phase)
