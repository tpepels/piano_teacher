extends SceneTree
# The production app and its real handlers own the renderer. Only outbound
# HTTP and the sampling time are supplied by this deterministic wire fixture.
class SampledApp extends "native_production_fixture.gd":
    var sampled_clock := 0.0
    var model_loads := 0
    func _transport_beat_now() -> float:
        return sampled_clock
    func _on_timeline_model(result: int, code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
        model_loads += 1
        super._on_timeline_model(result,code,headers,body)

class CorruptedView extends "res://notation/native/view.gd":
    # Test-only render mutations keep the original model, source notes,
    # transport snapshots and glyph assets intact.
    var corruption := ""
    var cutoff := 0.0
    func present(state: Dictionary, transport: float, visual: float = NAN) -> void:
        if corruption == "changed-speed" and visual > cutoff:
            visual = cutoff+(visual-cutoff)*.5
        elif corruption == "repeat-jump" and visual >= float(practice_timeline.get("stride_beats",INF)):
            visual += .25
        super.present(state,transport,visual)

class CorruptedContextPainter extends "res://notation/native/context_painter.gd":
    # Preparation corruption belongs at the actual drawing policy. The source
    # model/transport snapshot stays correct for the independent pixel oracle.
    var corruption := ""
    var preparing := false
    var preparation_rule := 0

    func paint_preparation_measure(canvas, frame: RenderPass, measure: Dictionary, previous: Dictionary,
            gap: float, playhead: float, opening: bool = false) -> void:
        var candidate: Dictionary = measure.duplicate(true)
        var density: float = score_layout.timeline.pixels_per_beat
        if corruption == "compressed-rest":
            candidate["end_beat"] = float(candidate["start_beat"])+float(candidate["duration_beats"])*.5
        elif corruption == "translated-rest":
            candidate["start_beat"] = float(candidate["start_beat"])+.25
            candidate["end_beat"] = float(candidate["end_beat"])+.25
        elif corruption == "local-density":
            score_layout.timeline.pixels_per_beat = density*.5
        preparing = true
        preparation_rule = 0
        super.paint_preparation_measure(canvas,frame,candidate,previous,gap,playhead,opening)
        preparing = false
        score_layout.timeline.pixels_per_beat = density

    func practice_barline(canvas, frame: RenderPass, x: float, mark: Dictionary, gap: float) -> void:
        preparation_rule += 1
        var shift: float = 8.0 if preparing and corruption == "moved-boundary" and preparation_rule == 2 else 0.0
        super.practice_barline(canvas,frame,x+shift,mark,gap)
        if preparing and corruption == "duplicate-boundary" and preparation_rule == 1:
            super.practice_barline(canvas,frame,x+8.0,mark,gap)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var args := OS.get_cmdline_user_args()
    var folder: String = args[0]
    var configuration: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[1]))
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("native.json")))
    var frames: Array = []
    root.mode = Window.MODE_WINDOWED
    root.borderless = true
    for dimensions in configuration["viewports"]:
        root.size = Vector2i(int(dimensions[0]),int(dimensions[1]))
        var app := SampledApp.new()
        app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
        root.add_child(app)
        await process_frame
        await process_frame
        var error: String = app.load_native_fixture(folder)
        if not error.is_empty():
            push_error(error)
            quit(1)
            return
        var renderer: Control = app.practice_view.stage.renderer
        var corruption: String = str(configuration.get("corruption",""))
        if corruption in ["changed-speed","repeat-jump"]:
            renderer.set_script(CorruptedView)
            renderer.corruption = corruption
            renderer.cutoff = float(payload.model.duration_beats)-.25
            app._on_layout(0,200,PackedStringArray(),JSON.stringify(payload.layout).to_utf8_buffer())
            app._on_timeline_model(0,200,PackedStringArray(),JSON.stringify(payload.model).to_utf8_buffer())
            assert(app._native_score_ready(),renderer.failure_reason)
        elif not corruption.is_empty():
            var painter: CorruptedContextPainter = CorruptedContextPainter.new(renderer.layout,renderer.symbols)
            painter.corruption = corruption
            renderer.context_painter = painter
        # One public scale input, chosen before the first attempt and then
        # retained across all tempo/phase changes without reloading the model.
        assert(renderer.set_density(float(configuration["density"])))
        renderer.set_fingering_annotations_enabled(false)
        renderer.set_transport_overlay_enabled(false)
        app.practice_view.stage.feedback.visible = false
        await process_frame
        await process_frame
        var fixed_region := Rect2i()
        for tempo in configuration["tempos"]:
            for sample in configuration["samples"]:
                var state: Dictionary = payload["state"].duplicate(true)
                state.merge(sample.get("state",{}),true)
                var origin: float = float(sample["clock"])
                var clock = load("res://visual_transport_clock.gd").new()
                var clock_state := {"revision":app.revision,"transport_id":int(tempo),
                    "bpm":tempo,"running":true,"paused":false,"clock_beat":origin}
                clock.accept(clock_state,100000,100000)
                for index in range(int(sample.get("count",3))):
                    var elapsed_ms: int = roundi(float(index)*float(configuration["step_beats"])*60000.0/float(tempo))
                    var expected: float = origin+float(elapsed_ms)*float(tempo)/60000.0
                    if bool(sample.get("pause_roundtrip",false)):
                        var step_ms: int = roundi(float(configuration["step_beats"])*60000.0/float(tempo))
                        elapsed_ms = [0,1000,2000,2000,2000+step_ms][index]
                        expected = origin+maxf(0.0,float(elapsed_ms-2000))*float(tempo)/60000.0
                        if index == 1:
                            clock_state.merge({"running":false,"paused":true,"clock_beat":origin},true)
                            clock.accept(clock_state,100000,100000)
                        elif index == 3:
                            clock_state.merge({"running":true,"paused":false,"clock_beat":origin},true)
                            clock.accept(clock_state,102000,102000)
                    app.sampled_clock = clock.now(100000+elapsed_ms)
                    state.merge({"loaded":true,"revision":app.revision,"bpm":tempo,
                        "running":true,"paused":true,"phase":"paused","mode":"practice",
                        "hand":configuration.get("hand","both"),"score_loop_enabled":true,
                        "visual_offset_beats":0.0,"play_from_beat":0.0,
                        "clock_beat":app.sampled_clock,"count_in_beats":0.0,
                        "visual_gap_beats":configuration["gap_beats"]},true)
                    # Recovery snapshots use absolute visual coordinates, not
                    # another offset added to the semantic source measures.
                    if sample.has("state"):
                        state.merge(sample["state"],true)
                        state["paused"] = true
                        if not bool(state.get("running",false)):
                            state["visual_scroll_beat"] = app.sampled_clock
                    app._on_state(0,200,PackedStringArray(),JSON.stringify(state).to_utf8_buffer())
                    app._process(0.0)
                    renderer.queue_redraw()
                    await process_frame
                    await process_frame
                    RenderingServer.force_draw()
                    var picture: Image = root.get_texture().get_image()
                    var ratio: Vector2 = Vector2(picture.get_size())/root.get_visible_rect().size
                    var rect: Rect2 = renderer.get_global_rect()
                    var region := Rect2i(Vector2i((rect.position*ratio).round()),Vector2i((rect.size*ratio).round()))
                    if fixed_region.size == Vector2i.ZERO:
                        fixed_region = region
                    assert(region == fixed_region,"Sampling may not move or resize the fixed image ROI")
                    var tag := "%dx%d-%d-%s-%d" % [dimensions[0],dimensions[1],tempo,sample["name"],index]
                    picture.save_png(folder.path_join(tag+"-app.png"))
                    picture.get_region(region).save_png(folder.path_join(tag+".png"))
                    frames.append({"name":tag,"group":sample["name"],"index":index,
                        "file":tag+".png","app":tag+"-app.png","clock":expected,
                        "seconds":float(elapsed_ms)/1000.0,"bpm":tempo,
                        "viewport":dimensions,"density_input":configuration["density"],
                        "pixel_scale":ratio.x,"revision":app.revision,"model_loads":app.model_loads,
                        "loop_enabled":bool(state.get("score_loop_enabled",true))})
        app.free()
        await process_frame
    var output := FileAccess.open(folder.path_join("measure-frames.json"),FileAccess.WRITE)
    output.store_string(JSON.stringify({"frames":frames}))
    quit()
