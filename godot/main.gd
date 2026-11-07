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
const ContinuousScoreFlow := preload("res://continuous_score_flow.gd")
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
const ScoreRunway := preload("res://score_runway.gd")
const PracticeFrameCoordinator := preload("res://practice_frame_coordinator.gd")
const PracticeStatePresenter := preload("res://practice_state_presenter.gd")
const CommandFailurePresenter := preload("res://command_failure_presenter.gd")
const CommandSuccessPolicy := preload("res://command_success_policy.gd")
const CommandSuccessPresenter := preload("res://command_success_presenter.gd")
const CommandSuccessEffects := preload("res://command_success_effects.gd")
const PracticeControlPolicy := preload("res://practice_control_policy.gd")
const StreamAdmission := preload("res://score_stream_admission.gd")
const MetronomeFrameCoordinator := preload("res://metronome_frame_coordinator.gd")
const CountInVoicePlayer := preload("res://countin_voice_player.gd")
const CommandRequestState := preload("res://command_request_state.gd")
const NavigationPolicy := preload("res://navigation_policy.gd")
const LiveMidiFeedback := preload("res://live_midi_feedback.gd")
const FeedbackEventInbox := preload("res://feedback_event_inbox.gd")

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
var learning_status_request
var learning_status_pending := false
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

var startup_last_music_checked := false
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

var last_state: Dictionary = {}
var last_state_tick := 0
var visual_transport_clock = VisualTransportClock.new()
var score_flow = ContinuousScoreFlow.new()
var metronome_frame
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
var last_published_control_started_ms := -1
# Opt-in diagnostic hook for the actual headless UI integration test only.
var phase0_smoke_mode := false
var listen_sync_diagnostics := false
var frame_diagnostics := false
var last_timing_phase := ""
var last_timing_transport := -1
var last_timing_revision := -1
var frame_meter = FrameMeter.new()
var frame_coordinator
var state_presenter
var command_failure_presenter
var command_state = CommandRequestState.new()
var command_success_presenter
var command_success_effects
var lesson_request
var device_pending: bool:
    get:
        return midi_devices.pending
    set(value):
        midi_devices.pending = value
var demo_player: Node
var ui_scale := 1.0
var practice_backdrop: ColorRect
# One acknowledged channel delivers every note-feedback event exactly once.
var feedback_inbox = FeedbackEventInbox.new()
var live_midi_feedback = LiveMidiFeedback.new()
var state_poll_timer: Timer
var inprocess_bus: Node
var score_runway
var _pending_stream_renderer
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
    # Audio has one root-owned lifetime, including score revisions, Pause,
    # source selection and renderer replacement. The visual countdown merely
    # delegates speech to this service.
    var spoken_countin := CountInVoicePlayer.new()
    spoken_countin.name = "CountInVoicePlayer"
    add_child(spoken_countin)
    practice_view.bind_countin_voice_player(spoken_countin)
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
    score_runway = ScoreRunway.new()
    add_child(score_runway)
    score_runway.configure(self,practice_view.stage,score_session,inprocess_bus)
    score_runway.preload_problem.connect(func(message: String):
        practice_view.present_message(message))
    score_runway.renderer_promoted.connect(func(renderer):
        renderer.fingering_change_requested.connect(
            _on_fingering_change_requested))
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
    learning_status_request = _new_request(_on_learning_status)
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
    frame_coordinator = PracticeFrameCoordinator.new(
        practice_view,settings_view,lesson_view,lesson_session,
        score_effects,demo_player,frame_meter)
    state_presenter = PracticeStatePresenter.new(
        practice_view,settings_view,lesson_view,lesson_session,
        score_effects,state_poll_timer)
    command_failure_presenter = CommandFailurePresenter.new(
        library_view,practice_view,settings_view,home_view)
    command_success_presenter = CommandSuccessPresenter.new(
        library_view,practice_view,settings_view,lesson_session)
    command_success_effects = CommandSuccessEffects.new(
        command_success_presenter,
        Callable(self,"_on_state"),
        Callable(self,"_navigate"),
        Callable(self,"_request_settings"),
        Callable(self,"_request_library"),
        Callable(self,"_request_library_health"),
        Callable(self,"_refresh_score_status"))
    metronome_frame = MetronomeFrameCoordinator.new(
        settings_view,practice_view,visual_transport_clock,
        Callable(self,"_transport_beat_at"),Callable(self,"_count_tick"),
        Callable(self,"_raw_click"))
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

