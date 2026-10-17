extends SceneTree

# This harness retains main.gd's ordinary HTTP polling, clock and _process.
# It only drives real API controls and measures the rendered desktop viewport.
class LiveApp extends "res://main.gd":
    var rendered_clock := 0.0

    func _process(delta: float) -> void:
        super._process(delta)
        # Record the clock used for this rendered frame. Reading it after the
        # GPU readback would include the elapsed capture time in the sample.
        rendered_clock = _transport_beat_now()

var app: Control
var folder := ""
var samples: Array = []
var failures: Array[String] = []
var tracked_id := ""
var baseline_size := Vector2.ZERO

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("VISIBLE_FAIL:", message)

func wait_for(predicate: Callable, seconds: float, description: String) -> bool:
    var deadline: int = Time.get_ticks_msec() + int(seconds * 1000.0)
    while not predicate.call():
        if Time.get_ticks_msec() >= deadline:
            check(false, "Timed out: " + description)
            return false
        await process_frame
    return true

func api(command: Dictionary) -> Dictionary:
    var request := HTTPRequest.new()
    request.timeout = 20.0
    root.add_child(request)
    var error := request.request("http://127.0.0.1:8765/control",
        ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(command))
    if error != OK:
        check(false, "Cannot send control: " + str(command))
        request.queue_free()
        return {}
    var response: Array = await request.request_completed
    request.queue_free()
    if int(response[1]) != 200:
        check(false, "Control failed: " + str(command) + " / " + str(response[1]))
        return {}
    var parsed: Variant = JSON.parse_string(response[3].get_string_from_utf8())
    if not parsed is Dictionary:
        check(false, "Control returned invalid JSON")
        return {}
    return parsed

func score_ready() -> bool:
    return app.score_view.texture != null and app.layout_revision == app.revision \
        and app.rendered_revision == app.revision and not app.layout_pending and not app.score_pending

func active_attempt(transport_id: int) -> bool:
    return int(app.last_state.get("transport_id", -1)) == transport_id \
        and bool(app.last_state.get("running", false)) and app.score_overlay.showing and score_ready()

func note_position(note: Dictionary) -> Vector2:
    var local: Vector2 = (Vector2(float(note.x), float(note.y)) - app.score_crop_origin) \
        / app.score_crop_size * app.score_content.size
    return app.score_content.get_global_transform_with_canvas() * local

func local_ink(frame: Image, position: Vector2) -> Dictionary:
    # Glyph coordinates locate the left edge of a notehead. Remove long
    # horizontal/vertical rules before counting compact contrasting ink;
    # thick staff lines and the timing beam cannot stand in for a notehead.
    var region := Rect2i(int(position.x) + 2, int(position.y) - 7, 24, 15)
    if not Rect2i(Vector2i.ZERO, frame.get_size()).encloses(region):
        return {"pixels": 0, "rows": 0, "columns": 0}
    var red: Array[float] = []
    var green: Array[float] = []
    var blue: Array[float] = []
    for y in range(region.position.y, region.end.y):
        for x in range(region.position.x, region.end.x):
            var color := frame.get_pixel(x, y)
            red.append(color.r)
            green.append(color.g)
            blue.append(color.b)
    red.sort()
    green.sort()
    blue.sort()
    var middle: int = red.size() / 2
    var background := Color(red[middle], green[middle], blue[middle])
    var mask := {}
    var row_counts := {}
    var column_counts := {}
    for y in range(region.position.y, region.end.y):
        for x in range(region.position.x, region.end.x):
            var color := frame.get_pixel(x, y)
            var contrast: float = maxf(absf(color.r - background.r),
                maxf(absf(color.g - background.g), absf(color.b - background.b)))
            if contrast >= 0.15:
                mask[Vector2i(x, y)] = true
                row_counts[y] = int(row_counts.get(y, 0)) + 1
                column_counts[x] = int(column_counts.get(x, 0)) + 1
    var pixels := 0
    var rows := {}
    var columns := {}
    for point in mask:
        if int(row_counts[point.y]) >= region.size.x * .8 \
                or int(column_counts[point.x]) >= region.size.y * .8:
            continue
        pixels += 1
        rows[point.y] = true
        columns[point.x] = true
    return {"pixels": pixels, "rows": rows.size(), "columns": columns.size()}

func has_note_ink(ink: Dictionary) -> bool:
    return int(ink.pixels) >= 8 and int(ink.rows) >= 4 and int(ink.columns) >= 3

func check_ink_detector() -> void:
    var frame := Image.create(64, 64, false, Image.FORMAT_RGBA8)
    var position := Vector2(16, 32)
    frame.fill(Color("#1E3A34"))
    frame.fill_rect(Rect2i(0, 31, 64, 3), Color.WHITE)
    check(not has_note_ink(local_ink(frame, position)), "A thick staff rule cannot count as a notehead")
    frame.fill_rect(Rect2i(24, 0, 3, 64), Color.WHITE)
    check(not has_note_ink(local_ink(frame, position)), "Crossed staff and timing rules cannot count as a notehead")
    frame.fill(Color("#1E3A34"))
    frame.fill_rect(Rect2i(0, 31, 64, 3), Color.WHITE)
    for y in range(26, 39):
        for x in range(19, 35):
            if pow((x-27.0)/8.0, 2) + pow((y-32.0)/6.0, 2) < 1.0:
                frame.set_pixel(x, y, Color.WHITE)
    check(has_note_ink(local_ink(frame, position)), "Compact notehead ink remains detectable across a staff rule")

