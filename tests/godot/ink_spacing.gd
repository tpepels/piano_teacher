extends SceneTree

const InkSpacing := preload("res://notation/native/ink_spacing.gd")

func _initialize() -> void:
    var failures := 0
    var same_register: Array = [
        {"staff":"right","beat":0.0,"ink":Rect2(0,0,20,8),
            "event":{"id":"a","kind":"note","note_type":"quarter"}},
        {"staff":"right","beat":0.25,"ink":Rect2(0,0,20,8),
            "event":{"id":"b","kind":"note","note_type":"16th"}},
    ]
    var before: Array = same_register.duplicate(true)
    var crowded: Dictionary = InkSpacing.minimum_density(same_register,24.0,10.0)
    if absf(float(crowded["density"])-88.0) > .0001:
        failures += 1
    if crowded["witness"].get("previous_id") != "a" or \
            crowded["witness"].get("next_id") != "b":
        failures += 1
    if same_register != before:
        failures += 1

    var separated: Array = same_register.duplicate(true)
    separated[1]["ink"] = Rect2(0,20,20,8)
    var no_collision: Dictionary = InkSpacing.minimum_density(separated,24.0,10.0)
    if absf(float(no_collision["density"])-24.0) > .0001 or \
            no_collision["witness"].get("reason") != "configured-density":
        failures += 1

    var different_staff: Array = same_register.duplicate(true)
    different_staff[1]["staff"] = "left"
    if absf(float(InkSpacing.minimum_density(different_staff,24.0,10.0)["density"])-24.0) > .0001:
        failures += 1

    var same_onset: Array = same_register.duplicate(true)
    same_onset[1]["beat"] = 0.0
    if absf(float(InkSpacing.minimum_density(same_onset,24.0,10.0)["density"])-24.0) > .0001:
        failures += 1

    print("INK_SPACING_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
