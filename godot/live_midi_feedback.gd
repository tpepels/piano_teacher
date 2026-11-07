extends RefCounted
## Resolve the current engraving's source attacks once per revision, so each
## live MIDI event is O(1). Drives transient stage reactions only; backend
## grading stays authoritative and score ink belongs to the status ledger.

var attack_map: Dictionary = {}
var revision := -1

func clear() -> void:
    attack_map.clear()
    revision = -1

func bind_layout(source_layout: Dictionary, source_revision: int) -> void:
    clear()
    revision = source_revision
    attack_map = source_layout.get("attack_map", {}).duplicate()

## Stage reaction for one backend attack event from the acknowledged feedback
## channel. Delivered exactly once, so no sequence bookkeeping lives here.
## The event names its own take; only graded attacks on the bound engraving
## produce a reaction. Score ink is owned by NativeScoreFeedback.
## `age_ms` is how long ago the attack happened; the transient reaction (effect,
## callout) is skipped when a backend stall delivered it late.
const MAX_REACTION_AGE_MS := 250.0
func react(event: Dictionary, stage, current_revision: int,
        age_ms: float = 0.0) -> bool:
    if age_ms > MAX_REACTION_AGE_MS:
        return false
    if str(event.get("kind","attack")) != "attack" or \
            not bool(event.get("graded",false)) or \
            revision < 0 or revision != current_revision or \
            int(event.get("revision",-1)) != revision:
        return false
    var status: String = str(event.get("status", ""))
    var mapped: String = str(event.get(
        "reference_source_id" if status == "unexpected" else "source_id", ""))
    # React only to an attack tied to a real engraved note of this revision.
    if status not in ["on_time", "early", "late", "unexpected"] or \
            not attack_map.has(mapped):
        return false
    stage.effects.react(status)
    stage.impact_callout.call("react", status)
    return true
