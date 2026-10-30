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
    # Three simultaneously sounding voices must not silently use
    # independent pitch-only stem defaults, especially at exact unisons.
    var triple := [
        _note("a","1","half"), _note("b","2","quarter"),
        _note("c","3","quarter")]
    var same_y := {"a":0.0, "b":0.0, "c":0.0}
    var triple_stems := VoiceLayout.stem_directions(triple, {}, same_y)
    if triple_stems.size() != 3 or not bool(triple_stems.get("a",false)) or \
            not bool(triple_stems.get("b",false)) or bool(triple_stems.get("c",true)):
        failures += 1
    var triple_columns := VoiceLayout.column_offsets(triple, {},
        triple_stems,bounds,{},same_y,20.0)
    if triple_columns.size() != 3:
        failures += 1
    else:
        # A hollow half cannot share a head with a filled quarter, and
        # the two equally directed quarter shafts need their own columns.
        if absf(float(triple_columns["a"])-float(triple_columns["b"])) <= 10.0 or \
                absf(float(triple_columns["b"])-float(triple_columns["c"])) <= 10.0:
            failures += 1
    # The upper voice can be the *third* source voice; source ordering
    # alone may not override a distinct actual register.
    var far_y := {"a":20.0,"b":10.0,"c":-10.0}
    var by_register := VoiceLayout.stem_directions(triple,{},far_y)
    if by_register.get("c") != true or by_register.get("b") != true or \
            by_register.get("a") != false:
        failures += 1
    var child: Dictionary = _note("d","1","half")
    child["chord"] = true
    var chord_stems := VoiceLayout.stem_directions(
        [triple[0], child, triple[1], triple[2]],
        {"a":[triple[0],child]}, {"a":0.0,"d":-8.0,"b":0.0,"c":0.0})
    if chord_stems.get("a") != chord_stems.get("d"):
        failures += 1
    # Only simultaneous events share this decision; later notes stay
    # source-owned even when they happen to use the same voice identifier.
    var later_source := _note("later-triple","2","quarter",2.0)
    var unaffected := VoiceLayout.stem_directions(
        [triple[0],triple[1],triple[2],later_source],{},
        {"a":0.0,"b":0.0,"c":0.0,"later-triple":0.0})
    if unaffected.has("later-triple"):
        failures += 1
    print("VOICE_LAYOUT_FAILURES:", failures)
    quit(0 if failures == 0 else 1)
