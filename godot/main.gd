extends Control

## Scene composition and application lifetime. Python owns MIDI and grading;
## Godot sessions own presentation, input, requests and navigation.
const Design := preload("res://practice_theme.gd")
const ScoreEffects := preload("res://score_effects.gd")
const GameBackdrop := preload("res://game_backdrop.gd")
const UI := preload("res://ui_factory.gd")
const LibraryScreen := preload("res://library_screen.gd")
const VisualTransportClock := preload("res://visual_transport_clock.gd")
const ContinuousScoreFlow := preload("res://continuous_score_flow.gd")
const FrameMeter := preload("res://frame_meter.gd")
const SettingsScreen := preload("res://settings_screen.gd")
const CalibrationScreen := preload("res://calibration_screen.gd")
const HomeScreen := preload("res://home_screen.gd")
const PracticeScreen := preload("res://practice_screen.gd")
const NavigationDrawer := preload("res://navigation_drawer.gd")
const LibraryCatalogCoordinator := preload("res://library_catalog_coordinator.gd")
const MidiDeviceCoordinator := preload("res://midi_device_coordinator.gd")
const ScoreAssetSession := preload("res://score_asset_session.gd")
const ScoreAssetQueue := preload("res://score_asset_queue.gd")
const InProcessBus := preload("res://inprocess_bus.gd")
const ScoreRunway := preload("res://score_runway.gd")
const ScoreAdmissionGateway := preload("res://score_admission_gateway.gd")
const PracticeFrameCoordinator := preload("res://practice_frame_coordinator.gd")
const PracticeStatePresenter := preload("res://practice_state_presenter.gd")
const CommandFailurePresenter := preload("res://command_failure_presenter.gd")
const CommandSuccessPresenter := preload("res://command_success_presenter.gd")
const CommandSuccessEffects := preload("res://command_success_effects.gd")
const MetronomeFrameCoordinator := preload("res://metronome_frame_coordinator.gd")
const CountInVoicePlayer := preload("res://countin_voice_player.gd")
const CountInAudioSession := preload("res://countin_audio_session.gd")
const NavigationSession := preload("res://navigation_session.gd")
const ApplicationInputSession := preload("res://application_input_session.gd")
const SettingsInteractionSession := preload("res://settings_interaction_session.gd")
const PracticeFeedbackSession := preload("res://practice_feedback_session.gd")
const ApplicationStateInbox := preload("res://application_state_inbox.gd")
const ApplicationPollSession := preload("res://application_poll_session.gd")
const GuidedPresentationSession := preload("res://guided_presentation_session.gd")
const PracticePresentationSession := preload("res://practice_presentation_session.gd")
const DebugSessionLogger := preload("res://debug_session_logger.gd")

var navigation_session = NavigationSession.new()
var state_inbox = ApplicationStateInbox.new()
var poll_session = ApplicationPollSession.new()
var input_session = ApplicationInputSession.new()
var settings_interactions = SettingsInteractionSession.new()
var navigation_drawer = NavigationDrawer.new()
var settings_view: SettingsScreen
var calibration_view: CalibrationScreen
var home_view: HomeScreen
var practice_view: PracticeScreen
var screens: Dictionary = {}
var library_catalog = LibraryCatalogCoordinator.new()
var statistics_coordinator
var library_view: LibraryScreen
var page_margins: Array[MarginContainer] = []
var score_session
var score_queue = ScoreAssetQueue.new()
var midi_devices = MidiDeviceCoordinator.new()
var score_effects = ScoreEffects.new()
var countin_audio = CountInAudioSession.new()
var visual_transport_clock = VisualTransportClock.new()
var score_flow = ContinuousScoreFlow.new()
var guided_presentation = GuidedPresentationSession.new(score_flow)
var presentation_session
var debug_session_logger = DebugSessionLogger.new()
var metronome_frame
# Opt-in diagnostic hook for the actual headless UI integration test only.
var phase0_smoke_mode := false
var listen_sync_diagnostics := false
var frame_diagnostics := false
var frame_meter = FrameMeter.new()
var frame_coordinator
var state_presenter
var command_failure_presenter
var command_coordinator = preload("res://practice_command_coordinator.gd").new()
var command_success_presenter
var command_success_effects
var demo_player: Node
var ui_scale := 1.0
var practice_backdrop: ColorRect
# One acknowledged channel delivers every note-feedback event exactly once.
var feedback_session = PracticeFeedbackSession.new()
var inprocess_bus: Node
var score_runway
var score_admission
var native_started := false

