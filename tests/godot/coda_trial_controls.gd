extends SceneTree
# Public Lesson screen exposes an explicit opt-in and source-restore action.
# The existing main.gd listener routes both actions to POST /control.
var failures: Array[String] = []
func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("CODA_TRIAL_CONTROLS_FAIL:",message)

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var screen=load("res://lesson_screen.gd").new()
    get_root().add_child(screen)
    await process_frame
    var commands: Array = []
    screen.command_requested.connect(func(value: Dictionary): commands.append(value))
    screen.present_context({
        "loaded":true,"warmup":false,"coda_available":true,
        "coda_trial":false,"piece_fingerprint":"midi-song","mode":"practice",
        "phase":"ready","hands":["right","both"],"hand":"right"
    },false)
    check(screen.coda_controls.visible,
        "MIDI source should expose experimental Coda choices")
    check(screen.coda_buttons.size()==3,
        "Coda must have three explicit timing transformations")
    check(not screen.coda_exit_button.visible,
        "Exit action is hidden before a trial starts")
    for button in screen.coda_buttons:
        check(not button.disabled,"An idle MIDI lesson must permit a Coda trial")
        button.pressed.emit()
    check(commands==[
        {"action":"coda_try","family":"tempo-shaping"},
        {"action":"coda_try","family":"dotted-rhythms"},
        {"action":"coda_try","family":"chordification"}
    ],"Every Coda button must send a concrete backend command")
    screen.present_context({
        "loaded":true,"warmup":false,"coda_available":true,
        "coda_trial":true,"coda_family":"tempo-shaping",
        "coda_source_bars":[2,3],"piece_fingerprint":"trial",
        "mode":"practice","phase":"ready","hands":["right"],"hand":"right"
    },false)
    check(screen.coda_exit_button.visible,
        "Trial must always expose return to original MIDI")
    screen.coda_exit_button.pressed.emit()
    check(commands.back()=={"action":"coda_exit"},
        "Exit must request the real backend source restoration")
    screen.present_busy(true)
    check(screen.coda_exit_button.disabled,
        "In-flight command must block a second trial switch")
    screen.present_context({"loaded":false},false)
    check(not screen.coda_controls.visible,
        "Coda choices must not appear without a loaded source")
    screen.free()
    print("CODA_TRIAL_CONTROLS_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
