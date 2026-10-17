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
const ScoreQuality := preload("res://score_quality.gd")
const StaffContinuity := preload("res://staff_continuity.gd")
const ScoreOverlay := preload("res://score_overlay.gd")
const NoteReactions := preload("res://note_reactions.gd")
const ChallengeFlow := preload("res://challenge_flow.gd")
const LivingScore := preload("res://living_score.gd")
const HintKeyboard := preload("res://hint_keyboard.gd")
const GameBackdrop := preload("res://game_backdrop.gd")
const GameStage := preload("res://game_stage.gd")
const GameStreak := preload("res://game_streak.gd")
const GameCountIn := preload("res://game_countin.gd")
const GamePhaseCue := preload("res://game_phase_cue.gd")
const GameTransportButton := preload("res://game_transport_button.gd")
const ActionButton := preload("res://action_button.gd")
const LibraryRow := preload("res://library_row.gd")
const GameInputIndicator := preload("res://game_input_indicator.gd")
const VisualTransportClock := preload("res://visual_transport_clock.gd")
const FrameMeter := preload("res://frame_meter.gd")

var current_screen := "practice"
var settings_return_screen := "practice"
var overlay_root: Control
var overlay_drawer: PanelContainer
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
var game_streak: Control
var game_input_indicator: Control
var game_count_in: Control
var score_status_panel: CenterContainer
var score_status_label: Label
var score_retry_button: Button
var score_error := ""
var library_error := ""
var pending_library_piece := ""
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
var note_reactions: Control
var score_frame: Control
var score_content: Control
var staff_continuity: Control
var score_crop_origin := Vector2.ZERO
var score_crop_size := Vector2.ONE
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
var score_pending := false
var requested_revision := -1
var layout_revision := -1
var requested_layout_revision := -1
var layout_pending := false
var score_layout: Dictionary = {}
var living_chords: Array = []
var source_layout: Dictionary = {}
var page_images: Array[Image] = []
var score_tiles: Array[TextureRect] = []
var strip_tiles: Array = []
# Phase 8G: static raster geometry is independent of the moving camera.
var score_tile_scale := -1.0
var cached_bounds: Dictionary = {}
var cached_bounds_revision := -1
# Only animated overlays use a 30 FPS redraw cadence. The engraving camera
# stays at 60 FPS and musical timing remains owned by the Python engine.
var last_overlay_animation_ms := -1000
var camera_last_scale := -1.0
var score_raster_width := 2000
var visible_tile_begin := 0
var visible_tile_end := 0
var tile_window_initialized := false
var tile_geometry_rebuilds := 0
var tile_window_changes := 0
var score_tile_upload_bytes := 0
var score_tile_packed_bytes := 0
# Phase 8I: long scores retain compressed CPU ink instead of offscreen
# Texture2Ds. Two neighbouring systems on each side are prefetched.
var deferred_tile_mode := false
var resident_tile_begin := 0
var resident_tile_end := 0
var resident_tile_bytes := 0
var restored_tile_count := 0
var current_page := -1
var requested_page := -1
var rendered_revision := -1
var action_pending := false
var last_state: Dictionary = {}
var hand_unlock_message := ""
var hand_unlock_until_ms := 0
var last_state_tick := 0
var last_playhead_strike_beat := -INF
var last_playhead_strike_transport := -1
var visual_transport_clock = VisualTransportClock.new()
var state_request_started_ms := 0
var last_audio_transport_id := -1
var follow_system_key := ""
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
    phase0_smoke_mode = OS.get_cmdline_user_args().has("--phase0-smoke")
    listen_sync_diagnostics = OS.get_cmdline_user_args().has("--listen-sync-diagnostics")
    frame_diagnostics = OS.get_cmdline_user_args().has("--frame-diagnostics")
    ui_scale = _readable_ui_scale()
    _build_interface()
    demo_player = preload("res://demo_player.gd").new()
    add_child(demo_player)
    listen_volume_slider.set_value_no_signal(float(demo_player.get("listen_volume_db")))
    _show_listen_volume(float(demo_player.get("listen_volume_db")))
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
        if current_screen == "practice" or current_screen == "settings":
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

func _score_note_bounds(page: int) -> Dictionary:
    if cached_bounds_revision == revision and cached_bounds.has(page):
        return cached_bounds[page]
    if cached_bounds_revision != revision:
        cached_bounds_revision = revision
        cached_bounds.clear()
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
    var bounds: Dictionary
    if not is_finite(left) or not is_finite(right):
        bounds = {"left": 0.0, "right": 1.0}
    else:
        bounds = {"left": clampf(left - 0.04, 0.0, 1.0),
            "right": clampf(right + 0.04, 0.0, 1.0)}
    cached_bounds[page] = bounds
    return bounds


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
    var systems: Array = score_layout.get("systems", [])
    var rail_center := .5
    if not systems.is_empty():
        var rails: Array = systems[0].get("staff_lines", [])
        if rails.size() >= 2:
            var native_gap: float = absf(float(rails[1]) - float(rails[0])) * image.y
            var rail_extent: float = absf(float(rails[-1]) - float(rails[0])) * image.y
            rail_center = (float(rails[0]) + float(rails[-1])) * .5
            if native_gap > .001 and rail_extent > .001:
                # The raster tile height includes large blank SVG margins.
                # Scale from the actual grand staff, not those margins.
                # Leave 35% of the stage for ledger lines and phrasing.
                # Score is the focal element; on a larger display the
                # *actual* noteheads/staves must grow with the stage.
                # The grand-staff bound protects both hands and ledger lines.
                var desired_gap: float = ScoreQuality.staff_gap(viewport.y, rails)
                scale = minf(width_scale, desired_gap / native_gap)
    var displayed_width: float = image.x * scale
    var displayed_height: float = image.y * scale
    if score_content.size.distance_to(Vector2(displayed_width, displayed_height)) > .1:
        score_content.size = Vector2(displayed_width, displayed_height)
    staff_continuity.position = Vector2.ZERO
    # Rebuilding a very long rail canvas every 60-Hz camera tick wastes
    # work; the rules are static until the score is resized or replaced.
    if staff_continuity.size.distance_to(score_content.size) > .1:
        staff_continuity.size = score_content.size
        staff_continuity.queue_redraw()
    # Keep all source tile geometry in local canvas coordinates. Only a
    # change in zoom requires touching every node; ordinary camera movement
    # changes score_content.position alone.
    if absf(scale - score_tile_scale) > .000001:
        for i in range(score_tiles.size()):
            var rect: Rect2 = strip_tiles[i]["rect"]
            score_tiles[i].position = rect.position * scale
            score_tiles[i].size = rect.size * scale
        score_tile_scale = scale
        tile_geometry_rebuilds += 1
    var midpoint_x: float = (focus_left + focus_right) * 0.5
    var target_x: float = viewport.x * 0.5 - midpoint_x * displayed_width
    if score_layout.has("strip_size") and not score_layout.get("notes", []).is_empty():
        target_x = viewport.x * 0.04
    if score_overlay.showing and not score_overlay.cursor.is_empty():
        var note_x: float = (float(score_overlay.cursor.get("x", 0.0))
            - score_crop_origin.x) / maxf(score_crop_size.x, 0.00001)
        target_x = viewport.x * 0.42 - note_x * displayed_width
    # Centre the *real staff*, not the large blank area in the SVG raster.
    var target_y: float = viewport.y * .5 - rail_center * displayed_height
    var target := Vector2(target_x, target_y)
    var key: String = "%d/%d/%d" % [revision, current_page, int(last_state.get("transport_id", 0))]
    # This is a musical projection, not a camera chasing a moving object.
    # Smoothing introduces tempo-dependent lag; clamps let the rule wander.
    score_content.position = target
    # Two binary searches locate the visible half-open tile interval.
    # Update only entering/leaving tiles, rather than all systems at 60 Hz.
    var tile_overscan: float = maxf(120.0, viewport.x * .18)
    var window: Vector2i = ScoreStrip.visible_tile_range(
        strip_tiles, target_x, scale, viewport.x, tile_overscan)
    # Stage new textures before releasing old ones, so rapid seeks have
    # no frame with a missing notehead or accidental.
    if not _set_tile_residency(window):
        _score_failed("An engraved score tile could not be decoded")
        return
    if not tile_window_initialized or visible_tile_begin != window.x \
            or visible_tile_end != window.y:
        tile_window_changes += 1
    if not tile_window_initialized:
        # Fresh TextureRect nodes default to visible; initialize them once.
        for tile in score_tiles:
            tile.visible = false
        tile_window_initialized = true
    else:
        for i in range(visible_tile_begin, visible_tile_end):
            if i < window.x or i >= window.y:
                score_tiles[i].visible = false
    for i in range(window.x, window.y):
        if i < visible_tile_begin or i >= visible_tile_end:
            score_tiles[i].visible = true
    visible_tile_begin = window.x
    visible_tile_end = window.y
    follow_system_key = key

