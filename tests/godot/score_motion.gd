extends SceneTree
const FramebufferTake := preload("framebuffer_take.gd")

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

func sample(world: float) -> Dictionary:
    # The world axis is monotonic and wall-clock driven in the application, so
    # this harness presents explicit world positions in ascending order: one
    # take whose origin is beat 0, as a framebuffer audit of moving ink needs.
    var view = app.practice_view.stage.renderer
    var state: Dictionary = {"loaded":true, "running":true, "paused":false,
        "phase":"count_in" if world < 0.0 else "playing", "mode":"practice",
        "bpm":80.0, "hand":"both", "transport_id":198, "play_from_beat":0.0,
        "count_in_beats":4.0, "duration_beats":view.timeline.duration_beats}
    await FramebufferTake.show(self, view, state, world)
    RenderingServer.force_draw()
    return view.drawn_noteheads.duplicate()

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1536,960)
    app = FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var error: String = await app.load_native_fixture(folder)
    check(error.is_empty(), error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.practice_view.stage.renderer
    var source: Dictionary = view.timeline.model.duplicate(true)
    # Start from an empty strip so the harness admits the one take it samples.
    view._stream_release_all()
    var size_before: Vector2 = view.size
    var position_before: Vector2 = view.position
    var density: float = view.timeline.pixels_per_beat
    var results: Array = []
    var checked := 0
    # Every sample is a world position; take them in ascending order and keep
    # the painted heads of each.
    var worlds: Dictionary = {}
    for event in view.layout.ordered_events:
        if str(event.get("kind", "")) == "note":
            worlds[float(event.beat)-.125] = true
            worlds[float(event.beat)+.125] = true
    for measure in view.timeline.measures:
        worlds[float(measure.start_beat)-.001] = true
        worlds[float(measure.start_beat)+.001] = true
    var ordered: Array = worlds.keys()
    ordered.sort()
    var painted: Dictionary = {}
    for world in ordered:
        painted[world] = await sample(world)
    # Every source attack, including later systems, must be present when its
    # beat reaches the fixed line; chord offsets are fixed source ink.
    for event in view.layout.ordered_events:
        if str(event.get("kind", "")) != "note":
            continue
        var id: String = str(event.id)
        var onset: float = float(event.beat)
        var before: Dictionary = painted[onset-.125]
        var after: Dictionary = painted[onset+.125]
        check(before.has(id) and after.has(id), "Source note remains painted around onset: " + id)
        if not before.has(id) or not after.has(id):
            continue
        var a: Vector2 = before[id]
        var b: Vector2 = after[id]
        check(absf((a.x-b.x)-density*.25) < .02,
            "Painted source head travels at constant density: " + id)
        check(absf(a.y-b.y) < .01, "Scrolling preserves source pitch: " + id)
        check(absf((a.x+b.x)*.5-view.size.x*view.PLAYHEAD_FRACTION) < view.staff_gap()*1.1,
            "Authentic head crosses timing line on source beat: " + id)
        check(view.size == size_before and view.position == position_before,
            "The native viewport stays fixed while notation moves")
        results.append({"id":id,"beat":onset,"before":a.x,"after":b.x})
        checked += 1
    check(checked >= 3, "Fixture checks several actual painted attacks")
    # Explicit source bar boundaries cannot introduce a speed change.
    for measure in view.timeline.measures:
        var boundary: float = float(measure.start_beat)
        var a: Dictionary = painted[boundary-.001]
        var b: Dictionary = painted[boundary+.001]
        var common := 0
        for painted_id in a:
            if b.has(painted_id):
                check(absf((a[painted_id].x-b[painted_id].x)-density*.002) < .02,
                    "Measure/system boundary never jumps or stalls")
                common += 1
        check(common > 0, "Boundary contains visible real notation")
    # The same world position paints the same ink: a held axis stays fixed.
    var held: Dictionary = await sample(float(ordered[-1]))
    await create_timer(.05).timeout
    check(await sample(float(ordered[-1])) == held, "A held world position stays fixed across wall time")
    check(view.timeline.model == source, "Motion never rewrites source events")
    check(app._native_score_ready(), "Production remains ready after all motion samples")
    var output := FileAccess.open(folder.path_join("samples.json"), FileAccess.WRITE)
    output.store_string(JSON.stringify(results))
    print("SCORE_MOTION_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
