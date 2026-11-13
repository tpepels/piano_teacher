extends SceneTree
const FramebufferTake := preload("framebuffer_take.gd")
var failures: Array[String] = []
func check(ok: bool, detail: String) -> void:
    if not ok:
        failures.append(detail)
        print("IDLE_RENDERING_FAIL:",detail)
func _initialize() -> void: call_deferred("run")
func generations(view: Control) -> Dictionary:
    var result: Dictionary = {}
    for segment in view.retained_all_segments:
        result[segment.get_instance_id()] = segment.compile_generation
    return result
func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.size = Vector2i(1220,780)
    # The explicit path is supplied by Python, outside Godot's resource root.
    var app = load(OS.get_cmdline_user_args()[1]).new()
    root.add_child(app)
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    await process_frame
    await process_frame
    var error: String = await app.load_native_fixture(folder)
    check(error.is_empty(),error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.practice_view.stage.renderer
    app.set_process(true)
    for settle in range(5): await process_frame
    var baseline: Dictionary = generations(view)
    var serial: int = view._stream_serial
    var revision: int = view.timeline.revision
    var world: float = view.stream_world_beat
    var payload: PackedByteArray = JSON.stringify(app.last_state).to_utf8_buffer()
    for poll in range(8):
        app._on_state(0,payload,Time.get_ticks_msec())
        await process_frame
        await process_frame
    check(generations(view) == baseline,"Identical polls never recompile/rasterize retained source/rest ink")
    check(view._stream_serial == serial,"Identical polls never duplicate source admission")
    check(view.timeline.revision == revision,"Identical polls preserve the source revision")
    check(view.stream_world_beat > world,"The intentional blank practice world continues moving")
    app.set_process(false)
    view._stream_release_all()
    var state := {"loaded":true,"running":true,"paused":false,"phase":"playing",
        "mode":"practice","bpm":80,"hand":"both","transport_id":198,
        "play_from_beat":0.0,"count_in_beats":4.0,"duration_beats":view.timeline.duration_beats,
        "piece_fingerprint":"idle-rendering","revision":view.timeline.revision,"graded":true}
    var feedback = app.practice_view.stage.feedback
    feedback.present(state)
    var key: String = load("res://note_status_registry.gd").take_key(state)
    view.stream_world_beat = -100.0
    view._stream_add_take(0.0,0.0,0.0,key)
    await FramebufferTake.show(self,view,state,0.0)
    RenderingServer.force_draw()
    var heads: Dictionary = view.drawn_noteheads.duplicate()
    check(not heads.is_empty(),"Playback paints authentic source heads")
    baseline = generations(view)
    await FramebufferTake.show(self,view,state,.25)
    RenderingServer.force_draw()
    var moved := 0
    for id in heads:
        if view.drawn_noteheads.has(id):
            check(absf(heads[id].x-view.drawn_noteheads[id].x-view.timeline.pixels_per_beat*.25)<.02,
                "Playback advances actual head positions")
            moved += 1
    check(moved > 0,"Playback motion checks common visible source ink")
    check(generations(view) == baseline,"Playback translates retained ink without recompilation")
    var before: Image = root.get_texture().get_image()
    var event: Dictionary = state.duplicate(true)
    event.merge({"kind":"assessment","sequence":1,"note_id":str(heads.keys()[0]),
        "dimensions":{"pitch":"correct","onset":"on_time","release":"on_time"}},true)
    var outcome: String = feedback.ingest(event)
    check(outcome == "applied","Changed feedback is accepted by the actual ledger: " + outcome)
    await FramebufferTake.show(self,view,state,.25)
    RenderingServer.force_draw()
    var after: Image = root.get_texture().get_image()
    check(before.get_data() != after.get_data(),"Changed feedback updates the actual painted source head")
    check(generations(view) == baseline,"Feedback updates its status layer without recompiling source ink")
    print("IDLE_RENDERING_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
