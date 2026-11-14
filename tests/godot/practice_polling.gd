extends SceneTree
class ScorePollSpy:
    extends RefCounted
    var model_calls := 0
    func poll(_now_ms: int) -> void:
        model_calls += 1

# Only the count-in side effects needed by command acknowledgement.
# All request state and busy ownership stay in the production coordinator.
class CountInSpy:
    extends RefCounted
    var cancellations := 0
    var acknowledgements := 0
    func cancel_reserved_count_in() -> void:
        cancellations += 1
    func acknowledge_reserved_count_in(_now_ms: int) -> void:
        acknowledgements += 1

class App extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        command_failure_presenter = CommandFailurePresenter.new(
            library_view,practice_view,settings_view,home_view)
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
        var count_in := CountInSpy.new()
        app.command_coordinator.configure(app.practice_view,app.settings_view,
            count_in,app.score_flow,app.visual_transport_clock,null,
            app.command_failure_presenter)
        var failures := 0
        # The production acknowledgement path must unlock Practice for
        # both a successful command and a failed worker response.
        for code in [OK, 1]:
            app.practice_view.present_busy(true)
            var locked: bool = app.practice_view.tempo_up_button.disabled
            var owner = app.command_coordinator.state
            var started: bool = owner.action_requested("tempo_up") and                 owner.begin("practice.command",Time.get_ticks_msec())
            app.command_coordinator.request_token += 1
            app._on_action(code,PackedByteArray())
            var cleared: bool = not app.practice_view.tempo_up_button.disabled                 and not owner.pending and owner.control_action.is_empty()
            if not locked or not started or not cleared:
                failures += 1
                print("PRACTICE_SCREEN_FAIL:Worker acknowledgement must clear Practice busy state, status=",code)
        if count_in.acknowledgements != 1 or count_in.cancellations != 1:
            failures += 1
            print("PRACTICE_SCREEN_FAIL:Count-in cleanup must match success and failure")
        app.free()
        print("PRACTICE_SCREEN_FAILURES:",failures)
        quit(0 if failures == 0 else 1)
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
