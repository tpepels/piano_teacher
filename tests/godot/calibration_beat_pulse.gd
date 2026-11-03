extends SceneTree

const Pulse := preload("res://calibration_beat_pulse.gd")

func _initialize() -> void:
    var pulse := Pulse.new()
    root.add_child(pulse)
    var failures := 0
    if pulse.visible:
        failures += 1
    pulse.present_beat(0.0, true, 8, 4)
    if not pulse.visible or not pulse.is_preparing():
        failures += 1
    pulse.present_beat(3.99, true, 8, 4)
    if not pulse.is_preparing():
        failures += 1
    pulse.present_beat(4.0, true, 8, 4)
    if pulse.is_preparing():
        failures += 1
    # At every subsequent round boundary, preparation must never return.
    for round_index in range(1, 5):
        pulse.present_beat(4.0 + float(round_index * 8), true, 8, 4)
        if pulse.is_preparing() or pulse.round_beats != 8:
            failures += 1
    pulse.present_beat(-1.0, false)
    if pulse.visible:
        failures += 1
    print("CALIBRATION_PULSE_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
