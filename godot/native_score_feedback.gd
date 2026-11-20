extends Node
## Owner of the note-status ledger. Python owns assessments; NativeView owns
## the original Verovio drawing and immutable note locations. This node draws
## nothing itself: each retained source strip paints its own status ink from
## this ledger (see notation/native/note_status_layer.gd). No halo, ring,
## badge, particle emitter, extra camera or grading logic lives here.
##
## Input is ONLY the backend's sequenced feedback events (attack, release,
## assessment), delivered once each, in order, by FeedbackEventInbox. Every
## event carries its own take identity, so it is never validated against a
## possibly stale state snapshot. An event for an engraving that is not bound
## yet is buffered for that revision and replayed when it binds.
const Statuses := preload("res://note_status_registry.gd")
const MAX_BUFFERED := 4096

var score: Control
var score_revision := -1
var statuses := Statuses.new()
var _active_take := ""
# revision -> {source_id: canonical attack note_id}, for every
# engraving that a live renderer (current or scrolling tail) still shows.
var _source_maps: Dictionary = {}
# revision -> {attack note_id: tied continuation IDs}. A continuation only
# inherits its physical attack's result once its own source beat is reached.
var _continuations: Dictionary = {}
var _event_beats: Dictionary = {}
var _continuation_beats: Dictionary = {}
var _listen_cursors: Dictionary = {}
var _source_notes: Dictionary = {}
var _presented_beats: Dictionary = {}
var _visual_revisions: Dictionary = {}
var _sounding: Dictionary = {}
var _ghosts: Dictionary = {}
var _renderers: Array = [] # [{renderer: WeakRef, revision: int}]
var _buffered: Array = []
var _overflow_logged := false
var applied_events := 0
var buffered_events := 0
var ignored_events := 0

func _init() -> void:
    name = "NativeScoreFeedback"
    set_process(false)

func bind_score(renderer: Control, revision: int) -> void:
    score = renderer
    score_revision = revision
    if not is_instance_valid(renderer):
        return
    if renderer.has_method("set_note_status_source"):
        renderer.set_note_status_source(self)
    _forget_renderer(renderer)
    if revision < 0:
        return
    _renderers.append({"renderer":weakref(renderer),"revision":revision})
    var by_source: Dictionary = {}
    var tied: Array = []
    var event_beats: Dictionary = {}
    var active: Dictionary = {}
    var sounding_notes: Array = []
    for id in renderer.timeline.model.get("active_note_ids",[]):
        active[str(id)] = true
    for note in renderer.timeline.notes:
        if active.has(str(note.get("id",""))):
            sounding_notes.append(note)
    var layout = renderer.get("layout")
    if layout != null:
        for event in layout.ordered_events:
            var id: String = str(event.get("id",""))
            if id.is_empty() or str(event.get("kind","note")) != "note":
                continue
            if not active.has(str(event.get("source_id",""))):
                continue
            event_beats[id] = float(event.get("beat",0.0))
            if event.get("source_id") == null:
                continue
            if bool(event.get("is_attack",false)):
                by_source[str(event["source_id"])] = id
            else:
                tied.append([id,str(event["source_id"])])
    var attack_of: Dictionary = {}
    var continuations: Dictionary = {}
    for pair in tied:
        var attack: String = str(by_source.get(pair[1],""))
        if attack.is_empty():
            continue
        attack_of[pair[0]] = attack
        if not continuations.has(attack):
            continuations[attack] = []
        continuations[attack].append(pair[0])
    sounding_notes.sort_custom(func(a: Dictionary,b: Dictionary) -> bool:
        return float(a["onset_beats"]) < float(b["onset_beats"]))
    var continuation_beats: Array = []
    for id in attack_of:
        continuation_beats.append(float(event_beats[id]))
    continuation_beats.sort()
    _continuation_beats[revision] = continuation_beats
    _event_beats[revision] = event_beats
    _source_notes[revision] = sounding_notes
    _source_maps[revision] = by_source
    _continuations[revision] = continuations
    _forget_unshown_revisions()
    # Replay, in sequence order, events that arrived before this engraving.
    var waiting: Array = _buffered
    _buffered = []
    _overflow_logged = false
    for event in waiting:
        ingest(event)

