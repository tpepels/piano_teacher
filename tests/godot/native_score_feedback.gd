extends SceneTree

class Score extends Control:
    var drawn_noteheads := {"attack-a":Vector2(100,80), "attack-b":Vector2(170,80)}
    var ordered_events := [
        {"id":"attack-a", "source_id":"source-a", "is_attack":true},
        {"id":"attack-b", "source_id":"source-b", "is_attack":true}]
    func _gap() -> float:
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
    var feedback = script.new()
    root.add_child(feedback)
    feedback.bind_score(score, 7)
    var design = load("res://practice_theme.gd")
    for status in ["assisted", "short", "long", "early", "late"]:
        check(feedback._tone(status) == design.AMBER, status+" keeps supportive amber feedback")
    check(feedback._tone("wrong") == design.CORAL, "Wrong pitch remains distinct from assisted success")
    var state := {"revision":7, "mode":"practice", "phase":"playing",
        "running":true, "transport_id":8, "preview_only":false,
        "feedback_marks":[{"note_id":"attack-b", "status":"missed"}],
        "midi_visual_events":[{"sequence":1, "source_id":"source-a",
            "transport_id":8, "status":"on_time", "age":.02}]}
    feedback.present(state)
    check(feedback.markers.has("attack-b"), "Missed note uses exact engraved identity")
    check(feedback.pulses.size() == 1 and feedback.pulses[0].id == "attack-a",
        "Physical note targets its own source identity despite repeated pitch")
    feedback.present(state)
    check(feedback.pulses.size() == 1, "Repeated polling cannot repeat a MIDI reward")
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
