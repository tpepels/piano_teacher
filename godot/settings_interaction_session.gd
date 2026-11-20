extends RefCounted
## Sole interpretation of SettingsScreen interaction into domain commands.
## Does not own or start transport; emits one semantic application command.
signal devices_requested
signal refresh_devices_requested
signal command_requested(operation: String, payload: Dictionary)
signal action_requested(payload: Dictionary)
signal volume_changed(db: float)
signal fullscreen_requested(enabled: bool)
signal exit_requested

var preferences: Dictionary = {}

func configure(view, statistics) -> void:
    view.choose_devices_requested.connect(func(): devices_requested.emit())
    view.refresh_devices_requested.connect(func(): refresh_devices_requested.emit())
    view.save_folder_requested.connect(func(path: String):
        command_requested.emit("settings.update",{"music_dir":path}))
    view.tempo_requested.connect(func(bpm: int):
        action_requested.emit({"action":"tempo","bpm":bpm}))
    view.strategy_requested.connect(func(strategy: String):
        command_requested.emit("settings.update",{"exercise_strategy":strategy}))
    view.diagnosis_strategy_requested.connect(func(strategy: String):
        command_requested.emit("settings.update",{"diagnosis_strategy":strategy}))
    view.learner_strategy_requested.connect(func(strategy: String):
        command_requested.emit("settings.update",{"learner_strategy":strategy}))
    view.mistake_response_requested.connect(func(strategy: String):
        command_requested.emit("settings.update",{"mistake_response_strategy":strategy}))
    view.metronome_requested.connect(func(enabled: bool):
        command_requested.emit("settings.update",{"metronome":enabled}))
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
    view.volume_changed.connect(func(db: float): volume_changed.emit(db))
    view.fullscreen_requested.connect(func(enabled: bool):
        fullscreen_requested.emit(enabled))
    view.exit_requested.connect(func(): exit_requested.emit())

func accept_preferences(values: Dictionary, settings_view,
        practice_view, connected_device: String, device_names: Array) -> String:
    ## Settings values and the saved-device reconnection decision have one
    ## owner; the scene applies only its returned explicit device selection.
    preferences = values.duplicate(true)
    settings_view.present_preferences(preferences)
    practice_view.present_metronome(bool(preferences.get("metronome",true)))
    var selected := str(preferences.get("midi_device",""))
    if not selected.is_empty() and connected_device.is_empty() and \
            device_names.has(selected) and \
            not selected.to_lower().contains("midi through"):
        return selected
    return ""
