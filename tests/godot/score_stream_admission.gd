extends SceneTree
## Regress the exact window policy and cross-pass note placement, including
## adversarial rapid Pause/Resume/Retry sequences with shared pitches.
const Admission := preload("res://score_stream_admission.gd")
var failures := 0

func check(ok: bool, name: String) -> void:
    if not ok:
        failures += 1
        print("SCORE_STREAM_ADMISSION_FAILED:",name)

func _initialize() -> void:
    var take: Array = []
    var notes: Array = [
        {"beat":0.0,"pitch":60},{"beat":0.5,"pitch":64},
        {"beat":1.0,"pitch":67},{"beat":2.0,"pitch":60},
        {"beat":3.0,"pitch":60},{"beat":4.0,"pitch":60},
        {"beat":5.0,"pitch":60},{"beat":6.0,"pitch":60},
        {"beat":7.0,"pitch":60}
    ]
    var start := Admission.window(-3.0,0.0,8.0,0.0,take)
    check(start["admit"] and is_equal_approx(start["floor"],0.0) and \
            is_equal_approx(start["ceiling"],.5),
        "count-in admits only future authentic score")
    take.append({"serial":1,"take_key":"attempt-1","world_origin":3.0,
        "source_floor":0.0,"source_ceiling":3.5})
    check(is_equal_approx(Admission.furthest_occupied_world(take,4.0),6.5),
        "old note ink remains reserved during pause")
    check(Admission.next_safe_world(take,4.0) > 7.0,
        "a retry cannot enter the existing moving score interval")

    var origin := 4.0
    var attempts := 1
    var prevented := 0
    for step in range(90):
        # Repeated pause/resume on the SAME graded transport and intentional
        # retries with another transport id both must respect global world ink.
        var source: float = -3.0 if step%3!=0 else -1.0
        var slot: Dictionary = Admission.window(source,0.0,8.0,origin,take)
        if bool(slot["admit"]):
            var candidate: Dictionary = {
                "serial":attempts+1,"take_key":"attempt-%d" % (step/3),
                "world_origin":origin-source,
                "source_floor":float(slot["floor"]),
                "source_ceiling":float(slot["ceiling"])}
            # Two genuine copies cannot occupy the same world interval.
            for older in take:
                var new_start: float = float(candidate["world_origin"]) + \
                    float(candidate["source_floor"])
                var new_end: float = float(candidate["world_origin"]) + \
                    float(candidate["source_ceiling"])
                var old_start: float = float(older["world_origin"]) + \
                    float(older["source_floor"])
                var old_end: float = float(older["world_origin"]) + \
                    float(older["source_ceiling"])
                check(not (new_start < old_end and old_start < new_end),
                    "attempt %d cannot overlap retained attempt" % step)
            take.append(candidate)
            attempts += 1
        else:
            prevented += 1
        var heads: Array = Admission.collision_pairs(take,notes,origin,96.0)
        check(heads.is_empty(),"different attempts cannot draw overlapping noteheads")
        origin += .12
    check(prevented>0 and attempts>1,
        "test must exercise queued deferral AND successful admission")
    var at_end: Dictionary = Admission.window(7.9,0.0,8.0,100.0,[])
    check(not at_end["admit"],"no note may be injected at the present time")
    check(Admission.reading_lead_seconds(take,origin,60.0)>0.0,
        "next transport deadline has a bounded reading lead")
    var bounds: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,4.0)
    check(bounds.x <= -300.0 and bounds.y >= 432.0,
        "first measure clip preserves negative Verovio clef/key/meter ink and terminal noteheads")
    var later: Vector2 = Admission.engraved_clip_bounds(
        2.0,4.0,96.0,24.0,4.0)
    check(later.x < 192.0 and later.x > 140.0,
        "resumed source reveals full first notehead without a second opening header")
    var interior: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,8.0)
    check(is_equal_approx(interior.y,384.0),
        "internal measure crop does not leak the next measure's first note")
    check(Admission.reading_lead_seconds(take,4.0,60.0,4.0) >
          Admission.reading_lead_seconds(take,4.0,60.0),
        "new opening context reserves room after previously exposed ink")
    var wide := Admission.window(-2.5,0.0,8.0,0.0,[],11.0)
    check(wide["admit"] and is_equal_approx(wide["ceiling"],8.0),
        "responsive visible source runs beyond the former 3.5-beat clip")
    print("SCORE_STREAM_ADMISSION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
