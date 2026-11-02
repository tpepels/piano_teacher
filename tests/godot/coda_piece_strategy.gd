extends SceneTree
# Coda is a piece-wide lesson strategy in Settings, not a per-passage trial.
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
        "exercise_strategy":"coda-midi",
        "available_exercise_strategies":[
            {"id":"legacy","label":"Original progression"},
            {"id":"coda-midi","label":"Coda · MIDI whole-piece lessons"}
        ],
        "timing_strategy":"original-timing",
        "available_timing_strategies":[
            {"id":"original-timing","label":"Original rhythm"}
        ],
        "tempo_strategy":"constant-tempo",
        "available_tempo_strategies":[
            {"id":"constant-tempo","label":"Constant tempo"}
        ]
    })
    var selected: String=""
    if settings.strategy_picker.selected>=0:
        selected=str(settings.strategy_picker.get_item_metadata(
            settings.strategy_picker.selected))
    check(selected=="coda-midi","Coda piece strategy is not selected")
    check(settings.timing_strategy_picker.disabled,
          "Piece-selected Coda must own generated rhythms")
    check(settings.tempo_strategy_picker.disabled,
          "Piece-selected Coda must own generated tempo stages")
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