## Apply one backend feedback event. Returns "applied", "buffered" or
## "ignored"; every outcome is final, so the caller may acknowledge it.
func ingest(event: Dictionary) -> String:
    var revision: int = int(event.get("revision",-1))
    if not _source_maps.has(revision):
        if revision > _highest_bound_revision():
            if _buffered.size() >= MAX_BUFFERED:
                _buffered.pop_front()
                if not _overflow_logged:
                    _overflow_logged = true
                    push_error("NOTE_FEEDBACK_BUFFER_OVERFLOW: oldest unbound events dropped")
            _buffered.append(event)
            buffered_events += 1
            return "buffered"
        ignored_events += 1
        return "ignored"
    if not bool(event.get("graded",false)):
        ignored_events += 1
        return "ignored"
    var take: String = Statuses.take_key(event)
    var changed := false
    match str(event.get("kind","")):
        "attack":
            var onset: String = str(event.get("status",""))
            if onset == "unexpected":
                var played: float = float(event.get("played_source_beat",NAN))
                var pitch: int = int(event.get("pitch",-1))
                if is_finite(played) and pitch >= 0 and pitch <= 127:
                    var ghosts: Array = _ghosts.get(take,[])
                    ghosts.append({"beat":played,"pitch":pitch,"staff":str(event.get("staff","right"))})
                    _ghosts[take] = ghosts
                    _touch(take)
                    applied_events += 1
                    return "applied"
            var id: String = _note_for_source(revision,str(event.get("source_id","")))
            if onset not in ["on_time","early","late"] or id.is_empty():
                ignored_events += 1
                return "ignored"
            changed = statuses.observe(take,id,{"pitch":"correct","onset":onset},false)
        "release":
            var release: String = str(event.get("release",""))
            var id: String = _note_for_source(revision,str(event.get("source_id","")))
            if release not in ["on_time","short","long"] or id.is_empty():
                ignored_events += 1
                return "ignored"
            changed = statuses.observe(take,id,{"pitch":"correct","release":release},false)
        "assessment":
            var id: String = str(event.get("note_id",""))
            var dimensions: Variant = event.get("dimensions")
            if _note_for_source(revision,str(event.get("source_id",""))) != id or id.is_empty():
                ignored_events += 1
                return "ignored"
            if str(event.get("status","")) == "pending" and dimensions == null:
                changed = statuses.clear_note(take,id,true)
            elif dimensions is Dictionary:
                changed = statuses.observe(take,id,dimensions,bool(event.get("final",false)),true)
            else:
                ignored_events += 1
                return "ignored"
        _:
            ignored_events += 1
            return "ignored"
    applied_events += 1
    if changed:
        _repaint()
    return "applied"

## Presentation context only: which take is active and whether graded ink
## may be shown. It never records a grade.
func present(state: Dictionary) -> void:
    var suppress: bool = bool(state.get("preview_only",false))
    # A buffered event older than the state's revision can never bind.
    var current_revision: int = int(state.get("revision",-2))
    if not _buffered.is_empty():
        _buffered = _buffered.filter(func(event: Dictionary) -> bool:
            return int(event.get("revision",-1)) >= current_revision)
    if int(state.get("revision",-2)) == score_revision and not suppress:
        _active_take = Statuses.take_key(state)
    if int(state.get("revision",-2)) == score_revision and str(state.get("mode","")) == "learn":
        var take: String = Statuses.take_key(state)
        var guided_ids: Dictionary = {}
        for mark in state.get("feedback_marks",[]):
            if not mark is Dictionary:
                continue
            var id: String = str(mark.get("id",""))
            var source: String = str(mark.get("source_id",""))
            if _note_for_source(score_revision,source) != id or id.is_empty():
                continue
            var status: String = str(mark.get("status",""))
            if status in ["correct","assisted","wrong"]:
                guided_ids[id] = true
                statuses.observe(take,id,{"pitch":"wrong" if status == "wrong" else "correct"},true)
        for id in statuses.statuses_for_take(take):
            if not guided_ids.has(id):
                statuses.clear_note(take,id,false)
    var keys: Array = []
    for entry in _live_renderers():
        var renderer = entry["renderer"].get_ref()
        renderer.set_note_status_visible(not suppress or str(state.get("mode","")) == "listen")
        keys.append_array(renderer.visible_take_keys())
    statuses.prune(keys,_active_take)
    keys.append(_active_take)
    for ledger in [_presented_beats,_visual_revisions,_sounding,_ghosts,_listen_cursors]:
        for take in ledger.keys():
            if not keys.has(take):
                ledger.erase(take)

func status_for(take: String, note_id: String) -> String:
    var own: String = statuses.status(take,note_id)
    if own != Statuses.UNPLAYED:
        return own
    return str(statuses_for_take(take).get(note_id,own))

