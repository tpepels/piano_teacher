extends SceneTree
## Source facts and compiled-head records are fixtures. All feedback ingestion,
## take selection, tied-head gating and status ink selection use production code.
const Native := preload("res://notation/native/view.gd")
const Feedback := preload("res://native_score_feedback.gd")
const Segment := preload("res://notation/native/retained_segment.gd")
const StatusLayer := preload("res://notation/native/note_status_layer.gd")
const Ink := preload("res://note_status_ink.gd")
const LiveReactions := preload("res://live_midi_feedback.gd")
const PracticeStage := preload("res://practice_score_stage.gd")
var failures := 0

func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        printerr("NOTE_FEEDBACK_FAIL: ",message)

func identity(transport: int = 10, revision: int = 7, mode: String = "practice") -> Dictionary:
    return {"piece_fingerprint":"piece","revision":revision,"transport_id":transport,"mode":mode}

func event(kind: String, source: String = "a", transport: int = 10) -> Dictionary:
    var value := identity(transport)
    value.merge({"kind":kind,"graded":true,"source_id":source})
    return value

func renderer(revision: int = 7):
    var view := Native.new()
    var model := {"schema":"piano-teacher-score-model-v1","beat_unit":"quarter",
        "revision":revision,"duration_beats":8.0,
        "active_note_ids":["a","b"],
        "notes":[{"id":"a","onset_beats":0.0,"duration_beats":5.0,"pitch":60,"hand":"right"},
            {"id":"b","onset_beats":6.0,"duration_beats":1.0,"pitch":60,"hand":"right"},
            {"id":"context","onset_beats":2.0,"duration_beats":1.0,"pitch":60,"hand":"left"}],
        "measures":[{"start_beat":0.0,"end_beat":4.0},{"start_beat":4.0,"end_beat":8.0}]}
    check(view.timeline.load_model(model),"Semantic fixture is a valid source score")
    view.layout.ordered_events = [
        {"kind":"note","id":"head-a","source_id":"a","beat":0.0,"is_attack":true},
        {"kind":"note","id":"tie-a","source_id":"a","beat":4.0,"is_attack":false},
        {"kind":"note","id":"head-b","source_id":"b","beat":6.0,"is_attack":true},
        {"kind":"note","id":"inactive-head","source_id":"context","beat":2.0,"is_attack":true}]
    return view

func assessment(source: String, head: String, dimensions: Dictionary, final := true, transport := 10) -> Dictionary:
    var value := event("assessment",source,transport)
    value.merge({"note_id":head,"dimensions":dimensions,"final":final,"release_advisory":true})
    return value

func color(feedback, take: String, head: String) -> Color:
    return Ink.color_for(feedback.status_for(take,head))

func _initialize() -> void:
    # SceneTree._initialize precedes the first entered frame. Assemble the
    # real stage only once its child-control _ready lifecycle can run.
    call_deferred("_run")


