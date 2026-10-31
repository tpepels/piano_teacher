extends ScrollContainer
# Standalone settings view. It owns its controls and visual hierarchy;
# the application coordinates HTTP, MIDI and platform actions via signals.
const Design := preload("res://practice_theme.gd")
const ActionButton := preload("res://action_button.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const ACCENT := Design.TEAL

signal choose_devices_requested
signal refresh_devices_requested
signal save_folder_requested(path: String)
signal device_selected(name: String)
signal tempo_requested(bpm: int)
signal strategy_requested(strategy: String)
signal timing_strategy_requested(strategy: String)
signal tempo_strategy_requested(strategy: String)
signal diagnosis_strategy_requested(strategy: String)
signal learner_strategy_requested(strategy: String)
signal metronome_requested(enabled: bool)
signal calibration_requested(action: String)
signal volume_changed(db: float)
signal fullscreen_requested(enabled: bool)
signal exit_requested

var ui_scale := 1.0
var default_font: Font
var settings_grid: GridContainer
var device_button: Button
var input_activity_label: Label
var calibration_label: Label
var calibration_apply_button: Button
var folder_controls: VBoxContainer
var folder_edit: LineEdit
var tempo_setting: SpinBox
var apply_tempo_button: Button
var metronome_toggle: CheckButton
var strategy_picker: OptionButton
var timing_strategy_picker: OptionButton
var tempo_strategy_picker: OptionButton
var diagnosis_strategy_picker: OptionButton
var learner_strategy_picker: OptionButton
var listen_volume_slider: HSlider
var listen_volume_label: Label
var fullscreen_toggle: CheckButton
var settings_message: Label
var folder_dialog: FileDialog
var device_menu: PopupMenu
var _device_names: Array = []

func _ui_font(base: int) -> int:
    return maxi(14, int(round(float(base) * ui_scale)))

func _label(value: String, font_size: int, color: Color, bold := false) -> Label:
    var control := Label.new()
    control.text = value
    control.add_theme_color_override("font_color", color)
    control.set_meta("ui_font_base", font_size)
    control.add_theme_font_size_override("font_size", _ui_font(font_size))
    control.add_theme_font_override("font", Design.font(700 if bold else 400))
    control.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return control

func _title(value: String, font_size: int) -> Label:
    var control := _label(value, font_size, INK)
    control.add_theme_font_override("font", Design.title_font())
    return control

func _stack(separation: int) -> VBoxContainer:
    var control := VBoxContainer.new()
    control.add_theme_constant_override("separation", separation)
    return control

func _section(value: String) -> VBoxContainer:
    var control := _stack(12)
    control.add_child(_label(value, 17, INK, true))
    return control

func _card() -> PanelContainer:
    var control := PanelContainer.new()
    control.add_theme_stylebox_override("panel", Design.card_surface())
    return control

func _card_body(panel: PanelContainer, margin: int = 28) -> MarginContainer:
    var control := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        control.add_theme_constant_override("margin_" + side, margin)
    panel.add_child(control)
    return control

func _button(value: String, callback: Callable, primary := false,
        role: String = "") -> Button:
    var control := ActionButton.new()
    control.text = value
    control.clip_text = false
    control.set_meta("ui_font_base", 15)
    control.add_theme_font_size_override("font_size", _ui_font(15))
    control.configure(role if not role.is_empty() else "primary" if primary else "secondary")
    var font: Font = default_font if default_font != null else Design.font(400)
    var width: float = font.get_string_size(value,
        HORIZONTAL_ALIGNMENT_LEFT, -1, _ui_font(15)).x
    control.custom_minimum_size = Vector2(
        maxf(96.0, width + 48.0 * ui_scale), 38.0 * ui_scale)
    control.pressed.connect(callback)
    return control

func _ready() -> void:
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    var content := _stack(20)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(content)
    content.add_child(_label("PIANO & PREFERENCES", 14, ACCENT, true))
    content.add_child(_title("Your piano & practice", 32))

    settings_grid = GridContainer.new()
    settings_grid.columns = 1
    settings_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_grid.add_theme_constant_override("h_separation", 18)
    settings_grid.add_theme_constant_override("v_separation", 18)
    content.add_child(settings_grid)
    var midi_panel := _card()
    midi_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_grid.add_child(midi_panel)
    var midi := _section("MIDI input")
    _card_body(midi_panel, 18).add_child(midi)
    var device_row := HFlowContainer.new()
    device_row.add_theme_constant_override("h_separation", 10)
    midi.add_child(device_row)
    device_button = _button("Choose USB MIDI piano", func(): choose_devices_requested.emit(), false, "settings")
    device_row.add_child(device_button)
    device_row.add_child(_button("Refresh devices", func(): refresh_devices_requested.emit(), false, "utility"))
    input_activity_label = _label("Connect your piano, then play a note to check input.", 14, MUTED)
    midi.add_child(input_activity_label)
    var calibration_row := HFlowContainer.new()
    calibration_row.add_theme_constant_override("h_separation", 8)
    midi.add_child(calibration_row)
    calibration_row.add_child(_button("Calibrate MIDI timing", func():
        calibration_requested.emit("calibration_start"), false, "settings"))
    calibration_apply_button = _button("Apply offset", func():
        calibration_requested.emit("calibration_apply"), false, "settings")
    calibration_apply_button.disabled = true
    calibration_row.add_child(calibration_apply_button)
    calibration_row.add_child(_button("Reset offset", func():
        calibration_requested.emit("calibration_reset"), false, "utility"))
    calibration_row.add_child(_button("Cancel", func():
        calibration_requested.emit("calibration_cancel"), false, "utility"))
    calibration_label = _label("No correction · tap in time with 8 clicks to estimate MIDI timing offset.", 14, MUTED)
    midi.add_child(calibration_label)

    var music := _section("Music library")
    var music_panel := _card()
    music_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_grid.add_child(music_panel)
    _card_body(music_panel, 18).add_child(music)
    # A fixed vertical arrangement prevents Browse/Save from crowding the
    # folder path on narrower logical viewports and fullscreen displays.
    folder_controls = VBoxContainer.new()
    folder_controls.add_theme_constant_override("separation", 8)
    music.add_child(folder_controls)
    folder_edit = LineEdit.new()
    folder_edit.custom_minimum_size = Vector2(0, 40)
    folder_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    folder_edit.placeholder_text = "~/Music/Piano Teacher"
    folder_edit.text_submitted.connect(func(_text: String): save_folder_requested.emit(folder_edit.text.strip_edges()))
    folder_controls.add_child(folder_edit)
    var folder_actions := HFlowContainer.new()
    folder_actions.add_theme_constant_override("h_separation", 10)
    folder_actions.add_theme_constant_override("v_separation", 6)
    folder_controls.add_child(folder_actions)
    folder_actions.add_child(_button("Choose folder…", _browse_folder, false, "navigation"))
    folder_actions.add_child(_button("Save folder", func(): save_folder_requested.emit(folder_edit.text.strip_edges()), false, "secondary"))
    music.add_child(_label("MIDI and MusicXML files in this folder and its subfolders.", 13, MUTED))

    var practice := _section("Practice tempo")
    var practice_panel := _card()
    practice_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_grid.add_child(practice_panel)
    _card_body(practice_panel, 18).add_child(practice)
    var tempo_row := HBoxContainer.new()
    tempo_row.add_theme_constant_override("separation", 12)
    practice.add_child(tempo_row)
    var tempo_caption := _label("Target tempo", 14, MUTED)
    tempo_caption.autowrap_mode = TextServer.AUTOWRAP_OFF
    tempo_caption.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    tempo_caption.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    tempo_caption.custom_minimum_size.x = 0
    tempo_row.add_child(tempo_caption)
    tempo_setting = SpinBox.new()
    tempo_setting.min_value = 12
    tempo_setting.max_value = 300
    tempo_setting.step = 1
    tempo_setting.suffix = " BPM"
    tempo_setting.custom_minimum_size = Vector2(150, 40)
    tempo_row.add_child(tempo_setting)
    apply_tempo_button = _button("Apply tempo", func(): tempo_requested.emit(int(tempo_setting.value)), false, "settings")
    tempo_row.add_child(apply_tempo_button)
    metronome_toggle = CheckButton.new()
    metronome_toggle.text = "Metronome during practice"
    metronome_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    metronome_toggle.tooltip_text = "Count-in is always audible, even when metronome is off"
    metronome_toggle.toggled.connect(func(enabled: bool): metronome_requested.emit(enabled))
    practice.add_child(metronome_toggle)
    practice.add_child(_label("Exercise generation", 14, MUTED))
    strategy_picker = OptionButton.new()
    strategy_picker.custom_minimum_size = Vector2(260, 40)
    strategy_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    strategy_picker.tooltip_text = "Select which rule-based exercise planner to compare."
    strategy_picker.item_selected.connect(func(index: int):
        strategy_requested.emit(str(strategy_picker.get_item_metadata(index))))
    practice.add_child(strategy_picker)
    practice.add_child(_label("Rhythm exercise", 14, MUTED))
    timing_strategy_picker = OptionButton.new()
    timing_strategy_picker.custom_minimum_size = Vector2(260, 40)
    timing_strategy_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    timing_strategy_picker.item_selected.connect(func(index: int):
        timing_strategy_requested.emit(str(timing_strategy_picker.get_item_metadata(index))))
    practice.add_child(timing_strategy_picker)
    practice.add_child(_label("Tempo pattern", 14, MUTED))
    tempo_strategy_picker = OptionButton.new()
    tempo_strategy_picker.custom_minimum_size = Vector2(260, 40)
    tempo_strategy_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    tempo_strategy_picker.item_selected.connect(func(index: int):
        tempo_strategy_requested.emit(str(tempo_strategy_picker.get_item_metadata(index))))
    practice.add_child(tempo_strategy_picker)
    practice.add_child(_label("Error assessment", 14, MUTED))
    diagnosis_strategy_picker = OptionButton.new()
    diagnosis_strategy_picker.custom_minimum_size = Vector2(260, 40)
    diagnosis_strategy_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    diagnosis_strategy_picker.item_selected.connect(func(index: int):
        diagnosis_strategy_requested.emit(str(diagnosis_strategy_picker.get_item_metadata(index))))
    practice.add_child(diagnosis_strategy_picker)
    practice.add_child(_label("Learner recommendation", 14, MUTED))
    learner_strategy_picker = OptionButton.new()
    learner_strategy_picker.custom_minimum_size = Vector2(260, 40)
    learner_strategy_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    learner_strategy_picker.item_selected.connect(func(index: int):
        learner_strategy_requested.emit(str(learner_strategy_picker.get_item_metadata(index))))
    practice.add_child(learner_strategy_picker)
    practice.add_child(_label(
        "Exercise, rhythm and tempo changes restart practice. Assessment policy changes affect future recommendations only.",
        12, MUTED))

    var audio := _section("Listen audio")
    var audio_panel := _card()
    audio_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_grid.add_child(audio_panel)
    _card_body(audio_panel, 18).add_child(audio)
    var audio_row := HBoxContainer.new()
    audio_row.add_theme_constant_override("separation", 12)
    audio.add_child(audio_row)
    var volume_caption := _label("Piano volume", 14, MUTED)
    volume_caption.autowrap_mode = TextServer.AUTOWRAP_OFF
    volume_caption.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    volume_caption.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    volume_caption.custom_minimum_size.x = 0
    audio_row.add_child(volume_caption)
    listen_volume_slider = HSlider.new()
    listen_volume_slider.min_value = -12.0
    listen_volume_slider.max_value = 12.0
    listen_volume_slider.step = 1.0
    listen_volume_slider.value = 6.0
    listen_volume_slider.custom_minimum_size = Vector2(180, 36)
    listen_volume_slider.tooltip_text = "Listen only. Saved locally; does not change MIDI or metronome."
    audio_row.add_child(listen_volume_slider)
    listen_volume_label = _label("+6 dB", 14, INK)
    audio_row.add_child(listen_volume_label)
    listen_volume_slider.value_changed.connect(func(db: float):
        listen_volume_label.text = "%+d dB" % int(round(db))
        volume_changed.emit(db))
    fullscreen_toggle = CheckButton.new()
    fullscreen_toggle.text = "Fullscreen application  ·  F11"
    fullscreen_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    fullscreen_toggle.button_pressed = true
    fullscreen_toggle.toggled.connect(func(enabled: bool): fullscreen_requested.emit(enabled))
    audio.add_child(fullscreen_toggle)
    var exit_button := _button("Exit application", func(): exit_requested.emit(), false, "utility")
    exit_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    content.add_child(exit_button)
    settings_message = _label("", 14, MUTED)
    content.add_child(settings_message)
    folder_dialog = FileDialog.new()
    folder_dialog.access = FileDialog.ACCESS_FILESYSTEM
    folder_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
    folder_dialog.use_native_dialog = true
    folder_dialog.dir_selected.connect(func(path: String):
        folder_edit.text = path
        save_folder_requested.emit(path.strip_edges()))
    add_child(folder_dialog)
    device_menu = PopupMenu.new()
    device_menu.id_pressed.connect(_device_chosen)
    add_child(device_menu)

func present_calibration(state: Dictionary, offset_ms: int) -> void:
    if calibration_label == null:
        return
    var result: Variant = state.get("result")
    var status := "Applied MIDI offset: %d ms." % offset_ms
    if bool(state.get("active", false)):
        status += " Tap any key with the clicks · %d/%d captured." % [
            int(state.get("samples", 0)), int(state.get("ticks", 8))]
    elif result is Dictionary:
        var measurement: Dictionary = result
        if bool(measurement.get("reliable", false)):
            status += " Estimated tap delay: %d ms, variation: %d ms. Apply to compensate." % [
                int(measurement.get("estimate_ms", 0)), int(measurement.get("jitter_ms", 0))]
        else:
            status += " Inconsistent taps; retry calibration."
    calibration_label.text = status
    calibration_label.tooltip_text = "Tap timing includes human reaction and audio output delay, not only Bluetooth MIDI latency."
    calibration_apply_button.disabled = not (result is Dictionary and bool(result.get("reliable", false)))

func present_preferences(values: Dictionary) -> void:
    folder_edit.text = str(values.get("music_dir", ""))
    present_window_mode(bool(values.get("fullscreen", true)))
    metronome_toggle.set_pressed_no_signal(bool(values.get("metronome", true)))
    _present_strategy_picker(strategy_picker,
        values.get("available_exercise_strategies", []),
        str(values.get("exercise_strategy", "coda-part")))
    _present_strategy_picker(timing_strategy_picker,
        values.get("available_timing_strategies", []),
        str(values.get("timing_strategy", "original-timing")))
    _present_strategy_picker(tempo_strategy_picker,
        values.get("available_tempo_strategies", []),
        str(values.get("tempo_strategy", "constant-tempo")))
    _present_strategy_picker(diagnosis_strategy_picker,
        values.get("available_diagnosis_strategies", []),
        str(values.get("diagnosis_strategy", "error-family")))
    _present_strategy_picker(learner_strategy_picker,
        values.get("available_learner_strategies", []),
        str(values.get("learner_strategy", "repeated-error")))

func _present_strategy_picker(picker: OptionButton, choices: Array, selected: String) -> void:
    picker.clear()
    for available in choices:
        if typeof(available) != TYPE_DICTIONARY:
            continue
        var index := picker.item_count
        picker.add_item(str(available.get("label", available.get("id", ""))))
        var strategy_id := str(available.get("id", ""))
        picker.set_item_metadata(index, strategy_id)
        if strategy_id == selected:
            picker.select(index)

func begin_editing(state: Dictionary) -> void:
    tempo_setting.set_value_no_signal(float(state.get("target_bpm", 40)))

func present_practice(state: Dictionary, editing: bool = false) -> void:
    var age = state.get("midi_input_age")
    var recent: bool = age != null and float(age) < 1.5
    if recent:
        input_activity_label.text = "Input received · MIDI note %d · %d notes received" % [
            int(state.get("midi_input_note", 0)), int(state.get("midi_input_count", 0))]
    else:
        input_activity_label.text = "Play a note to check input." if not str(state.get("device", "")).is_empty() else "Connect your MIDI piano, then play a note to check input."
    var tone: Color = ACCENT if recent else MUTED
    if input_activity_label.get_theme_color("font_color") != tone:
        input_activity_label.add_theme_color_override("font_color", tone)
    if bool(state.get("loaded", false)):
        tempo_setting.min_value = float(state.get("minimum_bpm", 12))
        tempo_setting.max_value = float(state.get("maximum_bpm", 300))
        if not editing:
            tempo_setting.set_value_no_signal(float(state.get("target_bpm", state.get("bpm", 40))))

func present_busy(pending: bool) -> void:
    apply_tempo_button.disabled = pending
    strategy_picker.disabled = pending
    timing_strategy_picker.disabled = pending
    tempo_strategy_picker.disabled = pending
    diagnosis_strategy_picker.disabled = pending
    learner_strategy_picker.disabled = pending

func present_volume(db: float) -> void:
    listen_volume_slider.set_value_no_signal(db)
    listen_volume_label.text = "%+d dB" % int(round(db))

func present_window_mode(fullscreen: bool) -> void:
    fullscreen_toggle.set_pressed_no_signal(fullscreen)

func present_message(message: String) -> void:
    settings_message.text = message

func apply_viewport(view_size: Vector2, scale: float) -> void:
    ui_scale = scale
    settings_grid.columns = 2 if view_size.x >= 1100.0 else 1
    for control in find_children("*", "Control", true, false):
        if control.has_meta("ui_font_base"):
            control.add_theme_font_size_override("font_size", _ui_font(int(control.get_meta("ui_font_base"))))

func present_devices(names: Array, connected: String, open_menu: bool = false) -> void:
    _device_names = names.duplicate(true)
    device_menu.clear()
    device_menu.add_item("No MIDI input · timing preview", -2)
    device_menu.add_separator()
    for index in range(_device_names.size()):
        device_menu.add_item(str(_device_names[index]), index)
    device_button.text = connected if not connected.is_empty() else "Choose USB MIDI piano"
    if open_menu:
        device_menu.position = Vector2i(device_button.get_screen_position()) + Vector2i(0, int(device_button.size.y))
        device_menu.popup()

func present_device_selection(name: String) -> void:
    device_button.text = name + "  ✓"

func _device_chosen(index: int) -> void:
    if index == -2:
        device_selected.emit("")
    elif index >= 0 and index < _device_names.size():
        device_selected.emit(str(_device_names[index]))

func _browse_folder() -> void:
    if DirAccess.dir_exists_absolute(folder_edit.text):
        folder_dialog.current_dir = folder_edit.text
    folder_dialog.popup_centered_ratio(0.7)
