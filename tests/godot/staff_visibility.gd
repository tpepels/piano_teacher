extends SceneTree

const Strip := preload("res://notation/legacy/strip.gd")

class FixtureApp extends "res://main.gd":
    func _ready() -> void:
        # Explicit legacy-raster coverage, even when the parent suite launches
        # with PIANO_TEACHER_NATIVE_NOTATION=1. Native canvas coverage is separate.
        native_notation_enabled = false
        timeline_preview_enabled = false
        _build_interface()
        _navigate("practice")
        resized.connect(_update_responsive_layout)
        _update_responsive_layout()
        set_process(false)

    func _send_post(_path: String, _payload: Dictionary) -> void:
        # This offline raster fixture has no HTTPRequest nodes or server.
        pass

    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
var pixel_checks := 0

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("STAFF_VISIBILITY_FAIL:", message)

# The legacy strip preserves a source column whenever it contains real
# notation outside staff bands. Those ivory glyph columns are not white-only
# continuity rails. Derive the exclusion from the ORIGINAL PNGs, not the
# rendered frame or cleaned tiles, so a broken rail cannot mask itself.
func source_glyph_spans(layout: Dictionary, originals: Array[Image]) -> Array[Vector2]:
    var spans: Array[Vector2] = []
    for mapping in layout.get("strip_mappings", []):
        var original: Image = originals[int(mapping.source_page)]
        var crop := Rect2i(mapping.crop)
        var source_size: Vector2 = mapping.source_size
        var rule_rows := PackedByteArray()
        rule_rows.resize(original.get_height())
        for rail in mapping.system.staff_lines:
            var center: int = roundi(float(rail) * source_size.y)
            for row in range(maxi(0, center - 3), mini(rule_rows.size(), center + 4)):
                rule_rows[row] = 1
        var first := -1
        for column in range(crop.position.x, crop.end.x + 1):
            var notation := false
            if column < crop.end.x:
                for row in range(crop.position.y, crop.end.y):
                    if rule_rows[row] != 0:
                        continue
                    var pixel: Color = original.get_pixel(column, row)
                    if pixel.a >= .1 and minf(pixel.r, minf(pixel.g, pixel.b)) < .9:
                        notation = true
                        break
            if notation and first < 0:
                first = column
            elif not notation and first >= 0:
                var a: Dictionary = Strip.map_point({
                    "page":mapping.source_page, "system":mapping.source_system,
                    "x":float(first - 2) / source_size.x}, layout)
                var b: Dictionary = Strip.map_point({
                    "page":mapping.source_page, "system":mapping.source_system,
                    "x":float(column + 2) / source_size.x}, layout)
                spans.append(Vector2(float(a.x), float(b.x)))
                first = -1
    return spans

func glyph_at(pixel_x: int, spans: Array[Vector2], transform: Transform2D,
        content_width: float, pixel_scale: float) -> bool:
    for span in spans:
        var left: float = (transform * Vector2(span.x * content_width, 0)).x * pixel_scale
        var right: float = (transform * Vector2(span.y * content_width, 0)).x * pixel_scale
        if float(pixel_x) >= left and float(pixel_x) <= right:
            return true
    return false

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
        var originals: Array[Image] = []
        for page in range(int(app.score_layout.pages)):
            var image := Image.load_from_file(source + "/page-%d.png" % page)
            originals.append(image.duplicate())
            app.page_images.append(image)
        app.last_state = {"phase":"ready", "hand":hand}
        app._on_score(0, 200, PackedStringArray(), FileAccess.get_file_as_bytes(source + "/score.png"))
        var glyph_spans: Array[Vector2] = source_glyph_spans(app.score_layout, originals)
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
                    var candidates := 0
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
                        candidates += 1
                        if glyph_at(x, glyph_spans, transform, app.score_content.size.x, pixels.x):
                            continue
                        var brightest := Color.BLACK
                        for row in range(maxi(0, y - 1), mini(frame.get_height(), y + 2)):
                            var color := frame.get_pixel(x, row)
                            if minf(color.r, minf(color.g, color.b)) > minf(brightest.r, minf(brightest.g, brightest.b)):
                                brightest = color
                        if minf(brightest.r, minf(brightest.g, brightest.b)) >= .97:
                            white += 1
                        tested += 1
                    check(tested >= maxi(40, ceili(float(candidates) * .5)),
                        "%s %s beat %.2f rail %d: enough unobstructed rail samples (%d/%d)" % [
                            dimensions, hand, beat, index, tested, candidates])
                    pixel_checks += 1
                    var fraction: float = float(white) / maxi(1, tested)
                    check(fraction >= .98 if active else fraction < .1,
                        "%s %s beat %.2f rail %d: active white / inactive subdued (white %.3f)" % [dimensions,hand,beat,index,fraction])
                frame.save_png(folder + "/staff-%s-%dx%d-%.2f.png" % [hand,dimensions.x,dimensions.y,beat])
    app._navigate("library")
    await create_timer(.25).timeout
    RenderingServer.force_draw()
    var modal_frame := root.get_texture().get_image()
    var modal_scale := Vector2(modal_frame.get_size()) / root.get_visible_rect().size
    var rail_y: int = roundi((app.score_content.global_position.y \
        + float(app.score_layout.systems[0].staff_lines[0]) * app.score_content.size.y) * modal_scale.y)
    var leaking := 0
    for x in range(roundi(400 * modal_scale.x), mini(modal_frame.get_width(), roundi(740 * modal_scale.x))):
        var color := modal_frame.get_pixel(x, rail_y)
        if minf(color.r, minf(color.g, color.b)) >= .97:
            leaking += 1
    check(leaking < 10, "Staff rules remain behind the Music drawer")
    modal_frame.save_png(folder + "/staff-library-overlay.png")
    print("STAFF_VISIBILITY_PIXEL_CHECKS:", pixel_checks)
    print("STAFF_VISIBILITY_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
