extends SceneTree

const FingeringSpatialLayout := preload("res://notation/native/fingering_spatial_layout.gd")

func _initialize() -> void:
    var failures := 0
    var bins := {}
    var obstacle := Rect2(100,100,30,30)
    FingeringSpatialLayout.block(obstacle,bins,64)
    if FingeringSpatialLayout.is_clear(obstacle,bins,64,[],400):
        failures += 1
    if not FingeringSpatialLayout.is_clear(Rect2(240,240,20,20),bins,64,[],400):
        failures += 1
    if FingeringSpatialLayout.is_clear(Rect2(100,180,20,20),bins,64,
            [Rect2(80,185,100,1)],400):
        failures += 1
    var samples := [{
        "event":{"id":"a","beat":0.0,"source_id":"a"},
        "assignment":{"hand":"right","finger":2,"source_id":"a"},
        "event_ids":["a"], "head":Vector2(180,135),
        "up":true, "direction":-1.0, "chord":false, "staff_center":160.0
    }]
    var metrics := {"cell":Vector2(14,20),"ink_offset":Vector2(1,5),
        "ink_size":Vector2(12,13)}
    var packed: Dictionary = FingeringSpatialLayout.pack(samples,metrics,
        20,400,64,bins,[],15)
    if packed["layout"].size() != 1 or not packed["issues"].is_empty():
        failures += 1
    print("FINGERING_SPATIAL_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
