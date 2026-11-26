extends SceneTree
# Run with: godot --headless --path godot --script res://tests/test_transient_pitch_spelling.gd
const Geometry := preload("res://notation/native/geometry.gd")

func _initialize() -> void:
    var cases := [
        [66,-6,"G",-1,4,""], [67,-6,"G",0,4,"acc_natural"],
        [65,1,"F",0,4,"acc_natural"], [66,1,"F",1,4,""],
        [60,7,"B",1,3,""], [59,-6,"C",-1,4,""],
        [60,0,"C",0,4,""], [61,0,"C",1,4,"acc_sharp"],
    ]
    for example in cases:
        var spelling: Dictionary = Geometry.key_signature_spelling(example[0],example[1])
        if [spelling.get("step"),spelling.get("alter"),spelling.get("octave"),spelling.get("accidental")] != example.slice(2):
            push_error("Key spelling mismatch: "+str(example)+" got "+str(spelling))
            quit(1)
            return
    var naturals := {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
    for fifths in range(-7,8):
        for pitch in range(128):
            var spelling: Dictionary = Geometry.key_signature_spelling(pitch,fifths)
            if spelling.is_empty() or (int(spelling["octave"])+1)*12+int(naturals[spelling["step"]])+int(spelling["alter"]) != pitch:
                push_error("Pitch reconstruction failed: "+str([pitch,fifths,spelling]))
                quit(1)
                return
    print("Transient pitch spelling passed")
    quit(0)
