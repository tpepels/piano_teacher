extends ScrollContainer
# Standalone settings view. It owns its controls and visual hierarchy;
# the application coordinates in-process commands, MIDI and platform actions via signals.
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
signal metronome_requested(enabled: bool)
signal hold_grading_requested(enabled: bool)
signal calibration_page_requested
var timing_label: Label
signal midi_range_requested(action: String)
signal volume_changed(db: float)
signal fullscreen_requested(enabled: bool)
signal retention_save_requested(days: int, budget_mib: int)
signal history_export_requested(path: String, include_detail: bool)
signal piece_history_delete_requested(fingerprint: String)
signal learner_history_delete_requested
signal exit_requested

var ui_scale := 1.0
var default_font: Font
var settings_grid: GridContainer
var history_actions_body: VBoxContainer
var history_toggle: Button
var device_button: Button
var input_activity_label: Label
var midi_range_label: Label
var midi_range_start_button: Button
var midi_range_cancel_button: Button
var folder_controls: VBoxContainer
var folder_edit: LineEdit
var tempo_setting: SpinBox
var apply_tempo_button: Button
var metronome_toggle: CheckButton
var hold_grading_toggle: CheckButton
var listen_volume_slider: HSlider
var listen_volume_label: Label
var fullscreen_toggle: CheckButton
var settings_message: Label
var folder_dialog: FileDialog
var device_menu: PopupMenu
var _device_names: Array = []
var evidence_days_setting: SpinBox
var evidence_budget_setting: SpinBox
var retention_save_button: Button
var export_detail_toggle: CheckButton
var export_history_button: Button
var export_dialog: FileDialog
var delete_piece_button: Button
var delete_learner_button: Button
var delete_piece_dialog: ConfirmationDialog
var delete_learner_dialog: ConfirmationDialog
var history_summary_label: Label
var _history_default_path := ""
var _current_fingerprint := ""
var _deletion_fingerprint := ""
var _history_busy := false
var statistics_view: VBoxContainer

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
    var control := _stack(10)
    control.add_child(_title(value, 26))
    return control

func _disclosure(parent: VBoxContainer, title: String,
        content: VBoxContainer) -> Button:
    var toggle := _button("▸ " + title, func(): pass,false,"secondary")
    toggle.name = title.replace(" ","") + "Disclosure"
    toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    content.visible = false
    parent.add_child(toggle)
    parent.add_child(content)
    toggle.pressed.connect(func():
        content.visible = not content.visible
        toggle.text = ("▾ " if content.visible else "▸ ") + title)
    return toggle


func _card() -> PanelContainer:
    # Sections sit on the stage, separated by space and a hairline, not boxed.
    var control := PanelContainer.new()
    var line := StyleBoxFlat.new()
    line.bg_color = Color.TRANSPARENT
    line.border_width_top = 1
    line.border_color = Color(Design.SAGE, .22)
    control.add_theme_stylebox_override("panel", line)
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
    # Actions are key caps; danger keys are rose.
    control.set_meta("ui_font_base", 16)
    control.add_theme_font_size_override("font_size", _ui_font(16))
    control.configure("key_danger" if role == "danger" else "key")
    var width: float = Design.font(600).get_string_size(value,
        HORIZONTAL_ALIGNMENT_LEFT, -1, _ui_font(16)).x
    control.custom_minimum_size = Vector2(width + 40.0 * ui_scale, 42.0 * ui_scale)
    control.pressed.connect(callback)
    return control