func _run() -> void:
    var view = renderer()
    var feedback := Feedback.new()
    feedback.bind_score(view,7)
    var take: String = feedback.statuses.take_key(identity())
    var next_take: String = feedback.statuses.take_key(identity(11))
    var green := Ink.color_for("hit")
    var red := Ink.color_for("missed")
    check(green.g > green.r and red.r > red.g,"Correct feedback is green and incorrect feedback is red")
    var hit := event("attack")
    hit.status = "on_time"
    check(feedback.ingest(hit) == "applied" and color(feedback,take,"head-a") == green,
        "A source-matched attack colors its intended engraved head green")
    check(feedback.status_for(take,"head-b") == "unplayed"
        and feedback.status_for(next_take,"head-a") == "unplayed",
        "Same-pitch future notes and the next take receive no credit")
    for source in ["absent-source","context"]:
        var unrelated := event("attack",source)
        unrelated.status = "on_time"
        check(feedback.ingest(unrelated) == "ignored","An unknown or inactive source cannot acquire graded color: "+source)
    check(feedback.status_for(take,"inactive-head") == "unplayed","The dimmed inactive hand stays ungraded")
    var segment := Segment.new()
    segment.source_floor = 0.0
    segment.source_ceiling = 8.0
    segment.instances_by_event = {"head-a":[{"instance_id":"current:a"}],
        "tie-a":[{"instance_id":"current:tie"}],"head-b":[{"instance_id":"current:b"}]}
    var layer := StatusLayer.new(segment)
    segment.add_child(layer)
    layer.sync(take,feedback,true)
    check(layer.status_of_instance("current:a") == "hit"
        and layer.status_of_instance("current:b") == "unplayed",
        "Retained status ink selects the exact source head rather than every matching pitch")
    layer.sync(next_take,feedback,true)
    check(layer.status_of_instance("current:a") == "unplayed","A future copy of the same head stays uncolored")
    var state := identity()
    feedback.present_source_beat(state,3.99)
    check(feedback.status_for(take,"tie-a") == "unplayed","A tied continuation stays neutral before its own beat")
    feedback.present_source_beat(state,4.0)
    check(color(feedback,take,"tie-a") == green,"A tied continuation inherits the attack at its source beat")
    var wrong := event("attack")
    wrong.merge({"status":"unexpected","pitch":61,"played_source_beat":1.25,"staff":"right"})
    feedback.ingest(wrong)
    feedback.ingest(assessment("b","head-b",{"pitch":"wrong"}))
    check(color(feedback,take,"head-b") == red and color(feedback,take,"head-a") == green,
        "Wrong-pitch assessment colors the intended target without changing a correct earlier note")
    var ghosts: Array = feedback.ghosts_for_take(take)
    check(ghosts.size() == 1 and ghosts[0].get("beat") == 1.25 and
        ghosts[0].get("pitch") == 61 and ghosts[0].get("staff") == "right" and
        int(ghosts[0].get("lifetime_ms",0)) > 0 and
        feedback.ghosts_for_take(next_take).is_empty(),"Wrong key keeps its actual pitch, beat, take and fading lifetime")
    var forged := assessment("a","head-b",{"pitch":"correct"})
    check(feedback.ingest(forged) == "ignored" and color(feedback,take,"head-b") == red,
        "A mismatched source/head pair cannot color another note")
    feedback.ingest(assessment("b","head-b",{"pitch":"missed"}))
    check(color(feedback,take,"head-b") == red,"A missed target is red")
    feedback.ingest(assessment("b","head-b",{"pitch":"correct","onset":"on_time"}))
    var release := event("release","b")
    release.merge({"release":"short","release_advisory":true})
    feedback.ingest(release)
    check(color(feedback,take,"head-b") == green
        and feedback.statuses.record_of(take,"head-b").release == "short",
        "Advisory key-up retains the measured release without turning a clean target red")
    # The canonical matcher can retract or replace its provisional choice.
    var provisional := assessment("a","head-a",{"pitch":"correct","onset":"late"},false,11)
    feedback.ingest(provisional)
    check(color(feedback,next_take,"head-a") == red,"An out-of-tolerance provisional onset is red")
    var retract := event("assessment","a",11)
    retract.merge({"note_id":"head-a","status":"pending"})
    feedback.ingest(retract)
    check(feedback.status_for(next_take,"head-a") == "unplayed","Canonical retraction clears provisional color")
    feedback.ingest(provisional)
    feedback.ingest(assessment("a","head-a",{"pitch":"correct","onset":"on_time"},true,11))
    provisional.kind = "attack"
    provisional.status = "late"
    feedback.ingest(provisional)
    check(color(feedback,next_take,"head-a") == green,"Final clean assessment replaces and locks provisional timing")
    feedback.ingest(assessment("a","head-a",{"pitch":"wrong"},true,11))
    check(color(feedback,next_take,"head-a") == red,"A later canonical final result can replace an earlier final result")
    var stale_hit := event("attack","a",11)
    stale_hit.status = "on_time"
    feedback.ingest(stale_hit)
    check(color(feedback,next_take,"head-a") == red,"A stale provisional attack cannot repaint a final wrong note green")
    feedback.ingest(retract)
    check(color(feedback,next_take,"head-a") == red,"A provisional retraction cannot erase a settled result")
    for onset in ["early","late"]:
        feedback.ingest(assessment("b","head-b",{"pitch":"correct","onset":onset}))
        check(color(feedback,take,"head-b") == red,"Out-of-tolerance onset uses red: "+onset)
    # Ungraded Listen uses the authorized source beat for sounding, never grades.
    var listen := identity(20,7,"listen")
    listen.running = true
    var listen_take: String = feedback.statuses.take_key(listen)
    var ungraded := hit.duplicate()
    ungraded.merge(listen,true)
    ungraded.graded = false
    check(feedback.ingest(ungraded) == "ignored","Listen attacks cannot award performance credit")
    feedback.present_source_beat(listen,0.0)
    check(feedback.status_for(listen_take,"head-a") == "sounding"
        and feedback.status_for(listen_take,"tie-a") == "unplayed","Listen lights only notes reached by the shared source beat")
    feedback.present_source_beat(listen,5.0)
    check(feedback.status_for(listen_take,"head-a") == "unplayed"
        and not feedback.statuses.is_settled(listen_take,"head-a"),"Listen release leaves no graded result")
    # A later engraving may arrive after its sequenced feedback event.
    var future := event("attack")
    future.revision = 8
    future.status = "on_time"
    check(feedback.ingest(future) == "buffered","An event waits for its own source revision")
    var next_view = renderer(8)
    feedback.bind_score(next_view,8)
    var future_take: String = feedback.statuses.take_key(future)
    check(color(feedback,future_take,"head-a") == green and color(feedback,take,"head-a") == green,
        "Binding a new revision replays its event without losing an old visible source result")
    # Free's authoritative target marks arrive in teaching snapshots rather
    # than timed assessments. They must use the same source-to-head binding.
    var free := identity(30,8,"learn")
    free.feedback_marks = [{"id":"head-a","source_id":"a","status":"wrong"},
        {"id":"head-b","source_id":"a","status":"correct"}]
    feedback.present(free)
    var free_take: String = feedback.statuses.take_key(free)
    check(color(feedback,free_take,"head-a") == red
        and feedback.status_for(free_take,"head-b") == "unplayed",
        "Free colors the intended source target red and rejects mismatched target marks")
    free.feedback_marks = [{"id":"head-a","source_id":"a","status":"correct"}]
    feedback.present(free)
    check(color(feedback,free_take,"head-a") == green,"Finding the correct Free key replaces its earlier red hint")
    free.feedback_marks = []
    feedback.present(free)
    check(feedback.status_for(free_take,"head-a") == "unplayed","Restarted Free cannot inherit completed target marks")
    # The actual stage must accept graded synthetic MIDI attacks without
    # touching a removed property. This is the physical Pathétique failure
    # route: event -> LiveMidiFeedback -> PracticeScoreStage.effects.
    var stage := PracticeStage.new()
    root.add_child(stage)
    var reactions := LiveReactions.new()
    reactions.bind_layout({"attack_map":{"a":"head-a"}},7)
    var physical_hit := event("attack")
    physical_hit.status = "on_time"
    var accepted: bool = reactions.react(physical_hit,stage,7,0.0)
    check(accepted and stage.effects.impact_energy > 0.0,
        "Fresh graded MIDI must reach the actual practice stage's impact effect")
    var before_impact: float = stage.effects.impact_energy
    var stale := physical_hit.duplicate()
    stale.revision = 8
    check(not reactions.react(stale,stage,7,0.0)
        and stage.effects.impact_energy == before_impact,
        "Stale source revision cannot react on the practice stage")
    var preview := physical_hit.duplicate()
    preview.graded = false
    check(not reactions.react(preview,stage,7,0.0)
        and stage.effects.impact_energy == before_impact,
        "Ungraded Listen MIDI cannot produce a scored stage reaction")
    check(not reactions.react(physical_hit,stage,7,251.0),
        "Feedback arriving after its live effect window is ignored")
    var wrong_key := physical_hit.duplicate()
    wrong_key.status = "unexpected"
    wrong_key.source_id = ""
    wrong_key.reference_source_id = "a"
    check(reactions.react(wrong_key,stage,7,0.0),
        "Unexpected graded MIDI reacts through its bound source note")
    stage.free()
    segment.free()
    next_view.free()
    view.free()
    feedback.free()
    print("NOTE_FEEDBACK_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
