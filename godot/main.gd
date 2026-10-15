extends Control

# Lightweight Godot presentation. Python owns MIDI timestamps, tempo and grading.
const URL := "http://127.0.0.1:8765"
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SLATE
const PAPER := Design.FOREST
const WHITE := Design.PANEL
const ACCENT := Design.TEAL
const ScoreStrip := preload("res://score_strip.gd")
const ScoreOverlay := preload("res://score_overlay.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")

var current_screen := "home"
var settings_return_screen := "home"
var screens: Dictionary = {}
var library_request: HTTPRequest
var settings_request: HTTPRequest
var library_pending := false
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
var score_status_panel: CenterContainer
var score_status_label: Label
var score_retry_button: Button
var score_error := ""
var library_error := ""
var home_recent_label: Label
var home_resume_button: Button
var library_search: LineEdit
var library_path_label: Label
var library_rows: VBoxContainer
var library_message: Label
var folder_edit: LineEdit
var folder_dialog: FileDialog
var fullscreen_toggle: CheckButton
var settings_message: Label
var last_post_path := ""
var last_control_action := ""
var pending_transport_action := ""
var action_request_started_ms := 0
var state_request: HTTPRequest
var score_request: HTTPRequest
var layout_request: HTTPRequest
var action_request: HTTPRequest
var device_request: HTTPRequest
var title_label: Label
var passage_label: Label
var hand_label: Label
var speed_label: Label
var feedback_label: Label
var progress_label: Label
var device_button: Button
var start_button: Button
var score_view: TextureRect
var score_overlay: ScoreOverlay
var score_frame: Control
var score_content: Control
var score_crop_origin := Vector2.ZERO
var score_crop_size := Vector2.ONE
var count_tick_index := -1
var play_tick_index := -1
var count_in_display: Label
var click_player: AudioStreamPlayer
var click_high: AudioStreamWAV
var click_low: AudioStreamWAV
var device_menu: PopupMenu
var device_names: Array = []
var revision := -1
var state_pending := false
var score_pending := false
var requested_revision := -1
var layout_revision := -1
var requested_layout_revision := -1
var layout_pending := false
var score_layout: Dictionary = {}
var source_layout: Dictionary = {}
var page_images: Array[Image] = []
var score_tiles: Array[TextureRect] = []
var strip_tiles: Array = []
var current_page := -1
var requested_page := -1
var rendered_revision := -1
var action_pending := false
var last_state: Dictionary = {}
var last_state_tick := 0
var state_request_started_ms := 0
var last_audio_transport_id := -1
var follow_system_key := ""
# Opt-in diagnostic hook for the actual headless UI integration test only.
var phase0_smoke_mode := false
var phase0_last_phase := ""
var phase0_last_cursor_tick := -1
var phase0_last_lead_tick := -999
var lesson_request: HTTPRequest
var lesson_pending := false
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
var score_margin_box: MarginContainer
var hint_keyboard: Control
var mode_choice: OptionButton
var hints_toggle: CheckButton
var demo_player: Node
var listen_button: Button
var performance_review: VBoxContainer
var performance_text: Label
var weak_button: Button
var pause_sheet: Control
var skip_stage_button: Button
var placement_button: Button
var apply_tempo_button: Button
var ui_scale := 1.0
var last_seen_midi_input_count := -1
var last_seen_midi_visual_sequence := 0
var state_poll_timer: Timer

func _ready() -> void:
    phase0_smoke_mode = OS.get_cmdline_user_args().has("--phase0-smoke")
    ui_scale = _readable_ui_scale()
    _build_interface()
    demo_player = preload("res://demo_player.gd").new()
    add_child(demo_player)
    demo_player.prepared.connect(func(token: String, ready_revision: int):
        _send_action({"action":"demo_ready", "token":token, "revision":ready_revision}))
    demo_player.failed.connect(func(message: String): feedback_label.text = message)
    if phase0_smoke_mode:
        _navigate("practice")
    click_high = _make_count_click(1160.0)
    click_low = _make_count_click(770.0)
    click_player = AudioStreamPlayer.new()
    click_player.volume_db = -5.0
    add_child(click_player)
    resized.connect(_update_responsive_layout)
    _update_responsive_layout()
    state_request = _new_request(_on_state)
    score_request = _new_request(_on_score)
    layout_request = _new_request(_on_layout)
    # Verovio can take longer to engrave a dense MIDI score on the first run.
    # Do not abandon the request after the generic five-second timeout.
    layout_request.timeout = 90.0
    score_request.timeout = 45.0
    action_request = _new_request(_on_action)
    action_request.timeout = 90.0
    device_request = _new_request(_on_devices)
    library_request = _new_request(_on_library)
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
        if current_screen == "practice" or current_screen == "settings":
            _request_devices()
    )
    add_child(scan_timer)
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
    # One backend-authoritative musical clock for count-in, sound and cursor.
    # The snapshot is anchored to the midpoint of the HTTP request rather
    # than arrival time, to reduce local loopback latency bias.
    var beat: float = float(last_state.get("clock_beat", 0.0))
    if bool(last_state.get("running", false)) and not bool(last_state.get("paused", false)):
        var elapsed: float = maxf(0.0, float(Time.get_ticks_msec() - last_state_tick) / 1000.0)
        beat += elapsed * float(last_state.get("bpm", 60.0)) / 60.0
    return beat

func _update_count_in() -> void:
    if last_state.is_empty() or not bool(last_state.get("running", false)):
        count_tick_index = -999
        play_tick_index = -1
        count_in_display.visible = false
        return
    var beat: float = _transport_beat_now()
    var paused: bool = bool(last_state.get("paused", false))
    var attempt: int = int(last_state.get("transport_id", 0))
    if attempt != last_audio_transport_id:
        count_tick_index = -999
        play_tick_index = -1
        last_audio_transport_id = attempt
    if paused:
        # A paused count-in and a paused score both freeze on their last beat.
        count_tick_index = int(floor(beat + 0.00001))
        count_in_display.text = "PAUSED"
        count_in_display.visible = true
        return
    var tick: int = int(floor(beat + 0.00001))
    if tick != count_tick_index:
        count_tick_index = tick
        # The pickup may be shorter than a whole bar. Accents still follow
        # the original musical meter, not its abbreviated preparation length.
        var bar_beats: int = maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4)))))
        _count_tick(posmod(tick, bar_beats) == 0)
    if beat < 0.0:
        var bar_beats: int = maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4)))))
        count_in_display.text = "COUNT IN  ·  %d / %d" % [posmod(tick, bar_beats) + 1, bar_beats]
        count_in_display.visible = true
    else:
        count_in_display.visible = false

func _score_note_bounds(page: int) -> Dictionary:
    # Derive framing from actual engraved required notes, not the white area
    # around the page or a cursor's approximated staff bounds.
    var left: float = INF
    var right: float = -INF
    for item in score_layout.get("notes", []):
        if int(item.get("page", -1)) != page:
            continue
        var px: float = (float(item.get("x", 0.0)) - score_crop_origin.x) / maxf(score_crop_size.x, 0.00001)
        left = minf(left, px)
        right = maxf(right, px)
    if not is_finite(left) or not is_finite(right):
        for item in score_layout.get("anchors", []):
            if int(item.get("page", -1)) != page:
                continue
            var ax: float = (float(item.get("x", 0.0)) - score_crop_origin.x) / maxf(score_crop_size.x, 0.00001)
            left = minf(left, ax)
            right = maxf(right, ax)
    if not is_finite(left) or not is_finite(right):
        return {"left": 0.0, "right": 1.0}
    return {"left": clampf(left - 0.04, 0.0, 1.0),
            "right": clampf(right + 0.04, 0.0, 1.0)}


func _visible_score_noteheads() -> int:
    # Validate where real noteheads appear after the actual Godot canvas
    # transform. Cursor movement alone previously passed with a blank panel.
    if score_frame == null or score_content == null:
        return 0
    var visible := 0
    for item in score_layout.get("notes", []):
        if int(item.get("page", -1)) != current_page:
            continue
        var normalized: Vector2 = (Vector2(float(item.get("x", 0.0)), float(item.get("y", 0.0)))
            - score_crop_origin) / score_crop_size
        var xy: Vector2 = score_content.position + normalized * score_content.size
        if xy.x >= 0.0 and xy.x <= score_frame.size.x and xy.y >= 0.0 and xy.y <= score_frame.size.y:
            visible += 1
    return visible


