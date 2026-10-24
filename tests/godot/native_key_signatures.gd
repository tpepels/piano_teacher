extends SceneTree

func _initialize() -> void:
    var geometry = load("res://notation/native/geometry.gd")
    var cases: Array = JSON.parse_string(FileAccess.get_file_as_string(OS.get_cmdline_user_args()[0]))
    var failures := 0
    for row in cases:
        var actual: Array = geometry.signature_steps(row["clef"],int(row["fifths"]))
        var expected: Array = []
        for value in row["steps"]:
            expected.append(int(value))
        if actual != expected:
            print("KEY_SIGNATURE_MISMATCH:",JSON.stringify(row)," observed=",actual)
            failures += 1
    print("NATIVE_KEY_FAILURES:",failures)
    quit(0 if failures == 0 else 1)
