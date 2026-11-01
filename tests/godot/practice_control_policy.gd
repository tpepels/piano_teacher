extends SceneTree
const Policy := preload("res://practice_control_policy.gd")

func _initialize() -> void:
    var failures := 0
    var cases: Array = [
        [{},true,"",{"action":"start"}],
        [{},false,"",{"message":Policy.NOTATION_WAIT}],
        [{"running":true,"phase":"playing"},true,"",{"action":"pause"}],
        [{"paused":true,"phase":"paused"},true,"",{"action":"resume"}],
        [{"paused":true,"phase":"paused"},true,"notation failed",
            {"message":"notation failed"}],
        [{"mode":"listen"},false,"",{"action":"listen"}],
        [{"mode":"listen","warmup":true},false,"",{"action":"practice"}],
        [{"mode":"learn","phase":"ready"},false,"",
            {"message":Policy.NOTATION_WAIT}],
        [{"mode":"learn","phase":"ready"},true,"",{"action":"learn_retry"}],
        [{"mode":"learn","phase":"guided_wait"},false,"",{"action":"pause"}],
        [{"mode":"learn","phase":"loading"},false,"",{"action":"pause"}],
        [{"mode":"learn","phase":"paused","paused":true},false,"",{"action":"resume"}],
        [{"mode":"learn","phase":"guided_complete",
            "teaching":{"has_more_units":true}},true,"",{"action":"learn_next"}],
        [{"mode":"learn","phase":"guided_complete",
            "teaching":{"has_more_units":true},"guided_recovery":true},
            true,"",{"action":"practice"}],
        [{"mode":"learn","phase":"disconnected"},true,"",{"action":"practice"}],
    ]
    for entry in cases:
        var got: Dictionary = Policy.primary(entry[0],entry[1],entry[2])
        if got != entry[3]:
            failures += 1
            print("PRIMARY_MISMATCH:",entry,got)
    if Policy.pause_toggle({}, "") != {}:
        failures += 1
    if Policy.pause_toggle({"phase":"guided_wait","mode":"learn"},"") != {"action":"pause"}:
        failures += 1
    if Policy.pause_toggle({"paused":true,"phase":"paused"},"") != {"action":"resume"}:
        failures += 1
    if Policy.retry({},false) != {}:
        failures += 1
    if Policy.retry({"mode":"learn"},true) != {"action":"learn_retry"}:
        failures += 1
    if Policy.listen_toggle({"mode":"listen"}) != {
            "action":"practice","wait_for_player":true}:
        failures += 1
    if Policy.listen_toggle({}) != {"action":"listen"}:
        failures += 1
    print("PRACTICE_CONTROL_POLICY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
