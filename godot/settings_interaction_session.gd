extends RefCounted
## Sole interpretation of SettingsScreen interaction into domain commands.
## Does not own or start transport; emits one semantic application command.
signal devices_requested
signal refresh_devices_requested
signal command_requested(operation: String, payload: Dictionary)
signal action_requested(payload: Dictionary)
signal exit_requested
const Reply := preload("res://inprocess_request.gd")

var preferences: Dictionary = {}
var _view
var _statistics
var _practice
var _devices
var _inbox
var _lesson
var _library
var _window: Window
var _demo
var _settings_request
var _history_request
var _settings_pending := false
var _history_pending := false

func configure(view, statistics) -> void:
    _view = view
    _statistics = statistics
    view.choose_devices_requested.connect(func(): devices_requested.emit())
    view.refresh_devices_requested.connect(func(): refresh_devices_requested.emit())
    view.save_folder_requested.connect(func(path: String):
        command_requested.emit("settings.update",{"music_dir":path}))
    view.tempo_requested.connect(func(bpm: int):
        action_requested.emit({"action":"tempo","bpm":bpm}))
    view.metronome_requested.connect(func(enabled: bool):
        command_requested.emit("settings.update",{"metronome":enabled}))
    view.hold_grading_requested.connect(func(enabled: bool):
        command_requested.emit("settings.update",{"grade_note_holds":enabled}))
    view.retention_save_requested.connect(func(days: int, budget_mib: int):
        command_requested.emit("settings.update",{
            "evidence_retention_days":days,"evidence_budget_mib":budget_mib}))
    view.history_export_requested.connect(func(path: String, include_detail: bool):
        command_requested.emit("learning.export",{
            "path":path,"include_detail":include_detail}))
    view.piece_history_delete_requested.connect(func(fingerprint: String):
        statistics.invalidate()
        command_requested.emit("learning.delete_piece",{
            "fingerprint":fingerprint,"confirm":true}))
    view.learner_history_delete_requested.connect(func():
        statistics.invalidate()
        command_requested.emit("learning.delete_learner",{"confirm":true}))
    view.calibration_requested.connect(func(action: String):
        action_requested.emit({"action":action}))
    view.midi_range_requested.connect(func(action: String):
        action_requested.emit({"action":action}))
    view.volume_changed.connect(set_listen_volume)
    view.fullscreen_requested.connect(set_fullscreen)
    view.exit_requested.connect(func(): exit_requested.emit())

func bind_application(window: Window, demo, practice, devices, inbox,
        lesson, library) -> void:
    _window = window
    _demo = demo
    _practice = practice
    _devices = devices
    _inbox = inbox
    _lesson = lesson
    _library = library
    _view.present_volume(float(_demo.get("listen_volume_db")))

func attach_requests(settings, history) -> void:
    _settings_request = settings
    _history_request = history

func request_settings() -> void:
    if _settings_pending or _settings_request == null:
        return
    _settings_pending = true
    if _settings_request.request("settings.snapshot") != OK:
        _settings_pending = false

func on_settings(code: int, body: PackedByteArray) -> void:
    _settings_pending = false
    if code != 0:
        _view.present_message(Reply.failure_message(code,body))
        return
    var parsed: Variant = Reply.decode_reply(body)
    if not parsed is Dictionary:
        return
    accept_preferences(parsed)
    request_learning_status()
    _apply_window_mode(bool(preferences.get("fullscreen",true)))
    _devices.maybe_restore(str(preferences.get("midi_device","")),
        str(_inbox.current.get("device","")))

func request_learning_status() -> void:
    if _history_pending or _history_request == null:
        return
    _history_pending = true
    if _history_request.request("learning.status") != OK:
        _history_pending = false
        _view.present_message("Cannot read local learning history")

func on_learning_status(code: int, body: PackedByteArray) -> void:
    _history_pending = false
    if code != 0:
        _view.present_message(Reply.failure_message(code,body))
        return
    var parsed: Variant = Reply.decode_reply(body)
    if parsed is Dictionary:
        _view.present_learning_status(parsed)
        _statistics.update_context(str(parsed.get("current_fingerprint","")),
            str(parsed.get("learner_id","")))

func learning_command_accepted(operation: String, values: Dictionary) -> void:
    if operation == "learning.export":
        _view.present_message("Learning history exported to " +
            str(values.get("path","chosen file")))
    else:
        _statistics.invalidate()
        _view.present_message("Current piece history and learning progress deleted."
            if operation == "learning.delete_piece" else
            "All learner history and learning progress deleted.")
        _lesson.invalidate()
        request_settings()
        _library.request_catalog()
    request_learning_status()

func set_metronome(enabled: bool) -> void:
    preferences["metronome"] = enabled
    command_requested.emit("settings.update",{"metronome":enabled})

func set_listen_volume(db: float) -> void:
    if _demo != null:
        _demo.set_listen_volume_db(db)

func _apply_window_mode(fullscreen: bool) -> void:
    var expected := Window.MODE_FULLSCREEN if fullscreen else Window.MODE_WINDOWED
    if _window.mode != expected:
        _window.mode = expected

func set_fullscreen(enabled: bool) -> void:
    _apply_window_mode(enabled)
    command_requested.emit("settings.update",{"fullscreen":enabled})

func toggle_fullscreen() -> void:
    var enabled: bool = _window.mode != Window.MODE_FULLSCREEN
    _view.present_window_mode(enabled)
    set_fullscreen(enabled)

func accept_preferences(values: Dictionary) -> void:
    preferences = values.duplicate(true)
    _view.present_preferences(preferences)
    _practice.present_metronome(bool(preferences.get("metronome",true)))
