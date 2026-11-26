extends VBoxContainer
# Practice interaction and snapshot presentation. Chrome owns widget/layout
# construction; this owner keeps backend snapshots and command/input policy.
const Chrome := preload("res://practice_chrome.gd")
const Design := preload("res://practice_theme.gd")
const ScoreStage := preload("res://practice_score_stage.gd")
var _chrome := Chrome.new()
signal navigation_requested(destination: String)
signal command_requested(command: Dictionary)
signal midi_start_suppression_requested(input_count: int)
signal play_requested
signal retry_requested
signal listen_requested
signal metronome_toggled(enabled: bool)
signal score_retry_requested
var stage: ScoreStage:
    get: return _chrome.stage
var practice_layout_box: VBoxContainer:
    get: return _chrome.practice_layout_box
var practice_header: HBoxContainer:
    get: return _chrome.practice_header
var practice_navigation: HBoxContainer:
    get: return _chrome.practice_navigation
var title_label: Label:
    get: return _chrome.title_label
var practice_controls: HFlowContainer:
    get: return _chrome.practice_controls
var practice_retry_button: Button:
    get: return _chrome.practice_retry_button
var start_button: Button:
    get: return _chrome.start_button
var listen_button: Button:
    get: return _chrome.listen_button
var flow_status_label: Label:
    get: return _chrome.flow_status_label
var metronome_switch: CheckButton:
    get: return _chrome.metronome_switch
var practice_music_button: Button:
    get: return _chrome.practice_music_button
var practice_settings_button: Button:
    get: return _chrome.practice_settings_button
var open_picker: Control:
    get: return _chrome.open_picker
var pause_sheet: Control:
    get: return _chrome.pause_sheet
var resume_banner: PanelContainer:
    get: return _chrome.resume_banner
var resume_banner_message: Label:
    get: return _chrome.resume_banner_message
var resume_review_button: Button:
    get: return _chrome.resume_review_button
var resume_continue_button: Button:
    get: return _chrome.resume_continue_button
var resume_measure_button: Button:
    get: return _chrome.resume_measure_button
var ui_scale: float:
    get: return _chrome.ui_scale
var _resume_open_state: Dictionary = {}
var advanced_pause_open := false
var _state: Dictionary = {}
var _score_ready := false
var _score_status: Dictionary = {"ready":false,"visible":true,
    "text":"Choose a piece to begin","error":"","retry_visible":false,
    "browse_visible":true}
var _busy := false
var _flash_id := -1
var _transition_id := -1
var _audio_error := false
var _active := true

func _ready() -> void:
    name = "PracticeScreen"
    size_flags_horizontal = Control.SIZE_EXPAND_FILL
    size_flags_vertical = Control.SIZE_EXPAND_FILL
    add_child(_chrome)
    _chrome.build()
    _chrome.navigation_requested.connect(func(destination: String): navigation_requested.emit(destination))
    _chrome.command_requested.connect(func(command: Dictionary): command_requested.emit(command))
    _chrome.play_requested.connect(func(): play_requested.emit())
    _chrome.retry_requested.connect(func(): retry_requested.emit())
    _chrome.listen_requested.connect(func(): listen_requested.emit())
    _chrome.metronome_toggled.connect(func(enabled: bool): metronome_toggled.emit(enabled))
    _chrome.score_retry_requested.connect(func(): score_retry_requested.emit())
    _chrome.dismiss_resume_requested.connect(_dismiss_resume_hint)
    _chrome.review_previous_requested.connect(_review_previous_steps)
    _chrome.resume_measure_requested.connect(_resume_choose_measure)
    _chrome.confirm_source_requested.connect(confirm_source_picker)
    _chrome.cancel_source_requested.connect(cancel_source_picker)

func apply_viewport(view_size: Vector2, scale: float) -> void:
    _chrome.apply_viewport(view_size, scale)

func bind_countin_voice_player(service: Node) -> void:
    _chrome.bind_countin_voice_player(service)

func present_metronome(enabled: bool) -> void:
    if metronome_switch != null and metronome_switch.button_pressed != enabled:
        metronome_switch.set_pressed_no_signal(enabled)