func _layout_moving_score(delta: float = 0.0) -> void:
    if score_view.texture == null or score_frame == null or score_content == null:
        return
    score_overlay.preparation_clefs = score_layout.get("staff_clefs", {})
    var viewport: Vector2 = score_frame.size
    var image: Vector2 = score_overlay.image_size
    if viewport.x < 10.0 or viewport.y < 10.0 or image.x <= 0.0 or image.y <= 0.0:
        return
    var bounds: Dictionary = _score_note_bounds(current_page)
    var focus_left: float = float(bounds["left"])
    var focus_right: float = float(bounds["right"])
    var focus_span: float = maxf(0.18, focus_right - focus_left)
    # Use one stable zoom for stopped, count-in and playing. Earlier versions
    # changed to a much larger scale on Start and then panned empty page space
    # across the entire visible panel.
    var width_scale: float = viewport.x * 0.83 / (image.x * focus_span)
    if score_layout.has("strip_size"):
        # Long passages stay readable: never shrink an entire composition to
        # the viewport. Tiles scroll through at a staff-based stable scale.
        width_scale = INF
    var height_scale: float = viewport.y * 0.77 / image.y
    var scale: float = maxf(0.01, minf(width_scale, height_scale))
    var displayed_width: float = image.x * scale
    var displayed_height: float = image.y * scale
    score_content.size = Vector2(displayed_width, displayed_height)
    for i in range(score_tiles.size()):
        var rect: Rect2 = strip_tiles[i]["rect"]
        score_tiles[i].position = rect.position * scale
        score_tiles[i].size = rect.size * scale
    var midpoint_x: float = (focus_left + focus_right) * 0.5
    var target_x: float = viewport.x * 0.5 - midpoint_x * displayed_width
    if score_layout.has("strip_size") and not score_layout.get("notes", []).is_empty():
        target_x = viewport.x * 0.04
    if score_overlay.showing and not score_overlay.cursor.is_empty():
        var note_x: float = (float(score_overlay.cursor.get("x", 0.0))
            - score_crop_origin.x) / maxf(score_crop_size.x, 0.00001)
        target_x = viewport.x * 0.42 - note_x * displayed_width
    var target_y: float = (viewport.y - displayed_height) * 0.5
    # The PNG is ink-cropped; centering it vertically keeps both staves on
    # screen. Do not re-center using the approximate notehead staff bounds.
    var target := Vector2(target_x, target_y)
    var key: String = "%d/%d/%d" % [revision, current_page, int(last_state.get("transport_id", 0))]
    # This is a musical projection, not a camera chasing a moving object.
    # Smoothing introduces tempo-dependent lag; clamps let the rule wander.
    score_content.position = target
    follow_system_key = key

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

func _readable_ui_scale() -> float:
    # Pixel fonts stayed tiny at 2048x1280 fullscreen. Increase the interface
    # text and touch targets with the actual window size, not the score zoom.
    # At 800x600 use the existing compact layout instead of shrinking type.
    return clampf(minf(size.x / 1150.0, size.y / 760.0), 1.0, 1.75)

func _ui_font(base: int) -> int:
    # Keep important labels at a readable physical pixel size. The earlier
    # 13-15px defaults remained miniature at desktop/fullscreen resolutions.
    var legibility := 1.35 if size.x >= 1100.0 else 1.12
    return maxi(16, int(round(float(base) * ui_scale * legibility)))

func _resize_ui_fonts(node: Node) -> void:
    if node is Control and node.has_meta("ui_font_base"):
        (node as Control).add_theme_font_size_override(
            "font_size", _ui_font(int(node.get_meta("ui_font_base"))))
    for child in node.get_children():
        _resize_ui_fonts(child)

func _label(text: String, size: int, color: Color, bold := false) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_color_override("font_color", color)
    label.set_meta("ui_font_base", size)
    label.add_theme_font_size_override("font_size", _ui_font(size))
    var font := SystemFont.new()
    font.font_names = PackedStringArray(["Inter", "Noto Sans", "DejaVu Sans"])
    font.font_weight = 700 if bold else 400
    label.add_theme_font_override("font", font)
    label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    return label

func _button(label: String, callback: Callable, primary := false) -> Button:
    var button := Button.new()
    button.text = label
    # Long song titles must not force a container wider than the viewport.
    button.clip_text = true
    # Short controls must fit their text; library rows override width.
    var text_width: float = theme.default_font.get_string_size(label, HORIZONTAL_ALIGNMENT_LEFT, -1, _ui_font(15)).x
    button.custom_minimum_size = Vector2(clampf(text_width + 34 * ui_scale, 110, 380), 50 * ui_scale)
    var style := StyleBoxFlat.new()
    style.bg_color = Design.PINE if primary else Design.PANEL
    style.set_corner_radius_all(8)
    style.set_border_width_all(1)
    style.border_color = Design.SAGE if primary else Color(Design.SAGE, .4)
    style.content_margin_left = 18 * ui_scale
    style.content_margin_right = 18 * ui_scale
    button.add_theme_stylebox_override("normal", style)
    var hover := style.duplicate() as StyleBoxFlat
    hover.bg_color = Design.SAGE if primary else Design.PINE
    button.add_theme_stylebox_override("hover", hover)
    button.add_theme_stylebox_override("pressed", hover)
    var disabled_style := style.duplicate() as StyleBoxFlat
    disabled_style.bg_color = Design.PANEL
    button.add_theme_stylebox_override("disabled", disabled_style)
    var focus := style.duplicate() as StyleBoxFlat
    focus.set_border_width_all(2)
    focus.border_color = ACCENT
    button.add_theme_stylebox_override("focus", focus)
    button.add_theme_color_override("font_color", INK)
    button.add_theme_color_override("font_hover_color", INK.lightened(.15))
    button.add_theme_color_override("font_disabled_color", MUTED)
    button.set_meta("ui_font_base", 15)
    button.add_theme_font_size_override("font_size", _ui_font(15))
    button.pressed.connect(callback)
    return button

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
    var style := StyleBoxFlat.new()
    style.bg_color = WHITE
    style.set_corner_radius_all(10)
    style.set_border_width_all(1)
    style.border_color = Color(Design.SAGE, .32)
    panel.add_theme_stylebox_override("panel", style)
    return panel

func _card_body(panel: PanelContainer, margin: int = 28) -> MarginContainer:
    var body := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        body.add_theme_constant_override("margin_" + side, margin)
    panel.add_child(body)
    return body

func _navigate(screen: String) -> void:
    if screen == "settings" and current_screen != "settings":
        settings_return_screen = current_screen
    if screen != "practice" and (current_screen == "practice" or screen in ["home", "library"]):
        var phase: String = str(last_state.get("phase", ""))
        var starting: bool = action_pending and last_post_path == "/control" and last_control_action in ["start", "restart", "resume", "score_ready", "learn", "learn_retry", "practice", "listen", "perform"]
        if screen in ["settings", "lesson"]:
            if phase in ["count_in", "playing", "guided_wait", "feedback", "recovering", "loading"] or starting:
                _send_action({"action": "pause"})
        elif phase in ["count_in", "playing", "guided_wait", "guided_complete", "disconnected", "paused", "feedback", "recovering", "loading"] or starting:
            _send_action({"action": "stop"})
    current_screen = screen
    if pause_sheet != null:
        pause_sheet.present(last_state if screen == "practice" else {})
    for key in screens:
        (screens[key] as Control).visible = str(key) == screen
    if screen == "library":
        _request_library()
    elif screen == "settings":
        tempo_setting.set_value_no_signal(float(last_state.get("target_bpm", 40)))
        _request_settings()
        _request_devices()
    elif screen == "lesson":
        _request_lesson()

func _go_back() -> void:
    _navigate(settings_return_screen if current_screen == "settings" else "practice")

