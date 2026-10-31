extends SceneTree

var failures: Array[String] = []
var keyboard: Control
var folder := ""
var rendered := false

func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        print("FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func target(pitch: int, label: String = "", hand: String = "right") -> Dictionary:
    return {"id": "note-%d" % pitch, "pitch": pitch, "label": label, "hand": hand}

func state(notes: Array, heard: Array = [], hint: bool = true) -> Dictionary:
    return {"expected_notes": notes, "heard_pitches": heard,
        "hint_visible": hint, "hint_reason": "wrong_note"}

func settle() -> void:
    await process_frame
    await process_frame

func fit_window(width: int, height: int) -> void:
    # The project starts fullscreen. X11 can deliver its old fullscreen
    # geometry after the first windowed resize request. Wait for actual,
    # stable viewport dimensions rather than assuming a fixed OS delay.
    var requested := Vector2i(width,height)
    var deadline: int = Time.get_ticks_msec()+2000
    var stable := 0
    while Time.get_ticks_msec() < deadline and stable < 3:
        if root.size != requested:
            root.size = requested
        await create_timer(.025).timeout
        stable = stable+1 if root.get_visible_rect().size == Vector2(width,height) else 0
    check(root.get_visible_rect().size == Vector2(width, height),
        "capture uses the requested %d by %d actual viewport (observed %s)" % [width, height,root.get_visible_rect().size])
    if is_instance_valid(keyboard):
        keyboard.position = Vector2(24, root.get_visible_rect().size.y - keyboard.size.y - 24)

func pixels(name: String) -> Image:
    await settle()
    RenderingServer.force_draw()
    var image := root.get_texture().get_image()
    image.save_png(folder.path_join(name + ".png"))
    return image

func color_distance(a: Color, b: Color) -> float:
    return Vector3(a.r - b.r, a.g - b.g, a.b - b.b).length()

func run() -> void:
    folder = OS.get_cmdline_user_args()[0]
    rendered = OS.get_cmdline_user_args()[1] == "rendered"
    var script = load("res://hint_keyboard.gd")
    check(script != null, "HintKeyboard is an actual loadable Godot control")
    if script == null:
        print("HINT_KEYBOARD_FAILURES:", failures.size())
        quit(1)
        return
    root.mode = Window.MODE_WINDOWED
    RenderingServer.set_default_clear_color(Color("#1E3A34"))
    await fit_window(800, 600)
    keyboard = script.new()
    keyboard.position = Vector2(24, root.get_visible_rect().size.y - 124)
    keyboard.size = Vector2(752, 100)
    root.add_child(keyboard)
    await settle()
    check(not keyboard.visible, "keyboard stays hidden before a requested hint")
    keyboard.update_state(state([target(60)], [], false))
    check(not keyboard.visible, "successful unhinted input does not reveal a keyboard")
    keyboard.update_state(state([target(60, "C4"), target(64, "E4"), target(67, "G4")], [61, 60]))
    await settle()
    check(keyboard.visible, "wrong-note hint reveals the current target")
    check(keyboard.mouse_filter == Control.MOUSE_FILTER_IGNORE, "piano diagram cannot submit answers")
    check(keyboard.focus_mode == Control.FOCUS_NONE, "piano diagram does not steal keyboard focus")
    check(keyboard.custom_minimum_size.y <= 100, "hint preserves notation height")
    check(keyboard._expected_label.text.contains("C4") and keyboard._expected_label.text.contains("E4")
        and keyboard._expected_label.text.contains("G4"), "all exact expected pitches remain named")
    check(keyboard._heard_label.text.contains("C#4") and keyboard._heard_label.text.contains("C4"),
        "heard names include actual MIDI pitches, not expected guesses")
    var keys: Dictionary = keyboard._keys
    check(keys.has(60) and keys.has(61) and keys.has(64), "context contains expected and nearby heard keys")
    if keys.has(60) and keys.has(61) and keys.has(62):
        var c: Rect2 = keys[60].rect
        var sharp: Rect2 = keys[61].rect
        var d: Rect2 = keys[62].rect
        check(c.position.x < sharp.position.x and sharp.position.x < d.position.x,
            "C sharp lies between C and D")
        check(sharp.size.y < c.size.y and sharp.size.x < c.size.x, "black keys have piano geometry")
        check(bool(keys[60].expected) and bool(keys[60].heard), "correctly heard expected key retains both states")
        check(not bool(keys[61].expected) and bool(keys[61].heard), "wrong heard key never becomes expected")
        check(not bool(keys[62].expected) and not bool(keys[62].heard), "unplayed key remains neutral")
    for segment in keyboard._registers:
        check(int(segment.high) - int(segment.low) <= 26, "ordinary hint range stays near two octaves")
    if rendered:
        var image: Image = await pixels("keyboard-800-chord")
        check(image.get_height() >= keyboard.position.y + keyboard.size.y,
            "actual viewport retains the entire keyboard including note labels")
        var c_rect: Rect2 = keys[60].rect
        var wrong_rect: Rect2 = keys[61].rect
        var neutral_rect: Rect2 = keys[62].rect
        var sample_y: float = c_rect.position.y + c_rect.size.y * .8
        var expected_pixel := image.get_pixelv(Vector2i(keyboard.position + Vector2(c_rect.get_center().x, sample_y)))
        var neutral_pixel := image.get_pixelv(Vector2i(keyboard.position + Vector2(neutral_rect.get_center().x, sample_y)))
        var wrong_pixel := image.get_pixelv(Vector2i(keyboard.position + wrong_rect.get_center()))
        check(color_distance(expected_pixel, neutral_pixel) > .08, "rendered target keys have a visible fill")
        check(color_distance(wrong_pixel, expected_pixel) > .08, "heard wrong key is visually distinct from expected")
        check(maxf(neutral_pixel.r, maxf(neutral_pixel.g, neutral_pixel.b)) < .72,
            "natural keys remain low glare on actual viewport pixels")
        var triangle_at := keyboard.position + Vector2(c_rect.get_center().x, c_rect.end.y - 22)
        var heard_at := keyboard.position + Vector2(c_rect.end.x - 6, c_rect.end.y - 14)
        check(color_distance(image.get_pixelv(Vector2i(triangle_at)), Color("#C8AC7C")) < .1,
            "rendered target has a triangular amber marker")
        check(color_distance(image.get_pixelv(Vector2i(heard_at)), load("res://practice_theme.gd").SLATE) < .1,
            "rendered correct pitch keeps its separate round heard marker")
    # Every black key must lie between its natural neighbours, including octave boundaries.
    for pitch in range(22, 108):
        keyboard.update_state(state([target(pitch)]))
        await settle()
        var current: Dictionary = keyboard._keys
        check(current.has(pitch), "current target pitch %d is visible" % pitch)
        if pitch % 12 in [1, 3, 6, 8, 10] and current.has(pitch - 1) and current.has(pitch + 1):
            check(current[pitch - 1].rect.get_center().x < current[pitch].rect.get_center().x
                and current[pitch].rect.get_center().x < current[pitch + 1].rect.get_center().x,
                "black key %d maps between the correct naturals" % pitch)
    # The two hands may span the full physical piano. Show both registers, never tiny 88-key trivia.
    for width in [752, 976, 1488]:
        keyboard.size = Vector2(width, 88 if width < 800 else 100)
        await fit_window(width + 48, 600 if width < 800 else (768 if width < 1200 else 960))
        keyboard.update_state(state([target(21, "A0", "left"), target(24, "C1", "left"),
            target(105, "A7"), target(108, "C8")], [60]))
        await settle()
        check(keyboard._registers.size() == 2, "wide hands get two separate contextual registers")
        for pitch in [21, 24, 105, 108]:
            check(keyboard._keys.has(pitch), "wide target %d survives at width %d" % [pitch, width])
        for key in keyboard._keys.values():
            var rect: Rect2 = key.rect
            check(rect.position.x >= 0 and rect.end.x <= width + .1, "wide keyboard stays inside its allocated width")
            if not bool(key.black):
                check(rect.size.x >= 22, "natural keys remain readable at width %d" % width)
        check(keyboard._heard_label.text.contains("C4"), "off-register heard pitch remains explicitly named")
        if rendered:
            var image: Image = await pixels("keyboard-%d-wide-hands" % (width + 48))
            check(image.get_width() >= keyboard.position.x + keyboard.size.x
                and image.get_height() >= keyboard.position.y + keyboard.size.y,
                "all rendered registers fit the actual viewport at width %d" % (width + 48))
    # MIDI note numbers cannot choose enharmonic labels. The actual score
    # signature must determine the physical key caption.
    keyboard.set_key_fifths(-4)
    check(keyboard._pitch_name(56) == "Ab3",
        "four flats label MIDI pitch 56 A-flat, not G-sharp")
    check(keyboard._pitch_name(58) == "Bb3",
        "four flats label MIDI pitch 58 B-flat")
    keyboard.set_key_fifths(-7)
    check(keyboard._pitch_name(59) == "Cb4",
        "seven flats preserve C-flat instead of B-natural")
    keyboard.set_key_fifths(0)
    check(keyboard._pitch_name(56) == "G#3",
        "without a key signature the chromatic label falls back to sharps")
    keyboard.update_state(state([], [60]))
    check(not keyboard.visible, "no target hides a stale hint immediately")
    var complete := state([target(60)])
    complete.completed = true
    keyboard.update_state(complete)
    check(not keyboard.visible, "completed guidance cannot leak a stale keyboard")
    complete.erase("completed")
    complete.phase = "guided_complete"
    keyboard.update_state(complete)
    check(not keyboard.visible, "guided-complete phase suppresses stale hints")
    keyboard.update_state(state([target(60)], [], false))
    check(not keyboard.visible, "successful next target hides the previous wrong-note hint")
    print("HINT_KEYBOARD_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