func present(parsed: Dictionary, ready: bool, busy := false, audio_error := false) -> void:
    # Display only: Python projects the status line, the problem notice,
    # the keyboard and every control (screen_projection, control_projection).
    _state = parsed.duplicate(true)
    if is_resume_prompt_open() and (bool(parsed.get("running",false)) or
            str(parsed.get("mode","")) == "listen" or
            int(parsed.get("lesson_step",-1)) != int(
                _resume_open_state.get("lesson_step",-1))):
        _dismiss_resume_hint()
    _score_ready = ready
    _audio_error = audio_error
    present_busy(busy)
    stage.present(parsed,busy)
    if not bool(parsed.get("paused",false)): advanced_pause_open = false
    _present_pause()
    var screen: Dictionary = parsed.get("screen",{}) if parsed.get("screen") is Dictionary else {}
    var status := str(screen.get("status",""))
    var transition: Dictionary = screen.get("transition",{}) if screen.get("transition") is Dictionary else {}
    if int(transition.get("id",0)) != _transition_id:
        _transition_id = int(transition.get("id",0))
        _transition_message = str(transition.get("text",""))
        _transition_until_ms = Time.get_ticks_msec() + TRANSITION_MS
    var flash: Dictionary = screen.get("flash",{}) if screen.get("flash") is Dictionary else {}
    if int(flash.get("id",0)) != _flash_id:
        _flash_id = int(flash.get("id",0))
        _flash_message = str(flash.get("text",""))
        _flash_until_ms = Time.get_ticks_msec() + TRANSITION_MS
    flow_status_label.visible = not status.is_empty()
    if flow_status_label.text != status:
        flow_status_label.text = status
    if not bool(parsed.get("loaded",false)):
        # A source picker / load failure must not blank the visual timeline.
        stage.renderer.visible = true
        _present_notice("")
        present_score(_score_status)
        return
    title_label.text = str(parsed.get("title", "Piano Teacher")).replace("_", " ")
    _present_notice("Listen audio could not load. Choose Listen to try again."
        if _audio_error else str(screen.get("notice","")))
    var primary_control: Dictionary = _control("primary")
    var listen_control: Dictionary = _control("listen")
    start_button.visible = true
    start_button.text = str(primary_control.get("label","Play"))
    var piano_key := str(primary_control.get("piano_key",""))
    start_button.tooltip_text = "Next section · F on your piano" if piano_key == "F" else "Resume · Space or play C on your piano" if piano_key == "C" else "Next section" if str(primary_control.get("action","")) == "section_next" else "Pause or resume · Space"
    start_button.call("set_piano_key_hint",piano_key)
    start_button.disabled = _primary_blocked()
    start_button.call("configure", "pause" if str(primary_control.get("action","")) == "pause" else "play",
        _active_transport(parsed) and not bool(parsed.get("paused", false)))
    var retry_control: Dictionary = _control("retry")
    practice_retry_button.visible = str(retry_control.get("action","")) == "section_repeat"
    practice_retry_button.tooltip_text = "Repeat at 100% · C on your piano" if not str(retry_control.get("piano_key","")).is_empty() else "Repeat at 100%"
    practice_retry_button.call("set_piano_key_hint",str(retry_control.get("piano_key","")))
    practice_retry_button.disabled = _retry_blocked()
    listen_button.text = str(listen_control.get("label","Listen again"))
    listen_button.tooltip_text = "Hear this passage again at the target tempo · L"
    listen_button.disabled = not bool(listen_control.get("enabled",false))
    listen_button.call("configure", "listen", str(parsed.get("mode", "")) == "listen")

const MESSAGE_MS := 4000
const TRANSITION_MS := 2400
var _notice := ""
var _message := ""
var _message_until_ms := 0
var _transition_message := ""
var _transition_until_ms := 0
var _flash_message := ""
var _flash_until_ms := 0

func _present_notice(text: String) -> void:
    # The one problem line, shown on the score's banner.
    _notice = text
    _show_banner()

func _show_banner() -> void:
    var now := Time.get_ticks_msec()
    var text := _notice
    if not _transition_message.is_empty() and now < _transition_until_ms:
        text = _transition_message
    if not _flash_message.is_empty() and now < _flash_until_ms:
        text = _flash_message
    if not _message.is_empty() and now < _message_until_ms:
        text = _message
    stage.present_notice(text)

func present_busy(busy: bool) -> void:
    _busy = busy

func present_score(status: Dictionary) -> void:
    _score_status = status.duplicate(true)
    _score_ready = bool(status.get("ready",false))
    stage.present_score_status(status)
    start_button.disabled = _primary_blocked()
    practice_retry_button.disabled = _retry_blocked()

func present_message(message: String, _reveal := false) -> void:
    # A command result or refusal ("Connect your MIDI piano…") holds the
    # banner briefly, then the projected notice returns.
    _message = message
    _message_until_ms = Time.get_ticks_msec() + MESSAGE_MS
    _show_banner()

