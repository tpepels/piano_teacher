extends Control

# Lightweight Godot presentation. Python owns MIDI timestamps, tempo and grading.
const Design := preload("res://practice_theme.gd")
const INK := Design.STONE
const MUTED := Design.SECONDARY_INK
const PAPER := Design.FOREST
const WHITE := Design.PANEL
const ACCENT := Design.TEAL
const ScoreEffects := preload("res://score_effects.gd")
const LivingScore := preload("res://living_score.gd")
const GameBackdrop := preload("res://game_backdrop.gd")
const UI := preload("res://ui_factory.gd")
const LibraryScreen := preload("res://library_screen.gd")
const VisualTransportClock := preload("res://visual_transport_clock.gd")
const TempoTimeline := preload("res://tempo_timeline.gd")
const FrameMeter := preload("res://frame_meter.gd")
const SourceMeasurePicker := preload("res://source_measure_picker.gd")
const SettingsScreen := preload("res://settings_screen.gd")
const HomeScreen := preload("res://home_screen.gd")
const LessonScreen := preload("res://lesson_screen.gd")
const LessonSession := preload("res://lesson_session.gd")
const PracticeScreen := preload("res://practice_screen.gd")
const NavigationDrawer := preload("res://navigation_drawer.gd")
const LibraryCatalogCoordinator := preload("res://library_catalog_coordinator.gd")
const MidiDeviceCoordinator := preload("res://midi_device_coordinator.gd")
const ScoreAssetSession := preload("res://score_asset_session.gd")
const ScoreAssetQueue := preload("res://score_asset_queue.gd")
const InProcessBus := preload("res://inprocess_bus.gd")

var current_screen := "practice"
var settings_return_screen := "practice"
var navigation_drawer = NavigationDrawer.new()
var settings_view: SettingsScreen
var home_view: HomeScreen
var practice_view: PracticeScreen
var lesson_view: LessonScreen
var lesson_session := LessonSession.new()
var screens: Dictionary = {}
var library_catalog = LibraryCatalogCoordinator.new()
var settings_request
var library_view: LibraryScreen
var settings_pending := false
var preferences: Dictionary = {}
var page_margins: Array[MarginContainer] = []
var fingering_save_error := ""
var score_session
var score_queue = ScoreAssetQueue.new()
var native_score_piece_fingerprint: String:
    get:
        return score_session.native_score_piece_fingerprint if score_session != null else ""
var score_error: String:
    get:
        return score_session.score_error if score_session != null else ""
    set(value):
        if score_session != null:
            score_session.score_error = value

var pending_library_piece := ""
var pending_library_resume := false
var library_resume_requested := false
var startup_last_music_checked := false
var calibration_tick_index := -999
var recovery_click_tick := -999
var retry_first_click_sent := false
var last_post_path := ""
var last_control_action := ""
var pending_transport_action := ""
var action_request_started_ms := 0
var state_request
var layout_request
var action_request
var midi_devices = MidiDeviceCoordinator.new()
var device_request  # Existing request callback wiring.
var device_menu_requested: bool:
    get:
        return midi_devices.picker_requested
    set(value):
        midi_devices.picker_requested = value
var score_effects = ScoreEffects.new()
var count_tick_index := -1
var play_tick_index := -1
var click_player: AudioStreamPlayer
var click_high: AudioStreamWAV
var click_low: AudioStreamWAV
var device_names: Array:
    get:
        return midi_devices.names
    set(value):
        midi_devices.names = value
var revision: int:
    get:
        return score_session.revision if score_session != null else -1
    set(value):
        if score_session != null:
            score_session.revision = value
var state_pending := false
var layout_revision: int:
    get:
        return score_session.layout_revision if score_session != null else -1
var layout_pending: bool:
    get:
        return score_session.layout_pending if score_session != null else false
var score_layout: Dictionary:
    get:
        return score_session.layout_snapshot() if score_session != null else {}
var living_chords: Array = []
var rendered_revision: int:
    get:
        return score_session.rendered_revision if score_session != null else -1

var action_pending := false
var last_state: Dictionary = {}
var last_state_tick := 0
var last_playhead_strike_beat := -INF
var last_playhead_strike_transport := -1
var visual_transport_clock = VisualTransportClock.new()
# The native compositor is the sole production score view.
var timeline_model_request
var timeline_model_pending: bool:
    get:
        return score_session.timeline_model_pending if score_session != null else false
var timeline_model_revision: int:
    get:
        return score_session.timeline_model_revision if score_session != null else -1
var timeline_model_retry_after_ms: int:
    get:
        return score_session.timeline_model_retry_after_ms if score_session != null else 0

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
var lesson_request
var device_pending: bool:
    get:
        return midi_devices.pending
    set(value):
        midi_devices.pending = value
