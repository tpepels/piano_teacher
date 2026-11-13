extends SceneTree
var failures := 0
func check(ok: bool, message: String) -> void:
    if not ok:
        failures += 1
        print("TEACHING_COORDINATORS_FAIL:",message)
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    check(ResourceLoader.exists("res://practice_command_coordinator.gd"),"command lifecycle owner absent")
    check(ResourceLoader.exists("res://practice_frame_coordinator.gd"),"frame snapshot projection owner absent")
    var stage = load("res://practice_score_stage.gd").new()
    root.add_child(stage)
    for dimensions in [Vector2(800,460), Vector2(1600,700)]:
        stage.size = dimensions
        await process_frame
        stage._present_hand_cue({"loaded":true,"hand":"both","phase":"count_in","transport_id":1})
        stage.count_in.present(-3.5,4,true,false,4.)
        await process_frame
        var badge: Rect2 = stage.hand_cue_panel.get_global_rect()
        var lights: Rect2 = stage.count_in.get_global_rect()
        check(not badge.intersects(lights),"Both hands overlaps count-in at "+str(dimensions))
    stage.queue_free()
    print("TEACHING_COORDINATORS_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
