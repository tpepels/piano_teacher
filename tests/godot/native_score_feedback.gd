extends SceneTree
## Contract of the note-status ledger and its event ingestion.
## Physical rendering (pixels, clipping, glow, alignment) is verified on the
## real Verovio framebuffer by tests/test_note_status_framebuffer.py.
const Status := preload("res://note_status_registry.gd")
const Ink := preload("res://note_status_ink.gd")
const Inbox := preload("res://feedback_event_inbox.gd")

class Layout extends RefCounted:
    var ordered_events: Array = []

class Renderer extends Control:
    var layout := Layout.new()
    var source = null
    var ink_visible := true
    var takes: Array = []
    func _init(ids: Array) -> void:
        for id in ids:
            layout.ordered_events.append({"id":id,"kind":"note",
                "source_id":"s"+id,"is_attack":true})
    func set_note_status_source(value) -> void:
        source = value
    func set_note_status_visible(enabled: bool) -> void:
        ink_visible = enabled
    func visible_take_keys() -> Array:
        return takes

var failures: Array[String] = []
var sequence := 0

func check(ok: bool, reason: String) -> void:
    if not ok:
        failures.append(reason)
        push_error("NATIVE_FEEDBACK_FAILED: "+reason)

func _take(transport: int, revision: int = 7) -> Dictionary:
    return {"piece_fingerprint":"fixture","revision":revision,
        "transport_id":transport,"mode":"practice","graded":true}

func _event(kind: String, transport: int, fields: Dictionary,
        revision: int = 7) -> Dictionary:
    sequence += 1
    var event: Dictionary = _take(transport,revision)
    event.merge(fields,true)
    event["kind"] = kind
    event["sequence"] = sequence
    return event

