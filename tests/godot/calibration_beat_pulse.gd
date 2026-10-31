extends SceneTree

const Pulse := preload("res://calibration_beat_pulse.gd")

func _initialize() -> void:
    var pulse := Pulse.new()
    root.add_child(pulse)
    var failures := 0
    if pulse.visible:
        failures += 1
    pulse.present_beat(0.0, true, 12, 4)
    if not pulse.visible or absf(pulse.beat) > .0001:
        failures += 1
    pulse.present_beat(4.25, true, 12, 4)
    if not pulse.visible or absf(pulse.beat-4.25) > .0001:
        failures += 1
    pulse.present_beat(12.0, true, 12, 4)
    if not pulse.visible or pulse.round_beats != 12:
        failures += 1
    pulse.present_beat(-1.0, false)
    if pulse.visible:
        failures += 1
    print("CALIBRATION_PULSE_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
