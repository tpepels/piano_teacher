"""Exercise the documented acceptance script without running Python/Godot suites."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
FOCUSED_MODULES = [
    "tests/test_adaptive_hybrid_journey.py",
    "tests/test_composed_midi_lessons.py",
    "tests/test_lesson_generator_architecture.py",
    "tests/test_course_consolidation.py",
    "tests/test_fukuda_midi_phase4.py",
    "tests/test_midi_stage_wiring.py",
    "tests/test_strategy_handoff.py",
    "tests/test_state_projection.py",
    "tests/test_runtime_architecture_contract.py",
    "tests/test_phase5_architecture_audit.py",
    "tests/test_inprocess_dispatcher.py",
    "tests/test_phase6_inprocess.py",
    "tests/test_mastered_stage_replanning.py",
]
FIXTURES = [
    "continuous_score_flow.gd",
    "score_stream_admission.gd",
    "lesson_stage_picker.gd",
    "settings_ownership.gd",
]


@pytest.fixture
def workflow(tmp_path):
    # Copy only the scripts being exercised and real current fixture files.
    # An isolated PATH prevents an installed Godot from masking discovery bugs.
    repo = tmp_path / "workspace with spaces"
    (repo / "scripts").mkdir(parents=True)
    (repo / "godot").mkdir()
    (repo / "tests/godot").mkdir(parents=True)
    for name in ("verify-hybrid-workflow.sh", "godot-test.sh"):
        shutil.copyfile(ROOT / "scripts" / name, repo / "scripts" / name)
    for name in FIXTURES:
        shutil.copyfile(ROOT / "tests/godot" / name, repo / "tests/godot" / name)
    bins = tmp_path / "bin"
    bins.mkdir()
    for name in ("bash", "dirname", "timeout", "grep"):
        (bins / name).symlink_to(shutil.which(name))
    executable = f"#!{sys.executable}\n"
    python = repo / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text(executable + '''import json, os, sys
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(["python", *sys.argv[1:]]) + "\\n")
sys.exit(int(os.environ.get("PYTHON_STATUS", "0")))
''')
    python.chmod(0o755)
    godot = tmp_path / "fake-godot"
    godot.write_text(executable + '''import json, os, pathlib, sys
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps(["godot", *sys.argv[1:]]) + "\\n")
script = pathlib.Path(sys.argv[sys.argv.index("--script") + 1])
if not script.is_absolute() or not script.is_file():
    print("ERROR: Failed to load script: " + str(script))
elif script.name == os.environ.get("FAIL_FIXTURE"):
    print(os.environ["GODOT_OUTPUT"])
else:
    print(script.stem.upper() + "_FAILURES:0")
sys.exit(int(os.environ.get("GODOT_STATUS", "0")))
''')
    godot.chmod(0o755)
    env = os.environ.copy()
    for name in ("GODOT_BIN", "PYTHON", "PYTHON_STATUS", "GODOT_STATUS",
                 "GODOT_OUTPUT", "FAIL_FIXTURE"):
        env.pop(name, None)
    env.update(PATH=str(bins), CALL_LOG=str(tmp_path / "calls.jsonl"))

    def run(mode="--focused", *, discovery="godot", **overrides):
        if discovery == "explicit":
            env["GODOT_BIN"] = str(godot)
        elif discovery is not None:
            (bins / discovery).symlink_to(godot)
        result = subprocess.run(
            [str(bins / "bash"), str(repo / "scripts/verify-hybrid-workflow.sh"),
             *([] if mode is None else [mode])],
            cwd=tmp_path, env=env | overrides, text=True,
            capture_output=True, timeout=10,
        )
        log = Path(env["CALL_LOG"])
        calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        return result, calls

    return repo, run


@pytest.mark.parametrize("discovery", ["godot", "godot4", "explicit"])
def test_focused_runs_current_fixtures_and_mastery_gate(workflow, discovery):
    repo, run = workflow
    result, calls = run(discovery=discovery)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[0] == ["python", "-m", "pytest", "-q", "--tb=short", *FOCUSED_MODULES]
    assert calls[1:] == [
        ["godot", "--headless", "--path", "godot", "--script",
         str(repo / "tests/godot" / fixture),
         *(["--", "preferences"] if fixture == "settings_ownership.gd" else [])]
        for fixture in FIXTURES
    ]
    assert "Hybrid MIDI software verification finished." in result.stdout


@pytest.mark.parametrize("output", [
    "SCRIPT ERROR: Invalid call",
    "Parse Error: Invalid identifier",
    "ERROR: Failed to load script: fixture.gd",
    "LESSON_STAGE_PICKER_FAILURES: 2",
])
def test_zero_exit_godot_errors_fail_the_workflow(workflow, output):
    _, run = workflow
    result, calls = run(FAIL_FIXTURE="lesson_stage_picker.gd", GODOT_OUTPUT=output)
    assert result.returncode != 0
    assert output in result.stdout
    assert "Hybrid MIDI software verification finished." not in result.stdout
    assert all("preferences" not in call for call in calls)


def test_missing_current_fixture_cannot_report_success(workflow):
    repo, run = workflow
    (repo / "tests/godot/continuous_score_flow.gd").unlink()
    result, _ = run()
    assert result.returncode != 0
    assert "ERROR: Failed to load script:" in result.stdout
    assert "Hybrid MIDI software verification finished." not in result.stdout


def test_nonzero_godot_exit_stops_the_workflow(workflow):
    _, run = workflow
    result, calls = run(GODOT_STATUS="7")
    assert result.returncode == 7
    assert len(calls) == 2


def test_python_failure_stops_before_godot(workflow):
    _, run = workflow
    result, calls = run(PYTHON_STATUS="5")
    assert result.returncode == 5
    assert len(calls) == 1


@pytest.mark.parametrize("mode", ["--corpus", "--all"])
def test_corpus_modes_preserve_the_repertoire_gate(workflow, mode):
    _, run = workflow
    result, calls = run(mode)
    assert result.returncode == 0, result.stdout + result.stderr
    assert calls[-1] == ["python", "-m", "pytest", "-q", "--tb=short",
                         "tests/test_composed_midi_repertoire.py"]
    assert len(calls) == (1 if mode == "--corpus" else 6)


def test_no_argument_defaults_to_focused(workflow):
    _, run = workflow
    result, calls = run(None)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(calls) == 5


def test_missing_godot_skips_only_godot(workflow):
    _, run = workflow
    result, calls = run(discovery=None)
    assert result.returncode == 0
    assert len(calls) == 1
    assert "Godot binary not installed" in result.stderr


def test_invalid_mode_is_rejected_before_running_checks(workflow):
    _, run = workflow
    result, calls = run("--unknown")
    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert calls == []
