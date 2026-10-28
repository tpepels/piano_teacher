extends SceneTree

const VoiceLayout := preload("res://notation/native/voice_layout.gd")

func _note(id: String, voice: String, kind: String, beat: float = 0.0) -> Dictionary:
    return {"id":id, "kind":"note", "staff":"right", "measure":1,
        "beat":beat, "voice":voice, "note_type":kind}

func _initialize() -> void:
    var failures := 0
    var upper := _note("upper", "1", "quarter")
    var lower := _note("lower", "2", "quarter")
    var events := [upper, lower]
    var y := {"upper":0.0, "lower":12.0}
    var directions: Dictionary = VoiceLayout.stem_directions(events, {}, y)
    if directions.get("upper") != true or directions.get("lower") != false:
        failures += 1
    var same_pitch: Dictionary = {"upper":0.0, "lower":0.0}
    directions = VoiceLayout.stem_directions(events, {}, same_pitch)
    if directions.get("upper") != true or directions.get("lower") != false:
        failures += 1
    var bounds := {"head_black":[-125, -62, 250, 124],
        "head_half":[-125, -62, 250, 124]}
    # Equal filled unisons with opposing stems can share their authentic head.
    var shared := VoiceLayout.column_offsets(events, {},
        {"upper":true, "lower":false}, bounds, {}, same_pitch, 20.0)
    if absf(float(shared.get("upper",99))) > .001 or absf(float(shared.get("lower",99))) > .001:
        failures += 1
    var filled := _note("filled", "1", "quarter")
    var hollow := _note("hollow", "2", "half")
    var split := VoiceLayout.column_offsets([filled,hollow], {},
        {"filled":true, "hollow":false}, bounds, {},
        {"filled":0.0, "hollow":0.0}, 20.0)
    if not (split.has("filled") and split.has("hollow") and
            absf(float(split["filled"])-float(split["hollow"])) > 10.0):
        failures += 1
    # An unrelated onset cannot inherit another voice's column translation.
    var separate := _note("later","1","quarter",2.0)
    var extra := VoiceLayout.column_offsets([filled,hollow,separate], {},
        {"filled":true, "hollow":false, "later":true}, bounds, {},
        {"filled":0.0, "hollow":0.0, "later":0.0}, 20.0)
    if absf(float(extra.get("later",0.0))) > .001:
        failures += 1
    print("VOICE_LAYOUT_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
