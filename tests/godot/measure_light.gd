extends SceneTree

func _initialize() -> void:
    var script = load("res://notation/native/measure_light.gd")
    if script == null:
        printerr("MEASURE_LIGHT: missing presentation helper")
        quit(1)
        return
    var measures := [{"start_beat":0.0,"end_beat":1.0},
        {"start_beat":1.0,"end_beat":4.0}, {"start_beat":4.0,"end_beat":9.0}]
    var contract := {"stride_beats":12.0,"gap":{"start_beat":9.0,"end_beat":12.0}}
    var failures := 0
    for pair in [[-.1,Vector2.INF],[0.0,Vector2(0,1)],
            [.999,Vector2(0,1)],[1.0,Vector2(1,4)],
            [8.99,Vector2(4,9)],[9.0,Vector2.INF]]:
        if script.interval(measures, pair[0], {}, {}, INF) != pair[1]:
            failures += 1
    if script.interval(measures,13.0,contract,{},INF) != Vector2(13,16):
        failures += 1
    if script.interval(measures,10.0,contract,{},INF) != Vector2(9,12):
        failures += 1
    var history := {12.0:{"measure":{"start_beat":11.0,"end_beat":14.0}}}
    if script.interval(measures,13.0,contract,history,INF) != Vector2(11,14):
        failures += 1
    if script.interval(measures,12.0,contract,{},12.0) != Vector2.INF:
        failures += 1
    print("MEASURE_LIGHT_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
