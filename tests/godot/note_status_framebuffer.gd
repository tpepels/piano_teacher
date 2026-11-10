extends "native_fingering.gd"
## Real-framebuffer capture of note-status ink on the production NativeView.
## Authentic Verovio assets, the real immutable stream queue (two physical
## copies of the same source with distinct takes), the real ledger and its
## event ingestion. Python measures the PNGs; nothing here asserts pixels.
const Status := preload("res://note_status_registry.gd")
const Ink := preload("res://note_status_ink.gd")

var renderer
var feedback
var viewport: SubViewport
var sequence := 0
var revision := 3

func _take(transport: int) -> Dictionary:
    return {"piece_fingerprint":"status-probe","revision":revision,
        "transport_id":transport,"mode":"practice","graded":true}

func _send(kind: String, transport: int, fields: Dictionary) -> String:
    sequence += 1
    var event: Dictionary = _take(transport)
    event.merge(fields,true)
    event["kind"] = kind
    event["sequence"] = sequence
    return feedback.ingest(event)

func _assess(transport: int, id: String, dims: Dictionary) -> String:
    return _send("assessment",transport,{"note_id":id,"status":"fixture",
        "dimensions":dims})

func _instances() -> Array:
    var result: Array = []
    for item in renderer.drawn_note_instances:
        var p: Vector2 = item["position"]
        var clip: Vector2 = item.get("clip_x",Vector2(-INF,INF))
        var ink: Color = item["ink"]
        result.append({"event_id":item["event_id"],"take_key":item["take_key"],
            "instance_id":item["instance_id"],"head":item["head"],
            "position":[p.x,p.y],"clip_x":[clip.x,clip.y],
            "ink":[ink.r,ink.g,ink.b,ink.a],"gap":float(item["gap"]),
            "source":str(item.get("source","")),
            "status":feedback.status_for(str(item["take_key"]),str(item["event_id"]))})
    return result

func _layer_paints() -> int:
    var total := 0
    for segment in renderer.retained_all_segments:
        if segment.get("status_layer") != null:
            total += int(segment.status_layer.paint_count)
    return total

func _status_frame(name: String, world: float) -> Dictionary:
    renderer.stream_world_beat = world
    await _capture(viewport,renderer,name+".png")
    return {"name":name,"file":name+".png","world":world,
        "instances":_instances(),"layer_paints":_layer_paints()}

