"""Adaptive recovery honors validated course settings in a fresh process."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("multiplier,guided_after,bpm,guidance,slowdown", [
    (.9, 2, 90, [False, True, True, True], "10%"),
    (.75, 4, 75, [False, False, False, True], "25%"),
])
def test_adaptive_recovery_uses_startup_settings_for_real_rolling_decisions(
        tmp_path, multiplier, guided_after, bpm, guidance, slowdown):
    settings = json.loads((ROOT / "piano_teacher/lesson_settings.json").read_text())
    settings.update(recovery_tempo_multiplier=multiplier,
                    guided_recovery_after_failures=guided_after)
    path = tmp_path / "lesson_settings.json"
    path.write_text(json.dumps(settings))
    child = subprocess.run(
        [sys.executable, "-c", """
import json
from pathlib import Path
import sys

from piano_teacher import lesson_settings
lesson_settings.SETTINGS = lesson_settings.load_lesson_settings(Path(sys.argv[1]))
from piano_teacher.application.mistake_responses import (
    available_mistake_policies, resolve_mistake_policy, rolling_response,
)
from piano_teacher.recovery import RecoveryDecision

policy = resolve_mistake_policy("adaptive")
key = None
count = 0
responses = []
for _ in range(4):
    result = rolling_response(
        policy, RecoveryDecision(8.0, 0.0, 5, 2, 3),
        identity="source:stage", bpm=100, minimum_bpm=12,
        previous_key=key, previous_count=count, grid=(0.0, 4.0, 8.0))
    responses.append({"bpm": result.bpm, "guided": result.guided})
    key, count = result.trouble_key, result.count
choice = next(choice for choice in available_mistake_policies()
              if choice["id"] == "adaptive")
print(json.dumps({"responses": responses, "description": choice["description"]}))
""", str(path)], cwd=ROOT, check=True, capture_output=True, text=True,
        timeout=10)
    observed = json.loads(child.stdout)
    assert [result["bpm"] for result in observed["responses"]] == [bpm] * 4
    assert [result["guided"] for result in observed["responses"]] == guidance
    assert slowdown in observed["description"]
    assert str(guided_after) in observed["description"]
