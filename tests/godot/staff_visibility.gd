extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
var pixel_checks := 0
func _initialize() -> void: call_deferred("run")
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("STAFF_VISIBILITY_FAIL:", message)

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    var app: Control
    for hand in ["right","left","both"]:
        # A fresh application per hand: a second score load in one application
        # does not re-arm the continuous source stream.
        if app != null:
            app.queue_free()
            await process_frame
        app = FixtureApp.new()
        app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(app)
        await process_frame
        await process_frame
        var error: String = await app.load_native_fixture(folder.path_join(hand))
        check(error.is_empty(),error)
        if not error.is_empty():
            quit(1)
            return
        var view = app.practice_view.stage.renderer
        # READY deliberately shows no source ink; Play arms the continuous
        # stream that admits the notation the probes below inspect.
        app._send_action({"action":"start"})
        for settle_frame in range(8):
            app._process(0.0)
            await process_frame
        for dimensions in [Vector2i(1536,960),Vector2i(800,600)]:
            root.size = dimensions
            await process_frame
            await process_frame
            for beat in [-1.0,.25,4.25]:
                app.last_state = {"loaded":true,"revision":app.revision,"hand":hand,
                    "phase":"count_in" if beat < 0.0 else "playing","running":true,
                    "paused":true,"clock_beat":beat,"bpm":80,"play_from_beat":0.0,
                    "transport_id":7,"duration_beats":view.timeline.duration_beats,
                    "count_in_beats":3.0,"mode":"practice","preview_only":true}
                app._process(0.0)
                view.queue_redraw()
                await process_frame
                await process_frame
                RenderingServer.force_draw()
                var frame: Image = root.get_texture().get_image()
                var pixels := Vector2(frame.get_size()) / root.get_visible_rect().size
                var transform: Transform2D = view.get_global_transform_with_canvas()
                var panel: Rect2 = app.practice_view.stage.score_frame.get_global_rect()
                var gap: float = view.staff_gap()
                # The step timeline is now a strip at the top of the score frame
                # (runway_steps); it must stay above the first engraved staff line.
                var first_line_y: float = (transform * Vector2(0, view.size.y*.36-2*gap)).y
                check(app.practice_view.stage.runway_steps.get_global_rect().end.y <= first_line_y,
                    "Lesson navigation stays above native notation")
                for index in range(10):
                    var staff: String = "right" if index < 5 else "left"
                    # Source staff placement is fixed (see below);
                    # the pixel oracle does not sample where a drawn line says it is.
                    # A single performing hand with an unused opposite staff is
                    # centred alone at 41% and the opposite staff is collapsed
                    # (d0bfdf8d); otherwise the grand staff keeps 36%/69%.
                    var focused: String = view.layout.focused_staff
                    if not focused.is_empty():
                        check(view.layout.visible_staves() == [focused], "Collapsed staff is not engraved")
                        if staff != focused:
                            continue
                    var fraction_y: float = .41 if staff == focused else (.36 if index < 5 else .69)
                    var local_y: float = view.size.y*fraction_y+(index%5-2)*gap
                    var y: int = roundi((transform * Vector2(0,local_y)).y*pixels.y)
                    var active: bool = hand == "both" or hand == staff
                    var bright := 0
                    var tested := 0
                    for local_x in range(50,floori(view.size.x)-20,3):
                        if absf(float(local_x)-view.size.x*view.PLAYHEAD_FRACTION) < 32.0:
                            continue
                        var near_glyph := false
                        for event in view.layout.ordered_events:
                            var event_x: float = view.timeline.screen_x(float(event.beat),beat,view.size.x*view.PLAYHEAD_FRACTION)
                            if absf(float(local_x)-event_x) < gap*2.5:
                                near_glyph = true
                                break
                        if near_glyph:
                            continue
                        var x: int = roundi((transform*Vector2(local_x,0)).x*pixels.x)
                        if x < 0 or x >= frame.get_width() or y < 1 or y >= frame.get_height()-1:
                            continue
                        var brightness := 0.0
                        for row in range(y-1,y+2):
                            var color: Color = frame.get_pixel(x,row)
                            brightness = maxf(brightness,minf(color.r,minf(color.g,color.b)))
                        if brightness >= .29:
                            bright += 1
                        tested += 1
                    check(tested >= 20,"Enough unobstructed native rule samples: %s %s rail %d (%d)" % [dimensions,hand,index,tested])
                    var fraction: float = float(bright)/maxi(1,tested)
                    check(fraction >= .90 if active else fraction < .10,
                        "%s %s beat %.2f rail %d: active bright/inactive subdued (%.3f)" % [dimensions,hand,beat,index,fraction])
                    pixel_checks += 1
                check(not view.drawn_noteheads.is_empty(), "Staff probe includes actual source noteheads")
                frame.save_png(folder.path_join("staff-%s-%dx%d-%.2f.png" % [hand,dimensions.x,dimensions.y,beat]))
    app._navigate("library")
    await create_timer(.25).timeout
    RenderingServer.force_draw()
    var modal: Image = root.get_texture().get_image()
    modal.save_png(folder.path_join("staff-library-overlay.png"))
    check(app.current_screen == "library", "Music drawer opens above the native score")
    print("STAFF_VISIBILITY_PIXEL_CHECKS:", pixel_checks)
    print("STAFF_VISIBILITY_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
