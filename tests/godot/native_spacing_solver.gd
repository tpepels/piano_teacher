extends SceneTree
const Spacing := preload("res://notation/native/spacing_layout.gd")
const Index := preload("res://notation/native/score_index.gd")
func _initialize() -> void:
    var failures: Array = []
    if OS.get_environment("PIANO_TEACHER_NATIVE_NOTATION") != "1":
        failures.append("Native engine must be selected")
    # A displaced source head already consumes 1.2 of the two-space budget.
    # The solver must translate its WHOLE rigid sprite, rather than clamping
    # the child head separately or merging it into its adjacent attack.
    var groups: Array = [
        {"id":"second","beat":0.0,"staff":"right","min_head":0.0,"max_head":1.2,
            "parts":[Rect2(-.6,0,2.4,1)],"left":-.6,"sweep_reach":8.0},
        {"id":"next","beat":.00625,"staff":"right","min_head":0.0,"max_head":0.0,
            "parts":[Rect2(-.6,0,1.2,1)],"left":-.6,"sweep_reach":8.0}]
    var solution: Dictionary = Spacing.solve(groups,20.0,480.0)
    if not bool(solution.get("ok",false)):
        failures.append("Dense source-displaced chord must fit")
    else:
        var first: float = float(solution["shifts"]["second"])
        var last: float = float(solution["shifts"]["next"])
        if absf(first)>2.00001 or absf(first+1.2)>2.00001 or absf(last)>2.00001:
            failures.append("Source head displacement must count toward the total bound")
        if first+1.8 > last-.6+.15-.00001:
            failures.append("Distinct authentic head footprints cannot overlap")
    # An interval spanning the viewport must survive culling even when its
    # first attack lies far outside it; remote short fragments are omitted.
    var items: Array = [{"id":"long","a":0.0,"b":1000.0},
        {"id":"remote","a":1.0,"b":2.0},{"id":"visible","a":499.0,"b":501.0}]
    var index: Dictionary = Index.interval_index(items,
        func(item: Dictionary) -> float: return float(item["a"]),
        func(item: Dictionary) -> float: return float(item["b"]))
    var visible: Array = Index.visible_intervals(index,500.0,500.5)
    if visible.size()!=2 or visible[0]["id"]!="long" or visible[1]["id"]!="visible":
        failures.append("Visible interval tree must retain long authentic spanners")
    print("NATIVE_SPACING_SOLVER_FAILURES:",failures.size()," ",failures)
    quit(0 if failures.is_empty() else 1)
