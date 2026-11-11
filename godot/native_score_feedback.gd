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
var _suppress_graded_ink := false
# revision -> {source_id: note_id} and revision -> {note_id: true}, for every
# engraving that a live renderer (current or scrolling tail) still shows.
var _source_maps: Dictionary = {}
var _note_ids: Dictionary = {}
# revision -> {continuation note_id: attack note_id}: a tied continuation head
# shows the colour of its attack (owner decision C4). Display only; the ledger
# itself stays keyed by the physical attack.
var _attack_of: Dictionary = {}
var _continuations: Dictionary = {}
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
    var ids: Dictionary = {}
    var tied: Array = []
    var layout = renderer.get("layout")
    if layout != null:
        for event in layout.ordered_events:
            var id: String = str(event.get("id",""))
            if id.is_empty() or str(event.get("kind","note")) != "note":
                continue
            ids[id] = true
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
    _source_maps[revision] = by_source
    _note_ids[revision] = ids
    _attack_of[revision] = attack_of
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
            if not (_note_ids[revision] as Dictionary).has(id) or \
                    not dimensions is Dictionary:
                ignored_events += 1
                return "ignored"
            changed = statuses.observe(take,id,dimensions,true)
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
    var suppress: bool = bool(state.get("preview_only",false)) or \
        str(state.get("mode","")) == "listen"
    _suppress_graded_ink = suppress
    # A buffered event older than the state's revision can never bind.
    var current_revision: int = int(state.get("revision",-2))
    if not _buffered.is_empty():
        _buffered = _buffered.filter(func(event: Dictionary) -> bool:
            return int(event.get("revision",-1)) >= current_revision)
    if int(state.get("revision",-2)) == score_revision and not suppress:
        _active_take = Statuses.take_key(state)
    var keys: Array = []
    for entry in _live_renderers():
        var renderer = entry["renderer"].get_ref()
        renderer.set_note_status_visible(not suppress)
        keys.append_array(renderer.visible_take_keys())
    statuses.prune(keys,_active_take)

func status_for(take: String, note_id: String) -> String:
    var own: String = statuses.status(take,note_id)
    if own != Statuses.UNPLAYED:
        return own
    var attack: String = str((_attack_of.get(_take_revision(take),{}) as Dictionary).get(note_id,""))
    return statuses.status(take,attack) if not attack.is_empty() else own

## Status per engraved note of a take, with every tied continuation carrying
## its attack's status unless it was graded on its own.
func statuses_for_take(take: String) -> Dictionary:
    var own: Dictionary = statuses.statuses_for_take(take)
    var result: Dictionary = own.duplicate()
    var continuations: Dictionary = _continuations.get(_take_revision(take),{})
    for attack in own:
        for id in continuations.get(attack,[]):
            if not result.has(id):
                result[id] = own[attack]
    return result

static func _take_revision(take: String) -> int:
    var parts: PackedStringArray = take.split("|")
    return int(parts[parts.size()-3]) if parts.size() >= 3 else -1

func take_revision(take: String) -> int:
    return statuses.take_revision(take)

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
            _note_ids.erase(revision)
            _attack_of.erase(revision)
            _continuations.erase(revision)

func _repaint() -> void:
    for entry in _live_renderers():
        entry["renderer"].get_ref().queue_redraw()
