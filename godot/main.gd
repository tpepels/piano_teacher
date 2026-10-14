extends Control

# Lightweight Godot presentation. Python owns MIDI timestamps, tempo and grading.
const URL := "http://127.0.0.1:8765"
const INK := Color("#293B34")
const MUTED := Color("#7F8982")
const PAPER := Color("#F3F5EF")
const WHITE := Color("#FFFEFA")
const ACCENT := Color("#325A4C")

var current_screen := "home"
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
var current_page := -1
var requested_page := -1
var rendered_revision := -1
var action_pending := false
var last_state: Dictionary = {}
var last_state_tick := 0

class ScoreOverlay extends Control:
    var cursor: Dictionary = {}
    var showing := false
    var image_size := Vector2.ZERO
    var marks: Array = []
    var active_page := -1

    func _sheet_xy(x: float, y: float) -> Vector2:
        # Match TextureRect.STRETCH_KEEP_ASPECT_CENTERED including letterboxing.
        var factor: float = min(size.x / image_size.x, size.y / image_size.y)
        var painted: Vector2 = image_size * factor
        return (size - painted) * 0.5 + painted * Vector2(x, y)

    func _draw() -> void:
        if image_size.x <= 0.0 or image_size.y <= 0.0:
            return
        # A faint green ring confirms correct notes; stronger colour markers
        # distinguish mistakes without altering the underlying engraving.
        var palette := {
            "correct": Color("#4A987B"), "wrong": Color("#BB4A4A"),
            "missed": Color("#BB4A4A"), "extra": Color("#BB4A4A"),
            "early": Color("#BA852B"), "late": Color("#BA852B"),
            "short": Color("#8660AF"), "long": Color("#8660AF")
        }
        var labels := {"wrong":"×", "missed":"!", "extra":"+",
                       "early":"←", "late":"→", "short":"−", "long":"+"}
        for marker in marks:
            if int(marker.get("page", -1)) != active_page:
                continue
            var status: String = str(marker.get("status", ""))
            var color: Color = palette.get(status, Color("#BB4A4A"))
            var center: Vector2 = _sheet_xy(float(marker.get("x", 0.0)), float(marker.get("y", 0.0)))
            if status == "correct":
                draw_arc(center, 9.0, 0.0, TAU, 20, Color(color, 0.37), 1.5, true)
            else:
                var radius := 12.0 if status == "missed" else 10.0
                draw_circle(center, radius, Color(1, 1, 1, 0.60))
                draw_arc(center, radius, 0.0, TAU, 24, color, 2.5, true)
                var symbol: String = str(labels.get(status, "!"))
                var font: Font = ThemeDB.fallback_font
                draw_string(font, center + Vector2(12, -9), symbol, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, color)
                if status == "extra":
                    draw_string(font, center + Vector2(12, 5), str(marker.get("label", "")), HORIZONTAL_ALIGNMENT_LEFT, -1, 11, color)
        if showing and not cursor.is_empty() and int(cursor.get("page", -1)) == active_page:
            var x: float = float(cursor.get("x", 0.0))
            var top: float = float(cursor.get("top", 0.0))
            var bottom: float = float(cursor.get("bottom", 1.0))
            var start: Vector2 = _sheet_xy(x, top)
            var end: Vector2 = _sheet_xy(x, bottom)
            draw_line(start, end, Color("#C39351"), 2.5, true)
            draw_circle(start, 4.0, Color("#C39351"))

func _ready() -> void:
    _build_interface()
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
    var poll := Timer.new()
    poll.wait_time = 0.15
    poll.autostart = true
    poll.timeout.connect(_poll)
    add_child(poll)
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
    )
    add_child(scan_timer)
    set_process(true)

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

func _label(text: String, size: int, color: Color, bold := false) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_color_override("font_color", color)
    label.add_theme_font_size_override("font_size", size)
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
    button.custom_minimum_size = Vector2(88, 45)
    var style := StyleBoxFlat.new()
    style.bg_color = ACCENT if primary else Color("#ECEFEA")
    style.set_corner_radius_all(11)
    style.content_margin_left = 18
    style.content_margin_right = 18
    button.add_theme_stylebox_override("normal", style)
    var hover := style.duplicate() as StyleBoxFlat
    hover.bg_color = Color("#426A5B") if primary else Color("#DDE8DD")
    button.add_theme_stylebox_override("hover", hover)
    button.add_theme_stylebox_override("pressed", hover)
    var disabled_style := style.duplicate() as StyleBoxFlat
    disabled_style.bg_color = Color("#E9EBE6")
    button.add_theme_stylebox_override("disabled", disabled_style)
    button.add_theme_color_override("font_color", WHITE if primary else INK)
    button.add_theme_color_override("font_hover_color", WHITE if primary else INK)
    button.add_theme_color_override("font_disabled_color", MUTED)
    button.add_theme_font_size_override("font_size", 15)
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
    style.set_corner_radius_all(17)
    style.set_border_width_all(1)
    style.border_color = Color("#DFE4DC")
    style.shadow_color = Color(0.14, 0.2, 0.15, 0.05)
    style.shadow_size = 6
    panel.add_theme_stylebox_override("panel", style)
    return panel

