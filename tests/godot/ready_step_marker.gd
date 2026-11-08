extends SceneTree
const NativeAssets := preload("res://native_score_assets.gd")
const FramebufferTake := preload("framebuffer_take.gd")
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("READY_STEP_MARKER_FAIL:",message)

func settle() -> void:
    for frame in range(5):
        await process_frame

func run() -> void:
    var payload: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(
        OS.get_cmdline_user_args()[0]))
    var screen = load("res://practice_screen.gd").new()
    root.size = Vector2i(1220,780)
    root.add_child(screen)
    screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    await settle()
    var stage = screen.stage
    var renderer = stage.renderer
    var installed: Dictionary = NativeAssets.install(renderer,payload.layout)
    check(bool(installed.get("ok",false)),"Authentic MIDI engraving assets install")
    for density in [96.0,300.0]:
        renderer.clear_score()
        check(renderer.set_density(density),"Stopped source accepts the selected density")
        check(renderer.load_score(payload.model),"Authentic native source model loads")
        renderer.visible = true
        await settle()
        for hand in ["right","left","both"]:
            var first := 12.0 if hand == "left" else 8.0
            var heading := {"loaded":true,"running":false,"paused":false,
                "phase":"ready","hand":hand,"lesson_step":1,"lesson_steps":2,
                "stage_label":"Original notes and rhythm","play_from_beat":0.0}
            renderer.present(heading,0.0,0.0)
            stage.present_runway_steps(heading,0.0,20.0,"Next source",220.0)
            await settle()
            check(stage.runway_steps._beat == 0.0,
                "Future renderer marker retains its own global source camera during READY")
            var first_id := ""
            for event in renderer.layout.ordered_events:
                if str(event.get("kind","")) == "note" and \
                        bool(event.get("is_attack",false)) and \
                        str(event.get("staff","")) == ("left" if hand == "left" else "right") and \
                        absf(float(event.get("beat",-1))-first) < .001:
                    first_id = str(event.id)
                    break
            # READY holds its take hidden offscreen until Play
            # (docs/architecture/immutable-score-queues.md); the marker's
            # own camera is checked here, the head alignment under Play below.
            check(not renderer.drawn_noteheads.has(first_id),
                "READY keeps its source take offscreen at %.0f px/beat" % density)
            check(renderer.clock_beat == 0.0 and renderer.play_from_beat == 0.0,
                "READY camera projection preserves the source transport origin")
            # Playback uses the real source clock, including its written rest.
            heading.running = true
            heading.phase = "playing"
            # A moving take whose origin is beat 0, on the monotonic world axis.
            renderer.clear_score()
            check(renderer.set_density(density) and renderer.load_score(payload.model),
                "Source reloads for the moving take")
            await FramebufferTake.show(self,renderer,heading,first,first)
            stage.present_runway_steps(heading,first)
            await settle()
            check(renderer.drawn_noteheads.has(first_id),"Playback retains its first source attack")
            if renderer.drawn_noteheads.has(first_id):
                var moving: Vector2 = renderer.drawn_noteheads[first_id]
                check(moving.x > 0 and moving.x < renderer.size.x,
                    "Long-rest playback exposes authentic note ink")
                check(absf(stage.runway_steps.marker_x(stage.runway_steps._current_start,
                    stage.runway_steps._current_beat,stage.runway_steps._density,
                    stage.runway_steps.size.x)-moving.x) < .01,
                    "Playing marker follows the authoritative source clock")
            heading.paused = true
            heading.phase = "paused"
            renderer.present(heading,first,first)
            stage.present_runway_steps(heading,first)
            await settle()
            check(absf(stage.runway_steps._beat-first) < .001,
                "Pause does not activate the READY camera preview")
    screen.free()
    print("READY_STEP_MARKER_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
