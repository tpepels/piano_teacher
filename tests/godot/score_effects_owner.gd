extends SceneTree
const ScoreEffects := preload("res://score_effects.gd")

class Canvas:
    extends RefCounted
    var preview_calls := 0
    var redraws := 0
    var impact_energy := 2.0
    func preview_react() -> void:
        preview_calls += 1
    func queue_redraw() -> void:
        redraws += 1

class Callout:
    extends RefCounted
    var clears := 0
    func clear() -> void:
        clears += 1

class Stage:
    extends RefCounted
    var effects = Canvas.new()
    var impact_callout = Callout.new()

func _initialize() -> void:
    var failures := 0
    var stage := Stage.new()
    var effects := ScoreEffects.new()
    effects.record_preview([{"notes":[{"x":12.0,"y":5.0,"page":0}]}],
        stage,1000)
    if effects.preview_pulses.size()!=1 or \
            effects.preview_pulses[0]["until_ms"]!=1220 or \
            stage.effects.preview_calls!=1:
        failures += 1
    effects.hit_pulses.append({"until_ms":1500})
    effects.transition_mode({"mode":"listen"},stage)
    if not effects.hit_pulses.is_empty() or \
            stage.effects.impact_energy!=0.0 or stage.effects.redraws!=1:
        failures += 1
    effects.transition_mode({"mode":"practice"},stage)
    if not effects.preview_pulses.is_empty():
        failures += 1
    print("SCORE_EFFECTS_OWNER_FAILURES:",failures)
    quit(0 if failures==0 else 1)