func write_samples() -> void:
    var output := FileAccess.open(folder + "/samples.json", FileAccess.WRITE)
    output.store_string(JSON.stringify({"samples": samples, "failures": failures,
        "renderer": DisplayServer.get_name()}, "  "))

func capture(bpm: int, label: String) -> Dictionary:
    await process_frame
    RenderingServer.force_draw()
    var frame: Image = root.get_texture().get_image()
    var note: Dictionary = {}
    for candidate in app.score_layout.get("notes", []):
        if str(candidate.get("id", "")) == tracked_id:
            note = candidate
            break
    check(not note.is_empty(), "Tracked note remains in the current score: " + tracked_id)
    if note.is_empty():
        return {}
    # Window managers may clamp the requested desktop size. Canvas coordinates
    # still use the project's stretched viewport, while captured pixels use
    # the actual render target dimensions.
    var pixel_scale := Vector2(frame.get_size()) / root.get_visible_rect().size
    var position: Vector2 = note_position(note) * pixel_scale
    var cursor: Dictionary = app.score_overlay.cursor
    var beam_local: Vector2 = (Vector2(float(cursor.get("x", 0.0)), 0.0) \
        - app.score_crop_origin) / app.score_crop_size * app.score_content.size
    var beam: Vector2 = (app.score_content.get_global_transform_with_canvas() * beam_local) * pixel_scale
    var canvas_panel: Rect2 = app.score_frame.get_global_rect()
    var panel := Rect2(canvas_panel.position * pixel_scale, canvas_panel.size * pixel_scale)
    check(absf(beam.x - (panel.position.x + panel.size.x * 0.42)) < 2.0,
        "%d BPM %s: timing line stays fixed" % [bpm, label])
    check(app.score_content.size.distance_to(baseline_size) < 0.5,
        "%d BPM %s: notation scale stays stable" % [bpm, label])
    var ink := local_ink(frame, position)
    var paused_modal: bool = app.pause_sheet.is_visible_in_tree()
    var modal_ink: Dictionary = {}
    if paused_modal:
        # The real pause sheet deliberately shades the staff. Its Resume text
        # must render, while note geometry remains frozen until it is uncovered.
        var resume_center: Vector2 = app.pause_sheet.resume_button.get_global_rect().get_center()
        modal_ink = local_ink(frame, (resume_center - Vector2(12, 0)) * pixel_scale)
        check(int(modal_ink.pixels) >= 6 and int(modal_ink.rows) >= 3 and int(modal_ink.columns) >= 3,
            "%d BPM %s: actual rendered Resume text exists (%s)" % [bpm, label, str(modal_ink)])
    else:
        # Empty staff before the first onset is intentional. Once playing,
        # check actual ink for a note inside the viewport, even after our
        # original tracked note has scrolled out of view.
        var visible_note := false
        var visible_ink := false
        for candidate in app.score_layout.get("notes", []):
            var point: Vector2 = note_position(candidate) * pixel_scale
            if panel.grow(-25.0).has_point(point):
                visible_note = true
                var pixels := local_ink(frame, point)
                visible_ink = visible_ink or has_note_ink(pixels)
        check(visible_ink or (not visible_note and app.rendered_clock < 0.0),
            "%d BPM %s: visible notation contains actual notehead pixels" % [bpm,label])
    var filename := "frame-%d-%s.png" % [bpm, label]
    check(frame.save_png(folder + "/" + filename) == OK, "Save rendered frame " + filename)
    var result := {"bpm": bpm, "label": label, "beat": app.rendered_clock,
        "phase": app.last_state.get("phase", ""), "note_id": tracked_id,
        "note_x": position.x, "note_y": position.y, "beam_x": beam.x,
        "width": app.score_content.size.x, "height": app.score_content.size.y,
        "ink": ink, "paused_modal": paused_modal, "modal_ink": modal_ink,
        "frame": filename, "pixel_scale": [pixel_scale.x, pixel_scale.y]}
    samples.append(result)
    write_samples()
    return result

