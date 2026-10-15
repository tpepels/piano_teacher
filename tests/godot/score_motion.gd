extends SceneTree

# Exercise the real UI raster and transforms, independently of HTTP scheduling.
# The desktop invocation also captures actual rendered frames for visual review.
class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        _build_interface()
        _navigate("practice")
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("FAIL: ", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var folder := args[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536, 960)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var transparent := Image.create(100, 80, false, Image.FORMAT_RGBA8)
    transparent.fill(Color(0, 0, 0, 0))
    transparent.fill_rect(Rect2i(20, 16, 30, 40), Color.BLACK)
    check(app._visible_engraving_bounds(transparent) == Rect2i(20, 16, 30, 40),
          "transparent margins must be excluded from ink crop")
    app.revision = 0
    app.layout_revision = 0
    app.requested_revision = 0
    app.requested_page = 0
    app.score_layout = JSON.parse_string(FileAccess.get_file_as_string(folder + "/layout.json"))
    for page in range(int(app.score_layout.pages)):
        app.page_images.append(Image.load_from_file(folder + "/page-%d.png" % page))
    app.source_layout = app.score_layout
    app.last_state = {"phase": "ready"}
    app._on_score(0, 200, PackedStringArray(), FileAccess.get_file_as_bytes(folder + "/score.png"))
    await process_frame
    await process_frame
    var initial_size: Vector2 = app.score_content.size
    var note: Dictionary = app.score_layout["notes"][0]
    var results: Array = []
    for bpm in [30, 40, 80, 120]:
        var lead: float = minf(3.0, floor(4.0 * bpm / 60.0 * 2.0) / 2.0)
        var clock: float = -lead
        var step: float = float(bpm) / 60.0 / 60.0
        var previous_x := INF
        var captures := 0
        while clock <= 2.05:
            app.last_state = {"running": true, "paused": false, "clock_beat": clock,
                "bpm": bpm, "play_from_beat": 0.0, "duration_beats": 6.0,
                "count_in_beats": lead, "transport_id": bpm, "phase": "playing"}
            app.last_state_tick = Time.get_ticks_msec()
            app._process(1.0 / 60.0)
            var projected: Vector2 = app.score_content.position + (
                Vector2(float(note.x), float(note.y)) - app.score_crop_origin
                ) / app.score_crop_size * app.score_content.size
            var cursor_x: float = app.score_content.position.x + (
                float(app.score_overlay.cursor.x) - app.score_crop_origin.x
                ) / app.score_crop_size.x * app.score_content.size.x
            check(absf(cursor_x - app.score_frame.size.x * 0.42) < 2.0,
                  "timing line must stay fixed at %d BPM / %.3f" % [bpm, clock])
            check(projected.x <= previous_x + 0.2, "same note moves left continuously")
            check(app.score_content.size.distance_to(initial_size) < 0.2,
                  "starting playback must preserve notation scale")
            previous_x = projected.x
            if absf(clock) < step * 0.51:
                check(absf(projected.x - cursor_x) < 2.0,
                      "first note must reach line on downbeat at %d BPM" % bpm)
            if clock >= -lead + float(captures) * (lead + 2.0) / 4.0:
                await process_frame
                await process_frame
                if DisplayServer.get_name() != "headless":
                    await RenderingServer.frame_post_draw
                    var frame := root.get_texture().get_image()
                    frame.save_png(folder + "/frame-%d-%d.png" % [bpm, captures])
                results.append({"bpm": bpm, "beat": clock, "note_x": projected.x,
                    "note_y": projected.y, "beam_x": cursor_x,
                    "frame_x": app.score_frame.global_position.x,
                    "frame_y": app.score_frame.global_position.y,
                    "scale_x": app.score_content.size.x / app.score_overlay.image_size.x})
                captures += 1
            clock += step
    # The same actual canvas must remain continuous at every system/page join.
    for system in app.score_layout.get("systems", []):
        var boundary: float = float(system.start_beat)
        if boundary <= 0.0:
            continue
        var before := Vector2.ZERO
        for offset in [-0.001, 0.001]:
            app.last_state = {"running": true, "paused": true,
                "clock_beat": boundary + offset, "duration_beats": app.score_layout.beats}
            app._process(1.0 / 60.0)
            if offset < 0.0:
                before = app.score_content.position
            else:
                check(app.score_content.position.distance_to(before) < 3.0,
                      "system/page transition must not jump or blank the canvas")
        check(app.score_view.texture != null and not app.score_tiles.is_empty(),
              "all score systems must already be loaded before playback")
        if DisplayServer.get_name() != "headless":
            await process_frame
            await process_frame
            await RenderingServer.frame_post_draw
            root.get_texture().get_image().save_png(folder + "/join-%.2f.png" % boundary)
    app.last_state = {"running": true, "paused": true, "clock_beat": 1.0,
        "duration_beats": app.score_layout.beats}
    app._process(1.0 / 60.0)
    var paused_position: Vector2 = app.score_content.position
    await create_timer(0.05).timeout
    app._process(1.0 / 60.0)
    check(app.score_content.position == paused_position, "pause freezes actual notation")
    app.last_state = {"running": false, "phase": "feedback"}
    app._process(1.0 / 60.0)
    check(app.score_content.position == paused_position,
          "feedback keeps the completed passage still for review")
    var output := FileAccess.open(folder + "/samples.json", FileAccess.WRITE)
    output.store_string(JSON.stringify(results, "  "))
    print("SCORE_MOTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