func _assess(transport: int, id: String, dims: Dictionary,
        revision: int = 7) -> Dictionary:
    return _event("assessment",transport,{"note_id":id,"source_id":"s"+id,
        "status":"x","dimensions":dims},revision)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    _registry()
    _precedence()
    await _ingestion()
    _inbox()
    print("NATIVE_FEEDBACK_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)

func _registry() -> void:
    var canonical := Status.new()
    check(canonical.record("take","id",Status.HIT) and
        canonical.status("take","id") == Status.HIT and
        canonical.record("take","id",Status.EARLY_RELEASE,true) and
        canonical.status("take","id") == Status.EARLY_RELEASE and
        not canonical.record("take","id",Status.HIT,false),
        "canonical status updates work and settled feedback overrides provisional hits")
    check(canonical.status("other","id")==Status.UNPLAYED,
        "a new take has no inherited note statuses")
    var revision: int = canonical.take_revision("take")
    canonical.record("take","id",Status.EARLY_RELEASE,true)
    check(canonical.take_revision("take") == revision,
        "an unchanged settled record does not invalidate the strip")
    check(Ink.glow_strength(Status.UNPLAYED) == 0.0 and
            Ink.glow_strength(Status.HIT) > 0.0 and
            Ink.glow_strength(Status.HIT) <= .05,
        "only played/graded notes have a minor contour-bound glow")
    check(Ink.material_for("erase").blend_mode == CanvasItemMaterial.BLEND_MODE_SUB and
            Ink.material_for("core").blend_mode == CanvasItemMaterial.BLEND_MODE_ADD,
        "status ink replaces the authentic head instead of overpainting it")

func _precedence() -> void:
    var cases := [
        [{"pitch":"wrong"},Status.MISSED],
        [{"pitch":"missed"},Status.MISSED],
        [{"pitch":"correct","onset":"late","release":"short"},Status.LATE],
        [{"pitch":"correct","onset":"early","release":"short"},Status.EARLY_ONSET],
        [{"pitch":"correct","onset":"early","release":"long"},Status.EARLY_ONSET],
        [{"pitch":"correct","onset":"on_time","release":"short"},Status.EARLY_RELEASE],
        [{"pitch":"correct","onset":"on_time","release":"long"},Status.LATE],
        [{"pitch":"correct","onset":"on_time","release":"unreleased"},Status.LATE],
        [{"pitch":"correct","onset":"on_time","release":"on_time"},Status.HIT],
        [{},Status.UNPLAYED]]
    for case in cases:
        check(Status.display_status(case[0]) == case[1],
            "precedence %s -> %s" % [str(case[0]),case[1]])

func _ingestion() -> void:
    var feedback = load("res://native_score_feedback.gd").new()
    root.add_child(feedback)
    var renderer := Renderer.new(["a","b","c","d","e","f"])
    root.add_child(renderer)
    feedback.bind_score(renderer,7)
    check(renderer.source == feedback, "the renderer reads the one note-status ledger")
    var t8: String = Status.take_key(_take(8))
    var t9: String = Status.take_key(_take(9))
    # Every strip key the renderer assigns equals the event take key.
    check(t8 == "fixture|7|8|practice", "event identity matches strip take keys")
    feedback.present({"piece_fingerprint":"fixture","revision":7,
        "transport_id":8,"mode":"practice","phase":"playing"})
    check(feedback.ingest(_event("attack",8,{"source_id":"sa","status":"on_time"})) ==
        "applied" and feedback.status_for(t8,"a") == Status.HIT,
        "a live accepted attack colors its own note immediately")
    check(feedback.ingest(_event("release",8,{"source_id":"sa","release":"short"})) ==
        "applied" and feedback.status_for(t8,"a") == Status.EARLY_RELEASE,
        "an observed early key-up shows early release before settlement")
    check(not feedback.statuses.is_settled(t8,"a"), "MIDI evidence stays provisional")
    feedback.ingest(_assess(8,"a",{"pitch":"correct","onset":"on_time","release":"on_time"}))
    check(feedback.status_for(t8,"a") == Status.HIT and feedback.statuses.is_settled(t8,"a"),
        "the settled assessment overrides provisional MIDI feedback")
    feedback.ingest(_event("release",8,{"source_id":"sa","release":"short"}))
    check(feedback.status_for(t8,"a") == Status.HIT,
        "late provisional evidence cannot change a settled note")
    feedback.ingest(_assess(8,"a",{"pitch":"correct","onset":"on_time","release":"long"}))
    check(feedback.status_for(t8,"a") == Status.LATE,
        "a later settled grade (after the real key-up) still replaces the earlier one")
    feedback.ingest(_assess(8,"b",{"pitch":"missed"}))
    feedback.ingest(_assess(8,"c",{"pitch":"correct","onset":"late","release":"on_time"}))
    feedback.ingest(_assess(8,"d",{"pitch":"correct","onset":"on_time","release":"short"}))
    feedback.ingest(_assess(8,"e",{"pitch":"correct","onset":"early","release":"short"}))
    check(feedback.status_for(t8,"b") == Status.MISSED and
            feedback.status_for(t8,"c") == Status.LATE and
            feedback.status_for(t8,"d") == Status.EARLY_RELEASE and
            feedback.status_for(t8,"e") == Status.EARLY_ONSET,
        "missed, late, early release and early onset are recorded distinctly")
    check((feedback.statuses.record_of(t8,"e") as Dictionary).get("release") == "short",
        "a combined early onset keeps its independent early-release observation")
    check(feedback.ingest(_assess(8,"unknown",{"pitch":"missed"})) == "ignored" and
            feedback.ingest(_event("attack",8,{"source_id":"sz","status":"on_time"})) == "ignored" and
            feedback.ingest(_event("attack",8,{"source_id":"sf","status":"unexpected"})) == "ignored",
        "unmapped or unexpected input cannot color a printed note")
    var ungraded: Dictionary = _event("attack",8,{"source_id":"sf","status":"on_time"})
    ungraded["graded"] = false
    check(feedback.ingest(ungraded) == "ignored" and
            feedback.status_for(t8,"f") == Status.UNPLAYED,
        "preview/listen attacks never earn an on-score grade")

    # P0 regression: Play/Resume/Retry start transport 9 before the UI has a
    # snapshot of it. The event names its own take and must not be lost.
    feedback.present({"piece_fingerprint":"fixture","revision":7,
        "transport_id":8,"mode":"practice","phase":"feedback"})
    check(feedback.ingest(_event("attack",9,{"source_id":"sb","status":"late"})) ==
        "applied" and feedback.status_for(t9,"b") == Status.LATE,
        "an attack of the new transport applies although the last state is stale")
    check(feedback.status_for(t8,"b") == Status.MISSED,
        "the same source note keeps its grade in the earlier physical copy")

    # Events for an engraving that is not bound yet are buffered, in order.
    var next := Renderer.new(["a","b"])
    root.add_child(next)
    var t10r8: String = Status.take_key(_take(10,8))
    check(feedback.ingest(_event("attack",10,{"source_id":"sa","status":"on_time"},8)) ==
        "buffered" and feedback.ingest(_assess(10,"b",{"pitch":"missed"},8)) == "buffered",
        "events for a future engraving are buffered instead of dropped")
    check(feedback.status_for(t10r8,"a") == Status.UNPLAYED, "buffered events are not shown early")
    renderer.takes = [t8,t9]
    feedback.bind_score(next,8)
    check(feedback.pending_events() == 0 and
            feedback.status_for(t10r8,"a") == Status.HIT and
            feedback.status_for(t10r8,"b") == Status.MISSED,
        "binding the engraving replays its buffered events")
    check(feedback.ingest(_event("attack",3,{"source_id":"sa","status":"on_time"},5)) ==
        "ignored", "events of an engraving no renderer shows are discarded")
    # The outgoing renderer still scrolls as a tail: its takes stay colored.
    feedback.present({"piece_fingerprint":"fixture","revision":8,
        "transport_id":10,"mode":"practice","phase":"playing"})
    check(feedback.status_for(t8,"b") == Status.MISSED and
            feedback.status_for(t9,"b") == Status.LATE,
        "grades of a still-visible outgoing engraving persist")
    renderer.takes = []
    feedback.present({"piece_fingerprint":"fixture","revision":8,
        "transport_id":10,"mode":"practice","phase":"playing"})
    check(feedback.status_for(t8,"b") == Status.UNPLAYED and
            feedback.status_for(t10r8,"b") == Status.MISSED,
        "takes are pruned only after their strips leave every renderer")
    feedback.present({"piece_fingerprint":"fixture","revision":8,"preview_only":true,
        "transport_id":11,"mode":"practice"})
    check(not next.ink_visible and not renderer.ink_visible and
            feedback.status_for(t10r8,"b") == Status.MISSED,
        "an ungraded preview hides graded ink without erasing it")
    feedback.present({"piece_fingerprint":"fixture","revision":8,
        "transport_id":11,"mode":"practice"})
    check(next.ink_visible, "returning to graded practice restores the ink")
    renderer.free()
    await process_frame
    feedback.bind_score(next,9)
    check(feedback.ingest(_event("attack",12,{"source_id":"sa","status":"on_time"},8)) ==
        "ignored", "a new engraving revision does not inherit the previous note map")
    feedback.free()
    next.free()

func _inbox() -> void:
    var inbox := Inbox.new()
    var events := [{"sequence":1},{"sequence":2},{"sequence":3}]
    var first: Array = inbox.accept({"events":events})
    check(first.size() == 3, "all unacknowledged events are delivered")
    inbox.acknowledge(2)
    var again: Array = inbox.accept({"events":events})
    check(again.size() == 1 and int(again[0]["sequence"]) == 3,
        "a repeated reply never re-applies acknowledged events")
    inbox.acknowledge(3)
    inbox.accept({"events":[{"sequence":5}]})
    check(inbox.gaps == 1, "a sequence gap is detected, never silently accepted")
    inbox.accept({"events":[],"lost_through":9})
    check(inbox.lost_through == 9, "backend overflow is reported")
