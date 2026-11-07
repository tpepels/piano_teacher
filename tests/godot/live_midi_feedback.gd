extends SceneTree
const Feedback := preload("res://live_midi_feedback.gd")

class ScoreEffects:
    extends RefCounted
    var hit_pulses: Array = []
    var wrong_ghosts: Array = []

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
    var particles := ScoreEffects.new()
    var stage := Stage.new()
    feedback.bind_layout({
        "attack_map":{"src-a":"id-a","src-b":"id-b"},
        "notes":[
            {"id":"id-a","x":12.0,"y":13.0,"page":0},
            {"id":"id-b","x":22.0,"y":23.0,"page":1}]},4)
    var take := {"piece_fingerprint":"p","revision":4,"transport_id":7,
        "mode":"practice","graded":true}
    var hit: Dictionary = take.merged({"kind":"attack","sequence":1,
        "source_id":"src-a","status":"on_time"})
    if not feedback.react(hit,particles,stage,4) or \
            particles.hit_pulses.size()!=1 or \
            particles.hit_pulses[0]["note_id"]!="id-a" or \
            stage.effects.reactions!=["on_time"]:
        failed += 1
    var wrong: Dictionary = take.merged({"kind":"attack","sequence":2,
        "reference_source_id":"src-b","status":"unexpected"})
    if not feedback.react(wrong,particles,stage,4) or \
            particles.wrong_ghosts.size()!=1 or \
            particles.wrong_ghosts[0]["page"]!=1:
        failed += 1
    # Ungraded (preview/listen) attacks never react, whatever the UI state.
    var ungraded: Dictionary = hit.duplicate()
    ungraded["graded"] = false
    if feedback.react(ungraded,particles,stage,4) or particles.hit_pulses.size()!=1:
        failed += 1
    # Release and assessment events are score ink, not stage reactions.
    var release: Dictionary = take.merged({"kind":"release","source_id":"src-a",
        "release":"short"})
    if feedback.react(release,particles,stage,4) or particles.hit_pulses.size()!=1:
        failed += 1
    # An event for another engraving revision cannot react on this one.
    var stale: Dictionary = hit.duplicate()
    stale["revision"] = 3
    if feedback.react(stale,particles,stage,4) or particles.hit_pulses.size()!=1:
        failed += 1
    feedback.clear()
    if feedback.react(hit,particles,stage,4) or particles.hit_pulses.size()!=1:
        failed += 1
    print("LIVE_MIDI_FEEDBACK_FAILURES:",failed)
    quit(0 if failed==0 else 1)