func _build_interface() -> void:
    theme = Design.create()
    theme.default_font_size = _ui_font(16)
    var background := ColorRect.new()
    background.color = PAPER
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    background.mouse_filter = Control.MOUSE_FILTER_IGNORE
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
    home_nav.add_child(_button("Settings", func(): _navigate("settings")))
    home_nav.add_child(_button("Quit", func(): get_tree().quit()))
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
    var library_layout := _stack(22)
    library_page.add_child(library_layout)
    var library_head := HBoxContainer.new()
    library_layout.add_child(library_head)
    library_head.add_child(_button("← Home", func(): _navigate("home")))
    library_head.add_child(_space())
    library_head.add_child(_button("Settings", func(): _navigate("settings")))
    library_layout.add_child(_label("Your music", 39, INK, true))
    library_path_label = _label("Looking for scores…", 15, MUTED)
    library_path_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    library_path_label.clip_text = true
    library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    library_layout.add_child(library_path_label)
    var library_controls := HBoxContainer.new()
    library_controls.add_theme_constant_override("separation", 12)
    library_layout.add_child(library_controls)
    library_search = LineEdit.new()
    library_search.placeholder_text = "Search your music"
    library_search.custom_minimum_size = Vector2(0, 48)
    library_search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    library_search.text_changed.connect(func(_text: String): _populate_library())
    library_controls.add_child(library_search)
    library_controls.add_child(_button("Refresh", _request_library))
    var library_panel := _card()
    library_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    library_layout.add_child(library_panel)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    _card_body(library_panel, 22).add_child(scroll)
    library_rows = _stack(6)
    library_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(library_rows)
    library_message = _label("", 14, MUTED)
    library_layout.add_child(library_message)

    # Settings are explicit, and keep the practice screen free from controls.
    var settings_page := _screen("Settings")
    screens["settings"] = settings_page
    var settings_scroll := ScrollContainer.new()
    settings_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    settings_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    settings_page.add_child(settings_scroll)
    var settings_layout := _stack(21)
    settings_layout.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    settings_scroll.add_child(settings_layout)
    var settings_head := HBoxContainer.new()
    settings_layout.add_child(settings_head)
    settings_head.add_child(_button("← Back", _go_back))
    settings_head.add_child(_space())
    settings_layout.add_child(_label("Settings", 39, INK, true))
    settings_layout.add_child(_label("Your piano, music folder and practice preferences.", 16, MUTED))
    var settings_card := _card()
    settings_layout.add_child(settings_card)
    var settings_content := _stack(24)
    _card_body(settings_card, 32).add_child(settings_content)
    settings_content.add_child(_label("MUSIC LIBRARY", 13, ACCENT, true))
    settings_content.add_child(_label("Piano Teacher scans this folder and its subfolders automatically.", 15, MUTED))
    var folder_row := BoxContainer.new()
    folder_controls = folder_row
    folder_row.add_theme_constant_override("separation", 12)
    settings_content.add_child(folder_row)
    folder_edit = LineEdit.new()
    folder_edit.custom_minimum_size = Vector2(0, 48)
    folder_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    folder_edit.placeholder_text = "~/Music/Piano Teacher"
    folder_edit.add_theme_color_override("font_color", INK)
    folder_edit.add_theme_color_override("font_placeholder_color", MUTED)
    folder_edit.text_submitted.connect(func(_text: String): _save_folder())
    folder_row.add_child(folder_edit)
    folder_row.add_child(_button("Browse…", _browse_folder))
    folder_row.add_child(_button("Save folder", _save_folder, true))
    settings_content.add_child(_label("PIANO INPUT", 13, ACCENT, true))
    var device_row := HBoxContainer.new()
    device_row.add_theme_constant_override("separation", 12)
    settings_content.add_child(device_row)
    device_button = _button("Choose USB MIDI piano", _show_devices)
    device_row.add_child(device_button)
    device_row.add_child(_button("Refresh devices", _request_devices))
    device_row.add_child(_space())
    input_activity_label = _label("Connect your MIDI piano, then play a note to check input.", 15, MUTED)
    settings_content.add_child(input_activity_label)
    settings_content.add_child(_label("PRACTICE", 13, ACCENT, true))
    var tempo_row := HBoxContainer.new()
    tempo_row.add_theme_constant_override("separation", 12)
    settings_content.add_child(tempo_row)
    tempo_row.add_child(_label("Target tempo", 16, INK))
    tempo_setting = SpinBox.new()
    tempo_setting.min_value = 12
    tempo_setting.max_value = 300
    tempo_setting.step = 1
    tempo_setting.suffix = " BPM"
    tempo_setting.custom_minimum_size = Vector2(160, 44)
    tempo_row.add_child(tempo_setting)
    apply_tempo_button = _button("Apply tempo", func(): _send_action({"action": "tempo", "bpm": int(tempo_setting.value)}))
    tempo_row.add_child(apply_tempo_button)
    metronome_toggle = CheckButton.new()
    metronome_toggle.text = "Metronome during practice · count-in always audible"
    metronome_toggle.toggled.connect(func(enabled: bool): _send_post("/settings", {"metronome": enabled}))
    settings_content.add_child(metronome_toggle)
    settings_content.add_child(_label("DISPLAY", 13, ACCENT, true))
    fullscreen_toggle = CheckButton.new()
    fullscreen_toggle.text = "Fullscreen application  (F11 to toggle)"
    fullscreen_toggle.button_pressed = true
    fullscreen_toggle.toggled.connect(_on_fullscreen_toggle)
    fullscreen_toggle.add_theme_color_override("font_color", INK)
    fullscreen_toggle.add_theme_color_override("font_hover_color", INK)
    settings_content.add_child(fullscreen_toggle)
    settings_message = _label("", 14, MUTED)
    settings_layout.add_child(settings_message)

    # Practice: standard engraving remains the central and dominant element.
    var practice_page := _screen("Practice")
    screens["practice"] = practice_page
    var practice_layout := _stack(19)
    practice_layout_box = practice_layout
    practice_page.add_child(practice_layout)
    # Navigation and lesson metadata are separate rows. A long title or
    # small viewport must never squeeze BPM into a one-letter column.
    practice_navigation = HFlowContainer.new()
    practice_navigation.add_theme_constant_override("h_separation", 10)
    practice_navigation.add_theme_constant_override("v_separation", 8)
    practice_navigation.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(practice_navigation)
    practice_navigation.add_child(_button("← Library", func(): _navigate("library")))
    mode_choice = OptionButton.new()
    mode_choice.disabled = true
    mode_choice.fit_to_longest_item = false
    mode_choice.add_item("Learn notes")
    mode_choice.add_item("Practice rhythm")
    mode_choice.add_item("Perform passage")
    mode_choice.add_item("Perform whole piece")
    mode_choice.custom_minimum_size = Vector2(210 * ui_scale, 48 * ui_scale)
    mode_choice.add_theme_font_size_override("font_size", _ui_font(15))
    mode_choice.item_selected.connect(func(index: int):
        _send_action({"action": "learn" if index == 0 else "practice" if index == 1 else "perform", "scope":"whole" if index == 3 else "current"}))
    practice_navigation.add_child(mode_choice)
    listen_button = _button("Listen", func(): _send_action({"action":"listen"}))
    practice_navigation.add_child(listen_button)
    hints_toggle = CheckButton.new()
    hints_toggle.text = "Hints"
    hints_toggle.add_theme_font_size_override("font_size", _ui_font(15))
    hints_toggle.tooltip_text = "Keep key hints visible while learning notes"
    hints_toggle.toggled.connect(func(enabled: bool): _send_action({"action":"hints", "enabled":enabled}))
    practice_navigation.add_child(hints_toggle)
    practice_navigation.add_child(_button("Lesson path", func(): _navigate("lesson")))
    practice_settings_button = _button("Settings", func(): _navigate("settings"))
    practice_navigation.add_child(practice_settings_button)

    practice_header = HBoxContainer.new()
    practice_header.add_theme_constant_override("separation", 20)
    practice_layout.add_child(practice_header)
    var heading := _stack(2)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    practice_header.add_child(heading)
    title_label = _label("Piano Teacher", 27, INK, true)
    title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(title_label)
    passage_label = _label("", 14, MUTED)
    passage_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    passage_label.clip_text = true
    heading.add_child(passage_label)
    var tempo := _stack(2)
    tempo.custom_minimum_size = Vector2(190, 0)
    tempo.size_flags_horizontal = Control.SIZE_SHRINK_END
    practice_header.add_child(tempo)
    speed_label = _label("-- BPM", 20, INK)
    speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(speed_label)
    hand_label = _label("", 13, MUTED)
    hand_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    hand_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(hand_label)
    lesson_info_label = _label("", 17, INK)
    lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_layout.add_child(lesson_info_label)
    practice_playback_banner = _label("", 18, Color("#F6BC70"), true)
    practice_playback_banner.visible = false
    practice_playback_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_layout.add_child(practice_playback_banner)
    var score_panel := _card()
    practice_score_panel = score_panel
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(score_panel)
    var score_margin := _card_body(score_panel, 26)
    score_margin_box = score_margin
    var score_region := VBoxContainer.new()
    score_region.add_theme_constant_override("separation", 8)
    score_margin.add_child(score_region)
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 210)
    score_region.add_child(score_area)
    score_frame = score_area
    score_frame.clip_contents = true
    score_frame.resized.connect(_layout_moving_score)
    score_content = Control.new()
    score_content.mouse_filter = Control.MOUSE_FILTER_IGNORE
    score_frame.add_child(score_content)
    score_view = TextureRect.new()
    score_view.mouse_filter = Control.MOUSE_FILTER_IGNORE
    score_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
    score_view.stretch_mode = TextureRect.STRETCH_SCALE
    score_content.add_child(score_view)
    score_overlay = ScoreOverlay.new()
    score_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
    score_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_content.add_child(score_overlay)
    # Score status must live inside the score panel: feedback_label is replaced
    # by regular state polling and cannot hold engraving errors reliably.
    score_status_panel = CenterContainer.new()
    score_status_panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_area.add_child(score_status_panel)
    var status_content := _stack(12)
    status_content.custom_minimum_size = Vector2(280, 85)
    status_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    score_status_panel.add_child(status_content)
    score_status_label = _label("Choose a piece from your library", 18, MUTED)
    score_status_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    score_status_label.clip_text = true
    status_content.add_child(score_status_label)
    score_retry_button = _button("Retry score", _retry_score)
    score_retry_button.visible = false
    status_content.add_child(score_retry_button)
    # A compact, unobtrusive cue. A huge centred numeral hid the movement.
    count_in_display = _label("GET READY", 18, ACCENT, true)
    count_in_display.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
    count_in_display.vertical_alignment = VERTICAL_ALIGNMENT_TOP
    count_in_display.mouse_filter = Control.MOUSE_FILTER_IGNORE
    count_in_display.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
    count_in_display.offset_left = 22.0
    count_in_display.offset_right = -22.0
    count_in_display.offset_top = 12.0
    count_in_display.offset_bottom = 52.0
    count_in_display.visible = false
    score_frame.add_child(count_in_display)
    hint_keyboard = HintKeyboard.new()
    score_region.add_child(hint_keyboard)
    practice_progress = ProgressBar.new()
    practice_progress.show_percentage = false
    practice_progress.max_value = 1.0
    practice_progress.custom_minimum_size = Vector2(0, 9)
    practice_progress.add_theme_stylebox_override("background", Design.surface(Design.PANEL, 3))
    practice_progress.add_theme_stylebox_override("fill", Design.surface(Design.SAGE, 3))
    (practice_progress.get_theme_stylebox("background") as StyleBoxFlat).set_content_margin_all(0)
    (practice_progress.get_theme_stylebox("fill") as StyleBoxFlat).set_content_margin_all(0)
    practice_layout.add_child(practice_progress)
    var information := VBoxContainer.new()
    information.add_theme_constant_override("separation", 4)
    practice_layout.add_child(information)
    progress_label = _label("", 17, INK)
    progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    information.add_child(progress_label)
    feedback_label = _label("Ready", 17, MUTED)
    feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    feedback_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    information.add_child(feedback_label)
    performance_review = VBoxContainer.new()
    performance_review.visible = false
    information.add_child(performance_review)
    performance_text = _label("", 14, INK)
    performance_review.add_child(performance_text)
    weak_button = _button("Practice weakest section", func(): _send_action({"action":"practice_weak"}))
    performance_review.add_child(weak_button)
    # Flow containers wrap whole readable buttons instead of clipping labels
    # when the practice window is narrow or the user uses larger UI fonts.
    var controls := HFlowContainer.new()
    practice_controls = controls
    controls.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    controls.alignment = FlowContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("h_separation", 12)
    controls.add_theme_constant_override("v_separation", 9)
    practice_layout.add_child(controls)
    controls.add_child(_button("Previous", func(): _send_action({"action": "previous"})))
    start_button = _button("Start  ·  Space", _toggle_playing, true)
    start_button.custom_minimum_size = Vector2(174 * ui_scale, 56 * ui_scale)
    controls.add_child(start_button)
    stop_button = _button("Stop", func(): _send_action({"action": "stop"}))
    stop_button.tooltip_text = "End this attempt · S"
    stop_button.disabled = true
    controls.add_child(stop_button)
    controls.add_child(_button("Restart", _restart_practice))
    controls.add_child(_button("Next", func(): _send_action({"action": "next"})))
    _build_lesson_screen()

    folder_dialog = FileDialog.new()
    folder_dialog.access = FileDialog.ACCESS_FILESYSTEM
    folder_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
    folder_dialog.use_native_dialog = true
    folder_dialog.dir_selected.connect(func(path: String):
        folder_edit.text = path
        _save_folder()
    )
    add_child(folder_dialog)
    device_menu = PopupMenu.new()
    device_menu.id_pressed.connect(_choose_device)
    add_child(device_menu)
    pause_sheet = preload("res://pause_sheet.gd").new()
    add_child(pause_sheet)
    pause_sheet.chosen.connect(func(command: Dictionary):
        if command.get("action") == "exit":
            _navigate("library")
        else:
            _send_action(command))
    _navigate("home")
    _refresh_score_status()

