extends Control

# Lightweight Godot presentation. Python owns MIDI timestamps, tempo and grading.
const URL := "http://127.0.0.1:8765"
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const PAPER := Design.FOREST
const WHITE := Design.PANEL
const ACCENT := Design.TEAL
const ScoreEffects := preload("res://score_effects.gd")
const ChallengeFlow := preload("res://challenge_flow.gd")
const LivingScore := preload("res://living_score.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")
const GameBackdrop := preload("res://game_backdrop.gd")
const GameStage := preload("res://game_stage.gd")
const GameImpactCallout := preload("res://game_impact_callout.gd")
const GameStreak := preload("res://game_streak.gd")
const GameCountIn := preload("res://game_countin.gd")
const GamePhaseCue := preload("res://game_phase_cue.gd")
const GameTransportButton := preload("res://game_transport_button.gd")
const ActionButton := preload("res://action_button.gd")
const LibraryRow := preload("res://library_row.gd")
const GameInputIndicator := preload("res://game_input_indicator.gd")
const VisualTransportClock := preload("res://visual_transport_clock.gd")
const NativeNotation := preload("res://notation/native/view.gd")
const FrameMeter := preload("res://frame_meter.gd")

var current_screen := "practice"
var settings_return_screen := "practice"
var overlay_root: Control
var overlay_drawer: PanelContainer
var navigation_rail: VBoxContainer
var screen_navigation: Dictionary = {}
var library_heading: BoxContainer
var library_grids: Array[GridContainer] = []
var settings_grid: GridContainer
var lesson_stage_labels: Dictionary = {}
var lesson_piece_title: Label
var path_reset_button: Button
var path_reset_confirmation: VBoxContainer
var path_reset_fingerprint := ""
var lesson_refresh_after_reset := false
var drawer_intro: Tween
var picker_intro: Tween
var overlay_backdrop: ColorRect
var score_browse_button: Button
var screens: Dictionary = {}
var library_request: HTTPRequest
var settings_request: HTTPRequest
var library_pending := false
var library_health_request: HTTPRequest
var library_health_pending := false
var library_health_info: Dictionary = {}
var library_health_button: Button
var library_health_label: Label
var settings_pending := false
var library_info: Dictionary = {}
var preferences: Dictionary = {}
var home_count_label: Label
var home_cards: BoxContainer
var page_margins: Array[MarginContainer] = []
var folder_controls: BoxContainer
var practice_settings_button: Button
var practice_navigation: HFlowContainer
var practice_header: HBoxContainer
var game_brand: Label
var game_stage: Control
var game_impact_callout: Control
var game_streak: Control
var game_input_indicator: Control
var game_count_in: Control
var score_status_panel: CenterContainer
var score_status_label: Label
var score_retry_button: Button
var fingering_status_label: Label
var fingering_save_error := ""
var native_score_piece_fingerprint := ""
var score_error := ""
var library_error := ""
var pending_library_piece := ""
var pending_library_resume := false
var library_resume_requested := false
var home_recent_label: Label
var home_resume_button: Button
var library_search: LineEdit
var library_filter_timer: Timer
var library_scroll: ScrollContainer
var library_path_label: Label
var library_rows: VBoxContainer
var library_message: Label
var open_picker: Control
var open_panel: PanelContainer
var open_measure: SpinBox
var open_measure_slider: HSlider
var open_mode: OptionButton
var open_title: Label
var practice_stage_bar: HFlowContainer
var practice_stage_labels: Dictionary = {}
var presented_hand_stages: Array = []
var practice_retry_button: Button
var practice_music_button: Button
var folder_edit: LineEdit
var folder_dialog: FileDialog
var fullscreen_toggle: CheckButton
var settings_message: Label
var last_post_path := ""
var last_control_action := ""
var pending_transport_action := ""
var action_request_started_ms := 0
var state_request: HTTPRequest
var layout_request: HTTPRequest
var action_request: HTTPRequest
var device_request: HTTPRequest
var title_label: Label
var passage_label: Label
var hand_label: Label
var speed_label: Label
var tempo_up_button: Button
var tempo_down_button: Button
var practice_step_picker: OptionButton
var practice_step_controls: HBoxContainer
var practice_step_previous_button: Button
var practice_step_next_button: Button
var practice_step_entries: Array = []
var lesson_choice_fingerprint := ""
var lesson_requested_fingerprint := ""
var feedback_label: Label
var progress_label: Label
var device_button: Button
var device_menu_requested := false
var start_button: Button
var score_effects = ScoreEffects.new()
var score_frame: Control
var count_tick_index := -1
var play_tick_index := -1
var game_phase_cue: Control
var click_player: AudioStreamPlayer
var click_high: AudioStreamWAV
var click_low: AudioStreamWAV
var device_menu: PopupMenu
var device_names: Array = []
var revision := -1
var state_pending := false
var layout_revision := -1
var requested_layout_revision := -1
var layout_pending := false
var score_layout: Dictionary = {}
var living_chords: Array = []
var rendered_revision := -1
var action_pending := false
var last_state: Dictionary = {}
var hand_unlock_message := ""
var hand_unlock_until_ms := 0
var last_state_tick := 0
var last_playhead_strike_beat := -INF
var last_playhead_strike_transport := -1
var visual_transport_clock = VisualTransportClock.new()
# The native compositor is the sole production score view.
var timeline_preview: Control
var native_score_feedback: Control
var timeline_model_request: HTTPRequest
var timeline_model_pending := false
var timeline_model_revision := -1
var timeline_model_retry_after_ms := 0
var state_request_started_ms := 0
var last_audio_transport_id := -1
# Opt-in diagnostic hook for the actual headless UI integration test only.
var phase0_smoke_mode := false
var listen_sync_diagnostics := false
var last_listen_sync_report_ms := 0
var frame_diagnostics := false
var frame_meter = FrameMeter.new()
var phase0_last_phase := ""
var phase0_last_cursor_tick := -1
var phase0_last_lead_tick := -999
var lesson_request: HTTPRequest
var lesson_pending := false
var lesson_columns: BoxContainer
var lesson_options: PanelContainer
var lesson_rows: VBoxContainer
var lesson_summary: Label
var lesson_description: Label
var input_activity_label: Label
var tempo_setting: SpinBox
var metronome_toggle: CheckButton
var stop_button: Button
var lesson_info_label: Label
var practice_progress: ProgressBar
var practice_controls: HFlowContainer
var hand_buttons: Dictionary = {}
var device_pending := false
var practice_layout_box: VBoxContainer
var practice_score_panel: PanelContainer
var practice_playback_banner: Label
var practice_note_feedback_panel: PanelContainer
var practice_note_feedback_label: Label
var score_margin_box: MarginContainer
var hint_keyboard: Control
var mode_choice: OptionButton
var hints_toggle: CheckButton
var demo_player: Node
var listen_button: Button
var listen_volume_slider: HSlider
var listen_volume_label: Label
var performance_review: VBoxContainer
var performance_text: Label
var weak_button: Button
var review_sheet: AcceptDialog
var pause_sheet: Control
var advanced_pause_open := false
var skip_stage_button: Button
var practice_skip_button: Button
var placement_button: Button
var apply_tempo_button: Button
var ui_scale := 1.0
var last_seen_midi_input_count := -1
var last_seen_midi_visual_sequence := 0
var state_poll_timer: Timer

func _ready() -> void:
    # On 120/144 Hz laptops Godot otherwise renders the entire translucent
    # piano stage on every monitor refresh even though MIDI timing is handled
    # by the independent Python transport. Cap visual frames, not music.
    Engine.max_fps = 60
    # The static score and drawers should not keep the display rendering
    # continuously while no transport is moving.
    OS.low_processor_usage_mode_sleep_usec = 33000
    OS.low_processor_usage_mode = true
    phase0_smoke_mode = OS.get_cmdline_user_args().has("--phase0-smoke")
    listen_sync_diagnostics = OS.get_cmdline_user_args().has("--listen-sync-diagnostics")
    frame_diagnostics = OS.get_cmdline_user_args().has("--frame-diagnostics")
    # Apply one device-independent Window scale before creating the controls.
    # Do not enlarge fonts and controls a second time in the layouts.
    _configure_ui_scaling()
    ui_scale = _readable_ui_scale()
    _build_interface()
    demo_player = preload("res://demo_player.gd").new()
    add_child(demo_player)
    listen_volume_slider.set_value_no_signal(float(demo_player.get("listen_volume_db")))
    _show_listen_volume(float(demo_player.get("listen_volume_db")))
    demo_player.prepared.connect(func(token: String, ready_revision: int):
        _send_action({"action": "demo_ready", "token": token, "revision": ready_revision}))
    demo_player.failed.connect(func(message: String): feedback_label.text = message)
    if phase0_smoke_mode:
        _navigate("practice")
    click_high = _make_count_click(1160.0)
    click_low = _make_count_click(770.0)
    click_player = AudioStreamPlayer.new()
    click_player.volume_db = -5.0
    add_child(click_player)
    resized.connect(_update_responsive_layout)
    if not get_window().size_changed.is_connected(_update_responsive_layout):
        get_window().size_changed.connect(_update_responsive_layout)
    _update_responsive_layout()
    state_request = _new_request(_on_state)
    layout_request = _new_request(_on_layout)
    timeline_model_request = _new_request(_on_timeline_model)
    # Verovio can take longer to engrave a dense MIDI score on the first run.
    # Do not abandon the request after the generic five-second timeout.
    layout_request.timeout = 90.0
    action_request = _new_request(_on_action)
    action_request.timeout = 90.0
    device_request = _new_request(_on_devices)
    library_request = _new_request(_on_library)
    library_health_request = _new_request(_on_library_health)
    settings_request = _new_request(_on_settings)
    lesson_request = _new_request(_on_lesson)
    state_poll_timer = Timer.new()
    state_poll_timer.wait_time = 0.15
    state_poll_timer.autostart = true
    state_poll_timer.timeout.connect(_poll)
    add_child(state_poll_timer)
    _poll()
    _request_devices()
    _request_settings()
    _request_library()
    var scan_timer := Timer.new()
    scan_timer.wait_time = 5.0
    scan_timer.autostart = true
    scan_timer.timeout.connect(func():
        if current_screen == "home" or current_screen == "library":
            _request_library()
        # The backend independently checks the chosen MIDI port every
        # MIDI_SCAN_SECONDS and reconnects the saved piano if needed. Repeating
        # ALSA enumeration in the Practice UI adds device-probe warnings and
        # lock contention without improving hotplug detection. Only discover
        # a new device while none is connected, in Settings, or on explicit tap.
        if current_screen == "settings" or (current_screen == "practice"
                and str(last_state.get("device", "")).is_empty()):
            _request_devices()
    )
    add_child(scan_timer)
    var health_timer := Timer.new()
    health_timer.wait_time = 1.2
    health_timer.autostart = true
    health_timer.timeout.connect(func():
        if current_screen == "library" and bool(library_health_info.get("running", false)):
            _request_library_health())
    add_child(health_timer)
    set_process(true)

func _make_count_click(frequency: float) -> AudioStreamWAV:
    # Locally generated sound: no MIDI output device or soundfont required.
    const RATE := 44100
    const FRAMES := 4200
    var samples := PackedByteArray()
    samples.resize(FRAMES * 2)
    for i in range(FRAMES):
        var t: float = float(i) / float(RATE)
        var envelope: float = pow(1.0 - float(i) / float(FRAMES), 4.0)
        var wave: float = sin(TAU * frequency * t) * envelope * 0.46
        samples.encode_s16(i * 2, int(wave * 32767.0))
    var audio := AudioStreamWAV.new()
    audio.format = AudioStreamWAV.FORMAT_16_BITS
    audio.mix_rate = RATE
    audio.stereo = false
    audio.data = samples
    return audio

func _count_tick(accent: bool) -> void:
    if click_player == null:
        return
    if not bool(preferences.get("metronome", true)) and _transport_beat_now() >= 0.0:
        return
    click_player.stream = click_high if accent else click_low
    click_player.play()
    # The smoke confirms clock scheduling; it cannot test physical speakers.
    if phase0_smoke_mode:
        print("PHASE0_CLICK:", str(last_state.get("phase", "")))

func _transport_beat_now() -> float:
    # Keep the score's musical clock phase-locked across uneven HTTP replies.
    # The Python engine remains authoritative for note timing and assessment.
    if visual_transport_clock.matches(last_state):
        return visual_transport_clock.now(Time.get_ticks_msec())
    # Direct-state smoke fixtures, before any network snapshot is received.
    var beat: float = float(last_state.get("clock_beat", 0.0))
    if bool(last_state.get("running", false)) and not bool(last_state.get("paused", false)):
        var elapsed: float = maxf(0.0, float(Time.get_ticks_msec() - last_state_tick) / 1000.0)
        beat += elapsed * float(last_state.get("bpm", 60.0)) / 60.0
    return beat

# Projection only: never change the backend's local MIDI grading clock.
# Across repeats the model is drawn at consecutive positions on one infinite
# visual axis. During feedback/recovery the server supplies the desired scroll
# direction; extrapolate its last snapshot between HTTP state polls.
func _unrolled_score_beat(transport_clock: float) -> float:
    if not last_state.has("visual_offset_beats"):
        return NAN
    if bool(last_state.get("running", false)):
        return float(last_state.get("visual_offset_beats", 0.0)) \
            + float(last_state.get("play_from_beat", 0.0)) + transport_clock
    var observed: float = float(last_state.get("visual_scroll_beat", 0.0))
    if bool(last_state.get("paused", false)):
        return observed
    var speed: float = float(last_state.get("visual_scroll_speed", 0.0))
    if absf(speed) < .000001:
        return observed
    var age: float = maxf(0.0, float(Time.get_ticks_msec() - last_state_tick) / 1000.0)
    var target: float = float(last_state.get("visual_target_beat", observed))
    return minf(target, observed + speed * age) if speed > 0.0 \
        else maxf(target, observed + speed * age)


func _update_count_in() -> void:
    if last_state.is_empty() or not bool(last_state.get("running", false)):
        game_count_in.present(0.0, 4, false, false)
        count_tick_index = -999
        play_tick_index = -1
        return
    var beat: float = _transport_beat_now()
    var paused: bool = bool(last_state.get("paused", false))
    game_count_in.present(beat,
        maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4))))),
        true, paused)
    var attempt: int = int(last_state.get("transport_id", 0))
    if attempt != last_audio_transport_id:
        count_tick_index = -999
        play_tick_index = -1
        last_audio_transport_id = attempt
    if paused:
        # A paused count-in and a paused score both freeze on their last beat.
        count_tick_index = int(floor(beat + 0.00001))
        return
    var tick: int = int(floor(beat + 0.00001))
    if tick != count_tick_index:
        count_tick_index = tick
        # The pickup may be shorter than a whole bar. Accents still follow
        # the original musical meter, not its abbreviated preparation length.
        var bar_beats: int = maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4)))))
        _count_tick(posmod(tick, bar_beats) == 0)

func _native_score_ready() -> bool:
    return timeline_preview != null and timeline_preview.native_ready \
        and layout_revision == revision and timeline_model_revision == revision \
        and rendered_revision == revision


func _visible_score_noteheads() -> int:
    if timeline_preview == null or not timeline_preview.is_visible_in_tree():
        return 0
    var viewport := Rect2(Vector2.ZERO, timeline_preview.size)
    var visible := 0
    for point in timeline_preview.drawn_noteheads.values():
        if viewport.has_point(point):
            visible += 1
    return visible


func _new_request(callback: Callable) -> HTTPRequest:
    var req := HTTPRequest.new()
    req.timeout = 5.0
    add_child(req)
    req.request_completed.connect(callback)
    return req

func _decode_json(body: PackedByteArray) -> Variant:
    # HTTPRequest can complete with an empty body when the Python service is
    # unavailable. JSON.parse_string() logs a parser error in that case.
    if body.is_empty():
        return null
    var document := JSON.new()
    if document.parse(body.get_string_from_utf8()) != OK:
        return null
    return document.data

func _http_failure(code: int, body: PackedByteArray) -> String:
    var response = _decode_json(body)
    if typeof(response) == TYPE_DICTIONARY:
        return str(response.get("error", "Request failed (HTTP %d)" % code))
    if code == 0:
        return "Practice engine unavailable. Start Piano Teacher with ./run.sh"
    return "Practice engine request failed (HTTP %d)" % code

func _configure_ui_scaling() -> void:
    # Godot must scale the *whole* interface once: text, drawing, music,
    # hit targets and popup placement. Scaling only individual font overrides
    # left score and controls at unrelated sizes on large/HiDPI displays.
    var window: Window = get_window()
    if window == null:
        return
    var physical := Vector2(window.size)
    var factor: float = maxf(1.0, minf(physical.x / 1280.0,
        physical.y / 800.0))
    if absf(window.content_scale_factor - factor) > .001:
        window.content_scale_factor = factor


func _readable_ui_scale() -> float:
    # Layout dimensions are logical pixels after Window content scaling.
    # Multiplying these again by screen resolution causes double scaling.
    return 1.0

func _ui_font(base: int) -> int:
    return maxi(14, int(round(float(base) * ui_scale)))

func _resize_ui_fonts(node: Node) -> void:
    if node is Control and node.has_meta("ui_font_base"):
        (node as Control).add_theme_font_size_override(
            "font_size", _ui_font(int(node.get_meta("ui_font_base"))))
    if node.has_method("set_text_scale"):
        node.call("set_text_scale", ui_scale)
    for child in node.get_children():
        _resize_ui_fonts(child)

func _label(text: String, size: int, color: Color, bold := false) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_color_override("font_color", color)
    label.set_meta("ui_font_base", size)
    label.add_theme_font_size_override("font_size", _ui_font(size))
    label.add_theme_font_override("font", Design.font(700 if bold else 400))
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return label

func _title(text: String, size: int = 28) -> Label:
    var label := _label(text, size, INK)
    label.add_theme_font_override("font", Design.title_font())
    return label

func _section(text: String) -> VBoxContainer:
    var section := _stack(12)
    section.add_child(_label(text, 17, INK, true))
    return section

func _divider() -> HSeparator:
    var divider := HSeparator.new()
    var line := StyleBoxLine.new()
    line.color = Color(Design.SAGE, .35)
    line.thickness = 1
    divider.add_theme_stylebox_override("separator", line)
    return divider

func _button(label: String, callback: Callable, primary := false,
        role: String = "") -> Button:
    var button := ActionButton.new()
    button.text = label
    button.clip_text = false
    button.set_meta("ui_font_base", 15)
    button.add_theme_font_size_override("font_size", _ui_font(15))
    button.configure(role if not role.is_empty() else "primary" if primary else "secondary")
    var text_width: float = theme.default_font.get_string_size(
        label, HORIZONTAL_ALIGNMENT_LEFT, -1, _ui_font(15)).x
    button.custom_minimum_size = Vector2(
        maxf(96.0, text_width + 48.0 * ui_scale), 38.0 * ui_scale)
    button.pressed.connect(callback)
    return button


