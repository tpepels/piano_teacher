extends SceneTree
var failures: Array[String] = []
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("LESSON_FAIL:",message)
func context(fp: String = "song") -> Dictionary:
    return {"loaded":true,"piece_fingerprint":fp,"title":"A_real_song","lesson_step":2,
        "lesson_level":"original","clean_runs_required":4,"hand":"right","hands":["right","both"],
        "mode":"learn","phase":"guided_wait","skip_available":true,"placement_available":true}
func overview(fp: String = "song") -> Dictionary:
    return {"piece_fingerprint":fp,"current_step":2,"completed_steps":1,"total_steps":3,
        "steps":[{"number":1,"exercise":0,"first_bar":1,"last_bar":4,"hand":"right","level":"skeleton","completed":true},
        {"number":2,"exercise":0,"first_bar":1,"last_bar":4,"hand":"right","level":"original","skip_status":"skipped"},
        {"number":3,"exercise":1,"first_bar":5,"last_bar":8,"hand":"both","level":"original","kind":"perform"}],
        "trouble_spots":[{"stage_key":"source-unit","start_beat":8.0,"first_bar":3,"last_bar":4}]}
func press(view: Node, caption: String) -> void:
    for button in view.find_children("*","Button",true,false):
        if button.text == caption:
            button.pressed.emit()
            return
    check(false,"Missing action: " + caption)
func texts(node: Node) -> String:
    var result := str(node.text) if node is Label else ""
    for child in node.get_children(): result += " " + texts(child)
    return result
func test_screen(view: Control, scenario: String) -> void:
    var commands: Array = []
    var navigation: Array = []
    view.command_requested.connect(func(command: Dictionary): commands.append(command))
    view.practice_requested.connect(func(): navigation.append("practice"))
    view.advanced_requested.connect(func(): navigation.append("advanced"))
    view.present_context(context(),false)
    view.present_overview(overview())
    match scenario:
        "overview":
            check(view.piece_title.text == "A real song", "Lesson owns its selected piece title")
            check(view.summary.text == "1 of 3 stages completed · 4 clean performances at your target tempo", "Completion and mastery requirement remain explicit")
            check(view.stage_labels.skeleton.visible and not view.stage_labels.outline.visible and view.stage_labels.original.text == "2. Original", "Only actual levels in this hand/passage are numbered")
            check("skipped; not mastered" in texts(view.rows) and "Current passage" in texts(view.rows), "Skipped work never claims mastery")
            press(view,"Revisit bars 3–4")
            check(commands == [{"action":"revisit_trouble","stage_key":"source-unit","start_beat":8.0}], "Trouble rows capture source identity as values")
            var changed := overview()
            view.present_overview(changed)
            changed.trouble_spots[0].stage_key = "mutated"
            commands.clear()
            press(view,"Revisit bars 3–4")
            check(commands[0].stage_key == "source-unit", "Presentation has no mutable input backreference")
        "choices":
            check(view.mode_choice.selected == 0 and view.hints_toggle.visible, "Learning exposes hints")
            view.mode_choice.item_selected.emit(3)
            view.hints_toggle.toggled.emit(true)
            press(view,"Left hand")
            press(view,"Stop attempt")
            press(view,"Skip this step · no mastery")
            press(view,"Try original notes")
            press(view,"Advanced practice controls")
            check(commands == [{"action":"perform","scope":"whole"},{"action":"hints","enabled":true},
                {"action":"hand","hand":"left"},{"action":"stop"},
                {"action":"skip_stage","reason":"Learner chose to skip this step"},{"action":"place_original"}], "Choices emit complete commands without service callbacks")
            check(navigation == ["practice","advanced"], "Navigation stays explicit")
            check(view.hand_buttons.right.disabled and view.hand_buttons.left.disabled and not view.hand_buttons.both.disabled, "Current and unavailable hands are disabled")
            var warmup := context()
            warmup.mode = "listen"
            warmup.warmup = true
            view.present_context(warmup,false)
            check(not view.mode_choice.disabled and not view.mode_choice.is_item_disabled(1) and view.mode_choice.is_item_disabled(0) and view.mode_choice.is_item_disabled(2), "Warm-up Listen always permits return to Practice")
            check(view.mode_choice.text == "Listen" and not view.hints_toggle.visible, "Listen caption and hints policy remain intact")
        "reset":
            press(view,"Reset this song's lesson path…")
            check(view.reset_confirmation.visible and commands.is_empty(), "Reset requires a second deliberate click")
            view.present_context(context("other"),false)
            press(view,"Erase this song's progress")
            check(not view.reset_confirmation.visible and commands.is_empty(), "Changing music cancels the captured reset identity")
            view.present_context(context(),false)
            press(view,"Reset this song's lesson path…")
            view.present_busy(true)
            press(view,"Erase this song's progress")
            check(commands.is_empty(), "An in-flight command cannot drop a destructive reset")
            view.present_busy(false)
            press(view,"Reset this song's lesson path…")
            press(view,"Erase this song's progress")
            check(commands == [{"action":"reset_path","fingerprint":"song","confirm":true}], "Confirmed reset carries the captured song identity")
        "layout":
            for dimensions in [Vector2i(800,600),Vector2i(1280,800),Vector2i(1536,960)]:
                root.size = dimensions
                view.apply_viewport(Vector2(dimensions),1.0)
                for frame in range(6): await process_frame
                check(view.columns.vertical == (dimensions.x < 1280), "Lesson owns its responsive column breakpoint")
                check(view.columns.get_child(0) == (view.options if dimensions.x < 1280 else view.rows), "Compact path puts choices before progression")
                check(view.rows.size.y > 100 and view.get_combined_minimum_size().x <= dimensions.x, "All stages remain in one reachable outer scroll")
