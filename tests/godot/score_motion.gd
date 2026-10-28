extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    # Sample deterministic backend snapshots through the production process.
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
var app: FixtureApp

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("SCORE_MOTION_FAIL:", message)

func _initialize() -> void: call_deferred("run")

func sample(beat: float, bpm: float = 80.0, start: float = 0.0) -> Dictionary:
    app.last_state = {"loaded":true, "revision":app.revision,
        "running":true, "paused":true, "phase":"count_in" if beat < 0.0 else "playing",
        "mode":"practice", "preview_only":true, "clock_beat":beat,
        "bpm":bpm, "hand":"both", "transport_id":198,
        "play_from_beat":start, "count_in_beats":4.0,
        "duration_beats":app.timeline_preview.timeline.duration_beats}
    app._process(0.0)
    app.timeline_preview.queue_redraw()
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    return app.timeline_preview.drawn_noteheads.duplicate()

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536,960)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var error: String = app.load_native_fixture(folder)
    check(error.is_empty(), error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.timeline_preview
    var source: Dictionary = view.timeline.model.duplicate(true)
    var size_before: Vector2 = view.size
    var position_before: Vector2 = view.position
    var density: float = view.timeline.pixels_per_beat
    var results: Array = []
    var checked := 0
    # Every source attack, including later systems, must be present when its
    # backend beat reaches the fixed line. Measure the painted head twice;
    # chord offsets are fixed source ink and cancel from the travel oracle.
    for event in view.layout.ordered_events:
        if str(event.get("kind", "")) != "note":
            continue
        var id: String = str(event.id)
        var onset: float = float(event.beat)
        var before: Dictionary = await sample(onset-.125)
        var after: Dictionary = await sample(onset+.125)
        check(before.has(id) and after.has(id), "Source note remains painted around onset: " + id)
        if not before.has(id) or not after.has(id):
            continue
        var a: Vector2 = before[id]
        var b: Vector2 = after[id]
        check(absf((a.x-b.x)-density*.25) < .02,
            "Painted source head travels at constant density: " + id)
        check(absf(a.y-b.y) < .01, "Scrolling preserves source pitch: " + id)
        check(absf((a.x+b.x)*.5-view.size.x*.42) < view.staff_gap()*1.1,
            "Authentic head crosses timing line on source beat: " + id)
        check(view.size == size_before and view.position == position_before,
            "The native viewport stays fixed while notation moves")
        results.append({"id":id,"beat":onset,"before":a.x,"after":b.x})
        checked += 1
    check(checked >= 3, "Fixture checks several actual painted attacks")
    # Negative count-in, seek offsets, and each tempo use that same axis.
    for bpm in [40.0,80.0,120.0]:
        for start in [0.0, minf(4.0,view.timeline.duration_beats*.5)]:
            var baseline: Dictionary = await sample(-.1,bpm,start)
            var later: Dictionary = await sample(-.1+bpm/60.0*.05,bpm,start)
            var shared := 0
            for painted_id in baseline:
                if later.has(painted_id):
                    check(absf((baseline[painted_id].x-later[painted_id].x)-density*bpm/60.0*.05) < .02,
                        "Count-in and seeks preserve tempo travel")
                    shared += 1
            check(shared > 0, "Count-in/seek samples contain authentic note ink")
    # Explicit source bar boundaries cannot introduce a speed change.
    for measure in view.timeline.measures:
        var boundary: float = float(measure.start_beat)
        var a: Dictionary = await sample(boundary-.001)
        var b: Dictionary = await sample(boundary+.001)
        var common := 0
        for painted_id in a:
            if b.has(painted_id):
                check(absf((a[painted_id].x-b[painted_id].x)-density*.002) < .02,
                    "Measure/system boundary never jumps or stalls")
                common += 1
        check(common > 0, "Boundary contains visible real notation")
    var paused: Dictionary = await sample(1.0)
    await create_timer(.05).timeout
    app._process(0.0)
    await process_frame
    check(view.drawn_noteheads == paused, "Paused notation stays fixed across wall time")
    check(view.timeline.model == source, "Motion never rewrites source events")
    check(app._native_score_ready(), "Production remains ready after all motion samples")
    var output := FileAccess.open(folder.path_join("samples.json"), FileAccess.WRITE)
    output.store_string(JSON.stringify(results))
    print("SCORE_MOTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
