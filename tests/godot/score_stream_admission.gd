extends SceneTree
const Admission := preload("res://score_stream_admission.gd")
var failures := 0

func check(ok: bool, name: String) -> void:
    if not ok:
        failures += 1
        print("SCORE_STREAM_ADMISSION_FAILED:",name)

func _initialize() -> void:
    var waiting: Dictionary = Admission.window(-5.0,0.0,8.0)
    check(not waiting["admit"],"no source admitted too early in count-in")
    var opening: Dictionary = Admission.window(-2.0,0.0,8.0)
    check(opening["admit"] and opening["floor"]==0.0 and \
        is_equal_approx(opening["ceiling"],1.5),"source ahead of playhead")
    check(10.0+float(opening["floor"])-(-2.0)>10.0,
        "all first-admitted noteheads have a future world time")

    var take: Array = [{"take_key":"piece|1|2|practice",
        "world_origin":6.0,"source_ceiling":2.5}]
    var occupied: float = Admission.reserved_through(
        take,"piece|1|2|practice",8.0)
    check(is_equal_approx(occupied,2.5),"pause retains future notes")
    var resumed: Dictionary = Admission.window(0.0,0.0,8.0,occupied)
    check(is_equal_approx(resumed["floor"],2.5) and \
        resumed["ceiling"]>resumed["floor"],
        "resume never re-admits a source interval still in flight")
    check(Admission.reserved_through(
        take,"piece|1|2|practice",10.0)==-INF,
        "expired notes can be offered again after long pauses")
    check(Admission.reserved_through(
        take,"piece|1|3|practice",8.0)==-INF,
        "a new attempt has an independent source identity")
    var tail: Dictionary = Admission.window(7.0,0.0,8.0)
    check(is_equal_approx(tail["ceiling"],8.0),
        "source admission never extends beyond the engraved score")
    print("SCORE_STREAM_ADMISSION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