func _card_body(panel: PanelContainer, margin: int = 28) -> MarginContainer:
    var body := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        body.add_theme_constant_override("margin_" + side, margin)
    panel.add_child(body)
    return body

func _navigate(screen: String) -> void:
    if screen != "practice" and current_screen == "practice" and bool(last_state.get("running", false)):
        _send_action({"action": "stop"})
    current_screen = screen
    for key in screens:
        (screens[key] as Control).visible = str(key) == screen
    if screen == "library":
        _request_library()
    elif screen == "settings":
        _request_settings()
        _request_devices()

func _build_interface() -> void:
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
    home_nav.add_child(_label("PIANO  /  TEACHER", 15, ACCENT, true))
    home_nav.add_child(_space())
    home_nav.add_child(_button("Settings", func(): _navigate("settings")))
    home_nav.add_child(_button("Quit", func(): get_tree().quit()))
    var header := _stack(12)
    home_layout.add_child(header)
    header.add_child(_label("Practice the music you love.", 44, INK, true))
    header.add_child(_label("Short passages. Both hands. Steady progress.", 20, MUTED))
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
    library_head.add_child(_button("Music folder", func(): _navigate("settings")))
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
    settings_head.add_child(_button("← Back", func(): _navigate("home")))
    settings_head.add_child(_space())
    settings_layout.add_child(_label("Settings", 39, INK, true))
    settings_layout.add_child(_label("Only the options you need to practice.", 16, MUTED))
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
    settings_content.add_child(_label("DISPLAY", 13, ACCENT, true))
    fullscreen_toggle = CheckButton.new()
    fullscreen_toggle.text = "Fullscreen application  (F11 to toggle)"
    fullscreen_toggle.button_pressed = true
    fullscreen_toggle.toggled.connect(_on_fullscreen_toggle)
    settings_content.add_child(fullscreen_toggle)
    settings_message = _label("", 14, MUTED)
    settings_layout.add_child(settings_message)

    # Practice: standard engraving remains the central and dominant element.
    var practice_page := _screen("Practice")
    screens["practice"] = practice_page
    var practice_layout := _stack(19)
    practice_page.add_child(practice_layout)
    var top := HBoxContainer.new()
    top.add_theme_constant_override("separation", 18)
    practice_layout.add_child(top)
    top.add_child(_button("← Library", func(): _navigate("library")))
    var heading := _stack(2)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    top.add_child(heading)
    title_label = _label("Piano Teacher", 27, INK, true)
    title_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    title_label.clip_text = true
    title_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    heading.add_child(title_label)
    passage_label = _label("", 14, MUTED)
    heading.add_child(passage_label)
    var tempo := _stack(2)
    top.add_child(tempo)
    speed_label = _label("-- BPM", 20, INK)
    speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(speed_label)
    hand_label = _label("", 13, MUTED)
    hand_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(hand_label)
    practice_settings_button = _button("Settings", func(): _navigate("settings"))
    top.add_child(practice_settings_button)
    var score_panel := _card()
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(score_panel)
    var score_margin := _card_body(score_panel, 26)
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
    score_area.custom_minimum_size = Vector2(0, 170)
    score_margin.add_child(score_area)
    score_view = TextureRect.new()
    score_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_view.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
    score_view.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
    score_area.add_child(score_view)
    score_overlay = ScoreOverlay.new()
    score_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
    score_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_area.add_child(score_overlay)
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
    var information := HBoxContainer.new()
    practice_layout.add_child(information)
    progress_label = _label("", 14, MUTED)
    information.add_child(progress_label)
    information.add_child(_space())
    feedback_label = _label("Ready", 14, MUTED)
    feedback_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    information.add_child(feedback_label)
    var controls := HBoxContainer.new()
    controls.alignment = BoxContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("separation", 15)
    practice_layout.add_child(controls)
    controls.add_child(_button("← Previous", func(): _send_action({"action": "previous"})))
    start_button = _button("Start  ·  Space", _toggle_playing, true)
    start_button.custom_minimum_size = Vector2(148, 53)
    controls.add_child(start_button)
    controls.add_child(_button("Next →", func(): _send_action({"action": "next"})))
    var listen := _button("Listen", _listen)
    listen.disabled = true
    listen.tooltip_text = "On-demand audio demonstration is not implemented yet"
    controls.add_child(listen)

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
    _navigate("home")
    _refresh_score_status()

