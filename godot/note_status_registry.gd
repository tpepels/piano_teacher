extends RefCounted
## The sole note-by-note visual status ledger. The Python engine remains
## authoritative for assessment; this ledger never grades or moves ink.
##
## A record belongs to one physical note instance: the immutable transport
## take that owns a source strip, plus the engraved note ID inside it. A
## repeated passage is a different take, so identical source notes in two
## copies have independent records.
##
## Each record keeps the three observations Python makes independently:
##   pitch:   correct | wrong | missed
##   onset:   on_time | early | late
##   release: on_time | short | long | unreleased
## Provisional MIDI evidence merges one dimension at a time. A settled
## assessment replaces the whole record and locks it against provisional
## evidence; a later settled assessment (e.g. after the real key-up) may
## still replace it.
const UNPLAYED := "unplayed"
const HIT := "hit"
const MISSED := "missed"
const LATE := "late"
const EARLY_RELEASE := "early_release"
# Onset timing and release timing are distinct assessment dimensions.
const EARLY_ONSET := "early_onset"
const VALID := [UNPLAYED, HIT, MISSED, LATE, EARLY_RELEASE, EARLY_ONSET]
const DIMENSIONS := ["pitch", "onset", "release"]

var _notes_by_take: Dictionary = {}
var _revision_by_take: Dictionary = {}

## Explicit visual precedence for combined mistakes, highest first. One
## notehead shows one color; the record keeps every dimension.
##   1. wrong or missed pitch           -> missed (coral)
##   2. late onset                      -> late (amber)
##   3. early onset                     -> early_onset (pale gold)
##   4. early release (observed key-up) -> early_release (lavender)
##   5. late release or still held      -> late (amber)
##   6. any clean observation           -> hit (mint)
## The order matches Python's own grading precedence (onset before release),
## so a combined early-onset/early-release note is colored as its grade.
static func display_status(record: Dictionary) -> String:
    var pitch: String = str(record.get("pitch", ""))
    var onset: String = str(record.get("onset", ""))
    var release: String = str(record.get("release", ""))
    if pitch in ["missed", "wrong"]:
        return MISSED
    if onset == "late":
        return LATE
    if onset == "early":
        return EARLY_ONSET
    if release == "short":
        return EARLY_RELEASE
    if release in ["long", "unreleased"]:
        return LATE
    if pitch == "correct" or onset == "on_time" or release == "on_time":
        return HIT
    return UNPLAYED

## Observation for a canonical display status, for direct writes and tests.
static func observation_for_status(status: String) -> Dictionary:
    match status:
        HIT:
            return {"pitch":"correct","onset":"on_time","release":"on_time"}
        MISSED:
            return {"pitch":"missed"}
        LATE:
            return {"pitch":"correct","onset":"late"}
        EARLY_ONSET:
            return {"pitch":"correct","onset":"early"}
        EARLY_RELEASE:
            return {"pitch":"correct","onset":"on_time","release":"short"}
    return {}

static func take_key(identity: Dictionary) -> String:
    # The same key the renderer assigns to the source strips of a take.
    # Python stamps every feedback event with these exact fields.
    return "%s|%d|%d|%s" % [
        str(identity.get("piece_fingerprint","")),
        int(identity.get("revision",-1)),
        int(identity.get("transport_id",-1)),
        str(identity.get("mode","practice"))]

func clear() -> void:
    _notes_by_take.clear()
    _revision_by_take.clear()

func record_of(take: String, note_id: String) -> Dictionary:
    return ((_notes_by_take.get(take,{}) as Dictionary).get(note_id,{}) as Dictionary)

func status(take: String, note_id: String) -> String:
    if take.is_empty() or note_id.is_empty():
        return UNPLAYED
    var record: Dictionary = record_of(take,note_id)
    return UNPLAYED if record.is_empty() else str(record["status"])

## Merge observations for one physical note. Returns true when its displayed
## status changed. Provisional evidence never overrides a settled record.
func observe(take: String, note_id: String, observation: Dictionary,
        settled: bool) -> bool:
    if take.is_empty() or note_id.is_empty():
        return false
    var notes: Dictionary = _notes_by_take.get(take,{})
    var previous: Dictionary = notes.get(note_id,{})
    if not settled and bool(previous.get("settled",false)):
        return false
    var record: Dictionary = {} if settled else previous.duplicate()
    for dimension in DIMENSIONS:
        var value: Variant = observation.get(dimension)
        if value != null and not str(value).is_empty():
            record[dimension] = str(value)
    var shown: String = display_status(record)
    if shown == UNPLAYED:
        return false
    record["status"] = shown
    record["settled"] = settled or bool(previous.get("settled",false))
    if record == previous:
        return false
    notes[note_id] = record
    _notes_by_take[take] = notes
    _revision_by_take[take] = int(_revision_by_take.get(take,0))+1
    return str(previous.get("status",UNPLAYED)) != shown

## Canonical direct write of one display status (tests and diagnostics).
func record(take: String, note_id: String, status_name: String,
        settled: bool = false) -> bool:
    return observe(take,note_id,observation_for_status(status_name),settled)

func is_settled(take: String, note_id: String) -> bool:
    return bool(record_of(take,note_id).get("settled",false))

## Monotonic per-take change counter; renderers repaint a strip only when it
## changes, never on every scroll frame.
func take_revision(take: String) -> int:
    return int(_revision_by_take.get(take,0))

func prune(visible_takes: Array, current_take: String) -> void:
    # Keep only attempts still represented by physical score ink, plus
    # the active attempt; do not discard old visible results on new Play.
    var keep: Dictionary = {current_take:true}
    for take in visible_takes:
        keep[str(take)] = true
    for key in _notes_by_take.keys():
        if not keep.has(str(key)):
            _notes_by_take.erase(key)
            _revision_by_take.erase(key)

func has_any() -> bool:
    return not _notes_by_take.is_empty()

## Display status of every colored note of one take: {note_id: status}.
func statuses_for_take(take: String) -> Dictionary:
    var result: Dictionary = {}
    var notes: Dictionary = _notes_by_take.get(take,{})
    for id in notes:
        result[id] = str(notes[id]["status"])
    return result

func snapshot() -> Dictionary:
    # Debug/test snapshot only; drawing must not deep-copy the whole ledger.
    return _notes_by_take.duplicate(true)
