extends SceneTree
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("HOME_SCREEN_FAIL:", message)

func listing() -> Dictionary:
    return {"count":2,"last_piece":"Collection/A_Real_Piece.mid", "pieces":[
        {"id":"Collection/A_Real_Piece.mid","title":"Metadata title","folder":"Collection"},
        {"id":"other.mid","title":"Other song"}],
        "warmups":[{"id":"warmup:chords","title":"Chord Changes"}]}

func catalog(view: Control) -> void:
    view.present_catalog(listing())
    check(view.count_label.text == "2 scores · 1 built-in warm-ups", "Home presents the backend personal count and warm-up count")
    check(view.recent_label.text == "A Real Piece" and not view.resume_button.disabled,
        "Personal recent music retains its filename-derived caption and valid Continue action")
    check(view.recent_label.clip_text and view.recent_label.text_overrun_behavior == TextServer.OVERRUN_TRIM_ELLIPSIS,
        "Long recent captions cannot widen navigation")

func recent_identity(view: Control) -> void:
    var requests: Array = []
    view.open_requested.connect(func(identifier: String, resume_saved: bool): requests.append([identifier,resume_saved]))
    var values := listing()
    view.present_catalog(values)
    values.pieces.clear()
    values.last_piece = "changed.mid"
    view.resume_button.pressed.emit()
    check(requests == [["Collection/A_Real_Piece.mid",true]], "Continue emits the captured valid identifier and saved-place intent")
    requests.clear()
    values = listing()
    values.last_piece = "missing.mid"
    view.present_catalog(values)
    view.resume_button.pressed.emit()
    check(view.resume_button.disabled and requests.is_empty(), "A missing last piece cannot advertise or open a broken Continue target")
    values.last_piece = "warmup:chords"
    view.present_catalog(values)
    view.resume_button.pressed.emit()
    check(view.recent_label.text == "Chord Changes" and requests == [["warmup:chords",true]],
        "Recent warm-ups use the catalog title and actual built-in identifier")
    view.present_catalog({"count":0,"pieces":[],"warmups":[]})
    check(view.recent_label.text == "No recent piece" and view.resume_button.disabled, "An empty catalog has no resume target")

func signals(view: Control) -> void:
    var intent: Array = []
    view.library_requested.connect(func(): intent.append("library"))
    view.settings_requested.connect(func(): intent.append("settings"))
    view.exit_requested.connect(func(): intent.append("exit"))
    for caption in ["Browse library  →","Settings","Quit"]:
        var matched := false
        for node in view.find_children("*","Button",true,false):
            if node.text == caption:
                node.pressed.emit()
                matched = true
                break
        check(matched,"Home includes its existing action: " + caption)
    check(intent == ["library","settings","exit"], "Home emits intent without a navigation/service callback")

func errors(view: Control) -> void:
    view.present_catalog(listing())
    view.present_catalog_unavailable()
    check(view.count_label.text == "Practice engine unavailable" and view.resume_button.disabled,
        "A failed library request disables the existing Continue action")
    view.present_operation_error("Pause rejected")
    check(view.recent_label.text == "Pause rejected", "Application failures remain visible in the recent-piece slot")
    view.present_catalog(listing())
    check(view.recent_label.text == "A Real Piece" and not view.resume_button.disabled,
        "A successful catalog response replaces the error with captured recent music")

func layout(view: Control) -> void:
    view.present_catalog(listing())
    for dimensions in [Vector2i(800,600),Vector2i(1280,800),Vector2i(1536,960)]:
        root.size = dimensions
        view.apply_viewport(Vector2(dimensions),1.0)
        for frame in range(6):
            await process_frame
        check(view.cards.vertical == (dimensions.x < 1380), "Home owns its existing stacked-card breakpoint")
        for action in view.find_children("*","Button",true,false):
            var rect: Rect2 = action.get_global_rect()
            check(rect.position.x >= -1 and rect.end.x <= dimensions.x+1,
                "Home actions fit the viewport without clipped labels: " + str(dimensions))

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    if not ResourceLoader.exists("res://home_screen.gd"):
        check(false,"Independent Home screen is not implemented")
    else:
        var view = load("res://home_screen.gd").new()
        view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(view)
        await process_frame
        match OS.get_cmdline_user_args()[0]:
            "catalog": catalog(view)
            "recent_identity": recent_identity(view)
            "signals": signals(view)
            "errors": errors(view)
            "layout": await layout(view)
        view.free()
    print("HOME_SCREEN_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
