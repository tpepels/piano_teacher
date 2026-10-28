extends SceneTree

const RestLanes := preload("res://notation/native/rest_lane_layout.gd")

func _initialize() -> void:
    var failures := 0
    var voices := ["1","2"]
    var offsets: Array = RestLanes.candidate_offsets("1", voices, "quarter")
    if offsets.size() != 29 or offsets[0] != -1.0:
        failures += 1
    var whole: Array = RestLanes.candidate_offsets("2", voices, "whole")
    if whole.size() != 29 or whole[0] != 1.0 or whole[1] != 2.0:
        failures += 1
    var default_ink := Rect2(0,0,10,8)
    var obstacle := [{"voice":"2","ink":Rect2(0,-10,10,9)}]
    var result: Dictionary = RestLanes.place_rest(
        default_ink,"1",voices,"quarter",10.0,obstacle)
    if not result["placed"] or absf(float(result["shift"])+1.0) < .0001:
        failures += 1
    if (result["ink"] as Rect2).intersects(
            (obstacle[0]["ink"] as Rect2).grow(.6)):
        failures += 1
    # Another event in the SAME voice must not displace this rest.
    var same_voice := [{"voice":"1","ink":Rect2(0,-10,10,9)}]
    var same: Dictionary = RestLanes.place_rest(
        default_ink,"1",voices,"quarter",10.0,same_voice)
    if not same["placed"] or same["shift"] != -1.0:
        failures += 1
    var impossible: Array = []
    for offset in offsets:
        impossible.append({"voice":"2","ink":Rect2(0,float(offset)*10,10,8)})
    var crowded: Dictionary = RestLanes.place_rest(
        default_ink,"1",voices,"quarter",10.0,impossible)
    if crowded["placed"]:
        failures += 1
    print("REST_LANE_LAYOUT_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