func _count_tick(accent: bool, sampled_beat: float = NAN) -> void:
    if click_player == null:
        return
    if not bool(preferences.get("metronome", true)) and \
            (sampled_beat if is_finite(sampled_beat) else _transport_beat_now()) >= 0.0:
        return
    click_player.stream = click_high if accent else click_low
    click_player.play()
    # The smoke confirms clock scheduling; it cannot test physical speakers.
    if phase0_smoke_mode:
        print("PHASE0_CLICK:", str(last_state.get("phase", "")))

func _transport_beat_now() -> float:
    return _transport_beat_at(Time.get_ticks_msec())

func _transport_beat_at(at_ms: int) -> float:
    # Keep the score's musical clock phase-locked across uneven replies.
    # The Python engine remains authoritative for note timing and assessment.
    if visual_transport_clock.matches(last_state):
        return visual_transport_clock.score_beat(at_ms)
    # Direct-state smoke fixtures, before any network snapshot is received.
    var beat: float = float(last_state.get("clock_beat", 0.0))
    if bool(last_state.get("running", false)) and not bool(last_state.get("paused", false)):
        var elapsed: float = maxf(0.0, float(at_ms - last_state_tick) / 1000.0)
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
    return _unrolled_score_beat_at(transport_clock,Time.get_ticks_msec())

func _unrolled_score_beat_at(transport_clock: float, at_ms: int) -> float:
    # The renderer's position is never a transport seek. The hardware
    # grading clock remains in _transport_beat_at; this one always advances.
    return score_flow.project(at_ms)


func _raw_click(accent: bool) -> void:
    # Calibration and retry preparation are audible even if practice
    # metronome is disabled. No MIDI clock is changed.
    click_player.stream = click_high if accent else click_low
    click_player.play()

