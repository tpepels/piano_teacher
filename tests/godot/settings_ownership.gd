extends SceneTree
const SettingsScreen := preload("res://settings_screen.gd")
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, message: String) -> void:
    if not ok:
        failures.append(message)
        print("SETTINGS_OWNERSHIP_FAIL:",message)

func button(view: Node, caption: String) -> Button:
    for node in view.find_children("*","Button",true,false):
        if node.text == caption:
            return node
    return null

func preferences(view: Control) -> void:
    var echoes: Array = []
    view.metronome_requested.connect(func(enabled: bool): echoes.append(enabled))
    view.fullscreen_requested.connect(func(enabled: bool): echoes.append(enabled))
    view.volume_changed.connect(func(db: float): echoes.append(db))
    view.strategy_requested.connect(func(id: String): echoes.append(id))
    view.present_preferences({
        "music_dir":"/scores", "fullscreen":false, "metronome":false,
        "exercise_strategy":"fukuda",
        "available_exercise_strategies":[
            {"id":"legacy", "label":"Original progression"},
            {"id":"fukuda", "label":"Fukuda"}
        ]})
    check(view.strategy_picker.item_count == 2
        and view.strategy_picker.selected == 1,
        "Backend strategy options and current selection are presented")
    view.strategy_picker.item_selected.emit(0)
    check(echoes == ["legacy"], "Changing the picker emits the selected strategy identifier")
    echoes.clear()
    view.present_volume(-3.0)
    check(view.folder_edit.text == "/scores" and not view.fullscreen_toggle.button_pressed
        and not view.metronome_toggle.button_pressed, "Preference snapshots present their values")
    check(view.listen_volume_slider.value == -3.0 and view.listen_volume_label.text == "-3 dB",
        "Listen gain and its caption have one view owner")
    check(echoes.is_empty(), "Presenting server/local values never sends settings commands")
    view.present_message("Settings saved")
    check(view.settings_message.text == "Settings saved", "Save/error messages stay in the screen")
    view.present_window_mode(true)
    check(view.fullscreen_toggle.button_pressed and echoes.is_empty(), "F11 presentation does not recursively save preferences")

func tempo_draft(view: Control) -> void:
    var state := {"loaded":true,"target_bpm":80,"bpm":64,"minimum_bpm":20,
        "maximum_bpm":240,"device":"Piano","midi_input_age":.1,"midi_input_note":60,"midi_input_count":4}
    view.begin_editing(state)
    view.present_practice(state,true)
    view.tempo_setting.value = 113
    state.target_bpm = 90
    view.present_practice(state,true)
    check(view.tempo_setting.value == 113, "State polling preserves the draft while Settings is open")
    check(view.tempo_setting.min_value == 20 and view.tempo_setting.max_value == 240,
        "Backend tempo limits still constrain the draft")
    check(view.input_activity_label.text.contains("MIDI note 60") and view.input_activity_label.text.contains("4 notes"),
        "Input diagnostics present authoritative MIDI values")
    view.present_busy(true)
    check(view.apply_tempo_button.disabled, "A pending command prevents dropping another tempo click")
    view.present_busy(false)
    check(not view.apply_tempo_button.disabled, "Acknowledgement makes tempo editable again")
    view.present_practice(state,false)
    check(view.tempo_setting.value == 90, "Leaving Settings resumes target-tempo presentation")
    state.device = ""
    state.midi_input_age = null
    view.present_practice(state,false)
    check(view.input_activity_label.text.contains("Connect your MIDI piano"), "Disconnected input diagnostics remain useful")

func signals(view: Control) -> void:
    var received: Array = []
    view.save_folder_requested.connect(func(path: String): received.append(["folder",path]))
    view.tempo_requested.connect(func(bpm: int): received.append(["tempo",bpm]))
    view.metronome_requested.connect(func(enabled: bool): received.append(["metronome",enabled]))
    view.volume_changed.connect(func(db: float): received.append(["volume",db]))
    view.fullscreen_requested.connect(func(enabled: bool): received.append(["fullscreen",enabled]))
    view.folder_edit.text = "  /music/learner  "
    button(view,"Save folder").pressed.emit()
    view.folder_edit.text_submitted.emit(view.folder_edit.text)
    view.tempo_setting.value = 112
    view.apply_tempo_button.pressed.emit()
    view.metronome_toggle.toggled.emit(false)
    view.listen_volume_slider.value = 9
    view.fullscreen_toggle.toggled.emit(false)
    check(received == [["folder","/music/learner"],["folder","/music/learner"],
        ["tempo",112],["metronome",false],["volume",9.0],["fullscreen",false]],
        "Settings emits explicit user values instead of exposing widgets to its parent")
    check(view.listen_volume_label.text == "+9 dB", "Local gain changes update their own caption")

func pickers(view: Control) -> void:
    var chosen: Array = []
    view.device_selected.connect(func(name: String): chosen.append(name))
    view.save_folder_requested.connect(func(path: String): chosen.append(path))
    var devices := ["Piano A","Piano B"]
    view.present_devices(devices,"Piano A")
    devices[1] = "Replaced caller value"
    view.device_menu.id_pressed.emit(1)
    view.device_menu.id_pressed.emit(-2)
    view.device_menu.id_pressed.emit(999)
    view.folder_dialog.dir_selected.emit("/chosen")
    check(chosen == ["Piano B","","/chosen"], "Local pickers emit captured device names and actual selected paths")
    check(view.folder_edit.text == "/chosen", "Choosing a folder updates the owned draft before saving")
    check(view.device_button.text == "Piano A", "Device caption reflects the authoritative connected device")
    view.present_device_selection("Piano B")
    check(view.device_button.text == "Piano B  ✓", "An explicit selection shows the existing acknowledgement caption")
    view.present_devices([],"")
    check(view.device_menu.get_item_id(0) == -2 and view.device_button.text == "Choose USB MIDI piano",
        "No MIDI input remains an explicit timing-preview choice")

func layout(view: Control) -> void:
    for dimensions in [Vector2i(800,600),Vector2i(1024,768),Vector2i(1280,800),Vector2i(1536,960)]:
        root.size = dimensions
        view.apply_viewport(Vector2(dimensions),1.0)
        for frame in range(6):
            await process_frame
        check(view.settings_grid.columns == (2 if dimensions.x >= 1100 else 1), "Settings owns its existing grid breakpoint")
        for field in [view.folder_edit,view.device_button,view.tempo_setting,view.listen_volume_slider]:
            var rect: Rect2 = field.get_global_rect()
            check(rect.position.x >= -1 and rect.end.x <= dimensions.x+1,
                "Settings fields fit their current viewport: " + str(dimensions))
    check(view.folder_controls is VBoxContainer, "Folder actions remain below the path on compact screens")

func run() -> void:
    root.mode = Window.MODE_WINDOWED
    root.size = Vector2i(800,600)
    var view := SettingsScreen.new()
    view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root.add_child(view)
    await process_frame
    var scenario := OS.get_cmdline_user_args()[0]
    var needed := {"preferences":"present_preferences","tempo_draft":"present_practice",
        "signals":"present_volume","pickers":"present_devices","layout":"apply_viewport"}
    check(view.has_method(needed[scenario]), "Independent Settings presentation contract is not implemented: " + scenario)
    if view.has_method(needed[scenario]):
        match scenario:
            "preferences": preferences(view)
            "tempo_draft": tempo_draft(view)
            "signals": signals(view)
            "pickers": pickers(view)
            "layout": await layout(view)
    view.free()
    print("SETTINGS_OWNERSHIP_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