func _game_button(button: Button, central := false) -> void:
    # Buttons on the piano stage are instrument controls rather than
    # generic form submissions. Keep a fixed tactile vocabulary.
    button.add_theme_font_size_override("font_size", _ui_font(17 if central else 15))
    var normal := StyleBoxFlat.new()
    var kind: String = str(button.get("action_kind"))
    var role: String = "play" if central else kind
    var accent: Color = Design.role_accent(role)
    normal.bg_color = Design.MINT if central else Design.role_fill(role)
    button.set_meta("ui_button_role",
        "transport_primary" if central else "transport_retry" if kind == "retry" else "transport_listen")
    normal.set_corner_radius_all(7)
    normal.set_content_margin_all(12)
    normal.set_border_width_all(1)
    normal.border_color = Color(accent, .7 if central else .22)
    normal.shadow_color = Color(Design.MINT, .10) if central else Color.TRANSPARENT
    normal.shadow_size = 10 if central else 0
    button.add_theme_stylebox_override("normal", normal)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = normal.bg_color.lightened(.16)
    hover.border_color = accent.lightened(.14)
    hover.shadow_size = 0
    button.add_theme_stylebox_override("hover", hover)
    var pressed := normal.duplicate() as StyleBoxFlat
    pressed.bg_color = normal.bg_color.darkened(.18)
    pressed.shadow_size = 0
    pressed.shadow_offset = Vector2.ZERO
    button.add_theme_stylebox_override("pressed", pressed)
    var disabled := normal.duplicate() as StyleBoxFlat
    disabled.bg_color = Design.PANEL_RECESSED
    disabled.border_color = Color(Design.BORDER, .3)
    disabled.shadow_size = 0
    button.add_theme_stylebox_override("disabled", disabled)
    var focus := normal.duplicate() as StyleBoxFlat
    focus.bg_color = Color.TRANSPARENT
    focus.border_color = Design.FOCUS
    focus.set_border_width_all(2)
    focus.shadow_size = 0
    button.add_theme_stylebox_override("focus", focus)
    if not button is GameTransportButton:
        button.add_theme_color_override("font_color", Color("#F4FFF9") if central else Color("#D6E7DD"))
        button.add_theme_color_override("font_hover_color", Color.WHITE)
        button.add_theme_color_override("font_pressed_color", Color.WHITE)
        button.add_theme_color_override("font_disabled_color", Color("#748B82"))
    button.clip_text = false


func _utility_button(button: Button, destructive := false) -> void:
    if button is ActionButton:
        button.configure("danger" if destructive else "utility")


func _transport_button(label: String, callback: Callable, kind: String, central := false) -> Button:
    var button := GameTransportButton.new()
    button.text = label
    button.clip_text = false
    button.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
    button.pressed.connect(callback)
    button.configure(kind)
    button.custom_minimum_size = Vector2(250 if central else 205, 76 if central else 70)
    _game_button(button, central)
    return button

func _show_listen_volume(db: float) -> void:
    if listen_volume_label != null:
        listen_volume_label.text = "%+d dB" % int(round(db))

func _on_listen_volume_changed(db: float) -> void:
    _show_listen_volume(db)
    if demo_player != null:
        demo_player.call("set_listen_volume_db", db)

func _exit_app() -> void:
    get_tree().quit()

func _screen(name: String) -> MarginContainer:
    var panel := MarginContainer.new()
    panel.name = name
    panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    panel.visible = false
    # Spacing is recomputed from the actual window width in fullscreen mode.
    for side in ["left", "right", "top", "bottom"]:
        panel.add_theme_constant_override("margin_" + side, 24)
    add_child(panel)
    page_margins.append(panel)
    return panel

func _stack(separation: int = 12) -> VBoxContainer:
    var stack := VBoxContainer.new()
    stack.add_theme_constant_override("separation", separation)
    return stack

func _space() -> Control:
    var spacer := Control.new()
    spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return spacer

func _card() -> PanelContainer:
    var panel := PanelContainer.new()
    panel.add_theme_stylebox_override("panel", Design.card_surface())
    return panel

func _card_body(panel: PanelContainer, margin: int = 28) -> MarginContainer:
    var body := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        body.add_theme_constant_override("margin_" + side, margin)
    panel.add_child(body)
    return body

# Music selection, lesson path and settings share a dedicated workspace.
# Opening another view pauses an ongoing attempt
# without discarding the player's place or MIDI assessment.
func _update_visual_frame_rate(state: Dictionary) -> void:
    # An idle screen or paused lesson does not need the same redraw budget
    # as a scrolling score. This never changes Python-owned audio, tempo
    # or MIDI grading, only how often the Godot display is presented.
    var active: bool = (bool(state.get("running", false)) \
        or absf(float(state.get("visual_scroll_speed", 0.0))) > .000001) \
        and not bool(state.get("paused", false)) \
        and current_screen == "practice"
    var target_fps: int = 60 if active else 30
    # Interactive transport retains its full 60 FPS camera. Idle score,
    # settings and library redraw only on user input or changed content.
    OS.low_processor_usage_mode = not active
    if Engine.max_fps != target_fps:
        Engine.max_fps = target_fps


func _navigate(screen: String) -> void:
    var previous_screen: String = current_screen
    if screen == "home":
        screen = "practice" # Old Home is no longer part of normal navigation.
    if screen == "settings" and current_screen != "settings":
        settings_return_screen = current_screen
    if screen != "practice" and current_screen == "practice":
        var phase: String = str(last_state.get("phase", ""))
        var starting: bool = (action_pending and last_post_path == "/control"
            and last_control_action in ["start", "restart", "resume", "score_ready",
            "learn", "learn_retry", "practice", "listen", "perform"])
        if (phase in ["count_in", "playing", "guided_wait", "feedback",
                      "recovering", "loading", "preview_gap"] or starting):
            _send_action({"action": "pause"})
    current_screen = screen
    for destination in screen_navigation:
        screen_navigation[destination].set_selected(destination == screen)
    _update_visual_frame_rate(last_state)
    if overlay_root != null:
        overlay_root.visible = screen != "practice"
        if drawer_intro != null and drawer_intro.is_running():
            drawer_intro.kill()
        if screen != "practice" and previous_screen == "practice":
            # A quick deliberate entrance; no continuously animated glass.
            # Only the drawer fades, not the fullscreen scrim or the score.
            overlay_drawer.modulate.a = 0.0
            drawer_intro = create_tween()
            drawer_intro.tween_property(overlay_drawer, "modulate:a", 1.0, .18) \
                .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
        else:
            overlay_drawer.modulate.a = 1.0
    if pause_sheet != null:
        pause_sheet.present(last_state if screen == "practice" and advanced_pause_open else {})
    for key in screens:
        (screens[key] as Control).visible = (str(key) == screen
            or str(key) == "practice" and screen != "practice")
    if screen == "library":
        _request_library()
        if library_search != null:
            library_search.call_deferred("grab_focus")
    elif screen == "settings":
        tempo_setting.set_value_no_signal(float(last_state.get("target_bpm", 40)))
        _request_settings()
        _request_devices()
    elif screen == "lesson":
        _request_lesson()


func _mount_overlays() -> void:
    # Dedicated music/settings views share a quiet navigation rail. The
    # practice scene remains mounted so returning preserves the exact take.
    overlay_root = Control.new()
    overlay_root.name = "MusicAndSettingsDrawer"
    overlay_root.z_index = 10
    overlay_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(overlay_root)
    overlay_backdrop = ColorRect.new()
    overlay_backdrop.color = Design.NIGHT
    overlay_backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_root.add_child(overlay_backdrop)
    overlay_drawer = PanelContainer.new()
    overlay_drawer.name = "ContextDrawer"
    overlay_drawer.clip_contents = true
    overlay_drawer.add_theme_stylebox_override("panel", Design.bordered_surface(Design.PANEL_RECESSED, 14, .25))
    overlay_root.add_child(overlay_drawer)
    var shell := HBoxContainer.new()
    shell.add_theme_constant_override("separation", 0)
    overlay_drawer.add_child(shell)
    var rail_panel := PanelContainer.new()
    rail_panel.add_theme_stylebox_override("panel", Design.surface(Color(Design.NIGHT, .52), 10))
    shell.add_child(rail_panel)
    navigation_rail = _stack(8)
    navigation_rail.custom_minimum_size.x = 150
    rail_panel.add_child(navigation_rail)
    var brand := _title("Piano\nTeacher", 23)
    brand.custom_minimum_size.y = 100
    navigation_rail.add_child(brand)
    for item in [["library", "Library"], ["lesson", "Lesson path"], ["settings", "Settings"]]:
        var destination: String = item[0]
        var button := _button(item[1], func(): _navigate(destination), false, "choice")
        button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        button.custom_minimum_size.x = 0
        navigation_rail.add_child(button)
        screen_navigation[destination] = button
    var spacer := Control.new()
    spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
    navigation_rail.add_child(spacer)
    navigation_rail.add_child(_button("Practice", func(): _navigate("practice"), true, "primary"))
    var rail_exit := _button("Exit", _exit_app, false, "danger")
    rail_exit.tooltip_text = "Close Piano Teacher (Ctrl+Q)"
    navigation_rail.add_child(rail_exit)
    var pages := Control.new()
    pages.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    pages.size_flags_vertical = Control.SIZE_EXPAND_FILL
    shell.add_child(pages)
    for page in ["library", "settings", "lesson"]:
        var content: Control = screens[page]
        content.reparent(pages, false)
        content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_root.visible = false
    _resize_overlay_drawer()


func _resize_overlay_drawer() -> void:
    if overlay_drawer == null:
        return
    var inset := 18.0 if size.x >= 1100.0 else 8.0
    overlay_drawer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_drawer.offset_left = inset
    overlay_drawer.offset_top = inset
    overlay_drawer.offset_right = -inset
    overlay_drawer.offset_bottom = -inset
    navigation_rail.custom_minimum_size.x = 160.0 if size.x >= 1100.0 else 125.0
    if library_heading != null:
        library_heading.vertical = size.x < 1100.0
        library_message.visible = size.x >= 1100.0 or not library_error.is_empty() \
            or not str(library_info.get("error", "")).is_empty() \
            or library_rows.get_child_count() == 0
        library_path_label.visible = false
        library_search.tooltip_text = library_path_label.text + "\nCtrl+F or / to search"
    if lesson_columns != null:
        lesson_columns.vertical = size.x < 1280.0
        # Compact learners can reach hand/mode choices without scrolling
        # past an entire course; the wide view keeps progression first.
        lesson_columns.move_child(lesson_options, 0 if lesson_columns.vertical else 1)
    if settings_grid != null:
        settings_grid.columns = 2 if size.x >= 1100.0 else 1
    # Folder controls always stack; only their actions wrap horizontally.
    for grid in library_grids:
        grid.columns = 1


func _go_back() -> void:
    _navigate(settings_return_screen if current_screen == "settings" else "practice")