var current_screen: String:
    get: return navigation_session.current_screen
var score_error: String:
    get: return score_session.score_error if score_session != null else ""
var startup_last_music_checked: bool:
    get: return library_catalog.startup_checked

func _ready() -> void:
    # Let the display pace rendering at its native refresh rate.
    # A fixed 60 Hz cap plus the old 33 ms low-power sleep caused uneven
    # scroll steps, especially on 90/120/144 Hz panels.
    DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED)
    Engine.max_fps = 0
    OS.low_processor_usage_mode_sleep_usec = 8000
    OS.low_processor_usage_mode = false
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
    _build_interface()
    navigation_session.configure(
        practice_backdrop,navigation_drawer,practice_view,
        library_view,settings_view,screens)
    navigation_session.suspend_requested.connect(
        func(): send_action({"action":"ui_suspend"}))
    navigation_session.library_requested.connect(library_catalog.request_catalog)
    navigation_session.settings_requested.connect(settings_interactions.request_settings)
    navigation_session.devices_requested.connect(midi_devices.discover)
    # The screens and navigation ports are now connected. Navigating
    # during _build_interface silently discarded startup presentation
    # because the navigation session did not exist yet.
    _navigate("practice")
    feedback_session.configure(inprocess_bus,practice_view.stage,visual_transport_clock)
    input_session.configure(practice_view,library_view)
    input_session.exit_requested.connect(_exit_app)
    input_session.fullscreen_requested.connect(settings_interactions.toggle_fullscreen)
    input_session.navigation_requested.connect(_navigate)
    input_session.advanced_pause_requested.connect(practice_view.open_advanced_pause)
    input_session.primary_requested.connect(command_coordinator.primary)
    input_session.pause_requested.connect(command_coordinator.pause)
    input_session.retry_requested.connect(command_coordinator.retry)
    input_session.listen_requested.connect(command_coordinator.listen)
    input_session.command_requested.connect(send_action)
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
    demo_player.prepared.connect(func(token: String, ready_revision: int):
        send_action({"action": "demo_ready", "token": token, "revision": ready_revision}))
    demo_player.failed.connect(func(message: String): practice_view.present_message(message))
    countin_audio.install(self)
    countin_audio.bind_preferences(settings_interactions,state_inbox,phase0_smoke_mode)
    resized.connect(_update_responsive_layout)
    if not get_window().size_changed.is_connected(_update_responsive_layout):
        get_window().size_changed.connect(_update_responsive_layout)
    _update_responsive_layout()
    score_queue.attach(self, score_session, inprocess_bus)
    score_runway = ScoreRunway.new()
    add_child(score_runway)
    score_runway.configure(self,practice_view.stage,score_session,inprocess_bus)
    score_runway.renderer_promoted.connect(func(renderer):
        renderer.fingering_change_requested.connect(
            command_coordinator.correct_fingering))

    var action_request = _new_request(command_coordinator.receive)
    action_request.timeout = 90.0
    midi_devices.attach_request(_new_request(midi_devices.on_devices))
    midi_devices.bind_context(navigation_session,state_inbox,settings_interactions)
    library_catalog.attach_requests(
        _new_request(library_catalog.on_catalog),
        _new_request(library_catalog.on_health))
    settings_interactions.bind_application(get_window(),demo_player,practice_view,
        midi_devices,state_inbox,library_catalog)
    settings_interactions.attach_requests(_new_request(settings_interactions.on_settings),
        _new_request(settings_interactions.on_learning_status))
    statistics_coordinator.configure(_new_request(statistics_coordinator.on_report), settings_view.statistics_view)
    poll_session.bind_state_request(_new_request(state_inbox.receive),state_inbox,
        command_coordinator,score_session,practice_view)
    poll_session.library_requested.connect(library_catalog.request_catalog)
    poll_session.devices_requested.connect(midi_devices.discover)
    poll_session.library_health_requested.connect(library_catalog.request_health)
    state_inbox.published.connect(poll_session.accept_state)
    add_child(poll_session)
    poll_session.configure(
        func() -> String: return current_screen,
        func() -> String: return str(state_inbox.current.get("device","")),
        func() -> bool: return library_catalog.health_running)
    frame_coordinator = PracticeFrameCoordinator.new(
        practice_view,settings_view,demo_player,frame_meter)
    state_presenter = PracticeStatePresenter.new(
        practice_view,settings_view,calibration_view)
    command_failure_presenter = CommandFailurePresenter.new(
        library_view,practice_view,settings_view,home_view)
    command_success_presenter = CommandSuccessPresenter.new(
        library_view,practice_view,settings_view)
    command_success_effects = CommandSuccessEffects.new(command_success_presenter)
    command_success_effects.publish_state.connect(state_inbox.receive)
    command_success_effects.navigate_practice.connect(_navigate)
    command_success_effects.request_settings.connect(settings_interactions.request_settings)
    command_success_effects.request_library.connect(library_catalog.request_catalog)
    command_success_effects.request_library_health.connect(library_catalog.request_health)
    metronome_frame = MetronomeFrameCoordinator.new(
        calibration_view,practice_view,visual_transport_clock,
        func(at_ms: int) -> float:
            return presentation_session.transport_beat(state_inbox.current,at_ms),
        countin_audio.practice_click,countin_audio.click)
    command_coordinator.configure(practice_view,settings_view,metronome_frame,
        action_request,command_failure_presenter,score_session)
    metronome_frame.score_flow = score_flow
    visual_transport_clock.score_flow = score_flow
    score_admission = ScoreAdmissionGateway.new()
    add_child(score_admission)
    score_admission.configure(self,inprocess_bus,practice_view.stage,
        score_session,score_runway,score_flow,visual_transport_clock,
        metronome_frame)
    score_admission.admission_problem.connect(func(message: String):
        practice_view.present_message(message)
        if frame_diagnostics:
            print("SCORE_ADMISSION:",message))
    presentation_session = PracticePresentationSession.new(
        visual_transport_clock,score_flow,guided_presentation,
        score_session,score_runway,score_admission,
        practice_view,score_effects,demo_player)
    command_coordinator.succeeded.connect(command_success_effects.apply)
    command_coordinator.learning_accepted.connect(settings_interactions.learning_command_accepted)
    command_coordinator.library_requested.connect(command_coordinator.open_library_piece,CONNECT_DEFERRED)
    command_coordinator.library_open_status.connect(library_view.present_open_status)
    command_coordinator.refresh_requested.connect(poll_session.poll)
    presentation_session.bind_frames(feedback_session,metronome_frame,frame_coordinator,
        frame_diagnostics,listen_sync_diagnostics,phase0_smoke_mode)
    state_inbox.configure(command_coordinator,practice_view,presentation_session,
        state_presenter,statistics_coordinator,debug_session_logger,
        navigation_session,input_session)
    command_success_effects.refresh_score.connect(presentation_session.refresh_status)
    practice_view.score_retry_requested.connect(presentation_session.retry_score)
    presentation_session.refresh_status()
    set_process(true)

