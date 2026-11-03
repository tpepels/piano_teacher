extends SceneTree
const Policy := preload("res://command_success_policy.gd")

func _initialize() -> void:
    var failures := 0
    var reset := Policy.decide("practice.command","reset_path",false)
    if not reset["publish_state"] or not reset["invalidate_lesson"] or \
            reset["navigate_practice"] or reset["refresh_settings"]:
        failures += 1
    var calibration := Policy.decide("practice.command","calibration_apply",false)
    if not calibration["refresh_settings"] or calibration["refresh_library"]:
        failures += 1
    var guided := Policy.decide("practice.command","revisit_trouble",false)
    if not guided["navigate_practice"] or not guided["publish_state"]:
        failures += 1
    var picker := Policy.decide("library.open","",false,{"warmup":false})
    if picker["open_mode"]!="picker" or picker["publish_state"] or \
            picker["navigate_practice"]:
        failures += 1
    var warmup := Policy.decide("library.open","",false,{"warmup":true})
    if warmup["open_mode"]!="practice" or not warmup["navigate_practice"] or \
            warmup["publish_state"]:
        failures += 1
    var restored := Policy.decide("library.open","",true,{"warmup":false})
    if restored["open_mode"]!="practice" or not restored["publish_state"]:
        failures += 1
    var invalid := Policy.decide("library.open","",false,"invalid payload")
    if invalid["open_mode"]!="none":
        failures += 1
    var settings := Policy.decide("settings.update","",false)
    if not settings["refresh_settings"] or not settings["refresh_library"]:
        failures += 1
    var device := Policy.decide("midi.device.select","",false)
    if not device["refresh_settings"] or device["refresh_library"]:
        failures += 1
    var health := Policy.decide("library.health.start","",false)
    if health["kind"]!="library_health":
        failures += 1
    var fingering := Policy.decide("fingering.correct","",false)
    if not fingering["publish_state"]:
        failures += 1
    print("COMMAND_SUCCESS_POLICY_FAILURES:",failures)
    quit(0 if failures==0 else 1)
