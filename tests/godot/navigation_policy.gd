extends SceneTree
const Policy := preload("res://navigation_policy.gd")

func _initialize() -> void:
    var failures := 0
    var idle = Policy.plan("settings","practice","ready",false,"","")
    if idle["pause"] or not idle["remember_settings"] or \
            idle["target"]!="settings":
        failures += 1
    var playing = Policy.plan("library","practice","playing",false,"","")
    if not playing["pause"]:
        failures += 1
    var starting = Policy.plan("library","practice","ready",
        true,"practice.command","start")
    if not starting["pause"]:
        failures += 1
    var pending_settings = Policy.plan("settings","settings","playing",
        true,"practice.command","pause")
    if pending_settings["pause"] or pending_settings["remember_settings"]:
        failures += 1
    var home = Policy.plan("home","practice","playing",false,"","")
    if home["target"]!="practice" or home["pause"]:
        failures += 1
    var returning = Policy.plan("practice","settings","ready",false,"","")
    if returning["pause"] or returning["remember_settings"]:
        failures += 1
    print("NAVIGATION_POLICY_FAILURES:",failures)
    quit(0 if failures==0 else 1)