var demo_player: Node
var ui_scale := 1.0
var last_seen_midi_visual_sequence := 0
var state_poll_timer: Timer
var inprocess_bus: Node
var native_started := false

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
    inprocess_bus = InProcessBus.new()
    add_child(inprocess_bus)
    var native_error: String = str(inprocess_bus.get("ready_error"))
    if not native_error.is_empty():
        printerr("Embedded Piano Teacher cannot start: " + native_error)
        get_tree().quit(1)
        return
    # Apply one device-independent Window scale before creating the controls.
    # Do not enlarge fonts and controls a second time in the layouts.
    _configure_ui_scaling()
    ui_scale = _readable_ui_scale()
    _build_interface()
    demo_player = preload("res://demo_player.gd").new()
    demo_player.call("configure", inprocess_bus)
    add_child(demo_player)
    settings_view.present_volume(float(demo_player.get("listen_volume_db")))
    demo_player.prepared.connect(func(token: String, ready_revision: int):
        _send_action({"action": "demo_ready", "token": token, "revision": ready_revision}))
    demo_player.failed.connect(func(message: String): practice_view.present_message(message))
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
    score_queue.attach(self, score_session, inprocess_bus)
    layout_request = score_queue.layout_request
    timeline_model_request = score_queue.model_request

    action_request = _new_request(_on_action)
    action_request.timeout = 90.0
    device_request = _new_request(_on_devices)
    midi_devices.attach_request(device_request)
    library_catalog.attach_requests(
        _new_request(library_catalog.on_catalog),
        _new_request(library_catalog.on_health))
    settings_request = _new_request(_on_settings)
    lesson_request = _new_request(_on_lesson)
    state_poll_timer = Timer.new()
    state_poll_timer.wait_time = 0.15
    state_poll_timer.autostart = true
    state_poll_timer.timeout.connect(_poll)
    add_child(state_poll_timer)
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
        if current_screen == "library" and library_catalog.health_running:
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
    # Keep the score's musical clock phase-locked across uneven replies.
    # The Python engine remains authoritative for note timing and assessment.
    if visual_transport_clock.matches(last_state):
        return visual_transport_clock.score_beat(Time.get_ticks_msec())
    # Direct-state smoke fixtures, before any network snapshot is received.
    var beat: float = float(last_state.get("clock_beat", 0.0))
    if bool(last_state.get("running", false)) and not bool(last_state.get("paused", false)):
        var elapsed: float = maxf(0.0, float(Time.get_ticks_msec() - last_state_tick) / 1000.0)
        var segments: Array = last_state.get("tempo_segments", [])
        if segments.is_empty():
            beat += elapsed * float(last_state.get("bpm", 60.0)) / 60.0
        else:
            beat = TempoTimeline.beat_at_seconds(
                float(last_state.get("clock_elapsed_seconds", 0.0)) + elapsed,
                float(last_state.get("bpm", 60.0)), segments)
    return beat

# Projection only: never change the backend's local MIDI grading clock.
# Across repeats the model is drawn at consecutive positions on one infinite
# visual axis. During feedback/recovery the server supplies the desired scroll
# direction; extrapolate its last snapshot between state polls.
func _unrolled_score_beat(transport_clock: float) -> float:
    # One presentation clock owns scrolling, reversal, retry count-in
    # and resumed playback; there is no independent retry camera.
    if visual_transport_clock.initialized and last_state.has("visual_offset_beats"):
        return visual_transport_clock.visual_beat(Time.get_ticks_msec())
    if not last_state.has("visual_offset_beats"):
        return NAN
    return float(last_state.get("visual_scroll_beat", transport_clock))


func _raw_click(accent: bool) -> void:
    # Calibration and retry preparation are audible even if practice
    # metronome is disabled. No MIDI clock is changed.
    click_player.stream = click_high if accent else click_low
    click_player.play()

