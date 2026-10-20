extends SceneTree
# Exercise the unmodified application scene, HTTP downloads and real transport.
var app: Control

func _initialize() -> void:
    call_deferred("run")

func wait_for(predicate: Callable, label: String) -> bool:
    var deadline := Time.get_ticks_msec() + 60000
    while not predicate.call():
        if Time.get_ticks_msec() > deadline:
            push_error("Native application timed out: " + label)
            return false
        await process_frame
    return true

func run() -> void:
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1":
        quit(1)
        return
    var folder: String = OS.get_cmdline_user_args()[0]
    app = load("res://main.gd").new()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    app._navigate("practice")
    var ready: bool = await wait_for(func() -> bool:
        return app.native_notation_enabled and app.timeline_preview != null and \
            app.timeline_preview.native_ready and app.timeline_preview.is_visible_in_tree() and \
            app.timeline_model_revision == app.revision and app.rendered_revision == app.revision,
        "actual native compositor ready")
    if not ready:
        quit(1)
        return
    app._send_action({"action":"start"})
    ready = await wait_for(func() -> bool:
        return str(app.last_state.get("phase","")) == "playing", "playing")
    if not ready:
        quit(1)
        return
    var renderer = app.timeline_preview
    var density: float = renderer.timeline.pixels_per_beat
    var first_clock: float = renderer.clock_beat
    var first_x: float = renderer.timeline.screen_x(1, first_clock, 500, 0)
    var linear := true
    var samples := 0
    var drawn := 0
    for index in range(3):
        ready = await wait_for(func() -> bool:
            return renderer.clock_beat >= first_clock + float(index + 1) * .25,
            "native musical clock advances")
        if not ready:
            quit(1)
            return
        var clock: float = renderer.clock_beat
        var x: float = renderer.timeline.screen_x(1, clock, 500, 0)
        linear = linear and absf((first_x - x) - (clock - first_clock) * density) < .001
        linear = linear and renderer.timeline.pixels_per_beat == density
        drawn = maxi(drawn, renderer.drawn_noteheads.size())
        samples += 1
    if DisplayServer.get_name() != "headless":
        await RenderingServer.frame_post_draw
        root.get_texture().get_image().save_png(folder.path_join("native-application.png"))
    var report := {"native_ready":renderer.native_ready,
        "visible":renderer.is_visible_in_tree(), "drawn_noteheads":drawn,
        "clock_samples":samples, "linear_timeline":linear,
        "pixels_per_beat":density, "first_bar":renderer.timeline.model.get("first_bar"),
        "play_from_beat":renderer.play_from_beat,
        "revision":app.revision}
    var file := FileAccess.open(folder.path_join("native-application.json"), FileAccess.WRITE)
    file.store_string(JSON.stringify(report))
    file.close()
    print("NATIVE_APPLICATION_ACTIVE:", JSON.stringify(report))
    quit(0 if renderer.native_ready and drawn > 0 and linear else 1)
