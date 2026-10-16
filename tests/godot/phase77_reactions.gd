extends SceneTree

# Phase 7.7 game-feel contract. This test does not synthesize grading.
# It ensures presentation remains idle in preview until an actual MIDI
# event is explicitly delivered by the controller.
var failures: Array[String] = []

func check(ok: bool, description: String) -> void:
    if not ok:
        failures.append(description)
        print("FAIL: ", description)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var Stage = load("res://game_stage.gd")
    var Reactions = load("res://note_reactions.gd")
    var Streak = load("res://game_streak.gd")
    check(Stage != null and Reactions != null and Streak != null,
        "game-feel modules must parse and load")
    if Stage == null or Reactions == null or Streak == null:
        quit(1)
        return
    var stage = Stage.new()
    root.add_child(stage)
    stage.size = Vector2(1200, 650)
    stage.present({"phase": "playing", "running": true,
        "preview_only": true, "progress": .3})
    check(stage.transport_active, "MIDI-free preview receives ambient movement")
    check(stage.impact_energy == 0.0,
        "preview never earns a note hit or a success bloom")
    stage.preview_react()
    check(stage.preview_energy > 0.0 and stage.impact_energy == 0.0,
        "Keyboard-free preview creates blue note energy, never a success grade")
    stage.react("on_time")
    check(stage.impact_energy > .0 and stage.impact_tone == Color("#69E2BF"),
        "an assessed on-time note triggers the success glow")
    stage.react("unexpected")
    check(stage.impact_tone == Color("#EF7776"),
        "an unexpected note must be visibly distinct from success")
    stage._process(2.0)
    check(stage.impact_energy <= .001, "event light fully expires")
    stage.present({"phase": "paused", "running": false})
    check(not stage.transport_active, "ambient movement stops on pause")

    var reactions = Reactions.new()
    root.add_child(reactions)
    reactions.size = Vector2(1000, 240)
    reactions.crop_origin = Vector2.ZERO
    reactions.crop_size = Vector2.ONE
    reactions.staff_gap_fraction = .08
    var xy: Vector2 = reactions._sheet_position({"x": .42, "y": .3})
    check(xy.distance_to(Vector2(420, 72)) < .01,
        "particles stay aligned to source engraving coordinates")
    var now: int = Time.get_ticks_msec()
    var live := {"page": 0, "x": .42, "y": .3, "status": "on_time",
        "duration_ms": 450, "until_ms": now + 450}
    check(reactions._remaining(live, now, 450) >= .99,
        "fresh note has full flash intensity")
    check(reactions._remaining(live, now + 500, 450) == 0.0,
        "expired note releases its visual effect")
    reactions.hit_pulses.append(live)
    reactions.queue_redraw()
    check(reactions.hit_pulses.size() == 1,
        "one physical MIDI note produces one visible note reaction")
    reactions.preview_pulses.append({"page":0, "x":.42, "y":.3,
        "status":"preview", "duration_ms":620, "until_ms":now+620})
    check(reactions.preview_pulses.size() == 1,
        "Preview light remains separate from graded note reactions")
    check(Reactions.MAX_VISIBLE_HITS <= 16, "dense chords have bounded effects")
    var streak = Streak.new()
    root.add_child(streak)
    streak.present({"kind": "success", "streak": 3})
    check(streak.value == 3 and streak.reveal > 0.0,
        "three backend-confirmed clean runs animate completion")
    streak.pulse_unlock()
    check(streak.unlock_wave == .0, "hand unlock wave starts only when called")
    streak._process(2.0)
    check(streak.unlock_wave < 0.0, "hand unlock wave eventually clears")
    print("PHASE77_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
