extends SceneTree
## The perpetual blank bar keeps source-authored meter and phase, including
## after notes/rest have exited. No fixed first-measure modulo is allowed.
const Grid := preload("res://moving_meter_grid.gd")
var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("MOVING_METER_GRID_FAILED:",message)

func contains_at(values: Array[float], point: float) -> bool:
    for value in values:
        if absf(value-point) < .00001:
            return true
    return false

func _initialize() -> void:
    var measures: Array = [
        {"start_beat":0.0,"end_beat":4.0},
        {"start_beat":4.0,"end_beat":7.0},
        {"start_beat":7.0,"end_beat":9.0}]
    var lines: Array[float] = Grid.visible_lines(
        6.6,800.0,264.0,100.0,0.0,measures)
    check(contains_at(lines,4.0) and contains_at(lines,7.0)
        and contains_at(lines,9.0) and contains_at(lines,11.0),
        "4/4 to 3/4 to 2/4 has exact source boundary and last-meter continuation")
    check(not contains_at(lines,8.0) and not contains_at(lines,12.0),
        "uniform 4/4 phantom bars must be absent after meter changes")
    var shifted: Array[float] = Grid.visible_lines(
        16.6,800.0,264.0,100.0,10.0,measures)
    check(contains_at(shifted,14.0) and contains_at(shifted,17.0)
        and contains_at(shifted,19.0),
        "score source origin translates all barlines into one immutable world")
    var pickup: Array[float] = Grid.visible_lines(
        1.0,800.0,264.0,100.0,0.0,[
            {"start_beat":0.0,"end_beat":1.0},
            {"start_beat":1.0,"end_beat":4.0}])
    check(contains_at(pickup,1.0) and contains_at(pickup,4.0),
        "pickup has a genuine one-beat first measure and later full meter")
    var empty: Array[float] = Grid.visible_lines(
        4.0,800.0,264.0,100.0,0.0,[])
    check(contains_at(empty,4.0) and contains_at(empty,8.0),
        "empty startup score uses the same continuously scrolling default 4/4")
    var many: Array = []
    for index in range(1000):
        many.append({"start_beat":float(index)*3.0,
            "end_beat":float(index+1)*3.0})
    var bounded: Array[float] = Grid.visible_lines(
        2000.0,800.0,264.0,100.0,0.0,many)
    check(contains_at(bounded,2001.0) and bounded.size() < 20,
        "large source returns only viewport-local bars without a complete scan")
    print("MOVING_METER_GRID_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
