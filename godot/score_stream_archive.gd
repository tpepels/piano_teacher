extends RefCounted
## Durable source-plan journal for the single online/offline music queue.
## No Godot nodes, render buffers or transport clocks are serialized.
## Each complete event is checksummed and appended before its owner is
## withdrawn. Replay consumes an offline plan in the same atomic enqueue
## event, so a crash cannot silently lose or duplicate the source plan.
const VERSION := 1
const DEFAULT_DIR := "user://score-stream-journal"

var pending: Array = []
var history: Array = []
var score_key := ""
var last_error := ""
var _path := ""
var _next_id := 1
var _session := "%d-%d" % [
    int(Time.get_unix_time_from_system()),Time.get_ticks_usec()]

func bind_score(key: String, directory: String = DEFAULT_DIR) -> bool:
    if key.is_empty():
        last_error = "A persistent score archive requires a score identity"
        return false
    if key == score_key and not _path.is_empty() and last_error.is_empty():
        return true
    score_key = key
    _path = directory.path_join(key.sha256_text()+".jsonl")
    pending.clear()
    history.clear()
    _next_id = 1
    last_error = ""
    var absolute: String = ProjectSettings.globalize_path(directory)
    if DirAccess.make_dir_recursive_absolute(absolute) != OK:
        last_error = "Cannot create score archive directory: " + absolute
        return false
    if not FileAccess.file_exists(_path):
        return true
    var file := FileAccess.open(_path,FileAccess.READ)
    if file == null:
        last_error = "Cannot read source plan journal"
        return false
    var active: Dictionary = {}
    var waiting: Dictionary = {}
    var lines := 0
    while not file.eof_reached():
        var line: String = file.get_line()
        if line.strip_edges().is_empty():
            continue
        lines += 1
        var envelope: Variant = JSON.parse_string(line)
        if not envelope is Dictionary:
            last_error = "Corrupt source plan journal at line %d" % lines
            break
        var payload: Variant = envelope.get("payload")
        if not payload is String or \
                str(envelope.get("sha256","")) != payload.sha256_text():
            last_error = "Invalid source plan checksum at line %d" % lines
            break
        var event: Variant = JSON.parse_string(payload)
        if not event is Dictionary or \
                int(event.get("version",-1)) != VERSION or \
                str(event.get("score_key","")) != score_key:
            last_error = "Incompatible source plan event at line %d" % lines
            break
        history.append(event)
        _next_id = maxi(_next_id,int(event.get("id",0))+1)
        _fold(event,active,waiting)
    file.close()
    # Keep intact events even if the final record was partially written.
    # Never silently overwrite a corrupt journal on the next mutation.
    if not last_error.is_empty():
        pending.clear()
        return false
    # An online passage from an interrupted process is recoverable offline.
    # It is never resumed at its old physical screen position.
    for item in active.values():
        var resumed: Dictionary = item.duplicate(true)
        resumed["event"] = "interrupted"
        waiting[int(item["id"])] = resumed
    var keys: Array = waiting.keys()
    keys.sort()
    for id in keys:
        pending.append(waiting[id])
    return true

func _fold(event: Dictionary, active: Dictionary,
        waiting: Dictionary) -> void:
    var kind: String = str(event.get("event",""))
    var owner: String = str(event.get("session","")) + ":" + \
        str(event.get("owner_serial",0))
    var from_id: int = int(event.get("from_id",0))
    if kind == "enqueued":
        active[owner] = event
        if from_id > 0:
            waiting.erase(from_id)
    elif kind in ["withdrawn","score_reset"]:
        active.erase(owner)
        waiting[int(event["id"])] = event
    elif kind == "completed":
        active.erase(owner)

func record(kind: String, owner_serial: int, plan: Array,
        reason: String = "", from_id: int = 0) -> bool:
    if kind not in ["enqueued","withdrawn","score_reset","completed"]:
        last_error = "Unsupported offline queue event " + kind
        return false
    if plan.is_empty() or owner_serial <= 0:
        last_error = "Cannot archive an empty or ownerless score passage"
        return false
    var event: Dictionary = {
        "version":VERSION,"id":_next_id,"score_key":score_key,
        "session":_session,"owner_serial":owner_serial,
        "event":kind,"reason":reason,"from_id":from_id,
        "plan":plan.duplicate(true)}
    if not _path.is_empty():
        if not last_error.is_empty():
            return false
        var payload: String = JSON.stringify(event)
        var row: String = JSON.stringify({
            "payload":payload,"sha256":payload.sha256_text()})
        var mode: FileAccess.ModeFlags = (
            FileAccess.READ_WRITE if FileAccess.file_exists(_path)
            else FileAccess.WRITE)
        var file := FileAccess.open(_path,mode)
        if file == null:
            last_error = "Cannot append the offline source queue journal"
            return false
        file.seek_end()
        file.store_line(row)
        file.flush()
        var failure: Error = file.get_error()
        file.close()
        if failure != OK:
            last_error = "Cannot flush offline source queue (%d)" % failure
            return false
    _next_id += 1
    history.append(event)
    # Keep in-memory pending material only if it actually leaves the score.
    if kind in ["withdrawn","score_reset"]:
        pending.append(event)
    elif kind == "enqueued" and from_id > 0:
        for i in range(pending.size()-1,-1,-1):
            if int(pending[i].get("id",0)) == from_id:
                pending.remove_at(i)
                break
    return true

func original_plan(owner_serial: int) -> Array:
    # A score may be unloaded after its source has exited but its written
    # rest is still onscreen. Recover the entire originally admitted source
    # from the journal, not an unusable rest-only fragment.
    for index in range(history.size()-1,-1,-1):
        var event: Dictionary = history[index]
        if str(event.get("event","")) == "enqueued" and \
                str(event.get("session","")) == _session and \
                int(event.get("owner_serial",-1)) == owner_serial:
            return (event.get("plan",[]) as Array).duplicate(true)
    return []


func compatible(requested: Array) -> Dictionary:
    if requested.is_empty() or str(requested[0].get("kind",""))!="source":
        return {}
    for entry in pending:
        var plan: Array = entry.get("plan",[])
        if plan.size() != requested.size() or plan.is_empty():
            continue
        var same := true
        for j in range(plan.size()):
            var a: Dictionary = plan[j]
            var b: Dictionary = requested[j]
            if str(a.get("kind","")) != str(b.get("kind","")) or \
                    absf(float(a.get("source_floor",-1))-
                        float(b.get("source_floor",-2)))>.00001 or \
                    absf(float(a.get("source_ceiling",-1))-
                        float(b.get("source_ceiling",-2)))>.00001:
                same = false
                break
        if same:
            return entry
    return {}

func materialize(entry: Dictionary, requested: Array) -> Array:
    # Only a BRAND-NEW enqueue may derive a new world origin, serial and
    # transport key from a withdrawn source. Archived plans remain untouched.
    var stored: Array = entry.get("plan",[])
    if stored.size()!=requested.size():
        return []
    var delta: float = float(requested[0]["world_origin"]) - \
        float(stored[0]["world_origin"])
    var result: Array = []
    for i in range(stored.size()):
        var spec: Dictionary = stored[i].duplicate(true)
        var replacement: Dictionary = requested[i]
        spec["owner_serial"] = int(replacement["owner_serial"])
        spec["world_origin"] = float(stored[i]["world_origin"])+delta
        spec["take_key"] = str(replacement.get("take_key","prepared"))
        spec["pending"] = bool(replacement.get("pending",false))
        spec["hidden_until_armed"] = bool(
            replacement.get("hidden_until_armed",false))
        spec.erase("slot_id")
        result.append(spec)
    return result