## Source-matched attacks retain their result; tied heads acquire that colour
## only when the shared source clock reaches their own segment.
func statuses_for_take(take: String) -> Dictionary:
    var own: Dictionary = statuses.statuses_for_take(take)
    var result: Dictionary = own.duplicate()
    var continuations: Dictionary = _continuations.get(_take_revision(take),{})
    for attack in own:
        for id in continuations.get(attack,[]):
            if not result.has(id) and float((_event_beats.get(_take_revision(take),{}) as Dictionary).get(id,INF)) <= float(_presented_beats.get(take,-INF))+.00001:
                result[id] = own[attack]
    for id in _sounding.get(take,{}):
        result[id] = "sounding"
    return result

func ghosts_for_take(take: String) -> Array:
    return _ghosts.get(take,[])

func _touch(take: String) -> void:
    _visual_revisions[take] = int(_visual_revisions.get(take,0))+1
    _repaint()

## Uses the shared transport sample; this projects sound/ink and never grades.
func present_source_beat(state: Dictionary, clock_beat: float) -> void:
    var take: String = Statuses.take_key(state)
    var revision: int = int(state.get("revision",-1))
    var beat: float = clock_beat+float(state.get("play_from_beat",0.0))
    var previous: float = float(_presented_beats.get(take,-INF))
    _presented_beats[take] = beat
    # Binary lookup in immutable continuation times avoids scanning a whole
    # score on every frame just to discover whether a head became current.
    var times: Array = _continuation_beats.get(revision,[])
    var low := 0
    var high: int = times.size()
    while low < high:
        var middle: int = (low+high)>>1
        if float(times[middle]) <= previous:
            low = middle+1
        else:
            high = middle
    var changed: bool = low < times.size() and float(times[low]) <= beat
    var sounding: Dictionary = {}
    if str(state.get("mode","")) == "listen" and bool(state.get("running",false)):
        var cursor: Dictionary = _listen_cursors.get(take,{"next":0,"active":{}})
        if beat < previous:
            cursor = {"next":0,"active":{}}
        var notes: Array = _source_notes.get(revision,[])
        var next: int = int(cursor["next"])
        var active: Dictionary = cursor["active"]
        while next < notes.size() and float(notes[next]["onset_beats"]) <= beat:
            var note: Dictionary = notes[next]
            active[str(note["id"])] = note
            next += 1
        for source in active.keys():
            var note: Dictionary = active[source]
            if beat >= float(note["onset_beats"])+float(note["duration_beats"]):
                active.erase(source)
                continue
            var attack: String = _note_for_source(revision,str(source))
            if not attack.is_empty():
                sounding[attack] = true
                for id in (_continuations.get(revision,{}) as Dictionary).get(attack,[]):
                    if float(_event_beats[revision].get(id,INF)) <= beat:
                        sounding[id] = true
        _listen_cursors[take] = {"next":next,"active":active}
    if sounding != _sounding.get(take,{}):
        _sounding[take] = sounding
        changed = true
    if changed:
        _touch(take)

static func _take_revision(take: String) -> int:
    var parts: PackedStringArray = take.split("|")
    return int(parts[parts.size()-3]) if parts.size() >= 3 else -1

func take_revision(take: String) -> int:
    return statuses.take_revision(take)+int(_visual_revisions.get(take,0))

func pending_events() -> int:
    return _buffered.size()

## Engraving revisions whose note identities are currently bound.
func bound_revisions() -> Array:
    return _source_maps.keys()

## Engraved note ID of a source attack in a bound revision ("" if unknown).
func note_for_source(revision: int, source_id: String) -> String:
    return _note_for_source(revision,source_id) if _source_maps.has(revision) else ""

func _note_for_source(revision: int, source_id: String) -> String:
    return str((_source_maps[revision] as Dictionary).get(source_id,""))

func _highest_bound_revision() -> int:
    var highest := -1
    for revision in _source_maps:
        highest = maxi(highest,int(revision))
    return highest

func _live_renderers() -> Array:
    var live: Array = []
    for entry in _renderers:
        var renderer = entry["renderer"].get_ref()
        if renderer != null and is_instance_valid(renderer):
            live.append(entry)
    _renderers = live
    return live

func _forget_renderer(renderer: Control) -> void:
    _renderers = _live_renderers().filter(func(entry: Dictionary) -> bool:
        return entry["renderer"].get_ref() != renderer)

func _forget_unshown_revisions() -> void:
    var shown: Dictionary = {}
    for entry in _live_renderers():
        shown[int(entry["revision"])] = true
    for revision in _source_maps.keys():
        if not shown.has(int(revision)):
            _source_maps.erase(revision)
            _continuations.erase(revision)
            _event_beats.erase(revision)
            _source_notes.erase(revision)
            _continuation_beats.erase(revision)

func _repaint() -> void:
    for entry in _live_renderers():
        entry["renderer"].get_ref().queue_redraw()