func _update_count_in(sampled_beat: float = NAN, now_ms: int = -1) -> void:
    if now_ms < 0:
        now_ms = Time.get_ticks_msec()
    metronome_frame.update(last_state,last_state_tick,sampled_beat,now_ms)


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
    # Every loaded Practice phase has the same forward-moving stage.
    # This includes ordinary pauses, completed takes, manual retries,
    # waiting for MIDI, and a missing physical keyboard.
    var active: bool = current_screen == "practice" and bool(state.get("loaded",false))
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
    var decision: Dictionary = NavigationPolicy.plan(
        screen,current_screen,str(last_state.get("phase","")),
        command_state.pending,command_state.operation,command_state.control_action)
    screen = str(decision["target"])
    var previous_screen: String = str(decision["previous"])
    if bool(decision["remember_settings"]):
        settings_return_screen = previous_screen
    if bool(decision["pause"]):
        _send_action({"action":"pause"})
    current_screen = screen
    if practice_backdrop != null:
        practice_backdrop.visible = screen == "practice"
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
    # The practice score is one seamless, edge-to-edge reading surface.
    # Keep the other application pages' background unchanged.
    practice_backdrop = ColorRect.new()
    practice_backdrop.name = "PracticeBackdrop"
    practice_backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
    practice_backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    practice_backdrop.color = Color.WHITE
    practice_backdrop.visible = false
    var backdrop_shader := Shader.new()
    backdrop_shader.code = """shader_type canvas_item;
void fragment() {
    vec2 offset = (UV - vec2(0.46,0.47)) * vec2(1.14,0.98);
    float vignette = smoothstep(0.10,0.86,length(offset));
    vec3 center = vec3(0.004,0.120,0.111);
    vec3 edge = vec3(0.002,0.062,0.059);
    COLOR = vec4(mix(center,edge,vignette),1.0);
}
"""
    var backdrop_material := ShaderMaterial.new()
    backdrop_material.shader = backdrop_shader
    practice_backdrop.material = backdrop_material
    add_child(practice_backdrop)

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
        var is_practice: bool = screens.has("practice") and panel == screens["practice"]
        panel.add_theme_constant_override("margin_left", margin)
        panel.add_theme_constant_override("margin_right", margin)
        panel.add_theme_constant_override("margin_top", 14 if compact else 19)
        # Reserve a little room below the transport, as in the reference.
        panel.add_theme_constant_override("margin_bottom",
            (22 if compact else 48) if is_practice else (14 if compact else 19))
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
        _send_command("settings.update", {"music_dir": path}))
    settings_view.device_selected.connect(_choose_device)
    settings_view.tempo_requested.connect(func(bpm: int):
        _send_action({"action": "tempo", "bpm": bpm}))
    settings_view.strategy_requested.connect(func(strategy: String):
        _send_command("settings.update", {"exercise_strategy": strategy}))
    settings_view.timing_strategy_requested.connect(func(strategy: String):
        _send_command("settings.update", {"timing_strategy": strategy}))
    settings_view.tempo_strategy_requested.connect(func(strategy: String):
        _send_command("settings.update", {"tempo_strategy": strategy}))
    settings_view.diagnosis_strategy_requested.connect(func(strategy: String):
        _send_command("settings.update", {"diagnosis_strategy": strategy}))
    settings_view.learner_strategy_requested.connect(func(strategy: String):
        _send_command("settings.update", {"learner_strategy": strategy}))
    settings_view.mistake_response_requested.connect(func(strategy: String):
        _send_command("settings.update", {"mistake_response_strategy": strategy}))
    settings_view.metronome_requested.connect(func(enabled: bool):
        _send_command("settings.update", {"metronome": enabled}))
    settings_view.retention_save_requested.connect(func(days: int, budget_mib: int):
        _send_command("settings.update", {
            "evidence_retention_days": days, "evidence_budget_mib": budget_mib}))
    settings_view.history_export_requested.connect(func(path: String, include_detail: bool):
        _send_command("learning.export", {"path": path, "include_detail": include_detail}))
    settings_view.piece_history_delete_requested.connect(func(fingerprint: String):
        _send_command("learning.delete_piece", {"fingerprint": fingerprint, "confirm": true}))
    settings_view.learner_history_delete_requested.connect(func():
        _send_command("learning.delete_learner", {"confirm": true}))
    settings_view.calibration_requested.connect(func(action: String):
        _send_action({"action": action}))
    settings_view.midi_range_requested.connect(func(action: String):
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
    lesson_session.request_failed.connect(lesson_view.present_error)

func _request_lesson() -> void:
    if lesson_request == null or lesson_request.request("lesson.overview") != OK:
        lesson_session.complete_response(null, "Cannot request lesson overview", Time.get_ticks_msec())

func _on_lesson(code: int, body: PackedByteArray) -> void:
    lesson_session.complete_response(_decode_json(body) if code == 0 else null,
        "" if code == 0 else _command_failure(code, body), Time.get_ticks_msec())

func _refresh_score_status(status: Dictionary = {}) -> void:
    if practice_view != null and score_session != null:
        practice_view.present_score(
            status if not status.is_empty() else score_session.status())

func _score_failed(message: String) -> void:
    if score_session != null:
        score_session.fail(message)

func _on_score_asset_failure(message: String) -> void:
    if phase0_smoke_mode:
        print("PHASE0_SCORE_ERROR:", message)
    practice_view.present_message(message)

func _on_score_assets_invalidated(_new_revision: int) -> void:
    live_midi_feedback.clear()
    living_chords.clear()
    score_effects.marks.clear()
    score_effects.hit_pulses.clear()
    score_effects.wrong_ghosts.clear()
    score_effects.preview_pulses.clear()

func _on_score_layout_published(_published_revision: int, values: Dictionary) -> void:
    living_chords = LivingScore.prepare(values)
    live_midi_feedback.bind_layout(values, _published_revision)

func _on_score_published(published_revision: int) -> void:
    if score_runway != null:
        score_runway.active_revision_published(published_revision)
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

func _on_library(code: int, body: PackedByteArray) -> void:
    library_catalog.on_catalog(code, body)

func _request_library_health() -> void:
    library_catalog.request_health()

func _on_library_health(code: int, body: PackedByteArray) -> void:
    library_catalog.on_health(code, body)

func _start_library_health() -> void:
    library_catalog.start_health(command_state.pending)


func _open_library_piece(identifier: String, resume_saved := false) -> void:
    # Pause requests are asynchronous. Store a quick selection and open it
    # once the transport has acknowledged the pause, rather than dropping
    # the click while command_state.pending is true.
    if command_state.pending:
        command_state.queue_library(identifier,resume_saved)
        library_view.present_open_status("Preparing your selected music…")
        return
    library_view.present_open_status("Opening score…")
    command_state.resume_requested = resume_saved
    _send_command("library.open", {"id": identifier})


func _request_settings() -> void:
    if settings_pending or settings_request == null:
        return
    settings_pending = true
    if settings_request.request("settings.snapshot") != OK:
        settings_pending = false

func _on_settings(code: int, body: PackedByteArray) -> void:
    settings_pending = false
    if code != 0:
        settings_view.present_message(_command_failure(code, body))
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    preferences = parsed
    settings_view.present_preferences(preferences)
    _request_learning_status()
    _apply_window_mode(bool(preferences.get("fullscreen", true)))
    var saved_device := str(preferences.get("midi_device", ""))
    if not saved_device.is_empty() and str(last_state.get("device", "")) == "" and not device_names.is_empty():
        if device_names.has(saved_device) and not saved_device.to_lower().contains("midi through"):
            _choose_device(saved_device)

func _request_learning_status() -> void:
    if learning_status_pending or learning_status_request == null:
        return
    learning_status_pending = true
    if learning_status_request.request("learning.status") != OK:
        learning_status_pending = false
        settings_view.present_message("Cannot read local learning history")

func _on_learning_status(code: int, body: PackedByteArray) -> void:
    learning_status_pending = false
    if code != 0:
        settings_view.present_message(_command_failure(code, body))
        return
    var parsed = _decode_json(body)
    if parsed is Dictionary:
        settings_view.present_learning_status(parsed)

func _learning_command_accepted(operation: String, values: Dictionary) -> void:
    if operation == "learning.export":
        settings_view.present_message("Learning history exported to " + str(values.get("path", "chosen file")))
    else:
        settings_view.present_message("Current piece history and learning progress deleted."
            if operation == "learning.delete_piece" else "All learner history and learning progress deleted.")
        lesson_session.invalidate()
        _request_settings()
        _request_library()
    _request_learning_status()

func _apply_window_mode(fullscreen: bool) -> void:
    var expected := Window.MODE_FULLSCREEN if fullscreen else Window.MODE_WINDOWED
    if get_window().mode != expected:
        get_window().mode = expected

func _on_fullscreen_toggle(enabled: bool) -> void:
    _apply_window_mode(enabled)
    _send_command("settings.update", {"fullscreen": enabled})

func _toggle_fullscreen() -> void:
    var enabled := get_window().mode != Window.MODE_FULLSCREEN
    settings_view.present_window_mode(enabled)
    _on_fullscreen_toggle(enabled)

func _read_feedback_events() -> void:
    if inprocess_bus == null or not inprocess_bus.is_ready():
        return
    _consume_feedback_reply(inprocess_bus.take_feedback_events())
    inprocess_bus.request_feedback_events(feedback_inbox.acknowledged)

func _consume_feedback_reply(reply: Variant) -> void:
    for event in feedback_inbox.accept(reply):
        _dispatch_feedback_event(event)
        # Acknowledge only after the consumers returned a final outcome.
        feedback_inbox.acknowledge(int(event["sequence"]))

func _dispatch_feedback_event(event: Dictionary) -> void:
    # Each event names its own take; no state snapshot is consulted.
    practice_view.stage.feedback.ingest(event)
    if str(event.get("kind","")) == "attack":
        # Python stamps `received_at` in backend monotonic seconds; the
        # clock's backend offset maps it to local ticks. Without a calibrated
        # offset the age is unknown and the reaction plays.
        var age_ms := 0.0
        if visual_transport_clock.has_backend_offset and event.has("received_at"):
            age_ms = float(Time.get_ticks_msec()) - (
                float(event["received_at"]) * 1000.0 +
                visual_transport_clock.backend_offset_ms)
        live_midi_feedback.react(event, score_effects, practice_view.stage,
            layout_revision if layout_revision == revision else -1, age_ms)

func _poll() -> void:
    if score_session != null and not practice_view.is_source_picker_open():
        score_session.poll(Time.get_ticks_msec())

    if not state_pending and not command_state.pending:
        state_pending = true
        state_request_started_ms = Time.get_ticks_msec()
        if state_request.request("state.snapshot") != OK:
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
    var ticks: int = Time.get_ticks_msec()
    var beat: float = _transport_beat_at(ticks)
    var source_bpm: float = float(last_state.get("bpm",40.0))
    if bool(last_state.get("running",false)) or bool(last_state.get("paused",false)):
        source_bpm = TempoTimeline.bpm_at_beat(beat,source_bpm,
            last_state.get("tempo_segments",[]))
    score_flow.sample(ticks,source_bpm)
    score_effects.prune_expired(ticks)
    _read_feedback_events()
    _update_count_in(beat,ticks)
    var arrivals: Array = frame_coordinator.advance(
        last_state,beat,_unrolled_score_beat_at(beat,ticks),ticks,_delta,
        command_state.pending,current_screen,_native_score_ready(),living_chords,
        frame_diagnostics,listen_sync_diagnostics,phase0_smoke_mode)
    if not arrivals.is_empty():
        score_effects.record_preview(arrivals,practice_view.stage,ticks)
    if score_runway != null:
        # Old score clips continue exiting even during a revision load or
        # a source-picker transition with no currently loaded piece.
        score_runway.present_frame(last_state,_unrolled_score_beat_at(beat,ticks))

func _on_state(code: int, body: PackedByteArray, sample_started_ms: int = -1) -> void:
    if sample_started_ms < 0:
        state_pending = false
        # A pre-action snapshot can arrive after the control response. It
        # must not put a fresh count-in or paused attempt back in its old state.
        if (command_state.started_ms > 0 and
                state_request_started_ms <= command_state.started_ms) or (
                last_published_control_started_ms >= 0 and
                state_request_started_ms <= last_published_control_started_ms):
            # Old polls remain invalid even after command_state.finish()
            # clears started_ms. Never replace a newer graded transport
            # with the earlier READY/paused snapshot.
            return
    if code != 0:
        practice_view.present_message(_command_failure(code, body))
        return
    var parsed = _decode_json(body)
    if typeof(parsed) != TYPE_DICTIONARY:
        return
    if frame_diagnostics:
        var phase_name: String = str(parsed.get("phase", ""))
        var attempt: int = int(parsed.get("transport_id", -1))
        var score_rev: int = int(parsed.get("revision", -1))
        if phase_name != last_timing_phase or attempt != last_timing_transport \
                or score_rev != last_timing_revision:
            print("TRANSPORT_TRANSITION:", JSON.stringify({
                "phase":phase_name, "transport_id":attempt,
                "revision":score_rev,
                "state_request_ms":Time.get_ticks_msec()-state_request_started_ms,
                "score_ready":_native_score_ready(),
                "layout_pending":layout_pending,
                "model_pending":timeline_model_pending,
                "awaiting_score_revision":parsed.get("awaiting_score_revision"),
                "visual_scroll_beat":parsed.get("visual_scroll_beat"),
                "visual_scroll_speed":parsed.get("visual_scroll_speed")}))
            last_timing_phase = phase_name
            last_timing_transport = attempt
            last_timing_revision = score_rev
    # A long MIDI should not engrave its default first passage while the
    # learner is still choosing a source measure in the library. Wait for
    # open_at to select the real passage before requesting any score pages.
    if practice_view.is_source_picker_open():
        practice_view.suppress_piano_input(parsed)
        return
    last_state = parsed
    settings_view.present_midi_key_range(
        parsed.get("midi_key_range",{}) if parsed.get("midi_key_range") is Dictionary else {})
    _update_visual_frame_rate(parsed)
    score_effects.transition_mode(parsed,practice_view.stage)
    var received_ms: int = Time.get_ticks_msec()
    var started_ms: int = (state_request_started_ms
        if sample_started_ms < 0 else sample_started_ms)
    last_state_tick = int((started_ms+received_ms)/2.0)
    visual_transport_clock.accept(parsed,last_state_tick,received_ms)
    var promoted_this_snapshot := false
    if score_runway != null:
        promoted_this_snapshot = score_runway.promote_if_ready(parsed)
        if not promoted_this_snapshot:
            # A manual, unprepared lesson change must replace the active
            # renderer BEFORE asset reset, preserving its moving notes.
            score_runway.preserve_unprepared_revision(parsed)
    if demo_player != null and bool(parsed.get("loaded",false)):
        demo_player.synchronize(parsed,_transport_beat_at(received_ms))
    score_session.update_context(parsed,received_ms)
    if score_runway != null:
        score_runway.update_state(parsed,received_ms)
    if bool(parsed.get("loaded",false)) and practice_view.stage.renderer != null:
        var beat: float = _transport_beat_at(received_ms)
        var world: float = _unrolled_score_beat_at(beat,received_ms)
        var renderer = practice_view.stage.renderer
        renderer.present(
            parsed,beat,world-float(renderer.runway_origin_beat))
        # The backend supplies one immutable next-score decision: source,
        # exact MIDI-graded monotonic deadline, and plan identity. This
        # includes failure recovery and disconnected-MIDI preview loops.
        # No streak, mastery or repeat policy may run in the renderer.
        var next_plan: Variant = parsed.get("score_queue_next")
        var transport_key: String = "%s|%d|%d|%s" % [
            str(parsed.get("piece_fingerprint","")),
            int(parsed.get("revision",-1)),
            int(parsed.get("transport_id",-1)),
            str(parsed.get("mode","practice"))]
        if next_plan is Dictionary and \
                visual_transport_clock.has_backend_offset and \
                str(parsed.get("mode","")) == "practice" and \
                not bool(parsed.get("paused",false)) and \
                not promoted_this_snapshot and \
                renderer._stream_armed_serial < 0 and \
                (renderer._stream_last_take != transport_key or \
                    str(parsed.get("phase","")) in [
                        "feedback","recovering","preview_gap"]) and \
                next_plan.has("deadline_at_ms") and \
                next_plan.has("source_from_beat") and \
                next_plan.has("plan_id"):
            var deadline_ms: int = roundi(
                float(next_plan["deadline_at_ms"]) +
                visual_transport_clock.backend_offset_ms)
            renderer.enqueue_recovery_queue(world,
                float(next_plan["source_from_beat"]),
                score_flow.project(deadline_ms),str(next_plan["plan_id"]))
        # Atomically bind an acknowledged transport ID to the already armed
        # source BEFORE publishing the new backend state. Otherwise the UI
        # may observe a running Retry while its note copy still has the
        # prepared key until the next animation frame.
        practice_view.stage.renderer.present_flow(world,parsed,beat)
    state_presenter.present(
        parsed,current_screen,command_state.pending,_native_score_ready(),
        fingering_save_error,
        demo_player != null and bool(demo_player.get("audio_error")),
        sample_started_ms < 0,received_ms,phase0_smoke_mode)
    _refresh_score_status()


func _request_layout() -> void:
    if score_session != null:
        score_session.request_layout()

func _on_layout(code: int, body: PackedByteArray) -> void:
    if score_session != null:
        var began: int = Time.get_ticks_msec()
        score_session.complete_response(
            "layout", score_session.pending_id("layout"), code, body,
            Time.get_ticks_msec())
        if frame_diagnostics:
            print("SCORE_ASSET_MAIN_THREAD:", JSON.stringify({
                "kind":"layout", "elapsed_ms":Time.get_ticks_msec()-began,
                "revision":score_session.revision, "phase":last_state.get("phase")}))

func _finish_native_score() -> void:
    if score_session != null:
        score_session.finish_native_score()

func _request_timeline_model() -> void:
    if score_session != null:
        score_session.request_model()

func _on_timeline_model(code: int, body: PackedByteArray) -> void:
    if score_session != null:
        var began: int = Time.get_ticks_msec()
        score_session.complete_response(
            "model", score_session.pending_id("model"), code, body,
            Time.get_ticks_msec())
        if frame_diagnostics:
            print("SCORE_ASSET_MAIN_THREAD:", JSON.stringify({
                "kind":"model", "elapsed_ms":Time.get_ticks_msec()-began,
                "revision":score_session.revision, "phase":last_state.get("phase")}))


func _send_action(command: Dictionary) -> void:
    var requested: String = str(command.get("action", ""))
    var previous_action: String = command_state.control_action
    if not command_state.action_requested(requested):
        # Busy operations still show their current action; Pause/Stop queues.
        practice_view.begin_action(requested, previous_action)
        return
    practice_view.begin_action(requested)
    if requested in ["start","restart","resume"] and \
            str(last_state.get("mode","practice")) in ["practice","perform"] and \
            practice_view.stage.renderer != null:
        # The user's action reserves the next musical deadline beyond all
        # notes still moving on the visual bar. The engine, not the GUI,
        # applies this lead to MIDI grading and count-in.
        var visual_now: float = score_flow.project(Time.get_ticks_msec())
        var renderer = practice_view.stage.renderer
        var opening: float = maxf(0.0,float(last_state.get("play_from_beat",0.0)))
        if requested == "resume":
            opening = maxf(opening,opening+_transport_beat_at(Time.get_ticks_msec()))
        # One preflighted transaction plans the maximal retractable suffix,
        # verifies a future admission, then commits it with one graded deadline.
        # Failure cannot mutate the online queue before a valid plan exists.
        var reserved: Dictionary = renderer.reserve_transport_action(
            requested,visual_now,opening)
        if reserved.is_empty():
            command_state.abort_action()
            practice_view.finish_action()
            practice_view.present_message(
                "Score reservation failed · see SCORE_TRANSPORT diagnostic")
            return
        _pending_stream_renderer = renderer
        command = command.duplicate(true)
        command["presentation_lead_seconds"] = StreamAdmission.lead_seconds(
            float(reserved["start_world"]),visual_now,score_flow.bpm)
        if requested == "resume":
            command["reuse_pending_score"] = bool(
                reserved.get("reused_unplayed_count_in",false))
        var written_rest: float = float(renderer.practice_timeline.get(
            "gap",{}).get("duration_beats",0.0))
        command["continuous_horizon_beats"] = StreamAdmission.automatic_horizon(
            written_rest,renderer._stream_right_beats(),
            renderer._stream_header_beats(0.0))
    _send_command("practice.command", command)


func _present_fingering_status(summary: Variant) -> void:
    var issues: int = practice_view.stage.renderer.annotations.fingering_placement_issues.size() if _native_score_ready() else 0
    practice_view.stage.present_fingering(summary, issues, fingering_save_error)

func _on_fingering_change_requested(source_id: String, finger: Variant) -> void:
    if command_state.pending or not _native_score_ready() or layout_pending or timeline_model_pending or \
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
    _send_command("fingering.correct",payload)

func _flush_transport_action() -> void:
    var action: String = command_state.take_transport()
    if not action.is_empty():
        _send_action({"action":action})

func _cancel_pending_stream_arm() -> void:
    if _pending_stream_renderer != null and \
            is_instance_valid(_pending_stream_renderer):
        _pending_stream_renderer.cancel_stream_arm()
    _pending_stream_renderer = null


func _send_command(operation: String, payload: Dictionary) -> void:
    if not command_state.begin(operation,Time.get_ticks_msec()):
        if operation == "practice.command":
            _cancel_pending_stream_arm()
        return
    practice_view.present_busy(true)
    settings_view.present_busy(true)
    var err: int = command_state.dispatch(action_request,operation,payload)
    if err != OK:
        if operation == "practice.command":
            _cancel_pending_stream_arm()
        practice_view.present_busy(false)
        settings_view.present_busy(false)
        if operation == "practice.command":
            practice_view.finish_action()
        var message := "Cannot reach practice engine (status %d)" % err
        if operation == "fingering.correct":
            fingering_save_error = message
            _present_fingering_status(last_state.get("fingering",{}))
        var queued_library_failed: bool = command_state.discard_library()
        command_failure_presenter.present(message,operation,queued_library_failed)
        _flush_transport_action()

func _on_action(code: int, body: PackedByteArray) -> void:
    # Only the active request may publish a success or error. A timed-out
    # callback or a canceled worker completion has no live command owner.
    if not command_state.pending:
        return
    var completed: Dictionary = command_state.finish()
    practice_view.present_busy(false)
    settings_view.present_busy(false)
    var operation: String = str(completed["operation"])
    if operation == "practice.command":
        practice_view.finish_action()
    var resume_saved: bool = bool(completed["resume_saved"])
    var completed_action: String = str(completed["action"])
    if code != 0:
        if operation == "practice.command":
            _cancel_pending_stream_arm()
        var message := _command_failure(code, body)
        if operation == "fingering.correct":
            fingering_save_error = message
            _present_fingering_status(last_state.get("fingering",{}))
        var queued_library_failed: bool = command_state.discard_library()
        command_failure_presenter.present(message,operation,queued_library_failed)
        _flush_transport_action()
        return
    var opened: Variant = _decode_json(body) if operation == "library.open" else null
    if operation in ["learning.export", "learning.delete_piece", "learning.delete_learner"]:
        var result = _decode_json(body)
        _learning_command_accepted(operation, result if result is Dictionary else {})
    var decision: Dictionary = CommandSuccessPolicy.decide(
        operation,completed_action,resume_saved,opened)
    if str(decision["kind"]) == "fingering":
        fingering_save_error = ""
    elif str(decision["kind"]) == "library_open":
        score_error = ""
    if bool(decision.get("publish_state",false)):
        last_published_control_started_ms = maxi(
            last_published_control_started_ms,int(completed["started_ms"]))
    if operation == "practice.command" and \
            _pending_stream_renderer != null and \
            is_instance_valid(_pending_stream_renderer):
        # Commit the provisional source owner only after successful backend
        # acknowledgement, before the response publishes its transport ID.
        _pending_stream_renderer.acknowledge_stream_arm()
    command_success_effects.apply(decision,opened,
        code,body,int(completed["started_ms"]))
    if operation == "practice.command":
        _pending_stream_renderer = null
    _flush_transport_action()
    _poll()
    var deferred_library: Dictionary = command_state.take_library()
    if not str(deferred_library["piece"]).is_empty():
        call_deferred("_open_library_piece",
            str(deferred_library["piece"]),bool(deferred_library["resume_saved"]))

func _apply_practice_control(decision: Dictionary) -> void:
    if decision.has("message"):
        practice_view.present_message(str(decision["message"]))
    elif decision.has("action"):
        _send_action(decision)

func _listen_or_return_to_practice() -> void:
    _apply_practice_control(PracticeControlPolicy.listen_toggle(last_state))

func _toggle_playing() -> void:
    _apply_practice_control(PracticeControlPolicy.primary(
        last_state, _native_score_ready(), score_error))

func _toggle_pause() -> void:
    _apply_practice_control(PracticeControlPolicy.pause_toggle(
        last_state, score_error))

func _restart_practice() -> void:
    _apply_practice_control(PracticeControlPolicy.retry(
        last_state, _native_score_ready()))

func _request_devices() -> void:
    midi_devices.discover()

func _on_devices(code: int, body: PackedByteArray) -> void:
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