func _new_request(callback: Callable):
    var req = preload("res://inprocess_request.gd").new()
    req.configure(inprocess_bus)
    req.timeout = 5.0
    add_child(req)
    req.request_completed.connect(callback)
    return req

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


func _ui_font(base: int) -> int:
    return maxi(14, int(round(float(base) * ui_scale)))

func _resize_ui_fonts(node: Node) -> void:
    if node == library_view or node == settings_view or node == home_view or node == practice_view:
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


func _navigate(screen: String) -> void:
    navigation_session.navigate(screen,state_inbox.current)


func _resize_overlay_drawer() -> void:
    navigation_drawer.resize(size)
    if library_view != null:
        library_view.apply_viewport(size, ui_scale)
    if settings_view != null:
        settings_view.apply_viewport(size, ui_scale)
    if calibration_view != null:
        calibration_view.apply_viewport(size, ui_scale)


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
    var backdrop_material := ShaderMaterial.new()
    backdrop_material.shader = preload("res://practice_backdrop.gdshader")
    practice_backdrop.material = backdrop_material
    add_child(practice_backdrop)

    _build_home_screen()
    _build_library_screen()
    _build_settings_screen()
    _build_practice_screen()
    library_catalog.configure(library_view,home_view,command_coordinator.request_command)
    library_catalog.open_requested.connect(command_coordinator.open_library_piece,CONNECT_DEFERRED)
    midi_devices.configure(settings_view,command_coordinator.request_command)
    score_session = ScoreAssetSession.new(
        practice_view.stage.renderer, practice_view.stage.feedback)
    score_session.action_requested.connect(send_action)


func _build_home_screen() -> void:
    var page := _screen("Home")
    screens["home"] = page
    home_view = HomeScreen.new()
    page.add_child(home_view)
    home_view.library_requested.connect(func(): _navigate("library"))
    home_view.settings_requested.connect(func(): _navigate("settings"))
    home_view.exit_requested.connect(_exit_app)
    home_view.open_requested.connect(open_library_piece)


