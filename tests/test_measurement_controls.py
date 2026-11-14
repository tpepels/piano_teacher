"""Validated local evidence preferences and the Settings command boundary."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from piano_teacher.inprocess import EngineCommands, INVALID, OK
from piano_teacher.library import ScoreLibrary


@pytest.mark.parametrize("key,default,lower,upper", [
    ("evidence_retention_days", 365, 7, 3650),
    ("evidence_budget_mib", 256, 16, 4096),
])
def test_retention_preferences_default_validate_and_persist(tmp_path, key, default, lower, upper):
    library = ScoreLibrary(tmp_path)
    assert library.public_settings().get(key) == default
    for value in (lower, upper):
        proposed = library.propose_update(**{key: value})
        assert proposed[key] == value
        assert library.settings[key] == default
    library.update(**{key: upper})
    assert ScoreLibrary(tmp_path).public_settings()[key] == upper
    for invalid in (lower - 1, upper + 1, True, False, None, str(lower), float(lower)):
        with pytest.raises(ValueError):
            library.propose_update(**{key: invalid})
    assert library.settings[key] == upper


@pytest.mark.parametrize("key,default,invalid", [
    ("evidence_retention_days", 365, 0),
    ("evidence_retention_days", 365, 3651),
    ("evidence_retention_days", 365, True),
    ("evidence_retention_days", 365, 8.0),
    ("evidence_budget_mib", 256, 15),
    ("evidence_budget_mib", 256, 4097),
    ("evidence_budget_mib", 256, False),
    ("evidence_budget_mib", 256, "32"),
])
def test_malformed_stored_retention_falls_back_without_blocking_startup(tmp_path, key, default, invalid):
    (tmp_path / "settings.json").write_text(json.dumps({key: invalid}))
    assert ScoreLibrary(tmp_path).public_settings().get(key) == default


class LocalHistoryEngine:
    """Narrow boundary double while ledger ownership lives in PracticeEngine."""
    def __init__(self):
        self.operations = []
        self.closed = False

    def learning_history_status(self):
        return {"summary": "2 attempts", "default_path": "/tmp/history.json",
                "current_fingerprint": "piece-sha", "learner_id": "learner-1",
                "attempt_count": 2, "detail_attempt_count": 1,
                "pruned_attempt_count": 1, "evidence_retention_days": 365,
                "evidence_budget_mib": 256}

    def export_learning_history(self, path, include_detail=False):
        self.operations.append(("export", path, include_detail))
        return {"path": path, "attempt_count": 2}

    def delete_piece_history(self, fingerprint, confirm=False):
        self.operations.append(("piece", fingerprint, confirm))
        return {"summary": "Piece history deleted", "attempt_count": 0}

    def delete_learner_history(self, confirm=False):
        self.operations.append(("learner", confirm))
        return {"summary": "Learner history deleted", "attempt_count": 0}

    def close(self):
        self.closed = True


def request(bridge, operation, payload=None):
    status, body = bridge.request(operation, json.dumps(payload) if payload is not None else "")
    return status, json.loads(body)


def test_learning_commands_preserve_selected_path_detail_and_confirmation():
    engine = LocalHistoryEngine()
    bridge = EngineCommands(engine=engine)
    assert request(bridge, "learning.status") == (OK, engine.learning_history_status())
    assert request(bridge, "learning.export", {"path": "/tmp/chosen.json"}) == (
        OK, {"path": "/tmp/chosen.json", "attempt_count": 2})
    assert request(bridge, "learning.export", {
        "path": "/tmp/detailed.json", "include_detail": True})[0] == OK
    assert request(bridge, "learning.delete_piece", {
        "fingerprint": "piece-sha", "confirm": True}) == (
        OK, {"summary": "Piece history deleted", "attempt_count": 0})
    assert request(bridge, "learning.delete_learner", {"confirm": True})[0] == OK
    assert engine.operations == [
        ("export", "/tmp/chosen.json", False),
        ("export", "/tmp/detailed.json", True),
        ("piece", "piece-sha", True), ("learner", True)]


@pytest.mark.parametrize("operation,payload", [
    ("learning.status", {"limit": 5}),
    ("learning.export", {}),
    ("learning.export", {"path": ""}),
    ("learning.export", {"path": 4}),
    ("learning.export", {"path": "/tmp/export.json", "include_detail": 1}),
    ("learning.export", {"path": "/tmp/export.json", "upload": True}),
    ("learning.delete_piece", {"fingerprint": "piece-sha"}),
    ("learning.delete_piece", {"fingerprint": "piece-sha", "confirm": False}),
    ("learning.delete_piece", {"fingerprint": "piece-sha", "confirm": 1}),
    ("learning.delete_piece", {"fingerprint": "", "confirm": True}),
    ("learning.delete_piece", {"fingerprint": 4, "confirm": True}),
    ("learning.delete_piece", {"fingerprint": "piece-sha", "confirm": True, "all": True}),
    ("learning.delete_learner", {}),
    ("learning.delete_learner", {"confirm": "yes"}),
    ("learning.delete_learner", {"confirm": True, "fingerprint": "piece-sha"}),
])
def test_learning_commands_reject_malformed_intent_before_engine_mutation(operation, payload):
    engine = LocalHistoryEngine()
    assert request(EngineCommands(engine=engine), operation, payload)[0] == INVALID
    assert engine.operations == []


def test_command_owner_closes_engine_session_but_borrower_does_not(monkeypatch):
    engine = LocalHistoryEngine()
    EngineCommands(engine=engine).close()
    assert not engine.closed
    monkeypatch.setattr("piano_teacher.inprocess.PracticeEngine", lambda: engine)
    EngineCommands().close()
    assert engine.closed


GODOT_CONTROLS = r'''
extends SceneTree

class RecordingRequest extends RefCounted:
    var timeout := 5.0
    var calls: Array[Dictionary] = []
    func request(operation: String, payload: Dictionary = {}) -> int:
        calls.append({"operation":operation,"payload":payload.duplicate(true)})
        return OK

class App extends "res://main.gd":
    var refreshes := 0
    var polls := 0
    func _ready() -> void:
        _build_interface()
        action_request = RecordingRequest.new()
        learning_status_request = RecordingRequest.new()
        command_failure_presenter = CommandFailurePresenter.new(
            library_view,practice_view,settings_view,home_view)
        command_success_presenter = CommandSuccessPresenter.new(
            library_view,practice_view,settings_view,lesson_session)
        command_success_effects = CommandSuccessEffects.new(command_success_presenter)
        command_success_effects.publish_state.connect(_on_state)
        command_success_effects.navigate_practice.connect(_navigate)
        command_success_effects.request_settings.connect(_request_settings)
        command_success_effects.request_library.connect(_request_library)
        command_success_effects.request_library_health.connect(_request_library_health)
        command_success_effects.refresh_score.connect(_refresh_score_status)
        # Match Main's extracted command lifecycle. The test's request spy
        # replaces only the transport adapter, not the command coordinator.
        command_coordinator.configure(practice_view,settings_view,null,score_flow,
            visual_transport_clock,action_request,command_failure_presenter)
        command_coordinator.succeeded.connect(command_success_effects.apply)
        command_coordinator.learning_accepted.connect(_learning_command_accepted)
        command_coordinator.refresh_requested.connect(_poll)
        set_process(false)
    func _poll() -> void: polls += 1
    func _request_settings() -> void: refreshes += 1
    func _request_library() -> void: pass
    func _request_library_health() -> void: pass
    func _request_devices() -> void: pass

var failures: Array[String] = []
func check(condition: bool, message: String) -> void:
    if not condition:
        failures.append(message)
        print("MEASUREMENT_CONTROL_FAIL:",message)

func _initialize() -> void: call_deferred("run")

func run() -> void:
    var app := App.new()
    root.add_child(app)
    await process_frame
    var view: Control = app.settings_view
    var required := ["retention_save_requested", "history_export_requested",
        "piece_history_delete_requested", "learner_history_delete_requested"]
    for name in required:
        check(view.has_signal(name), "Settings exposes working " + name)
    if failures.is_empty():
        var days: SpinBox = view.get("evidence_days_setting")
        var budget: SpinBox = view.get("evidence_budget_setting")
        var detail: CheckButton = view.get("export_detail_toggle")
        var file_dialog: FileDialog = view.get("export_dialog")
        var piece_dialog: ConfirmationDialog = view.get("delete_piece_dialog")
        var learner_dialog: ConfirmationDialog = view.get("delete_learner_dialog")
        check(days.min_value == 7 and days.max_value == 3650 and days.step == 1,
            "Detail days remain in the approved integer range")
        check(budget.min_value == 16 and budget.max_value == 4096 and budget.step == 1,
            "Detail budget remains in the approved integer range")
        check(not detail.button_pressed, "Detailed observations require explicit selection")
        check(file_dialog.file_mode == FileDialog.FILE_MODE_SAVE_FILE and
            file_dialog.access == FileDialog.ACCESS_FILESYSTEM,
            "Export uses a local save-file chooser")
        view.call("present_preferences", {"evidence_retention_days":30,"evidence_budget_mib":32})
        check(days.value == 30 and budget.value == 32, "Saved retention values populate Settings")
        app._request_learning_status()
        check(app.learning_status_request.calls == [{"operation":"learning.status","payload":{}}],
            "Settings requests its history summary through the typed read operation")
        app._on_learning_status(0,JSON.stringify({"summary":"2 attempts",
            "detail_attempt_count":1,"pruned_attempt_count":1,
            "default_path":"/tmp/history.json","current_fingerprint":"piece-sha"}).to_utf8_buffer())
        check(not app.learning_status_pending and view.get("history_summary_label").text.contains("1 pruned"),
            "History status exposes retained coverage and pruned detail")
        days.value = 60
        budget.value = 64
        var save: Button = view.get("retention_save_button")
        save.pressed.emit()
        check(app.action_request.calls.back() == {"operation":"settings.update",
            "payload":{"evidence_retention_days":60,"evidence_budget_mib":64}},
            "Save sends both validated retention preferences through the command owner")
        app._on_action(0,JSON.stringify({}).to_utf8_buffer())
        file_dialog.file_selected.emit("/tmp/chosen.json")
        check(app.action_request.calls.back() == {"operation":"learning.export",
            "payload":{"path":"/tmp/chosen.json","include_detail":false}},
            "Default export sends the chosen local path without observations")
        app._on_action(0,JSON.stringify({"path":"/tmp/chosen.json"}).to_utf8_buffer())
        check(view.get("settings_message").text.contains("/tmp/chosen.json"),
            "Export acknowledgement identifies the saved local file")
        detail.button_pressed = true
        file_dialog.file_selected.emit("/tmp/detail.json")
        check(app.action_request.calls.back().payload.include_detail,
            "Detailed export forwards explicit observation selection")
        app._on_action(1,JSON.stringify({"error":"Disk full"}).to_utf8_buffer())
        check(view.get("settings_message").text.contains("Disk full"),
            "Export failure remains visible in Settings")
        var piece_button: Button = view.get("delete_piece_button")
        var prior: int = app.action_request.calls.size()
        piece_button.pressed.emit()
        check(piece_dialog.visible and app.action_request.calls.size() == prior,
            "Piece deletion waits for an explicit confirmation")
        check(piece_dialog.dialog_text.contains("learning progress"),
            "Piece confirmation explains that saved learning progress is deleted")
        view.call("present_learning_status", {"current_fingerprint":"other-piece"})
        piece_dialog.confirmed.emit()
        piece_dialog.hide()
        check(app.action_request.calls.back() == {"operation":"learning.delete_piece",
            "payload":{"fingerprint":"piece-sha","confirm":true}},
            "Confirmed piece deletion is bound to its captured fingerprint")
        var polls_before: int = app.polls
        app._on_action(0,JSON.stringify({"summary":"Deleted"}).to_utf8_buffer())
        check(app.polls > polls_before and app.refreshes > 0,
            "Deletion refreshes application state and preferences")
        var all_button: Button = view.get("delete_learner_button")
        prior = app.action_request.calls.size()
        all_button.pressed.emit()
        check(learner_dialog.visible and app.action_request.calls.size() == prior,
            "Learner deletion waits for its own explicit confirmation")
        check(learner_dialog.dialog_text.contains("export"),
            "Permanent deletion explains exported files remain outside deletion")
        learner_dialog.confirmed.emit()
        learner_dialog.hide()
        check(app.action_request.calls.back() == {"operation":"learning.delete_learner",
            "payload":{"confirm":true}}, "Confirmed learner deletion uses its typed command")
        app._on_action(0,JSON.stringify({"summary":"Deleted"}).to_utf8_buffer())
    app.free()
    print("MEASUREMENT_CONTROL_FAILURES:",failures.size())
    quit(0 if failures.is_empty() else 1)
'''


def test_settings_controls_drive_typed_commands_and_present_results(tmp_path):
    executable = shutil.which("godot") or shutil.which("godot4")
    if executable is None:
        pytest.skip("Godot 4 unavailable")
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "measurement_controls.gd"
    script.write_text(GODOT_CONTROLS)
    result = subprocess.run([executable, "--headless", "--path", str(root / "godot"),
                             "--script", str(script)], capture_output=True,
                            text=True, timeout=25)
    log = result.stdout + result.stderr
    assert "SCRIPT ERROR" not in log, log
    assert "ERROR:" not in log, log
    assert result.returncode == 0, log
    assert "MEASUREMENT_CONTROL_FAILURES:0" in log, log