func _ready() -> void:
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    var content := _stack(20)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    add_child(content)
    content.add_child(_title("Settings", 44))

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
    device_button = _button("Choose piano", func(): choose_devices_requested.emit(), false, "settings")
    device_row.add_child(device_button)
    device_row.add_child(_button("Refresh", func(): refresh_devices_requested.emit(), false, "utility"))
    input_activity_label = _label("Play a note to test.", 14, MUTED)
    midi.add_child(input_activity_label)
    var keyboard_range_row := HFlowContainer.new()
    keyboard_range_row.add_theme_constant_override("h_separation",8)
    midi.add_child(keyboard_range_row)
    midi_range_start_button = _button("Set key range",func():
        midi_range_requested.emit("midi_range_start"),false,"settings")
    keyboard_range_row.add_child(midi_range_start_button)
    midi_range_cancel_button = _button("Cancel",func():
        midi_range_requested.emit("midi_range_cancel"),false,"utility")
    midi_range_cancel_button.visible = false
    keyboard_range_row.add_child(midi_range_cancel_button)
    midi_range_label = _label("",14,MUTED)
    midi.add_child(midi_range_label)
    # Timing calibration has its own page; here: the current correction.
    var timing_row := HBoxContainer.new()
    timing_row.add_theme_constant_override("separation", 12)
    midi.add_child(timing_row)
    timing_row.add_child(_button("Calibrate timing", func(): calibration_page_requested.emit()))
    timing_label = _label("", 14, MUTED)
    timing_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    timing_row.add_child(timing_label)

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
    folder_actions.add_child(_button("Choose folder", _browse_folder, false, "navigation"))
    folder_actions.add_child(_button("Save", func(): save_folder_requested.emit(folder_edit.text.strip_edges()), false, "secondary"))
    music.add_child(_label("MIDI and MusicXML, including subfolders.", 13, MUTED))
    # History is a full-width secondary section, not part of folder setup.

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
    apply_tempo_button = _button("Apply", func(): tempo_requested.emit(int(tempo_setting.value)), false, "settings")
    tempo_row.add_child(apply_tempo_button)
    metronome_toggle = CheckButton.new()
    metronome_toggle.text = "Metronome"
    metronome_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    metronome_toggle.tooltip_text = "Count-in is always audible, even when metronome is off"
    metronome_toggle.toggled.connect(func(enabled: bool): metronome_requested.emit(enabled))
    practice.add_child(metronome_toggle)
    hold_grading_toggle = CheckButton.new()
    hold_grading_toggle.text = "Grade note length"
    hold_grading_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    hold_grading_toggle.tooltip_text = (
        "Off: pitch and note attacks determine success; key-release data is saved. "
        + "On: early, late and missing key releases affect grading. Sustain pedal "
        + "may extend sound beyond the physical key release.")
    hold_grading_toggle.toggled.connect(func(enabled: bool):
        hold_grading_requested.emit(enabled))
    practice.add_child(hold_grading_toggle)
    practice.add_child(_label(
        "Off by default.", 12, MUTED))

    var audio := _section("Listening & display")
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
    fullscreen_toggle.text = "Fullscreen"
    fullscreen_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    fullscreen_toggle.button_pressed = true
    fullscreen_toggle.toggled.connect(func(enabled: bool): fullscreen_requested.emit(enabled))
    audio.add_child(fullscreen_toggle)
    # Put the highest-priority controls (MIDI and tempo) in the first row.
    # Folder configuration and listening occupy the second row.
    settings_grid.move_child(practice_panel,1)
    var history_panel := _card()
    history_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    content.add_child(history_panel)
    var history := _section("Learning history")
    _card_body(history_panel,18).add_child(history)
    _build_learning_controls(history)
    settings_message = _label("", 14, MUTED)
    settings_message.visible = false
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

