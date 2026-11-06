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
    # With a low practice tempo, redundant blank travel used to exceed
    # five seconds before the earliest glyph reached the viewport edge.
    # Keep the real printed header offscreen yet show its first ink promptly.
    var ready_start: float = Admission.position(
        [],world,11.0,3.5,NAN,Admission.READY_TRAVEL_BEATS)
    var offscreen_entry_beats: float = ready_start-world-11.0-3.5
    var offscreen_entry_seconds: float = offscreen_entry_beats*60.0/31.0
    check(offscreen_entry_beats > 0.0 and
        offscreen_entry_seconds < 1.5,
        "at 31 BPM the first clef enters from outside the screen within 1.5 seconds")
    check(ready_start-world > 11.0+3.5,
        "faster entry cannot position initial score ink inside the viewport")
    passes.append({"serial":1,"owner_serial":1,"kind":"source",
        "pending":true,"armed":false,"take_key":"prepared",
        "world_origin":first,"source_floor":0.0,"source_ceiling":6.0})
    passes.append({"serial":-1,"owner_serial":1,"kind":"rest",
        "pending":false,"world_origin":first+8.0,
        "source_floor":0.0,"source_ceiling":4.0})
    check(Admission.select(passes,"ready",0.0,world,11.0,3.5)==0,
        "normal Play claims one prepositioned original source")
    check(Admission.select(passes,"idle",0.0,world)==0,
        "idle identifies its unexposed candidate for safe tail withdrawal")
    check(Admission.select(passes,"ready",0.0,first-6.0,11.0,3.5)==-1,
        "any source whose header entered the viewport fails safe")
    check(not is_finite(Admission.position(passes,world,11.0,3.5,
        first+1.0)),"explicit placement must reject overlaps including paired rests")
    var appended: float = Admission.position(passes,first-7.0,11.0,3.5,
        NAN,Admission.READY_TRAVEL_BEATS)
    check(appended>first+12.0,
        "new READY passage follows original source/rest without retiming them")
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
    var preview_horizon: float = Admission.automatic_horizon(4.0,2.0,1.2)
    var previous: Array = [
        {"owner_serial":7,"world_origin":20.0,"source_floor":0.0,
            "source_ceiling":8.0,"kind":"source"},
        {"owner_serial":7,"world_origin":28.0,"source_floor":0.0,
            "source_ceiling":4.0,"kind":"rest"}]
    var next_expected: float = 20.0+8.0+preview_horizon
    check(is_equal_approx(preview_horizon,6.2) and
        is_equal_approx(Admission.position(
            previous,20.0,2.0,1.2,next_expected),next_expected),
        "preview/auto source clears written rest and header at exact backend deadline")
    check(not is_finite(Admission.position(
            previous,20.0,2.0,1.2,next_expected-.2)),
        "renderer must reject a shorter deadline instead of silently retiming notes")
    var bounds: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,4.0)
    check(bounds.x < -300 and bounds.y > 384,
        "engraved header and last notehead remain in crop")
    var interior: Vector2 = Admission.engraved_clip_bounds(
        0.0,4.0,96.0,24.0,8.0)
    check(is_equal_approx(interior.y,384.0),
        "internal measure boundary may not show half the next note")
    # Source's final barline/trailing notation belongs to the occupied
    # world interval. The next score's header must clear that actual ink,
    # not just its source_ceiling beat (which would clip overlapping bars).
    var ended: Array = [{"kind":"source","owner_serial":12,
        "world_origin":10.0,"source_floor":0.0,"source_ceiling":4.0}]
    var d := 96.0
    var g := 24.0
    var last_ink: float = 10.0 + Admission.clip_bounds(
        ended[0],d,g,4.0).y/d
    var safe: float = Admission.position(ended,10.0,2.0,3.75,
        NAN,0.0,d,g,4.0)
    check(last_ink > 14.0 and safe >= last_ink+3.75,
        "new source begins beyond the last actual printed pixel and next header")
    var premature: float = Admission.position(ended,10.0,2.0,3.75,
        last_ink+3.0,0.0,d,g,4.0)
    check(not is_finite(premature),
        "a source position that overlaps the preceding printed clip is rejected")
    print("SCORE_STREAM_ADMISSION_FAILURES:",failures)
    quit(0 if failures==0 else 1)