func _build_interface() -> void:
    theme = Design.create()
    theme.default_font_size = _ui_font(16)
    var background := GameBackdrop.new()
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(background)

    # Home: a title, one recent piece and two decisions, with ample whitespace.
    var home := _screen("Home")
    screens["home"] = home
    var home_scroll := ScrollContainer.new()
    home_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    home_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    home.add_child(home_scroll)
    var home_layout := _stack(26)
    home_layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_scroll.add_child(home_layout)
    var home_nav := HBoxContainer.new()
    home_layout.add_child(home_nav)
    home_nav.add_child(_label("Piano Teacher", 24, INK, true))
    home_nav.add_child(_space())
    home_nav.add_child(_button("Settings", func(): _navigate("settings"), false, "settings"))
    home_nav.add_child(_button("Quit", func(): get_tree().quit(), false, "danger"))
    var header := _stack(12)
    home_layout.add_child(header)
    header.add_child(_label("Your practice", 34, INK, true))
    header.add_child(_label("Choose your music or continue your last lesson.", 18, MUTED))
    var home_row := BoxContainer.new()
    home_cards = home_row
    home_row.add_theme_constant_override("separation", 20)
    home_layout.add_child(home_row)
    var library_card := _card()
    library_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_row.add_child(library_card)
    var library_inner := _stack(17)
    _card_body(library_card, 32).add_child(library_inner)
    library_inner.add_child(_label("YOUR MUSIC", 13, MUTED, true))
    home_count_label = _label("Discovering your music…", 25, INK, true)
    library_inner.add_child(home_count_label)
    library_inner.add_child(_label("MIDI and MusicXML from your selected folder", 15, MUTED))
    library_inner.add_child(_button("Browse library  →", func(): _navigate("library"), true))
    var recent_card := _card()
    recent_card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    home_row.add_child(recent_card)
    var recent_inner := _stack(17)
    _card_body(recent_card, 32).add_child(recent_inner)
    recent_inner.add_child(_label("LAST OPENED", 13, MUTED, true))
    home_recent_label = _label("No recent piece", 25, INK, true)
    home_recent_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    home_recent_label.clip_text = true
    home_recent_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    recent_inner.add_child(home_recent_label)
    recent_inner.add_child(_label("Pick up where you left off", 15, MUTED))
    home_resume_button = _button("Continue  →", _resume_last, true)
    recent_inner.add_child(home_resume_button)
    home_layout.add_child(_label("Connect your USB MIDI keyboard and select your music. Progress stays on this computer.", 14, MUTED))

    # Library: automatic indexing without manually opening each MIDI file.
    var library_page := _screen("Library")
    screens["library"] = library_page
    var library_layout := _stack(10)
    library_layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    library_page.add_child(library_layout)
    library_heading = BoxContainer.new()
    library_heading.add_theme_constant_override("separation", 20)
    library_layout.add_child(library_heading)
    var library_intro := _stack(4)
    library_intro.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    library_heading.add_child(library_intro)
    library_intro.add_child(_label("PIANO TEACHER", 14, ACCENT, true))
    library_intro.add_child(_title("Your music", 32))
    library_path_label = _label("Looking for scores…", 13, MUTED)
    library_path_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    library_path_label.clip_text = true
    library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    library_layout.add_child(library_path_label)
    library_search = LineEdit.new()
    library_search.placeholder_text = "Search songs…"
    library_search.clear_button_enabled = true
    library_search.tooltip_text = "Ctrl+F or / to focus search · Esc closes the library"
    library_search.custom_minimum_size = Vector2(220, 40)
    library_search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    # Avoid destroying and recreating every music-row button on every key.
    # The visible search text changes immediately; results settle after the
    # final keystroke without blocking the score renderer.
    library_filter_timer = Timer.new()
    library_filter_timer.one_shot = true
    library_filter_timer.wait_time = .12
    library_filter_timer.timeout.connect(_populate_library)
    add_child(library_filter_timer)
    library_search.text_changed.connect(func(_text: String):
        if library_scroll != null:
            library_scroll.scroll_vertical = 0
        library_filter_timer.start())
    library_heading.add_child(library_search)
    # Shortcuts remain active and discoverable in the search tooltip.
    # A permanent tiny instruction line made the library feel like a form.
    var library_utilities := HBoxContainer.new()
    library_utilities.add_theme_constant_override("separation", 10)
    library_layout.add_child(library_utilities)
    library_utilities.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    library_utilities.add_child(_button("Refresh", _request_library, false, "utility"))
    library_health_button = _button("Check files", func(): _start_library_health(), false, "settings")
    # Dynamic text also says "Checking…" or "Recheck files". Reserve room
    # from the start so the button does not visibly resize or clip.
    library_health_button.custom_minimum_size.x = maxf(
        library_health_button.custom_minimum_size.x,
        _ui_font(15) * 8.3 + 48.0 * ui_scale)
    library_utilities.add_child(library_health_button)
    # Import problems must appear next to the action, not at the very
    # bottom of a full-screen library where they are easy to miss.
    library_message = _label("", 13, MUTED)
    library_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_message.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    library_utilities.add_child(library_message)
    library_health_label = _label("", 16, MUTED)
    library_health_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_health_label.visible = false
    library_layout.add_child(library_health_label)
    var scroll := ScrollContainer.new()
    library_scroll = scroll
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    library_layout.add_child(scroll)
    library_rows = _stack(18)
    library_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(library_rows)
    _build_settings_screen()

    # Practice: standard engraving remains the central and dominant element.
    var practice_page := _screen("Practice")
    screens["practice"] = practice_page
    var practice_layout := _stack(12)
    practice_layout_box = practice_layout
    practice_page.add_child(practice_layout)
    # One compact lesson header. Music occupies the expanding stage below;
    # navigation never gets a separate full-width toolbar of its own.
    practice_header = HBoxContainer.new()
    practice_header.add_theme_constant_override("separation", 20)
    practice_layout.add_child(practice_header)
    var heading := _stack(5)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    heading.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    practice_header.add_child(heading)
    title_label = _title("Choose your music", 26)
    title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(title_label)
    passage_label = _label("A little practice. A little progress.", 14, MUTED)
    passage_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    passage_label.clip_text = true
    passage_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(passage_label)
    var context := _stack(6)
    context.custom_minimum_size.x = 435
    context.size_flags_horizontal = Control.SIZE_SHRINK_END
    practice_header.add_child(context)
    practice_navigation = HFlowContainer.new()
    practice_navigation.alignment = FlowContainer.ALIGNMENT_END
    practice_navigation.add_theme_constant_override("h_separation", 6)
    context.add_child(practice_navigation)
    game_brand = _title("Piano Teacher", 18)
    game_brand.visible = false
    practice_navigation.add_child(game_brand)
    practice_music_button = _button("Music", func(): _navigate("library"), false, "library")
    practice_music_button.tooltip_text = "Choose a piece · Escape"
    practice_navigation.add_child(practice_music_button)
    var path_button := _button("Path", func(): _navigate("lesson"), false, "navigation")
    path_button.tooltip_text = "Learning stages and advanced practice"
    practice_navigation.add_child(path_button)
    practice_settings_button = _button("Settings", func(): _navigate("settings"), false, "settings")
    practice_navigation.add_child(practice_settings_button)
    var details := HBoxContainer.new()
    details.add_theme_constant_override("separation", 14)
    details.alignment = BoxContainer.ALIGNMENT_END
    context.add_child(details)
    speed_label = _label("-- BPM", 14, INK)
    speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    speed_label.size_flags_horizontal = Control.SIZE_SHRINK_END
    details.add_child(speed_label)
    hand_label = _label("", 14, ACCENT)
    hand_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    hand_label.size_flags_horizontal = Control.SIZE_SHRINK_END
    details.add_child(hand_label)
    game_input_indicator = GameInputIndicator.new()
    details.add_child(game_input_indicator)
    mode_choice = OptionButton.new()
    mode_choice.disabled = true
    mode_choice.fit_to_longest_item = false
    for activity_name in ["Learn notes", "Practice rhythm", "Perform passage", "Perform whole piece"]:
        mode_choice.add_item(activity_name)
    mode_choice.item_selected.connect(func(index: int):
        _send_action({"action": "learn" if index == 0 else "practice" if index == 1 else "perform", "scope": "whole" if index == 3 else "current"}))
    hints_toggle = CheckButton.new()
    hints_toggle.text = "Hints"
    hints_toggle.toggled.connect(func(enabled: bool): _send_action({"action": "hints", "enabled": enabled}))
    lesson_info_label = _label("", 14, MUTED)
    lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_stage_bar = HFlowContainer.new()
    practice_stage_bar.add_theme_constant_override("h_separation", 10)
    practice_stage_bar.add_theme_constant_override("v_separation", 6)
    practice_stage_bar.visible = false
    for hand in ["right", "left", "both"]:
        var stage_label := _label("", 12, MUTED)
        stage_label.custom_minimum_size = Vector2(140, 26)
        stage_label.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
        stage_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
        var stage_style := Design.bordered_surface(Design.PANEL_RECESSED, Design.RADIUS_INPUT, .25)
        stage_style.set_content_margin_all(8)
        stage_label.add_theme_stylebox_override("normal", stage_style)
        practice_stage_bar.add_child(stage_label)
        practice_stage_labels[hand] = stage_label
    practice_playback_banner = _label("", 18, Design.AMBER, true)
    practice_playback_banner.visible = false
    practice_playback_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_playback_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
    var score_panel := _card()
    # One continuous performance stage, not another grey website card.
    score_panel.add_theme_stylebox_override("panel", Design.stage_surface())
    practice_score_panel = score_panel
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(score_panel)
    var score_margin := _card_body(score_panel, 10)
    score_margin_box = score_margin
    var score_region := VBoxContainer.new()
    score_region.add_theme_constant_override("separation", 8)
    score_margin.add_child(score_region)
    # Reserve a stable header row so navigation clears high notes and staves.
    var score_header := HBoxContainer.new()
    score_header.alignment = BoxContainer.ALIGNMENT_END
    score_header.add_theme_constant_override("separation", 8)
    score_region.add_child(score_header)
    practice_stage_bar.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_header.add_child(practice_stage_bar)
    fingering_status_label = _label("",12,Design.SECONDARY_INK)
    fingering_status_label.visible = false
    fingering_status_label.clip_text = true
    fingering_status_label.custom_minimum_size.x = 180
    fingering_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    score_header.add_child(fingering_status_label)
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 210)
    score_region.add_child(score_area)
    score_frame = score_area
    score_frame.clip_contents = true
    game_stage = GameStage.new()
    game_stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(game_stage)
    timeline_preview = NativeNotation.new()
    timeline_preview.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    timeline_preview.visible = false
    score_frame.add_child(timeline_preview)
    timeline_preview.fingering_change_requested.connect(_on_fingering_change_requested)
    game_stage.surface_visible = false
    game_stage.z_index = 1
    native_score_feedback = preload("res://native_score_feedback.gd").new()
    native_score_feedback.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(native_score_feedback)
    if not timeline_preview.set_density_from_env():
        push_warning("Native score density: " + str(timeline_preview.notice))
    # Score status must live inside the score panel: feedback_label is replaced
    # by regular state polling and cannot hold engraving errors reliably.
    score_status_panel = CenterContainer.new()
    score_status_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_area.add_child(score_status_panel)
    var status_content := _stack(12)
    status_content.custom_minimum_size = Vector2(280, 85)
    status_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_status_panel.add_child(status_content)
    score_status_label = _label("Choose a piece from your library", 18, Design.SCORE_INK)
    score_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    score_status_label.clip_text = true
    status_content.add_child(score_status_label)
    score_browse_button = _button("Choose music", func(): _navigate("library"), true)
    score_browse_button.visible = true
    status_content.add_child(score_browse_button)
    score_retry_button = _button("Retry score", _retry_score, false, "review")
    score_retry_button.visible = false
    status_content.add_child(score_retry_button)
    # A compact, unobtrusive cue. A huge centred numeral hid the movement.
    game_phase_cue = GamePhaseCue.new()
    game_phase_cue.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    game_phase_cue.offset_left = 178.0
    game_phase_cue.offset_right = -18.0
    game_phase_cue.offset_top = 46.0
    game_phase_cue.offset_bottom = 88.0
    score_frame.add_child(game_phase_cue)
    # Short earned-judgment coaching, placed below the notes on the right.
    # No preview note may create one of these success/correction labels.
    game_impact_callout = GameImpactCallout.new()
    # Native reactions stay on exact noteheads. The legacy coaching card
    # can cover low staff ink when the contextual keyboard reduces height.
    game_impact_callout.visible = false
    game_impact_callout.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    game_impact_callout.offset_left = -264.0
    game_impact_callout.offset_right = -14.0
    game_impact_callout.offset_top = -116.0
    game_impact_callout.offset_bottom = -54.0
    score_frame.add_child(game_impact_callout)
    game_count_in = GameCountIn.new()
    game_count_in.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    game_count_in.position = Vector2(22, 46)
    game_count_in.size = Vector2(142, 38)
    game_count_in.visible = false
    score_frame.add_child(game_count_in)
    # A visible retry notice must not consume vertical space or force the
    # bottom transport buttons off smaller laptop screens.
    practice_playback_banner.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    practice_playback_banner.offset_left = 20.0
    practice_playback_banner.offset_right = -20.0
    practice_playback_banner.offset_top = 54.0
    practice_playback_banner.offset_bottom = 112.0
    score_frame.add_child(practice_playback_banner)
    # A stationary feedback badge stays visible even after a missed note
    # scrolls left out of view. It never covers the playing cursor.
    practice_note_feedback_panel = PanelContainer.new()
    var feedback_style := Design.surface(Color("#27362F"), 9)
    feedback_style.set_border_width_all(2)
    feedback_style.border_color = Color("#ED665F")
    feedback_style.set_content_margin_all(9)
    practice_note_feedback_panel.add_theme_stylebox_override("panel", feedback_style)
    practice_note_feedback_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_note_feedback_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
    practice_note_feedback_panel.offset_left = -330.0
    practice_note_feedback_panel.offset_right = -12.0
    practice_note_feedback_panel.offset_top = 10.0
    practice_note_feedback_panel.offset_bottom = 60.0
    practice_note_feedback_panel.visible = false
    score_frame.add_child(practice_note_feedback_panel)
    practice_note_feedback_label = _label("", 20, Color("#FF827A"), true)
    practice_note_feedback_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_note_feedback_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    practice_note_feedback_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    practice_note_feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_note_feedback_panel.add_child(practice_note_feedback_label)
    hint_keyboard = HintKeyboard.new()
    score_region.add_child(hint_keyboard)
    practice_progress = ProgressBar.new()
    practice_progress.show_percentage = false
    practice_progress.max_value = 1.0
    practice_progress.custom_minimum_size = Vector2(0, 4)
    practice_progress.add_theme_stylebox_override("background", Design.surface(Color("#25443E"), 3))
    practice_progress.add_theme_stylebox_override("fill", Design.surface(Color("#70E5BF"), 3))
    (practice_progress.get_theme_stylebox("background") as StyleBoxFlat).set_content_margin_all(0)
    (practice_progress.get_theme_stylebox("fill") as StyleBoxFlat).set_content_margin_all(0)
    practice_layout.add_child(practice_progress)
    # Progress already appears as a single thin rail *inside* GameStage.
    # A second full-width bar below the notation made this a dashboard.
    practice_progress.visible = false
    var information := VBoxContainer.new()
    information.add_theme_constant_override("separation", 4)
    practice_layout.add_child(information)
    var challenge_bar := HBoxContainer.new()
    challenge_bar.add_theme_constant_override("separation", 18)
    information.add_child(challenge_bar)
    progress_label = _label("", 14, MUTED)
    progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    progress_label.clip_text = true
    progress_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    progress_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    challenge_bar.add_child(progress_label)
    # Keep navigation separate from both notation ink and the progress/tempo
    # row, whose combined minimum width would clip an 800x600 practice window.
    practice_step_controls = HBoxContainer.new()
    practice_step_controls.name = "PracticeStepControls"
    practice_step_controls.size_flags_horizontal = Control.SIZE_SHRINK_END
    practice_step_controls.add_theme_constant_override("separation", 5)
    practice_step_controls.z_index = 6
    score_header.add_child(practice_step_controls)
    practice_step_previous_button = _button("‹", func(): _navigate_practice_step(-1), false, "navigation")
    practice_step_previous_button.custom_minimum_size = Vector2(38, 38)
    practice_step_previous_button.tooltip_text = "Previous lesson step (hand and note level)"
    practice_step_controls.add_child(practice_step_previous_button)
    practice_step_picker = OptionButton.new()
    practice_step_picker.name = "PracticeLessonStepPicker"
    practice_step_picker.custom_minimum_size = Vector2(225, 38)
    practice_step_picker.fit_to_longest_item = false
    practice_step_picker.clip_text = true
    practice_step_picker.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    practice_step_picker.disabled = true
    practice_step_picker.tooltip_text = "Choose any lesson step directly, without earning mastery"
    practice_step_picker.item_selected.connect(_on_practice_step_selected)
    practice_step_controls.add_child(practice_step_picker)
    practice_step_next_button = _button("›", func(): _navigate_practice_step(1), false, "navigation")
    practice_step_next_button.custom_minimum_size = Vector2(38, 38)
    practice_step_next_button.tooltip_text = "Next lesson step (hand and note level)"
    practice_step_controls.add_child(practice_step_next_button)
    tempo_down_button = _button("-5 BPM", func(): _send_action({"action":"tempo_down"}),
        false, "settings")
    tempo_down_button.tooltip_text = "Slow this lesson step without changing its song target"
    challenge_bar.add_child(tempo_down_button)
    tempo_up_button = _button("+5 BPM", func(): _send_action({"action":"tempo_up"}),
        false, "settings")
    tempo_up_button.tooltip_text = "Advance this stage's tempo without changing its target or awarding clean passes"
    tempo_up_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(tempo_up_button)
    game_streak = GameStreak.new()
    challenge_bar.add_child(game_streak)
    # Navigation is deliberately outside the three transport buttons.
    # The progress row directly below the score gives Skip a stable,
    # immediately visible location without changing the control cluster.
    practice_skip_button = _button("Next lesson", _skip_current_lesson,
        false, "navigation")
    practice_skip_button.tooltip_text = "Go to the next lesson without earning mastery"
    practice_skip_button.disabled = true
    practice_skip_button.visible = false
    practice_skip_button.size_flags_horizontal = Control.SIZE_SHRINK_END
    challenge_bar.add_child(practice_skip_button)
    feedback_label = _label("Ready", 14, MUTED)
    feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    feedback_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    information.add_child(_caption_slot(feedback_label, 1))
    information.add_child(_caption_slot(lesson_info_label, 1))
    performance_review = VBoxContainer.new()
    performance_review.visible = false
    information.add_child(performance_review)
    performance_text = _label("", 17, INK)
    performance_review.add_child(performance_text)
    weak_button = _button("Review notes and repeat a section", func():
        if review_sheet != null:
            review_sheet.call("open_review", last_state.get("performance_summary", {})), false, "review")
    performance_review.add_child(weak_button)
    # Flow containers wrap whole readable buttons instead of clipping labels
    # when the practice window is narrow or the user uses larger UI fonts.
    var controls := HFlowContainer.new()
    practice_controls = controls
    controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    controls.alignment = FlowContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("h_separation", 12)
    controls.add_theme_constant_override("v_separation", 8)
    practice_layout.add_child(controls)
    practice_retry_button = _transport_button("Retry", _restart_practice, "retry")
    practice_retry_button.tooltip_text = "Repeat the current passage · R"
    controls.add_child(practice_retry_button)
    start_button = _transport_button("Play", _toggle_playing, "play", true)
    controls.add_child(start_button)
    listen_button = _transport_button("Listen", _listen_or_return_to_practice, "listen")
    listen_button.tooltip_text = "Hear this passage, or return to practice · L"
    controls.add_child(listen_button)
    # Keyboard and Lesson Path retain Stop, passage navigation and mode
    # choices, without competing with the three routine controls.
    stop_button = _button("Stop attempt", func(): _send_action({"action": "stop"}), false, "danger")
    stop_button.tooltip_text = "End the attempt · S"
    stop_button.disabled = true
    _build_lesson_screen()
    _mount_overlays()

    folder_dialog = FileDialog.new()
    folder_dialog.access = FileDialog.ACCESS_FILESYSTEM
    folder_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
    folder_dialog.use_native_dialog = true
    folder_dialog.dir_selected.connect(func(path: String):
        folder_edit.text = path
        _save_folder()
    )
    add_child(folder_dialog)
    # MIDI files can be long. Choose the exact source measure before opening
    # a course stage, rather than forcing the user to skip through passages.
    # Native/embedded ConfirmationDialog geometry was broken under a
    # fullscreen Godot window: its contents were squeezed into a narrow,
    # nearly full-height window, and the music drawer stayed visible behind
    # it. Use one predictable in-stage modal with ordinary Control layout.
    open_picker = Control.new()
    open_picker.name = "StartingMeasureOverlay"
    open_picker.z_index = 20
    open_picker.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    open_picker.mouse_filter = Control.MOUSE_FILTER_STOP
    open_picker.visible = false
    add_child(open_picker)
    var start_scrim := ColorRect.new()
    start_scrim.color = Color("#06110F", .81)
    start_scrim.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    start_scrim.mouse_filter = Control.MOUSE_FILTER_STOP
    start_scrim.gui_input.connect(func(event: InputEvent):
        if event is InputEventMouseButton and event.pressed:
            _cancel_open_picker())
    open_picker.add_child(start_scrim)
    open_panel = PanelContainer.new()
    open_panel.name = "StartingMeasurePanel"
    open_panel.mouse_filter = Control.MOUSE_FILTER_STOP
    # CenterContainer otherwise expands its child to the full viewport:
    # the old bug appeared as a 900px-high, unusable skinny panel.
    open_panel.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
    open_panel.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    open_panel.add_theme_stylebox_override("panel", Design.modal_surface())
    open_picker.add_child(open_panel)
    var start_scroll := ScrollContainer.new()
    start_scroll.name = "StartContentScroll"
    start_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    start_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
    start_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    # Keep primary modal actions outside its scrolling content: in an
    # 800x600 window learners must not scroll to discover Open music/Cancel.
    var picker_column := _stack(10)
    picker_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    picker_column.size_flags_vertical = Control.SIZE_EXPAND_FILL
    _card_body(open_panel, 18).add_child(picker_column)
    picker_column.add_child(start_scroll)
    var start_content := _stack(12)
    start_scroll.add_child(start_content)
    start_content.add_child(_label("CHOOSE A STARTING POINT", 14, ACCENT, true))
    open_title = _label("", 24, INK, true)
    open_title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    start_content.add_child(open_title)
    var start_hint := _label(
        "Start at any measure of this piece.", 16, MUTED)
    start_content.add_child(start_hint)
    start_content.add_child(_label("SOURCE MEASURE", 14, ACCENT, true))
    open_measure = SpinBox.new()
    open_measure.min_value = 1
    open_measure.max_value = 1
    open_measure.step = 1
    open_measure.custom_minimum_size = Vector2(0, 54)
    open_measure.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    open_measure.add_theme_font_size_override("font_size", _ui_font(19))
    start_content.add_child(open_measure)
    open_measure_slider = HSlider.new()
    open_measure_slider.min_value = 1
    open_measure_slider.max_value = 1
    open_measure_slider.step = 1
    open_measure_slider.custom_minimum_size.y = 32
    start_content.add_child(open_measure_slider)
    open_measure.value_changed.connect(func(value: float):
        open_measure_slider.set_value_no_signal(value))
    open_measure_slider.value_changed.connect(func(value: float):
        open_measure.set_value_no_signal(value))
    var source_jumps := HBoxContainer.new()
    source_jumps.name = "SourceMeasureQuickJumps"
    source_jumps.add_theme_constant_override("separation", 10)
    start_content.add_child(source_jumps)
    for kind in ["Beginning", "Middle", "End"]:
        var choice: String = kind
        var jump := _button(kind, func():
            var target := 1 if choice == "Beginning" else (
                int(ceil(open_measure.max_value / 2.0)) if choice == "Middle"
                else int(open_measure.max_value))
            open_measure.value = target, false, "utility")
        jump.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        jump.custom_minimum_size = Vector2(0, 40)
        jump.add_theme_font_size_override("font_size", _ui_font(13))
        source_jumps.add_child(jump)
    start_content.add_child(_label("BEGIN WITH", 14, ACCENT, true))
    open_mode = OptionButton.new()
    open_mode.add_item("Learn notes (without timing)")
    open_mode.add_item("Practice rhythm")
    open_mode.custom_minimum_size.y = 54
    open_mode.add_theme_font_size_override("font_size", _ui_font(16))
    start_content.add_child(open_mode)
    var start_note := _label(
        "Learn starts with notes only. Practice uses the metronome and rhythm.", 14, MUTED)
    start_content.add_child(start_note)
    var start_actions := HBoxContainer.new()
    start_actions.name = "StartPickerActions"
    start_actions.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    start_actions.add_theme_constant_override("separation", 12)
    picker_column.add_child(start_actions)
    var cancel_picker := _button("Cancel", _cancel_open_picker, false, "navigation")
    cancel_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    start_actions.add_child(cancel_picker)
    var confirm_picker := _button("Open music", _confirm_open_picker, true)
    confirm_picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    start_actions.add_child(confirm_picker)
    _resize_open_picker()
    device_menu = PopupMenu.new()
    device_menu.id_pressed.connect(_choose_device)
    add_child(device_menu)
    pause_sheet = preload("res://pause_sheet.gd").new()
    pause_sheet.z_index = 30
    add_child(pause_sheet)
    pause_sheet.chosen.connect(func(command: Dictionary):
        if command.get("action") == "exit":
            _send_action({"action": "stop"})
            _navigate("library")
        else:
            _send_action(command))
    review_sheet = preload("res://review_sheet.gd").new()
    add_child(review_sheet)
    review_sheet.retry_requested.connect(func(first_bar: int, last_bar: int):
        _send_action({"action": "review_retry",
                      "first_bar": first_bar, "last_bar": last_bar}))
    _navigate("practice")
    _refresh_score_status()

func _caption_slot(caption: Label, lines: int) -> Control:
    # Containers must reserve this space even when the phase hides its text.
    # A plain Control prevents wrapped label minimum sizes resizing the score.
    var slot := Control.new()
    slot.name = "FeedbackCaption" if caption == feedback_label else "InstructionCaption"
    slot.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    slot.clip_contents = true
    caption.set_meta("caption_lines", lines)
    caption.max_lines_visible = lines
    caption.mouse_filter = Control.MOUSE_FILTER_PASS
    caption.clip_text = true
    caption.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    caption.autowrap_mode = TextServer.AUTOWRAP_OFF if lines == 1 else TextServer.AUTOWRAP_WORD_SMART
    slot.add_child(caption)
    caption.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    return slot


