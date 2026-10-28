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
signal save_folder_requested
signal browse_folder_requested
signal tempo_requested(bpm: int)
signal metronome_requested(enabled: bool)
signal volume_changed(db: float)
signal fullscreen_requested(enabled: bool)
signal exit_requested

var ui_scale := 1.0
var default_font: Font
var settings_grid: GridContainer
var device_button: Button
var input_activity_label: Label
var folder_controls: VBoxContainer
var folder_edit: LineEdit
var tempo_setting: SpinBox
var apply_tempo_button: Button
var metronome_toggle: CheckButton
var listen_volume_slider: HSlider
var listen_volume_label: Label
var fullscreen_toggle: CheckButton
var settings_message: Label

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
    folder_edit.text_submitted.connect(func(_text: String): save_folder_requested.emit())
    folder_controls.add_child(folder_edit)
    var folder_actions := HFlowContainer.new()
    folder_actions.add_theme_constant_override("h_separation", 10)
    folder_actions.add_theme_constant_override("v_separation", 6)
    folder_controls.add_child(folder_actions)
    folder_actions.add_child(_button("Choose folder…", func(): browse_folder_requested.emit(), false, "navigation"))
    folder_actions.add_child(_button("Save folder", func(): save_folder_requested.emit(), false, "secondary"))
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
    listen_volume_slider.value_changed.connect(func(db: float): volume_changed.emit(db))
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


