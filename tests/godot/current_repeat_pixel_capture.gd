extends SceneTree
## Photographed repeat against the current forward-only immutable score queue.
## One original passage, its genuine full-meter rest, and a fresh source pass
## use the SAME native source, epoch and renderer as production. No retired
## looping camera, rewind or alternate test renderer is involved.
const StreamAdmission := preload("res://score_stream_admission.gd")
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("_run")

func fail(message: String) -> void:
    failures.append(message)
    printerr("CURRENT_REPEAT_PIXEL_FAILED:", message)

func _photograph(view: SubViewport, renderer, world: float,
        snapshot: Dictionary, output: String) -> void:
    for i in range(20):
        renderer.present(snapshot,0.0)
        renderer.present_flow(world,snapshot,0.0,false)
        await process_frame
        if i >= 1 and renderer.retained_ready():
            break
    await process_frame
    await RenderingServer.frame_post_draw
    var frame: Image = view.get_texture().get_image()
    if frame.is_empty() or frame.save_png(output) != OK:
        fail("Cannot photograph " + output)

func _run() -> void:
    var arguments := OS.get_cmdline_user_args()
    if arguments.size() != 2:
        fail("Usage: -- FIXTURE_JSON OUTPUT_DIRECTORY")
        quit(2)
        return
    var fixture: Variant = JSON.parse_string(FileAccess.get_file_as_string(arguments[0]))
    if not fixture is Dictionary or not fixture.has("assets") or not fixture.has("model"):
        fail("No authentic source-bound notation fixture")
        quit(2)
        return
    var output: String = arguments[1]
    DirAccess.make_dir_recursive_absolute(output)
    var viewport := SubViewport.new()
    viewport.size = Vector2i(1536,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var renderer = preload("res://notation/native/view.gd").new()
    renderer.size = Vector2(viewport.size)
    viewport.add_child(renderer)
    renderer.set_fingering_annotations_enabled(false)
    renderer.set_transport_overlay_enabled(true)
    var assets: Dictionary = fixture["assets"]
    if not renderer.set_verovio_glyphs(
            assets["native_glyphs"], assets["native_note_templates"],
            assets["native_tie_templates"], assets["native_chord_templates"],
            assets["native_beam_fragments"], assets["native_tuplet_fragments"],
            assets["native_slur_fragments"], assets["native_required_slur_pairs"],
            assets["native_slurs_complete"], assets["native_required_beam_groups"],
            assets["native_beams_complete"]):
        fail("Missing native Verovio glyph assets: " + renderer.failure_reason)
        quit(1)
        return
    if not renderer.load_score(fixture["model"]):
        fail("Cannot load canonical source model: " + renderer.failure_reason)
        quit(1)
        return
    for i in range(25):
        if renderer.retained_ready():
            break
        await process_frame
    if not renderer.retained_ready():
        fail("Original/rest native ink did not compile")
        quit(1)
        return
    var duration: float = float(renderer.timeline.duration_beats)
    var gap: float = float(renderer.practice_timeline["gap"]["duration_beats"])
    if gap <= 0.0:
        fail("The authoritative timeline has no full-measure rest")
        quit(1)
        return
    var density: float = renderer.timeline.pixels_per_beat
    var staff_gap: float = renderer.staff_gap()
    renderer.stream_world_beat = -maxf(100.0,duration+40.0)
    renderer._stream_add_take(0.0,0.0,0.0,"repeat-first")
    var first_size: int = renderer._stream_queue.online.size()
    if first_size < 2:
        fail("First passage did not enqueue its authored preparation rest")
        quit(1)
        return
    var replay_origin: float = StreamAdmission.position(
        renderer._stream_queue.online,0.0,renderer._stream_right_beats(),
        renderer._stream_header_beats(0.0),NAN,0.0,density,staff_gap,duration)
    if not is_finite(replay_origin):
        fail("Cannot reserve a disjoint future replay")
        quit(1)
        return
    renderer._stream_add_take(0.0,replay_origin,0.0,"repeat-second")
    var online: Array = renderer._stream_queue.online
    var rest_count := 0
    var replay_count := 0
    for item in online:
        if str(item.get("kind","")) == "rest":
            rest_count += 1
        if str(item.get("take_key","")) == "repeat-second" and \
                str(item.get("kind","")) == "source":
            replay_count += 1
    if rest_count < 2 or replay_count < 1:
        fail("Future source/rest queue omitted one required retained clip")
        quit(1)
        return
    var first_origins: Array = []
    var second_origins: Array = []
    for item in online:
        if str(item.get("kind","")) == "source":
            if str(item.get("take_key","")) == "repeat-first":
                first_origins.append(float(item["world_origin"]))
            if str(item.get("take_key","")) == "repeat-second":
                second_origins.append(float(item["world_origin"]))
    if first_origins.is_empty() or second_origins.is_empty() or \
            float(second_origins[0]) < duration+gap:
        fail("Replay source overlaps its predecessor's rest")
        quit(1)
        return
    var snapshot := {
        "loaded":true,"running":true,"paused":false,
        "phase":"playing","mode":"practice","bpm":40.0,
        "transport_id":11,"revision":1,
        "hand":str(fixture.get("hand","both")),
        "piece_fingerprint":"repeat-native-photo",
        "play_from_beat":0.0,"count_in_beats":0.0,
    }
    # Both note-on clocks are placed at the fixed playhead; only the world
    # origin changes, with a fully authored rest occupying the middle shot.
    await _photograph(viewport,renderer,0.0,snapshot,output.path_join("first.png"))
    await _photograph(viewport,renderer,duration+gap*0.5,snapshot,
        output.path_join("rest.png"))
    await _photograph(viewport,renderer,replay_origin,snapshot,
        output.path_join("replay.png"))
    var summary := {"source_duration":duration,"rest_duration":gap,
        "replay_origin":replay_origin,"source_first":first_origins,
        "source_replay":second_origins,"queue_count":online.size(),
        "rest_count":rest_count,"density":density,"staff_gap":staff_gap,
        "errors":failures}
    var file := FileAccess.open(output.path_join("repeat.json"),FileAccess.WRITE)
    if file == null:
        fail("Could not publish repeat witness")
    else:
        file.store_string(JSON.stringify(summary,"  "))
        file.close()
    print("CURRENT_REPEAT_PIXEL_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
