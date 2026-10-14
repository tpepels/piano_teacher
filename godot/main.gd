extends Control

# Lightweight Godot presentation. Python owns MIDI timestamps, tempo and grading.
const URL := "http://127.0.0.1:8765"
const INK := Color("#293B34")
const MUTED := Color("#7F8982")
const PAPER := Color("#F6F5F0")
const WHITE := Color("#FFFEFA")
const ACCENT := Color("#3B574C")

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
var file_dialog: FileDialog
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
    state_request = _new_request(_on_state)
    score_request = _new_request(_on_score)
    layout_request = _new_request(_on_layout)
    action_request = _new_request(_on_action)
    device_request = _new_request(_on_devices)
    var poll := Timer.new()
    poll.wait_time = 0.15
    poll.autostart = true
    poll.timeout.connect(_poll)
    add_child(poll)
    _poll()
    _request_devices()
    set_process(true)

func _new_request(callback: Callable) -> HTTPRequest:
    var req := HTTPRequest.new()
    req.timeout = 5.0
    add_child(req)
    req.request_completed.connect(callback)
    return req

func _label(text: String, size: int, color: Color, bold := false) -> Label:
    var label := Label.new()
    label.text = text
    label.add_theme_color_override("font_color", color)
    label.add_theme_font_size_override("font_size", size)
    if bold:
        label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0))
    return label

func _button(label: String, callback: Callable, primary := false) -> Button:
    var button := Button.new()
    button.text = label
    button.custom_minimum_size = Vector2(88, 45)
    var style := StyleBoxFlat.new()
    style.bg_color = ACCENT if primary else Color("#ECEFEA")
    style.set_corner_radius_all(11)
    style.content_margin_left = 18
    style.content_margin_right = 18
    button.add_theme_stylebox_override("normal", style)
    button.add_theme_stylebox_override("hover", style)
    button.add_theme_color_override("font_color", WHITE if primary else INK)
    button.add_theme_color_override("font_hover_color", WHITE if primary else INK)
    button.pressed.connect(callback)
    return button

func _build_interface() -> void:
    var background := ColorRect.new()
    background.color = PAPER
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(background)
    var margins := MarginContainer.new()
    margins.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    for side in ["left", "right", "top", "bottom"]:
        margins.add_theme_constant_override("margin_" + side, 30)
    add_child(margins)
    var layout := VBoxContainer.new()
    layout.add_theme_constant_override("separation", 17)
    margins.add_child(layout)

    var top := HBoxContainer.new()
    layout.add_child(top)
    var heading := VBoxContainer.new()
    heading.add_theme_constant_override("separation", 4)
    top.add_child(heading)
    title_label = _label("Piano Teacher", 27, INK, true)
    heading.add_child(title_label)
    passage_label = _label("Open a score to begin", 14, MUTED)
    heading.add_child(passage_label)
    var stretch := Control.new()
    stretch.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    top.add_child(stretch)
    var tempo := VBoxContainer.new()
    tempo.add_theme_constant_override("separation", 3)
    top.add_child(tempo)
    speed_label = _label("-- BPM", 19, INK)
    speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(speed_label)
    hand_label = _label("USB MIDI piano", 13, MUTED)
    hand_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(hand_label)
    top.add_child(_button("Open file", _open_file))
    device_button = _button("Piano", _show_devices)
    top.add_child(device_button)

    var score_panel := PanelContainer.new()
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    var panel_style := StyleBoxFlat.new()
    panel_style.bg_color = WHITE
    panel_style.set_corner_radius_all(14)
    panel_style.set_border_width_all(1)
    panel_style.border_color = Color("#E6E7E0")
    score_panel.add_theme_stylebox_override("panel", panel_style)
    layout.add_child(score_panel)
    var score_margin := MarginContainer.new()
    for side in ["left", "right", "top", "bottom"]:
        score_margin.add_theme_constant_override("margin_" + side, 22)
    score_panel.add_child(score_margin)
    var score_area := Control.new()
    score_area.size_flags_vertical = Control.SIZE_EXPAND_FILL
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
    var placeholder := _label("Choose a MIDI or MusicXML file to start practicing", 18, MUTED)
    placeholder.name = "Placeholder"
    placeholder.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    placeholder.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
    placeholder.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    score_area.add_child(placeholder)

    var information := HBoxContainer.new()
    layout.add_child(information)
    progress_label = _label("", 13, MUTED)
    information.add_child(progress_label)
    var filler := Control.new()
    filler.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    information.add_child(filler)
    feedback_label = _label("Connect a piano, then play", 13, MUTED)
    feedback_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    information.add_child(feedback_label)

    var controls := HBoxContainer.new()
    controls.alignment = BoxContainer.ALIGNMENT_CENTER
    controls.add_theme_constant_override("separation", 14)
    layout.add_child(controls)
    controls.add_child(_button("← Previous", func(): _send_action({"action":"previous"})))
    start_button = _button("Start", _toggle_playing, true)
    controls.add_child(start_button)
    controls.add_child(_button("Next →", func(): _send_action({"action":"next"})))
    var listen := _button("Listen", _listen)
    listen.disabled = true
    listen.tooltip_text = "Demonstration playback is planned for a subsequent milestone"
    controls.add_child(listen)

    file_dialog = FileDialog.new()
    file_dialog.access = FileDialog.ACCESS_FILESYSTEM
    file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
    file_dialog.filters = PackedStringArray(["*.mid, *.midi ; MIDI", "*.musicxml, *.xml, *.mxl ; MusicXML"])
    file_dialog.file_selected.connect(func(path: String): _send_post("/load", {"path":path}))
    add_child(file_dialog)
    device_menu = PopupMenu.new()
    device_menu.id_pressed.connect(_choose_device)
    add_child(device_menu)

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
        feedback_label.text = "Backend unavailable - run ./run.sh"
        return
    var parsed = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    last_state = parsed
    last_state_tick = Time.get_ticks_msec()
    if not bool(parsed.get("loaded", false)):
        feedback_label.text = str(parsed.get("feedback", "Open a score"))
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
    start_button.text = "Stop" if bool(parsed.get("running", false)) else "Start"
    score_overlay.marks = parsed.get("feedback_marks", [])
    score_overlay.queue_redraw()
    var new_revision := int(parsed.get("revision", 0))
    if new_revision != revision:
        revision = new_revision
        layout_revision = -1
        score_layout = {}
        current_page = -1
        score_view.texture = null
        score_overlay.showing = false
        score_overlay.marks = []
        _request_layout()
    if str(parsed.get("phase", "")) == "feedback" and not score_overlay.marks.is_empty():
        var target_page: int = int(score_overlay.marks[0].get("page", 0))
        if current_page != target_page and layout_revision == revision:
            _request_score(target_page)
    var placeholder: Control = score_view.get_parent().get_node("Placeholder") as Control
    placeholder.visible = score_view.texture == null

