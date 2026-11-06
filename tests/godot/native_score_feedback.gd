extends SceneTree
const Status := preload("res://note_status_registry.gd")
const Ink := preload("res://note_status_ink.gd")

class GlyphRecorder extends RefCounted:
    var paints: Array = []
    func paint(_canvas: CanvasItem, name: String, x: float, y: float,
            gap: float, tone: Color, centered: bool = false) -> bool:
        paints.append({"name":name,"x":x,"y":y,"gap":gap,
            "tone":tone,"centered":centered})
        return true

class Score extends Control:
    var glyphs := GlyphRecorder.new()
    var drawn_noteheads := {
        "a":Vector2(100,80),"b":Vector2(155,80),
        "c":Vector2(205,80),"d":Vector2(255,80),
        "e":Vector2(310,80),"f":Vector2(350,80)}
    var drawn_note_instances: Array = []
    var stream_passes: Array = []
    var layout := {"ordered_events":[
        {"id":"a","kind":"note","note_type":"quarter",
            "source_id":"sa","is_attack":true},
        {"id":"b","kind":"note","note_type":"half",
            "source_id":"sb","is_attack":true},
        {"id":"c","kind":"note","note_type":"whole",
            "source_id":"sc","is_attack":true},
        {"id":"d","kind":"note","note_type":"quarter",
            "source_id":"sd","is_attack":true},
        {"id":"e","kind":"note","note_type":"quarter",
            "source_id":"se","is_attack":true},
        {"id":"f","kind":"note","note_type":"quarter",
            "source_id":"sf","is_attack":true}]}
    func staff_gap() -> float:
        return 16.0

var failures: Array[String] = []
func check(ok: bool, reason: String) -> void:
    if not ok:
        failures.append(reason)
        push_error("NATIVE_FEEDBACK_FAILED: "+reason)

func _state(transport: int) -> Dictionary:
    return {"piece_fingerprint":"fixture","revision":7,
        "mode":"practice","phase":"playing","running":true,
        "transport_id":transport,"preview_only":false,
        "feedback_marks":[],"midi_visual_events":[]}

