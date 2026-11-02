extends SceneTree
# Phase 4 must expose the exact MIDI-only strategy in the native UI.
# This does NOT pretend a headless script tested a physical MIDI keyboard.
var failures: Array[String] = []

func check(ok: bool, why: String) -> void:
    if not ok:
        failures.append(why)
        print("FUKUDA_MIDI_GODOT_FAIL:", why)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var settings = load("res://settings_screen.gd").new()
    get_root().add_child(settings)
    await process_frame
    settings.present_preferences({
        "music_dir": "/tmp/music",
        "exercise_strategy": "fukuda-midi",
        "available_exercise_strategies": [
            {"id": "legacy", "label": "Original progression"},
            {"id": "fukuda-midi", "label": "Fukuda · MIDI adaptive simplification"},
            {"id": "coda-midi", "label": "Coda · MIDI whole-piece lessons"}
        ],
        "timing_strategy": "original-timing",
        "available_timing_strategies": [
            {"id": "original-timing", "label": "Original rhythm"}
        ],
        "tempo_strategy": "constant-tempo",
        "available_tempo_strategies": [
            {"id": "constant-tempo", "label": "Constant tempo"}
        ]
    })
    var value: String = ""
    if settings.strategy_picker.selected >= 0:
        value = str(settings.strategy_picker.get_item_metadata(settings.strategy_picker.selected))
    check(value == "fukuda-midi", "MIDI Fukuda strategy not selected")
    check(not settings.timing_strategy_picker.disabled,
          "Fukuda should not lock the ordinary rhythm controls")
    check(not settings.tempo_strategy_picker.disabled,
          "Fukuda should not lock the ordinary tempo controls")

    var lesson = load("res://lesson_screen.gd").new()
    get_root().add_child(lesson)
    await process_frame
    lesson.present_context({
        "loaded": true,
        "warmup": false,
        "mode": "practice",
        "phase": "ready",
        "hands": ["right", "left", "both"],
        "hand": "right",
        "lesson_level": "fukuda-midi-chord-outer",
        "lesson_steps": [
            {"exercise": 0, "hand": "right",
             "level": "fukuda-midi-chord-outer", "mastered": false},
            {"exercise": 0, "hand": "right",
             "level": "fukuda-midi-fast-thin", "mastered": false},
            {"exercise": 0, "hand": "right",
             "level": "fukuda-midi-return-leap", "mastered": false},
            {"exercise": 0, "hand": "right",
             "level": "original", "mastered": false}
        ]
    }, false)
    check(lesson.mode_choice.item_count == 4,
          "Practice/Listen/Perform controls changed")
    check(lesson.hand_buttons.has("right") and lesson.hand_buttons.has("both"),
          "Ordinary hand navigation missing")
    check(lesson.placement_button != null and lesson.skip_button != null,
          "Return-to-original/skip controls missing")
    settings.free()
    lesson.free()
    print("FUKUDA_MIDI_GODOT_FAILURES:", failures.size())
    quit(0 if failures.is_empty() else 1)
