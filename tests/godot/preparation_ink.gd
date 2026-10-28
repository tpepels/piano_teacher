extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("PREPARATION_INK_FAIL:", message)
func _initialize() -> void: call_deferred("run")
func frame() -> Image:
    await process_frame
    await process_frame
    RenderingServer.force_draw()
    return root.get_texture().get_image()

func run() -> void:
    var folder: String = OS.get_cmdline_user_args()[0]
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(1220,780)
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    await process_frame
    var error: String = app.load_native_fixture(folder)
    check(error.is_empty(),error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.timeline_preview
    for onset in [0.0,4.0]:
        app.last_state = {"loaded":true,"revision":app.revision,"running":false,
            "paused":false,"phase":"ready","clock_beat":0.0,"hand":"right",
            "mode":"practice","preview_only":true,"bpm":80,"transport_id":7,
            "play_from_beat":onset,"duration_beats":8.0,"count_in_beats":0.0}
        app._process(0.0)
        var original: Image = await frame()
        var repeated: Image = await frame()
        check(original.get_data() == repeated.get_data(),
            "Frozen native baseline is stable before preparation intervention")
        var heads: Dictionary = view.drawn_noteheads.duplicate()
        app.last_state.count_in_beats = 4.0
        app.last_state.running = true
        app.last_state.paused = false
        app.last_state.phase = "count_in"
        # An exact logical-pixel translation makes the independent before/
        # after pixel comparison insensitive to camera movement itself.
        app.last_state.clock_beat = -10.0/view.timeline.pixels_per_beat
        app._process(0.0)
        var prepared: Image = await frame()
        check(app.game_count_in.visible, "Backend count-in actually enables preparation lights")
        check(original.get_data() != prepared.get_data(), "Preparation intervention changes the actual stage")
        original.save_png(folder.path_join("original-%.0f.png" % onset))
        prepared.save_png(folder.path_join("prepared-%.0f.png" % onset))
        var pixel_scale := Vector2(original.get_size()) / root.get_visible_rect().size
        var transform: Transform2D = view.get_global_transform_with_canvas()
        var gap: float = view.staff_gap()
        var expected := 0
        var retained := 0
        var tested := 0
        for event in view.layout.ordered_events:
            if str(event.get("kind","")) != "note" or absf(float(event.beat)-onset) > .00001:
                continue
            var id: String = str(event.id)
            if not heads.has(id):
                continue
            var head: Vector2 = heads[id]
            check(view.drawn_noteheads.has(id), "Preparation retains the source head")
            if not view.drawn_noteheads.has(id):
                continue
            var after_head: Vector2 = view.drawn_noteheads[id]
            var displacement: Vector2 = (transform*after_head-transform*head)*pixel_scale
            check(absf(displacement.y) < .01, "Preparation preserves source pitch")
            var staff: String = str(event.get("staff","right"))
            var ink_left: Vector2 = (transform * (head-Vector2(gap*2.7,gap*2.0))) * pixel_scale
            var ink_right: Vector2 = (transform * (head+Vector2(-gap*.65,gap*2.0))) * pixel_scale
            for y in range(maxi(0,floori(ink_left.y)),mini(original.get_height(),ceili(ink_right.y))):
                var local_y: float = (float(y)/pixel_scale.y-view.global_position.y)
                var on_rail := false
                for line in range(5):
                    if absf(local_y-(view.layout.staff_center(staff)+(line-2)*gap)) < 2.0:
                        on_rail = true
                if on_rail:
                    continue
                for x in range(maxi(0,floori(ink_left.x)),mini(original.get_width(),ceili(ink_right.x))):
                    var before: Color = original.get_pixel(x,y)
                    if minf(before.r,minf(before.g,before.b)) > .65:
                        expected += 1
                        var after: Color = prepared.get_pixel(x+roundi(displacement.x),y+roundi(displacement.y))
                        if minf(after.r,minf(after.g,after.b)) > .65:
                            retained += 1
            tested += 1
        check(tested >= 2 and expected > 15,
            "Fixture contains actual accidental/ledger ink at source onset %.0f (%d pixels)" % [onset,expected])
        check(retained >= expected*.98,
            "Native preparation retains source accidental/ledger pixels at %.0f: %d/%d" % [onset,retained,expected])
    print("PREPARATION_INK_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
