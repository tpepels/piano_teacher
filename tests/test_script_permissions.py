"""Release scripts must remain directly executable after GitHub tree edits."""
import os
from pathlib import Path


def test_verify_notation_script_retains_executable_mode():
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify-notation.sh"
    assert os.access(script, os.X_OK), (
        "scripts/verify-notation.sh must remain executable for ./scripts/verify-notation.sh"
    )