func _build_learning_controls(parent: VBoxContainer) -> void:
    parent.add_child(_label("Saved practice results", 14, MUTED))
    history_summary_label = _label("Loading local learning history…", 13, MUTED)
    parent.add_child(history_summary_label)
    statistics_view = preload("res://learning_statistics_view.gd").new()
    _disclosure(parent, "Practice statistics", statistics_view)
    history_actions_body = _stack(10)
    history_toggle = _disclosure(parent,"Retention, export and deletion",history_actions_body)
    var retention_row := HFlowContainer.new()
    retention_row.add_theme_constant_override("h_separation", 10)
    retention_row.add_theme_constant_override("v_separation", 6)
    history_actions_body.add_child(retention_row)
    evidence_days_setting = SpinBox.new()
    evidence_days_setting.min_value = 7
    evidence_days_setting.max_value = 3650
    evidence_days_setting.step = 1
    evidence_days_setting.value = 365
    evidence_days_setting.suffix = " days"
    evidence_days_setting.tooltip_text = "Retain detailed note observations for 7–3,650 days."
    evidence_days_setting.custom_minimum_size = Vector2(150, 40)
    retention_row.add_child(evidence_days_setting)
    evidence_budget_setting = SpinBox.new()
    evidence_budget_setting.min_value = 16
    evidence_budget_setting.max_value = 4096
    evidence_budget_setting.step = 1
    evidence_budget_setting.value = 256
    evidence_budget_setting.suffix = " MiB"
    evidence_budget_setting.tooltip_text = "Logical detail payload budget, 16–4,096 MiB."
    evidence_budget_setting.custom_minimum_size = Vector2(150, 40)
    retention_row.add_child(evidence_budget_setting)
    retention_save_button = _button("Save retention", func():
        retention_save_requested.emit(int(evidence_days_setting.value),
            int(evidence_budget_setting.value)), false, "settings")
    retention_row.add_child(retention_save_button)
    history_actions_body.add_child(_label(
        "Limits apply to note detail at the next safe transition. Compact summaries " +
        "remain until deletion. The MiB budget measures detail payload, not database file size.",
        13, MUTED))
    export_detail_toggle = CheckButton.new()
    export_detail_toggle.text = "Include detailed note observations in export"
    export_detail_toggle.button_pressed = false
    history_actions_body.add_child(export_detail_toggle)
    var actions := HFlowContainer.new()
    actions.add_theme_constant_override("h_separation", 10)
    actions.add_theme_constant_override("v_separation", 6)
    history_actions_body.add_child(actions)
    export_history_button = _button("Export history", _browse_history_export, false, "secondary")
    actions.add_child(export_history_button)
    delete_piece_button = _button("Delete this piece's history", _confirm_piece_history_delete, false, "danger")
    delete_piece_button.disabled = true
    actions.add_child(delete_piece_button)
    delete_learner_button = _button("Delete all history", func():
        _popup_confirmation(delete_learner_dialog), false, "danger")
    actions.add_child(delete_learner_button)
    history_actions_body.add_child(_label(
        "Deleting history also deletes saved progress. Your music files stay.",
        13, MUTED))
    export_dialog = FileDialog.new()
    export_dialog.title = "Export local learning history"
    export_dialog.access = FileDialog.ACCESS_FILESYSTEM
    export_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
    export_dialog.filters = PackedStringArray(["*.json ; Learning history JSON"])
    export_dialog.use_native_dialog = true
    export_dialog.file_selected.connect(func(path: String):
        history_export_requested.emit(path, export_detail_toggle.button_pressed))
    add_child(export_dialog)
    delete_piece_dialog = _confirmation("Delete this piece's history?",
        "This permanently deletes the learning history and saved progress of " +
        "this piece. Your music files, settings and earlier exports stay.",
        "Delete piece history")
    delete_piece_dialog.confirmed.connect(func():
        piece_history_delete_requested.emit(_deletion_fingerprint))
    add_child(delete_piece_dialog)
    delete_learner_dialog = _confirmation("Delete all history?",
        "This permanently deletes all learning history and saved progress on " +
        "this computer, for every piece. Your music files, settings and earlier " +
        "exports stay.",
        "Delete all history")
    delete_learner_dialog.confirmed.connect(func(): learner_history_delete_requested.emit())
    add_child(delete_learner_dialog)

## A confirmation in the app's own look whose text wraps: it is never wider
## than the window (a long line made the box run off the screen).
func _confirmation(title: String, text: String, ok_text: String) -> ConfirmationDialog:
    var dialog := ConfirmationDialog.new()
    dialog.title = title
    dialog.dialog_text = text
    dialog.dialog_autowrap = true
    dialog.ok_button_text = ok_text
    dialog.theme = Design.create()
    var panel := StyleBoxFlat.new()
    panel.bg_color = Design.PANEL_RECESSED
    panel.set_content_margin_all(22)
    dialog.add_theme_stylebox_override("panel", panel)
    # The window frame and title bar in the same dark look, not Godot grey.
    var frame := StyleBoxFlat.new()
    frame.bg_color = Design.PANEL_RECESSED
    frame.border_color = Color(Design.CORAL, .55)
    frame.set_border_width_all(1)
    frame.set_corner_radius_all(12)
    frame.expand_margin_top = 40
    frame.expand_margin_left = 2
    frame.expand_margin_right = 2
    frame.expand_margin_bottom = 2
    for name in ["embedded_border", "embedded_unfocused_border"]:
        dialog.add_theme_stylebox_override(name, frame)
    dialog.add_theme_color_override("title_color", INK)
    dialog.get_label().add_theme_color_override("font_color", INK)
    dialog.get_ok_button().add_theme_color_override("font_color", Design.CORAL)
    return dialog

func _popup_confirmation(dialog: ConfirmationDialog) -> void:
    var view: Vector2 = get_viewport_rect().size
    var width: int = int(minf(620.0*ui_scale, view.x*.86))
    dialog.size = Vector2i(width, 0)
    dialog.popup_centered(Vector2i(width, 0))
    # After the wrapped text is laid out at this width, shrink the box to
    # its content and centre it inside the window.
    await get_tree().process_frame
    dialog.size = Vector2i(width, 0)
    dialog.position = Vector2i((Vector2(view) - Vector2(dialog.size))*.5)

func _browse_history_export() -> void:
    if not _history_default_path.is_empty():
        var directory := _history_default_path.get_base_dir()
        while not directory.is_empty() and not DirAccess.dir_exists_absolute(directory):
            var ancestor := directory.get_base_dir()
            if ancestor == directory:
                break
            directory = ancestor
        if DirAccess.dir_exists_absolute(directory):
            export_dialog.current_dir = directory
        export_dialog.current_file = _history_default_path.get_file()
    else:
        export_dialog.current_file = "learning-history.json"
    export_dialog.popup_centered_ratio(0.7)

