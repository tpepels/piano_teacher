extends RefCounted

# Musical lookahead is visual only; no grading or guessed staff geometry.
# Prepare a source-attack index ONCE per engraved score, then use binary
# search per frame so whole-piece Perform does not scan thousands of notes.
const ATTACK_TOLERANCE := 0.015
const ONSET_TAIL_BEATS := 0.10
const MAX_LEAD_BEATS := 1.25


static func prepare(layout: Dictionary) -> Array:
    var attacks: Array = []
    for entry in layout.get("notes", []):
        if not entry is Dictionary or not bool(entry.get("is_attack", false)):
            continue
        var onset: float = float(entry.get("source_beat", entry.get("beat", -INF)))
        if not is_finite(onset):
            continue
        attacks.append({"beat":onset, "note":entry})
    attacks.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
        return float(a.beat) < float(b.beat))
    var grouped: Array = []
    for item in attacks:
        if grouped.is_empty() or absf(float(grouped[-1]["beat"]) - float(item.beat)) > ATTACK_TOLERANCE:
            grouped.append({"beat": float(item.beat), "notes": [item.note]})
        else:
            grouped[-1]["notes"].append(item.note)
    return grouped


static func cue(groups: Array, beat: float, assessed: Array = [],
        lead_beats: float = MAX_LEAD_BEATS) -> Array:
    if not is_finite(beat) or lead_beats <= 0.0 or groups.is_empty():
        return []
    var low := 0
    var high := groups.size()
    while low < high:
        var mid: int = (low + high) / 2
        if float(groups[mid]["beat"]) < beat - ONSET_TAIL_BEATS:
            low = mid + 1
        else:
            high = mid
    if low >= groups.size():
        return []
    var group: Dictionary = groups[low]
    var onset: float = float(group["beat"])
    if onset > beat + lead_beats:
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
        1.0 - maxf(0.0, onset-beat) / lead_beats, 0.0, 1.0)
    var pending: Array = []
    for entry in group["notes"]:
        var note_id: String = str(entry.get("id", ""))
        var source_id: String = str(entry.get("source_id", ""))
        if consumed.has(note_id) or (not source_id.is_empty() and consumed.has(source_id)):
            continue
        pending.append({"id":note_id, "source_id":source_id,
            "page":int(entry.get("page", 0)),
            "x":float(entry.get("x", 0.0)), "y":float(entry.get("y", 0.0)),
            "pitch":int(entry.get("pitch", 60)),
            "hand":str(entry.get("hand", "")),
            "beat":float(entry.get("source_beat", entry.get("beat", onset))),
            "emphasis":emphasis})
    return pending


# Convenient pure function for diagnostics and UI layout tests. Production
# animation uses cached groups via cue() above, not prepare() every frame.
static func next_chord(layout: Dictionary, beat: float, assessed: Array = [],
        lead_beats: float = MAX_LEAD_BEATS) -> Array:
    return cue(prepare(layout), beat, assessed, lead_beats)
