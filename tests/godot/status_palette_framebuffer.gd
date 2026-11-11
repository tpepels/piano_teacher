extends "native_fingering.gd"
## Palette sheet: all six statuses on filled and hollow heads. Real-framebuffer capture of note-status ink on the production NativeView.
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
const WORLD := 6.0

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
    viewport.size = Vector2i(2400,520)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    renderer = load("res://notation/native/view.gd").new()
    renderer.size = Vector2(2400,520)
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
        "practice_timeline":fixture["model"]["practice_timeline"],"visual_gap_beats":4.0}
    renderer.present(state,0.0,0.0)
    var deadline := Time.get_ticks_msec()+8000
    while not renderer.retained_ready() and Time.get_ticks_msec() < deadline:
        renderer.queue_redraw()
        await process_frame
    assert(renderer.retained_ready(),"retained source strips compiled")
    feedback = load("res://native_score_feedback.gd").new()
    root.add_child(feedback)
    feedback.bind_score(renderer,revision)
    var key: String = Status.take_key(_take(1))
    renderer.stream_world_beat = -40.0
    renderer._stream_add_take(0.0,0.0,0.0,key)
    var compile_deadline := Time.get_ticks_msec()+8000
    while Time.get_ticks_msec() < compile_deadline:
        renderer.stream_world_beat = 6.0
        renderer.queue_redraw()
        await process_frame
        load("res://notation/native/stream_lifecycle.gd").attach_compiled(renderer._stream_queue.online)
        var all_compiled := true
        for strip in renderer._stream_queue.online:
            if strip.get("segment") == null or strip["segment"].get_parent() != strip["clip"]:
                all_compiled = false
        if all_compiled:
            break
    renderer.stream_world_beat = -40.0
    feedback.present({"piece_fingerprint":"status-probe","revision":revision,
        "transport_id":1,"mode":"practice"})
    var ids: Dictionary = {}
    for event in renderer.layout.ordered_events:
        if str(event.get("kind","")) == "note" and bool(event.get("is_attack",false)):
            ids[str(event["source_id"])] = str(event["id"])
    var frames: Array = []
    frames.append(await _status_frame("baseline",WORLD))
    var dims := {
        "unplayed":{}, "hit":{"pitch":"correct","onset":"on_time","release":"on_time"},
        "missed":{"pitch":"missed"},
        "late":{"pitch":"correct","onset":"late","release":"on_time"},
        "early_release":{"pitch":"correct","onset":"on_time","release":"short"},
        "early_onset":{"pitch":"correct","onset":"early","release":"on_time"}}
    var order := ["unplayed","hit","missed","late","early_release","early_onset"]
    var filled := ["xml-p0-m0-e1","xml-p0-m0-e2","xml-p0-m0-e3","xml-p0-m0-e4","xml-p0-m1-e0","xml-p0-m1-e1"]
    var hollow := ["xml-p0-m1-e2","xml-p0-m2-e0","xml-p0-m2-e1","xml-p0-m3-e0","xml-p0-m3-e1","xml-p0-m4-e0"]
    var expected: Dictionary = {}
    for i in range(6):
        for group in [filled,hollow]:
            expected[ids[group[i]]] = order[i]
            if order[i] != "unplayed":
                _assess(1,ids[group[i]],dims[order[i]])
    # C4: a whole note tied over a barline; its attack is missed (coral).
    frames.append(await _status_frame("tied-base",WORLD+20.0))
    _assess(1,ids["xml-p0-m5-e0"],{"pitch":"missed"})
    frames.append(await _status_frame("graded",WORLD))
    frames.append(await _status_frame("tied",WORLD+20.0))
    var bg: Color = renderer.Design.STAGE
    var ink: Color = renderer.NOTE_INK
    var tints: Dictionary = {}
    for status in Ink.COLORS:
        var c: Color = Ink.COLORS[status]
        tints[status] = [c.r,c.g,c.b]
    var file := FileAccess.open(folder.path_join("status-report.json"),FileAccess.WRITE)
    file.store_string(JSON.stringify({"frames":frames,"expected":expected,
        "background":[bg.r,bg.g,bg.b],"ink":[ink.r,ink.g,ink.b,ink.a],"tints":tints}))
    file.close()
    feedback.free()
    quit()
