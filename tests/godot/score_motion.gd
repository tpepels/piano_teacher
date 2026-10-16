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
    # Responsive zoom must follow the grand staff's actual geometry, not
    # the legacy maximum of 27 pixels at every desktop resolution.
    var Quality = load("res://score_quality.gd")
    var native_rails: Array = app.score_layout.systems[0].staff_lines
    var page_aspect: float = float(app.source_layout.heights[0]) / float(app.source_layout.widths[0])
    var chosen_width: int = Quality.png_width(app.source_layout, app.score_frame.size.y)
    check(chosen_width >= 2000 and chosen_width <= 7200,
        "High-resolution score request stays in bounded PNG limits")
    check(float(chosen_width) * float(chosen_width) * page_aspect <= 18000000.0 + 7200.0,
        "Responsive engraving respects the memory budget")
    check(Quality.staff_gap(800.0, native_rails) >
        Quality.staff_gap(400.0, native_rails) * 1.25,
        "Large stage must produce visibly larger staves and notes")
    var initial_size: Vector2 = app.score_content.size
    # Phase 8G keeps tile positions and sizes fixed during ordinary
    # scrolling. Only score_content.position is allowed to move per frame.
    var first_tile_position: Vector2 = app.score_tiles[0].position
    var first_tile_size: Vector2 = app.score_tiles[0].size
    var initial_geometry_rebuilds: int = app.tile_geometry_rebuilds
    check(app.tile_window_initialized and app.score_tile_scale > 0.0,
        "8G camera must initialize cached raster geometry and visibility")
    check(app.deferred_tile_mode == (
        app.source_layout.get("systems", []).size() >=
        load("res://score_strip.gd").DEFERRED_MIN_SYSTEMS),
        "8I enables deferred score textures only for long scores")
    var note: Dictionary = app.score_layout["notes"][0]
    var first_rails: Array = app.score_layout["systems"][0].get("staff_lines", [])
    check(app.staff_continuity.staff_lines == first_rails,
        "The same horizontal staff continues underneath every engraved tile")
    check(app.staff_continuity.size.distance_to(app.score_content.size) < 2.0,
        "Continuous staff shares the real scroll and zoom transform: %s vs %s" % [
            str(app.staff_continuity.size), str(app.score_content.size)])
    if first_rails.size() >= 2:
        var displayed_gap: float = absf(float(first_rails[1]) - float(first_rails[0])) * app.score_content.size.y
        check(displayed_gap >= 18.0,
            "Practice staves must be readable, not minimized by blank SVG margins")
    check(app.score_overlay._symbols.size() == 4, "count-in loads the score's actual clefs and rests")
    var original_clefs: Dictionary = app.score_layout.get("staff_clefs", {})
    var changed_clefs := {"right":{"sign":"F","line":4,"octave_change":0},
        "left":{"sign":"G","line":2,"octave_change":0}}
    app.score_layout["staff_clefs"] = changed_clefs
    app._layout_moving_score()
    check(app.score_overlay.preparation_clefs == changed_clefs,
          "active score clefs reach the count-in through the actual UI layout")
    app.score_layout["staff_clefs"] = original_clefs
    app._layout_moving_score()
    var results: Array = []
    for bpm in [30, 40, 80, 120]:
        var lead: float = minf(3.0, floor(4.0 * bpm / 60.0 * 2.0) / 2.0)
        var positions: Array[float] = []
        for sample in [-0.01, 0.0, 0.01]:
            app.last_state = {"running": true, "paused": true, "clock_beat": sample,
                "bpm": bpm, "play_from_beat": 0.0, "duration_beats": 6.0,
                "count_in_beats": lead, "count_in_meter": [3, 4]}
            app._process(0.0)
            positions.append(app.score_content.position.x)
        var incoming: float = positions[1] - positions[0]
        var outgoing: float = positions[2] - positions[1]
        check(absf(incoming - outgoing) < maxf(.05, absf(outgoing) * .02),
              "count-in and opening notes have matching speed at %d BPM" % bpm)
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
            if clock >= 0.0:
                var tile_scale: float = app.score_content.size.x / float(app.score_layout.strip_size.x)
                var ink_tile_under_cursor := false
                for tile_index in range(app.strip_tiles.size()):
                    var tile_rect: Rect2 = app.strip_tiles[tile_index]["rect"]
                    var screen_left: float = app.score_content.position.x + tile_rect.position.x * tile_scale
                    var screen_right: float = screen_left + tile_rect.size.x * tile_scale
                    if screen_left - .1 <= cursor_x and screen_right + .1 >= cursor_x:
                        ink_tile_under_cursor = true
                        check(app.score_tiles[tile_index].visible,
                            "the actual engraved tile at the timing line must never be culled")
                        check(app.score_tiles[tile_index].texture != null,
                            "8I must restore real note ink beneath the playhead before drawing")
                check(ink_tile_under_cursor,
                    "musical playback must keep a source tile under the timing line")
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
    check(initial_geometry_rebuilds == 1 and
        app.tile_geometry_rebuilds == initial_geometry_rebuilds,
        "8G must build tile geometry only once at a fixed zoom, even while moving")
    check(app.tile_window_changes >= 1,
        "8G must track visibility changes independently of geometry")
    if app.deferred_tile_mode:
        var resident_count := 0
        var summed_bytes := 0
        for i in range(app.score_tiles.size()):
            var loaded: bool = app.score_tiles[i].texture != null
            check(loaded == (i >= app.resident_tile_begin and
                i < app.resident_tile_end),
                "8I only the neighbourhood of the camera is on the GPU")
            if loaded:
                resident_count += 1
                summed_bytes += int(app.strip_tiles[i].get("upload_bytes", 0))
        check(app.resident_tile_bytes == summed_bytes,
            "8I resident memory accounting must track actual uploaded tiles")
        check(resident_count <= app.visible_tile_end - app.visible_tile_begin + 4,
            "8I cannot retain unbounded offscreen engraving textures")
    check(app.score_tiles[0].position.distance_to(first_tile_position) < .01,
        "8G cannot reposition an engraved tile during constant-scale playback")
    check(app.score_tiles[0].size.distance_to(first_tile_size) < .01,
        "8G cannot resize notation while the music is moving")
    for i in range(app.score_tiles.size()):
        check(app.score_tiles[i].visible ==
            (i >= app.visible_tile_begin and i < app.visible_tile_end),
            "8G cached tile window must equal actual rendered system visibility")
    # Musical metronome and visible notes must share one transport beat.
    # A constant-rate camera applied to unequally-spaced Verovio glyphs
    # previously let notes pass the playhead off the metronome clicks.
    var last_checked_beat := -INF
    var checked_onsets := 0
    for entry in app.score_layout.get("anchors", []):
        var onset_beat: float = float(entry.get("beat", -INF))
        if onset_beat <= last_checked_beat + .00001 or onset_beat < 0:
            continue
        last_checked_beat = onset_beat
        app.last_state = {"running": true, "paused": true, "preview_only": true,
            "mode":"practice", "clock_beat": onset_beat, "bpm": 60,
            "play_from_beat": 0.0, "duration_beats": app.score_layout.beats,
            "transport_id": 198, "phase": "playing"}
        app._process(.016)
        var ink_x: float = app.score_content.position.x + (
            (float(entry.get("x", 0.0)) - app.score_crop_origin.x)
            / app.score_crop_size.x * app.score_content.size.x)
        check(absf(ink_x - app.score_frame.size.x * .42) < 2.0,
            "Preview note must cross the fixed playhead on its exact metronome beat")
        checked_onsets += 1
        if checked_onsets >= 12:
            break
    check(checked_onsets >= 3,
        "The score/metronome fixture must verify multiple note arrivals")
    # A time-proportional strip must interpolate *through* each original
    # system join rather than freezing until the following first note.
    var checked_system_join := false
    var all_anchors: Array = app.score_layout.get("anchors", [])
    for i in range(all_anchors.size()-1):
        var left: Dictionary = all_anchors[i]
        var right: Dictionary = all_anchors[i+1]
        if str(left.get("source_system", "")) == str(right.get("source_system", "")):
            continue
        if float(right.beat)-float(left.beat) <= .00001:
            continue
        var midpoint: float = (float(left.beat)+float(right.beat))*.5
        var join_cursor: Dictionary = app._position_at_beat(midpoint)
        check(absf(float(join_cursor.get("x", 0.0)) -
            (float(left.x)+float(right.x))*.5) < .00001,
            "Camera cannot stall between systems: midpoint must lie midway between notes")
        checked_system_join = true
    if app.score_layout.get("systems", []).size() > 1:
        check(checked_system_join,
            "Multi-system timing fixture must include a time-bearing system join")
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
    app.last_state = {"running": false, "phase": "paused", "pause_context": "feedback"}
    app._process(1.0 / 60.0)
    check(app.score_content.position == paused_position,
          "pausing an automatic break holds the performed score for reading")
    app.last_state = {"running": false, "phase": "feedback"}
    app._process(1.0 / 60.0)
    check(app.score_content.position == paused_position,
          "feedback keeps the completed passage still for review")
    app.last_state = {"running": false, "phase": "ready"}
    app._process(1.0 / 60.0)
    check(absf(app.score_content.position.x - app.score_frame.size.x * .04) < 1.0,
          "Stop during feedback returns the score to its ready position")
    var output := FileAccess.open(folder + "/samples.json", FileAccess.WRITE)
    output.store_string(JSON.stringify(results, "  "))
    print("SCORE_MOTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
