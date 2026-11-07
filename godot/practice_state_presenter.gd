extends RefCounted
## Present an already accepted backend snapshot. No application root, HTTP
## request lifecycle, musical clock, or transport mutation is available here.
## All visual collaborators are injected once.

var practice_view
var settings_view
var lesson_view
var lesson_session
var poll_timer: Timer
var last_smoke_phase := ""

func _init(practice, settings, lesson, session, timer: Timer) -> void:
    practice_view = practice
    settings_view = settings
    lesson_view = lesson
    lesson_session = session
    poll_timer = timer

func present(parsed: Dictionary, screen: String, busy: bool,
        score_ready: bool, fingering_error: String, audio_error: bool,
        sampled_state: bool, now_ms: int, smoke: bool) -> void:
    var placement_issues := 0
    if score_ready:
        placement_issues = practice_view.stage.renderer.annotations.fingering_placement_issues.size()
    practice_view.stage.present_fingering(
        parsed.get("fingering",{}),placement_issues,fingering_error)
    lesson_view.present_context(parsed,busy)
    settings_view.present_calibration(
        parsed.get("midi_calibration",{}),int(parsed.get("midi_offset_ms",0)))
    lesson_session.update_context(parsed,now_ms)

    if poll_timer != null:
        var live_rate: bool = screen == "practice" and \
            not str(parsed.get("device","")).is_empty()
        var interval := .08 if live_rate else .15
        if absf(poll_timer.wait_time-interval)>.001:
            poll_timer.wait_time = interval
    settings_view.present_practice(parsed,screen == "settings")
    practice_view.present(parsed,score_ready,busy,audio_error)

    if not bool(parsed.get("loaded",false)):
        return
    var phase: String = str(parsed.get("phase","ready"))
    if smoke and phase != last_smoke_phase:
        last_smoke_phase = phase
        print("PHASE0_PHASE:",phase)
    practice_view.present_busy(busy)
    practice_view.consider_piano_start(sampled_state,screen == "practice")
