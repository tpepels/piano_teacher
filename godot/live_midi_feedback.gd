extends RefCounted
## Resolve the current source attack map once per engraving revision.
## Each live MIDI event is then O(1), independent of score length.
## This module renders feedback only; backend grading remains authoritative.

var attack_map: Dictionary = {}
var note_by_id: Dictionary = {}
var revision := -1

func clear() -> void:
    attack_map.clear()
    note_by_id.clear()
    revision = -1

func bind_layout(source_layout: Dictionary, source_revision: int) -> void:
    clear()
    revision = source_revision
    attack_map = source_layout.get("attack_map", {}).duplicate()
    for note in source_layout.get("notes", []):
        if note is Dictionary:
            note_by_id[str(note.get("id", ""))] = note

## Stage reaction for one backend attack event from the acknowledged feedback
## channel. Delivered exactly once, so no sequence bookkeeping lives here.
## The event names its own take; only graded attacks on the bound engraving
## produce a reaction. Score ink is owned by NativeScoreFeedback.
## `age_ms` is how long ago the attack happened; the transient reaction (pulse,
## ghost, callout) is skipped when a backend stall delivered it late.
const MAX_REACTION_AGE_MS := 250.0
func react(event: Dictionary, effects, stage, current_revision: int,
        age_ms: float = 0.0) -> bool:
    if age_ms > MAX_REACTION_AGE_MS:
        return false
    if str(event.get("kind","attack")) != "attack" or \
            not bool(event.get("graded",false)) or \
            revision < 0 or revision != current_revision or \
            int(event.get("revision",-1)) != revision:
        return false
    var status: String = str(event.get("status", ""))
    if status == "unexpected":
        var reference: String = str(event.get("reference_source_id", ""))
        var reference_note_id: String = str(attack_map.get(reference, ""))
        var missed_note: Dictionary = note_by_id.get(reference_note_id, {})
        if missed_note.is_empty():
            return false
        effects.wrong_ghosts.append({
            "page": int(missed_note.get("page", 0)),
            "x": float(missed_note.get("x", 0.0)),
            "y": float(missed_note.get("y", 0.0)),
            "duration_ms": 420,
            "until_ms": Time.get_ticks_msec() + 420
        })
        if effects.wrong_ghosts.size() > 32:
            effects.wrong_ghosts.pop_front()
        stage.effects.react("unexpected")
        stage.impact_callout.call("react", "unexpected")
        return true
    if status not in ["on_time", "early", "late"]:
        return false
    var source: String = str(event.get("source_id", ""))
    var note_id: String = str(attack_map.get(source, ""))
    var hit_note: Dictionary = note_by_id.get(note_id, {})
    if hit_note.is_empty():
        return false
    effects.hit_pulses.append({
        "page": int(hit_note.get("page", 0)),
        "x": float(hit_note.get("x", 0.0)),
        "y": float(hit_note.get("y", 0.0)),
        "status": status,
        "note_id": note_id,
        "duration_ms": 220,
        "until_ms": Time.get_ticks_msec() + 220
    })
    if effects.hit_pulses.size() > 32:
        effects.hit_pulses.pop_front()
    stage.effects.react(status)
    stage.impact_callout.call("react", status)
    return true
