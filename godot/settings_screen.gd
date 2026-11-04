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
signal mistake_response_requested(strategy: String)
signal metronome_requested(enabled: bool)
signal calibration_requested(action: String)
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
var device_button: Button
var input_activity_label: Label
var calibration_label: Label
var calibration_count_label: Label
var calibration_beat_pulse: Control
var calibration_progress: ProgressBar
var calibration_round_labels: Array[Label] = []
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
var mistake_response_picker: OptionButton
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
    calibration_count_label = _label("4 · 3 · 2 · 1 → PLAY", 28, INK, true)
    calibration_count_label.visible = false
    midi.add_child(calibration_count_label)
    calibration_beat_pulse = preload("res://calibration_beat_pulse.gd").new()
    midi.add_child(calibration_beat_pulse)
    calibration_progress = ProgressBar.new()
    calibration_progress.min_value = 0
    calibration_progress.max_value = 100
    calibration_progress.show_percentage = false
    calibration_progress.custom_minimum_size.y = 16
    calibration_progress.visible = false
    midi.add_child(calibration_progress)
    var rounds_row := HFlowContainer.new()
    rounds_row.add_theme_constant_override("h_separation", 16)
    midi.add_child(rounds_row)
    for number in range(1, 6):
        var round_label := _label("Round %d/5" % number, 14, MUTED)
        calibration_round_labels.append(round_label)
        rounds_row.add_child(round_label)
    calibration_label = _label("One 4-beat count-in, then 5 continuous rounds of 8 taps.", 14, MUTED)
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
    music.add_child(_label("MIDI files in this folder and its subfolders.", 13, MUTED))
    _build_learning_controls(music)

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
    practice.add_child(_label("When a note is wrong", 14, MUTED))
    mistake_response_picker = OptionButton.new()
    mistake_response_picker.custom_minimum_size = Vector2(260,40)
    mistake_response_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    mistake_response_picker.tooltip_text = (
        "Choose how mistakes affect the next rewind, tempo or guided exercise. "
        + "Changing this affects future mistakes without resetting the current lesson.")
    mistake_response_picker.item_selected.connect(func(index: int):
        mistake_response_requested.emit(
            str(mistake_response_picker.get_item_metadata(index))))
    practice.add_child(mistake_response_picker)
    practice.add_child(_label(
        "Exercise, rhythm and tempo generation changes restart practice. "
        + "Mistake responses can be changed without resetting your progress.",
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

func _build_learning_controls(parent: VBoxContainer) -> void:
    parent.add_child(_label("Local learning history", 17, INK, true))
    history_summary_label = _label("Loading local learning history…", 13, MUTED)
    parent.add_child(history_summary_label)
    var retention_row := HFlowContainer.new()
    retention_row.add_theme_constant_override("h_separation", 10)
    retention_row.add_theme_constant_override("v_separation", 6)
    parent.add_child(retention_row)
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
    parent.add_child(_label(
        "Limits apply to note detail at the next safe transition. Compact summaries " +
        "remain until deletion. The MiB budget measures detail payload, not database file size.",
        13, MUTED))
    export_detail_toggle = CheckButton.new()
    export_detail_toggle.text = "Include detailed note observations in export"
    export_detail_toggle.button_pressed = false
    parent.add_child(export_detail_toggle)
    var actions := HFlowContainer.new()
    actions.add_theme_constant_override("h_separation", 10)
    actions.add_theme_constant_override("v_separation", 6)
    parent.add_child(actions)
    export_history_button = _button("Export history…", _browse_history_export, false, "secondary")
    actions.add_child(export_history_button)
    delete_piece_button = _button("Delete current piece history…", _confirm_piece_history_delete, false, "utility")
    delete_piece_button.disabled = true
    actions.add_child(delete_piece_button)
    delete_learner_button = _button("Delete all learner history…", func():
        delete_learner_dialog.popup_centered(), false, "utility")
    actions.add_child(delete_learner_button)
    parent.add_child(_label(
        "Reset Lesson restarts lesson progress and preserves learning history. " +
        "Permanent deletion also removes saved learning progress. Exported files " +
        "remain wherever you saved them. Source MIDI and device settings are preserved.",
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
    delete_piece_dialog = ConfirmationDialog.new()
    delete_piece_dialog.title = "Delete current piece history?"
    delete_piece_dialog.dialog_text = (
        "Permanently delete this piece's learning history and all saved learning progress " +
        "and generator feedback? Source MIDI and device settings remain. " +
        "Previously exported files are outside this deletion.")
    delete_piece_dialog.ok_button_text = "Delete piece history"
    delete_piece_dialog.confirmed.connect(func():
        piece_history_delete_requested.emit(_deletion_fingerprint))
    add_child(delete_piece_dialog)
    delete_learner_dialog = ConfirmationDialog.new()
    delete_learner_dialog.title = "Delete all learner history?"
    delete_learner_dialog.dialog_text = (
        "Permanently delete all local learning history and learning progress, including " +
        "mastery, tempo credit, guidance and generator feedback? A new local learner " +
        "starts on next use. Source MIDI and device settings remain. " +
        "Previously exported files are outside this deletion.")
    delete_learner_dialog.ok_button_text = "Delete all learner history"
    delete_learner_dialog.confirmed.connect(func(): learner_history_delete_requested.emit())
    add_child(delete_learner_dialog)

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
    delete_piece_dialog.popup_centered()

func present_learning_status(values: Dictionary) -> void:
    history_summary_label.text = str(values.get("summary", "Local learning history"))
    if values.has("detail_attempt_count") and values.has("pruned_attempt_count"):
        history_summary_label.text += " %d takes with detail retained; %d pruned." % [
            int(values["detail_attempt_count"]), int(values["pruned_attempt_count"])]
    _history_default_path = str(values.get("default_path", ""))
    _current_fingerprint = str(values.get("current_fingerprint", ""))
    delete_piece_button.disabled = _history_busy or _current_fingerprint.is_empty()

func animate_calibration_beat(beat: float, active: bool,
        round_beats: int = 12, preparation: int = 4) -> void:
    if calibration_beat_pulse != null:
        calibration_beat_pulse.call(
            "present_beat", beat, active, round_beats, preparation)

func present_calibration(state: Dictionary, offset_ms: int) -> void:
    if calibration_label == null:
        return
    var result: Variant = state.get("result")
    var active: bool = bool(state.get("active", false))
    var total_rounds: int = maxi(1,int(state.get("rounds",5)))
    var current: int = clampi(int(state.get("round",1)),1,total_rounds)
    var total_taps: int = maxi(1,int(state.get("ticks",8)))
    var round_samples: Array = state.get("round_samples", [])
    calibration_progress.visible = active
    calibration_count_label.visible = active
    calibration_progress.value = 100.0 * clampf(
        float(state.get("progress",0.0)),0.0,1.0)
    var phase: String = str(state.get("phase","ready"))
    if active:
        if phase == "ready":
            calibration_count_label.text = "READY · 4 · 3 · 2 · 1"
        elif phase == "count_in":
            calibration_count_label.text = "COUNT IN · %d" % int(state.get("countdown",4))
        else:
            calibration_count_label.text = "ROUND %d/%d · TAP %d/%d" % [
                current,total_rounds,int(state.get("tap_number",0)),total_taps]
    for i in range(calibration_round_labels.size()):
        var count: int = int(round_samples[i]) if i < round_samples.size() else 0
        calibration_round_labels[i].text = "Round %d/%d · %d taps" % [
            i+1,total_rounds,count]
        calibration_round_labels[i].add_theme_color_override("font_color",
            INK if active and i == current-1 else MUTED)
    var status := "Saved correction: %d ms. " % offset_ms
    if active:
        status += ("Tap one key for every click. One initial count-in; " +
            "five uninterrupted eight-tap rounds.")
    elif result is Dictionary:
        var measurement: Dictionary = result
        if bool(measurement.get("reliable",false)):
            var estimate: int = int(measurement.get("estimate_ms",0))
            status += ("Measured: %d ms, %d/%d rounds used; " +
                "%d anomalous taps excluded (max jitter %d ms).") % [
                estimate,int(measurement.get("used_rounds",0)),total_rounds,
                int(measurement.get("discarded_taps",0)),
                int(measurement.get("jitter_ms",0))]
            if estimate != offset_ms:
                status += " Select Apply offset to save this correction."
            else:
                status += " This matches the saved correction."
        else:
            status += str(measurement.get("error",
                "Inconsistent timing; calibrate again."))
        var round_results: Array = measurement.get("rounds",[])
        for i in range(mini(calibration_round_labels.size(),round_results.size())):
            var entry: Dictionary = round_results[i]
            var round_status := "excluded"
            if bool(entry.get("included",false)):
                round_status = "%d ms" % int(entry.get("median_ms",0))
            calibration_round_labels[i].text = "Round %d: %s" % [i+1,round_status]
    else:
        status += "Calibrate: four-beat count-in once, then five eight-tap rounds."
    calibration_label.text = status
    calibration_label.tooltip_text = (
        "This measures tap timing relative to audible clicks, including human " +
        "timing and audio output delay; it does not isolate Bluetooth MIDI latency.")
    calibration_apply_button.disabled = not (result is Dictionary and
        bool(result.get("reliable",false)))

func present_preferences(values: Dictionary) -> void:
    folder_edit.text = str(values.get("music_dir", ""))
    evidence_days_setting.set_value_no_signal(float(values.get("evidence_retention_days", 365)))
    evidence_budget_setting.set_value_no_signal(float(values.get("evidence_budget_mib", 256)))
    present_window_mode(bool(values.get("fullscreen", true)))
    metronome_toggle.set_pressed_no_signal(bool(values.get("metronome", true)))
    _present_strategy_picker(strategy_picker,
        values.get("available_exercise_strategies", []),
        str(values.get("exercise_strategy", "coda-midi")))
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
    _present_strategy_picker(mistake_response_picker,
        values.get("available_mistake_response_strategies", []),
        str(values.get("mistake_response_strategy", "adaptive")))
    for option in values.get("available_mistake_response_strategies", []):
        if option is Dictionary and str(option.get("id","")) == \
                str(values.get("mistake_response_strategy","adaptive")):
            mistake_response_picker.tooltip_text = str(option.get("description",""))
            break
    var selected_strategy: String = str(values.get("exercise_strategy", ""))
    var owns_timing := false
    for entry in values.get("available_exercise_strategies", []):
        if entry is Dictionary and str(entry.get("id", "")) == selected_strategy:
            owns_timing = bool(entry.get("owns_timing", false))
            break
    timing_strategy_picker.disabled = owns_timing
    tempo_strategy_picker.disabled = owns_timing
    timing_strategy_picker.tooltip_text = (
        "This lesson generator owns its rhythmic exercises."
        if owns_timing else "Choose an independent timing transformation.")
    tempo_strategy_picker.tooltip_text = (
        "This lesson generator owns its tempo stages."
        if owns_timing else "Choose an independent tempo policy.")

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
    _history_busy = pending
    apply_tempo_button.disabled = pending
    strategy_picker.disabled = pending
    timing_strategy_picker.disabled = pending
    tempo_strategy_picker.disabled = pending
    diagnosis_strategy_picker.disabled = pending
    learner_strategy_picker.disabled = pending
    mistake_response_picker.disabled = pending
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
