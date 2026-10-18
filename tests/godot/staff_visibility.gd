extends SceneTree

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("STAFF_VISIBILITY_FAIL:", message)

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    for hand in ["right", "left", "both"]:
        var source: String = folder.path_join(hand)
        app.revision += 1
        app.layout_revision = app.revision
        app.requested_revision = app.revision
        app.requested_page = 0
        app.score_layout = JSON.parse_string(FileAccess.get_file_as_string(source + "/layout.json"))
        app.source_layout = app.score_layout
        app.page_images.clear()
        for page in range(int(app.score_layout.pages)):
            app.page_images.append(Image.load_from_file(source + "/page-%d.png" % page))
        app.last_state = {"phase":"ready", "hand":hand}
        app._on_score(0, 200, PackedStringArray(), FileAccess.get_file_as_bytes(source + "/score.png"))
        for dimensions in [Vector2i(1536,960), Vector2i(800,600)]:
            root.size = dimensions
            await process_frame
            await process_frame
            for beat in [-1.0, 0.25, 4.25]:
                app.last_state = {"phase":"count_in" if beat < 0 else "playing", "hand":hand,
                    "running":true, "paused":false, "clock_beat":beat, "bpm":80,
                    "play_from_beat":0.0, "duration_beats":16.0, "count_in_beats":3.0}
                app._process(0.0)
                # This probe measures staff ink, independently of colored cues.
                app.score_overlay.next_chord = []
                app.score_overlay.queue_redraw()
                await process_frame
                RenderingServer.force_draw()
                var frame := root.get_texture().get_image()
                var pixels := Vector2(frame.get_size()) / root.get_visible_rect().size
                var panel: Rect2 = app.score_frame.get_global_rect()
                var transform: Transform2D = app.score_content.get_global_transform_with_canvas()
                var rails: Array = app.score_layout.systems[0].staff_lines
                for index in range(rails.size()):
                    var y: int = roundi((transform * Vector2(0, float(rails[index]) * app.score_content.size.y)).y * pixels.y)
                    var active: bool = hand == "both" or (index < 5) == (hand == "right")
                    var white := 0
                    var tested := 0
                    for x in range(ceili((panel.position.x + 12) * pixels.x), floori((panel.end.x - 12) * pixels.x), 3):
                        # Feedback and the timing beam are intentionally colored.
                        if absf(x - (panel.position.x + panel.size.x * .42) * pixels.x) < 35:
                            continue
                        if beat < 0.0 and app.game_count_in.get_global_rect().has_point(Vector2(x/pixels.x, y/pixels.y)):
                            continue
                        var preparation_glyph := false
                        if beat < 0.0:
                            var first_x: float = float(app.score_overlay.lead_first.get("x", 0)) * app.score_content.size.x
                            for count in range(ceili(app.score_overlay.lead_beats)):
                                var local_x: float = first_x + (-app.score_overlay.lead_beats + count) \
                                    * app.score_overlay.lead_width_px / app.score_overlay.lead_beats
                                if absf(x - (transform * Vector2(local_x, 0)).x * pixels.x) < 40:
                                    preparation_glyph = true
                        if preparation_glyph:
                            continue
                        var brightest := Color.BLACK
                        for row in range(maxi(0, y - 1), mini(frame.get_height(), y + 2)):
                            var color := frame.get_pixel(x, row)
                            if minf(color.r, minf(color.g, color.b)) > minf(brightest.r, minf(brightest.g, brightest.b)):
                                brightest = color
                        if minf(brightest.r, minf(brightest.g, brightest.b)) >= .97:
                            white += 1
                        tested += 1
                    var fraction: float = float(white) / maxi(1, tested)
                    check(fraction >= .98 if active else fraction < .1,
                        "%s %s beat %.2f rail %d: active white / inactive subdued (white %.3f)" % [dimensions,hand,beat,index,fraction])
                frame.save_png(folder + "/staff-%s-%dx%d-%.2f.png" % [hand,dimensions.x,dimensions.y,beat])
    app._navigate("library")
    await create_timer(.25).timeout
    RenderingServer.force_draw()
    var modal_frame := root.get_texture().get_image()
    var rail_y: int = roundi(app.score_content.global_position.y \
        + float(app.score_layout.systems[0].staff_lines[0]) * app.score_content.size.y)
    var leaking := 0
    for x in range(400, 740):
        var color := modal_frame.get_pixel(x, rail_y)
        if minf(color.r, minf(color.g, color.b)) >= .97:
            leaking += 1
    check(leaking < 10, "Staff rules remain behind the Music drawer")
    modal_frame.save_png(folder + "/staff-library-overlay.png")
    print("STAFF_VISIBILITY_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
