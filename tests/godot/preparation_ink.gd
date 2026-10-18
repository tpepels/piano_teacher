extends SceneTree

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
        print("FAIL:", message)

func frame() -> Image:
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    return root.get_texture().get_image()

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1220, 780)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    app.revision = 0
    app.layout_revision = 0
    app.requested_revision = 0
    app.requested_page = 0
    app.score_layout = JSON.parse_string(FileAccess.get_file_as_string(folder + "/layout.json"))
    for page in range(int(app.score_layout.pages)):
        app.page_images.append(Image.load_from_file(folder + "/page-%d.png" % page))
    app.source_layout = app.score_layout
    app.last_state = {"phase": "ready"}
    app._on_score(0, 200, PackedStringArray(), FileAccess.get_file_as_bytes(folder + "/page-0.png"))
    await process_frame
    for onset in [0.0, 4.0]:
        app.last_state = {"running": true, "paused": true, "clock_beat": -.1,
            "play_from_beat": onset, "duration_beats": 8.0, "bpm": 80,
            "count_in_beats": 4.0, "count_in_meter": [4, 4]}
        app._process(0.0)
        app.score_overlay.cursor = {} # Compare ink without the timing beam.
        app.score_overlay.showing = false
        app.score_overlay.queue_redraw()
        var original: Image = await frame()
        original.save_png(folder + "/original-%.0f.png" % onset)
        app.score_overlay.showing = true
        app.score_overlay.queue_redraw()
        var prepared: Image = await frame()
        prepared.save_png(folder + "/prepared-%.0f.png" % onset)
        var anchor: Dictionary = app._position_at_beat(onset)
        var pixel_scale := Vector2(original.get_size()) / root.get_visible_rect().size
        var first: Vector2 = (app.score_content.global_position + Vector2(float(anchor.x), float(anchor.top)) * app.score_content.size) * pixel_scale
        var left: float = (app.score_content.global_position.x + float(anchor.ink_left) * app.score_content.size.x) * pixel_scale.x
        var bottom: float = (app.score_content.global_position.y + float(anchor.bottom) * app.score_content.size.y) * pixel_scale.y
        var expected := 0
        var retained := 0
        for y in range(maxi(0, floori(first.y)), mini(original.get_height(), ceili(bottom))):
            var staff_line := false
            for line in app.score_overlay.lead_staff_lines:
                var staff_y: float = (app.score_content.global_position.y + float(line) * app.score_content.size.y) * pixel_scale.y
                if absf(float(y) - staff_y) < 2.0:
                    staff_line = true
            if staff_line:
                continue
            for x in range(maxi(0, floori(left)-1), mini(original.get_width(), floori(first.x))):
                var before: Color = original.get_pixel(x, y)
                if minf(before.r, minf(before.g, before.b)) > .65:
                    expected += 1
                    var after: Color = prepared.get_pixel(x, y)
                    if minf(after.r, minf(after.g, after.b)) > .65:
                        retained += 1
        check(expected > 15, "fixture contains actual accidental/ledger ink left of onset %.0f" % onset)
        check(retained >= expected * .98, "preparation preserves opening ink at %.0f: %d of %d pixels" % [onset, retained, expected])
    print("PREPARATION_INK_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