func _update_responsive_layout() -> void:
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
    if folder_controls != null:
        folder_controls.vertical = width < 1000
    if practice_header == null:
        return
    practice_header.add_theme_constant_override("separation", 16)
    practice_navigation.add_theme_constant_override("h_separation", 10 if width >= 1000.0 else 7)
    practice_navigation.add_theme_constant_override("v_separation", 7)
    if mode_choice != null:
        mode_choice.add_theme_font_size_override("font_size", _ui_font(15))
        mode_choice.custom_minimum_size = Vector2(minf(235.0, maxf(170.0, width * 0.22)), 50.0)
    if hints_toggle != null:
        hints_toggle.add_theme_font_size_override("font_size", _ui_font(15))
    for child in practice_navigation.get_children():
        if child is Button and child != mode_choice and child != hints_toggle:
            var button := child as Button
            var font_size := _ui_font(15)
            button.add_theme_font_size_override("font_size", font_size)
            var measured: float = button.get_theme_font("font").get_string_size(
                button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
            button.custom_minimum_size = Vector2(maxf(110.0, measured + 36.0), 50.0)
            button.clip_text = false
    if practice_controls != null:
        practice_layout_box.add_theme_constant_override("separation", 10 if compact else 14)
        score_frame.custom_minimum_size.y = 170 if compact else 220
        for side in ["left", "right", "top", "bottom"]:
            score_margin_box.add_theme_constant_override("margin_" + side, 12 if compact else 20)
        for child in practice_controls.get_children():
            if child is Button:
                var button := child as Button
                var font_size := _ui_font(15)
                button.add_theme_font_size_override("font_size", font_size)
                var measured: float = button.get_theme_font("font").get_string_size(
                    button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                button.custom_minimum_size = Vector2(
                    maxf(132.0, measured + 38.0), 51.0 if compact else 57.0)
                button.clip_text = false
        title_label.add_theme_font_size_override("font_size", _ui_font(25))
        passage_label.add_theme_font_size_override("font_size", _ui_font(15))
        speed_label.add_theme_font_size_override("font_size", _ui_font(19))
        hand_label.add_theme_font_size_override("font_size", _ui_font(15))
        progress_label.add_theme_font_size_override("font_size", _ui_font(16))
        feedback_label.add_theme_font_size_override("font_size", _ui_font(17))
        lesson_info_label.add_theme_font_size_override("font_size", _ui_font(16))
        practice_playback_banner.add_theme_font_size_override("font_size", _ui_font(17))

func _build_lesson_screen() -> void:
    var page := _screen("Lesson")
    screens["lesson"] = page
    var content := _stack(20)
    page.add_child(content)
    var navigation := HBoxContainer.new()
    content.add_child(navigation)
    navigation.add_child(_button("← Practice", _go_back))
    navigation.add_child(_space())
    navigation.add_child(_label("Piano Teacher", 18, INK, true))
    content.add_child(_label("Your lesson path", 34, INK, true))
    lesson_summary = _label("Open a piece to see its lessons.", 18, INK)
    content.add_child(lesson_summary)
    lesson_description = _label("", 16, MUTED)
    content.add_child(lesson_description)
    var hand_row := HBoxContainer.new()
    hand_row.add_theme_constant_override("separation", 12)
    content.add_child(hand_row)
    for hand in ["right", "left", "both"]:
        var button := _button(hand.capitalize() + (" hands" if hand == "both" else " hand"),
            func():
                _send_action({"action": "hand", "hand": hand})
                _navigate("practice")
        )
        hand_buttons[hand] = button
        hand_row.add_child(button)
    var course_choices := HBoxContainer.new()
    course_choices.add_theme_constant_override("separation", 8)
    content.add_child(course_choices)
    skip_stage_button = _button("Skip this step · no mastery", func(): _send_action({"action":"skip_stage", "reason":"Learner chose to skip this step"}))
    skip_stage_button.custom_minimum_size.x = 250
    course_choices.add_child(skip_stage_button)
    placement_button = _button("Try original notes", func(): _send_action({"action":"place_original"}))
    course_choices.add_child(placement_button)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    content.add_child(scroll)
    lesson_rows = _stack(10)
    lesson_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(lesson_rows)

func _request_lesson() -> void:
    if lesson_request == null or lesson_pending or not bool(last_state.get("loaded", false)):
        return
    lesson_pending = true
    if lesson_request.request(URL + "/lesson") != OK:
        lesson_pending = false

func _on_lesson(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    lesson_pending = false
    if code != 200:
        lesson_summary.text = _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    lesson_summary.text = "%d of %d stages completed · three clean performances at your target tempo" % [
        int(parsed.get("completed_steps", 0)), int(parsed.get("total_steps", 0))]
    lesson_description.text = "Learn each passage, bring the hands together, connect adjoining passages, then play the complete piece."
    for child in lesson_rows.get_children():
        lesson_rows.remove_child(child)
        child.queue_free()
    var trouble: Array = parsed.get("trouble_spots", [])
    if not trouble.is_empty():
        lesson_rows.add_child(_label("Your trouble spots", 18, INK, true))
        for spot in trouble:
            var stage_key: String = str(spot.get("stage_key", ""))
            var from_beat: float = float(spot.get("start_beat", 0))
            var revisit := _button("Revisit bars %d–%d" % [int(spot.get("first_bar", 1)),int(spot.get("last_bar", 1))],
                func(): _send_action({"action":"revisit_trouble", "stage_key":stage_key, "start_beat":from_beat}))
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
        var row := _stack(4)
        var status := "Completed" if bool(group["complete"]) else "Current passage" if bool(group["current"]) else str(group["kind"]).capitalize()
        row.add_child(_label("%s · Measures %d–%d" % [status, int(group["first"]), int(group["last"])], 18,
            ACCENT if bool(group["current"]) else INK, bool(group["current"])))
        var detail: String = " → ".join(group["labels"])
        row.tooltip_text = detail
        if bool(group["current"]):
            row.add_child(_label(detail, 14, MUTED))
        lesson_rows.add_child(row)

func _refresh_score_status() -> void:
    if score_status_panel == null or score_view == null:
        return
    score_status_panel.visible = score_view.texture == null
    if not score_status_panel.visible:
        return
    if not score_error.is_empty():
        score_status_label.text = "Unable to display sheet music:\n" + score_error
        score_retry_button.visible = true
    elif bool(last_state.get("loaded", false)):
        score_status_label.text = "Preparing sheet music…"
        score_retry_button.visible = false
    else:
        score_status_label.text = "Choose a piece from your library"
        score_retry_button.visible = false

func _score_failed(message: String) -> void:
    if phase0_smoke_mode:
        print("PHASE0_SCORE_ERROR:", message)
    score_error = message
    feedback_label.text = message
    _refresh_score_status()

func _retry_score() -> void:
    if not bool(last_state.get("loaded", false)) or layout_pending or score_pending:
        return
    score_error = ""
    score_layout = {}
    layout_revision = -1
    rendered_revision = -1
    current_page = -1
    score_view.texture = null
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

func _populate_library() -> void:
    if library_rows == null:
        return
    for child in library_rows.get_children():
        library_rows.remove_child(child)
        child.queue_free()
    var pieces: Array = library_info.get("pieces", [])
    var warmups: Array = library_info.get("warmups", [])
    var query := library_search.text.strip_edges().to_lower()
    var visible := 0
    for section in [{"title": "BUILT-IN WARM-UPS", "entries": warmups},
                    {"title": "YOUR MUSIC", "entries": pieces}]:
        var section_added := false
        for entry in section.entries:
            var title: String = str(entry.get("title", "Untitled"))
            var location: String = str(entry.get("folder", ""))
            var focus: String = str(entry.get("focus", ""))
            if not query.is_empty() and not (title + " " + location + " " + focus).to_lower().contains(query):
                continue
            if not section_added:
                library_rows.add_child(_label(str(section.title), 13, ACCENT, true))
                section_added = true
            var identifier: String = str(entry.get("id", ""))
            var format_name: String = str(entry.get("format", ""))
            var hint: String = ("%d BPM · %s" % [int(entry.get("bpm", 0)), focus]
                if not focus.is_empty() else
                location if not location.is_empty() else "Music folder")
            var button := _button("%s     ·     %s     ·     %s" % [title, format_name, hint], func(): _open_library_piece(identifier))
            button.alignment = HORIZONTAL_ALIGNMENT_LEFT
            button.custom_minimum_size = Vector2(0, 58 * ui_scale)
            button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
            button.tooltip_text = str(entry.get("description", ""))
            library_rows.add_child(button)
            visible += 1
    var issue: String = str(library_info.get("error", ""))
    if not library_error.is_empty():
        library_message.text = library_error
    elif not issue.is_empty():
        library_message.text = issue
    elif pieces.is_empty() and warmups.is_empty():
        library_message.text = "No scores yet. Add .mid, .midi or MusicXML files to this folder."
    elif visible == 0:
        library_message.text = "No matching scores."
    else:
        library_message.text = "%d personal files  ·  %d built-in warm-ups  ·  %d shown" % [pieces.size(), warmups.size(), visible]

func _open_library_piece(identifier: String) -> void:
    library_error = ""
    library_message.text = "Opening score…"
    _send_post("/library/open", {"id": identifier})

func _resume_last() -> void:
    var identifier: String = str(library_info.get("last_piece", ""))
    if not identifier.is_empty():
        _open_library_piece(identifier)

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
    if not state_pending and not action_pending:
        state_pending = true
        state_request_started_ms = Time.get_ticks_msec()
        if state_request.request(URL + "/state") != OK:
            state_pending = false

func _process(_delta: float) -> void:
    # Animate short-lived hit pulses between HTTP state samples.
    var ticks: int = Time.get_ticks_msec()
    for index in range(score_overlay.hit_pulses.size() - 1, -1, -1):
        if int(score_overlay.hit_pulses[index].get("until_ms", 0)) <= ticks:
            score_overlay.hit_pulses.remove_at(index)
    for index in range(score_overlay.wrong_ghosts.size() - 1, -1, -1):
        if int(score_overlay.wrong_ghosts[index].get("until_ms", 0)) <= ticks:
            score_overlay.wrong_ghosts.remove_at(index)
    if not score_overlay.hit_pulses.is_empty() or not score_overlay.wrong_ghosts.is_empty():
        score_overlay.queue_redraw()
    apply_tempo_button.disabled = action_pending
    _update_count_in()
    if str(last_state.get("mode", "practice")) == "learn":
        _layout_guided_score()
        return
    score_overlay.guided_active = false
    if last_state.is_empty() or not bool(last_state.get("running", false)) or layout_revision != revision:
        if score_overlay.showing:
            score_overlay.showing = false
            score_overlay.queue_redraw()
            if str(last_state.get("phase", "ready")) not in ["feedback", "recovering", "loading", "paused"]:
                _layout_moving_score(_delta)
        elif str(last_state.get("phase", "ready")) in ["ready", "disconnected"]:
            _layout_moving_score(_delta)
        return
    # Count-in uses negative beats on the same spacing as the opening notes.
    # position advances at BPM regardless of the user's MIDI performance.
    var clock: float = _transport_beat_now()
    var play_from: float = float(last_state.get("play_from_beat", 0.0))
    var beat: float = clampf(play_from + maxf(0.0, clock), 0.0, float(last_state.get("duration_beats", 1.0)))
    var active: bool = not bool(last_state.get("paused", false))
    var cursor: Dictionary = _position_at_beat(beat)
    if cursor.is_empty():
        score_overlay.showing = false
        score_overlay.queue_redraw()
        return
    var page: int = int(cursor.get("page", 0))
    if current_page != page or rendered_revision != revision:
        _request_score(page)
        score_overlay.showing = false
        score_overlay.queue_redraw()
        return
    # A fixed origin for the blank measure is necessary: rebuilding it
    # from the changing cursor made the measure jump/disappear at downbeat.
    var initial_cursor: Dictionary = _position_at_beat(play_from)
    score_overlay.lead_first = {}
    score_overlay.lead_width_px = 0.0
    score_overlay.lead_staff_lines = []
    if int(initial_cursor.get("page", -1)) == current_page:
        var lead_beats: float = maxf(0.5, float(last_state.get("count_in_beats", 3)))
        var beat_width: float = _beat_width_at(play_from)
        score_overlay.lead_first = initial_cursor
        score_overlay.lead_beats = lead_beats
        score_overlay.lead_meter = last_state.get("count_in_meter", [4, 4])
        for system in score_layout.get("systems", []):
            if int(system.get("page", -1)) == current_page and str(system.get("system", "")) == str(initial_cursor.get("system", "")):
                score_overlay.lead_staff_lines = system.get("staff_lines", [])
                break
        score_overlay.lead_width_px = lead_beats * beat_width / score_crop_size.x * score_content.size.x
        if clock < 0.0:
            cursor["x"] = float(initial_cursor.get("x", 0.0)) + clock * beat_width
    score_overlay.cursor = cursor
    score_overlay.showing = true
    score_overlay.transport_active = active
    _layout_moving_score(_delta)
    if phase0_smoke_mode and clock < 0.0:
        var lead_tick: int = int(floor(clock * 4.0))
        if lead_tick != phase0_last_lead_tick:
            phase0_last_lead_tick = lead_tick
            var cursor_screen_x: float = score_content.position.x + (
                (float(cursor.get("x", 0.0)) - score_crop_origin.x)
                / score_crop_size.x * score_content.size.x)
            print("PHASE0_LEAD_BEAT:", clock, " CONTENT_X:", score_content.position.x,
                  " CURSOR_X:", cursor_screen_x, " VISIBLE:", score_overlay.showing)
    if phase0_smoke_mode and active and clock >= 0.0:
        print("PHASE0_VISIBLE_NOTES:", _visible_score_noteheads(),
              " PANEL_WIDTH:", score_frame.size.x,
              " CONTENT_X:", score_content.position.x)
    if phase0_smoke_mode and active and clock >= 0.0:
        var cursor_tick: int = int(floor(beat * 4.0))
        if cursor_tick > phase0_last_cursor_tick:
            phase0_last_cursor_tick = cursor_tick
            var cropped_x: float = (float(cursor.get("x", 0.0)) - score_crop_origin.x) / score_crop_size.x
            var screen_x: float = score_content.position.x + cropped_x * score_content.size.x
            print("PHASE0_CURSOR_BEAT:", beat, " SCREEN_X:", screen_x,
                  " VISIBLE:", score_overlay.showing, " CONTENT_X:", score_content.position.x)
    score_overlay.queue_redraw()

func _layout_guided_score() -> void:
    score_overlay.guided_active = true
    score_overlay.lead_first = {}
    score_overlay.lead_width_px = 0.0
    score_overlay.showing = false
    if layout_revision != revision or rendered_revision != revision or score_view.texture == null:
        score_overlay.queue_redraw()
        return
    var teaching: Dictionary = last_state.get("teaching", {}) if last_state.get("teaching") is Dictionary else {}
    var expected: Array = teaching.get("expected_notes", [])
    if not expected.is_empty():
        var cursor: Dictionary = _position_at_beat(float(expected[0].get("beat", 0.0)))
        if not cursor.is_empty():
            score_overlay.cursor = cursor
            score_overlay.showing = true
    elif str(last_state.get("phase", "")) == "guided_complete":
        score_overlay.queue_redraw()
        return # Keep the finished idea still while the student chooses rhythm.
    _layout_moving_score()
    score_overlay.queue_redraw()

func _beat_width_at(beat: float) -> float:
    var points: Array = score_layout.get("anchors", [])
    for index in range(points.size() - 1):
        var left: Dictionary = points[index]
        var right: Dictionary = points[index + 1]
        if float(right.get("beat", 0.0)) <= beat + .000001:
            continue
        var span: float = float(right.get("beat", 0.0)) - float(left.get("beat", 0.0))
        if span > 0.0 and float(right.x) > float(left.x):
            return (float(right.x) - float(left.x)) / span
    return .01

func _position_at_beat(beat: float) -> Dictionary:
    var points: Array = score_layout.get("anchors", [])
    if points.is_empty():
        return {}
    var at: int = 0
    for i in range(points.size()):
        if float(points[i].get("beat", 0.0)) <= beat + 0.000001:
            at = i
        else:
            break
    var left: Dictionary = points[at]
    var position: Dictionary = left.duplicate()
    if at + 1 < points.size():
        var right: Dictionary = points[at + 1]
        if int(left.get("page", 0)) == int(right.get("page", 0)) and str(left.get("system", "")) == str(right.get("system", "")):
            var span: float = float(right.get("beat", 0.0)) - float(left.get("beat", 0.0))
            if span > 0:
                var fraction: float = clampf((beat - float(left.get("beat", 0.0))) / span, 0.0, 1.0)
                position["x"] = lerpf(float(left["x"]), float(right["x"]), fraction)
    return position

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
    var old_phase: String = str(last_state.get("phase", ""))
    var old_revision: int = int(last_state.get("revision", -1))
    var total_input_attacks: int = int(parsed.get("midi_input_count", 0))
    var fresh_piano_key: bool = last_seen_midi_input_count >= 0 and total_input_attacks > last_seen_midi_input_count
    last_seen_midi_input_count = total_input_attacks
    last_state = parsed
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
    last_state_tick = int((started_ms + Time.get_ticks_msec()) / 2.0)
    if not bool(parsed.get("loaded", false)):
        mode_choice.disabled = true
        feedback_label.text = str(parsed.get("feedback", "Open a score"))
        _refresh_score_status()
        return
    title_label.text = str(parsed.get("title", "Piano Teacher"))
    var kind := str(parsed.get("kind", "learn")).capitalize()
    passage_label.text = ("%s · Measures %d–%d" % [
        kind, int(parsed.get("first_bar", 0)), int(parsed.get("last_bar", 0))])
    if bool(parsed.get("warmup", false)):
        var hand_step: int = (["left", "right", "both"].find(str(parsed.get("hand", "left"))) + 1)
        passage_label.text = "WARM-UP %d/3 · %s · Measures %d–%d" % [
            hand_step, str(parsed.get("hand", "left")).to_upper(),
            int(parsed.get("first_bar", 1)), int(parsed.get("last_bar", 8))]
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
    speed_label.text = "%d BPM · target %d" % [int(parsed.get("bpm", 0)),int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
    var recovery_notice: Variant = parsed.get("recovery_notice")
    practice_playback_banner.visible = recovery_notice is Dictionary and str(parsed.get("mode", "")) == "practice"
    if practice_playback_banner.visible:
        var notice: Dictionary = recovery_notice
        if str(notice.get("kind", "")) == "speedup":
            practice_playback_banner.text = (
                "Clean slower passage  ·  Tempo %d → %d BPM  ·  Keep practising"
                % [int(notice.get("from_bpm", 0)), int(notice.get("to_bpm", 0))])
            practice_playback_banner.add_theme_color_override("font_color", Color("#79DAAD"))
        else:
            practice_playback_banner.text = (
                "%d missing/wrong pitches  ·  Tempo %d → %d BPM  ·  Retry measures %d–%d"
                % [int(notice.get("errors", 0)), int(notice.get("from_bpm", 0)),
                   int(notice.get("to_bpm", 0)), int(notice.get("first_bar", 1)),
                   int(notice.get("last_bar", 1))])
            practice_playback_banner.add_theme_color_override("font_color", Color("#F6BC70"))
    speed_label.add_theme_font_size_override("font_size", _ui_font(16 if size.x < 900 else 18))
    speed_label.tooltip_text = "Current practice tempo and your selected target"
    hand_label.text = "Both hands" if str(parsed.get("hand", "right")) == "both" else str(parsed.get("hand", "right")).capitalize() + " hand"
    hand_label.text += " · " + ("Piano connected" if not str(parsed.get("device", "")).is_empty() else "No piano")
    hand_label.tooltip_text = str(parsed.get("device", "Connect your USB MIDI piano in Settings"))
    if current_screen != "settings":
        tempo_setting.set_value_no_signal(float(parsed.get("target_bpm", parsed.get("bpm", 40))))
    var stage: String = str(parsed.get("lesson_level", "original"))
    var explanations := {"skeleton": "Find the main notes first.",
        "outline": "Add the chord notes while keeping the pulse.",
        "original": "Bring every note together."}
    lesson_info_label.text = str(explanations.get(stage, ""))
    var learning: bool = str(parsed.get("mode", "practice")) == "learn"
    var teaching: Dictionary = parsed.get("teaching", {}) if parsed.get("teaching") is Dictionary else {}
    var learner: Dictionary = parsed.get("learner", {}) if parsed.get("learner") is Dictionary else {}
    placement_button.visible = bool(parsed.get("placement_available", false))
    skip_stage_button.disabled = not bool(parsed.get("skip_available", false))
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
            var context: String = "Idea %d of %d" % [unit_number,int(learner.get("total_units", 1))] if unit_number > 0 else "Selected bars %d–%d" % [int(parsed.get("first_bar", 1)),int(parsed.get("last_bar", 1))]
            progress_label.text = "%s · Notes found %d of %d" % [context,int(teaching.get("target_index", 0)),targets]
    for hand in hand_buttons:
        var button: Button = hand_buttons[hand]
        button.disabled = not parsed.get("hands", []).has(hand) or str(parsed.get("hand", "")) == hand
    practice_progress.value = float(parsed.get("progress", 0.0))
    stop_button.disabled = not bool(parsed.get("running", false))
    var phase: String = str(parsed.get("phase", "ready"))
    pause_sheet.present(parsed if current_screen == "practice" else {})
    start_button.visible = phase != "paused"
    if demo_player != null:
        demo_player.synchronize(parsed)
    listen_button.disabled = not bool(parsed.get("loaded", false))
    var summary: Dictionary = parsed.get("performance_summary", {}) if parsed.get("performance_summary") is Dictionary else {}
    performance_review.visible = not summary.is_empty()
    if not summary.is_empty():
        var weakest: Array = summary.get("weakest_bars", [])
        var bars: String = "%d–%d" % [int(weakest[0].get("first_bar", 1)),int(weakest[0].get("last_bar", 1))] if not weakest.is_empty() else "—"
        performance_text.text = "%.0f%% correct · %d early · %d late · %d missed pitches · %d extra\nWeakest measures %s · Review only; Practice earns clean runs." % [float(summary.get("accuracy_percent", 0)),int(summary.get("early", 0)),int(summary.get("late", 0)),summary.get("missed_pitches", []).size(),int(summary.get("extra_notes", 0)),bars]
        weak_button.disabled = weakest.is_empty()
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
        feedback_label.text = "Paused · Space to resume · R to restart"
    elif phase == "loading":
        feedback_label.text = "Preparing next passage · count-in waits for score"
    elif phase == "recovering":
        feedback_label.text = str(parsed.get("feedback", "Short break before retry"))
    elif phase == "count_in":
        feedback_label.text = "Follow the moving staff · play at the teal line"
    elif phase == "playing":
        var midi_count: int = int(parsed.get("midi_notes", 0))
        if bool(parsed.get("preview_only", false)):
            feedback_label.text = "Timing preview · connect your piano to enable scoring"
        else:
            feedback_label.text = "Playing · %d MIDI notes received" % midi_count if midi_count > 0 else "Playing · listening for your piano"
    else:
        feedback_label.text = str(parsed.get("feedback", ""))
    if str(parsed.get("mode", "")) == "listen":
        feedback_label.text = "Listening · follow the score" if bool(parsed.get("running", false)) else str(parsed.get("feedback", "Preparing Listen audio"))
        if bool(parsed.get("paused", false)):
            feedback_label.text = "Listen paused · Space to resume"
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
        lesson_info_label.text = "Idea complete. Play a new piano key to continue, or press Space."
    if not learning:
        progress_label.text = "Clean runs %d of 3 at %d BPM" % [int(parsed.get("streak", 0)), int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
        if bool(parsed.get("warmup", false)):
            var name: String = "Both hands" if str(parsed.get("hand", "")) == "both" else str(parsed.get("hand", "")).capitalize() + " hand"
            progress_label.text = "%s · %d of 3 clean runs · Next hand unlocks when mastered" % [
                name, int(parsed.get("streak", 0))]
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
    start_button.text = "Resume  ·  Space" if bool(parsed.get("paused", false)) else "Pause  ·  Space" if active_transport else "Start  ·  Space"
    if learning:
        start_button.text = "Resume  ·  Space" if phase == "paused" else "Try rhythm · Space" if phase in ["guided_complete", "disconnected"] else "Pause  ·  Space" if phase in ["guided_wait", "loading"] else "Learn · Space"
        if phase == "guided_complete" and bool(parsed.get("guided_recovery", false)):
            start_button.text = "Retry rhythm"
        elif phase == "guided_complete" and bool(teaching.get("has_more_units", false)):
            start_button.text = "Next idea · Space"
    elif str(parsed.get("mode", "")) == "listen" and not active_transport:
        start_button.text = "Back to warm-up" if bool(parsed.get("warmup", false)) else "Listen again"
    start_button.tooltip_text = "Space: start, pause or resume · R: restart · S: stop"
    start_button.disabled = not active_transport and (score_view.texture == null or layout_revision != revision)
    score_overlay.marks = []
    for marker in parsed.get("feedback_marks", []):
        score_overlay.marks.append(ScoreStrip.map_point(marker, score_layout) if score_layout.has("strip_size") else marker)
    score_overlay.queue_redraw()
    _consume_live_piano_hits(parsed)
    var new_revision := int(parsed.get("revision", 0))
    if new_revision != revision:
        revision = new_revision
        layout_revision = -1
        score_layout = {}
        source_layout = {}
        page_images.clear()
        current_page = -1
        score_view.texture = null
        score_error = ""
        _refresh_score_status()
        score_overlay.showing = false
        score_overlay.marks = []
        score_overlay.hit_pulses.clear()
        score_overlay.wrong_ghosts.clear()
        _request_layout()
    if str(parsed.get("phase", "")) == "loading" and layout_revision == revision and rendered_revision == revision and score_view.texture != null:
        _send_action({"action": "score_ready", "revision": revision})
    if str(parsed.get("phase", "")) == "feedback" and not score_overlay.marks.is_empty():
        var target_page: int = int(score_overlay.marks[0].get("page", 0))
        if current_page != target_page and layout_revision == revision:
            _request_score(target_page)
    # A physical note-on is the hands-free equivalent of Start on this
    # screen only. Poll-based arming keeps device checks in Settings inert.
    # A completion note in Learn must NOT instantly skip the completed idea;
    # require a new note-on after the finished state was already displayed.
    var current_phase: String = str(parsed.get("phase", ""))
    if (fresh_piano_key and sample_started_ms < 0 and current_screen == "practice"
            and not action_pending and old_revision == int(parsed.get("revision", -1))
            and old_phase == current_phase and not str(parsed.get("device", "")).is_empty()
            and score_view.texture != null and layout_revision == revision
            and current_phase in ["ready", "performance_complete", "guided_complete"]):
        if str(parsed.get("mode", "")) == "learn":
            _toggle_playing()
        elif str(parsed.get("mode", "")) in ["practice", "perform"]:
            _send_action({"action": "start"})
    _refresh_score_status()

func _staff_diatonic_index(pitch: int) -> int:
    # Equal chromatic pitches share a stave step (e.g. C and C#).
    var letter_steps := [0, 0, 1, 1, 2, 3, 3, 4, 4, 5, 5, 6]
    return int(pitch / 12) * 7 + letter_steps[posmod(pitch, 12)]


func _wrong_note_ghost(pitch: int, note: Dictionary) -> Dictionary:
    # Position the wrong physical pitch using the real engraved note's
    # pitch, hand, and local five-line staff. The source note's Verovio
    # coordinate is authoritative; only pitch displacement is calculated.
    var source_y: float = float(note.get("y", 0.0))
    var source_x: float = float(note.get("x", 0.0))
    var staff: Dictionary = {}
    for candidate in score_layout.get("systems", []):
        if int(candidate.get("page", -1)) != int(note.get("page", -2)):
            continue
        if (source_x >= float(candidate.get("left", -1.0)) - 0.001
                and source_x <= float(candidate.get("right", 2.0)) + 0.001
                and candidate.get("staff_lines", []).size() >= 10):
            staff = candidate
            break
    if staff.is_empty():
        return {}
    var lines: Array = staff.get("staff_lines", [])
    var hand: String = str(note.get("hand", "right"))
    var index: int = 5 if hand == "left" else 0
    var gap: float = absf(float(lines[index+1]) - float(lines[index]))
    if gap <= 0.0:
        return {}
    var steps: int = _staff_diatonic_index(pitch) - _staff_diatonic_index(int(note.get("pitch", pitch)))
    var target_y: float = source_y - float(steps) * gap * 0.5
    var ledgers: Array = []
    var top: float = float(lines[index])
    var bottom: float = float(lines[index+4])
    for n in range(1, 7):
        if target_y <= top - float(n) * gap + gap * 0.25:
            ledgers.append(top - float(n) * gap)
        if target_y >= bottom + float(n) * gap - gap * 0.25:
            ledgers.append(bottom + float(n) * gap)
    var names := ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return {
        "page": int(note.get("page", -1)),
        "x": source_x, "y": target_y,
        "label": names[posmod(pitch, 12)] + str(int(pitch / 12) - 1),
        "ledger_lines": ledgers,
    }


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
                var ghost: Dictionary = _wrong_note_ghost(int(event.get("pitch", -1)), note)
                if not ghost.is_empty():
                    ghost["until_ms"] = Time.get_ticks_msec() + maxi(1, 1050 - int(age * 1000.0))
                    score_overlay.wrong_ghosts.append(ghost)
                break
            continue
        if status not in ["on_time", "early", "late"] or age > .75:
            continue
        var note_id: String = str(mapping.get(source, ""))
        if note_id.is_empty():
            continue
        for note in notes:
            if str(note.get("id", "")) == note_id:
                score_overlay.hit_pulses.append({
                    "page": int(note.get("page", 0)),
                    "x": float(note.get("x", 0.0)),
                    "y": float(note.get("y", 0.0)),
                    "status": status,
                    "until_ms": Time.get_ticks_msec() + maxi(1, 700 - int(age * 1000.0))
                })
                break


func _request_layout() -> void:
    if layout_pending:
        return
    layout_pending = true
    requested_layout_revision = revision
    if layout_request.request(URL + "/score/layout") != OK:
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
    score_layout = parsed
    source_layout = parsed
    page_images.clear()
    page_images.resize(int(parsed.get("pages", 0)))
    layout_revision = revision
    _request_score(0)

func _request_score(page: int) -> void:
    if score_pending or layout_revision != revision:
        return
    # The whole virtual strip is ready; original source pages must never be
    # fetched in response to an old feedback marker during playback.
    if rendered_revision == revision and score_layout.has("strip_size"):
        return
    if page == current_page and rendered_revision == revision:
        return
    if page < 0 or page >= int(source_layout.get("pages", score_layout.get("pages", 0))):
        return
    score_pending = true
    requested_page = page
    requested_revision = revision
    if score_request.request(URL + "/score.png?page=%d" % page) != OK:
        score_pending = false
        _score_failed("Cannot request score page from the practice engine")

func _visible_engraving_bounds(picture: Image) -> Rect2i:
    # Verovio PNGs have transparent black margins; some imports are opaque
    # white. Only visible dark pixels are engraving ink in either format.
    picture.convert(Image.FORMAT_RGBA8)
    var rgba: PackedByteArray = picture.get_data()
    var width: int = picture.get_width()
    var height: int = picture.get_height()
    var left: int = width
    var top: int = height
    var right: int = -1
    var bottom: int = -1
    # Coarse sampling is sufficient for a bounding box and avoids a slow
    # pixel-by-pixel GDScript pass over a large raster.
    for y in range(0, height, 2):
        for x in range(0, width, 2):
            var offset: int = (y * width + x) * 4
            if rgba[offset + 3] < 8:
                continue
            if rgba[offset] >= 240 and rgba[offset + 1] >= 240 and rgba[offset + 2] >= 240:
                continue
            left = mini(left, x)
            right = maxi(right, x)
            top = mini(top, y)
            bottom = maxi(bottom, y)
    if right < left or bottom < top:
        return Rect2i(0, 0, 0, 0)
    return Rect2i(left, top, mini(width - left, right - left + 2),
                  mini(height - top, bottom - top + 2))


func _on_score(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    score_pending = false
    if requested_revision != revision:
        if layout_revision == revision:
            _request_score(0)
        return
    if code != 200:
        _score_failed(_http_failure(code, body))
        return
    var picture := Image.new()
    if picture.load_png_from_buffer(body) != OK:
        _score_failed("The practice engine sent an invalid score image (PNG)")
        return
    if picture.get_width() < 32 or picture.get_height() < 32:
        _score_failed("The engraved score image is unexpectedly small")
        return
    if page_images.is_empty():
        if source_layout.is_empty():
            source_layout = score_layout
        page_images.resize(int(source_layout.get("pages", 1)))
    page_images[requested_page] = picture
    for page in range(page_images.size()):
        if page_images[page] == null:
            _request_score(page)
            return
    # Remove empty page margins without breaking notehead annotations.
    var original_size := Vector2(picture.get_width(), picture.get_height())
    var opaque_bounds := _visible_engraving_bounds(picture)
    if opaque_bounds.size.x < 16 or opaque_bounds.size.y < 16:
        _score_failed("The engraving image contains no visible musical notation")
        return
    var pad := maxi(18, int(0.035 * float(opaque_bounds.size.y)))
    var crop_rect := Rect2i(
        Vector2i(maxi(0, opaque_bounds.position.x - pad), maxi(0, opaque_bounds.position.y - pad)),
        Vector2i(0, 0)
    )
    var right := mini(picture.get_width(), opaque_bounds.end.x + pad)
    var bottom := mini(picture.get_height(), opaque_bounds.end.y + pad)
    crop_rect.size = Vector2i(right, bottom) - crop_rect.position
    var cropped := picture.get_region(crop_rect)
    var strip: Dictionary = ScoreStrip.build(source_layout, page_images)
    if strip.has("error") or strip["tiles"].is_empty():
        _score_failed(str(strip.get("error", "No staff systems were found in the engraving")))
        return
    for tile in score_tiles:
        score_content.remove_child(tile)
        tile.queue_free()
    score_tiles.clear()
    strip_tiles = strip["tiles"]
    var notation_material := Design.notation_material()
    for item in strip_tiles:
        var tile := TextureRect.new()
        tile.texture = item["texture"]
        tile.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
        tile.stretch_mode = TextureRect.STRETCH_SCALE
        tile.mouse_filter = Control.MOUSE_FILTER_IGNORE
        tile.material = notation_material
        score_content.add_child(tile)
        score_content.move_child(tile, score_overlay.get_index())
        score_tiles.append(tile)
    score_layout = strip["layout"]
    score_crop_origin = Vector2.ZERO
    score_crop_size = Vector2.ONE
    score_view.texture = ImageTexture.create_from_image(cropped)
    score_view.visible = false
    score_overlay.image_size = strip["size"]
    score_overlay.load_symbols(source_layout.get("symbols", {}))
    # Cropped tile textures now own all visible imagery. Release full pages
    # rather than retaining a second whole-song raster in CPU memory.
    page_images.clear()
    score_overlay.crop_origin = score_crop_origin
    score_overlay.crop_size = score_crop_size
    current_page = 0
    score_overlay.active_page = current_page
    rendered_revision = revision
    score_error = ""
    if phase0_smoke_mode:
        print("PHASE0_SCORE_READY:", picture.get_width(), "x", picture.get_height())
        print("PHASE0_LESSON_READY: REVISION:", revision, " LEVEL:",
              str(last_state.get("lesson_level", "")), " REQUIRED:",
              int(last_state.get("required_notes", 0)))
    start_button.disabled = false
    score_overlay.queue_redraw()
    _layout_moving_score()
    _refresh_score_status()
    if str(last_state.get("phase", "")) == "loading" and int(last_state.get("awaiting_score_revision", -1)) == revision:
        _send_action({"action": "score_ready", "revision": revision})

func _send_action(command: Dictionary) -> void:
    if action_pending:
        # Navigation intent must survive an in-flight Start or Resume. Keep
        # just the latest pause/stop intent, rather than queuing stale clicks.
        if str(command.get("action", "")) in ["pause", "stop"]:
            pending_transport_action = str(command["action"])
        return
    last_control_action = str(command.get("action", ""))
    _send_post("/control", command)

func _flush_transport_action() -> void:
    if not pending_transport_action.is_empty():
        var action := pending_transport_action
        pending_transport_action = ""
        _send_action({"action": action})

func _send_post(path: String, payload: Dictionary) -> void:
    if action_pending:
        return
    action_pending = true
    last_post_path = path
    action_request_started_ms = Time.get_ticks_msec()
    var err := action_request.request(URL + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
    if err != OK:
        action_pending = false
        feedback_label.text = "Cannot reach practice engine"

func _on_action(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    action_pending = false
    var path := last_post_path
    var completed_action := last_control_action
    if code != 200:
        var message := _http_failure(code, body)
        if path == "/library/open":
            library_error = "Cannot open score: " + message
        feedback_label.text = message
        settings_message.text = message
        library_message.text = message
        home_recent_label.text = message
        _flush_transport_action()
        return
    if path == "/control":
        _on_state(_result, code, _headers, body, action_request_started_ms)
        if completed_action in ["skip_stage", "place_original", "revisit_trouble"]:
            _navigate("practice")
    elif path == "/library/open":
        library_error = ""
        score_error = ""
        var opened: Variant = _decode_json(body)
        _navigate("practice")
        _refresh_score_status()
        # Warm-ups arrive as repeatable Perform sessions. Do not silently
        # replace them with the normal imported-piece Learn curriculum.
        if not (opened is Dictionary and (bool(opened.get("warmup", false))
                or str(opened.get("mode", "")) == "perform")):
            _send_action({"action":"learn"})
    elif path == "/settings":
        settings_message.text = "Settings saved"
        _request_settings()
        _request_library()
    elif path == "/device":
        _request_settings()
    _flush_transport_action()
    _poll()

func _has_active_transport() -> bool:
    return bool(last_state.get("running", false)) or str(last_state.get("phase", "")) in ["count_in", "playing", "paused", "feedback", "recovering", "loading"]

func _toggle_playing() -> void:
    if str(last_state.get("mode", "")) == "listen" and not _has_active_transport():
        _send_action({"action": "practice" if bool(last_state.get("warmup", false)) else "listen"})
        return
    if str(last_state.get("mode", "practice")) == "learn":
        var phase: String = str(last_state.get("phase", "ready"))
        var teaching: Dictionary = last_state.get("teaching", {}) if last_state.get("teaching") is Dictionary else {}
        if phase == "guided_complete" and bool(teaching.get("has_more_units", false)) and not bool(last_state.get("guided_recovery", false)):
            _send_action({"action":"learn_next"})
            return
        _send_action({"action": "resume" if phase == "paused" else "practice" if phase in ["guided_complete", "disconnected"] else "pause" if phase in ["guided_wait", "loading"] else "learn_retry"})
        return
    if bool(last_state.get("paused", false)):
        _send_action({"action": "resume"})
        return
    if _has_active_transport():
        _send_action({"action": "pause"})
        return
    if not bool(last_state.get("running", false)) and (score_view.texture == null or layout_revision != revision):
        feedback_label.text = "Preparing sheet music - wait for the notes before starting"
        return
    _send_action({"action": "pause" if bool(last_state.get("running", false)) else "start"})

func _toggle_pause() -> void:
    if _has_active_transport() or (str(last_state.get("mode", "practice")) == "learn" and str(last_state.get("phase", "")) in ["guided_wait", "paused"]):
        _send_action({"action": "resume" if bool(last_state.get("paused", false)) else "pause"})

func _restart_practice() -> void:
    if score_view.texture != null and layout_revision == revision:
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
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
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

func _show_devices() -> void:
    _request_devices()
    device_menu.position = Vector2i(device_button.get_screen_position()) + Vector2i(0, int(device_button.size.y))
    device_menu.popup()

func _choose_device(id: int) -> void:
    if id == -2:
        _send_post("/device", {"name": ""})
        return
    if id < 0 or id >= device_names.size():
        return
    _send_post("/device", {"name":device_names[id]})
    device_button.text = str(device_names[id]) + "  ✓"

func _input(event: InputEvent) -> void:
    if not event is InputEventKey:
        return
    if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]:
        return
    if get_viewport().gui_get_focus_owner() is LineEdit and event.keycode not in [KEY_F11, KEY_ESCAPE]:
        return
    var practice_shortcut: bool = current_screen == "practice" and event.keycode in [
        KEY_ESCAPE, KEY_SPACE, KEY_P, KEY_R, KEY_S, KEY_LEFT, KEY_RIGHT]
    if event.keycode == KEY_F11 or practice_shortcut:
        # Consume press and release before focused buttons see ui_accept.
        # Handling only the press can also activate Next/Stop on release.
        _unhandled_key_input(event)
        get_viewport().set_input_as_handled()

func _unhandled_key_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
        if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]:
            return
        if get_viewport().gui_get_focus_owner() is LineEdit and event.keycode not in [KEY_F11, KEY_ESCAPE]:
            return
        if event.keycode == KEY_F11:
            _toggle_fullscreen()
            get_viewport().set_input_as_handled()
            return
        if event.keycode == KEY_ESCAPE and current_screen == "practice":
            _navigate("library")
            get_viewport().set_input_as_handled()
            return
        if current_screen != "practice":
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
            KEY_S:
                _send_action({"action":"stop"})
                get_viewport().set_input_as_handled()
            KEY_LEFT:
                _send_action({"action":"previous"})
                get_viewport().set_input_as_handled()
            KEY_RIGHT:
                _send_action({"action":"next"})
                get_viewport().set_input_as_handled()
