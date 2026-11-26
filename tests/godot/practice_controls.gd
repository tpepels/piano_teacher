extends SceneTree
## Snapshot presentation only; MIDI/audio/physical layout need piano acceptance.
const Screen := preload("res://practice_screen.gd")
const StateInbox := preload("res://application_state_inbox.gd")
const Navigation := preload("res://navigation_session.gd")
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
    # Regression: repeated backend publications must not reintroduce a
    # software 60 FPS cap over the display's native refresh cadence.
    var previous_cap: int = Engine.max_fps
    var previous_sleep: bool = OS.low_processor_usage_mode
    var navigation := Navigation.new()
    navigation.update_frame_rate({})
    check(Engine.max_fps == 0 and not OS.low_processor_usage_mode,
        "Practice preparation uses display cadence")
    for phase in ["playing","count_in","guided_wait","paused"]:
        navigation.update_frame_rate(state("practice",phase))
        check(Engine.max_fps == 0 and not OS.low_processor_usage_mode,
            "Practice snapshot does not restore a software FPS cap: "+phase)
    navigation.current_screen = "settings"
    navigation.update_frame_rate({})
    check(Engine.max_fps == 30 and OS.low_processor_usage_mode,
        "Idle drawer may save power")
    navigation.current_screen = "calibration"
    navigation.update_frame_rate({"midi_calibration":{"active":true}})
    check(Engine.max_fps == 0 and not OS.low_processor_usage_mode,
        "Active timing calibration uses display cadence")
    navigation.current_screen = "practice"
    navigation.update_frame_rate({"loaded":true})
    check(Engine.max_fps == 0 and not OS.low_processor_usage_mode,
        "Returning to practice releases the drawer FPS cap")
    Engine.max_fps = previous_cap
    OS.low_processor_usage_mode = previous_sleep
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