func _set_tile_residency(visible_range: Vector2i) -> bool:
    if not deferred_tile_mode:
        return true
    var next_begin: int = maxi(0, visible_range.x - 2)
    var next_end: int = mini(score_tiles.size(), visible_range.y + 2)
    if resident_tile_begin == next_begin and resident_tile_end == next_end:
        return true
    # Decode incoming ink before evicting outgoing textures. The preload
    # margin is wider than one system so normal playback almost always
    # reveals a tile that has already been uploaded.
    var incoming: Dictionary = {}
    for i in range(next_begin, next_end):
        if i >= resident_tile_begin and i < resident_tile_end:
            continue
        var texture: Texture2D = ScoreStrip.tile_texture(strip_tiles[i])
        if texture == null:
            return false
        incoming[i] = texture
    for i in range(resident_tile_begin, resident_tile_end):
        if i < next_begin or i >= next_end:
            score_tiles[i].texture = null
            resident_tile_bytes -= int(strip_tiles[i].get("upload_bytes", 0))
    for i in incoming:
        score_tiles[i].texture = incoming[i]
        resident_tile_bytes += int(strip_tiles[i].get("upload_bytes", 0))
        restored_tile_count += 1
    resident_tile_begin = next_begin
    resident_tile_end = next_end
    return true


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
        maxf(118.0, text_width + (80.0 if button.action_role != "secondary"
            else 58.0) * ui_scale), 50.0 * ui_scale)
    button.pressed.connect(callback)
    return button


func _game_button(button: Button, central := false) -> void:
    # Buttons on the piano stage are instrument controls rather than
    # generic form submissions. Keep a fixed tactile vocabulary.
    button.add_theme_font_size_override("font_size", _ui_font(17 if central else 15))
    var normal := StyleBoxFlat.new()
    var kind: String = str(button.get("action_kind"))
    var accent := Color("#A1FCD5") if central else (
        Color("#F3CE93") if kind == "retry" else
        Color("#9ECFFF") if kind == "listen" else Color("#A1FCD5"))
    normal.bg_color = Color("#286E60") if central else (
        Color("#3A3029") if kind == "retry" else
        Color("#253C4C") if kind == "listen" else Color("#234438"))
    button.set_meta("ui_button_role",
        "transport_primary" if central else "transport_retry" if kind == "retry" else "transport_listen")
    normal.set_corner_radius_all(15 if central else 12)
    normal.set_content_margin_all(12)
    normal.set_border_width_all(2 if central else 1)
    normal.border_color = Color(accent, .94 if central else .65)
    normal.shadow_color = Color(accent, .25 if central else .12)
    normal.shadow_size = 7 if central else 2
    normal.shadow_offset = Vector2(0, 3)
    button.add_theme_stylebox_override("normal", normal)
    var hover := normal.duplicate() as StyleBoxFlat
    hover.bg_color = normal.bg_color.lightened(.16)
    hover.border_color = accent.lightened(.14)
    hover.shadow_size = 12 if central else 4
    button.add_theme_stylebox_override("hover", hover)
    var pressed := normal.duplicate() as StyleBoxFlat
    pressed.bg_color = normal.bg_color.darkened(.18)
    pressed.shadow_size = 0
    pressed.shadow_offset = Vector2.ZERO
    button.add_theme_stylebox_override("pressed", pressed)
    var disabled := normal.duplicate() as StyleBoxFlat
    disabled.bg_color = Color("#172324")
    disabled.border_color = Color("#456059", .3)
    disabled.shadow_size = 0
    button.add_theme_stylebox_override("disabled", disabled)
    var focus := normal.duplicate() as StyleBoxFlat
    focus.bg_color = Color.TRANSPARENT
    focus.border_color = Color("#F5FFF7")
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

# Music selection, lesson path and settings are drawers over the
# persistent practice stage. Opening a drawer pauses an ongoing attempt
# without discarding the player's place or MIDI assessment.
func _update_visual_frame_rate(state: Dictionary) -> void:
    # An idle screen or paused lesson does not need the same redraw budget
    # as a scrolling score. This never changes Python-owned audio, tempo
    # or MIDI grading, only how often the Godot display is presented.
    var active: bool = bool(state.get("running", false)) \
        and not bool(state.get("paused", false)) \
        and current_screen == "practice"
    var target_fps: int = 60 if active else 30
    if Engine.max_fps != target_fps:
        Engine.max_fps = target_fps