func _update_count_in() -> void:
    var now_ms := Time.get_ticks_msec()
    var calibration: Dictionary = last_state.get("midi_calibration", {})
    if bool(calibration.get("active", false)):
        recovery_click_tick = -999
        var beat := float(calibration.get("beat", -2.0)) + \
            maxf(0.0, float(now_ms-last_state_tick)/1000.0) * \
            float(calibration.get("bpm", 80.0))/60.0
        settings_view.animate_calibration_beat(
            beat, true, int(calibration.get("round_beats", 12)),
            int(calibration.get("count_in", 4)))
        var interval := maxi(1, int(calibration.get("round_beats", 12)))
        var total := interval * maxi(1, int(calibration.get("rounds", 3)))
        if beat >= 0.0 and beat < float(total):
            var tick := floori(beat + .00001)
            if tick != calibration_tick_index:
                # Do not play a missed initial click halfway into its beat.
                var timely := calibration_tick_index != -999 or beat - float(tick) < .12
                calibration_tick_index = tick
                if timely:
                    var inside_round := posmod(tick, interval)
                    _raw_click(inside_round == 0 or
                        inside_round == int(calibration.get("count_in", 4)))
        return
    calibration_tick_index = -999
    if settings_view.calibration_beat_pulse != null and settings_view.calibration_beat_pulse.visible:
        settings_view.animate_calibration_beat(-1.0, false)

    if (str(last_state.get("phase", "")) in ["feedback", "recovering"]
            and visual_transport_clock.retry_active
            and visual_transport_clock.retry_preparing(now_ms)
            and not bool(last_state.get("paused", false))):
        var count_beat: float = visual_transport_clock.retry_count_in_beat(now_ms)
        var bar := maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4)))))
        practice_view.stage.count_in.present(count_beat, bar, true, false)
        var tick := floori(count_beat + .00001)
        if tick != recovery_click_tick:
            # The preparation measure is forward, always at one fixed BPM.
            if count_beat < .10 and count_beat >= -float(bar):
                _raw_click(posmod(tick, bar) == 0)
                if tick == 0:
                    retry_first_click_sent = true
            recovery_click_tick = tick
        return
    if last_state.is_empty() or not bool(last_state.get("running", false)):
        recovery_click_tick = -999
        practice_view.stage.count_in.present(0.0, 4, false, false)
        count_tick_index = -999
        play_tick_index = -1
        return
    recovery_click_tick = -999
    var beat: float = _transport_beat_now()
    var paused: bool = bool(last_state.get("paused", false))
    practice_view.stage.count_in.present(beat,
        maxi(1, int(round(float(last_state.get("count_in_bar_beats", 4))))),
        true, paused)
    var attempt: int = int(last_state.get("transport_id", 0))
    if attempt != last_audio_transport_id:
        count_tick_index = -999
        play_tick_index = -1
        last_audio_transport_id = attempt
    if paused:
        count_tick_index = int(floor(beat + .00001))
        return
    var tick := int(floor(beat + .00001))
    if tick != count_tick_index:
        count_tick_index = tick
        var bar_beats := maxi(1,int(round(float(last_state.get("count_in_bar_beats",4)))))
        if not (tick == 0 and retry_first_click_sent):
            _count_tick(posmod(tick,bar_beats) == 0)
        if tick >= 0:
            retry_first_click_sent = false


func _native_score_ready() -> bool:
    return score_session != null and score_session.is_ready()


func _visible_score_noteheads() -> int:
    if practice_view.stage.renderer == null or not practice_view.stage.renderer.is_visible_in_tree():
        return 0
    var viewport := Rect2(Vector2.ZERO, practice_view.stage.renderer.size)
    var visible := 0
    for point in practice_view.stage.renderer.drawn_noteheads.values():
        if viewport.has_point(point):
            visible += 1
    return visible


func _new_request(callback: Callable):
    var req = preload("res://inprocess_request.gd").new()
    req.configure(inprocess_bus)
    req.timeout = 5.0
    add_child(req)
    req.request_completed.connect(callback)
    return req

func _decode_json(body: PackedByteArray) -> Variant:
    # An engine command can return an empty payload on failure.
    # Avoid parsing empty JSON.
    if body.is_empty():
        return null
    var document := JSON.new()
    if document.parse(body.get_string_from_utf8()) != OK:
        return null
    return document.data

func _command_failure(code: int, body: PackedByteArray) -> String:
    var response = _decode_json(body)
    if typeof(response) == TYPE_DICTIONARY:
        return str(response.get("error", "Command failed (status %d)" % code))
    return "Embedded practice engine unavailable (status %d)" % code

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
    if node == library_view or node == settings_view or node == home_view or node == lesson_view or node == practice_view:
        return # Screens own their text scaling through apply_viewport.
    if node is Control and node.has_meta("ui_font_base"):
        (node as Control).add_theme_font_size_override(
            "font_size", _ui_font(int(node.get_meta("ui_font_base"))))
    if node.has_method("set_text_scale"):
        node.call("set_text_scale", ui_scale)
    for child in node.get_children():
        _resize_ui_fonts(child)


func _button(label: String, callback: Callable, primary := false,
        role: String = "") -> Button:
    var button := UI.button(label,
        role if not role.is_empty() else "primary" if primary else "secondary", ui_scale)
    button.pressed.connect(callback)
    return button


func _on_listen_volume_changed(db: float) -> void:
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
    var calibrating := current_screen == "settings" and bool(
        state.get("midi_calibration", {}).get("active", false))
    active = active or calibrating
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
    _update_visual_frame_rate(last_state)
    navigation_drawer.present(screen, previous_screen)
    if practice_view != null:
        practice_view.set_active(screen == "practice")
    for key in screens:
        (screens[key] as Control).visible = (str(key) == screen
            or str(key) == "practice" and screen != "practice")
    if screen == "library":
        _request_library()
        library_view.call_deferred("focus_search")
    elif screen == "settings":
        settings_view.begin_editing(last_state)
        _request_settings()
        _request_devices()
    elif screen == "lesson":
        lesson_session.refresh(Time.get_ticks_msec())


func _resize_overlay_drawer() -> void:
    navigation_drawer.resize(size)
    if library_view != null:
        library_view.apply_viewport(size, ui_scale)
    if lesson_view != null:
        lesson_view.apply_viewport(size, ui_scale)
    if settings_view != null:
        settings_view.apply_viewport(size, ui_scale)


func _go_back() -> void:
    _navigate(settings_return_screen if current_screen == "settings" else "practice")

