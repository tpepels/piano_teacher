extends SceneTree

# Exercise production layout and resize hooks without creating HTTP requests,
# MIDI devices or musical transport. The Window owns all screen-space scaling.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        if has_method("_configure_ui_scaling"):
            call("_configure_ui_scaling")
        resized.connect(_update_responsive_layout)
        if not get_window().size_changed.is_connected(_update_responsive_layout):
            get_window().size_changed.connect(_update_responsive_layout)
        _update_responsive_layout()
        _navigate("practice")
        set_process(false)

    func _request_library() -> void:
        pass

    func _request_devices() -> void:
        pass

    func _request_settings() -> void:
        pass

    func _request_lesson() -> void:
        pass

var failures: Array[String] = []
var samples: Array = []
var baseline: Dictionary = {}
var seen: Dictionary = {}
var output := ""

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("UI_SCALING_FAIL:", message)

func settle() -> void:
    # Allow deferred Container minimum sizes and Window/Control resize signals
    # to reach their final state before comparing physical dimensions.
    for frame in range(5):
        await process_frame

func screen_transform(control: Control) -> Transform2D:
    # get_screen_transform() is identity in the headless display server.
    # The final root transform includes actual Window content scaling there.
    return root.get_final_transform() * control.get_global_transform_with_canvas()

func screen_rect(control: Control) -> Rect2:
    return screen_transform(control) * Rect2(Vector2.ZERO, control.size)

func screen_font(control: Control) -> float:
    return float(control.get_theme_font_size("font_size")) * screen_transform(control).y.length()

func in_screen(control: Control, dimensions: Vector2i) -> bool:
    var rectangle := screen_rect(control)
    return rectangle.position.x >= -2 and rectangle.position.y >= -2 \
        and rectangle.end.x <= dimensions.x + 2 and rectangle.end.y <= dimensions.y + 2

func window_scale(window: Window) -> float:
    var factor: float = window.get_final_transform().y.length()
    if window != root and window.is_embedded():
        factor *= root.get_final_transform().y.length()
    return factor

func window_size(window: Window) -> Vector2:
    return Vector2(window.size) * (root.get_final_transform().y.length() if window.is_embedded() else 1.0)

func measure(app: Control, dimensions: Vector2i) -> Dictionary:
    app._navigate("practice")
    await settle()
    var result := {
        "transport_width": screen_rect(app.start_button).size.x,
        "transport_height": screen_rect(app.start_button).size.y,
        "transport_font": screen_font(app.start_button),
        "navigation_height": screen_rect(app.practice_music_button).size.y,
        "navigation_font": screen_font(app.practice_music_button),
        "input_lamp_width": screen_rect(app.game_input_indicator).size.x,
        "input_lamp_height": screen_rect(app.game_input_indicator).size.y,
        # The custom lamp paints at FONT_SIZE=13 rather than theme font size.
        "input_lamp_font": 13.0 * screen_transform(app.game_input_indicator).y.length(),
    }
    for button in [app.start_button, app.practice_retry_button, app.listen_button,
            app.practice_music_button, app.practice_settings_button]:
        check(in_screen(button, dimensions), "%s: practice action fits: %s" % [dimensions, button.text])
    app._navigate("library")
    await settle()
    var library_button: Control = app.screen_navigation["library"]
    result["sidebar_width"] = screen_rect(app.navigation_rail).size.x
    result["sidebar_button_height"] = screen_rect(library_button).size.y
    result["sidebar_font"] = screen_font(library_button)
    result["search_height"] = screen_rect(app.library_view.library_search).size.y
    result["search_font"] = screen_font(app.library_view.library_search)
    for button in app.screen_navigation.values():
        check(in_screen(button, dimensions), "%s: sidebar action fits: %s" % [dimensions, button.text])
    check(in_screen(app.library_view.library_search, dimensions), "%s: library search fits" % dimensions)
    app._navigate("settings")
    await settle()
    result["settings_button_height"] = screen_rect(app.settings_view.device_button).size.y
    result["settings_font"] = screen_font(app.settings_view.device_button)
    check(in_screen(app.settings_view.device_button, dimensions), "%s: MIDI device control fits" % dimensions)

    app.pause_sheet.present({"paused":true, "mode":"practice", "bpm":80,
        "hand":"right", "hands":["right", "left", "both"], "first_bar":1, "last_bar":4})
    await settle()
    result["pause_width"] = screen_rect(app.pause_sheet.modal_panel).size.x
    result["pause_height"] = screen_rect(app.pause_sheet.modal_panel).size.y
    result["pause_font"] = screen_font(app.pause_sheet.resume_button)
    check(in_screen(app.pause_sheet.modal_panel, dimensions), "%s: pause modal fits" % dimensions)
    check(in_screen(app.pause_sheet.resume_button, dimensions), "%s: pause Resume action fits" % dimensions)
    app.pause_sheet.present({})

    # AcceptDialog/PopupMenu are Windows, unlike the Control-based pause sheet.
    # Embedded windows inherit the parent's final transform; native windows
    # must provide their own content scale and appropriately sized surface.
    app.review_sheet.open_review({"accuracy_percent":75, "correct":3, "total":4,
        "missed":1, "sections":[]})
    await settle()
    result["review_width"] = window_size(app.review_sheet).x
    result["review_height"] = window_size(app.review_sheet).y
    result["review_font"] = float(app.review_sheet.summary_label.get_theme_font_size("font_size")) \
        * window_scale(app.review_sheet)
    check(window_size(app.review_sheet).x <= dimensions.x + 2 \
        and window_size(app.review_sheet).y <= dimensions.y + 2, "%s: review dialog fits" % dimensions)
    app.review_sheet.hide()
    app.settings_view.present_devices(["Digital Piano (MIDI)"], "", true)
    await settle()
    result["device_menu_font"] = float(app.settings_view.device_menu.get_theme_font_size("font_size")) * window_scale(app.settings_view.device_menu)
    result["device_menu_height"] = window_size(app.settings_view.device_menu).y
    app.settings_view.device_menu.hide()
    return result

