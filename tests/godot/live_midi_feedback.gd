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
    var state := {"phase":"playing","transport_id":7,
        "midi_visual_events":[{"sequence":1,"transport_id":7,
            "source_id":"src-a","status":"on_time","age":0.0}]}
    var last: int = feedback.consume(state,particles,stage,0,4)
    if last != 1 or particles.hit_pulses.size()!=1 or \
            particles.hit_pulses[0]["note_id"]!="id-a" or \
            stage.effects.reactions!=["on_time"]:
        failed += 1
    # A repeated datagram cannot produce a second grade-colored animation.
    last = feedback.consume(state,particles,stage,last,4)
    if last!=1 or particles.hit_pulses.size()!=1:
        failed += 1
    state["midi_visual_events"] = [{"sequence":2,"transport_id":7,
        "reference_source_id":"src-b","status":"unexpected","age":0.1}]
    last = feedback.consume(state,particles,stage,last,4)
    if last!=2 or particles.wrong_ghosts.size()!=1 or \
            particles.wrong_ghosts[0]["page"]!=1:
        failed += 1
    state["mode"] = "listen"
    state["midi_visual_events"] = [{"sequence":3,"transport_id":7,
        "source_id":"src-a","status":"on_time","age":0.0}]
    last = feedback.consume(state,particles,stage,last,4)
    if last!=3 or particles.hit_pulses.size()!=1:
        failed += 1
    state.erase("mode")
    feedback.clear()
    state["midi_visual_events"] = [{"sequence":4,"transport_id":7,
        "source_id":"src-a","status":"on_time","age":0.0}]
    last = feedback.consume(state,particles,stage,last,4)
    if last!=4 or particles.hit_pulses.size()!=1:
        failed += 1
    print("LIVE_MIDI_FEEDBACK_FAILURES:",failed)
    quit(0 if failed==0 else 1)