func _resize_caption_slots() -> void:
    for caption in [feedback_label, lesson_info_label]:
        var lines: int = int(caption.get_meta("caption_lines", 1))
        var font: Font = caption.get_theme_font("font")
        var font_size: int = caption.get_theme_font_size("font_size")
        var line_spacing: int = caption.get_theme_constant("line_spacing")
        caption.get_parent().custom_minimum_size.y = ceilf(
            font.get_height(font_size) * lines + line_spacing * (lines - 1))


func _update_responsive_layout() -> void:
    _configure_ui_scaling()
    ui_scale = _readable_ui_scale()
    theme.default_font_size = _ui_font(16)
    _resize_ui_fonts(self)
    if hint_keyboard != null:
        hint_keyboard.set_ui_scale(ui_scale)
    var width: float = size.x
    var compact: bool = size.y < 750.0
    # Leave sufficient space for score, keyboard, and transport at all sizes.
    # Margins are not multiplied twice by UI scale.
    var margin: int = 26 if width >= 1100.0 else 14
    for panel in page_margins:
        panel.add_theme_constant_override("margin_left", margin)
        panel.add_theme_constant_override("margin_right", margin)
        panel.add_theme_constant_override("margin_top", 14 if compact else 19)
        panel.add_theme_constant_override("margin_bottom", 14 if compact else 19)
    if home_cards != null:
        home_cards.vertical = width < 1380
    _resize_overlay_drawer()
    _resize_open_picker()
    if practice_stage_bar != null:
        _update_hand_stages(last_state)
    if practice_header == null:
        return
    # The reserved score header keeps navigation outside the notation region.
    var compact_steps: bool = width < 1250.0
    progress_label.visible = true
    if practice_step_controls != null:
        var controls_width: float = 350.0 if width < 850.0 else 420.0 if compact_steps else 500.0
        practice_step_controls.custom_minimum_size.x = controls_width
        practice_step_picker.custom_minimum_size.x = 120.0 if width < 850.0 else 150.0 if compact_steps else 180.0
        for arrow in [practice_step_previous_button, practice_step_next_button]:
            arrow.custom_minimum_size.x = 40.0
    for bpm_button in [tempo_down_button, tempo_up_button]:
        bpm_button.custom_minimum_size.x = 84.0 if compact_steps else 100.0
    practice_header.add_theme_constant_override("separation", 10 if width < 950.0 else 20)
    game_brand.visible = false
    practice_navigation.add_theme_constant_override("h_separation", 8 if width >= 1000.0 else 5)
    practice_navigation.add_theme_constant_override("v_separation", 4)
    if mode_choice != null:
        mode_choice.add_theme_font_size_override("font_size", _ui_font(15))
        mode_choice.custom_minimum_size = Vector2(minf(235.0, maxf(170.0, width * 0.22)), 50.0)
    if hints_toggle != null:
        hints_toggle.add_theme_font_size_override("font_size", _ui_font(15))
    for child in practice_navigation.get_children():
        if child is Button and child != mode_choice and child != hints_toggle:
            var button := child as Button
            var font_size := _ui_font(12)
            button.add_theme_font_size_override("font_size", font_size)
            var measured: float = button.get_theme_font("font").get_string_size(
                button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
            # Icon + label still need one accessible, unclipped click target.
            button.custom_minimum_size = Vector2(maxf(78.0, measured + 40.0),
                32.0)
            button.clip_text = false
    if practice_controls != null:
        practice_layout_box.add_theme_constant_override("separation", 6 if compact else 9)
        # The expanding score panel gets all remaining vertical space.
        # A window-relative minimum ignored the keyboard/status heights and
        # pushed the transport below the screen when those became visible.
        score_frame.custom_minimum_size.y = 135.0
        for side in ["left", "right", "top", "bottom"]:
            score_margin_box.add_theme_constant_override("margin_" + side, 1 if compact else 6)
        for child in practice_controls.get_children():
            if child is Button:
                var button := child as Button
                var central: bool = button == start_button
                var font_size := _ui_font(16 if central else 15)
                button.add_theme_font_size_override("font_size", font_size)
                var measured: float = button.get_theme_font("font").get_string_size(
                    button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                var available: float = maxf(0.0, width - float(margin * 2) - 56.0)
                var ideal: float = maxf(180.0 if central else 145.0, measured + 68.0)
                # At 800px all three keys must fit on one row, without
                # shrinking their active hit areas to website-sized chips.
                var per_button: float = maxf(155.0, (available - 48.0) / 3.0)
                button.custom_minimum_size = Vector2(
                    minf(ideal * (1.13 if width >= 1600.0 else 1.0), per_button * (1.18 if central else .91)),
                    54.0)
                button.clip_text = false
        title_label.add_theme_font_size_override("font_size", _ui_font(24))
        passage_label.add_theme_font_size_override("font_size", _ui_font(15))
        speed_label.add_theme_font_size_override("font_size", _ui_font(14))
        hand_label.add_theme_font_size_override("font_size", _ui_font(14))
        progress_label.add_theme_font_size_override("font_size", _ui_font(15))
        game_streak.custom_minimum_size = Vector2(130 if width < 950 else 155, 30)
        game_input_indicator.custom_minimum_size.y = 22
        feedback_label.add_theme_font_size_override("font_size", _ui_font(14))
        lesson_info_label.add_theme_font_size_override("font_size", _ui_font(14))
        var instruction_lines := 2 if width < 1000.0 else 1
        lesson_info_label.set_meta("caption_lines", instruction_lines)
        lesson_info_label.max_lines_visible = instruction_lines
        lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART if instruction_lines == 2 else TextServer.AUTOWRAP_OFF
        _resize_caption_slots()
        practice_playback_banner.add_theme_font_size_override("font_size", _ui_font(17))
        practice_note_feedback_label.add_theme_font_size_override("font_size", _ui_font(18))
        practice_note_feedback_panel.offset_left = - minf(330.0, maxf(180.0, score_frame.size.x - 24.0))

func _build_settings_screen() -> void:
    var page := _screen("Settings")
    screens["settings"] = page
    var scroll := ScrollContainer.new()
    scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    page.add_child(scroll)
    var content := _stack(20)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(content)
    content.add_child(_label("PIANO & PREFERENCES", 14, ACCENT, true))
    content.add_child(_title("Your piano & practice", 32))

    settings_grid = GridContainer.new()
    settings_grid.columns = 2 if size.x >= 1100.0 else 1
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
    device_button = _button("Choose USB MIDI piano", _show_devices, false, "settings")
    device_row.add_child(device_button)
    device_row.add_child(_button("Refresh devices", _request_devices, false, "utility"))
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
    folder_edit.text_submitted.connect(func(_text: String): _save_folder())
    folder_controls.add_child(folder_edit)
    var folder_actions := HFlowContainer.new()
    folder_actions.add_theme_constant_override("h_separation", 10)
    folder_actions.add_theme_constant_override("v_separation", 6)
    folder_controls.add_child(folder_actions)
    folder_actions.add_child(_button("Choose folder…", _browse_folder, false, "navigation"))
    folder_actions.add_child(_button("Save folder", _save_folder, false, "secondary"))
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
    apply_tempo_button = _button("Apply tempo", func(): _send_action({"action": "tempo", "bpm": int(tempo_setting.value)}), false, "settings")
    tempo_row.add_child(apply_tempo_button)
    metronome_toggle = CheckButton.new()
    metronome_toggle.text = "Metronome during practice"
    metronome_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    metronome_toggle.tooltip_text = "Count-in is always audible, even when metronome is off"
    metronome_toggle.toggled.connect(func(enabled: bool): _send_post("/settings", {"metronome": enabled}))
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
    listen_volume_slider.value_changed.connect(_on_listen_volume_changed)
    fullscreen_toggle = CheckButton.new()
    fullscreen_toggle.text = "Fullscreen application  ·  F11"
    fullscreen_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    fullscreen_toggle.button_pressed = true
    fullscreen_toggle.toggled.connect(_on_fullscreen_toggle)
    audio.add_child(fullscreen_toggle)
    var exit_button := _button("Exit application", _exit_app, false, "utility")
    exit_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    content.add_child(exit_button)
    settings_message = _label("", 14, MUTED)
    content.add_child(settings_message)


func _build_lesson_screen() -> void:
    var page := _screen("Lesson")
    screens["lesson"] = page
    # Wrap the entire lesson content in a ScrollContainer so all controls
    # remain accessible on short laptop viewports (mirrors settings screen).
    var outer_scroll := ScrollContainer.new()
    outer_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    outer_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    outer_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    page.add_child(outer_scroll)
    var content := _stack(14)
    content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    outer_scroll.add_child(content)
    content.add_child(_label("YOUR NEXT STEPS", 14, ACCENT, true))
    content.add_child(_title("Lesson path", 32))
    lesson_piece_title = _title("Choose music to begin", 25)
    content.add_child(lesson_piece_title)
    var stages := HBoxContainer.new()
    stages.add_theme_constant_override("separation", 0)
    content.add_child(stages)
    for stage in ["skeleton", "outline", "original"]:
        var label := _label("%d. %s" % [lesson_stage_labels.size() + 1, stage.capitalize()], 15, MUTED)
        label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
        label.tooltip_text = "The current simplification level; available stages depend on this passage."
        label.visible = false
        stages.add_child(label)
        lesson_stage_labels[stage] = label
    lesson_summary = _label("Open a piece to see its lessons.", 15, MUTED)
    content.add_child(lesson_summary)
    lesson_description = _label("", 14, MUTED)
    content.add_child(lesson_description)
    lesson_columns = BoxContainer.new()
    lesson_columns.vertical = size.x < 1280.0
    lesson_columns.add_theme_constant_override("separation", 24)
    content.add_child(lesson_columns)
    lesson_rows = _stack(10)
    lesson_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    lesson_rows.size_flags_stretch_ratio = 1.15
    lesson_columns.add_child(lesson_rows)
    var options_panel := _card()
    lesson_options = options_panel
    options_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    options_panel.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
    lesson_columns.add_child(options_panel)
    var path_options := _stack(14)
    _card_body(options_panel, 18).add_child(path_options)
    path_options.add_child(_label("Practice choices", 17, INK, true))
    # FlowContainer inside an expanding, vertically scrolling VBox can
    # calculate a near-zero width for its Label during a resize. The label
    # then wraps to one letter per line and forces the entire activity
    # section (including OptionButton) to become hundreds of pixels tall.
    # These three small controls fit in a single bounded horizontal row.
    var activity := HBoxContainer.new()
    activity.name = "LessonActivityRow"
    activity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    activity.add_theme_constant_override("separation", 14)
    path_options.add_child(activity)
    var activity_caption := _label("Activity", 17, MUTED)
    activity_caption.name = "LessonActivityCaption"
    activity_caption.autowrap_mode = TextServer.AUTOWRAP_OFF
    activity_caption.custom_minimum_size.x = 90
    activity_caption.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    activity_caption.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(activity_caption)
    mode_choice.custom_minimum_size = Vector2(210, 44)
    mode_choice.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    mode_choice.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(mode_choice)
    hints_toggle.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    hints_toggle.size_flags_vertical = Control.SIZE_SHRINK_CENTER
    activity.add_child(hints_toggle)
    var passage_nav := HFlowContainer.new()
    passage_nav.add_theme_constant_override("h_separation", 10)
    path_options.add_child(passage_nav)
    passage_nav.add_child(_button("Previous passage", func():
        _send_action({"action": "previous"})
        _navigate("practice"), false, "navigation"))
    passage_nav.add_child(_button("Next passage", func():
        _send_action({"action": "next"})
        _navigate("practice"), false, "navigation"))
    passage_nav.add_child(stop_button)
    var hand_row := HFlowContainer.new()
    hand_row.add_theme_constant_override("separation", 12)
    path_options.add_child(hand_row)
    for hand in ["right", "left", "both"]:
        var button := _button(hand.capitalize() + (" hands" if hand == "both" else " hand"),
            func():
                _send_action({"action": "hand", "hand": hand})
                _navigate("practice")
        )
        button.configure("choice")
        hand_buttons[hand] = button
        hand_row.add_child(button)
    var course_choices := HFlowContainer.new()
    course_choices.add_theme_constant_override("separation", 8)
    path_options.add_child(course_choices)
    skip_stage_button = _button("Skip this step · no mastery", func(): _send_action({"action": "skip_stage", "reason": "Learner chose to skip this step"}), false, "review")
    skip_stage_button.custom_minimum_size.x = 220
    course_choices.add_child(skip_stage_button)
    placement_button = _button("Try original notes", func(): _send_action({"action": "place_original"}), false, "primary")
    course_choices.add_child(placement_button)
    # The outer scroll owns the whole path. A nested expanding ScrollContainer
    # has zero minimum height inside it, hiding every lesson stage.
    var advanced := _button("Advanced practice controls", _open_advanced_pause, false, "settings")
    advanced.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    path_options.add_child(advanced)
    # Reset lives in the full Lesson Path drawer, not alongside the three
    # everyday Play / Retry / Listen buttons. It requires a second click.
    path_reset_button = _button("Reset this song's lesson path…",
        _show_path_reset_confirmation, false, "danger")
    path_reset_button.disabled = true
    path_reset_button.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
    path_reset_button.tooltip_text = "Erase saved mastery, tempo, skipped steps and trouble spots for this song only"
    path_options.add_child(path_reset_button)
    path_reset_confirmation = _stack(8)
    path_reset_confirmation.name = "ResetPathConfirmation"
    path_reset_confirmation.visible = false
    path_options.add_child(path_reset_confirmation)
    var reset_warning := _label(
        "Reset this song to step 1? All saved tempos, mastery, completed notes and skipped steps for this song will be erased. Other songs are unaffected.",
        15, INK)
    reset_warning.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    path_reset_confirmation.add_child(reset_warning)
    var reset_actions := HFlowContainer.new()
    reset_actions.add_theme_constant_override("h_separation", 10)
    path_reset_confirmation.add_child(reset_actions)
    reset_actions.add_child(_button("Cancel", _cancel_path_reset, false, "navigation"))
    reset_actions.add_child(_button("Erase this song's progress", _confirm_path_reset,
        false, "danger"))

func _show_path_reset_confirmation() -> void:
    if action_pending or not bool(last_state.get("loaded", false)):
        return
    path_reset_fingerprint = str(last_state.get("piece_fingerprint", ""))
    path_reset_confirmation.visible = not path_reset_fingerprint.is_empty()

func _cancel_path_reset() -> void:
    path_reset_confirmation.visible = false
    path_reset_fingerprint = ""

func _confirm_path_reset() -> void:
    var current: String = str(last_state.get("piece_fingerprint", ""))
    if action_pending or path_reset_fingerprint.is_empty() or path_reset_fingerprint != current:
        _cancel_path_reset()
        return
    _send_action({"action": "reset_path", "fingerprint": current, "confirm": true})
    _cancel_path_reset()

func _navigate_practice_step(offset: int) -> void:
    var target: int = int(last_state.get("lesson_step", 0)) + offset
    if target >= 1 and target <= practice_step_entries.size() and not action_pending:
        _send_action({"action": "select_step", "number": target})


func _on_practice_step_selected(index: int) -> void:
    var number: int = index + 1
    if number != int(last_state.get("lesson_step", 0)) and not action_pending:
        _send_action({"action": "select_step", "number": number})


func _sync_practice_step_navigation(state: Dictionary) -> void:
    if practice_step_picker == null:
        return
    var loaded: bool = bool(state.get("loaded", false))
    var fingerprint: String = str(state.get("piece_fingerprint", ""))
    if not loaded:
        practice_step_picker.clear()
        practice_step_entries.clear()
        lesson_choice_fingerprint = ""
        lesson_requested_fingerprint = ""
    elif fingerprint != lesson_choice_fingerprint and fingerprint != lesson_requested_fingerprint and not lesson_pending:
        _request_lesson()
    var ready: bool = loaded and fingerprint == lesson_choice_fingerprint and not practice_step_entries.is_empty()
    var current: int = int(state.get("lesson_step", 0))
    practice_step_picker.disabled = action_pending or not ready
    practice_step_previous_button.disabled = action_pending or not ready or current <= 1
    practice_step_next_button.disabled = action_pending or not ready or current >= practice_step_entries.size()
    if ready and current >= 1 and current <= practice_step_picker.item_count:
        if practice_step_picker.selected != current - 1:
            practice_step_picker.select(current - 1)
        # The popup has the complete hand/measure/variant descriptions;
        # only the selected caption is shortened to avoid widening Practice.
        practice_step_picker.text = "Step %d / %d" % [current, practice_step_entries.size()]


func _request_lesson() -> void:
    if lesson_request == null or lesson_pending or not bool(last_state.get("loaded", false)):
        return
    lesson_pending = true
    if lesson_request.request(URL + "/lesson") != OK:
        lesson_pending = false
    else:
        lesson_requested_fingerprint = str(last_state.get("piece_fingerprint", ""))

func _on_lesson(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    lesson_pending = false
    if lesson_refresh_after_reset:
        # Discard the response of a request started before the reset. It
        # carries the same piece fingerprint but obsolete mastery flags.
        lesson_refresh_after_reset = false
        _request_lesson()
        return
    if code != 200:
        lesson_summary.text = _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    var fingerprint: String = str(parsed.get("piece_fingerprint", ""))
    if fingerprint != str(last_state.get("piece_fingerprint", "")):
        return # A stale response from music that has already been replaced.
    lesson_choice_fingerprint = fingerprint
    practice_step_entries = parsed.get("steps", []).duplicate(true)
    practice_step_picker.clear()
    for step in practice_step_entries:
        var number: int = int(step.get("number", 0))
        var caption: String = "%d/%d · %d–%d · %s · %s" % [
            number, practice_step_entries.size(),
            int(step.get("first_bar", 1)), int(step.get("last_bar", 1)),
            str(step.get("hand", "")).capitalize(), str(step.get("level", "")).capitalize()]
        practice_step_picker.add_item(caption)
    _sync_practice_step_navigation(last_state)
    lesson_piece_title.text = str(last_state.get("title", "Your music")).replace("_", " ")
    var available: Array = []
    var current: Dictionary = {}
    for step in parsed.get("steps", []):
        if int(step.get("number", -1)) == int(parsed.get("current_step", 0)):
            current = step
            break
    for step in parsed.get("steps", []):
        if step.get("exercise") == current.get("exercise") and step.get("hand") == current.get("hand") \
                and not available.has(str(step.get("level", ""))):
            available.append(str(step.get("level", "")))
    var visible_number := 0
    for level in lesson_stage_labels:
        var label: Label = lesson_stage_labels[level]
        label.visible = available.has(level)
        if label.visible:
            visible_number += 1
            label.text = "%d. %s" % [visible_number, str(level).capitalize()]
        var selected: bool = str(last_state.get("lesson_level", "")) == level
        label.add_theme_color_override("font_color", INK if selected else MUTED)
        var face := Design.bordered_surface(Design.PINE if selected else Design.PANEL_RECESSED, 6, .6 if selected else .25)
        face.border_color = Design.TEAL if selected else Color(Design.SAGE, .3)
        label.add_theme_stylebox_override("normal", face)
    lesson_summary.text = "%d of %d stages completed · %d clean performances at your target tempo" % [
        int(parsed.get("completed_steps", 0)), int(parsed.get("total_steps", 0)),
        int(last_state.get("clean_runs_required", 3))]
    lesson_description.text = "Learn the notes. Bring the hands together. Make it music."
    for child in lesson_rows.get_children():
        lesson_rows.remove_child(child)
        child.queue_free()
    var trouble: Array = parsed.get("trouble_spots", [])
    if not trouble.is_empty():
        lesson_rows.add_child(_label("Your trouble spots", 18, INK, true))
        for spot in trouble:
            var stage_key: String = str(spot.get("stage_key", ""))
            var from_beat: float = float(spot.get("start_beat", 0))
            var revisit := _button("Revisit bars %d–%d" % [int(spot.get("first_bar", 1)), int(spot.get("last_bar", 1))],
                func(): _send_action({"action": "revisit_trouble", "stage_key": stage_key, "start_beat": from_beat}))
            revisit.call("configure", "review")
            revisit.tooltip_text = "Find these notes again, then return to rhythm practice"
            lesson_rows.add_child(revisit)
    var groups: Dictionary = {}
    for step in parsed.get("steps", []):
        var key := str(step.get("exercise", 0))
        if not groups.has(key):
            groups[key] = {"first": step.get("first_bar", 0), "last": step.get("last_bar", 0),
                "kind": str(step.get("kind", "learn")), "labels": [], "complete": true, "current": false}
        var group: Dictionary = groups[key]
        group["complete"] = bool(group["complete"]) and bool(step.get("completed", false))
        group["current"] = bool(group["current"]) or int(step.get("number", 0)) == int(parsed.get("current_step", 0))
        var detail := "%s: %s" % [str(step.get("hand", "")).capitalize(), str(step.get("level", "")).capitalize()]
        if str(step.get("skip_status", "active")) in ["skipped", "placed"] and not bool(step.get("completed", false)):
            detail += " (%s; not mastered)" % str(step["skip_status"])
        group["labels"].append(detail)
    for key in groups:
        var group: Dictionary = groups[key]
        var chapter := PanelContainer.new()
        var chapter_style := Design.surface(Color(Design.PINE,.32) if bool(group["current"]) else Color.TRANSPARENT, 6)
        chapter_style.set_content_margin_all(14)
        chapter_style.set_border_width(SIDE_LEFT, 3 if bool(group["current"]) else 1)
        chapter_style.border_color = ACCENT if bool(group["current"]) else Color(Design.SAGE,.3)
        chapter.add_theme_stylebox_override("panel", chapter_style)
        var row := _stack(4)
        chapter.add_child(row)
        var status := "Completed" if bool(group["complete"]) else "Current passage" if bool(group["current"]) else str(group["kind"]).capitalize()
        row.add_child(_label("%s · Measures %d–%d" % [status, int(group["first"]), int(group["last"])], 18,
            ACCENT if bool(group["current"]) else INK, bool(group["current"])))
        var detail: String = " → ".join(group["labels"])
        row.tooltip_text = detail
        if bool(group["current"]):
            row.add_child(_label(detail, 14, MUTED))
        lesson_rows.add_child(chapter)

func _refresh_score_status() -> void:
    if score_status_panel == null:
        return
    score_status_panel.visible = not _native_score_ready()
    # Phase guidance already has captions below the score and count-in
    # lights. An opaque capsule must never cover engraved noteheads.
    game_phase_cue.visible = score_status_panel.visible
    if not score_status_panel.visible:
        return
    if not score_error.is_empty():
        score_status_label.text = "Unable to display sheet music:\n" + score_error
        score_retry_button.visible = true
        score_browse_button.visible = false
    elif bool(last_state.get("loaded", false)):
        score_status_label.text = "Preparing sheet music…"
        score_retry_button.visible = false
        score_browse_button.visible = false
    else:
        score_status_label.text = "Choose a piece to begin"
        score_retry_button.visible = false
        score_browse_button.visible = true

func _score_failed(message: String) -> void:
    if phase0_smoke_mode:
        print("PHASE0_SCORE_ERROR:", message)
    score_error = message
    rendered_revision = -1
    timeline_model_revision = -1
    if timeline_preview != null:
        timeline_preview.clear_score()
        timeline_preview.visible = false
    if native_score_feedback != null:
        native_score_feedback.bind_score(timeline_preview, -1)
    start_button.disabled = true
    practice_retry_button.disabled = true
    feedback_label.text = message
    _refresh_score_status()

func _retry_score() -> void:
    if not bool(last_state.get("loaded", false)) or layout_pending:
        return
    score_error = ""
    score_layout = {}
    layout_revision = -1
    rendered_revision = -1
    timeline_model_revision = -1
    timeline_preview.clear_score()
    timeline_preview.visible = false
    _refresh_score_status()
    _request_layout()

func _request_library() -> void:
    if library_pending or library_request == null:
        return
    library_pending = true
    if library_request.request(URL + "/library") != OK:
        library_pending = false

func _on_library(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    library_pending = false
    if code != 200:
        library_message.text = _http_failure(code, body)
        home_count_label.text = "Practice engine unavailable"
        home_resume_button.disabled = true
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    library_info = parsed
    home_count_label.text = "%d scores · %d built-in warm-ups" % [int(parsed.get("count", 0)), parsed.get("warmups", []).size()]
    library_path_label.text = str(parsed.get("folder", ""))
    _populate_library()
    _request_library_health()
    var recent: String = str(parsed.get("last_piece", ""))
    home_resume_button.disabled = recent.is_empty()
    var exists_in_library := false
    for entry in parsed.get("warmups", []) + parsed.get("pieces", []):
        if str(entry.get("id", "")) == recent:
            exists_in_library = true
            break
    home_resume_button.disabled = not exists_in_library
    var recent_title := recent.get_file().get_basename().replace("_", " ")
    for entry in parsed.get("warmups", []):
        if str(entry.get("id", "")) == recent:
            recent_title = str(entry.get("title", recent_title))
            break
    home_recent_label.text = recent_title if not recent.is_empty() else "No recent piece"

func _request_library_health() -> void:
    if library_health_request == null or library_health_pending:
        return
    library_health_pending = true
    if library_health_request.request(URL + "/library/health") != OK:
        library_health_pending = false


func _start_library_health() -> void:
    if action_pending or bool(library_health_info.get("running", false)):
        return
    library_health_label.visible = true
    library_health_label.text = "Starting music file check…"
    _send_post("/library/health", {})


func _on_library_health(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    library_health_pending = false
    if code != 200:
        library_health_label.visible = true
        library_health_label.text = "Cannot check music files: " + _http_failure(code, body)
        return
    var parsed: Variant = _decode_json(body)
    if not parsed is Dictionary:
        return
    var previous_started: bool = bool(library_health_info.get("started", false))
    var previous_running: bool = bool(library_health_info.get("running", false))
    library_health_info = parsed
    var active: bool = bool(parsed.get("running", false))
    var started: bool = bool(parsed.get("started", false))
    library_health_button.disabled = active
    library_health_button.text = "Checking…" if active else "Recheck files" if started else "Check files"
    library_health_label.visible = started
    if started:
        library_health_label.text = (
            "Checking %d of %d files · %d OK · %d repaired · %d errors" if active
            else "File check complete: %d of %d · %d OK · %d repaired · %d errors"
        ) % [int(parsed.get("checked", 0)), int(parsed.get("total", 0)),
             int(parsed.get("ok", 0)), int(parsed.get("warning", 0)), int(parsed.get("error", 0))]
        if not str(parsed.get("message", "")).is_empty():
            library_health_label.text += "\n" + str(parsed["message"])
    # A large music collection may scan hundreds of files. Rebuilding
    # every clickable row at each file-progress tick caused visible drawer
    # flicker, lost keyboard focus and expensive Godot allocations. Keep
    # updating the small progress label; rebuild row statuses only at start
    # and once when the scan finishes.
    if previous_started != started or (previous_running and not active):
        _populate_library()


func _last_library_entry() -> Dictionary:
    var identifier: String = str(library_info.get("last_piece", ""))
    if not identifier.is_empty():
        for entry in library_info.get("warmups", []) + library_info.get("pieces", []):
            if str(entry.get("id", "")) == identifier:
                return entry
    return {}


func _populate_library() -> void:
    if library_rows == null:
        return
    if library_filter_timer != null and not library_filter_timer.is_stopped():
        library_filter_timer.stop()
    for child in library_rows.get_children():
        library_rows.remove_child(child)
        child.queue_free()
    library_grids.clear()
    var pieces: Array = library_info.get("pieces", [])
    var warmups: Array = library_info.get("warmups", [])
    var query := library_search.text.strip_edges().to_lower()
    var visible := 0
    var recent: Dictionary = _last_library_entry()
    var show_recent: bool = query.is_empty() and not recent.is_empty()
    var sections: Array = []
    if show_recent:
        sections.append({"title": "LAST OPENED", "entries": [recent], "resume": true})
    sections.append({"title": "YOUR MUSIC", "entries": pieces})
    sections.append({"title": "BUILT-IN WARM-UPS", "entries": warmups})
    for section in sections:
        var section_added := false
        var grid: GridContainer
        for entry in section.entries:
            var identifier: String = str(entry.get("id", ""))
            var resume_saved: bool = bool(section.get("resume", false))
            if show_recent and not resume_saved and identifier == str(recent.get("id", "")):
                continue
            var title: String = str(entry.get("title", "Untitled"))
            var location: String = str(entry.get("folder", ""))
            var focus: String = str(entry.get("focus", ""))
            if not query.is_empty() and not (title + " " + location + " " + focus).to_lower().contains(query):
                continue
            if not section_added:
                library_rows.add_child(_label(str(section.title).capitalize(), 15, MUTED, true))
                grid = GridContainer.new()
                grid.columns = 1
                grid.add_theme_constant_override("h_separation", 12)
                grid.add_theme_constant_override("v_separation", 12)
                grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
                library_rows.add_child(grid)
                library_grids.append(grid)
                section_added = true
            var format_name: String = str(entry.get("format", ""))
            var hint: String = ("%d BPM · %s" % [int(entry.get("bpm", 0)), focus]
                if not focus.is_empty() else
                location if not location.is_empty() else "Music folder")
            var diagnosis: Dictionary = library_health_info.get("items", {}).get(identifier, {})
            var status: String = str(diagnosis.get("status", ""))
            var detail: String = format_name + "  ·  " + hint
            if status == "error":
                detail = "Needs attention  ·  " + detail
            elif status == "warning":
                detail = "Repaired  ·  " + detail
            if resume_saved:
                detail = "Continue from saved place  ·  " + detail
            var row := LibraryRow.new()
            if resume_saved:
                row.pressed.connect(_resume_last)
            else:
                row.pressed.connect(func(): _open_library_piece(identifier))
            grid.add_child(row)
            row.set_entry(title.replace("_", " "), detail, status)
            row.set_text_scale(ui_scale)
            if entry.has("description"):
                row.tooltip_text += "\n" + str(entry["description"])
            if not diagnosis.is_empty():
                row.tooltip_text += "\nImport check: " + str(diagnosis.get("message", ""))
                if status != "error":
                    row.tooltip_text += " · %d notes · %d measures" % [
                        int(diagnosis.get("notes", 0)), int(diagnosis.get("measures", 0))]
            visible += 1
    var issue: String = str(library_info.get("error", ""))
    if not library_error.is_empty():
        library_message.text = library_error
        library_message.add_theme_color_override("font_color", Color("#FF8B82"))
    elif not issue.is_empty():
        library_message.text = issue
    elif pieces.is_empty() and warmups.is_empty():
        library_message.text = "No scores yet. Add .mid, .midi or MusicXML files to this folder."
    elif visible == 0:
        library_message.text = "No matches for “%s”. Try another title or clear the search." % library_search.text.strip_edges()
    else:
        library_message.text = "%d personal files  ·  %d built-in warm-ups  ·  %d shown" % [pieces.size(), warmups.size(), visible]
    if library_error.is_empty():
        library_message.add_theme_color_override("font_color", MUTED)
    library_message.visible = size.x >= 1100.0 or not library_error.is_empty() \
        or not issue.is_empty() or visible == 0

func _resize_open_picker() -> void:
    if open_panel == null:
        return
    # Centered from the actual viewport. Never a 240px-wide, 900px-tall
    # native subwindow, including fullscreen and high-density displays.
    var width: float = minf(620.0, maxf(280.0, size.x - 36.0))
    # The PanelContainer is positioned directly under the full-screen
    # overlay, NOT under a CenterContainer that might expand it vertically.
    # The scroll area handles short laptop windows without hiding Cancel.
    var height: float = minf(570.0, size.y * .84)
    open_panel.custom_minimum_size = Vector2(width, 0)
    open_panel.size = Vector2(width, height)
    open_panel.position = (size - open_panel.size) * .5


func _cancel_open_picker() -> void:
    open_picker.visible = false
    _navigate("library")


func _confirm_open_picker() -> void:
    if action_pending or not open_picker.visible:
        return
    # Godot sends _input() before a SpinBox's embedded LineEdit commits its
    # pending digits. Honor the value the learner actually typed on Enter.
    if get_viewport().gui_get_focus_owner() == open_measure.get_line_edit():
        open_measure.value = clampi(
            open_measure.get_line_edit().text.to_int(), 1,
            int(open_measure.max_value))
    open_picker.visible = false
    _navigate("practice")
    _send_action({"action": "open_at", "bar": int(open_measure.value),
        "mode": "practice" if open_mode.selected == 1 else "learn"})


func _show_open_picker(state: Dictionary) -> void:
    # Opening metadata is source-based and does not require Verovio rendering
    # or a connected MIDI piano. Do not start the first guided lesson yet.
    var last_bar: int = maxi(1, int(state.get("piece_last_bar", 1)))
    open_title.text = str(state.get("title", "Untitled piece")).replace("_", " ")
    open_measure.max_value = last_bar
    open_measure.min_value = 1
    open_measure.value = clampi(int(state.get("selected_start_bar", 1)), 1, last_bar)
    open_measure.suffix = " / %d" % last_bar
    open_measure_slider.max_value = last_bar
    open_measure_slider.min_value = 1
    open_measure_slider.set_value_no_signal(open_measure.value)
    open_mode.select(0)
    # Close the music drawer before presenting the modal. A picker over an
    # open drawer had two active layers and unreadable, overlapping controls.
    _navigate("practice")
    _resize_open_picker()
    open_picker.visible = true
    if picker_intro != null and picker_intro.is_running():
        picker_intro.kill()
    open_panel.modulate.a = 0.0
    picker_intro = create_tween()
    picker_intro.tween_property(open_panel, "modulate:a", 1.0, .18) \
        .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
    open_measure.get_line_edit().grab_focus()


func _update_hand_stages(state: Dictionary) -> void:
    var stages: Array = state.get("hand_stages", [])
    # Transport changes must not add/remove a layout row: doing so changes
    # the score's zoom and moves its notes at Start and Pause.
    practice_stage_bar.visible = not stages.is_empty()
    if stages == presented_hand_stages:
        return
    presented_hand_stages = stages.duplicate(true)
    var by_hand: Dictionary = {}
    for stage in stages:
        by_hand[str(stage.get("hand", ""))] = stage
    for hand in practice_stage_labels:
        var label: Label = practice_stage_labels[hand]
        label.visible = by_hand.has(hand)
        if not label.visible:
            continue
        var stage: Dictionary = by_hand[hand]
        var active: bool = bool(stage.get("active", false))
        var complete: bool = bool(stage.get("complete", false))
        var locked: bool = bool(stage.get("locked", false))
        var word: String = "Both hands" if hand == "both" else str(hand).capitalize() + " hand"
        label.autowrap_mode = TextServer.AUTOWRAP_OFF
        label.clip_text = true
        label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
        label.text = ("✓ " if complete else "● " if active else "○ ") + word + (" · locked" if locked else "")
        label.tooltip_text = "Completed" if complete else "Active hand" if active else "Locked" if locked else "Next hand"
        label.custom_minimum_size = Vector2(102 if size.x < 1150.0 else 122, 24)
        label.add_theme_color_override("font_color",
            Color("#79DAAD") if complete else INK if active else MUTED)
        # Read as a three-step instrument runway, not three separate
        # web-form cards. The active hand has a bright lower edge; completed
        # hands retain a quieter mint trace, and locked ones recede.
        var stage_color := Color(Design.PINE, .45) if active else Color.TRANSPARENT
        var style := Design.surface(stage_color, 5)
        style.set_content_margin_all(5)
        style.set_border_width_all(0)
        style.set_border_width(SIDE_BOTTOM, 1)
        style.border_color = Design.TEAL if active else Color(Design.SAGE, .3)
        label.add_theme_stylebox_override("normal", style)


# Animate the newly active hand without extra buttons or a separate
# modal. Deferred until the backend-driven hand-stage labels are updated.
func _pulse_hand_stage() -> void:
    var hand: String = str(last_state.get("hand", ""))
    if not practice_stage_labels.has(hand):
        return
    var label: Label = practice_stage_labels[hand]
    if not label.visible:
        return
    label.modulate = Color("#A6FFE0")
    var transition := create_tween()
    transition.tween_property(label, "modulate", Color.WHITE, .68) \
        .set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)


func _open_library_piece(identifier: String, resume_saved := false) -> void:
    # Pause requests are asynchronous. Store a quick selection and open it
    # once the transport has acknowledged the pause, rather than dropping
    # the click while action_pending is true.
    if action_pending:
        pending_library_piece = identifier
        pending_library_resume = resume_saved
        library_message.text = "Preparing your selected music…"
        return
    library_error = ""
    library_message.text = "Opening score…"
    library_message.add_theme_color_override("font_color", MUTED)
    library_resume_requested = resume_saved
    _send_post("/library/open", {"id": identifier})

func _resume_last() -> void:
    var recent: Dictionary = _last_library_entry()
    if not recent.is_empty():
        _open_library_piece(str(recent["id"]), true)

func _request_settings() -> void:
    if settings_pending or settings_request == null:
        return
    settings_pending = true
    if settings_request.request(URL + "/settings") != OK:
        settings_pending = false

func _on_settings(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    settings_pending = false
    if code != 200:
        settings_message.text = _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    preferences = parsed
    folder_edit.text = str(preferences.get("music_dir", ""))
    fullscreen_toggle.set_pressed_no_signal(bool(preferences.get("fullscreen", true)))
    metronome_toggle.set_pressed_no_signal(bool(preferences.get("metronome", true)))
    _apply_window_mode(bool(preferences.get("fullscreen", true)))
    var saved_device := str(preferences.get("midi_device", ""))
    if not saved_device.is_empty() and str(last_state.get("device", "")) == "" and not device_names.is_empty():
        if device_names.has(saved_device) and not saved_device.to_lower().contains("midi through"):
            _choose_device(device_names.find(saved_device))

func _save_folder() -> void:
    _send_post("/settings", {"music_dir": folder_edit.text.strip_edges()})

func _browse_folder() -> void:
    if DirAccess.dir_exists_absolute(folder_edit.text):
        folder_dialog.current_dir = folder_edit.text
    folder_dialog.popup_centered_ratio(0.7)

func _apply_window_mode(fullscreen: bool) -> void:
    var expected := Window.MODE_FULLSCREEN if fullscreen else Window.MODE_WINDOWED
    if get_window().mode != expected:
        get_window().mode = expected

func _on_fullscreen_toggle(enabled: bool) -> void:
    _apply_window_mode(enabled)
    _send_post("/settings", {"fullscreen": enabled})

func _toggle_fullscreen() -> void:
    var enabled := get_window().mode != Window.MODE_FULLSCREEN
    fullscreen_toggle.set_pressed_no_signal(enabled)
    _on_fullscreen_toggle(enabled)

func _poll() -> void:
    if bool(last_state.get("loaded", false)) and score_error.is_empty() \
            and timeline_model_revision != revision \
            and not timeline_model_pending \
            and Time.get_ticks_msec() >= timeline_model_retry_after_ms:
        _request_timeline_model()
    if not state_pending and not action_pending:
        state_pending = true
        state_request_started_ms = Time.get_ticks_msec()
        if state_request.request(URL + "/state") != OK:
            state_pending = false

func _process(_delta: float) -> void:
    # On-device frame intervals, opt-in only. _delta is never fed back into
    # the backend tempo or score assessment; tests may call _process(0).
    if frame_diagnostics and current_screen == "practice":
        var frame_result: Dictionary = frame_meter.record_frame(_delta)
        if not frame_result.is_empty():
            frame_result["native_visible_noteheads"] = _visible_score_noteheads()
            frame_result["native_scanned_events"] = timeline_preview.frame_scanned_events
            frame_result["phase"] = str(last_state.get("phase", ""))
            print("PHASE8D_FRAME_INTERVALS:", JSON.stringify(frame_result))
    # Animate short-lived hit pulses between HTTP state samples.
    var ticks: int = Time.get_ticks_msec()
    for index in range(score_effects.hit_pulses.size() - 1, -1, -1):
        if int(score_effects.hit_pulses[index].get("until_ms", 0)) <= ticks:
            score_effects.hit_pulses.remove_at(index)
    for index in range(score_effects.wrong_ghosts.size() - 1, -1, -1):
        if int(score_effects.wrong_ghosts[index].get("until_ms", 0)) <= ticks:
            score_effects.wrong_ghosts.remove_at(index)
    for index in range(score_effects.preview_pulses.size() - 1, -1, -1):
        if int(score_effects.preview_pulses[index].get("until_ms", 0)) <= ticks:
            score_effects.preview_pulses.remove_at(index)
    apply_tempo_button.disabled = action_pending
    if tempo_down_button != null:
        tempo_down_button.disabled = (action_pending or not bool(last_state.get("loaded", false))
            or not bool(last_state.get("can_decrease_tempo", false))
            or str(last_state.get("phase", "")) in ["count_in", "playing", "loading"])
    if practice_step_picker != null:
        _sync_practice_step_navigation(last_state)
    if tempo_up_button != null:
        tempo_up_button.disabled = (action_pending or not bool(last_state.get("loaded",false))
            or not bool(last_state.get("can_increase_tempo",false))
            or str(last_state.get("phase","")) in ["count_in","playing","loading"])
    # Start Listen WAV on the actual negative-to-zero beat crossing at
    # frame rate, not on the next 150ms HTTP state poll. This preserves the
    # first note AND keeps its attack aligned with the engraved notehead.
    if demo_player != null and str(last_state.get("mode", "")) == "listen" \
            and bool(last_state.get("running", false)) \
            and not bool(last_state.get("paused", false)) \
            and bool(demo_player.get("loaded")) \
            and not bool(demo_player.get("started")):
        demo_player.synchronize(last_state, _transport_beat_now())
    # Continuous Listen drift measurements are display/audio only and
    # never feed back into the MIDI grading or the Python transport.
    if demo_player != null and str(last_state.get("mode", "")) == "listen" \
            and bool(last_state.get("running", false)) \
            and not bool(last_state.get("paused", false)):
        demo_player.keep_synchronized(_transport_beat_now(),
            maxf(1.0, float(last_state.get("bpm", 60.0))))
        if listen_sync_diagnostics and ticks - last_listen_sync_report_ms >= 1000:
            last_listen_sync_report_ms = ticks
            print("PHASE8B_LISTEN_SOFTWARE_SYNC:",
                JSON.stringify(demo_player.sync_report()))
    _update_count_in()
    # Frame-accurate native projection uses the SAME clock as score and
    # count-in. No Verovio X positions or per-note speed correction.
    if timeline_preview != null \
            and bool(last_state.get("loaded", false)):
        var score_clock: float = _transport_beat_now()
        timeline_preview.present(last_state, score_clock,
            _unrolled_score_beat(score_clock))
    # The stage's lighting follows exactly the musical beat used by the
    # moving Verovio notation. Preview/Listen use a neutral pulse; neither
    # this visual beat nor its glow can create grading events.
    if game_stage != null and bool(last_state.get("running", false)) \
            and not bool(last_state.get("paused", false)):
        game_stage.sync_beat(
            _transport_beat_now(),
            maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4))))),
            bool(last_state.get("preview_only", false))
                or str(last_state.get("mode", "")) == "listen")
    # Source-event reactions still follow the backend clock. Native feedback
    # owns visible note cues and grading; no page-coordinate camera runs here.
    if last_state.is_empty() or not bool(last_state.get("running", false)) \
            or bool(last_state.get("paused", false)) or not _native_score_ready():
        last_playhead_strike_transport = -1
        return
    var clock: float = _transport_beat_now()
    var musical_clock: float = float(last_state.get("play_from_beat", 0.0)) + clock
    var strike_transport: int = int(last_state.get("transport_id", 0))
    if last_playhead_strike_transport == strike_transport \
            and musical_clock >= last_playhead_strike_beat \
            and musical_clock - last_playhead_strike_beat <= .5:
        var onsets: Array = LivingScore.groups_crossed(
            living_chords, last_playhead_strike_beat, musical_clock)
        if not onsets.is_empty() and (bool(last_state.get("preview_only", false)) \
                or str(last_state.get("mode", "")) == "listen"):
            _preview_note_arrivals(onsets)
    last_playhead_strike_transport = strike_transport
    last_playhead_strike_beat = musical_clock
    if phase0_smoke_mode:
        var tick: int = int(floor(clock * 4.0))
        var playhead: float = timeline_preview.size.x * .42
        var content_x: float = -timeline_preview.clock_beat * timeline_preview.timeline.pixels_per_beat
        if clock < 0.0 and tick != phase0_last_lead_tick:
            phase0_last_lead_tick = tick
            print("PHASE0_LEAD_BEAT:", clock, " CONTENT_X:", content_x,
                " CURSOR_X:", playhead, " VISIBLE:", timeline_preview.visible)
        elif clock >= 0.0 and tick != phase0_last_cursor_tick:
            phase0_last_cursor_tick = tick
            print("PHASE0_VISIBLE_NOTES:", _visible_score_noteheads(),
                " PANEL_WIDTH:", score_frame.size.x, " CONTENT_X:", content_x)
            print("PHASE0_CURSOR_BEAT:", musical_clock, " SCREEN_X:", playhead,
                " VISIBLE:", timeline_preview.visible, " CONTENT_X:", content_x)