func run() -> void:
    var args := OS.get_cmdline_user_args()
    if not args.is_empty():
        output = str(args[0])
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1280, 800)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await settle()
    # Repeated sizes catch cumulative metric multiplication and stale resize
    # factors in both directions; 16:9 also checks proportional aspect fitting.
    for dimensions in [Vector2i(1280,800), Vector2i(2560,1600), Vector2i(3840,2400),
            Vector2i(3840,2160), Vector2i(800,600), Vector2i(1280,800),
            Vector2i(3840,2400), Vector2i(1280,800)]:
        root.size = dimensions
        await settle()
        var factor: float = maxf(1.0, minf(float(dimensions.x)/1280.0, float(dimensions.y)/800.0))
        check(absf(root.get_final_transform().y.length()-factor) < .001,
            "%s: one proportional Window factor %.3f" % [dimensions, factor])
        check(absf(float(app.ui_scale)-1.0) < .001,
            "%s: logical UI metrics remain 1x" % dimensions)
        var metrics: Dictionary = await measure(app, dimensions)
        var key := str(dimensions)
        if baseline.is_empty():
            baseline = metrics.duplicate(true)
        if dimensions.x >= 1280:
            for metric in baseline:
                var expected: float = float(baseline[metric]) * factor
                check(absf(float(metrics[metric])-expected) <= maxf(2.0, expected*.015),
                    "%s: %s grows once (%.2f vs %.2f)" % [dimensions, metric, float(metrics[metric]), expected])
        if seen.has(key):
            for metric in metrics:
                check(absf(float(metrics[metric])-float(seen[key][metric])) <= 1.0,
                    "%s: %s is idempotent after resizing" % [dimensions, metric])
        seen[key] = metrics.duplicate(true)
        samples.append({"window":[dimensions.x,dimensions.y], "factor":factor, "metrics":metrics})
        if not output.is_empty() and DisplayServer.get_name() != "headless":
            app._navigate("settings")
            await settle()
            RenderingServer.force_draw()
            root.get_texture().get_image().save_png(output.path_join("ui-%dx%d.png" % [dimensions.x,dimensions.y]))
    if not output.is_empty():
        var file := FileAccess.open(output.path_join("ui-scaling.json"), FileAccess.WRITE)
        file.store_string(JSON.stringify({"samples":samples, "failures":failures}, "  "))
    print("UI_SCALING_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
