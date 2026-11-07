extends RefCounted
## Transient stage reactions only (beat accents and the impact callout).
## Score ink belongs to the note-status ledger and its retained strips;
## nothing here stores, positions or draws notes.

## Ungraded preview arrivals give a beat accent, never graded credit.
func record_preview(groups: Array, stage) -> void:
    if not groups.is_empty() and stage.effects != null:
        stage.effects.preview_react()

## Score feedback is graded, preview accents are not. Entering an ungraded
## mode discards any graded reaction still on screen. Grading, transport and
## score ink are untouched.
func transition_mode(state: Dictionary, stage) -> void:
    var ungraded: bool = bool(state.get("preview_only", false)) or \
        str(state.get("mode", "")) == "listen"
    if not ungraded:
        return
    if stage.impact_callout != null:
        stage.impact_callout.call("clear")
    if stage.effects != null and float(stage.effects.impact_energy) != 0.0:
        stage.effects.impact_energy = 0.0
        stage.effects.queue_redraw()
