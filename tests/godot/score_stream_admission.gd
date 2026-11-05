extends SceneTree
const Admission := preload("res://score_stream_admission.gd")
var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("SCORE_STREAM_ADMISSION_FAILED:",message)
func _initialize() -> void:
    var world := 20.0
    var passes: Array = []
    var first := Admission.future_start(passes,world,11.0,3.5)
    check(first>world+14.0,
        "first clef and source note must start beyond viewport edge")
    passes.append({"serial":1,"pending":true,
        "world_origin":first,"source_floor":0.0,"source_ceiling":6.0})
    check(Admission.pending_index(passes,0.0,world)==0,
        "Play selects already reserved original source")
    check(Admission.future_start(passes,world,11.0,3.5) >=
        first+6.0+Admission.REST_GAP_BEATS+3.5,
        "upcoming repeat cannot collide with still-moving first copy")
    check(Admission.pending_index(passes,0.0,first+1.0)==-1,
        "a past or imminent first note is not available to Play")
    check(Admission.lead_seconds(first,world,31.0)>25.0,
        "graded start must respect actual offscreen travel even at slow BPM")
    var bounds: Vector2 = Admission.engraved_clip_bounds(0.0,4.0,96.0,24.0,4.0)
    check(bounds.x < -300 and bounds.y > 384,
        "source header and last original notehead remain within crop")
    var interior: Vector2 = Admission.engraved_clip_bounds(0.0,4.0,96.0,24.0,8.0)
    check(is_equal_approx(interior.y,384.0),
        "one source copy never exposes half of another measure")
    print("SCORE_STREAM_ADMISSION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
