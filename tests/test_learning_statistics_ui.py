import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from test_learning_statistics import ledger, begin, finish

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("godot") is None, reason="Godot unavailable")
def test_settings_statistics_controls_and_request_lifecycle(ledger, tmp_path):
    from piano_teacher.learning_statistics import learning_statistics
    begin(ledger, "report-take")
    finish(ledger, "report-take")
    report = learning_statistics(ledger)
    artifact = tmp_path / "report.json"
    artifact.write_text(json.dumps(report))
    result = subprocess.run(["godot", "--headless", "--path", str(ROOT / "godot"),
        "--script", str(ROOT / "tests/godot/learning_statistics.gd"), "--", str(artifact)],
        capture_output=True, text=True, timeout=20, env={**os.environ, "GODOT_SILENCE_ROOT_WARNING": "1"})
    output = result.stdout + result.stderr
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    assert "LEARNING_STATISTICS_UI_OK" in output, output
