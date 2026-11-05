extends SceneTree
## Drives production score admission and production retained-note projection
## without a synthetic image oracle. Different attempts must not have any
## overlapping noteheads; legitimate simultaneous notes inside one pass remain.
const Admission := preload("res://score_stream_admission.gd")

class FakeSegment:
    extends Node2D
    var compiled := true
    var note_instances: Array = []

class InstrumentedView:
    extends "res://notation/native/view.gd"
    var additions: Array = []

    func retained_ready() -> bool:
        return true

    func _stream_add_take(source_beat: float, start_world: float,
            from_beat: float, through_beat: float, take_key: String) -> void:
        var clip := Control.new()
        clip.clip_contents = true
        add_child(clip)
        var segment := FakeSegment.new()
        clip.add_child(segment)
        for i in range(8):
            segment.note_instances.append({
                "event_id":"attack-%d" % i,
                "source_id":"source-%d" % i,
                "position":Vector2(float(i)*96.0,200.0)})
        _stream_serial += 1
        _stream_live_serial = _stream_serial
        additions.append({"at":start_world,"floor":from_beat,
            "origin":start_world-source_beat,"serial":_stream_serial})
        stream_passes.append({
            "segment":segment,"clip":clip,"world_origin":start_world-source_beat,
            "source_floor":from_beat,"source_ceiling":through_beat,
            "take_key":take_key,"serial":_stream_serial})

var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("STREAM_PROJECTED_OVERLAP_FAILED:",message)

func _initialize() -> void:
    var view := InstrumentedView.new()
    view.size = Vector2(800.0,440.0)
    view.stream_enabled = true
    view.native_ready = true
    view.timeline.duration_beats = 8.0
    view.timeline.pixels_per_beat = 96.0
    var state: Dictionary = {
        "running":true,"paused":false,"phase":"count_in",
        "mode":"practice","piece_fingerprint":"score",
        "revision":1,"transport_id":12,"play_from_beat":0.0}
    var world := 0.0
    var source := -3.0
    var total_admissions := 0
    var paused_checks := 0
    var visited: Dictionary = {}
    var snapshots_with_notes := 0
    for tick in range(150):
        var phase_step := tick%15
        if phase_step == 5:
            state["paused"] = true
            state["phase"] = "paused"
        elif phase_step == 6:
            state["paused"] = false
            state["phase"] = "count_in"
            var lead_beats: float = maxf(4.0,
                Admission.reading_lead_seconds(
                    view.stream_passes,world,60.0))
            source = maxf(0.0,source)-lead_beats
        elif phase_step == 11:
            state["transport_id"] = int(state["transport_id"])+1
            state["phase"] = "count_in"
            source = -4.0
        else:
            if not bool(state["paused"]):
                source += .15
            state["phase"] = "playing" if source >= 0.0 else "count_in" \
                if not bool(state["paused"]) else "paused"
        var before := view.additions.size()
        view.present_flow(world,state,source)
        if bool(state["paused"]):
            paused_checks += 1
            check(before == view.additions.size(),
                "pause cannot admit new source")
        for index in range(before,view.additions.size()):
            var fresh: Dictionary = view.additions[index]
            check(float(fresh["origin"])+float(fresh["floor"]) >= world +
                Admission.FUTURE_GUARD_BEATS-.0001,
                "new note ink starts in the future, not on the playhead")
            total_admissions += 1
        view.drawn_note_instances.clear()
        view.drawn_noteheads.clear()
        view.fingering_pass_clocks.clear()
        view.frame_scanned_events = 0
        view._project_stream(view.size.x*.33)
        var heads: Array = view.drawn_note_instances
        if not heads.is_empty():
            snapshots_with_notes += 1
        for i in range(heads.size()):
            var one: Dictionary = heads[i]
            var id: String = str(one["instance_id"])
            var point: Vector2 = one["position"]
            if visited.has(id):
                check(point.x <= float(visited[id])+.001,
                    "a retained notehead must never reverse its x position")
            visited[id] = point.x
            for j in range(i+1,heads.size()):
                var two: Dictionary = heads[j]
                if int(one["pass_index"]) == int(two["pass_index"]):
                    continue
                var other: Vector2 = two["position"]
                check(absf(point.x-other.x) >= 12.0 or
                      absf(point.y-other.y) >= 10.0,
                      "different score copies drew colliding noteheads")
        world += .15
    check(paused_checks>0 and total_admissions>2 and
          snapshots_with_notes>2,
        "real projection must exercise pauses, retries, and visible noteheads")
    view.free()
    print("STREAM_PROJECTED_OVERLAP_FAILURES:",failures)
    quit(0 if failures==0 else 1)
