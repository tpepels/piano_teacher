extends SceneTree

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _request_library() -> void:
        pass
    func _request_settings() -> void:
        pass
    func _request_devices() -> void:
        pass
    func _request_lesson() -> void:
        pass

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("FAIL: ", message)

func _initialize() -> void:
    run.call_deferred()

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var dimensions := args[0].split("x")
    root.mode = Window.MODE_WINDOWED
    root.borderless = true
    root.size = Vector2i(int(dimensions[0]), int(dimensions[1]))
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    app.library_view.present_catalog({"pieces": [], "warmups": [
        {"id":"warmup:chords", "title":"Chord Changes", "description":"Beginner triads", "bpm":68},
        {"id":"warmup:finger-patterns", "title":"Five-Finger Ladders", "description":"Parallel finger motion", "bpm":70}]})
    for stage in range(12):
        var row := Button.new()
        row.text = "Lesson %d · Practice this passage" % (stage + 1)
        row.custom_minimum_size.y = 54
        app.lesson_rows.add_child(row)
    for page in ["library", "lesson", "settings", "library", "lesson"]:
        app._navigate(page)
        # Containers and minimum-size invalidation settle on deferred frames.
        for frame in range(8):
            await process_frame
        app.overlay_drawer.modulate.a = 1.0
        var drawer: Rect2 = app.overlay_drawer.get_global_rect()
        print("DRAWER:", page, " ", drawer)
        check(drawer.position.x >= -1 and drawer.end.x <= root.get_visible_rect().size.x + 1,
            page + " drawer fits the window")
        var content: Control = app.screens[page]
        var clip: Rect2 = content.get_global_rect()
        check(clip.position.x >= drawer.position.x - 1 and clip.end.x <= drawer.end.x + 1,
            page + " content fits its clipping panel")
        for field in content.find_children("*", "Control", true, false):
            if not field.is_visible_in_tree() or field.size.x <= 0:
                continue
            if field is Button or field is LineEdit or field is OptionButton:
                var rect: Rect2 = field.get_global_rect()
                check(rect.position.x >= drawer.position.x - 1 and rect.end.x <= drawer.end.x + 1,
                    "%s action fits drawer: %s %s" % [page, field.name, rect])
        if page == "library":
            check(app.library_view.library_scroll.size.y >= 130,
                "Library leaves a usable visible list, got %.1fpx" % app.library_view.library_scroll.size.y)
        if page == "lesson":
            # The nested lesson list must have a usable viewport, including
            # when there are enough stages to require scrolling.
            check(app.lesson_rows.get_parent().size.y >= 100,
                "Lesson stages have a visible scroll area, got %.1fpx" % app.lesson_rows.get_parent().size.y)
            var outer := app.lesson_rows.get_parent().get_parent() as ScrollContainer
            if outer != null:
                var final_row: Control = app.lesson_rows.get_child(app.lesson_rows.get_child_count()-1)
                outer.ensure_control_visible(final_row)
                await process_frame
                await process_frame
                check(outer.get_global_rect().encloses(final_row.get_global_rect()),
                    "Last lesson can be scrolled fully into view")
                outer.scroll_vertical = 0
                await process_frame
        if args.size() > 1 and DisplayServer.get_name() != "headless":
            RenderingServer.force_draw()
            root.get_texture().get_image().save_png(args[1] + "/" + args[0] + "-" + page + ".png")
    app._show_open_picker({"title":"Imported MIDI", "piece_last_bar":77, "selected_start_bar":1})
    for frame in range(8):
        await process_frame
    check(app.open_picker.panel.get_global_rect().position.x >= 0 and app.open_picker.panel.get_global_rect().end.x <= root.get_visible_rect().size.x,
        "Starting point fits horizontally")
    if args.size() > 1 and DisplayServer.get_name() != "headless":
        RenderingServer.force_draw()
        root.get_texture().get_image().save_png(args[1] + "/" + args[0] + "-picker.png")
    print("RECOVERY_LAYOUT_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
