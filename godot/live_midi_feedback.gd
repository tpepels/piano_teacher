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

func consume(state: Dictionary, effects, stage, last_sequence: int,
        current_revision: int) -> int:
    var events: Array = state.get("midi_visual_events", [])
    var ungraded: bool = bool(state.get("preview_only", false)) or \
        str(state.get("mode", "")) == "listen"
    var applicable: bool = revision == current_revision and \
        str(state.get("phase", "")) == "playing"
    var current_transport: int = int(state.get("transport_id", -2))
    for candidate in events:
        if not candidate is Dictionary:
            continue
        var event: Dictionary = candidate
        var sequence: int = int(event.get("sequence", 0))
        if sequence <= last_sequence:
            continue
        # Consume the sequence even if it is stale, ungraded, or from an
        # older attempt. Do not replay it later when the lesson changes.
        last_sequence = sequence
        if ungraded or not applicable or \
                int(event.get("transport_id", -1)) != current_transport:
            continue
        var status: String = str(event.get("status", ""))
        var age: float = float(event.get("age", 99.0))
        if age > 1.05:
            continue
        if status == "unexpected":
            var reference: String = str(event.get("reference_source_id", ""))
            var note_id: String = str(attack_map.get(reference, ""))
            var note: Dictionary = note_by_id.get(note_id, {})
            if note.is_empty():
                continue
            var remaining: int = maxi(1, 420 - int(age * 1000.0))
            effects.wrong_ghosts.append({
                "page": int(note.get("page", 0)),
                "x": float(note.get("x", 0.0)),
                "y": float(note.get("y", 0.0)),
                "duration_ms": 420,
                "until_ms": Time.get_ticks_msec() + remaining
            })
            if effects.wrong_ghosts.size() > 32:
                effects.wrong_ghosts.pop_front()
            stage.effects.react("unexpected")
            stage.impact_callout.call("react", "unexpected")
            continue
        if status not in ["on_time", "early", "late"] or age > .22:
            continue
        var source: String = str(event.get("source_id", ""))
        var note_id: String = str(attack_map.get(source, ""))
        var note: Dictionary = note_by_id.get(note_id, {})
        if note.is_empty():
            continue
        effects.hit_pulses.append({
            "page": int(note.get("page", 0)),
            "x": float(note.get("x", 0.0)),
            "y": float(note.get("y", 0.0)),
            "status": status,
            "note_id": note_id,
            "duration_ms": 220,
            "until_ms": Time.get_ticks_msec() + maxi(1, 220 - int(age * 1000.0))
        })
        if effects.hit_pulses.size() > 32:
            effects.hit_pulses.pop_front()
        stage.effects.react(status)
        stage.impact_callout.call("react", status)
    return last_sequence
