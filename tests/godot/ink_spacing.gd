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

    # More legible outgoing barline clearance for rapid MIDI rhythms.
    # The stem/flag contour is left intact; spacing is global.
    var outgoing: Array = [{"staff":"right","beat":1.75,
        "ink":Rect2(-10,0,30,8),"event":{"id":"flag"}}]
    var boundaries: Array = [{"beat":2.0,"ink":Rect2(-14,0,1,20)}]
    var constrained: Dictionary = InkSpacing.minimum_density(outgoing,96.0,10.0,boundaries)
    if absf(float(constrained["density"])-178.0) > .0001 or \
            constrained["witness"].get("reason") != "outgoing-barline-clearance":
        failures += 1
    var paired: Array = boundaries.duplicate(true)
    paired.append({"beat":2.0,"ink":Rect2(-18,0,2,20)})
    if InkSpacing.minimum_density(outgoing,96.0,10.0,paired)["density"] != 194.0:
        failures += 1
    # A sufficiently early note stays at the ordinary fixed scale.
    outgoing[0]["beat"] = 1.5
    if InkSpacing.minimum_density(outgoing,96.0,10.0,boundaries)["density"] != 96.0:
        failures += 1
    # Exact incoming clocks are not a density-solvable collision. Do not
    # divide by zero or reject a valid score for a same-clock accidental.
    outgoing[0]["beat"] = 2.0
    if InkSpacing.minimum_density(outgoing,96.0,10.0,boundaries)["density"] != 96.0:
        failures += 1
    # Finite actual contour bands, not a sprite's enclosing empty rectangle.
    outgoing[0]["beat"] = 1.75
    outgoing[0]["boundary_ink"] = [Rect2(-10,30,30,8)]
    if InkSpacing.minimum_density(outgoing,96.0,10.0,boundaries)["density"] != 96.0:
        failures += 1
    outgoing[0]["boundary_ink"] = [] # Intentional connector ink supplies no glyph constraint.
    if InkSpacing.minimum_density(outgoing,96.0,10.0,boundaries)["density"] != 96.0:
        failures += 1

    # Repeated quick MIDI attacks need more air even without literal ink
    # collision; a single grace/rolled attack must not stretch everything.
    var sixteenths: Array = [
        {"onset_beats":0.0}, {"onset_beats":0.25},
        {"onset_beats":0.5}, {"onset_beats":0.75}]
    if absf(InkSpacing.readable_density(sixteenths,96.0)-208.0) > .001:
        failures += 1
    var eighths: Array = [
        {"onset_beats":0.0}, {"onset_beats":0.5},
        {"onset_beats":1.0}, {"onset_beats":1.5}]
    if InkSpacing.readable_density(eighths,96.0) != 96.0:
        failures += 1
    var rolled: Array = [
        {"onset_beats":0.0}, {"onset_beats":0.15},
        {"onset_beats":1.0}, {"onset_beats":2.0}]
    if InkSpacing.readable_density(rolled,96.0) != 96.0:
        failures += 1
    var thirty_seconds: Array = [
        {"onset_beats":0.0}, {"onset_beats":0.125},
        {"onset_beats":0.25}, {"onset_beats":0.375}]
    if absf(InkSpacing.readable_density(thirty_seconds,96.0)-416.0) > .001:
        failures += 1
    # Chord heads on the same beat are still one onset.
    sixteenths.append({"onset_beats":0.5})
    if absf(InkSpacing.readable_density(sixteenths,96.0)-144.0) > .001:
        failures += 1

    # The first attack after a barline also needs room for its actual ink.
    var after_barline: Array = [{"staff":"right","beat":2.25,
        "ink":Rect2(-36,0,20,8),"event":{"id":"next16th"}}]
    var incoming := InkSpacing.minimum_density(after_barline,96.0,10.0,boundaries)
    if absf(float(incoming["density"])-128.0) > .0001 or \
            incoming["witness"].get("reason") != "incoming-barline-clearance":
        failures += 1
    print("INK_SPACING_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
