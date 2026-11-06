extends RefCounted
## The sole note-by-note visual status ledger. The Python engine remains
## authoritative for assessment; this ledger never grades or moves ink.
## Each result is scoped to the immutable transport take so repeated score
## copies can have different colors even when their source IDs are identical.
const UNPLAYED := "unplayed"
const HIT := "hit"
const MISSED := "missed"
const LATE := "late"
const EARLY_RELEASE := "early_release"
# Onset timing and release timing are distinct assessment dimensions.
const EARLY_ONSET := "early_onset"
const VALID := [UNPLAYED, HIT, MISSED, LATE, EARLY_RELEASE, EARLY_ONSET]

var _notes_by_take: Dictionary = {}
var _settled_by_take: Dictionary = {}

static func from_assessment(raw: String) -> String:
    match raw:
        "correct", "on_time", "hit":
            return HIT
        "early_release":
            return EARLY_RELEASE
        "early_onset":
            return EARLY_ONSET
        "missed", "wrong":
            return MISSED
        "late", "long":
            return LATE
        "short":
            return EARLY_RELEASE
        "early":
            return EARLY_ONSET
        "unplayed":
            return UNPLAYED
    # "extra" has no canonical printed notehead. "assisted" does not
    # assert clean timing. Never invent a colored note for either.
    return UNPLAYED

static func take_key(state: Dictionary) -> String:
    return "%s|%d|%d|%s" % [
        str(state.get("piece_fingerprint","")),
        int(state.get("revision",-1)),
        int(state.get("transport_id",-1)),
        str(state.get("mode","practice"))]

func clear() -> void:
    _notes_by_take.clear()
    _settled_by_take.clear()

func status(take: String, note_id: String) -> String:
    if take.is_empty() or note_id.is_empty():
        return UNPLAYED
    return str((_notes_by_take.get(take,{}) as Dictionary).get(note_id,UNPLAYED))

func record(take: String, note_id: String, raw: String,
        settled: bool = false) -> bool:
    if take.is_empty() or note_id.is_empty():
        return false
    var normalized := from_assessment(raw)
    if normalized == UNPLAYED:
        return false
    var locked: Dictionary = _settled_by_take.get(take,{})
    if not settled and bool(locked.get(note_id,false)):
        return false
    var notes: Dictionary = _notes_by_take.get(take,{})
    var changed: bool = str(notes.get(note_id,UNPLAYED)) != normalized
    notes[note_id] = normalized
    _notes_by_take[take] = notes
    if settled:
        locked[note_id] = true
        _settled_by_take[take] = locked
    return changed

func is_settled(take: String, note_id: String) -> bool:
    return bool((_settled_by_take.get(take,{}) as Dictionary).get(note_id,false))

func prune(visible_takes: Array, current_take: String) -> void:
    # Keep only attempts still represented by physical score ink, plus
    # the active attempt; do not discard old visible results on new Play.
    var keep: Dictionary = {current_take:true}
    for take in visible_takes:
        keep[str(take)] = true
    for key in _notes_by_take.keys():
        if not keep.has(str(key)):
            _notes_by_take.erase(key)
            _settled_by_take.erase(key)

func has_any() -> bool:
    return not _notes_by_take.is_empty()

func statuses_for_take(take: String) -> Dictionary:
    return (_notes_by_take.get(take,{}) as Dictionary).duplicate()

func snapshot() -> Dictionary:
    # Debug/test snapshot only; drawing must not deep-copy the whole ledger.
    return _notes_by_take.duplicate(true)