func _on_state(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray, sample_started_ms: int = -1) -> void:
    if sample_started_ms < 0:
        state_pending = false
        # A pre-action snapshot can arrive after the control response. It
        # must not put a fresh count-in or paused attempt back in its old state.
        if action_request_started_ms > 0 and state_request_started_ms <= action_request_started_ms:
            return
    if code != 200:
        feedback_label.text = _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    # A long MIDI should not engrave its default first passage while the
    # learner is still choosing a source measure in the library. Wait for
    # open_at to select the real passage before requesting any score pages.
    if current_screen == "library" and open_picker != null and open_picker.visible:
        return
    var old_phase: String = str(last_state.get("phase", ""))
    var old_revision: int = int(last_state.get("revision", -1))
    var total_input_attacks: int = int(parsed.get("midi_input_count", 0))
    var fresh_piano_key: bool = last_seen_midi_input_count >= 0 and total_input_attacks > last_seen_midi_input_count
    last_seen_midi_input_count = total_input_attacks
    var unlocked: String = ChallengeFlow.newly_unlocked(last_state, parsed)
    if not unlocked.is_empty():
        hand_unlock_message = unlocked
        hand_unlock_until_ms = Time.get_ticks_msec() + 2600
        game_streak.pulse_unlock()
        call_deferred("_pulse_hand_stage")
    last_state = parsed
    _present_fingering_status(parsed.get("fingering",{}))
    if path_reset_confirmation != null:
        if not bool(parsed.get("loaded", false)) or (
                path_reset_confirmation.visible
                and str(parsed.get("piece_fingerprint", "")) != path_reset_fingerprint):
            _cancel_path_reset()
    if path_reset_button != null:
        path_reset_button.disabled = action_pending or not bool(parsed.get("loaded", false))
    _sync_practice_step_navigation(parsed)
    if native_score_feedback != null:
        native_score_feedback.present(parsed)
    _update_visual_frame_rate(parsed)
    _clear_assessed_effects_in_ungraded_mode(parsed)
    game_phase_cue.present(parsed)
    # Low-latency local polling only while playing from a connected piano.
    # The backend remains authoritative; Godot never guesses note scoring.
    if state_poll_timer != null:
        var live_rate := (current_screen == "practice"
            and not str(parsed.get("device", "")).is_empty())
        var interval := 0.05 if live_rate else 0.15
        if absf(state_poll_timer.wait_time - interval) > 0.001:
            state_poll_timer.wait_time = interval
    var input_age = parsed.get("midi_input_age")
    if input_age != null and float(input_age) < 1.5:
        input_activity_label.text = "Input received · MIDI note %d · %d notes received" % [
            int(parsed.get("midi_input_note", 0)), int(parsed.get("midi_input_count", 0))]
        input_activity_label.add_theme_color_override("font_color", ACCENT)
    else:
        input_activity_label.text = "Play a note to check input." if not str(parsed.get("device", "")).is_empty() else "Connect your MIDI piano, then play a note to check input."
        input_activity_label.add_theme_color_override("font_color", MUTED)
    # The backend sampled the clock during this HTTP round trip. Estimate
    # that sample at the midpoint so music never waits for the poll interval.
    var started_ms: int = state_request_started_ms if sample_started_ms < 0 else sample_started_ms
    var received_ms: int = Time.get_ticks_msec()
    last_state_tick = int((started_ms + received_ms) / 2.0)
    visual_transport_clock.accept(parsed, last_state_tick, received_ms)
    if not bool(parsed.get("loaded", false)):
        if timeline_preview != null:
            timeline_preview.visible = false
        game_input_indicator.present(parsed)
        game_stage.present(parsed)
        game_streak.present({})
        mode_choice.disabled = true
        feedback_label.text = str(parsed.get("feedback", "Open a score"))
        _refresh_score_status()
        return
    title_label.text = str(parsed.get("title", "Piano Teacher")).replace("_", " ")
    var kind := str(parsed.get("kind", "learn")).capitalize()
    passage_label.text = ("%s · Measures %d–%d" % [
        kind, int(parsed.get("first_bar", 0)), int(parsed.get("last_bar", 0))])
    if bool(parsed.get("warmup", false)):
        var hand_step: int = (["left", "right", "both"].find(str(parsed.get("hand", "left"))) + 1)
        passage_label.text = "WARM-UP %d/3 · %s · Measures %d–%d" % [
            hand_step, str(parsed.get("hand", "left")).to_upper(),
            int(parsed.get("first_bar", 1)), int(parsed.get("last_bar", 8))]
    if not bool(parsed.get("warmup", false)):
        var chosen_bar: int = int(parsed.get("selected_start_bar", 1))
        if chosen_bar > int(parsed.get("first_bar", 1)):
            passage_label.text += " · Start at measure %d" % chosen_bar
    # The live bar number comes from Python's source meter grid. Do not infer
    # measures from elapsed seconds in Godot (pickup and changing meters).
    var current_bar: int = int(parsed.get("current_bar", 0))
    var phase_for_bar: String = str(parsed.get("phase", "ready"))
    if current_bar > 0 and phase_for_bar in ["count_in", "playing", "paused"]:
        var first_bar: int = int(parsed.get("first_bar", 1))
        var last_bar: int = int(parsed.get("last_bar", first_bar))
        var bar_text := "Measure %d of %d" % [current_bar, last_bar]
        if bool(parsed.get("warmup", false)):
            var hand_step: int = ["left", "right", "both"].find(str(parsed.get("hand", "left"))) + 1
            passage_label.text = "WARM-UP %d/3 · %s · %s" % [
                hand_step, str(parsed.get("hand", "left")).to_upper(), bar_text]
        else:
            passage_label.text = "%s · %s" % [kind, bar_text]
    _update_note_feedback_hud(parsed)
    if tempo_down_button != null:
        tempo_down_button.text = "-%d BPM" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_down_button.disabled = (action_pending or not bool(parsed.get("can_decrease_tempo", false))
            or str(parsed.get("phase", "")) in ["count_in", "playing", "loading"])
    if tempo_up_button != null:
        tempo_up_button.text = "+%d BPM" % int(parsed.get("manual_tempo_step_bpm", 5))
        tempo_up_button.disabled = (action_pending or not bool(parsed.get("can_increase_tempo",false))
            or str(parsed.get("phase","")) in ["count_in","playing","loading"])
    speed_label.text = "%d BPM" % int(parsed.get("bpm", 0))
    if int(parsed.get("bpm", 0)) != int(parsed.get("target_bpm", parsed.get("bpm", 0))):
        speed_label.text += " · target %d" % int(parsed.get("target_bpm", 0))
    var recovery_notice: Variant = parsed.get("recovery_notice")
    speed_label.add_theme_font_size_override("font_size", _ui_font(14))
    speed_label.tooltip_text = "Current practice tempo and your selected target"
    hand_label.text = "Both hands" if str(parsed.get("hand", "right")) == "both" else str(parsed.get("hand", "right")).capitalize() + " hand"
    hand_label.tooltip_text = "Current hand of the backend lesson"
    game_input_indicator.present(parsed)
    tempo_setting.min_value = float(parsed.get("minimum_bpm", 12))
    tempo_setting.max_value = float(parsed.get("maximum_bpm", 300))
    if current_screen != "settings":
        tempo_setting.set_value_no_signal(float(parsed.get("target_bpm", parsed.get("bpm", 40))))
    var stage: String = str(parsed.get("lesson_level", "original"))
    var explanations := {"skeleton": "Find the main notes first.",
        "outline": "Add the chord notes while keeping the pulse.",
        "original": "Bring every note together."}
    lesson_info_label.text = str(explanations.get(stage, ""))
    var import_warnings: Array = parsed.get("import_warnings", [])
    if not import_warnings.is_empty() and str(parsed.get("phase", "")) in ["ready", "feedback", "performance_complete"]:
        lesson_info_label.text = "MIDI imported with repairs: " + "  ".join(import_warnings)
        lesson_info_label.add_theme_color_override("font_color", Color("#F1C67D"))
    else:
        lesson_info_label.add_theme_color_override("font_color", INK)
    var learning: bool = str(parsed.get("mode", "practice")) == "learn"
    var teaching: Dictionary = parsed.get("teaching", {}) if parsed.get("teaching") is Dictionary else {}
    var learner: Dictionary = parsed.get("learner", {}) if parsed.get("learner") is Dictionary else {}
    placement_button.visible = bool(parsed.get("placement_available", false))
    skip_stage_button.disabled = not bool(parsed.get("skip_available", false))
    practice_skip_button.visible = bool(parsed.get("loaded", false))
    practice_skip_button.disabled = not bool(parsed.get("skip_available", false)) or action_pending
    mode_choice.select(0 if learning else 2 if str(parsed.get("mode", "")) == "perform" else 1)
    if str(parsed.get("mode", "")) == "listen":
        mode_choice.text = "Listen"
    var is_warmup: bool = bool(parsed.get("warmup", false))
    mode_choice.set_item_text(1, "Warm-up practice" if is_warmup else "Practice rhythm")
    mode_choice.set_item_disabled(0, is_warmup)
    mode_choice.set_item_disabled(2, is_warmup)
    mode_choice.set_item_disabled(3, is_warmup)
    # Keep Practice selectable after Listen, or the learner would get stuck
    # in demonstration mode until reopening the warm-up from the library.
    mode_choice.disabled = false
    hints_toggle.visible = learning
    hints_toggle.disabled = not learning or str(parsed.get("phase", "")) == "loading"
    hints_toggle.set_pressed_no_signal(bool(parsed.get("hints_enabled", false)))
    _update_hand_stages(parsed)
    if learning:
        hint_keyboard.update_state(teaching)
    else:
        hint_keyboard.update_live(
            parsed.get("midi_next_pitches", []),
            parsed.get("midi_held_pitches", []),
            parsed.get("midi_visual_events", []),
            not str(parsed.get("device", "")).is_empty()
                and str(parsed.get("mode", "")) in ["practice", "perform"]
        )
    if learning:
        var targets: int = int(teaching.get("target_count", 0))
        lesson_info_label.text = "Find the highlighted notes at your own pace."
        progress_label.text = "Notes found %d of %d · No rhythm scoring yet" % [int(teaching.get("target_index", 0)), targets]
        if not learner.is_empty():
            var unit_number: int = int(learner.get("unit_number", 0))
            var context: String = "Idea %d of %d" % [unit_number, int(learner.get("total_units", 1))] if unit_number > 0 else "Selected bars %d–%d" % [int(parsed.get("first_bar", 1)), int(parsed.get("last_bar", 1))]
            progress_label.text = "%s · Notes found %d of %d" % [context, int(teaching.get("target_index", 0)), targets]
    for hand in hand_buttons:
        var button: Button = hand_buttons[hand]
        if button is ActionButton:
            button.call("set_selected", str(parsed.get("hand", "")) == hand)
        button.disabled = not parsed.get("hands", []).has(hand) or str(parsed.get("hand", "")) == hand
    practice_progress.value = float(parsed.get("progress", 0.0))
    game_stage.present(parsed)
    stop_button.disabled = not bool(parsed.get("running", false))
    var phase: String = str(parsed.get("phase", "ready"))
    if not bool(parsed.get("paused", false)):
        advanced_pause_open = false
    pause_sheet.present(parsed if current_screen == "practice" and advanced_pause_open else {})
    start_button.visible = true
    # Play/Resume stays on the score even when paused. The old modal is
    # optional instead of interrupting every brief pause.
    start_button.visible = true
    if demo_player != null:
        # Rendered note arrival and Listen audio start share the same
        # continuously extrapolated clock, not an older HTTP snapshot.
        demo_player.synchronize(parsed, _transport_beat_now())
    listen_button.disabled = not bool(parsed.get("loaded", false))
    listen_button.text = "Practice" if str(parsed.get("mode", "")) == "listen" else "Listen"
    var listen_kind := "practice" if listen_button.text == "Practice" else "listen"
    if str(listen_button.get("action_kind")) != listen_kind:
        listen_button.call("configure", listen_kind)
        _game_button(listen_button)
    practice_retry_button.disabled = (not bool(parsed.get("loaded", false))
        or not _native_score_ready())
    var summary: Dictionary = parsed.get("performance_summary", {}) if parsed.get("performance_summary") is Dictionary else {}
    performance_review.visible = not summary.is_empty()
    if not summary.is_empty():
        var weakest: Array = summary.get("weakest_bars", [])
        performance_text.text = "%.0f%% correct · %d/%d notes · %d missed · %d wrong · %d timing/duration · %d extra" % [
            float(summary.get("accuracy_percent", 0)), int(summary.get("correct", 0)),
            int(summary.get("total", 0)), int(summary.get("missed", 0)),
            int(summary.get("wrong", 0)),
            int(summary.get("early", 0)) + int(summary.get("late", 0))
                + int(summary.get("short", 0)) + int(summary.get("long", 0)),
            int(summary.get("extra_notes", 0))]
        weak_button.visible = not weakest.is_empty()
        weak_button.disabled = weakest.is_empty()
    var selected_retry: Variant = parsed.get("review_range")
    if selected_retry is Dictionary:
        passage_label.text = "Repeating measures %d–%d · %s" % [
            int(selected_retry.get("first_bar", 1)),
            int(selected_retry.get("last_bar", 1)),
            "No full-passage mastery"]
    var active_transport: bool = _has_active_transport()
    if not learning:
        stop_button.disabled = not active_transport
    if phase0_smoke_mode and phase != phase0_last_phase:
        phase0_last_phase = phase
        print("PHASE0_PHASE:", phase)
    if learning:
        feedback_label.text = str(parsed.get("feedback", "Find the highlighted notes at your own pace."))
        stop_button.disabled = phase in ["ready", "guided_complete", "disconnected"]
    elif phase == "paused":
        feedback_label.text = "Paused · press Play to resume"
    elif phase == "loading":
        feedback_label.text = "Preparing next passage · count-in waits for score"
    elif phase == "recovering":
        feedback_label.text = str(parsed.get("feedback", "Short break before retry"))
    elif phase == "count_in":
        feedback_label.text = "GET READY · follow the teal playhead"
    elif phase == "playing":
        var midi_count: int = int(parsed.get("midi_notes", 0))
        if bool(parsed.get("preview_only", false)):
            feedback_label.text = "PREVIEW · connect your piano to earn clean runs"
        else:
            feedback_label.text = "PLAYING · %d notes heard" % midi_count if midi_count > 0 else "PLAYING · waiting for your piano"
    else:
        feedback_label.text = str(parsed.get("feedback", ""))
    if str(parsed.get("mode", "")) == "listen":
        var demo_info: Dictionary = parsed.get("demo", {}) if parsed.get("demo") is Dictionary else {}
        var instrument: String = str(demo_info.get("instrument", "Preparing piano audio"))
        feedback_label.text = ("Listening · " + instrument if bool(parsed.get("running", false))
            else str(parsed.get("feedback", "Preparing Listen audio")))
        if bool(parsed.get("paused", false)):
            feedback_label.text = "Listen paused · " + instrument
        if bool(demo_info.get("audio_available", false)) and not bool(demo_info.get("sampled", false)):
            lesson_info_label.text = "Basic piano sound · install the Salamander samples for acoustic Listen (see README)."
        elif bool(demo_info.get("sampled", false)):
            lesson_info_label.text = "Acoustic grand piano · " + instrument
        if demo_player != null and bool(demo_player.get("audio_error")):
            feedback_label.text = "Listen audio could not load. Choose Listen to try again."
    feedback_label.tooltip_text = feedback_label.text
    var unpositioned: int = int(parsed.get("feedback_unmapped", 0))
    if unpositioned > 0:
        feedback_label.text += " · %d unpositioned note(s)" % unpositioned
    if (not learning and phase in ["ready", "performance_complete"]
            and not str(parsed.get("device", "")).is_empty()):
        lesson_info_label.text = "Play any piano key to start the count-in. Release it, then play after the count-in."
    elif learning and phase == "guided_complete" and not str(parsed.get("device", "")).is_empty():
        lesson_info_label.text = "Idea complete · play one new piano key to continue."
    elif phase == "feedback" and not bool(parsed.get("auto", false)) and not str(parsed.get("device", "")).is_empty():
        lesson_info_label.text = "Review the red notes · play a new piano key to retry."
    if not learning:
        var needed_runs: int = int(parsed.get("clean_runs_required", 3))
        progress_label.text = "Clean runs %d of %d at %d BPM" % [
            int(parsed.get("streak", 0)), needed_runs, int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
        if bool(parsed.get("warmup", false)):
            var name: String = "Both hands" if str(parsed.get("hand", "")) == "both" else str(parsed.get("hand", "")).capitalize() + " hand"
            progress_label.text = "%s · %d of %d clean runs · Next hand unlocks when mastered" % [
                name, int(parsed.get("streak", 0)), needed_runs]
        if str(parsed.get("mode", "")) == "perform":
            progress_label.text = "Perform · keep going to the end; review follows"
        elif str(parsed.get("mode", "")) == "listen":
            progress_label.text = "Listen · example audio; your playing is not graded"
    var next_action: String = str(parsed.get("next_action", ""))
    if not next_action.is_empty() and (phase in ["feedback", "recovering", "loading", "paused"] or bool(parsed.get("guided_recovery", false))):
        lesson_info_label.text = next_action
        var remaining = parsed.get("transition_in_seconds")
        if remaining != null:
            lesson_info_label.text = ("After resume · " if phase == "paused" else "Next in %.1f s · " % maxf(0.0, float(remaining))) + next_action
    # The backend's judged take and persisted streak are the ONLY sources
    # for this three-clean-pass challenge. No UI-side scoring or timers.
    var challenge: Dictionary = ChallengeFlow.present(parsed)
    game_streak.present(challenge)
    if bool(challenge.get("visible", false)):
        progress_label.text = str(challenge.get("label", ""))
        progress_label.tooltip_text = str(challenge.get("detail", ""))
        var challenge_kind: String = str(challenge.get("kind", ""))
        progress_label.add_theme_color_override("font_color",
            Color("#78DBAD") if challenge_kind == "success" else
            Color("#F0B971") if challenge_kind in ["retry", "recovering"] else INK)
        if challenge_kind == "success" and next_action.is_empty():
            lesson_info_label.text = str(challenge.get("detail", ""))
        if Time.get_ticks_msec() < hand_unlock_until_ms:
            progress_label.text = hand_unlock_message
            progress_label.add_theme_color_override("font_color", Color("#78DBAD"))
            progress_label.tooltip_text = hand_unlock_message
    # Some recovery transitions provide only recovery_notice, without a
    # next_action. Keep the essential tempo and measure changes in the normal
    # instruction line; never restore the in-score banner.
    if (recovery_notice is Dictionary and next_action.is_empty()
            and str(parsed.get("mode", "")) == "practice"
            and phase in ["ready", "feedback", "recovering", "loading"]
            and str(challenge.get("kind", "")) != "success"):
        var notice: Dictionary = recovery_notice
        var previous_tempo: int = int(notice.get("from_bpm", 0))
        var new_tempo: int = int(notice.get("to_bpm", 0))
        if str(notice.get("kind", "")) == "speedup":
            lesson_info_label.text = "Tempo %d → %d BPM · keep practising" % [previous_tempo, new_tempo]
        else:
            lesson_info_label.text = "Tempo %d → %d BPM · retry measures %d–%d" % [
                previous_tempo, new_tempo, int(notice.get("first_bar", 1)),
                int(notice.get("last_bar", 1))]
    # During graded playback, notation and MIDI note reactions provide the
    # information. Preserve warnings for ungraded previews and audio errors.
    var busy_music: bool = phase in ["playing", "count_in"] and not learning
    var audio_problem: bool = demo_player != null and bool(demo_player.get("audio_error"))
    feedback_label.visible = not busy_music or bool(parsed.get("preview_only", false)) \
        or audio_problem or unpositioned > 0
    lesson_info_label.visible = (learning or not busy_music
        or bool(parsed.get("guided_recovery", false)))
    feedback_label.tooltip_text = feedback_label.text
    lesson_info_label.tooltip_text = lesson_info_label.text
    # One short verb belongs on the central game control. Shortcuts and
    # explanations live in the tooltip instead of making every button a menu.
    start_button.text = "Resume" if bool(parsed.get("paused", false)) else "Pause" if active_transport else "Play"
    if learning:
        start_button.text = "Resume" if phase == "paused" else "Try rhythm" if phase in ["guided_complete", "disconnected"] else "Pause" if phase in ["guided_wait", "loading"] else "Learn"
        if phase == "guided_complete" and bool(parsed.get("guided_recovery", false)):
            start_button.text = "Retry rhythm"
        elif phase == "guided_complete" and bool(teaching.get("has_more_units", false)):
            start_button.text = "Next idea"
    elif str(parsed.get("mode", "")) == "listen" and not active_transport:
        start_button.text = "Back to warm-up" if bool(parsed.get("warmup", false)) else "Listen again"
    start_button.tooltip_text = "Play, pause or resume · Space · Play any piano key when ready"
    start_button.disabled = not active_transport and (not _native_score_ready())
    start_button.call("configure", "pause" if start_button.text == "Pause" else "play",
        active_transport and not bool(parsed.get("paused", false)))
    listen_button.call("configure", "practice" if str(parsed.get("mode", "")) == "listen" else "listen",
        str(parsed.get("mode", "")) == "listen")
    score_effects.marks = []
    for marker in parsed.get("feedback_marks", []):
        score_effects.marks.append(marker)
    _consume_live_piano_hits(parsed)
    var new_revision := int(parsed.get("revision", 0))
    if new_revision != revision:
        revision = new_revision
        if timeline_preview != null:
            timeline_preview.clear_score()
            timeline_preview.visible = false
            timeline_model_revision = -1
            timeline_model_retry_after_ms = 0
        layout_revision = -1
        score_layout = {}
        living_chords.clear()
        rendered_revision = -1
        score_error = ""
        start_button.disabled = not active_transport
        practice_retry_button.disabled = true
        _refresh_score_status()
        score_effects.marks = []
        score_effects.hit_pulses.clear()
        score_effects.wrong_ghosts.clear()
        score_effects.preview_pulses.clear()
        _request_layout()
    if str(parsed.get("phase", "")) == "loading" and _native_score_ready():
        _send_action({"action": "score_ready", "revision": revision})
    # A physical note-on is the hands-free equivalent of Start on this
    # screen only. Poll-based arming keeps device checks in Settings inert.
    # A completion note in Learn must NOT instantly skip the completed idea;
    # require a new note-on after the finished state was already displayed.
    var current_phase: String = str(parsed.get("phase", ""))
    if (fresh_piano_key and sample_started_ms < 0 and current_screen == "practice"
            and not action_pending and old_revision == int(parsed.get("revision", -1))
            and old_phase == current_phase and not str(parsed.get("device", "")).is_empty()
            and _native_score_ready()
            and (current_phase in ["ready", "performance_complete", "guided_complete"]
                or (current_phase == "feedback" and str(parsed.get("mode", "")) == "practice"
                    and not bool(parsed.get("auto", false))))):
        if str(parsed.get("mode", "")) == "learn":
            _toggle_playing()
        elif current_phase == "feedback":
            _send_action({"action": "restart"})
        elif str(parsed.get("mode", "")) in ["practice", "perform"]:
            _send_action({"action": "start"})
    _refresh_score_status()

func _update_note_feedback_hud(parsed: Dictionary) -> void:
    # The red HUD has its own fixed screen position. Score-head markers
    # alone are easy to miss once the continuous score scrolls away.
    var active_mode: String = str(parsed.get("mode", "practice"))
    var active_phase: String = str(parsed.get("phase", "ready"))
    var feedback: Variant = parsed.get("live_note_feedback")
    practice_note_feedback_panel.visible = false
    # All mapped mistakes appear directly on the engraved notes.
    # The status line below the score already reports feedback_unmapped;
    # do not overlay another (potentially clipped) notification on the music.


func _preview_note_arrivals(groups: Array) -> void:
    # Demonstrate musical energy when there is no keyboard, but in blue
    # rather than graded mint. These are backend-clock onsets, never grades.
    if groups.is_empty():
        return
    var now_ms: int = Time.get_ticks_msec()
    for group in groups:
        var notes: Array = group.get("notes", [])
        for note in notes:
            if score_effects.preview_pulses.size() >= 24:
                score_effects.preview_pulses.pop_front()
            score_effects.preview_pulses.append({
                "page": int(note.get("page", 0)),
                "x": float(note.get("x", 0.0)),
                "y": float(note.get("y", 0.0)),
                "duration_ms": 220,
                "until_ms": now_ms + 220,
                "status": "preview"
            })
    game_stage.preview_react()


func _clear_assessed_effects_in_ungraded_mode(state: Dictionary) -> void:
    # Mode-specific colors have distinct meanings. Clear old assessed
    # success when entering preview/Listen, and clear blue preview sparks
    # when returning to a real scored MIDI take.
    var ungraded: bool = bool(state.get("preview_only", false)) \
        or str(state.get("mode", "")) == "listen"
    if ungraded:
        if game_impact_callout != null:
            game_impact_callout.call("clear")
        if score_effects.hit_pulses.is_empty() and score_effects.wrong_ghosts.is_empty():
            return
        score_effects.hit_pulses.clear()
        score_effects.wrong_ghosts.clear()
        # The stage is a separate canvas and must drop its older earned
        # success energy along with the note particles on mode change.
        game_stage.impact_energy = 0.0
        game_stage.queue_redraw()
    else:
        if score_effects.preview_pulses.is_empty():
            return
        score_effects.preview_pulses.clear()


func _consume_live_piano_hits(state: Dictionary) -> void:
    var events: Array = state.get("midi_visual_events", [])
    var mapping: Dictionary = score_layout.get("attack_map", {})
    var notes: Array = score_layout.get("notes", [])
    for event in events:
        if not event is Dictionary:
            continue
        var sequence: int = int(event.get("sequence", 0))
        if sequence <= last_seen_midi_visual_sequence:
            continue
        last_seen_midi_visual_sequence = sequence
        # Even if an old MIDI event survived a mode transition, Listen
        # and keyboard-free preview must never display a success burst.
        if bool(state.get("preview_only", false)) or str(state.get("mode", "")) == "listen":
            continue
        if str(state.get("phase", "")) != "playing" or layout_revision != revision:
            continue
        if int(event.get("transport_id", -1)) != int(state.get("transport_id", -2)):
            continue
        var status: String = str(event.get("status", ""))
        var age: float = float(event.get("age", 99.0))
        if age > 1.05:
            continue
        var source: String = str(event.get("source_id", ""))
        if status == "unexpected":
            var reference: String = str(event.get("reference_source_id", ""))
            var reference_id: String = str(mapping.get(reference, ""))
            if reference_id.is_empty():
                continue
            for note in notes:
                if str(note.get("id", "")) != reference_id:
                    continue
                var remaining: int = maxi(1, 420 - int(age * 1000.0))
                score_effects.wrong_ghosts.append({
                    "page": int(note.get("page", 0)),
                    "x": float(note.get("x", 0.0)),
                    "y": float(note.get("y", 0.0)),
                    "duration_ms": 420,
                    "until_ms": Time.get_ticks_msec() + remaining
                })
                if score_effects.wrong_ghosts.size() > 32:
                    score_effects.wrong_ghosts.pop_front()
                game_stage.react("unexpected")
                game_impact_callout.call("react", "unexpected")
                break
            continue
        if status not in ["on_time", "early", "late"] or age > .22:
            continue
        var note_id: String = str(mapping.get(source, ""))
        if note_id.is_empty():
            continue
        for note in notes:
            if str(note.get("id", "")) == note_id:
                score_effects.hit_pulses.append({
                    "page": int(note.get("page", 0)),
                    "x": float(note.get("x", 0.0)),
                    "y": float(note.get("y", 0.0)),
                    "status": status,
                    "note_id": note_id,
                    "duration_ms": 220,
                    "until_ms": Time.get_ticks_msec() + maxi(1, 220 - int(age * 1000.0))
                })
                if score_effects.hit_pulses.size() > 32:
                    score_effects.hit_pulses.pop_front()
                game_stage.react(status)
                game_impact_callout.call("react", status)
                break


func _request_layout() -> void:
    if layout_pending:
        return
    layout_pending = true
    requested_layout_revision = revision
    var score_url: String = URL + "/score/layout?native=1"
    if layout_request.request(score_url) != OK:
        layout_pending = false
        _score_failed("Cannot request score geometry from the practice engine")

func _on_layout(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    layout_pending = false
    if requested_layout_revision != revision:
        _request_layout()
        return
    if code != 200:
        _score_failed(_http_failure(code, body))
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("anchors"):
        _score_failed("The engraving engine returned invalid note positions")
        return
    if parsed.has("revision") and int(parsed["revision"]) != revision:
        # A control request may have advanced the server before its state
        # response reached this window. Wait for that revision's normal poll.
        return
    # Authentic Verovio contours remain the only musical glyph assets.
    if not timeline_preview.set_verovio_glyphs(
            parsed.get("native_glyphs", {}),
            parsed.get("native_note_templates", {}),
            parsed.get("native_tie_templates", {}),
            parsed.get("native_chord_templates", {}),
            parsed.get("native_beam_fragments", {}),
            parsed.get("native_tuplet_fragments", {}),
            parsed.get("native_slur_fragments", {}),
            parsed.get("native_required_slur_pairs", []),
            bool(parsed.get("native_slurs_complete", false)),
            parsed.get("native_required_beam_groups", []),
            bool(parsed.get("native_beams_complete", false))):
        _score_failed(str(timeline_preview.failure_reason))
        return
    parsed.erase("native_glyphs")
    parsed.erase("native_note_templates")
    parsed.erase("native_tie_templates")
    parsed.erase("native_chord_templates")
    parsed.erase("native_beam_fragments")
    parsed.erase("native_tuplet_fragments")
    parsed.erase("native_slur_fragments")
    parsed.erase("native_required_slur_pairs")
    parsed.erase("native_slurs_complete")
    parsed.erase("native_required_beam_groups")
    parsed.erase("native_beams_complete")
    score_layout = parsed
    living_chords = LivingScore.prepare(score_layout)
    layout_revision = revision
    timeline_model_revision = -1
    score_error = ""
    _refresh_score_status()
    _request_timeline_model()

func _finish_native_score() -> void:
    if layout_revision != revision or timeline_model_revision != revision \
            or not timeline_preview.native_ready:
        return
    rendered_revision = revision
    score_error = ""
    start_button.disabled = false
    _refresh_score_status()
    if phase0_smoke_mode:
        print("PHASE0_SCORE_READY_NATIVE: REVISION:", revision)
    if str(last_state.get("phase","")) == "loading" and \
            int(last_state.get("awaiting_score_revision",-1)) == revision:
        _send_action({"action":"score_ready","revision":revision})


func _request_timeline_model() -> void:
    if timeline_model_request == null or timeline_model_pending \
            or not bool(last_state.get("loaded", false)):
        return
    # The semantic model must wait for this revision's authentic glyphs.
    # _on_layout requests the model once the font atlas is actually ready.
    if not score_error.is_empty() or layout_revision != revision or \
            timeline_preview == null or not timeline_preview.glyphs.ready():
        return
    timeline_model_pending = true
    var error: Error = timeline_model_request.request(URL + "/score/model")
    if error != OK:
        timeline_model_pending = false
        timeline_model_retry_after_ms = Time.get_ticks_msec() + 2000
        if timeline_preview != null:
            timeline_preview.notice = "Cannot load semantic score"
            timeline_preview.queue_redraw()


func _on_timeline_model(_result: int, code: int,
        _headers: PackedStringArray, body: PackedByteArray) -> void:
    timeline_model_pending = false
    if timeline_preview == null or layout_revision != revision or not score_error.is_empty():
        return
    var candidate: Variant = _decode_json(body)
    if code == 200 and candidate is Dictionary:
        # Ignore stale replies after lesson/hand/variant transitions.
        if int(candidate.get("revision", -1)) != revision:
            return
        if not timeline_preview.load_score(candidate):
            _score_failed(str(timeline_preview.failure_reason))
            return
        native_score_piece_fingerprint = str(last_state.get("piece_fingerprint",""))
        timeline_model_revision = revision
        timeline_preview.visible = true
        _finish_native_score()
        if native_score_feedback != null:
            native_score_feedback.bind_score(timeline_preview, revision)
            native_score_feedback.present(last_state)
        print("NATIVE_MODEL_READY: ", revision,
            " NOTES: ", timeline_preview.timeline.notes.size(),
            " DENSITY: ", timeline_preview.timeline.pixels_per_beat)
        return
    timeline_model_retry_after_ms = Time.get_ticks_msec() + 2000
    timeline_preview.notice = "Score model unavailable; retrying"
    timeline_preview.queue_redraw()


func _send_action(command: Dictionary) -> void:
    var requested: String = str(command.get("action", ""))
    if action_pending:
        # Avoid an apparently dead button: the user sees precisely which
        # operation is still pending, rather than silently dropping clicks.
        if requested in ["pause", "stop"]:
            pending_transport_action = requested
        feedback_label.text = "Please wait · finishing " + last_control_action
        feedback_label.visible = true
        return
    last_control_action = requested
    var verb: String = {
        "listen": "Preparing piano audio", "practice": "Returning to practice",
        "start": "Starting count-in", "pause": "Pausing",
        "resume": "Resuming", "restart": "Restarting the passage",
        "skip_stage": "Loading next lesson", "stop": "Stopping"
    }.get(requested, "Applying " + requested.replace("_", " "))
    feedback_label.text = verb + "…"
    feedback_label.visible = true
    if practice_playback_banner != null:
        practice_playback_banner.text = verb + "…"
        practice_playback_banner.visible = true
    _send_post("/control", command)


func _present_fingering_status(summary: Variant) -> void:
    if fingering_status_label == null:
        return
    if not summary is Dictionary:
        summary = {}
    var status: String = str(summary.get("status",""))
    var unknown: int = int(summary.get("unknown",0))
    var review: int = int(summary.get("review",0))
    var unavailable: bool = status in ["unavailable","failed","error"]
    var detail: String = str(summary.get("error",""))
    var issues := PackedStringArray()
    for issue in summary.get("issues",[]):
        issues.append(str(issue))
    if not issues.is_empty():
        detail += ("\n" if not detail.is_empty() else "")+"\n".join(issues)
    fingering_status_label.visible = unavailable or unknown > 0 or review > 0 or not fingering_save_error.is_empty()
    if not fingering_save_error.is_empty():
        fingering_status_label.text = "Fingering not saved"
        detail = fingering_save_error
    elif unavailable:
        fingering_status_label.text = "Automatic fingering unavailable"
    elif unknown > 0:
        fingering_status_label.text = "%d unknown finger%s" % [unknown,"" if unknown == 1 else "s"]
        if detail.is_empty():
            detail = "Some source notes have no reliable finger assignment."
    elif review > 0:
        fingering_status_label.text = "Check %d fingering%s" % [review,"" if review == 1 else "s"]
    else:
        fingering_status_label.text = ""
    fingering_status_label.tooltip_text = (detail+"\n" if not detail.is_empty() else "")+ \
        "Right-click any attack note, or tap a finger number, to correct it. Unknown notes can also be edited."


func _on_fingering_change_requested(source_id: String, finger: Variant) -> void:
    if action_pending or not _native_score_ready() or layout_pending or timeline_model_pending or \
            int(last_state.get("revision",-1)) != timeline_model_revision or \
            native_score_piece_fingerprint != str(last_state.get("piece_fingerprint","")):
        fingering_save_error = "Wait for the current score operation to finish, then try again."
        _present_fingering_status(last_state.get("fingering",{}))
        return
    fingering_save_error = ""
    var payload: Dictionary = {"source_id":source_id,"finger":finger}
    # XML identities repeat between pieces. Bind a correction to the piece
    # visible when the popup was opened even if another client loads music.
    var fingerprint: String = native_score_piece_fingerprint
    if not fingerprint.is_empty():
        payload["fingerprint"] = fingerprint
    _send_post("/fingering",payload)

func _flush_transport_action() -> void:
    if not pending_transport_action.is_empty():
        var action := pending_transport_action
        pending_transport_action = ""
        _send_action({"action": action})

func _send_post(path: String, payload: Dictionary) -> void:
    if action_pending:
        return
    action_pending = true
    # A complete local composition can take longer than a small control
    # request. Allow the bounded whole-piece inference to finish saving.
    action_request.timeout = 360.0 if path in ["/fingering","/load","/library/open"] else 5.0
    last_post_path = path
    action_request_started_ms = Time.get_ticks_msec()
    var err := action_request.request(URL + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
    if err != OK:
        action_pending = false
        feedback_label.text = "Cannot reach practice engine"
        feedback_label.visible = true
        if path == "/fingering":
            fingering_save_error = "Cannot reach practice engine. Try the correction again."
            _present_fingering_status(last_state.get("fingering",{}))

func _on_action(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    action_pending = false
    if last_post_path == "/control" and practice_playback_banner != null:
        practice_playback_banner.visible = false
    var path := last_post_path
    var resume_saved: bool = path == "/library/open" and library_resume_requested
    if path == "/library/open":
        library_resume_requested = false
    var completed_action := last_control_action
    if code != 200:
        var message := _http_failure(code, body)
        if path == "/fingering":
            fingering_save_error = message
            _present_fingering_status(last_state.get("fingering",{}))
        var queued_library_failed: bool = not pending_library_piece.is_empty()
        pending_library_piece = ""
        pending_library_resume = false
        if path == "/library/open":
            library_error = "Cannot open score: " + message
            library_message.add_theme_color_override("font_color", Color("#FF8B82"))
        elif queued_library_failed:
            library_error = "Cannot open selected music: " + message
            library_message.add_theme_color_override("font_color", Color("#FF8B82"))
        feedback_label.text = message
        settings_message.text = message
        library_message.text = library_error if queued_library_failed else message
        home_recent_label.text = message
        _flush_transport_action()
        return
    if path == "/fingering":
        fingering_save_error = ""
        _on_state(_result,code,_headers,body,action_request_started_ms)
    elif path == "/control":
        if completed_action == "reset_path":
            # The fingerprint stays the same after a reset; invalidate the
            # cached lesson overview so mastered/skip badges refresh.
            lesson_choice_fingerprint = ""
            lesson_requested_fingerprint = ""
            lesson_refresh_after_reset = lesson_pending
        _on_state(_result, code, _headers, body, action_request_started_ms)
        if completed_action in ["skip_stage", "place_original", "revisit_trouble"]:
            _navigate("practice")
    elif path == "/library/health":
        _request_library_health()
    elif path == "/library/open":
        library_error = ""
        _populate_library()
        score_error = ""
        var opened: Variant = _decode_json(body)
        if opened is Dictionary and (bool(opened.get("warmup", false)) or resume_saved):
            _navigate("practice")
            if resume_saved:
                # Loading already restores the backend's lesson, hand, tempo
                # and clean streak. A new open_at would replace that place.
                _on_state(_result, code, _headers, body, action_request_started_ms)
            _refresh_score_status()
        elif opened is Dictionary:
            _show_open_picker(opened)
    elif path == "/settings":
        settings_message.text = "Settings saved"
        _request_settings()
        _request_library()
    elif path == "/device":
        _request_settings()
    _flush_transport_action()
    _poll()
    if not pending_library_piece.is_empty():
        var queued: String = pending_library_piece
        var queued_resume: bool = pending_library_resume
        pending_library_piece = ""
        pending_library_resume = false
        call_deferred("_open_library_piece", queued, queued_resume)

func _has_active_transport() -> bool:
    return bool(last_state.get("running", false)) or str(last_state.get("phase", "")) in ["count_in", "playing", "paused", "feedback", "recovering", "loading", "preview_gap"]

func _listen_or_return_to_practice() -> void:
    # Listen is a one-tap reversible action, never a scored take.
    if str(last_state.get("mode", "")) == "listen":
        _send_action({"action": "practice", "wait_for_player": true})
    else:
        _send_action({"action": "listen"})


func _toggle_playing() -> void:
    if bool(last_state.get("paused", false)) and not score_error.is_empty():
        feedback_label.text = score_error
        return
    if str(last_state.get("mode", "")) == "listen" and not _has_active_transport():
        _send_action({"action": "practice" if bool(last_state.get("warmup", false)) else "listen"})
        return
    if str(last_state.get("mode", "practice")) == "learn":
        var phase: String = str(last_state.get("phase", "ready"))
        if phase not in ["paused", "guided_wait", "loading"] and not _native_score_ready():
            feedback_label.text = "Preparing sheet music - wait for the notes before starting"
            return
        var teaching: Dictionary = last_state.get("teaching", {}) if last_state.get("teaching") is Dictionary else {}
        if phase == "guided_complete" and bool(teaching.get("has_more_units", false)) and not bool(last_state.get("guided_recovery", false)):
            _send_action({"action": "learn_next"})
            return
        _send_action({"action": "resume" if phase == "paused" else "practice" if phase in ["guided_complete", "disconnected"] else "pause" if phase in ["guided_wait", "loading"] else "learn_retry"})
        return
    if bool(last_state.get("paused", false)):
        _send_action({"action": "resume"})
        return
    if _has_active_transport():
        _send_action({"action": "pause"})
        return
    if not bool(last_state.get("running", false)) and (not _native_score_ready()):
        feedback_label.text = "Preparing sheet music - wait for the notes before starting"
        return
    _send_action({"action": "pause" if bool(last_state.get("running", false)) else "start"})

func _open_advanced_pause() -> void:
    _navigate("practice")
    advanced_pause_open = true
    if bool(last_state.get("paused", false)):
        pause_sheet.present(last_state)
    elif _has_active_transport():
        _send_action({"action": "pause"})
    else:
        # Advanced options require a live paused attempt; use Path controls
        # directly when nothing is playing.
        advanced_pause_open = false


func _toggle_pause() -> void:
    if bool(last_state.get("paused", false)) and not score_error.is_empty():
        feedback_label.text = score_error
        return
    if _has_active_transport() or (str(last_state.get("mode", "practice")) == "learn" and str(last_state.get("phase", "")) in ["guided_wait", "paused"]):
        _send_action({"action": "resume" if bool(last_state.get("paused", false)) else "pause"})

func _skip_current_lesson() -> void:
    if action_pending or not bool(last_state.get("skip_available", false)):
        return
    _send_action({"action": "skip_stage",
        "reason": "Learner skipped to the next lesson from the practice screen"})


func _restart_practice() -> void:
    if _native_score_ready():
        _send_action({"action": "learn_retry" if str(last_state.get("mode", "practice")) == "learn" else "restart"})

func _request_devices() -> void:
    if device_pending or device_request == null:
        return
    device_pending = true
    if device_request.request(URL + "/devices") != OK:
        device_pending = false

func _on_devices(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    device_pending = false
    if code != 200:
        # Failed ALSA discovery previously disappeared silently, leaving a
        # stale device picker. Give a diagnostic in Settings without
        # interrupting a running practice take.
        device_menu_requested = false
        if current_screen == "settings" and settings_message != null:
            settings_message.text = "MIDI device scan failed: " + _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        device_menu_requested = false
        return
    device_names = parsed.get("devices", [])
    device_menu.clear()
    device_menu.add_item("No MIDI input · timing preview", -2)
    device_menu.add_separator()
    for i in range(device_names.size()):
        device_menu.add_item(str(device_names[i]), i)
    device_button.text = str(last_state.get("device", "Choose USB MIDI piano")) if not str(last_state.get("device", "")).is_empty() else "Choose USB MIDI piano"
    if str(last_state.get("device", "")) == "":
        var saved: String = str(preferences.get("midi_device", ""))
        if device_names.has(saved) and not saved.is_empty() and not saved.to_lower().contains("midi through"):
            _choose_device(device_names.find(saved))
    if device_menu_requested:
        # Populate from this fresh response before showing the popup. The
        # former implementation opened stale items while scanning asynchronously.
        device_menu_requested = false
        device_menu.position = Vector2i(device_button.get_screen_position()) + Vector2i(0, int(device_button.size.y))
        device_menu.popup()

func _show_devices() -> void:
    device_menu_requested = true
    _request_devices()

func _choose_device(id: int) -> void:
    if id == -2:
        _send_post("/device", {"name": ""})
        return
    if id < 0 or id >= device_names.size():
        return
    _send_post("/device", {"name": device_names[id]})
    device_button.text = str(device_names[id]) + "  ✓"

func _input(event: InputEvent) -> void:
    if open_picker != null and open_picker.visible and event is InputEventKey \
            and event.pressed and not event.echo:
        if event.keycode == KEY_ESCAPE:
            _cancel_open_picker()
            get_viewport().set_input_as_handled()
            return
        if event.keycode == KEY_ENTER or event.keycode == KEY_KP_ENTER:
            if open_mode.get_popup().visible:
                return
            _confirm_open_picker()
            get_viewport().set_input_as_handled()
            return
    # Never pass modal keyboard input to background Play/Pause/Retry/Listen
    # shortcuts; Tab and Space must remain available to the focused controls.
    if open_picker != null and open_picker.visible:
        return
    if not event is InputEventKey:
        return
    # Search without hunting for a small field in the Music drawer.
    # Once focused, / remains normal text input.
    if event.pressed and not event.echo and current_screen == "library" \
            and ((event.ctrl_pressed and event.keycode == KEY_F) or
            (event.keycode == KEY_SLASH and get_viewport().gui_get_focus_owner() != library_search)):
        library_search.grab_focus()
        library_search.select_all()
        get_viewport().set_input_as_handled()
        return
    if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_TAB]:
        return
    if get_viewport().gui_get_focus_owner() is LineEdit and event.keycode not in [KEY_F11, KEY_ESCAPE] and not (event.ctrl_pressed and event.keycode == KEY_Q):
        return
    var practice_shortcut: bool = current_screen == "practice" and event.keycode in [
        KEY_ESCAPE, KEY_SPACE, KEY_P, KEY_R, KEY_S, KEY_L, KEY_LEFT, KEY_RIGHT]
    if event.keycode == KEY_ESCAPE and current_screen in ["library", "settings", "lesson"]:
        _unhandled_key_input(event)
        get_viewport().set_input_as_handled()
        return
    if event.keycode == KEY_F11 or (event.ctrl_pressed and event.keycode == KEY_Q) or practice_shortcut:
        # Consume press and release before focused buttons see ui_accept.
        # Handling only the press can also activate Next/Stop on release.
        _unhandled_key_input(event)
        get_viewport().set_input_as_handled()

func _unhandled_key_input(event: InputEvent) -> void:
    if open_picker != null and open_picker.visible:
        return
    if event is InputEventKey and event.pressed and not event.echo:
        if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN, KEY_TAB]:
            return
        if get_viewport().gui_get_focus_owner() is LineEdit and event.keycode not in [KEY_F11, KEY_ESCAPE] and not (event.ctrl_pressed and event.keycode == KEY_Q):
            return
        if event.ctrl_pressed and event.keycode == KEY_Q:
            _exit_app()
            get_viewport().set_input_as_handled()
            return
        if event.keycode == KEY_F11:
            _toggle_fullscreen()
            get_viewport().set_input_as_handled()
            return
        if event.keycode == KEY_ESCAPE:
            _navigate("library" if current_screen == "practice" else "practice")
            get_viewport().set_input_as_handled()
            return
        if current_screen != "practice":
            return
        if event.keycode == KEY_P and event.shift_pressed:
            _open_advanced_pause()
            get_viewport().set_input_as_handled()
            return
        match event.keycode:
            KEY_SPACE:
                _toggle_playing()
                get_viewport().set_input_as_handled()
            KEY_P:
                _toggle_pause()
                get_viewport().set_input_as_handled()
            KEY_R:
                _restart_practice()
                get_viewport().set_input_as_handled()
            KEY_L:
                _listen_or_return_to_practice()
                get_viewport().set_input_as_handled()
            KEY_S:
                _send_action({"action": "stop"})
                get_viewport().set_input_as_handled()
            KEY_LEFT:
                _send_action({"action": "previous"})
                get_viewport().set_input_as_handled()
            KEY_RIGHT:
                _send_action({"action": "next"})
                get_viewport().set_input_as_handled()
