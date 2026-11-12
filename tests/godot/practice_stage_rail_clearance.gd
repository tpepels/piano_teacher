extends SceneTree
## G1: every notation view in the practice stage's score frame keeps its ink
## above the progress rail: the stage's own view, and views the score
## runway adds later (a pre-engraved next stage, a promoted replacement).

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var failures: Array[String] = []
    var stage = load("res://practice_score_stage.gd").new()
    stage.size = Vector2(1600, 700)
    root.add_child(stage)
    await process_frame
    var rail: float = load("res://notation/shared/view_base.gd").PROGRESS_RAIL_CLEARANCE
    if stage.renderer == null or float(stage.renderer.layout.bottom_clearance) != rail:
        failures.append("the stage's own view clears the rail")
    var later = load("res://notation/native/view.gd").new()
    stage.score_frame.add_child(later)
    if float(later.layout.bottom_clearance) != rail:
        failures.append("a view added later clears the rail before it lays out")
    var loose = load("res://notation/native/view.gd").new()
    root.add_child(loose)
    if float(loose.layout.bottom_clearance) != 0.0:
        failures.append("a view outside the practice stage keeps the old margins")
    for failure in failures:
        print("RAIL_CLEARANCE_FAIL: ", failure)
    print("RAIL_CLEARANCE_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
