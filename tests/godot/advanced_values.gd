extends SceneTree
func _initialize() -> void:
    var Geometry=load('res://notation/native/geometry.gd')
    var model={"notation_events":[{"id":"tiny","kind":"note","staff":"right",
        "note_type":"128th","dots":5,"duration_beats":.0615234375,
        "spelling":{"step":"C","octave":5}}],
        "measures":[{"clefs":{"right":{"sign":"C","line":4,"octave_change":2},
            "left":{"sign":"F","line":5,"octave_change":-2}},"keys":{}}]}
    var reason: String=Geometry.supported(model)
    if not reason.is_empty() or Geometry.beam_level('128th') != 5:
        push_error('ADVANCED_VALUES: '+reason)
        quit(1)
    else:
        print('ADVANCED_VALUES_PASS')
        quit(0)
