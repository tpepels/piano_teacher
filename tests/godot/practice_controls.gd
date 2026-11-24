extends SceneTree
## Snapshot presentation only; MIDI/audio/physical layout need piano acceptance.
const Screen := preload("res://practice_screen.gd")
const Lessons := preload("res://lesson_session.gd")
const StateInbox := preload("res://application_state_inbox.gd")
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("PRACTICE_CONTROLS_FAIL: ",message)

func state(mode: String, phase: String) -> Dictionary:
    # A presentation fixture supplies the state contract published by Python.
    # It cannot invoke a duplicate Godot application policy.
    var paused := phase == "paused"
    var available_listen := mode != "listen"
    var controls := {
        "flow_active":true,"transport_active":true,
        "primary":{"action":"resume" if paused else "pause",
            "label":"Resume" if paused else "Pause",
            "enabled":true,"requires_score":false},
        "listen":{"action":"listen" if available_listen else "",
            "enabled":available_listen,"label":"Listen again"},
        "retry":{"enabled":false,"visible":false,"requires_score":true},
        "previous":{"enabled":false,"visible":false},
        "skip":{"enabled":false,"visible":false},
        "tempo_up":{"enabled":false},"tempo_down":{"enabled":false},
    }
    return {"loaded":true,"controls":controls,"revision":1,"piece_fingerprint":"piece",
        "title":"Piece","mode":mode,"phase":phase,"hand":"right",
        "bpm":40,"target_bpm":80,"first_bar":2,"last_bar":3,
        "running":phase in ["playing","count_in"],"paused":phase == "paused",
        "device":"Piano","flow":{"status":"Measures 2–3 · Right hand · Free"},
        "screen":{"status":"Measures 2–3 · Right hand · Free","notice":"","keyboard":"hidden"},
        "teaching":{"expected_notes":[{"pitch":60}],"hint_visible":false}}

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    root.size = Vector2i(1024,768)
    var view := Screen.new()
    root.add_child(view)
    await process_frame
    var actions: Array = []
    view.play_requested.connect(func(): actions.append("transport"))
    view.listen_requested.connect(func(): actions.append("listen"))
    view.metronome_toggled.connect(func(on: bool): actions.append(on))
    check(view.metronome_switch.button_pressed,"Metronome starts on")
    var free := state("learn","guided_wait")
    view.present(free,true)
    check(view.start_button.visible and view.start_button.text == "Pause"
        and view.listen_button.visible and view.listen_button.text == "Listen again"
        and view.metronome_switch.visible,"Free exposes the normal practice controls")
    check(not view.practice_retry_button.visible,
        "Default flow progresses without manual lesson controls")
    check(view.flow_status_label.text.contains("2–3") and view.flow_status_label.text.contains("Right hand")
        and view.flow_status_label.text.contains("Free"),"Status identifies the complete window, hand and step")
    check(not view.stage.keyboard.visible,"Thinking in Free does not show a keyboard")
    # Python decides when the hint shows (screen_projection.keyboard).
    free.screen.keyboard = "hint"
    view.present(free,true)
    check(view.stage.keyboard.visible,"A wrong note reveals the target keyboard hint")
    free.screen.keyboard = "hidden"
    view.present(free,true)
    check(not view.stage.keyboard.visible,"Correcting the target hides the hint")
    free.screen.notice = "Connect your MIDI piano to play in tempo."
    view.present(free,true)
    check(view.stage.practice_playback_banner.visible
        and view.stage.practice_playback_banner.text == free.screen.notice,
        "A projected problem notice is shown on the score banner")
    free.screen.notice = ""
    view.present(free,true)
    check(not view.stage.practice_playback_banner.visible,"No notice, no banner")
    for mode in ["practice","listen"]:
        var playing := state(mode,"playing")
        view.present(playing,true)
        check(not view.stage.keyboard.visible,"The hint stays hidden outside Free: "+mode)
        check(view.start_button.text == "Pause" and playing.controls.primary.action == "pause",
            "The same control pauses "+mode)
        check(view.listen_button.disabled == (mode == "listen"),"Listen again cannot compete with an active Listen")
        playing.paused = true
        playing.phase = "paused"
        playing.controls.primary.action = "resume"
        playing.controls.primary.label = "Resume"
        view.present(playing,true)
        check(view.start_button.text == "Resume" and playing.controls.primary.action == "resume",
            "The same control resumes "+mode)
    view.present(free,true)
    view.start_button.pressed.emit()
    view.listen_button.pressed.emit()
    view.present_metronome(false)
    check(actions == ["transport","listen"],"Presenting metronome preference sends no user command")
    view.metronome_switch.button_pressed = true
    check(actions == ["transport","listen",true],"Practice controls dispatch one intent per user action")
    check(free.controls.listen.action == "listen","Listen again is a published action")
    # The real LessonSession caches the backend's course overview, but
    # a graded mastery result may unlock a new stage with the same piece.
    # No new user command is required to refresh that read-only overview.
    var lesson_cache := Lessons.new()
    var selected := {"loaded":true,"piece_fingerprint":"warmup",
        "lesson_step":1,"lesson_steps_mastered":0,"revision":1}
    lesson_cache.update_context(selected,0)
    lesson_cache.complete_response({"piece_fingerprint":"warmup",
        "steps":[{"number":1,"available":true},
                 {"number":2,"available":false}]}, "",1)
    check(not lesson_cache.pending and lesson_cache.snapshot()["steps"][1]["available"] == false,
        "Lesson Path initially displays the backend's locked next stage")
    selected["lesson_step"] = 2
    selected["lesson_steps_mastered"] = 1
    selected["revision"] = 2
    lesson_cache.update_context(selected,2)
    check(lesson_cache.pending and lesson_cache.snapshot().is_empty(),
        "Earned mastery invalidates an obsolete Lesson Path selection snapshot")
    lesson_cache.complete_response({"piece_fingerprint":"warmup",
        "steps":[{"number":1,"available":true},
                 {"number":2,"available":true}]}, "",3)
    check(not lesson_cache.pending and lesson_cache.snapshot()["steps"][1]["available"] == true,
        "Newly unlocked warm-up step is available without reopening the piece")
    # A corrupt successful snapshot must not leave old commands active;
    # stale polls are discarded independently by the ordered-state gate.
    var inbox := StateInbox.new()
    check(inbox.accept(0,PackedByteArray(),0,0,-1).has("contract_error"),
        "Empty backend state must fail closed")
    check(inbox.accept(0,"[]".to_utf8_buffer(),0,0,-1).has("contract_error"),
        "Non-object backend state must fail closed")
    check(inbox.accept(0,"{}".to_utf8_buffer(),0,0,-1).has("state"),
        "JSON-object backend state still reaches schema validation")
    view.free()
    print("PRACTICE_CONTROLS_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
