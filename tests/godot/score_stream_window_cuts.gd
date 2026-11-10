extends SceneTree
## Measure splits are withdrawable ONLY when the retained authentic graphic
## has an unoccupied pixel column. Changing a seam never edits MIDI beats.
const Cuts := preload("res://score_stream_window_cuts.gd")
var failures := 0

func check(ok: bool,why: String) -> void:
    if not ok:
        failures += 1
        print("SCORE_STREAM_WINDOW_CUT_FAILED:",why)

func _initialize() -> void:
    var measures: Array = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":8.0},
        {"start_beat":8.0,"end_beat":12.0}]
    var source: Array[Vector2] = [
        Vector2(3.94,4.07), # first notehead would split at bar 2
        Vector2(7.86,7.90)]
    var safe: Array[Vector2] = Cuts.safe_windows(
        0.0,12.0,measures,source)
    check(safe.size()==3,
        "a barline notehead shifts one cut without merging entire piece")
    check(safe[0].y < 3.94 and safe[1].x == safe[0].y and
        safe[1].y == safe[2].x,
        "no split intersects the photographic full notehead contour")
    check(is_equal_approx(safe[1].y,8.0),
        "an unrelated later boundary stays at its actual authored beat")
    var tied: Array[Vector2] = [Vector2(3.0,5.0)]
    var grouped: Array[Vector2] = Cuts.safe_windows(
        0.0,12.0,measures,tied)
    check(grouped.size()==2 and is_equal_approx(grouped[0].y,8.0),
        "a cross-measure tie is an indivisible visual FIFO unit")
    var stacked: Array[Vector2] = [Vector2(3.8,4.05),
        Vector2(4.04,4.25),Vector2(4.22,4.35)]
    var unioned: Array[Vector2] = Cuts.safe_windows(
        0.0,12.0,measures,stacked)
    check(unioned.size()==3 and
        unioned[0].y < 3.8 and unioned[0].y > 3.4,
        "overlapping glyph clusters use one actual whitespace seam")
    var dense: Array[Vector2] = [Vector2(3.3,4.7),
        Vector2(7.3,8.7)]
    var inseparable: Array[Vector2] = Cuts.safe_windows(
        0.0,12.0,measures,dense)
    check(inseparable.size()==1 and
        inseparable[0] == Vector2(0,12),
        "unavoidable spanning ink retains whole connected visual group")
    var resumed: Array[Vector2] = Cuts.safe_windows(
        3.25,12.0,measures,source)
    check(is_equal_approx(resumed[0].x,3.25),
        "resume preserves exact source opening, not a rounded measure start")
    var long_measures: Array = []
    var long_ink: Array[Vector2] = []
    for index in range(1000):
        long_measures.append({"start_beat":float(index)*4.0,
            "end_beat":float(index+1)*4.0})
        long_ink.append(Vector2(float(index)*4.0+.5,
            float(index)*4.0+1.0))
    var many: Array[Vector2] = Cuts.safe_windows(
        0.0,4000.0,long_measures,long_ink)
    check(many.size()==1000,
        "large score preserves independent measure strips and linear-time cuts")
    print("SCORE_STREAM_WINDOW_CUT_FAILURES:",failures)
    quit(0 if failures==0 else 1)