func _update_responsive_layout() -> void:
    # Fit smaller laptops and high-DPI/scaled fullscreen windows. Fixed-size
    # cards and long labels previously forced the right edge off-screen.
    var width: float = size.x
    var margin: int = 56 if width >= 1550 else 32 if width >= 1100 else 16
    for panel in page_margins:
        panel.add_theme_constant_override("margin_left", margin)
        panel.add_theme_constant_override("margin_right", margin)
        panel.add_theme_constant_override("margin_top", 28 if width >= 900 else 14)
        panel.add_theme_constant_override("margin_bottom", 28 if width >= 900 else 14)
    if home_cards != null:
        home_cards.vertical = width < 1380
    if folder_controls != null:
        folder_controls.vertical = width < 1000
    if practice_settings_button != null:
        practice_settings_button.visible = width >= 1050

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
    home_count_label.text = "%d scores available" % int(parsed.get("count", 0))
    library_path_label.text = str(parsed.get("folder", ""))
    _populate_library()
    var recent: String = str(parsed.get("last_piece", ""))
    home_resume_button.disabled = recent.is_empty()
    var exists_in_library := false
    for entry in parsed.get("pieces", []):
        if str(entry.get("id", "")) == recent:
            exists_in_library = true
            break
    home_resume_button.disabled = not exists_in_library
    home_recent_label.text = recent.get_file().get_basename().replace("_", " ") if not recent.is_empty() else "No recent piece"

func _populate_library() -> void:
    if library_rows == null:
        return
    for child in library_rows.get_children():
        library_rows.remove_child(child)
        child.queue_free()
    var pieces: Array = library_info.get("pieces", [])
    var query := library_search.text.strip_edges().to_lower()
    var visible := 0
    for entry in pieces:
        var title: String = str(entry.get("title", "Untitled"))
        var location: String = str(entry.get("folder", ""))
        if not query.is_empty() and not (title + " " + location).to_lower().contains(query):
            continue
        var identifier: String = str(entry.get("id", ""))
        var format_name: String = str(entry.get("format", ""))
        var hint: String = location if not location.is_empty() else "Music folder"
        var button := _button("%s     ·     %s     ·     %s" % [title, format_name, hint], func(): _open_library_piece(identifier))
        button.alignment = HORIZONTAL_ALIGNMENT_LEFT
        button.custom_minimum_size = Vector2(0, 58)
        button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        library_rows.add_child(button)
        visible += 1
    var issue: String = str(library_info.get("error", ""))
    if not library_error.is_empty():
        library_message.text = library_error
    elif not issue.is_empty():
        library_message.text = issue
    elif pieces.is_empty():
        library_message.text = "No scores yet. Add .mid, .midi or MusicXML files to this folder."
    elif visible == 0:
        library_message.text = "No matching scores."
    else:
        library_message.text = "%d files  ·  %d shown  ·  Automatically refreshed" % [pieces.size(), visible]

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
    _apply_window_mode(bool(preferences.get("fullscreen", true)))
    var saved_device := str(preferences.get("midi_device", ""))
    if not saved_device.is_empty() and str(last_state.get("device", "")) == "" and not device_names.is_empty():
        if device_names.has(saved_device):
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
    if not state_pending:
        state_pending = true
        if state_request.request(URL + "/state") != OK:
            state_pending = false

func _process(_delta: float) -> void:
    if last_state.is_empty() or not bool(last_state.get("running", false)):
        score_overlay.showing = false
        score_overlay.queue_redraw()
        return
    if str(last_state.get("phase", "")) != "playing" or layout_revision != revision:
        score_overlay.showing = false
        score_overlay.queue_redraw()
        return
    var elapsed: float = float(Time.get_ticks_msec() - last_state_tick) / 1000.0
    var beat: float = float(last_state.get("beat", 0.0)) + elapsed * float(last_state.get("bpm", 60.0)) / 60.0
    beat = clampf(beat, 0.0, float(last_state.get("duration_beats", 1.0)))
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
    score_overlay.cursor = cursor
    score_overlay.showing = true
    score_overlay.queue_redraw()

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

