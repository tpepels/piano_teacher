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
    # Glyph coordinates locate the left edge of a notehead. Detect contrast
    # across several rows/columns so a single staff line or timing beam alone
    # cannot satisfy the notehead check. Median color works on light/dark UI.
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
    var pixels := 0
    var rows := {}
    var columns := {}
    for y in range(region.position.y, region.end.y):
        for x in range(region.position.x, region.end.x):
            var color := frame.get_pixel(x, y)
            var contrast: float = maxf(absf(color.r - background.r),
                maxf(absf(color.g - background.g), absf(color.b - background.b)))
            if contrast >= 0.15:
                pixels += 1
                rows[y] = true
                columns[x] = true
    return {"pixels": pixels, "rows": rows.size(), "columns": columns.size()}

func write_samples() -> void:
    var output := FileAccess.open(folder + "/samples.json", FileAccess.WRITE)
    output.store_string(JSON.stringify({"samples": samples, "failures": failures,
        "renderer": DisplayServer.get_name()}, "  "))

func capture(bpm: int, label: String) -> Dictionary:
    await process_frame
    await RenderingServer.frame_post_draw
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
    check(panel.has_point(position), "%d BPM %s: tracked note is visible" % [bpm, label])
    check(absf(beam.x - (panel.position.x + panel.size.x * 0.42)) < 2.0,
        "%d BPM %s: timing line stays fixed" % [bpm, label])
    check(app.score_content.size.distance_to(baseline_size) < 0.5,
        "%d BPM %s: notation scale stays stable" % [bpm, label])
    var ink := local_ink(frame, position)
    var paused_modal: bool = bool(app.last_state.get("paused", false))
    var modal_ink: Dictionary = {}
    if paused_modal:
        # The real pause sheet deliberately shades the staff. Its Resume text
        # must render, while note geometry remains frozen until it is uncovered.
        check(app.pause_sheet.is_visible_in_tree(), "%d BPM %s: actual pause sheet is visible" % [bpm, label])
        var resume_center: Vector2 = app.pause_sheet.resume_button.get_global_rect().get_center()
        modal_ink = local_ink(frame, (resume_center - Vector2(12, 0)) * pixel_scale)
        check(int(modal_ink.pixels) >= 6 and int(modal_ink.rows) >= 3 and int(modal_ink.columns) >= 3,
            "%d BPM %s: actual rendered Resume text exists (%s)" % [bpm, label, str(modal_ink)])
    else:
        check(int(ink.pixels) >= 6 and int(ink.rows) >= 3 and int(ink.columns) >= 3,
            "%d BPM %s: actual rendered notehead ink exists (%s)" % [bpm, label, str(ink)])
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
    baseline_size = app.score_content.size
    tracked_id = str(app.score_layout["notes"][0].get("id", ""))
    check(not tracked_id.is_empty(), "Required note has a stable ID")
    var started: Dictionary = await api({"action": "start"})
    var transport_id: int = int(started.get("transport_id", -2))
    if not await wait_for(func(): return active_attempt(transport_id), 10.0, "running attempt"):
        return
    var previous: Dictionary = {}
    var lead: float = float(started.get("count_in_beats", 3.0))
    # At slow tempi the opening note leaves the viewport sooner in musical
    # beats because those beats deliberately have more horizontal space.
    for target in [-lead + .2, -0.65, -0.1, 0.35, 0.7, 1.1]:
        if not await wait_for(func(): return app._transport_beat_now() >= target,
                12.0, "target musical beat " + str(target)):
            return
        var sample: Dictionary = await capture(bpm, "beat-%s" % str(target).replace(".", "_"))
        if not previous.is_empty() and not sample.is_empty():
            check(float(sample.note_x) < float(previous.note_x) - 2.0,
                "%d BPM: same note moves left through count-in and playback" % bpm)
        previous = sample
    await api({"action": "pause"})
    if not await wait_for(func(): return bool(app.last_state.get("paused", false)), 5.0, "pause"):
        return
    var paused_a: Dictionary = await capture(bpm, "paused-a")
    await create_timer(0.4).timeout
    var paused_b: Dictionary = await capture(bpm, "paused-b")
    check(absf(float(paused_b.get("note_x", 0.0)) - float(paused_a.get("note_x", 0.0))) < 1.0,
        "%d BPM: pause freezes the actual displayed note" % bpm)
    var pause_beat: float = app._transport_beat_now()
    await api({"action": "resume"})
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