func begin_action(requested: String, pending := "") -> void:
    if not pending.is_empty():
        present_message("One moment — finishing the previous action.",true)
        return
    var verb: String = {"listen":"Preparing piano audio","practice":"Returning to practice",
        "start":"Starting count-in","pause":"Pausing","resume":"Resuming","restart":"Restarting the passage",
"select_step":"Opening lesson","stop":"Stopping"}.get(requested,"One moment")
    present_message(verb + "…")

func finish_action() -> void:
    _message_until_ms = 0
    _show_banner()

func _control(name: String) -> Dictionary:
    var controls: Dictionary = _state.get("controls",{})
    var choice: Variant = controls.get(name,{})
    return choice if choice is Dictionary else {}

func _primary_blocked() -> bool:
    var primary: Dictionary = _control("primary")
    return (not bool(primary.get("enabled",false)) or
        (bool(primary.get("requires_score",false)) and not _score_ready))

func _retry_blocked() -> bool:
    var retry: Dictionary = _control("retry")
    return not bool(retry.get("enabled",false)) or (
        bool(retry.get("requires_score",false)) and not _score_ready)

func _active_transport(state: Dictionary) -> bool:
    var controls: Dictionary = state.get("controls",{})
    return bool(controls.get("transport_active",false))

func set_active(active: bool) -> void:
    _active = active
    _present_pause()

func _present_pause() -> void:
    pause_sheet.present(_state if _active and advanced_pause_open else {})

func open_advanced_pause() -> void:
    navigation_requested.emit("practice")
    advanced_pause_open = true
    if bool(_state.get("paused",false)):
        _present_pause()
    elif bool(_control("pause").get("enabled",false)):
        # An advanced Pause is the same raw gesture as the on-screen and
        # physical shortcut. Python resolves it from the latest locked
        # session state; the modal never bypasses transport policy.
        command_requested.emit({"action":"ui_pause"})
    else:
        advanced_pause_open = false

func is_source_picker_open() -> bool:
    return open_picker != null and open_picker.visible

func is_resume_prompt_open() -> bool:
    return resume_banner != null and resume_banner.visible

func _dismiss_resume_hint() -> void:
    if resume_banner != null:
        resume_banner.hide()
    _resume_open_state.clear()

func show_resume_prompt(state: Dictionary, allow_measure: bool) -> void:
    var step: int = int(state.get("lesson_step",1))
    if step <= 1:
        if allow_measure:
            show_source_picker(state)
        return
    navigation_requested.emit("practice")
    midi_start_suppression_requested.emit(int(state.get("midi_input_count",0)))
    _resume_open_state = state.duplicate(true)
    resume_measure_button.visible = allow_measure
    resume_banner_message.text = "Continue at step %d?" % step
    resume_banner_message.tooltip_text = "Your earlier progress is preserved. Play to continue the saved step."
    _chrome.position_resume_banner()
    resume_banner.show()

func _review_previous_steps() -> void:
    if _resume_open_state.is_empty():
        return
    var context := _resume_open_state.duplicate(true)
    _dismiss_resume_hint()
    command_requested.emit({"action":"ui_review_previous",
        "context_fingerprint":str(context.get("piece_fingerprint","")),
        "context_revision":int(context.get("revision",-1))})

func _resume_choose_measure() -> void:
    if _resume_open_state.is_empty():
        return
    var state := _resume_open_state.duplicate(true)
    _dismiss_resume_hint()
    show_source_picker(state)

func show_source_picker(state: Dictionary) -> void:
    navigation_requested.emit("practice")
    midi_start_suppression_requested.emit(int(state.get("midi_input_count",0)))
    _dismiss_resume_hint()
    open_picker.show_piece(state)

func cancel_source_picker() -> void:
    open_picker.visible = false
    navigation_requested.emit("library")

func confirm_source_picker() -> void:
    if _busy or not is_source_picker_open(): return
    var bar: int = open_picker.selected_bar()
    var mode: String = open_picker.selected_mode()
    open_picker.visible = false
    navigation_requested.emit("practice")
    command_requested.emit({"action":"open_at","bar":bar,"mode":mode})

func handle_source_input(event: InputEvent) -> bool:
    if not is_source_picker_open(): return false
    if event is InputEventKey and event.pressed and not event.echo:
        if event.keycode == KEY_ESCAPE:
            cancel_source_picker()
            get_viewport().set_input_as_handled()
        elif event.keycode in [KEY_ENTER,KEY_KP_ENTER] and not open_picker.is_mode_popup_open():
            confirm_source_picker()
            get_viewport().set_input_as_handled()
    return true

func retains_modal_navigation(code: Key) -> bool:
    return pause_sheet.visible and code in [KEY_LEFT,KEY_RIGHT,KEY_UP,KEY_DOWN,KEY_TAB]