func _on_state(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    state_pending = false
    if code != 200:
        feedback_label.text = _http_failure(code, body)
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    last_state = parsed
    last_state_tick = Time.get_ticks_msec()
    if not bool(parsed.get("loaded", false)):
        feedback_label.text = str(parsed.get("feedback", "Open a score"))
        _refresh_score_status()
        return
    title_label.text = str(parsed.get("title", "Piano Teacher"))
    var kind := str(parsed.get("kind", "learn")).capitalize()
    passage_label.text = "%s · Measures %d–%d" % [kind, int(parsed.get("first_bar", 0)), int(parsed.get("last_bar", 0))]
    speed_label.text = "%d BPM" % int(parsed.get("bpm", 0))
    hand_label.text = "%s hand · %d%% speed" % [str(parsed.get("hand", "right")).capitalize(), int(round(float(parsed.get("bpm", 0)) / max(1.0, float(parsed.get("original_bpm", 1))) * 100.0))]
    feedback_label.text = str(parsed.get("feedback", ""))
    var unpositioned: int = int(parsed.get("feedback_unmapped", 0))
    if unpositioned > 0:
        feedback_label.text += " · %d unpositioned note(s)" % unpositioned
    progress_label.text = "Exercise %d/%d  ·  %d mastered" % [int(parsed.get("exercise", 1)),int(parsed.get("exercise_count", 1)),int(parsed.get("mastered", 0))]
    start_button.text = "Stop  ·  Space" if bool(parsed.get("running", false)) else "Start  ·  Space"
    score_overlay.marks = parsed.get("feedback_marks", [])
    score_overlay.queue_redraw()
    var new_revision := int(parsed.get("revision", 0))
    if new_revision != revision:
        revision = new_revision
        layout_revision = -1
        score_layout = {}
        current_page = -1
        score_view.texture = null
        score_error = ""
        _refresh_score_status()
        score_overlay.showing = false
        score_overlay.marks = []
        _request_layout()
    if str(parsed.get("phase", "")) == "feedback" and not score_overlay.marks.is_empty():
        var target_page: int = int(score_overlay.marks[0].get("page", 0))
        if current_page != target_page and layout_revision == revision:
            _request_score(target_page)
    _refresh_score_status()

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
    layout_revision = revision
    _request_score(0)

func _request_score(page: int) -> void:
    if score_pending or layout_revision != revision:
        return
    if page == current_page and rendered_revision == revision:
        return
    if page < 0 or page >= int(score_layout.get("pages", 0)):
        return
    score_pending = true
    requested_page = page
    requested_revision = revision
    if score_request.request(URL + "/score.svg?page=%d" % page) != OK:
        score_pending = false
        _score_failed("Cannot request score page from the practice engine")

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
    if picture.load_svg_from_buffer(body, 1.5) != OK:
        _score_failed("Godot could not render the SVG score generated by Verovio")
        return
    score_view.texture = ImageTexture.create_from_image(picture)
    score_overlay.image_size = Vector2(picture.get_width(), picture.get_height())
    current_page = requested_page
    score_overlay.active_page = current_page
    rendered_revision = revision
    score_error = ""
    score_overlay.queue_redraw()
    _refresh_score_status()

func _send_action(command: Dictionary) -> void:
    _send_post("/control", command)

func _send_post(path: String, payload: Dictionary) -> void:
    if action_pending:
        return
    action_pending = true
    last_post_path = path
    var err := action_request.request(URL + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
    if err != OK:
        action_pending = false
        feedback_label.text = "Cannot reach practice engine"

func _on_action(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    action_pending = false
    var path := last_post_path
    if code != 200:
        var message := _http_failure(code, body)
        if path == "/library/open":
            library_error = "Cannot open score: " + message
        feedback_label.text = message
        settings_message.text = message
        library_message.text = message
        home_recent_label.text = message
        return
    if path == "/library/open":
        library_error = ""
        score_error = ""
        _navigate("practice")
        _refresh_score_status()
    elif path == "/settings":
        settings_message.text = "Settings saved"
        _request_settings()
        _request_library()
    elif path == "/device":
        _request_settings()
    _poll()

func _toggle_playing() -> void:
    _send_action({"action": "stop" if bool(last_state.get("running", false)) else "start"})

func _listen() -> void:
    pass

func _request_devices() -> void:
    device_request.request(URL + "/devices")

func _on_devices(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if code != 200:
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    device_names = parsed.get("devices", [])
    device_menu.clear()
    for i in range(device_names.size()):
        device_menu.add_item(str(device_names[i]), i)
    device_button.text = str(last_state.get("device", "Choose USB MIDI piano")) if not str(last_state.get("device", "")).is_empty() else "Choose USB MIDI piano"
    if str(last_state.get("device", "")) == "":
        var saved: String = str(preferences.get("midi_device", ""))
        if device_names.has(saved) and not saved.is_empty():
            _choose_device(device_names.find(saved))
        elif device_names.size() == 1:
            _choose_device(0)

func _show_devices() -> void:
    _request_devices()
    device_menu.position = Vector2i(device_button.get_screen_position()) + Vector2i(0, int(device_button.size.y))
    device_menu.popup()

func _choose_device(id: int) -> void:
    if id < 0 or id >= device_names.size():
        return
    _send_post("/device", {"name":device_names[id]})
    device_button.text = str(device_names[id]) + "  ✓"

func _unhandled_key_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
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
            KEY_LEFT:
                _send_action({"action":"previous"})
                get_viewport().set_input_as_handled()
            KEY_RIGHT:
                _send_action({"action":"next"})
                get_viewport().set_input_as_handled()