func run_tempo(bpm: int) -> void:
    print("VISIBLE_STAGE:", bpm, " BPM real HTTP playback")
    var tempo: Dictionary = await api({"action": "tempo", "bpm": bpm})
    var wanted_revision: int = int(tempo.get("revision", -2))
    if not await wait_for(func(): return app.revision == wanted_revision and score_ready(),
            90.0, "engraved score revision at " + str(bpm)):
        return
    await process_frame
    await process_frame
    baseline_size = app.score_content.size
    tracked_id = str(app.score_layout["notes"][0].get("id", ""))
    check(not tracked_id.is_empty(), "Required note has a stable ID")
    var prior_id: int = int(app.last_state.get("transport_id", -1))
    app.start_button.pressed.emit()
    if not await wait_for(func(): return int(app.last_state.get("transport_id", -1)) > prior_id \
            and active_attempt(int(app.last_state.get("transport_id", -1))), 10.0, "Play button starts a running attempt"):
        return
    var started: Dictionary = app.last_state
    var transport_id: int = int(started.get("transport_id", -2))
    var previous: Dictionary = {}
    var moving_samples: Array = []
    var lead: float = float(started.get("count_in_beats", 3.0))
    # At slow tempi the opening note leaves the viewport sooner in musical
    # beats because those beats deliberately have more horizontal space.
    for target in [-lead + .2, -0.65, -0.1, 0.0, 0.35, 0.7, 1.1]:
        if not await wait_for(func(): return app._transport_beat_now() >= target,
                12.0, "target musical beat " + str(target)):
            return
        var sample: Dictionary = await capture(bpm, "beat-%s" % str(target).replace(".", "_"))
        moving_samples.append(sample)
        if not previous.is_empty() and not sample.is_empty():
            check(float(sample.note_x) < float(previous.note_x) - 2.0,
                "%d BPM: same note moves left through count-in and playback" % bpm)
        previous = sample
    if moving_samples.size() >= 2 and not moving_samples[0].is_empty() and not previous.is_empty():
        var first: Dictionary = moving_samples[0]
        var pixels_per_beat: float = (float(first.note_x) - float(previous.note_x)) \
            / (float(previous.beat) - float(first.beat))
        for sample in moving_samples:
            if sample.is_empty():
                continue
            var at_downbeat: float = float(sample.note_x) + float(sample.beat) * pixels_per_beat
            check(absf(at_downbeat - float(sample.beam_x)) < 1.5,
                "%d BPM: constant screen-space travel arrives at the line on beat zero" % bpm)
    app.start_button.pressed.emit()
    if not await wait_for(func(): return bool(app.last_state.get("paused", false)), 5.0, "pause"):
        return
    var paused_a: Dictionary = await capture(bpm, "paused-a")
    await create_timer(0.4).timeout
    var paused_b: Dictionary = await capture(bpm, "paused-b")
    check(absf(float(paused_b.get("note_x", 0.0)) - float(paused_a.get("note_x", 0.0))) < 1.0,
        "%d BPM: pause freezes the actual displayed note" % bpm)
    var pause_beat: float = app._transport_beat_now()
    app.start_button.pressed.emit()
    if not await wait_for(func(): return not bool(app.last_state.get("paused", true)) \
            and app._transport_beat_now() >= pause_beat + 0.35, 5.0, "resume"):
        return
    var resumed: Dictionary = await capture(bpm, "resumed")
    check(float(resumed.get("note_x", 0.0)) < float(paused_b.get("note_x", 0.0)) - 2.0,
        "%d BPM: resume continues leftward movement" % bpm)
    var restarted: Dictionary = await api({"action": "restart"})
    var restart_id: int = int(restarted.get("transport_id", -2))
    check(restart_id > transport_id, "Restart creates a new attempt")
    if await wait_for(func(): return active_attempt(restart_id) \
            and app._transport_beat_now() >= -0.65, 12.0, "restart count-in"):
        var restart: Dictionary = await capture(bpm, "restarted")
        check(float(restart.get("beat", 1.0)) < 0.0, "Restart supplies a fresh moving count-in")
        check(float(restart.get("note_x", 0.0)) > float(resumed.get("note_x", 0.0)) + 2.0,
            "Restart rewinds the same displayed note")
    await api({"action": "stop"})
    check(int(app.last_state.get("mastered", -1)) == 0, "Silent previews never award mastery")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[0]
    check_ink_detector()
    if DisplayServer.get_name() == "headless":
        check(false, "A real desktop renderer is required")
        write_samples()
        quit(1)
        return
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(int(args[2]), int(args[3]))
    app = LiveApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    app._navigate("practice")
    if not await wait_for(score_ready, 90.0, "initial real HTTP score loading"):
        write_samples()
        quit(1)
        return
    for value in args[1].split(","):
        await run_tempo(int(value))
        if not failures.is_empty():
            break
    if failures.is_empty():
        print("VISIBLE_STAGE:240 BPM complete silent preview")
        var tempo: Dictionary = await api({"action": "tempo", "bpm": 240})
        var revision: int = int(tempo.get("revision", -2))
        if await wait_for(func(): return app.revision == revision and score_ready(), 90.0, "final score"):
            var final: Dictionary = await api({"action": "start"})
            var transport_id: int = int(final.get("transport_id", -2))
            if await wait_for(func(): return active_attempt(transport_id), 5.0, "final preview starts"):
                await wait_for(func(): return not bool(app.last_state.get("running", true)),
                    8.0, "preview naturally completes")
                check(str(app.last_state.get("phase", "")) == "ready", "Completed preview returns to ready")
                check(int(app.last_state.get("mastered", -1)) == 0, "Completed preview does not master a lesson")
    write_samples()
    print("VISIBLE_RESULT:", "PASS" if failures.is_empty() else "FAIL", " samples=", samples.size())
    quit(0 if failures.is_empty() else 1)
