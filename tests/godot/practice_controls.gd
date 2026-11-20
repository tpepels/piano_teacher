extends SceneTree
## Snapshot presentation only; MIDI/audio/physical layout need piano acceptance.
const Screen := preload("res://practice_screen.gd")
const Policy := preload("res://practice_control_policy.gd")
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("PRACTICE_CONTROLS_FAIL: ",message)

func state(mode: String, phase: String) -> Dictionary:
    return {"loaded":true,"revision":1,"piece_fingerprint":"piece",
        "title":"Piece","mode":mode,"phase":phase,"hand":"right",
        "bpm":40,"target_bpm":80,"first_bar":2,"last_bar":3,
        "running":phase in ["playing","count_in"],"paused":phase == "paused",
        "device":"Piano","flow":{"status":"Measures 2–3 · Right hand · Free"},
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
    check(not view.practice_retry_button.visible and not view.practice_previous_button.visible
        and not view.practice_skip_button.visible,"Default flow progresses without manual lesson controls")
    check(view.flow_status_label.text.contains("2–3") and view.flow_status_label.text.contains("Right hand")
        and view.flow_status_label.text.contains("Free"),"Status identifies the complete window, hand and step")
    check(not view.stage.keyboard.visible,"Thinking in Free does not show a keyboard")
    free.teaching.hint_visible = true
    free.teaching.hint_reason = "waiting"
    view.present(free,true)
    check(not view.stage.keyboard.visible,"An elapsed-wait hint cannot reveal the Free keyboard")
    free.teaching.hint_reason = "wrong_note"
    view.present(free,true)
    check(view.stage.keyboard.visible,"A wrong note reveals the target keyboard hint")
    free.teaching.hint_visible = false
    view.present(free,true)
    check(not view.stage.keyboard.visible,"Correcting the target hides the hint")
    for mode in ["practice","listen"]:
        var playing := state(mode,"playing")
        playing.teaching.hint_visible = true
        playing.teaching.hint_reason = "wrong_note"
        view.present(playing,true)
        check(not view.stage.keyboard.visible,"The hint stays hidden outside Free: "+mode)
        check(view.start_button.text == "Pause" and Policy.primary(playing,true,"") == {"action":"pause"},
            "The same control pauses "+mode)
        check(view.listen_button.disabled == (mode == "listen"),"Listen again cannot compete with an active Listen")
        playing.paused = true
        playing.phase = "paused"
        view.present(playing,true)
        check(view.start_button.text == "Resume" and Policy.primary(playing,true,"") == {"action":"resume"},
            "The same control resumes "+mode)
    view.present(free,true)
    view.start_button.pressed.emit()
    view.listen_button.pressed.emit()
    view.present_metronome(false)
    check(actions == ["transport","listen"],"Presenting metronome preference sends no user command")
    view.metronome_switch.button_pressed = true
    check(actions == ["transport","listen",true],"Practice controls dispatch one intent per user action")
    check(Policy.listen_toggle(free) == {"action":"listen"},"Listen again requests the current passage")
    view.free()
    print("PRACTICE_CONTROLS_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