func _navigate(screen: String) -> void:
    if screen == "home":
        screen = "practice"  # Old Home is no longer part of normal navigation.
    if screen == "settings" and current_screen != "settings":
        settings_return_screen = current_screen
    if screen != "practice" and current_screen == "practice":
        var phase: String = str(last_state.get("phase", ""))
        var starting: bool = (action_pending and last_post_path == "/control"
            and last_control_action in ["start", "restart", "resume", "score_ready",
            "learn", "learn_retry", "practice", "listen", "perform"])
        if (phase in ["count_in", "playing", "guided_wait", "feedback",
                      "recovering", "loading"] or starting):
            _send_action({"action": "pause"})
    current_screen = screen
    _update_visual_frame_rate(last_state)
    if overlay_root != null:
        overlay_root.visible = screen != "practice"
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
    # Reuse the existing complete library/settings/course controls, but mount
    # them as a right-side in-context sheet instead of routing to another page.
    overlay_root = Control.new()
    overlay_root.name = "MusicAndSettingsDrawer"
    overlay_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(overlay_root)
    overlay_backdrop = ColorRect.new()
    overlay_backdrop.color = Color(0.012, 0.035, 0.028, 0.68)
    overlay_backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
    overlay_backdrop.gui_input.connect(func(event: InputEvent):
        if event is InputEventMouseButton and event.pressed:
            _navigate("practice"))
    overlay_root.add_child(overlay_backdrop)
    overlay_drawer = PanelContainer.new()
    overlay_drawer.name = "ContextDrawer"
    overlay_drawer.clip_contents = true
    overlay_drawer.mouse_filter = Control.MOUSE_FILTER_STOP
    var style := Design.surface(Design.PANEL, 12)
    style.set_border_width_all(2)
    style.border_color = Color(Design.TEAL, 0.5)
    style.set_content_margin_all(3)
    overlay_drawer.add_theme_stylebox_override("panel", style)
    overlay_root.add_child(overlay_drawer)
    for page in ["library", "settings", "lesson"]:
        var content: Control = screens[page]
        content.reparent(overlay_drawer, false)
        content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    overlay_root.visible = false
    _resize_overlay_drawer()