func _request_layout() -> void:
    if layout_pending:
        return
    layout_pending = true
    requested_layout_revision = revision
    if layout_request.request(URL + "/score/layout") != OK:
        layout_pending = false
        feedback_label.text = "Cannot request score geometry"

func _on_layout(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    layout_pending = false
    if requested_layout_revision != revision:
        _request_layout()
        return
    if code != 200:
        feedback_label.text = "Engraving layout failed: " + body.get_string_from_utf8().substr(0, 140)
        return
    var parsed = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY or not parsed.has("anchors"):
        feedback_label.text = "Invalid engraving geometry"
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
        feedback_label.text = "Cannot request score page"

func _on_score(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    score_pending = false
    if requested_revision != revision:
        if layout_revision == revision:
            _request_score(0)
        return
    if code != 200:
        feedback_label.text = "Engraving failed: " + body.get_string_from_utf8().substr(0, 150)
        return
    var picture := Image.new()
    if picture.load_svg_from_buffer(body, 1.5) != OK:
        feedback_label.text = "Unable to display the engraved score"
        return
    score_view.texture = ImageTexture.create_from_image(picture)
    score_overlay.image_size = Vector2(picture.get_width(), picture.get_height())
    current_page = requested_page
    score_overlay.active_page = current_page
    rendered_revision = revision
    score_overlay.queue_redraw()
    (score_view.get_parent().get_node("Placeholder") as Control).hide()

func _send_action(command: Dictionary) -> void:
    _send_post("/control", command)

func _send_post(path: String, payload: Dictionary) -> void:
    if action_pending:
        return
    action_pending = true
    var err := action_request.request(URL + path, ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
    if err != OK:
        action_pending = false
        feedback_label.text = "Cannot reach practice engine"

func _on_action(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    action_pending = false
    if code != 200:
        var response = JSON.parse_string(body.get_string_from_utf8())
        feedback_label.text = str(response.get("error", "Request failed")) if typeof(response) == TYPE_DICTIONARY else "Request failed"
    _poll()

func _toggle_playing() -> void:
    _send_action({"action": "stop" if bool(last_state.get("running", false)) else "start"})

func _open_file() -> void:
    file_dialog.popup_centered_ratio(0.78)

func _listen() -> void:
    pass

func _request_devices() -> void:
    device_request.request(URL + "/devices")

func _on_devices(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    if code != 200:
        return
    var parsed = JSON.parse_string(body.get_string_from_utf8())
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    device_names = parsed.get("devices", [])
    device_menu.clear()
    for i in range(device_names.size()):
        device_menu.add_item(str(device_names[i]), i)
    if device_names.size() == 1 and str(last_state.get("device", "")) == "":
        _choose_device(0)

func _show_devices() -> void:
    _request_devices()
    device_menu.position = Vector2i(device_button.get_screen_position()) + Vector2i(0, device_button.size.y)
    device_menu.popup()

func _choose_device(id: int) -> void:
    if id < 0 or id >= device_names.size():
        return
    _send_post("/device", {"name":device_names[id]})
    device_button.text = "Piano ✓"

func _unhandled_key_input(event: InputEvent) -> void:
    if event is InputEventKey and event.pressed and not event.echo:
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