func _build_interface() -> void:
    theme = Design.create()
    theme.default_font_size = _ui_font(16)
    var background := GameBackdrop.new()
    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    add_child(background)

    _build_home_screen()
    _build_library_screen()
    _build_settings_screen()
    _build_practice_screen()
    library_catalog.configure(library_view, home_view,
        _decode_json, _command_failure, _send_command)
    library_catalog.catalog_loaded.connect(_resume_last_music_on_start)
    midi_devices.configure(settings_view,
        _decode_json, _command_failure, _send_command)
    score_session = ScoreAssetSession.new(
        practice_view.stage.renderer, practice_view.stage.feedback)
    score_session.assets_invalidated.connect(_on_score_assets_invalidated)
    score_session.layout_published.connect(_on_score_layout_published)
    score_session.score_published.connect(_on_score_published)
    score_session.score_failed.connect(_on_score_asset_failure)
    score_session.status_changed.connect(_refresh_score_status)
    score_session.action_requested.connect(_send_action)


func _build_home_screen() -> void:
    var page := _screen("Home")
    screens["home"] = page
    home_view = HomeScreen.new()
    page.add_child(home_view)
    home_view.library_requested.connect(func(): _navigate("library"))
    home_view.settings_requested.connect(func(): _navigate("settings"))
    home_view.exit_requested.connect(_exit_app)
    home_view.open_requested.connect(_open_library_piece)


func _build_library_screen() -> void:
    var page := _screen("Library")
    screens["library"] = page
    library_view = LibraryScreen.new()
    page.add_child(library_view)
    library_view.open_requested.connect(_open_library_piece)
    library_view.refresh_requested.connect(_request_library)
    library_view.health_check_requested.connect(_start_library_health)


func _build_practice_screen() -> void:
    var page := _screen("Practice")
    screens["practice"] = page
    practice_view = PracticeScreen.new()
    page.add_child(practice_view)
    practice_view.navigation_requested.connect(_navigate)
    practice_view.command_requested.connect(_send_action)
    practice_view.play_requested.connect(_toggle_playing)
    practice_view.retry_requested.connect(_restart_practice)
    practice_view.listen_requested.connect(_listen_or_return_to_practice)
    practice_view.score_retry_requested.connect(_retry_score)
    practice_view.stage.renderer.fingering_change_requested.connect(_on_fingering_change_requested)
    _build_lesson_screen()
    navigation_drawer.mount(self, screens, _button, _navigate, _exit_app)
    _resize_overlay_drawer()
    _navigate("practice")
    _refresh_score_status()

func _update_responsive_layout() -> void:
    _configure_ui_scaling()
    ui_scale = _readable_ui_scale()
    theme.default_font_size = _ui_font(16)
    _resize_ui_fonts(self)
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
    if home_view != null:
        home_view.apply_viewport(size, ui_scale)
    _resize_overlay_drawer()
    practice_view.apply_viewport(size, ui_scale)

func _build_settings_screen() -> void:
    var page := _screen("Settings")
    screens["settings"] = page
    settings_view = SettingsScreen.new()
    settings_view.ui_scale = ui_scale
    settings_view.default_font = theme.default_font
    page.add_child(settings_view)
    settings_view.choose_devices_requested.connect(_show_devices)
    settings_view.refresh_devices_requested.connect(_request_devices)
    settings_view.save_folder_requested.connect(func(path: String):
        _send_command("/settings", {"music_dir": path}))
    settings_view.device_selected.connect(_choose_device)
    settings_view.tempo_requested.connect(func(bpm: int):
        _send_action({"action": "tempo", "bpm": bpm}))
    settings_view.strategy_requested.connect(func(strategy: String):
        _send_command("/settings", {"exercise_strategy": strategy}))
    settings_view.timing_strategy_requested.connect(func(strategy: String):
        _send_command("/settings", {"timing_strategy": strategy}))
    settings_view.tempo_strategy_requested.connect(func(strategy: String):
        _send_command("/settings", {"tempo_strategy": strategy}))
    settings_view.diagnosis_strategy_requested.connect(func(strategy: String):
        _send_command("/settings", {"diagnosis_strategy": strategy}))
    settings_view.learner_strategy_requested.connect(func(strategy: String):
        _send_command("/settings", {"learner_strategy": strategy}))
    settings_view.metronome_requested.connect(func(enabled: bool):
        _send_command("/settings", {"metronome": enabled}))
    settings_view.calibration_requested.connect(func(action: String):
        _send_action({"action": action}))
    settings_view.volume_changed.connect(_on_listen_volume_changed)
    settings_view.fullscreen_requested.connect(_on_fullscreen_toggle)
    settings_view.exit_requested.connect(_exit_app)

func _build_lesson_screen() -> void:
    var page := _screen("Lesson")
    screens["lesson"] = page
    lesson_view = LessonScreen.new()
    page.add_child(lesson_view)
    lesson_view.command_requested.connect(_send_action)
    lesson_view.practice_requested.connect(func(): _navigate("practice"))
    lesson_view.advanced_requested.connect(practice_view.open_advanced_pause)
    lesson_session.request_requested.connect(_request_lesson)
    lesson_session.overview_changed.connect(lesson_view.present_overview)
    lesson_session.overview_changed.connect(practice_view.stage.steps.present_overview)
    lesson_session.request_failed.connect(lesson_view.present_error)