func _run() -> void:
    var args := OS.get_cmdline_user_args()
    folder = args[1]
    var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    viewport = SubViewport.new()
    viewport.size = Vector2i(2048,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(2048,520)
    viewport.add_child(renderer)
    var a: Dictionary = fixture["assets"]
    assert(renderer.set_verovio_glyphs(a["native_glyphs"],a["native_note_templates"],
        a["native_tie_templates"],a["native_chord_templates"],a["native_beam_fragments"],
        a["native_tuplet_fragments"],a["native_slur_fragments"],a["native_required_slur_pairs"],
        a["native_slurs_complete"],a["native_required_beam_groups"],a["native_beams_complete"]))
    assert(renderer.load_score(fixture["model"]),renderer.failure_reason)
    assert(renderer.set_density(96.0))
    renderer.set_transport_overlay_enabled(false)
    renderer.set_fingering_annotations_enabled(false)
    var state: Dictionary = {"running":true,"paused":true,"hand":"both","bpm":60.0,
        "play_from_beat":0.0,"score_loop_enabled":true,
        "practice_timeline":fixture["model"]["practice_timeline"],
        "visual_gap_beats":4.0}
    renderer.present(state,0.0,0.0)
    var deadline := Time.get_ticks_msec()+8000
    while not renderer.retained_ready() and Time.get_ticks_msec() < deadline:
        renderer.queue_redraw()
        await process_frame
    assert(renderer.retained_ready(),"retained source strips compiled")
    feedback = load("res://native_score_feedback.gd").new()
    root.add_child(feedback)
    feedback.bind_score(renderer,revision)
    var key_a: String = Status.take_key(_take(1))
    var key_b: String = Status.take_key(_take(2))
    # Two physical copies of the same source through the view's own
    # admission: the first take, then its repetition after the rest measure.
    renderer.stream_world_beat = -40.0
    renderer._stream_add_take(0.0,0.0,0.0,key_a)
    var repeat_origin: float = 12.0+renderer._stream_header_beats(0.0)+.05
    renderer._stream_add_take(0.0,repeat_origin,0.0,key_b)
    assert(renderer.visible_take_keys().count(key_a) == 2 and
        renderer.visible_take_keys().count(key_b) == 2,
        "both physical copies are admitted as two measure strips each")
    # Newly admitted strips compile lazily; wait until every copy is attached.
    var compile_deadline := Time.get_ticks_msec()+8000
    while Time.get_ticks_msec() < compile_deadline:
        renderer.stream_world_beat = 6.0
        renderer.queue_redraw()
        await process_frame
        # The frame coordinator (present_flow) attaches compiled strips to
        # their presentation clips; this harness has no backend frames.
        load("res://notation/native/stream_lifecycle.gd").attach_compiled(renderer._stream_queue.online)
        var all_compiled := true
        for strip in renderer._stream_queue.online:
            if strip.get("segment") == null or strip["segment"].get_parent() != strip["clip"]:
                all_compiled = false
        if all_compiled:
            break
    renderer.stream_world_beat = -40.0
    feedback.present({"piece_fingerprint":"status-probe","revision":revision,
        "transport_id":2,"mode":"practice"})
    var ids: Dictionary = {} # source ID -> engraved note ID
    for event in renderer.layout.ordered_events:
        if str(event.get("kind","")) == "note" and bool(event.get("is_attack",false)):
            ids[str(event["source_id"])] = str(event["id"])
    var frames: Array = []
    frames.append(await _status_frame("baseline",6.0))
    frames.append(await _status_frame("baseline-moved",6.5))
    var outcomes: Array = []
    var clean := {"pitch":"correct","onset":"on_time","release":"on_time"}
    # Take 1: every status, on isolated, chord, beamed, half and whole heads.
    outcomes.append(_assess(1,ids["xml-p0-m0-e1"],clean))
    outcomes.append(_assess(1,ids["xml-p0-m0-e2"],{"pitch":"missed"}))
    outcomes.append(_assess(1,ids["xml-p0-m0-e3"],
        {"pitch":"correct","onset":"late","release":"on_time"}))
    outcomes.append(_assess(1,ids["xml-p0-m0-e4"],
        {"pitch":"correct","onset":"on_time","release":"short"}))
    outcomes.append(_assess(1,ids["xml-p0-m1-e0"],
        {"pitch":"correct","onset":"early","release":"on_time"}))
    # Provisional MIDI attack only (not yet settled).
    outcomes.append(_send("attack",1,{"source_id":"xml-p0-m1-e2","status":"on_time"}))
    outcomes.append(_assess(1,ids["xml-p0-m1-e3"],
        {"pitch":"correct","onset":"on_time","release":"unreleased"}))
    # Combined early onset and early release on a hollow whole note.
    outcomes.append(_assess(1,ids["xml-p1-m0-e1"],
        {"pitch":"correct","onset":"early","release":"short"}))
    outcomes.append(_assess(1,ids["xml-p1-m1-e0"],{"pitch":"wrong"}))
    # Take 2, the repeated copy: the same source notes, different results.
    outcomes.append(_assess(2,ids["xml-p0-m0-e1"],{"pitch":"missed"}))
    outcomes.append(_assess(2,ids["xml-p1-m0-e1"],clean))
    var paints_before: int = _layer_paints()
    frames.append(await _status_frame("graded",6.0))
    var paints_graded: int = _layer_paints()
    frames.append(await _status_frame("graded-moved",6.5))
    var paints_moved: int = _layer_paints()
    feedback.present({"piece_fingerprint":"status-probe","revision":revision,
        "transport_id":3,"mode":"practice","preview_only":true})
    frames.append(await _status_frame("suppressed",6.5))
    var bg: Color = renderer.Design.STAGE
    var ink: Color = renderer.NOTE_INK
    var tints: Dictionary = {}
    for status in Ink.COLORS:
        var c: Color = Ink.COLORS[status]
        tints[status] = [c.r,c.g,c.b]
    var file := FileAccess.open(folder.path_join("status-report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"density":96.0,
        "playhead_x":renderer.size.x*renderer.PLAYHEAD_FRACTION,
        "background":[bg.r,bg.g,bg.b],"ink":[ink.r,ink.g,ink.b,ink.a],
        "tints":tints,"ids":ids,"take_a":key_a,"take_b":key_b,"repeat_origin":repeat_origin,
        "outcomes":outcomes,"paints":{"before":paints_before,
            "graded":paints_graded,"moved":paints_moved},
        "glow":{"inner_scale":Ink.INNER_SCALE,"outer_scale":Ink.OUTER_SCALE,
            "inner_alpha":Ink.INNER_GLOW_ALPHA,"outer_alpha":Ink.OUTER_GLOW_ALPHA}}))
    file.close()
    feedback.free()
    quit()