func test_selector(view: Control) -> void:
    var commands: Array = []
    view.step_requested.connect(func(number: int): commands.append(number))
    view.present_context(context(),false)
    check(view.picker.disabled, "Selector waits for matching lesson data")
    var values := overview()
    view.present_overview(values)
    values.steps.clear()
    check(view.picker.item_count == 3 and view.picker.text == "Step 2 / 3", "Captured popup rows have a bounded selected caption")
    check(view.picker.get_item_text(0) == "1/3 · 1–4 · Right · Skeleton", "Popup retains complete step descriptions")
    view.previous_button.pressed.emit()
    view.next_button.pressed.emit()
    view.picker.item_selected.emit(1)
    view.picker.item_selected.emit(2)
    check(commands == [1,3,3], "Arrows and direct picker emit only actual selection changes")
    view.present_busy(true)
    view.next_button.pressed.emit()
    check(commands == [1,3,3] and view.picker.disabled, "Busy selectors cannot lose queued user intent")
    view.present_context(context("other"),false)
    view.picker.item_selected.emit(0)
    check(view.picker.disabled and commands == [1,3,3], "Old-song rows cannot select a new-song step")
    view.present_context({"loaded":false},false)
    check(view.picker.item_count == 0, "Unload releases the captured step rows")
func test_session(model: RefCounted, scenario: String) -> void:
    var requests: Array = []
    var snapshots: Array = []
    var errors: Array = []
    model.request_requested.connect(func(): requests.append("GET /lesson"))
    model.overview_changed.connect(func(values: Dictionary): snapshots.append(values))
    model.request_failed.connect(func(message: String): errors.append(message))
    model.update_context(context(),10)
    model.ensure_current(11)
    check(requests.size() == 1 and model.pending, "The owner coalesces overview demand")
    match scenario:
        "cache":
            var values := overview()
            model.complete_response(values,"",20)
            values.steps.clear()
            model.ensure_current(21)
            check(requests.size() == 1 and not model.pending and model.snapshot().steps.size() == 3, "Successful responses are cached by piece and detached from inputs")
            var copy: Dictionary = model.snapshot()
            copy.steps.clear()
            check(model.snapshot().steps.size() == 3, "Consumers cannot mutate the owned cache")
        "retry":
            model.complete_response(null,"Engine unavailable",20)
            model.ensure_current(21)
            check(errors == ["Engine unavailable"] and requests.size() == 1 and not model.pending, "Failure is visible and retry does not spin at frame rate")
            model.ensure_current(1020)
            check(requests.size() == 2 and model.pending, "A failed overview retries for the same fingerprint after bounded backoff")
            model.complete_response([],"",1030)
            model.ensure_current(2030)
            check(requests.size() == 3, "Malformed responses cannot permanently poison the same-song cache")
            model.complete_response(overview(),"",2040)
            model.ensure_current(5000)
            check(requests.size() == 3 and model.snapshot().steps.size() == 3, "Recovery ends automatic retries")
        "stale_reset":
            model.update_context(context("other"),11)
            model.complete_response(overview(),"",20)
            check(requests.size() == 2 and model.pending and model.snapshot().is_empty(), "An old-song response is discarded and current-song demand proceeds")
            model.complete_response(overview("other"),"",21)
            model.refresh(22)
            model.invalidate()
            model.ensure_current(23)
            model.complete_response(overview("other"),"",24)
            check(requests.size() == 4 and model.pending and model.snapshot().is_empty(), "Reset invalidation discards an in-flight response even when the fingerprint is unchanged")
            var reset_values := overview("other")
            reset_values.completed_steps = 0
            model.complete_response(reset_values,"",25)
            check(model.snapshot().completed_steps == 0 and not model.pending, "Only the post-reset overview repopulates the cache")
func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    var scenario := OS.get_cmdline_user_args()[0]
    var path := "res://lesson_screen.gd"
    if scenario == "selector": path = "res://practice_step_selector.gd"
    elif scenario in ["cache","retry","stale_reset"]: path = "res://lesson_session.gd"
    if not ResourceLoader.exists(path):
        check(false,"Independent Lesson owner is not implemented: " + path)
    elif scenario in ["cache","retry","stale_reset"]:
        test_session(load(path).new(),scenario)
    else:
        var view = load(path).new()
        view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(view)
        await process_frame
        if scenario == "selector": test_selector(view)
        else: await test_screen(view,scenario)
        view.free()
    print("LESSON_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