func _assert_ink(paints: Array, glyph: String, x: float,
        status: String) -> bool:
    var color: Color = Ink.color_for(status)
    var core := 0
    var inner := 0
    var outer := 0
    for paint in paints:
        if str(paint["name"]) != glyph or \
                absf(float(paint["x"])-x) > .001:
            continue
        var tone: Color = paint["tone"]
        if absf(tone.r-color.r) > .0001 or \
                absf(tone.g-color.g) > .0001 or \
                absf(tone.b-color.b) > .0001:
            continue
        var gap: float = float(paint["gap"])
        if absf(gap-16.0)<.001 and tone.a > .9:
            core += 1
        elif absf(gap-16.0*Ink.INNER_SCALE)<.001 and \
                tone.a <= .11:
            inner += 1
        elif absf(gap-16.0*Ink.OUTER_SCALE)<.001 and \
                tone.a <= .05:
            outer += 1
    return core==1 and inner==1 and outer==1

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var canonical := Status.new()
    check(canonical.record("take","id",Status.HIT) and
        canonical.status("take","id") == Status.HIT and
        canonical.record("take","id",Status.EARLY_RELEASE,true) and
        canonical.status("take","id") == Status.EARLY_RELEASE and
        not canonical.record("take","id",Status.HIT,false),
        "canonical status updates work and settled feedback overrides provisional hits")
    check(canonical.status("other","id")==Status.UNPLAYED,
        "a new take has no inherited note statuses")
    var score := Score.new()
    score.size = Vector2(720,180)
    var a: String = Status.take_key(_state(8))
    var b: String = Status.take_key(_state(9))
    score.stream_passes = [
        {"serial":10,"kind":"source","take_key":a},
        {"serial":11,"kind":"source","take_key":b}]
    for id in score.drawn_noteheads:
        score.drawn_note_instances.append({
            "event_id":id,"position":score.drawn_noteheads[id],
            "pass_index":10})
    # Same semantic note, physically present in a newer retry copy.
    score.drawn_note_instances.append({
        "event_id":"a","position":Vector2(480,80),"pass_index":11})
    score.drawn_note_instances.append({
        "event_id":"b","position":Vector2(530,80),"pass_index":11})
    root.add_child(score)
    var feedback = load("res://native_score_feedback.gd").new()
    root.add_child(feedback)
    feedback.size = score.size
    feedback.bind_score(score,7)
    check(feedback.status_for(a,"a") == Status.UNPLAYED,
        "every original note starts unplayed")
    check(Ink.glow_strength(Status.UNPLAYED) == 0.0 and \
            Ink.glow_strength(Status.HIT) > 0.0 and \
            Ink.glow_strength(Status.HIT) <= .05,
        "only played/graded notes have a minor contour-bound glow")
    await process_frame
    score.glyphs.paints.clear()
    feedback.queue_redraw()
    await process_frame
    check(score.glyphs.paints.is_empty(),
        "unplayed noteheads retain the original unmodified Verovio ink")
    var state := _state(8)
    state.midi_visual_events = [{"sequence":1,"source_id":"sa",
        "transport_id":8,"status":"on_time","age":.01}]
    feedback.present(state)
    check(feedback.status_for(a,"a")==Status.HIT,
        "live accepted attack colors its correct note immediately")
    feedback.present(state)
    check(feedback.statuses.snapshot().get(a,{}).size()==1,
        "repeated polls cannot duplicate or recolor another note")
    score.glyphs.paints.clear()
    feedback.queue_redraw()
    await process_frame
    check(_assert_ink(score.glyphs.paints,"head_black",100,Status.HIT),
        "hit renders subtle mint directly through authentic notehead mask")
    check(not score.glyphs.paints.any(func(item: Dictionary) -> bool:
        return absf(float(item.get("x",0))-480)<.001),
        "next unplayed repetition of the SAME note stays completely unchanged")
    state.feedback_marks = [
        {"note_id":"a","status":"correct"},
        {"note_id":"b","status":"missed"},
        {"note_id":"c","status":"late"},
        {"note_id":"d","status":"short"},
        {"note_id":"e","status":"early"},
        {"note_id":"f","status":"extra","estimated":true}]
    feedback.present(state)
    check(feedback.status_for(a,"a")==Status.HIT and \
            feedback.status_for(a,"b")==Status.MISSED and \
            feedback.status_for(a,"c")==Status.LATE and \
            feedback.status_for(a,"d")==Status.EARLY_RELEASE and \
            feedback.status_for(a,"e")==Status.EARLY_ONSET,
        "hit missed late early release and early onset all have distinct records")
    check(feedback.status_for(a,"f")==Status.UNPLAYED,
        "unmatched/estimated extras cannot color a printed source note")
    score.glyphs.paints.clear()
    feedback.queue_redraw()
    await process_frame
    check(_assert_ink(score.glyphs.paints,"head_half",155,Status.MISSED),
        "missed uses exactly the engraved hollow note contour in coral")
    check(_assert_ink(score.glyphs.paints,"head_whole",205,Status.LATE),
        "late has its own golden status on the actual whole note")
    check(_assert_ink(score.glyphs.paints,"head_black",255,Status.EARLY_RELEASE),
        "early release has independent lavender status from Python short grade")
    check(_assert_ink(score.glyphs.paints,"head_black",310,Status.EARLY_ONSET),
        "early onset is not mislabeled as an early key release")
    state.feedback_marks = [{"note_id":"f","status":"short",
        "release_unobserved":true}]
    feedback.present(state)
    check(feedback.status_for(a,"f")==Status.LATE,
        "an unreleased held note must never be shown as an early release")
    state.feedback_marks = []
    feedback.present(state)
    check(feedback.status_for(a,"b")==Status.MISSED,
        "graded status persists after the backend slides its feedback window")
    var next := _state(9)
    feedback.present(next)
    check(feedback.status_for(a,"b")==Status.MISSED and \
            feedback.status_for(b,"b")==Status.UNPLAYED,
        "old moving copy retains grade while next take is unplayed")
    next.feedback_marks = [{"note_id":"b","status":"correct"}]
    feedback.present(next)
    score.glyphs.paints.clear()
    feedback.queue_redraw()
    await process_frame
    check(_assert_ink(score.glyphs.paints,"head_half",155,Status.MISSED) and \
            _assert_ink(score.glyphs.paints,"head_half",530,Status.HIT),
        "two simultaneous copies of the same source note have distinct colors")
    next.preview_only = true
    feedback.present(next)
    check(feedback.status_for(a,"b")==Status.MISSED,
        "preview cannot erase authoritative already-visible assessment")
    score.glyphs.paints.clear()
    feedback.queue_redraw()
    await process_frame
    check(score.glyphs.paints.is_empty(),
        "ungraded preview never paints a misleading graded head")
    next.preview_only = false
    feedback.present(next)
    check(feedback.status_for(a,"b")==Status.MISSED,
        "restoring practice preserves already graded notes in old copies")
    var other_score := Score.new()
    root.add_child(other_score)
    feedback.bind_score(other_score,8)
    check(feedback.statuses.snapshot().is_empty(),
        "new engraving revision resets all old note-status records")
    feedback.free()
    score.free()
    other_score.free()
    print("NATIVE_FEEDBACK_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
