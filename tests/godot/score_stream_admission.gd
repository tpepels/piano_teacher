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
    var first: float = Admission.position(passes,world,11.0,3.5)
    check(first > world+14.0,
        "one placement boundary keeps clef and source beyond viewport")
    passes.append({"serial":1,"owner_serial":1,"kind":"source",
        "pending":true,"armed":false,"take_key":"prepared",
        "world_origin":first,"source_floor":0.0,"source_ceiling":6.0})
    passes.append({"serial":-1,"owner_serial":1,"kind":"rest",
        "pending":false,"world_origin":first+8.0,
        "source_floor":0.0,"source_ceiling":4.0})
    check(Admission.select(passes,"ready",0.0,world,11.0,3.5)==0,
        "normal Play claims one prepositioned original source")
    check(Admission.select(passes,"idle",0.0,world)==0,
        "idle retimes the existing hidden source, never a second copy")
    check(Admission.select(passes,"ready",0.0,first-6.0,11.0,3.5)==-1,
        "any source whose header entered the viewport fails safe")
    check(not is_finite(Admission.position(passes,world,11.0,3.5,
        first+1.0)),"explicit placement must reject overlaps including paired rests")
    var retimed: float = Admission.position(passes,first-7.0,11.0,3.5,
        NAN,1,Admission.READY_TRAVEL_BEATS)
    check(retimed>first,
        "repositioning excludes only the hidden owner's source and rest")
    passes[0]["take_key"] = "transport-one"
    passes[0]["pending"] = false
    check(Admission.select(passes,"paused",0.0,world,0.0,0.0,
        "transport-one")==0,
        "paused source can be reused before its first graded note")
    check(Admission.select(passes,"paused",0.0,first+1.0,0.0,0.0,
        "transport-one")==-1,
        "passed source cannot be reused by Resume")
    var second_world: float = first+21.0
    passes.append({"serial":2,"owner_serial":2,"kind":"source",
        "pending":true,"armed":false,"take_key":"autopending",
        "world_origin":second_world,"source_floor":0.0,"source_ceiling":6.0})
    check(Admission.select(passes,"ready",0.0,world)==-1,
        "READY must never select an automatic successor or a published take")
    check(Admission.select(passes,"automatic",0.0,world,11.0,3.5)==2,
        "manual Retry can claim already printed automatic source")
    check(Admission.select(passes,"automatic_due",0.0,second_world,
        0.0,0.0,"",second_world)==2,
        "backend automatic deadline binds even when its onset is due now")
    check(Admission.select(passes,"automatic_due",0.0,second_world,
        0.0,0.0,"",second_world+1.0)==-1,
        "backend deadlines cannot bind a different automatic passage")
    check(Admission.select(passes,"bound",0.0,world,0.0,0.0,
        "transport-one")==0,"first backend attempt selects its bound source")
    passes.append({"serial":3,"owner_serial":3,"kind":"source",
        "pending":false,"take_key":"transport-one",
        "world_origin":second_world+10.0,
        "source_floor":2.0,"source_ceiling":6.0})
    check(Admission.select(passes,"bound",0.0,world,0.0,0.0,
        "transport-one")==3,
        "same backend transport chooses the latest disjoint Resume interval")
    check(Admission.position(passes,world,11.0,3.5) >=
        second_world+6.0+Admission.REST_GAP_BEATS+3.5,
        "future passage must clear all existing note and rest extents")
    check(Admission.lead_seconds(first,world,31.0)>25.0,
        "grading respects offscreen travel at low tempo")
    var bounds: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,4.0)
    check(bounds.x < -300 and bounds.y > 384,
        "engraved header and last notehead remain in crop")
    var interior: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,8.0)
    check(is_equal_approx(interior.y,384.0),
        "internal measure boundary may not show half the next note")
    print("SCORE_STREAM_ADMISSION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
