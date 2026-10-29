extends SceneTree

class FixtureApp extends "native_production_fixture.gd":
    func _transport_beat_now() -> float:
        return float(last_state.get("clock_beat", 0.0))

var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("SCORE_BOUNDS_FAIL:", message)
func _initialize() -> void: call_deferred("run")

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    var app := FixtureApp.new()
    app.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(app)
    await process_frame
    var error: String = app.load_native_fixture(OS.get_cmdline_user_args()[0])
    check(error.is_empty(), error)
    if not error.is_empty():
        quit(1)
        return
    var view = app.practice_view.stage.renderer
    for dimensions in [Vector2i(1536,960),Vector2i(1024,768),Vector2i(800,600)]:
        root.size = dimensions
        await process_frame
        await process_frame
        var baseline := Rect2()
        var baseline_gap := 0.0
        for phase in ["ready","count_in","playing","paused","playing"]:
            app.last_state = {"loaded":true,"revision":app.revision,"phase":phase,
                "running":phase != "ready","paused":true,"clock_beat":0.0,
                "hand":"both","bpm":80,"play_from_beat":0.0,"count_in_beats":4.0,
                "hand_stages":[{"hand":"left","active":true},{"hand":"right"},{"hand":"both"}]}
            app.practice_view.stage._update_hand_stages(app.last_state)
            app._process(0.0)
            view.queue_redraw()
            await process_frame
            await process_frame
            RenderingServer.force_draw()
            if baseline.size == Vector2.ZERO:
                baseline = view.get_global_rect()
                baseline_gap = view.staff_gap()
            check(view.get_global_rect() == baseline and is_equal_approx(view.staff_gap(),baseline_gap),
                "%s %s: transport preserves actual notation scale" % [dimensions,phase])
            check(app.practice_view.stage.score_frame.get_global_rect().encloses(view.get_global_rect()),
                "Native notation stays inside the music stage")
            check(view.size.y >= 135.0 and not view.drawn_noteheads.is_empty(),
                "Compact stage contains real painted source notes")
            for point in view.drawn_noteheads.values():
                check(point.y > view.staff_gap() and point.y < view.size.y-view.staff_gap(),
                    "%s: complete notehead fits vertically" % dimensions)
            # Test the authentic source note/accidental bounds, not a raster
            # crop or a self-reported boolean that bypasses drawing.
            var gap: float = view.staff_gap()
            var heads: Dictionary = view.layout.engraved_head_offsets(gap)
            var offsets: Dictionary = view.Geometry.accidental_offsets(
                view.layout.ordered_events,gap,heads,view.glyphs.bounds)
            for event in view.layout.ordered_events:
                if not view.drawn_noteheads.has(str(event.get("id",""))):
                    continue
                var ink: Rect2 = view.layout.event_ink_rect(event,gap,heads,offsets)
                check(ink.position.y >= 0.0 and ink.end.y <= view.size.y,
                    "%s: authentic source glyph bounds fit without clipping" % dimensions)
            check(app._native_score_ready(), "Responsive layout keeps the production revision ready")
    print("SCORE_BOUNDS_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
