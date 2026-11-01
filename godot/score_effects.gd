extends RefCounted
# Source-event queues for stage reactions. NativeScoreFeedback owns visible
# score marks; these queues never draw or transform page-coordinate ink.
var marks: Array = []
var hit_pulses: Array = []
var wrong_ghosts: Array = []
var preview_pulses: Array = []

func prune_expired(ticks_ms: int) -> void:
    # Visual lifespan only. No scoring, timing, or MIDI input is modified.
    for queue in [hit_pulses, wrong_ghosts, preview_pulses]:
        for index in range(queue.size() - 1, -1, -1):
            if int(queue[index].get("until_ms", 0)) <= ticks_ms:
                queue.remove_at(index)

func record_preview(groups: Array, stage, ticks_ms: int) -> void:
    # Ungraded note arrivals cannot create graded MIDI feedback.
    if groups.is_empty():
        return
    for group in groups:
        for note in group.get("notes", []):
            if preview_pulses.size() >= 24:
                preview_pulses.pop_front()
            preview_pulses.append({
                "page": int(note.get("page", 0)),
                "x": float(note.get("x", 0.0)),
                "y": float(note.get("y", 0.0)),
                "duration_ms": 220,
                "until_ms": ticks_ms + 220,
                "status": "preview"
            })
    stage.effects.preview_react()

func transition_mode(state: Dictionary, stage) -> void:
    # Score feedback is graded, preview sparks are not. Mode changes must
    # discard stale effects without changing backend grading or transport.
    var ungraded: bool = bool(state.get("preview_only", false)) or \
        str(state.get("mode", "")) == "listen"
    if ungraded:
        if stage.impact_callout != null:
            stage.impact_callout.call("clear")
        if hit_pulses.is_empty() and wrong_ghosts.is_empty():
            return
        hit_pulses.clear()
        wrong_ghosts.clear()
        stage.effects.impact_energy = 0.0
        stage.effects.queue_redraw()
    else:
        if not preview_pulses.is_empty():
            preview_pulses.clear()
