extends SceneTree

const Design := preload("res://practice_theme.gd")

# Desktop native capture with a backend-derived clock. Saves every frame and
# its projection, so motion can be inspected as video and measured separately.
class FixtureApp extends "native_production_fixture.gd":
    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        _update_responsive_layout()
        set_process(false)

func _initialize() -> void:
    run.call_deferred()

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var folder: String = args[0]
    var output: String = args[1]
    var checking: bool = args.has("--check")
    var failures := 0
    root.mode = Window.MODE_WINDOWED
    root.borderless = true
    root.size = Vector2i(1536, 960)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var error: String = app.load_native_fixture(folder)
    if not error.is_empty():
        push_error(error)
        quit(1)
        return
    await process_frame
    await process_frame
    var samples: Array = []
    for bpm in [40, 80, 120]:
        var initial_beat: float = -float(bpm)/60.0*.2 if checking else -1.0
        var state := {"revision":app.revision, "transport_id":bpm, "bpm":bpm,
            "loaded":true, "running":true, "paused":false, "phase":"count_in",
            "mode":"practice", "preview_only":true, "clock_beat":initial_beat,
            "play_from_beat":0.0, "duration_beats":app.practice_view.stage.renderer.timeline.duration_beats,
            "count_in_beats":1, "count_in_bar_beats":4}
        var clock = load(args[2] if args.size() > 2 else "res://visual_transport_clock.gd").new()
        clock.accept(state, 100000, 100000)
        var start_ms: int = Time.get_ticks_msec()
        # Four seconds at a fixed 30 Hz capture cadence, count-in included.
        for frame in range(12 if checking else 120):
            var elapsed: float = float(frame) / 30.0
            var at_ms: int = 100000 + roundi(elapsed * 1000.0)
            if frame % 5 == 0 and frame > 0:
                state.clock_beat = initial_beat + (elapsed + .065) * float(bpm) / 60.0
                clock.accept(state, at_ms, at_ms)
            var beat: float = clock.now(at_ms)
            # Use a frozen snapshot so the captured pixels represent exactly
            # the measured projection, independent of screenshot overhead.
            app.last_state = state.duplicate()
            app.last_state.clock_beat = beat
            app.last_state.paused = true
            app.last_state.phase = "playing" if beat >= 0 else "count_in"
            # Sample the production native compositor on every display frame.
            app._process(0.0)
            app.practice_view.stage.renderer.queue_redraw()
            await process_frame
            RenderingServer.force_draw()
            var pixels: Image = root.get_texture().get_image()
            if not checking:
                pixels.save_png(output + "/%d-%03d.png" % [bpm, frame])
            var pixel_scale := Vector2(pixels.get_size()) / root.get_visible_rect().size
            var expected_x: float = (app.practice_view.stage.renderer.global_position.x + app.practice_view.stage.renderer.size.x * .42) * pixel_scale.x
            var line_y: int = roundi(app.practice_view.stage.renderer.get_global_rect().get_center().y * pixel_scale.y)
            var line_x := -1
            var best := 1.0
            for x in range(maxi(0,roundi(expected_x)-35), mini(pixels.get_width(),roundi(expected_x)+36)):
                var color: Color = pixels.get_pixel(x,line_y)
                var distance: float = absf(color.r - Design.MINT.r) \
                    + absf(color.g - Design.MINT.g) + absf(color.b - Design.MINT.b)
                if distance < best:
                    best = distance
                    line_x = x
            samples.append({"bpm":bpm, "frame":frame, "seconds":elapsed,
                "beat":beat, "clock_beat":app.practice_view.stage.renderer.clock_beat,
                "noteheads":app.practice_view.stage.renderer.drawn_noteheads,
                "expected_line_x":expected_x, "rendered_line_x":line_x, "line_color_error":best,
                "width":pixels.get_width(), "height":pixels.get_height(),
                "pixel_scale":[pixel_scale.x, pixel_scale.y]})
            if best > .35 or absf(float(line_x) - expected_x) > 2.0:
                failures += 1
                print("PLAYHEAD_PIXEL_FAIL:", bpm, "/", frame, " line=", line_x, " expected=", expected_x, " color_error=", best)
            var wait_ms: int = start_ms + roundi(float(frame + 1) * 1000.0 / 30.0) - Time.get_ticks_msec()
            if wait_ms > 0:
                await create_timer(float(wait_ms) / 1000.0).timeout
    var file := FileAccess.open(output + "/motion.json", FileAccess.WRITE)
    file.store_string(JSON.stringify(samples))
    print("RECOVERY_CAPTURE_FRAMES:", samples.size())
    print("RECOVERY_PLAYHEAD_FAILURES:", failures)
    quit(1 if checking and failures > 0 else 0)
