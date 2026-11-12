extends SceneTree
# The one exercise strategy (adaptive Coda + Fukuda) is piece-wide, not a per-passage trial.
var failures: Array[String] = []

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("CODA_PIECE_STRATEGY_FAIL:", message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var settings=load("res://settings_screen.gd").new()
    get_root().add_child(settings)
    await process_frame
    settings.present_preferences({
        "music_dir":"/tmp/music",
        "exercise_strategy":"coda-fukuda-midi",
        "available_exercise_strategies":[
            {"id":"coda-fukuda-midi","label":"Coda + Fukuda · MIDI combined lessons",
             "midi_only":true}
        ]
    })
    var selected: String=""
    if settings.strategy_picker.selected>=0:
        selected=str(settings.strategy_picker.get_item_metadata(
            settings.strategy_picker.selected))
    check(selected=="coda-fukuda-midi","The default Coda + Fukuda strategy is not selected")
    check(settings.strategy_picker.item_count==1,
          "The strategy picker must offer only the default")
    check(not ("timing_strategy_picker" in settings) and
          not ("tempo_strategy_picker" in settings),
          "The default generator owns rhythm and tempo stages; no separate pickers")
    var lesson=load("res://lesson_screen.gd").new()
    get_root().add_child(lesson)
    await process_frame
    check(lesson.find_child("CodaMidiTrial",true,false)==null,
          "Temporary passage-level trial control still exists")
    lesson.present_context({
        "loaded":true,"warmup":false,"mode":"practice",
        "phase":"ready","hands":["right","left","both"],"hand":"right"
    },false)
    check(lesson.mode_choice.item_count==4,
          "The existing teaching choices must remain intact")
    settings.free()
    lesson.free()
    print("CODA_PIECE_STRATEGY_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