func _confirm_piece_history_delete() -> void:
    if _current_fingerprint.is_empty() or _history_busy:
        return
    _deletion_fingerprint = _current_fingerprint
    _popup_confirmation(delete_piece_dialog)

func present_learning_status(values: Dictionary) -> void:
    history_summary_label.text = str(values.get("summary", "Local learning history"))
    _history_default_path = str(values.get("default_path", ""))
    _current_fingerprint = str(values.get("current_fingerprint", ""))
    delete_piece_button.disabled = _history_busy or _current_fingerprint.is_empty()

func present_midi_key_range(state: Dictionary) -> void:
    if midi_range_label == null:
        return
    var device: String = str(state.get("device",""))
    var active: bool = bool(state.get("active",false))
    midi_range_start_button.disabled = device.is_empty() or active
    midi_range_cancel_button.visible = active
    if active:
        midi_range_label.text = ("Press the keyboard's LOWEST physical key."
            if str(state.get("step","")) == "lowest"
            else "Now press the HIGHEST physical key (higher than the lowest).")
    elif bool(state.get("configured",false)):
        midi_range_label.text = ("Shortcuts: lowest key %d = Pause/Resume; "
            + "highest key %d = Restart with count-in. Notes in this exercise take priority.") % [
                int(state.get("low",0)),int(state.get("high",127))]
    elif device.is_empty():
        midi_range_label.text = ""
    else:
        midi_range_label.text = ""


func present_calibration(_state: Dictionary, offset_ms: int) -> void:
    if timing_label != null:
        timing_label.text = "Current correction: %d ms" % offset_ms

func present_preferences(values: Dictionary) -> void:
    folder_edit.text = str(values.get("music_dir", ""))
    evidence_days_setting.set_value_no_signal(float(values.get("evidence_retention_days", 365)))
    evidence_budget_setting.set_value_no_signal(float(values.get("evidence_budget_mib", 256)))
    present_window_mode(bool(values.get("fullscreen", true)))
    metronome_toggle.set_pressed_no_signal(bool(values.get("metronome", true)))
    hold_grading_toggle.set_pressed_no_signal(bool(values.get("grade_note_holds", false)))

func begin_editing(state: Dictionary) -> void:
    tempo_setting.set_value_no_signal(float(state.get("target_bpm", 40)))

func present_practice(state: Dictionary, editing: bool = false) -> void:
    # The committed backend snapshot owns the device label, including hot-plug.
    var connected: String = str(state.get("device", ""))
    device_button.text = connected if not connected.is_empty() else "Choose piano"
    var age = state.get("midi_input_age")
    var recent: bool = age != null and float(age) < 1.5
    if recent:
        input_activity_label.text = "Input received · MIDI note %d · %d notes received" % [
            int(state.get("midi_input_note", 0)), int(state.get("midi_input_count", 0))]
    else:
        input_activity_label.text = "Play a note to test." if not str(state.get("device", "")).is_empty() else "Connect your piano, then play a note to test."
    var tone: Color = ACCENT if recent else MUTED
    if input_activity_label.get_theme_color("font_color") != tone:
        input_activity_label.add_theme_color_override("font_color", tone)
    if bool(state.get("loaded", false)):
        tempo_setting.min_value = float(state.get("minimum_bpm", 12))
        tempo_setting.max_value = float(state.get("maximum_bpm", 300))
        if not editing:
            tempo_setting.set_value_no_signal(float(state.get("target_bpm", state.get("bpm", 40))))

func present_busy(pending: bool) -> void:
    _history_busy = pending
    apply_tempo_button.disabled = pending
    retention_save_button.disabled = pending
    evidence_days_setting.editable = not pending
    evidence_budget_setting.editable = not pending
    export_history_button.disabled = pending
    export_detail_toggle.disabled = pending
    delete_piece_button.disabled = pending or _current_fingerprint.is_empty()
    delete_learner_button.disabled = pending

func present_volume(db: float) -> void:
    listen_volume_slider.set_value_no_signal(db)
    listen_volume_label.text = "%+d dB" % int(round(db))

func present_window_mode(fullscreen: bool) -> void:
    fullscreen_toggle.set_pressed_no_signal(fullscreen)

func present_message(message: String) -> void:
    settings_message.text = message
    settings_message.visible = not message.is_empty()

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
    device_button.text = connected if not connected.is_empty() else "Choose piano"
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