func _resize_overlay_drawer() -> void:
    if overlay_drawer == null:
        return
    var viewport: Vector2 = size
    var drawer_width: float = viewport.x if viewport.x <= 700 else minf(
        1000.0, maxf(500.0, viewport.x * 0.72))
    # Right-anchored offsets must be relative to the RIGHT edge. Setting
    # both global position and size after PRESET_TOP_RIGHT can shrink the
    # panel to its minimum width on resize (real 1536×960 screenshot).
    overlay_drawer.anchor_left = 1.0
    overlay_drawer.anchor_right = 1.0
    overlay_drawer.anchor_top = 0.0
    overlay_drawer.anchor_bottom = 1.0
    overlay_drawer.offset_left = -drawer_width
    overlay_drawer.offset_right = 0.0
    overlay_drawer.offset_top = 0.0
    overlay_drawer.offset_bottom = 0.0


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
    var library_layout := _stack(22)
    library_page.add_child(library_layout)
    var library_head := HBoxContainer.new()
    library_layout.add_child(library_head)
    library_head.add_child(_button("Close", func(): _navigate("practice"), false, "navigation"))
    library_head.add_child(_space())
    library_head.add_child(_button("Settings", func(): _navigate("settings"), false, "settings"))
    library_layout.add_child(_label("Your music", 39, INK, true))
    library_path_label = _label("Looking for scores…", 15, MUTED)
    library_path_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    library_path_label.clip_text = true
    library_path_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    library_layout.add_child(library_path_label)
    # Keep search full-width in the narrow Music drawer.
    var library_controls := VBoxContainer.new()
    library_controls.add_theme_constant_override("separation", 9)
    library_layout.add_child(library_controls)
    library_search = LineEdit.new()
    library_search.placeholder_text = "Search title, composer or folder"
    library_search.clear_button_enabled = true
    library_search.tooltip_text = "Ctrl+F or / to focus search · Esc closes the library"
    library_search.custom_minimum_size = Vector2(0, 48)
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
    library_controls.add_child(library_search)
    library_controls.add_child(_label(
        "Ctrl+F or / to search  ·  Enter opens music  ·  Esc closes", 12, MUTED))
    var library_utilities := HBoxContainer.new()
    library_utilities.add_theme_constant_override("separation", 10)
    library_controls.add_child(library_utilities)
    library_utilities.add_child(_button("Refresh", _request_library, false, "utility"))
    library_health_button = _button("Check files", func(): _start_library_health(), false, "settings")
    # Dynamic text also says "Checking…" or "Recheck files". Reserve room
    # from the start so the button does not visibly resize or clip.
    library_health_button.custom_minimum_size.x = maxf(
        library_health_button.custom_minimum_size.x,
        _ui_font(15) * 8.3 + 80.0 * ui_scale)
    library_utilities.add_child(library_health_button)
    # Import problems must appear next to the action, not at the very
    # bottom of a full-screen library where they are easy to miss.
    library_message = _label("", 18, MUTED, true)
    library_message.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_layout.add_child(library_message)
    library_health_label = _label("", 16, MUTED)
    library_health_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    library_health_label.visible = false
    library_layout.add_child(library_health_label)
    var library_panel := _card()
    library_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    library_layout.add_child(library_panel)
    var scroll := ScrollContainer.new()
    library_scroll = scroll
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    _card_body(library_panel, 22).add_child(scroll)
    library_rows = _stack(6)
    library_rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    scroll.add_child(library_rows)
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
    settings_head.add_child(_button("← Back", _go_back, false, "navigation"))
    settings_head.add_child(_space())
    settings_layout.add_child(_label("Settings", 39, INK, true))
    settings_layout.add_child(_label("Your piano, music folder and practice preferences.", 16, MUTED))
    var settings_card := _card()
    settings_layout.add_child(settings_card)
    var settings_content := _stack(24)
    _card_body(settings_card, 32).add_child(settings_content)
    settings_content.add_child(_label("MUSIC LIBRARY", 13, ACCENT, true))
    settings_content.add_child(_label("Piano Teacher scans this folder and its subfolders automatically.", 15, MUTED))
    var folder_row := VBoxContainer.new()
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
    var folder_actions := HFlowContainer.new()
    folder_actions.add_theme_constant_override("h_separation", 12)
    folder_actions.add_theme_constant_override("v_separation", 8)
    folder_row.add_child(folder_actions)
    folder_actions.add_child(_button("Browse…", _browse_folder, false, "navigation"))
    folder_actions.add_child(_button("Save folder", _save_folder, true))
    settings_content.add_child(_label("PIANO INPUT", 13, ACCENT, true))
    var device_row := HFlowContainer.new()
    device_row.add_theme_constant_override("separation", 12)
    settings_content.add_child(device_row)
    device_button = _button("Choose USB MIDI piano", _show_devices, false, "settings")
    device_row.add_child(device_button)
    device_row.add_child(_button("Refresh devices", _request_devices, false, "utility"))
    input_activity_label = _label("Connect your MIDI piano, then play a note to check input.", 15, MUTED)
    settings_content.add_child(input_activity_label)
    settings_content.add_child(_label("PRACTICE", 13, ACCENT, true))
    var tempo_row := HFlowContainer.new()
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
    apply_tempo_button = _button("Apply tempo", func(): _send_action({"action": "tempo", "bpm": int(tempo_setting.value)}), false, "settings")
    tempo_row.add_child(apply_tempo_button)
    metronome_toggle = CheckButton.new()
    metronome_toggle.text = "Metronome during practice"
    metronome_toggle.tooltip_text = "Count-in is always audible, even when metronome is off"
    metronome_toggle.toggled.connect(func(enabled: bool): _send_post("/settings", {"metronome": enabled}))
    settings_content.add_child(metronome_toggle)
    settings_content.add_child(_label("LISTEN AUDIO", 13, ACCENT, true))
    var audio_row := HFlowContainer.new()
    audio_row.add_theme_constant_override("h_separation", 16)
    audio_row.add_theme_constant_override("v_separation", 8)
    settings_content.add_child(audio_row)
    audio_row.add_child(_label("Piano volume", 16, INK))
    listen_volume_slider = HSlider.new()
    listen_volume_slider.min_value = -12.0
    listen_volume_slider.max_value = 12.0
    listen_volume_slider.step = 1.0
    listen_volume_slider.value = 6.0
    listen_volume_slider.custom_minimum_size = Vector2(200, 40)
    listen_volume_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    listen_volume_slider.tooltip_text = "Listen only. Saved locally; does not change MIDI or metronome."
    audio_row.add_child(listen_volume_slider)
    listen_volume_label = _label("+6 dB", 16, INK, true)
    listen_volume_label.custom_minimum_size.x = 70
    audio_row.add_child(listen_volume_label)
    listen_volume_slider.value_changed.connect(_on_listen_volume_changed)
    settings_content.add_child(_label("Increase if Listen is quiet; lower if loud chords distort.", 14, MUTED))
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
    var practice_layout := _stack(12)
    practice_layout_box = practice_layout
    practice_page.add_child(practice_layout)
    # Navigation and lesson metadata are separate rows. A long title or
    # small viewport must never squeeze BPM into a one-letter column.
    practice_navigation = HFlowContainer.new()
    practice_navigation.add_theme_constant_override("h_separation", 10)
    practice_navigation.add_theme_constant_override("v_separation", 8)
    practice_navigation.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(practice_navigation)
    game_brand = _label("PIANO TEACHER", 13, Color("#75CEAF"), true)
    game_brand.custom_minimum_size = Vector2(168, 32)
    game_brand.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    game_brand.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
    practice_navigation.add_child(game_brand)
    practice_music_button = _button("Music", func(): _navigate("library"))
    practice_music_button.tooltip_text = "Choose a piece · Escape"
    practice_navigation.add_child(practice_music_button)
    _utility_button(practice_music_button)
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
    # Advanced mode and hint choices live in Lesson Path, not the stage.
    # Listen is a main transport choice, not a navigation option.
    hints_toggle = CheckButton.new()
    hints_toggle.text = "Hints"
    hints_toggle.add_theme_font_size_override("font_size", _ui_font(15))
    hints_toggle.tooltip_text = "Keep key hints visible while learning notes"
    hints_toggle.toggled.connect(func(enabled: bool): _send_action({"action":"hints", "enabled":enabled}))
    # Teaching hints are controlled in Lesson Path.
    var path_button := _button("Path", func(): _navigate("lesson"))
    path_button.tooltip_text = "Learning stages and advanced practice"
    practice_navigation.add_child(path_button)
    _utility_button(path_button)
    practice_settings_button = _button("Settings", func(): _navigate("settings"))
    practice_navigation.add_child(practice_settings_button)
    _utility_button(practice_settings_button)
    var exit_button := _button("Exit", _exit_app)
    exit_button.tooltip_text = "Close Piano Teacher · Ctrl+Q"
    practice_navigation.add_child(exit_button)
    _utility_button(exit_button, true)

    practice_header = HBoxContainer.new()
    practice_header.add_theme_constant_override("separation", 20)
    practice_layout.add_child(practice_header)
    var heading := _stack(2)
    heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    practice_header.add_child(heading)
    title_label = _label("Piano Teacher", 27, Color("#F3F7EF"), true)
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
    speed_label = _label("-- BPM", 20, Color("#90E9C6"), true)
    speed_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    speed_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(speed_label)
    hand_label = _label("", 13, MUTED)
    hand_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    hand_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
    tempo.add_child(hand_label)
    game_input_indicator = GameInputIndicator.new()
    tempo.add_child(game_input_indicator)
    lesson_info_label = _label("", 16, Color("#A9C2B7"))
    lesson_info_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_stage_bar = HFlowContainer.new()
    practice_stage_bar.add_theme_constant_override("h_separation", 10)
    practice_stage_bar.add_theme_constant_override("v_separation", 6)
    practice_stage_bar.visible = false
    practice_layout.add_child(practice_stage_bar)
    for hand in ["left", "right", "both"]:
        var stage_label := _label("", 15, MUTED, true)
        stage_label.custom_minimum_size = Vector2(168, 38)
        stage_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
        var stage_style := Design.surface(Design.PANEL, 6)
        stage_style.set_content_margin_all(8)
        stage_label.add_theme_stylebox_override("normal", stage_style)
        practice_stage_bar.add_child(stage_label)
        practice_stage_labels[hand] = stage_label
    practice_playback_banner = _label("", 18, Color("#F6BC70"), true)
    practice_playback_banner.visible = false
    practice_playback_banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    practice_playback_banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
    var score_panel := _card()
    # One continuous performance stage, not another grey website card.
    var stage_shell := StyleBoxFlat.new()
    stage_shell.bg_color = Color("#101B1C")
    stage_shell.set_corner_radius_all(12)
    stage_shell.set_border_width_all(1)
    stage_shell.border_color = Color("#527B70", .27)
    stage_shell.shadow_color = Color.BLACK
    stage_shell.shadow_size = 0
    score_panel.add_theme_stylebox_override("panel", stage_shell)
    practice_score_panel = score_panel
    score_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
    practice_layout.add_child(score_panel)
    var score_margin := _card_body(score_panel, 10)
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
    game_stage = GameStage.new()
    game_stage.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_frame.add_child(game_stage)
    score_content = Control.new()
    score_content.mouse_filter = Control.MOUSE_FILTER_IGNORE
    score_frame.add_child(score_content)
    staff_continuity = StaffContinuity.new()
    staff_continuity.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_content.add_child(staff_continuity)
    # The positive MIDI feedback halo is behind the actual engraved ink.
    note_reactions = NoteReactions.new()
    note_reactions.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    score_content.add_child(note_reactions)
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
    note_reactions.hit_pulses = score_overlay.hit_pulses
    note_reactions.preview_pulses = score_overlay.preview_pulses
    note_reactions.wrong_ghosts = score_overlay.wrong_ghosts
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
    game_phase_cue.offset_right = -12.0
    game_phase_cue.offset_top = 9.0
    game_phase_cue.offset_bottom = 46.0
    score_frame.add_child(game_phase_cue)
    game_count_in = GameCountIn.new()
    game_count_in.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
    game_count_in.position = Vector2(22, 12)
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
    progress_label = _label("", 17, Color("#CDECDD"), true)
    progress_label.autowrap_mode = TextServer.AUTOWRAP_OFF
    progress_label.clip_text = true
    progress_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    challenge_bar.add_child(progress_label)
    game_streak = GameStreak.new()
    challenge_bar.add_child(game_streak)
    feedback_label = _label("Ready", 16, Color("#A1BAAF"))
    feedback_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    feedback_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    information.add_child(feedback_label)
    information.add_child(lesson_info_label)
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
    controls.add_theme_constant_override("h_separation", 16)
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
    var start_style := Design.surface(Color("#1C3130"), 18)
    start_style.set_content_margin_all(5)
    start_style.set_border_width_all(2)
    start_style.border_color = Color("#85D9BD", .63)
    start_style.shadow_color = Color.BLACK
    start_style.shadow_size = 16
    start_style.shadow_offset = Vector2(0, 8)
    open_panel.add_theme_stylebox_override("panel", start_style)
    open_picker.add_child(open_panel)
    var start_scroll := ScrollContainer.new()
    start_scroll.name = "StartContentScroll"
    start_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    start_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
    _card_body(open_panel, 18).add_child(start_scroll)
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
    start_actions.add_theme_constant_override("separation", 12)
    start_content.add_child(start_actions)
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
    add_child(pause_sheet)
    pause_sheet.chosen.connect(func(command: Dictionary):
        if command.get("action") == "exit":
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
    _resize_overlay_drawer()
    _resize_open_picker()
    if practice_header == null:
        return
    practice_header.add_theme_constant_override("separation", 16)
    game_brand.visible = width >= 1280.0
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
            button.custom_minimum_size = Vector2(maxf(90.0, measured + 60.0),
                34.0 if compact else 36.0)
            button.clip_text = false
    if practice_controls != null:
        practice_layout_box.add_theme_constant_override("separation", 6 if compact else 9)
        # Give the score roughly half the window height instead of
        # allowing transport, menus and hint keyboard to dwarf it.
        score_frame.custom_minimum_size.y = 195.0 if compact else clampf(
            size.y * .48, 320.0, 760.0)
        for side in ["left", "right", "top", "bottom"]:
            score_margin_box.add_theme_constant_override("margin_" + side, 5 if compact else 10)
        for child in practice_controls.get_children():
            if child is Button:
                var button := child as Button
                var central: bool = button == start_button
                var font_size := _ui_font(20 if central else 18)
                button.add_theme_font_size_override("font_size", font_size)
                var measured: float = button.get_theme_font("font").get_string_size(
                    button.text, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x
                var available: float = maxf(0.0, width - float(margin * 2) - 56.0)
                var ideal: float = maxf(246.0 if central else 198.0, measured + 108.0)
                # At 800px all three keys must fit on one row, without
                # shrinking their active hit areas to website-sized chips.
                var per_button: float = maxf(155.0, (available - 48.0) / 3.0)
                button.custom_minimum_size = Vector2(
                    minf(ideal * (1.13 if width >= 1600.0 else 1.0), per_button * (1.18 if central else .91)),
                    58.0 if compact else 80.0 if central else 73.0)
                button.clip_text = false
        title_label.add_theme_font_size_override("font_size", _ui_font(25))
        passage_label.add_theme_font_size_override("font_size", _ui_font(15))
        speed_label.add_theme_font_size_override("font_size", _ui_font(19))
        hand_label.add_theme_font_size_override("font_size", _ui_font(15))
        progress_label.add_theme_font_size_override("font_size", _ui_font(15))
        game_streak.custom_minimum_size = Vector2(130 if width < 950 else 155, 30)
        game_input_indicator.custom_minimum_size = Vector2(145, 25)
        feedback_label.add_theme_font_size_override("font_size", _ui_font(17))
        lesson_info_label.add_theme_font_size_override("font_size", _ui_font(16))
        practice_playback_banner.add_theme_font_size_override("font_size", _ui_font(17))
        practice_note_feedback_label.add_theme_font_size_override("font_size", _ui_font(18))
        practice_note_feedback_panel.offset_left = -minf(330.0, maxf(180.0, score_frame.size.x - 24.0))

func _build_lesson_screen() -> void:
    var page := _screen("Lesson")
    screens["lesson"] = page
    var content := _stack(20)
    page.add_child(content)
    var navigation := HBoxContainer.new()
    content.add_child(navigation)
    navigation.add_child(_button("← Practice", _go_back, false, "navigation"))
    navigation.add_child(_space())
    navigation.add_child(_label("Piano Teacher", 18, INK, true))
    content.add_child(_label("Your lesson path", 34, INK, true))
    lesson_summary = _label("Open a piece to see its lessons.", 18, INK)
    content.add_child(lesson_summary)
    lesson_description = _label("", 16, MUTED)
    content.add_child(lesson_description)
    var activity := HFlowContainer.new()
    activity.add_theme_constant_override("h_separation", 12)
    activity.add_theme_constant_override("v_separation", 8)
    content.add_child(activity)
    activity.add_child(_label("Activity", 17, MUTED))
    activity.add_child(mode_choice)
    activity.add_child(hints_toggle)
    var passage_nav := HFlowContainer.new()
    passage_nav.add_theme_constant_override("h_separation", 10)
    content.add_child(passage_nav)
    passage_nav.add_child(_button("Previous passage", func():
        _send_action({"action":"previous"})
        _navigate("practice"), false, "navigation"))
    passage_nav.add_child(_button("Next passage", func():
        _send_action({"action":"next"})
        _navigate("practice"), false, "navigation"))
    passage_nav.add_child(stop_button)
    var hand_row := HBoxContainer.new()
    hand_row.add_theme_constant_override("separation", 12)
    content.add_child(hand_row)
    for hand in ["right", "left", "both"]:
        var button := _button(hand.capitalize() + (" hands" if hand == "both" else " hand"),
            func():
                _send_action({"action": "hand", "hand": hand})
                _navigate("practice")
        )
        button.configure("choice")
        hand_buttons[hand] = button
        hand_row.add_child(button)
    var course_choices := HBoxContainer.new()
    course_choices.add_theme_constant_override("separation", 8)
    content.add_child(course_choices)
    skip_stage_button = _button("Skip this step · no mastery", func(): _send_action({"action":"skip_stage", "reason":"Learner chose to skip this step"}), false, "review")
    skip_stage_button.custom_minimum_size.x = 250
    course_choices.add_child(skip_stage_button)
    placement_button = _button("Try original notes", func(): _send_action({"action":"place_original"}), false, "primary")
    course_choices.add_child(placement_button)
    var scroll := ScrollContainer.new()
    scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
    scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
    content.add_child(scroll)
    content.add_child(_button("Advanced practice controls", _open_advanced_pause, false, "settings"))
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


func _populate_library() -> void:
    if library_rows == null:
        return
    if library_filter_timer != null and not library_filter_timer.is_stopped():
        library_filter_timer.stop()
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
            var diagnosis: Dictionary = library_health_info.get("items", {}).get(identifier, {})
            var status: String = str(diagnosis.get("status", ""))
            var detail: String = format_name + "  ·  " + hint
            if status == "error":
                detail = "Needs attention  ·  " + detail
            elif status == "warning":
                detail = "Repaired  ·  " + detail
            var row := LibraryRow.new()
            row.pressed.connect(func(): _open_library_piece(identifier))
            library_rows.add_child(row)
            row.set_entry(title.replace("_", " "), detail, status)
            row.custom_minimum_size.y = 72.0 * ui_scale
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

func _resize_open_picker() -> void:
    if open_panel == null:
        return
    # Centered from the actual viewport. Never a 240px-wide, 900px-tall
    # native subwindow, including fullscreen and high-density displays.
    var width: float = minf(620.0, maxf(280.0, size.x-36.0))
    # The PanelContainer is positioned directly under the full-screen
    # overlay, NOT under a CenterContainer that might expand it vertically.
    # The scroll area handles short laptop windows without hiding Cancel.
    var height: float = minf(570.0, size.y*.84)
    open_panel.custom_minimum_size = Vector2(width, 0)
    open_panel.size = Vector2(width, height)
    open_panel.position = (size - open_panel.size)*.5


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
    _send_action({"action":"open_at", "bar":int(open_measure.value),
        "mode":"practice" if open_mode.selected == 1 else "learn"})


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
    open_measure.get_line_edit().grab_focus()


func _update_hand_stages(state: Dictionary) -> void:
    var stages: Array = state.get("hand_stages", [])
    practice_stage_bar.visible = not stages.is_empty()
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
        var word: String = "BOTH HANDS" if hand == "both" else str(hand).to_upper() + " HAND"
        label.text = ("✓ " if complete else "▶ " if active else "○ ") + word + (
            " · DONE" if complete else " · NOW" if active else " · LOCKED" if locked else " · NEXT")
        label.add_theme_color_override("font_color",
            Color("#79DAAD") if complete else INK if active else MUTED)
        # Read as a three-step instrument runway, not three separate
        # web-form cards. The active hand has a bright lower edge; completed
        # hands retain a quieter mint trace, and locked ones recede.
        var stage_color := (Color("#183932") if active else
            Color("#152C27") if complete else Color("#142321"))
        var style := Design.surface(stage_color, 5)
        style.set_content_margin_all(8)
        style.set_border_width_all(0)
        style.set_border_width(SIDE_BOTTOM, 3 if active else 2)
        style.border_color = (Color("#8DE9C9") if active else
            Color("#4DAE8D") if complete else Color("#2A4540"))
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


func _open_library_piece(identifier: String) -> void:
    # Pause requests are asynchronous. Store a quick selection and open it
    # once the transport has acknowledged the pause, rather than dropping
    # the click while action_pending is true.
    if action_pending:
        pending_library_piece = identifier
        library_message.text = "Preparing your selected music…"
        return
    library_error = ""
    library_message.text = "Opening score…"
    library_message.add_theme_color_override("font_color", MUTED)
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
    # On-device frame intervals, opt-in only. _delta is never fed back into
    # the backend tempo or score assessment; tests may call _process(0).
    if frame_diagnostics and current_screen == "practice":
        var frame_result: Dictionary = frame_meter.record_frame(_delta)
        if not frame_result.is_empty():
            frame_result["score_tiles"] = score_tiles.size()
            frame_result["visible_score_tiles"] = visible_tile_end - visible_tile_begin
            frame_result["tile_upload_mib"] = snappedf(
                float(score_tile_upload_bytes) / (1024.0 * 1024.0), .01)
            frame_result["resident_tile_mib"] = snappedf(
                float(resident_tile_bytes) / (1024.0 * 1024.0), .01)
            frame_result["packed_tile_mib"] = snappedf(
                float(score_tile_packed_bytes) / (1024.0 * 1024.0), .01)
            frame_result["resident_tiles"] = resident_tile_end - resident_tile_begin \
                if deferred_tile_mode else score_tiles.size()
            frame_result["tile_restores"] = restored_tile_count
            frame_result["tile_geometry_rebuilds"] = tile_geometry_rebuilds
            frame_result["tile_window_changes"] = tile_window_changes
            frame_result["phase"] = str(last_state.get("phase", ""))
            print("PHASE8D_FRAME_INTERVALS:", JSON.stringify(frame_result))
    # Animate short-lived hit pulses between HTTP state samples.
    var ticks: int = Time.get_ticks_msec()
    var effects_were_visible: bool = (not score_overlay.hit_pulses.is_empty()
        or not score_overlay.wrong_ghosts.is_empty()
        or not score_overlay.preview_pulses.is_empty())
    var effects_before: int = score_overlay.hit_pulses.size() + \
        score_overlay.wrong_ghosts.size() + score_overlay.preview_pulses.size()
    for index in range(score_overlay.hit_pulses.size() - 1, -1, -1):
        if int(score_overlay.hit_pulses[index].get("until_ms", 0)) <= ticks:
            score_overlay.hit_pulses.remove_at(index)
    for index in range(score_overlay.wrong_ghosts.size() - 1, -1, -1):
        if int(score_overlay.wrong_ghosts[index].get("until_ms", 0)) <= ticks:
            score_overlay.wrong_ghosts.remove_at(index)
    for index in range(score_overlay.preview_pulses.size() - 1, -1, -1):
        if int(score_overlay.preview_pulses[index].get("until_ms", 0)) <= ticks:
            score_overlay.preview_pulses.remove_at(index)
    # Redraw the *last* expiry too. Otherwise a paused score may retain
    # the final faded wrong pitch until another transport update arrives.
    var effects_after: int = score_overlay.hit_pulses.size() + \
        score_overlay.wrong_ghosts.size() + score_overlay.preview_pulses.size()
    var pulse_expired: bool = effects_before != effects_after
    # Expired particles disappear immediately; live particles and
    # anticipation normally redraw at 30 rather than 60 FPS.
    if effects_were_visible and (pulse_expired or \
            ticks - last_overlay_animation_ms >= 33):
        last_overlay_animation_ms = ticks
        score_overlay.queue_redraw()
        note_reactions.queue_redraw()
    apply_tempo_button.disabled = action_pending
    # Continuous Listen drift measurements are display/audio only and
    # never feed back into the MIDI grading or the Python transport.
    if demo_player != null and str(last_state.get("mode", "")) == "listen" \
            and bool(last_state.get("running", false)):
        demo_player.keep_synchronized(_transport_beat_now(),
            maxf(1.0, float(last_state.get("bpm", 60.0))))
        if listen_sync_diagnostics and ticks - last_listen_sync_report_ms >= 1000:
            last_listen_sync_report_ms = ticks
            print("PHASE8B_LISTEN_SOFTWARE_SYNC:",
                JSON.stringify(demo_player.sync_report()))
    _update_count_in()
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
    if str(last_state.get("mode", "practice")) == "learn":
        score_overlay.next_chord.clear()
        _layout_guided_score()
        return
    score_overlay.guided_active = false
    if last_state.is_empty() or not bool(last_state.get("running", false)) or layout_revision != revision:
        if not score_overlay.preview_pulses.is_empty():
            score_overlay.preview_pulses.clear()
            score_overlay.queue_redraw()
            note_reactions.queue_redraw()
        last_playhead_strike_transport = -1
        score_overlay.onset_until_ms = 0
        # The very first expected attack must be visible before the pianist
        # starts. A ready practice passage should not show an empty score
        # until Play is pressed or the first physical key is struck.
        var ready_preview: Array = []
        if layout_revision == revision and str(last_state.get("phase", "")) in ["ready", "disconnected"]:
            ready_preview = LivingScore.cue(living_chords,
                float(last_state.get("play_from_beat", 0.0)), score_overlay.marks)
        if ready_preview != score_overlay.next_chord:
            score_overlay.next_chord = ready_preview
            score_overlay.queue_redraw()
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
    var musical_clock: float = play_from + clock
    var strike_transport: int = int(last_state.get("transport_id", 0))
    if not active or last_playhead_strike_transport != strike_transport \
            or musical_clock < last_playhead_strike_beat - .001:
        last_playhead_strike_transport = strike_transport
        last_playhead_strike_beat = musical_clock
        score_overlay.onset_until_ms = 0
    else:
        if musical_clock - last_playhead_strike_beat <= .5:
            var onsets: Array = LivingScore.groups_crossed(
                living_chords, last_playhead_strike_beat, musical_clock)
            if not onsets.is_empty():
                score_overlay.onset_until_ms = Time.get_ticks_msec() + 180
                if bool(last_state.get("preview_only", false)) or str(last_state.get("mode", "")) == "listen":
                    _preview_note_arrivals(onsets)
        last_playhead_strike_beat = musical_clock
    # The note cue is a musical preview on the exact score, not an evaluator.
    # During count-in show the first chord. It disappears during rests longer
    # than 1.25 beats, and correct/missed/wrong pitch marks always take priority.
    score_overlay.next_chord = LivingScore.cue(
        living_chords, beat, score_overlay.marks)
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
    # Score transforms are still applied each visual frame. The line,
    # notehalo and particles do not need to repaint that often.
    if ticks - last_overlay_animation_ms >= 33:
        last_overlay_animation_ms = ticks
        score_overlay.queue_redraw()

func _layout_guided_score() -> void:
    score_overlay.guided_active = true
    score_overlay.next_chord.clear()
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
    if points.size() < 2:
        return .01
    # Start at the same indexed region as the camera. A silent lead-in
    # should not walk a hundred pages of future notes every rendered frame.
    var low := 0
    var high: int = points.size()
    while low < high:
        var middle: int = (low + high) / 2
        if float(points[middle].get("beat", 0.0)) <= beat + .000001:
            low = middle + 1
        else:
            high = middle
    var index: int = clampi(low - 1, 0, points.size() - 2)
    for offset in range(index, mini(index + 3, points.size() - 1)):
        var left: Dictionary = points[offset]
        var right: Dictionary = points[offset + 1]
        var span: float = float(right.get("beat", 0.0)) - float(left.get("beat", 0.0))
        if span > 0.0 and float(right.x) > float(left.x):
            return (float(right.x) - float(left.x)) / span
    return .01

func _position_at_beat(beat: float) -> Dictionary:
    var points: Array = score_layout.get("anchors", [])
    if points.is_empty():
        return {}
    # A long imported song may have thousands of anchors. The old linear
    # search walked from beat zero at every display frame (120 times/sec on
    # many laptops), causing rising CPU use and late camera frames.
    var low := 0
    var high: int = points.size()
    while low < high:
        var middle: int = (low + high) / 2
        if float(points[middle].get("beat", 0.0)) <= beat + .000001:
            low = middle + 1
        else:
            high = middle
    var at: int = maxi(0, low - 1)
    var left: Dictionary = points[at]
    var position: Dictionary = left.duplicate()
    if at + 1 < points.size():
        var right: Dictionary = points[at + 1]
        # The generated scrolling strip is a single time-proportional
        # canvas. Interpolate right THROUGH former page/system joins. Holding
        # the last notehead until the next system would stop the camera for
        # part of a beat and then jump ahead despite equalized engraving.
        var continuous: bool = score_layout.has("strip_size")
        if continuous or (int(left.get("page", 0)) == int(right.get("page", 0)) and str(left.get("system", "")) == str(right.get("system", ""))):
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
    speed_label.text = "%d BPM · target %d" % [int(parsed.get("bpm", 0)),int(parsed.get("target_bpm", parsed.get("bpm", 0)))]
    var recovery_notice: Variant = parsed.get("recovery_notice")
    speed_label.add_theme_font_size_override("font_size", _ui_font(16 if size.x < 900 else 18))
    speed_label.tooltip_text = "Current practice tempo and your selected target"
    hand_label.text = "Both hands" if str(parsed.get("hand", "right")) == "both" else str(parsed.get("hand", "right")).capitalize() + " hand"
    hand_label.tooltip_text = "Current hand of the backend lesson"
    game_input_indicator.present(parsed)
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
    # While notes are moving, the fixed HUD already identifies the hand.
    # Restore the three-hand roadmap at Ready, Pause and Feedback.
    if str(parsed.get("phase", "")) in ["playing", "count_in"]:
        practice_stage_bar.visible = false
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
        or score_view.texture == null or layout_revision != revision)
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
        if challenge_kind == "success":
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
    start_button.disabled = not active_transport and (score_view.texture == null or layout_revision != revision)
    start_button.call("configure", "pause" if start_button.text == "Pause" else "play",
        active_transport and not bool(parsed.get("paused", false)))
    listen_button.call("configure", "practice" if str(parsed.get("mode", "")) == "listen" else "listen",
        str(parsed.get("mode", "")) == "listen")
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
        living_chords.clear()
        source_layout = {}
        page_images.clear()
        current_page = -1
        score_view.texture = null
        score_error = ""
        _refresh_score_status()
        score_overlay.showing = false
        score_overlay.marks = []
        score_overlay.next_chord.clear()
        score_overlay.hit_pulses.clear()
        score_overlay.wrong_ghosts.clear()
        score_overlay.preview_pulses.clear()
        note_reactions.queue_redraw()
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
            if score_overlay.preview_pulses.size() >= 24:
                score_overlay.preview_pulses.pop_front()
            score_overlay.preview_pulses.append({
                "page": int(note.get("page", 0)),
                "x": float(note.get("x", 0.0)),
                "y": float(note.get("y", 0.0)),
                "duration_ms": 620,
                "until_ms": now_ms + 620,
                "status": "preview"
            })
    game_stage.preview_react()
    score_overlay.queue_redraw()
    note_reactions.queue_redraw()


func _clear_assessed_effects_in_ungraded_mode(state: Dictionary) -> void:
    # Mode-specific colors have distinct meanings. Clear old assessed
    # success when entering preview/Listen, and clear blue preview sparks
    # when returning to a real scored MIDI take.
    var ungraded: bool = bool(state.get("preview_only", false)) \
        or str(state.get("mode", "")) == "listen"
    if ungraded:
        if score_overlay.hit_pulses.is_empty() and score_overlay.wrong_ghosts.is_empty():
            return
        score_overlay.hit_pulses.clear()
        score_overlay.wrong_ghosts.clear()
        # The stage is a separate canvas and must drop its older earned
        # success energy along with the note particles on mode change.
        game_stage.impact_energy = 0.0
        game_stage.queue_redraw()
    else:
        if score_overlay.preview_pulses.is_empty():
            return
        score_overlay.preview_pulses.clear()
    score_overlay.queue_redraw()
    note_reactions.queue_redraw()


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
                score_overlay.wrong_ghosts.append({
                    "page": int(note.get("page", 0)),
                    "x": float(note.get("x", 0.0)),
                    "y": float(note.get("y", 0.0)),
                    "duration_ms": 420,
                    "until_ms": Time.get_ticks_msec() + remaining
                })
                if score_overlay.wrong_ghosts.size() > 32:
                    score_overlay.wrong_ghosts.pop_front()
                game_stage.react("unexpected")
                note_reactions.queue_redraw()
                break
            continue
        if status not in ["on_time", "early", "late"] or age > .42:
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
                    "note_id": note_id,
                    "duration_ms": 450,
                    "until_ms": Time.get_ticks_msec() + maxi(1, 450 - int(age * 1000.0))
                })
                if score_overlay.hit_pulses.size() > 32:
                    score_overlay.hit_pulses.pop_front()
                game_stage.react(status)
                note_reactions.queue_redraw()
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
    cached_bounds.clear()
    cached_bounds_revision = -1
    score_layout = parsed
    source_layout = parsed
    # Select once for this score revision. All pages need identical
    # resolution for the geometric strip; resizing during playback must
    # never mix pixel densities within one source score.
    score_raster_width = ScoreQuality.png_width(source_layout, score_frame.size.y)
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
    if score_request.request(URL + "/score.png?page=%d&width=%d" % [
            page, score_raster_width]) != OK:
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
    # Validate that the source page has real notation. System tiles
    # are the only visible score images; an additional cropped whole-page
    # image would create an unused full-resolution CPU allocation.
    var opaque_bounds := _visible_engraving_bounds(picture)
    if opaque_bounds.size.x < 16 or opaque_bounds.size.y < 16:
        _score_failed("The engraving image contains no visible musical notation")
        return
    var should_defer: bool = source_layout.get("systems", []).size() >= \
        ScoreStrip.DEFERRED_MIN_SYSTEMS
    var strip: Dictionary = ScoreStrip.build(
        source_layout, page_images, should_defer)
    if strip.has("error") or strip["tiles"].is_empty():
        _score_failed(str(strip.get("error", "No staff systems were found in the engraving")))
        return
    for tile in score_tiles:
        score_content.remove_child(tile)
        tile.queue_free()
    score_tiles.clear()
    score_tile_scale = -1.0
    visible_tile_begin = 0
    visible_tile_end = 0
    tile_window_initialized = false
    deferred_tile_mode = false
    resident_tile_begin = 0
    resident_tile_end = 0
    resident_tile_bytes = 0
    restored_tile_count = 0
    tile_geometry_rebuilds = 0
    tile_window_changes = 0
    strip_tiles = strip["tiles"]
    deferred_tile_mode = should_defer
    score_tile_upload_bytes = 0
    score_tile_packed_bytes = 0
    for item in strip_tiles:
        score_tile_upload_bytes += int(item.get("upload_bytes", 0))
        var packed: PackedByteArray = item.get("packed_ink", PackedByteArray())
        score_tile_packed_bytes += packed.size()
    var notation_material := Design.notation_material()
    for item in strip_tiles:
        var tile := TextureRect.new()
        tile.texture = item.get("texture") as Texture2D
        tile.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
        tile.stretch_mode = TextureRect.STRETCH_SCALE
        tile.mouse_filter = Control.MOUSE_FILTER_IGNORE
        tile.material = notation_material
        score_content.add_child(tile)
        score_content.move_child(tile, score_overlay.get_index())
        score_tiles.append(tile)
    if not deferred_tile_mode:
        resident_tile_begin = 0
        resident_tile_end = score_tiles.size()
        resident_tile_bytes = score_tile_upload_bytes
    score_layout = strip["layout"]
    cached_bounds.clear()
    cached_bounds_revision = -1
    var rail_groups: Array = score_layout.get("systems", [])
    if not rail_groups.is_empty():
        staff_continuity.set_rails(rail_groups[0].get("staff_lines", []))
    else:
        staff_continuity.set_rails([])
    # Exact same measured staff geometry for the MIDI resonance glow.
    note_reactions.staff_lines = staff_continuity.staff_lines
    living_chords = LivingScore.prepare(score_layout)
    score_crop_origin = Vector2.ZERO
    score_crop_size = Vector2.ONE
    # The invisible score image is only a readiness sentinel. Do not keep
    # an extra complete engraved page uploaded to the GPU.
    var ready_pixel := Image.create(1, 1, false, Image.FORMAT_LA8)
    ready_pixel.fill(Color(1, 1, 1, 0))
    score_view.texture = ImageTexture.create_from_image(ready_pixel)
    score_view.visible = false
    score_overlay.image_size = strip["size"]
    note_reactions.active_page = 0
    note_reactions.crop_origin = Vector2.ZERO
    note_reactions.crop_size = Vector2.ONE
    # Pixel-accurate relative staff gap follows the same strip scaling as
    # every real glyph, even at unusual screen sizes and dense chord voicing.
    var systems: Array = score_layout.get("systems", [])
    if not systems.is_empty():
        var staff_lines: Array = systems[0].get("staff_lines", [])
        if staff_lines.size() >= 2:
            var gap_ratio: float = absf(float(staff_lines[1]) - float(staff_lines[0]))
            score_overlay.staff_gap_fraction = gap_ratio
            note_reactions.staff_gap_fraction = gap_ratio
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
            library_message.add_theme_color_override("font_color", Color("#FF8B82"))
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
    elif path == "/library/health":
        _request_library_health()
    elif path == "/library/open":
        library_error = ""
        _populate_library()
        score_error = ""
        var opened: Variant = _decode_json(body)
        if opened is Dictionary and bool(opened.get("warmup", false)):
            _navigate("practice")
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
        pending_library_piece = ""
        call_deferred("_open_library_piece", queued)

func _has_active_transport() -> bool:
    return bool(last_state.get("running", false)) or str(last_state.get("phase", "")) in ["count_in", "playing", "paused", "feedback", "recovering", "loading"]

func _listen_or_return_to_practice() -> void:
    # Listen is a one-tap reversible action, never a scored take.
    if str(last_state.get("mode", "")) == "listen":
        _send_action({"action": "practice", "wait_for_player": true})
    else:
        _send_action({"action": "listen"})


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

func _open_advanced_pause() -> void:
    _navigate("practice")
    advanced_pause_open = true
    if bool(last_state.get("paused", false)):
        pause_sheet.present(last_state)
    elif _has_active_transport():
        _send_action({"action":"pause"})
    else:
        # Advanced options require a live paused attempt; use Path controls
        # directly when nothing is playing.
        advanced_pause_open = false


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
    if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]:
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
        if pause_sheet != null and pause_sheet.visible and event.keycode in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]:
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
                _send_action({"action":"stop"})
                get_viewport().set_input_as_handled()
            KEY_LEFT:
                _send_action({"action":"previous"})
                get_viewport().set_input_as_handled()
            KEY_RIGHT:
                _send_action({"action":"next"})
                get_viewport().set_input_as_handled()
