extends RefCounted

# Pure view-only lookahead, using Verovio's canonical source-attack geometry.
# No note grading, MIDI prediction or fake staff positioning.
const ATTACK_TOLERANCE := 0.015
const ONSET_TAIL_BEATS := 0.10
const MAX_LEAD_BEATS := 1.25


static func next_chord(layout: Dictionary, beat: float, assessed: Array = [],
        lead_beats: float = MAX_LEAD_BEATS) -> Array:
    if not is_finite(beat) or lead_beats <= 0.0:
        return []
    var notes: Array = layout.get("notes", [])
    var closest := INF
    # A chord shares one *source* onset regardless of which stave or tile its
    # individual noteheads occupy. Do not collect the next note per hand.
    for entry in notes:
        if not entry is Dictionary or not bool(entry.get("is_attack", false)):
            continue
        var onset: float = float(entry.get("source_beat", entry.get("beat", -INF)))
        if not is_finite(onset) or onset < beat - ONSET_TAIL_BEATS:
            continue
        if onset > beat + lead_beats:
            continue
        closest = minf(closest, onset)
    if not is_finite(closest):
        return []
    var consumed: Dictionary = {}
    for mark in assessed:
        if not mark is Dictionary:
            continue
        var status: String = str(mark.get("status", ""))
        if status in ["correct", "wrong", "missed", "early", "late", "short", "long", "assisted"]:
            consumed[str(mark.get("note_id", mark.get("id", "")))] = true
            consumed[str(mark.get("source_id", ""))] = true
    var emphasis: float = clampf(
        1.0 - maxf(0.0, closest - beat) / lead_beats, 0.0, 1.0)
    var pending: Array = []
    for entry in notes:
        if not entry is Dictionary or not bool(entry.get("is_attack", false)):
            continue
        var onset: float = float(entry.get("source_beat", entry.get("beat", -INF)))
        if absf(onset - closest) > ATTACK_TOLERANCE:
            continue
        var note_id: String = str(entry.get("id", ""))
        var source_id: String = str(entry.get("source_id", ""))
        if consumed.has(note_id) or (not source_id.is_empty() and consumed.has(source_id)):
            continue
        pending.append({"id": note_id, "source_id": source_id,
            "page": int(entry.get("page", 0)),
            "x": float(entry.get("x", 0.0)),
            "y": float(entry.get("y", 0.0)),
            "pitch": int(entry.get("pitch", 60)),
            "hand": str(entry.get("hand", "")),
            "beat": onset, "emphasis": emphasis})
    return pending
