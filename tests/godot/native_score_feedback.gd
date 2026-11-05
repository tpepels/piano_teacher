extends SceneTree

class GlyphRecorder extends RefCounted:
    var paints: Array = []
    func paint(_canvas: CanvasItem, name: String, x: float, y: float,
            gap: float, tone: Color, centered: bool = false) -> bool:
        paints.append({"name":name,"x":x,"y":y,"gap":gap,
            "tone":tone,"centered":centered})
        return true

class Score extends Control:
    var glyphs := GlyphRecorder.new()
    var drawn_noteheads := {"attack-a":Vector2(100,80),
        "attack-b":Vector2(170,80),"attack-c":Vector2(225,80)}
    var layout := {"ordered_events":[
        {"id":"attack-a","kind":"note","note_type":"quarter",
            "source_id":"source-a","is_attack":true},
        {"id":"attack-b","kind":"note","note_type":"half",
            "source_id":"source-b","is_attack":true},
        {"id":"attack-c","kind":"note","note_type":"whole",
            "source_id":"source-c","is_attack":true}]}
    func staff_gap() -> float:
        return 16.0

var failures: Array[String] = []
func check(ok: bool, label: String) -> void:
    if not ok:
        failures.append(label)
        push_error(label)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var script = load("res://native_score_feedback.gd")
    if script == null:
        quit(1)
        return
    var score := Score.new()
    root.add_child(score)
    score.size = Vector2(300,160)
    var feedback = script.new()
    root.add_child(feedback)
    feedback.size = Vector2(300,160)
    feedback.bind_score(score, 7)
    var design = load("res://practice_theme.gd")
    for status in ["assisted", "short", "long", "early", "late"]:
        check(feedback._tone(status) == design.AMBER, status+" keeps supportive amber feedback")
    check(feedback._tone("wrong") == design.CORAL, "Wrong pitch remains distinct from assisted success")
    var state := {"revision":7, "mode":"practice", "phase":"playing",
        "running":true, "transport_id":8, "preview_only":false,
        "feedback_marks":[{"note_id":"attack-b", "status":"missed"},
            {"note_id":"attack-c", "status":"early"},
            {"note_id":"missing", "status":"correct", "estimated":true}],
        "midi_visual_events":[{"sequence":1, "source_id":"source-a",
            "transport_id":8, "status":"on_time", "age":.02}]}
    feedback.present(state)
    check(feedback.markers.has("attack-b"), "Missed note uses exact engraved identity")
    check(feedback.pulses.size() == 1 and feedback.pulses[0].id == "attack-a",
        "Physical note targets its own source identity despite repeated pitch")
    feedback.present(state)
    check(feedback.pulses.size() == 1, "Repeated polling cannot repeat a MIDI reward")
    check(not feedback.markers.has("missing"),
        "Estimated/unmapped feedback cannot falsely color a note")
    # The feedback layer actually draws native Verovio HEAD glyph masks, not
    # merely halos around the still-white source heads.
    feedback.queue_redraw()
    await process_frame
    await process_frame
    var paints: Array = score.glyphs.paints
    check(paints.any(func(p): return p.name == "head_black" and
        p.x == 100.0 and p.tone.r == design.MINT.r and
        p.tone.g == design.MINT.g and p.tone.b == design.MINT.b and
        p.tone.a > 0.0),
        "Immediate played quarter-note head fills mint")
    check(paints.any(func(p): return p.name == "head_half" and
        p.x == 170.0 and p.tone.r == design.CORAL.r and
        p.tone.g == design.CORAL.g and p.tone.b == design.CORAL.b and
        p.tone.a > .5),
        "Graded missed half-note head takes authentic red contour")
    check(paints.any(func(p): return p.name == "head_whole" and
        p.x == 225.0 and p.tone.r == design.AMBER.r and
        p.tone.g == design.AMBER.g and p.tone.b == design.AMBER.b and
        p.tone.a > .5),
        "Mistimed whole-note head retains its hollow amber contour")
    check(paints.all(func(p): return bool(p.centered) and p.gap == 16.0),
        "Tint uses exact source head centers and original Verovio staff scale")
    state.feedback_marks = []
    feedback.present(state)
    check(feedback.markers.has("attack-b") and
        feedback.markers.has("attack-c"),
        "Previously assessed note colors remain during the same attempt")
    var next_take := state.duplicate(true)
    next_take.transport_id = 9
    next_take.midi_visual_events = []
    feedback.present(next_take)
    check(feedback.markers.is_empty(),
        "A new transport take cannot inherit past colored noteheads")
    feedback.present(state)
    check(feedback.note_position("attack-a") == Vector2(100,80), "Uses painted native coordinate")
    score.drawn_noteheads["attack-a"] = Vector2(45,80)
    check(feedback.note_position("attack-a") == Vector2(45,80), "Feedback follows scrolling note")
    check(feedback.note_position("missing") == Vector2.INF, "Unknown identities never guess a position")
    state.preview_only = true
    state.midi_visual_events[0].sequence = 2
    feedback.present(state)
    check(feedback.markers.is_empty() and feedback.pulses.is_empty(), "Preview cannot retain earned feedback")
    state.preview_only = false
    feedback.present(state)
    check(feedback.pulses.is_empty(), "Returning from preview cannot replay its old events")
    state.mode = "listen"
    feedback.present(state)
    check(feedback.markers.is_empty() and feedback.pulses.is_empty(), "Listen cannot award feedback")
    state.mode = "practice"
    state.revision = 6
    feedback.present(state)
    check(feedback.markers.is_empty(), "Stale lesson cannot mark current notes")
    print("NATIVE_FEEDBACK_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