func _build_library_screen() -> void:
    var page := _screen("Library")
    screens["library"] = page
    library_view = LibraryScreen.new()
    page.add_child(library_view)
    library_view.open_requested.connect(open_library_piece)
    library_view.refresh_requested.connect(library_catalog.request_catalog)
    library_view.health_check_requested.connect(func():
        library_catalog.start_health(command_coordinator.state.pending))


func _build_practice_screen() -> void:
    var page := _screen("Practice")
    screens["practice"] = page
    practice_view = PracticeScreen.new()
    page.add_child(practice_view)
    practice_view.navigation_requested.connect(_navigate)
    practice_view.command_requested.connect(send_action)
    practice_view.play_requested.connect(command_coordinator.primary)
    practice_view.retry_requested.connect(command_coordinator.retry)
    practice_view.listen_requested.connect(command_coordinator.listen)
    practice_view.metronome_toggled.connect(settings_interactions.set_metronome)
    practice_view.stage.renderer.fingering_change_requested.connect(command_coordinator.correct_fingering)
    navigation_drawer.mount(self, screens, _button, _navigate, _exit_app)
    _resize_overlay_drawer()

func _update_responsive_layout() -> void:
    _configure_ui_scaling()
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
    statistics_coordinator = preload("res://learning_statistics_coordinator.gd").new()
    add_child(statistics_coordinator)
    var page := _screen("Settings")
    screens["settings"] = page
    settings_view = SettingsScreen.new()
    settings_view.ui_scale = ui_scale
    settings_view.default_font = theme.default_font
    page.add_child(settings_view)
    settings_interactions.configure(settings_view,statistics_coordinator)
    settings_interactions.devices_requested.connect(midi_devices.show_picker)
    settings_interactions.refresh_devices_requested.connect(midi_devices.discover)
    settings_interactions.command_requested.connect(command_coordinator.request_command)
    settings_interactions.action_requested.connect(send_action)
    settings_view.device_selected.connect(midi_devices.choose)
    settings_view.sight_reading_requested.connect(func(level: int, tempo: String):
        command_coordinator.request_command("sight_reading.start",{"level":level,"tempo":tempo}))
    settings_interactions.exit_requested.connect(_exit_app)
    # Timing calibration is its own page, opened from Settings.
    var calibration_page := _screen("Calibration")
    screens["calibration"] = calibration_page
    calibration_view = CalibrationScreen.new()
    calibration_page.add_child(calibration_view)
    settings_view.calibration_page_requested.connect(func(): _navigate("calibration"))
    calibration_view.navigation_requested.connect(_navigate)
    calibration_view.calibration_requested.connect(func(action: String):
        send_action({"action":action}))

func _input(event: InputEvent) -> void:
    if input_session.capture(event,current_screen,get_viewport()):
        get_viewport().set_input_as_handled()


func _unhandled_key_input(event: InputEvent) -> void:
    if input_session.dispatch(event,current_screen,get_viewport()):
        get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
    if not native_started and inprocess_bus != null:
        var native_error: String = str(inprocess_bus.get("ready_error"))
        if not native_error.is_empty():
            printerr("Embedded Piano Teacher stopped: " + native_error)
            get_tree().quit(1)
            return
        if inprocess_bus.is_ready():
            native_started = true
            if OS.get_environment("PIANO_TEACHER_HEADLESS_SMOKE") == "1":
                print("PIANO_PACKAGE_NATIVE_READY")
            poll_session.poll()
            midi_devices.discover()
            settings_interactions.request_settings()
            library_catalog.request_catalog()
    # Keep continuous frame pacing for all practice states (including
    # count-in, rests, paused feedback fades and Free holds). Other screens
    # may save power without sleeping the moving score.
    var idle_mode: bool = current_screen != "practice"
    if OS.low_processor_usage_mode != idle_mode:
        OS.low_processor_usage_mode = idle_mode
    var frame_ms: float = float(Time.get_ticks_usec()) * .001
    presentation_session.advance(state_inbox.current,state_inbox.tick_ms,
        int(frame_ms),delta,command_coordinator.state.pending,current_screen,frame_ms)

func current_state() -> Dictionary:
    return state_inbox.current.duplicate(true)

func send_action(command: Dictionary) -> void:
    command_coordinator.request_action(command,state_inbox.current)

func open_library_piece(identifier: String, resume_saved := false) -> void:
    command_coordinator.open_library_piece(identifier,resume_saved)

func transport_beat_now() -> float:
    return presentation_session.transport_beat(state_inbox.current,Time.get_ticks_msec())
