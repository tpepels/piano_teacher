extends SceneTree
## Transient stage reactions for backend attack events. Score ink is covered
## by native_score_feedback.gd and the real-framebuffer test.
const Feedback := preload("res://live_midi_feedback.gd")

class Responses:
    extends RefCounted
    var reactions: Array = []
    func react(kind: String) -> void:
        reactions.append(kind)

class Stage:
    extends RefCounted
    var effects = Responses.new()
    var impact_callout = Responses.new()

func _initialize() -> void:
    var failed := 0
    var feedback := Feedback.new()
    var stage := Stage.new()
    feedback.bind_layout({"attack_map":{"src-a":"id-a","src-b":"id-b"}},4)
    var take := {"piece_fingerprint":"p","revision":4,"transport_id":7,
        "mode":"practice","graded":true}
    var hit: Dictionary = take.merged({"kind":"attack","sequence":1,
        "source_id":"src-a","status":"on_time"})
    if not feedback.react(hit,stage,4) or stage.effects.reactions != ["on_time"] or \
            stage.impact_callout.reactions != ["on_time"]:
        failed += 1
    # A wrong pitch reacts only when it references a real engraved note.
    var wrong: Dictionary = take.merged({"kind":"attack","sequence":2,
        "reference_source_id":"src-b","status":"unexpected"})
    var stray: Dictionary = take.merged({"kind":"attack","sequence":3,
        "reference_source_id":"","status":"unexpected"})
    if not feedback.react(wrong,stage,4) or feedback.react(stray,stage,4) or \
            stage.effects.reactions != ["on_time","unexpected"]:
        failed += 1
    var ungraded: Dictionary = hit.duplicate()
    ungraded["graded"] = false
    var release: Dictionary = take.merged({"kind":"release","source_id":"src-a",
        "release":"short"})
    var stale: Dictionary = hit.duplicate()
    stale["revision"] = 3
    var unmapped: Dictionary = hit.duplicate()
    unmapped["source_id"] = "src-z"
    for event in [ungraded,release,stale,unmapped]:
        if feedback.react(event,stage,4):
            failed += 1
    # A backend stall delivers old attacks: no burst of late reactions.
    if feedback.react(hit,stage,4,900.0) or not feedback.react(hit,stage,4,100.0):
        failed += 1
    feedback.clear()
    if feedback.react(hit,stage,4):
        failed += 1
    print("LIVE_MIDI_FEEDBACK_FAILURES:",failed)
    quit(0 if failed==0 else 1)