func _request_lesson() -> void:
    if lesson_request == null or lesson_request.request("/lesson") != OK:
        lesson_session.complete_response(null, "Cannot request lesson overview", Time.get_ticks_msec())

func _on_lesson(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    lesson_session.complete_response(_decode_json(body) if code == 200 else null,
        "" if code == 200 else _command_failure(code, body), Time.get_ticks_msec())

func _refresh_score_status(_status: Dictionary = {}) -> void:
    if practice_view != null:
        practice_view.present_score(_native_score_ready(), score_error)

func _score_failed(message: String) -> void:
    if score_session != null:
        score_session.fail(message)

func _on_score_asset_failure(message: String) -> void:
    if phase0_smoke_mode:
        print("PHASE0_SCORE_ERROR:", message)
    practice_view.present_message(message)

func _on_score_assets_invalidated(_new_revision: int) -> void:
    living_chords.clear()
    score_effects.marks.clear()
    score_effects.hit_pulses.clear()
    score_effects.wrong_ghosts.clear()
    score_effects.preview_pulses.clear()

func _on_score_layout_published(_published_revision: int, values: Dictionary) -> void:
    living_chords = LivingScore.prepare(values)

func _on_score_published(published_revision: int) -> void:
    if phase0_smoke_mode:
        print("PHASE0_SCORE_READY_NATIVE: REVISION:", published_revision)
    print("NATIVE_MODEL_READY: ", published_revision,
        " NOTES: ", practice_view.stage.renderer.timeline.notes.size(),
        " DENSITY: ", practice_view.stage.renderer.timeline.pixels_per_beat)

func _retry_score() -> void:
    if score_session != null:
        score_session.retry(Time.get_ticks_msec())

func _resume_last_music_on_start(catalog: Dictionary) -> void:
    if startup_last_music_checked:
        return
    startup_last_music_checked = true
    var identifier := str(catalog.get("last_piece", ""))
    if identifier.is_empty():
        return
    for entry in catalog.get("pieces", []):
        if entry is Dictionary and str(entry.get("id", "")) == identifier:
            call_deferred("_open_library_piece", identifier, true)
            return

func _request_library() -> void:
    library_catalog.request_catalog()

func _on_library(result: int, code: int,
        headers: PackedStringArray, body: PackedByteArray) -> void:
    # Keep the existing application callback contract for in-process clients.
    library_catalog.on_catalog(result, code, headers, body)

func _request_library_health() -> void:
    library_catalog.request_health()

func _on_library_health(result: int, code: int,
        headers: PackedStringArray, body: PackedByteArray) -> void:
    library_catalog.on_health(result, code, headers, body)

func _start_library_health() -> void:
    library_catalog.start_health(action_pending)


func _open_library_piece(identifier: String, resume_saved := false) -> void:
    # Pause requests are asynchronous. Store a quick selection and open it
    # once the transport has acknowledged the pause, rather than dropping
    # the click while action_pending is true.
    if action_pending:
        pending_library_piece = identifier
        pending_library_resume = resume_saved
        library_view.present_open_status("Preparing your selected music…")
        return
    library_view.present_open_status("Opening score…")
    library_resume_requested = resume_saved
    _send_command("/library/open", {"id": identifier})


func _request_settings() -> void:
    if settings_pending or settings_request == null:
        return
    settings_pending = true
    if settings_request.request("/settings") != OK:
        settings_pending = false

func _on_settings(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    settings_pending = false
    if code != 200:
        settings_view.present_message(_command_failure(code, body))
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    preferences = parsed
    settings_view.present_preferences(preferences)
    _apply_window_mode(bool(preferences.get("fullscreen", true)))
    var saved_device := str(preferences.get("midi_device", ""))
    if not saved_device.is_empty() and str(last_state.get("device", "")) == "" and not device_names.is_empty():
        if device_names.has(saved_device) and not saved_device.to_lower().contains("midi through"):
            _choose_device(saved_device)

func _apply_window_mode(fullscreen: bool) -> void:
    var expected := Window.MODE_FULLSCREEN if fullscreen else Window.MODE_WINDOWED
    if get_window().mode != expected:
        get_window().mode = expected

func _on_fullscreen_toggle(enabled: bool) -> void:
    _apply_window_mode(enabled)
    _send_command("/settings", {"fullscreen": enabled})

func _toggle_fullscreen() -> void:
    var enabled := get_window().mode != Window.MODE_FULLSCREEN
    settings_view.present_window_mode(enabled)
    _on_fullscreen_toggle(enabled)

func _read_live_midi() -> void:
    if inprocess_bus == null or not inprocess_bus.is_ready():
        return
    for message in inprocess_bus.poll_midi(last_seen_midi_visual_sequence):
        if not message is Dictionary:
            continue
        var event: Dictionary = message
        event["age"] = 0.0
        practice_view.stage.feedback.accept_live_event(event, last_state)
        var display_state: Dictionary = last_state.duplicate(false)
        display_state["midi_visual_events"] = [event]
        _consume_live_piano_hits(display_state)

func _poll() -> void:
    if score_session != null and not practice_view.is_source_picker_open():
        score_session.poll(Time.get_ticks_msec())

    if not state_pending and not action_pending:
        state_pending = true
        state_request_started_ms = Time.get_ticks_msec()
        if state_request.request("/state") != OK:
            state_pending = false

func _process(_delta: float) -> void:
    if not native_started and inprocess_bus != null:
        var native_error: String = str(inprocess_bus.get("ready_error"))
        if not native_error.is_empty():
            printerr("Embedded Piano Teacher stopped: " + native_error)
            get_tree().quit(1)
            return
    if not native_started and inprocess_bus != null and inprocess_bus.is_ready():
        native_started = true
        _poll()
        _request_devices()
        _request_settings()
        _request_library()
    # On-device frame intervals, opt-in only. _delta is never fed back into
    # the backend tempo or score assessment; tests may call _process(0).
    if frame_diagnostics and current_screen == "practice":
        var frame_result: Dictionary = frame_meter.record_frame(_delta)
        if not frame_result.is_empty():
            frame_result["native_visible_noteheads"] = _visible_score_noteheads()
            frame_result["native_scanned_events"] = practice_view.stage.renderer.frame_scanned_events
            frame_result["phase"] = str(last_state.get("phase", ""))
            print("PHASE8D_FRAME_INTERVALS:", JSON.stringify(frame_result))
    # Animate short-lived hit pulses between state samples.
    var ticks: int = Time.get_ticks_msec()
    score_effects.prune_expired(ticks)
    _read_live_midi()
    settings_view.present_busy(action_pending)
    practice_view.present_busy(action_pending)
    lesson_view.present_busy(action_pending)
    lesson_session.ensure_current(ticks)
    # Start Listen WAV on the actual negative-to-zero beat crossing at
    # frame rate, not on the next 150ms state poll. This preserves the
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
            maxf(1.0, float(last_state.get("bpm", 60.0))),
            last_state.get("tempo_segments", []))
        if listen_sync_diagnostics and ticks - last_listen_sync_report_ms >= 1000:
            last_listen_sync_report_ms = ticks
            print("PHASE8B_LISTEN_SOFTWARE_SYNC:",
                JSON.stringify(demo_player.sync_report()))
    _update_count_in()
    # Frame-accurate native projection uses the SAME clock as score and
    # count-in. No Verovio X positions or per-note speed correction.
    if practice_view.stage.renderer != null \
            and bool(last_state.get("loaded", false)):
        var score_clock: float = _transport_beat_now()
        practice_view.stage.renderer.present(last_state, score_clock,
            _unrolled_score_beat(score_clock))
    # The stage's lighting follows exactly the musical beat used by the
    # moving Verovio notation. Preview/Listen use a neutral pulse; neither
    # this visual beat nor its glow can create grading events.
    if practice_view.stage.effects != null and bool(last_state.get("running", false)) \
            and not bool(last_state.get("paused", false)):
        practice_view.stage.effects.sync_beat(
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
        var playhead: float = practice_view.stage.renderer.size.x * .42
        var content_x: float = -practice_view.stage.renderer.clock_beat * practice_view.stage.renderer.timeline.pixels_per_beat
        if clock < 0.0 and tick != phase0_last_lead_tick:
            phase0_last_lead_tick = tick
            print("PHASE0_LEAD_BEAT:", clock, " CONTENT_X:", content_x,
                " CURSOR_X:", playhead, " VISIBLE:", practice_view.stage.renderer.visible)
        elif clock >= 0.0 and tick != phase0_last_cursor_tick:
            phase0_last_cursor_tick = tick
            print("PHASE0_VISIBLE_NOTES:", _visible_score_noteheads(),
                " PANEL_WIDTH:", practice_view.stage.score_frame.size.x, " CONTENT_X:", content_x)
            print("PHASE0_CURSOR_BEAT:", musical_clock, " SCREEN_X:", playhead,
                " VISIBLE:", practice_view.stage.renderer.visible, " CONTENT_X:", content_x)


func _on_state(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray, sample_started_ms: int = -1) -> void:
    if sample_started_ms < 0:
        state_pending = false
        # A pre-action snapshot can arrive after the control response. It
        # must not put a fresh count-in or paused attempt back in its old state.
        if action_request_started_ms > 0 and state_request_started_ms <= action_request_started_ms:
            return
    if code != 200:
        practice_view.present_message(_command_failure(code, body))
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    # A long MIDI should not engrave its default first passage while the
    # learner is still choosing a source measure in the library. Wait for
    # open_at to select the real passage before requesting any score pages.
    if practice_view.is_source_picker_open():
        practice_view.suppress_piano_input(parsed)
        return
    last_state = parsed
    _present_fingering_status(parsed.get("fingering",{}))
    lesson_view.present_context(parsed, action_pending)
    settings_view.present_calibration(
        parsed.get("midi_calibration", {}), int(parsed.get("midi_offset_ms", 0)))
    lesson_session.update_context(parsed, Time.get_ticks_msec())
    _update_visual_frame_rate(parsed)
    _clear_assessed_effects_in_ungraded_mode(parsed)
    # Low-latency local polling only while playing from a connected piano.
    # The backend remains authoritative; Godot never guesses note scoring.
    if state_poll_timer != null:
        var live_rate := (current_screen == "practice"
            and not str(parsed.get("device", "")).is_empty())
        # Note-on cues arrive via loopback datagrams within the next frame;
        # full-state projections can now poll slightly less often.
        var interval := 0.08 if live_rate else 0.15
        if absf(state_poll_timer.wait_time - interval) > 0.001:
            state_poll_timer.wait_time = interval
    settings_view.present_practice(parsed, current_screen == "settings")
    # The backend sampled the clock during this round trip. Estimate
    # that sample at the midpoint so music never waits for the poll interval.
    var started_ms: int = state_request_started_ms if sample_started_ms < 0 else sample_started_ms
    var received_ms: int = Time.get_ticks_msec()
    last_state_tick = int((started_ms + received_ms) / 2.0)
    visual_transport_clock.accept(parsed, last_state_tick, received_ms)
    if demo_player != null and bool(parsed.get("loaded",false)):
        demo_player.synchronize(parsed, _transport_beat_now())
    # ScoreAssetSession owns revision invalidation and the score_ready handshake.
    score_session.update_context(parsed, received_ms)
    practice_view.present(parsed, _native_score_ready(), action_pending,
        demo_player != null and bool(demo_player.get("audio_error")))
    if not bool(parsed.get("loaded",false)):
        _refresh_score_status()
        return
    var phase: String = str(parsed.get("phase","ready"))
    if phase0_smoke_mode and phase != phase0_last_phase:
        phase0_last_phase = phase
        print("PHASE0_PHASE:",phase)
    score_effects.marks = []
    for marker in parsed.get("feedback_marks", []):
        score_effects.marks.append(marker)
    _consume_live_piano_hits(parsed)

    practice_view.present_busy(action_pending)
    practice_view.consider_piano_start(sample_started_ms < 0, current_screen == "practice")
    _refresh_score_status()

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
    practice_view.stage.effects.preview_react()


func _clear_assessed_effects_in_ungraded_mode(state: Dictionary) -> void:
    # Mode-specific colors have distinct meanings. Clear old assessed
    # success when entering preview/Listen, and clear blue preview sparks
    # when returning to a real scored MIDI take.
    var ungraded: bool = bool(state.get("preview_only", false)) \
        or str(state.get("mode", "")) == "listen"
    if ungraded:
        if practice_view.stage.impact_callout != null:
            practice_view.stage.impact_callout.call("clear")
        if score_effects.hit_pulses.is_empty() and score_effects.wrong_ghosts.is_empty():
            return
        score_effects.hit_pulses.clear()
        score_effects.wrong_ghosts.clear()
        # The stage is a separate canvas and must drop its older earned
        # success energy along with the note particles on mode change.
        practice_view.stage.effects.impact_energy = 0.0
        practice_view.stage.effects.queue_redraw()
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
                practice_view.stage.effects.react("unexpected")
                practice_view.stage.impact_callout.call("react", "unexpected")
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
                practice_view.stage.effects.react(status)
                practice_view.stage.impact_callout.call("react", status)
                break


func _request_layout() -> void:
    if score_session != null:
        score_session.request_layout()

func _on_layout(_result: int, code: int, _headers: PackedStringArray,
        body: PackedByteArray) -> void:
    if score_session != null:
        score_session.complete_response(
            "layout", score_session.pending_id("layout"), code, body,
            Time.get_ticks_msec())

func _finish_native_score() -> void:
    if score_session != null:
        score_session.finish_native_score()

func _request_timeline_model() -> void:
    if score_session != null:
        score_session.request_model()

func _on_timeline_model(_result: int, code: int,
        _headers: PackedStringArray, body: PackedByteArray) -> void:
    if score_session != null:
        score_session.complete_response(
            "model", score_session.pending_id("model"), code, body,
            Time.get_ticks_msec())


func _send_action(command: Dictionary) -> void:
    var requested: String = str(command.get("action", ""))
    if action_pending:
        # Avoid an apparently dead button: the user sees precisely which
        # operation is still pending, rather than silently dropping clicks.
        if requested in ["pause", "stop"]:
            pending_transport_action = requested
        practice_view.begin_action(requested, last_control_action)
        return
    last_control_action = requested
    practice_view.begin_action(requested)
    _send_command("/control", command)


func _present_fingering_status(summary: Variant) -> void:
    var issues: int = practice_view.stage.renderer.annotations.fingering_placement_issues.size() if _native_score_ready() else 0
    practice_view.stage.present_fingering(summary, issues, fingering_save_error)

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
    _send_command("/fingering",payload)

func _flush_transport_action() -> void:
    if not pending_transport_action.is_empty():
        var action := pending_transport_action
        pending_transport_action = ""
        _send_action({"action": action})

func _send_command(path: String, payload: Dictionary) -> void:
    if action_pending:
        return
    action_pending = true
    practice_view.present_busy(true)
    # A complete local composition can take longer than a small control
    # request. Allow the bounded whole-piece inference to finish saving.
    action_request.timeout = 360.0 if path in ["/fingering","/load","/library/open"] else 5.0
    last_post_path = path
    action_request_started_ms = Time.get_ticks_msec()
    # The in-process request adapter is dynamically typed; := cannot infer
    # an Error from its Variant-returning request() method.
    var err: int = int(action_request.request(path, JSON.stringify(payload), "POST"))
    if err != OK:
        action_pending = false
        practice_view.present_busy(false)
        practice_view.present_message("Cannot reach practice engine", true)
        if path == "/fingering":
            fingering_save_error = "Cannot reach practice engine. Try the correction again."
            _present_fingering_status(last_state.get("fingering",{}))

func _on_action(_result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    action_pending = false
    practice_view.present_busy(false)
    if last_post_path == "/control":
        practice_view.finish_action()
    var path := last_post_path
    var resume_saved: bool = path == "/library/open" and library_resume_requested
    if path == "/library/open":
        library_resume_requested = false
    var completed_action := last_control_action
    if code != 200:
        var message := _command_failure(code, body)
        if path == "/fingering":
            fingering_save_error = message
            _present_fingering_status(last_state.get("fingering",{}))
        var queued_library_failed: bool = not pending_library_piece.is_empty()
        pending_library_piece = ""
        pending_library_resume = false
        if path == "/library/open":
            library_view.present_open_status("Cannot open score: " + message, true)
        elif queued_library_failed:
            library_view.present_open_status("Cannot open selected music: " + message, true)
        practice_view.present_message(message)
        settings_view.present_message(message)
        if path != "/library/open" and not queued_library_failed:
            library_view.present_request_error(message)
        home_view.present_operation_error(message)
        _flush_transport_action()
        return
    if path == "/fingering":
        fingering_save_error = ""
        _on_state(_result,code,_headers,body,action_request_started_ms)
    elif path == "/control":
        if completed_action == "reset_path":
            lesson_session.invalidate()
        if completed_action in ["calibration_apply", "calibration_reset"]:
            _request_settings()
        _on_state(_result, code, _headers, body, action_request_started_ms)
        if completed_action in ["skip_stage", "place_original", "revisit_trouble"]:
            _navigate("practice")
    elif path == "/library/health":
        _request_library_health()
    elif path == "/library/open":
        library_view.present_open_status("")
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
            practice_view.show_source_picker(opened)
    elif path == "/settings":
        settings_view.present_message("Settings saved")
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
        practice_view.present_message(score_error)
        return
    if str(last_state.get("mode", "")) == "listen" and not _has_active_transport():
        _send_action({"action": "practice" if bool(last_state.get("warmup", false)) else "listen"})
        return
    if str(last_state.get("mode", "practice")) == "learn":
        var phase: String = str(last_state.get("phase", "ready"))
        if phase not in ["paused", "guided_wait", "loading"] and not _native_score_ready():
            practice_view.present_message("Preparing sheet music - wait for the notes before starting")
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
        practice_view.present_message("Preparing sheet music - wait for the notes before starting")
        return
    _send_action({"action": "pause" if bool(last_state.get("running", false)) else "start"})

func _toggle_pause() -> void:
    if bool(last_state.get("paused", false)) and not score_error.is_empty():
        practice_view.present_message(score_error)
        return
    if _has_active_transport() or (str(last_state.get("mode", "practice")) == "learn" and str(last_state.get("phase", "")) in ["guided_wait", "paused"]):
        _send_action({"action": "resume" if bool(last_state.get("paused", false)) else "pause"})

func _restart_practice() -> void:
    if _native_score_ready():
        _send_action({"action": "learn_retry" if str(last_state.get("mode", "practice")) == "learn" else "restart"})

func _request_devices() -> void:
    midi_devices.discover()

func _on_devices(_result: int, code: int,
        _headers: PackedStringArray, body: PackedByteArray) -> void:
    midi_devices.receive(code, body, current_screen,
        str(last_state.get("device", "")),
        str(preferences.get("midi_device", "")))

func _show_devices() -> void:
    midi_devices.show_picker()

func _choose_device(name: String) -> void:
    midi_devices.choose(name)


func _input(event: InputEvent) -> void:
    if practice_view.handle_source_input(event):
        return
    if not event is InputEventKey:
        return
    # Search without hunting for a small field in the Music drawer.
    # Once focused, / remains normal text input.
    if event.pressed and not event.echo and current_screen == "library" \
            and ((event.ctrl_pressed and event.keycode == KEY_F) or
            (event.keycode == KEY_SLASH and not library_view.is_search_focused())):
        library_view.focus_search(true)
        get_viewport().set_input_as_handled()
        return
    if practice_view.retains_modal_navigation(event.keycode):
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
    if practice_view.is_source_picker_open():
        return
    if event is InputEventKey and event.pressed and not event.echo:
        if practice_view.retains_modal_navigation(event.keycode):
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
            practice_view.open_advanced_pause()
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
