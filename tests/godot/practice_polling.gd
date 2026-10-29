extends SceneTree
class ScorePollSpy:
    extends RefCounted
    var model_calls := 0
    func poll(_now_ms: int) -> void:
        model_calls += 1

class App extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        _update_responsive_layout()
        set_process(false)
    func _request_library() -> void: pass
func _initialize() -> void: call_deferred("run")
func run() -> void:
    var app := App.new()
    root.add_child(app)
    await process_frame
    if OS.get_cmdline_user_args()[0] == "app_busy_ack":
        var values := {"loaded":true,"phase":"ready","can_increase_tempo":true}
        app.practice_view.present(values,true)
        app.practice_view.present_busy(true)
        app.action_pending = true
        app._on_action(0,503,PackedStringArray(),PackedByteArray())
        var cleared: bool = not app.practice_view.tempo_up_button.disabled
        if not cleared: print("PRACTICE_SCREEN_FAIL:HTTP acknowledgement must publish cleared busy state to Practice immediately")
        app.free()
        print("PRACTICE_SCREEN_FAILURES:",0 if cleared else 1)
        quit(0 if cleared else 1)
        return
    app.last_state = {"loaded":true,"revision":1,"piece_last_bar":80}
    # The score session owns model polling now. Spy on that owner, rather
    # than on the removed Main implementation of model requests.
    var score_poll := ScorePollSpy.new()
    app.score_session = score_poll
    app.state_pending = true
    app.practice_view.show_source_picker(app.last_state)
    app._poll()
    var blocked: bool = score_poll.model_calls == 0
    app.practice_view.cancel_source_picker()
    app._poll()
    var resumed: bool = score_poll.model_calls == 1
    if not blocked: print("PRACTICE_SCREEN_FAIL:Score model polling must wait for source selection")
    if not resumed: print("PRACTICE_SCREEN_FAIL:Closing source selection resumes ordinary model polling")
    app.free()
    print("PRACTICE_SCREEN_FAILURES:",0 if blocked and resumed else 1)
    quit(0 if blocked and resumed else 1)
