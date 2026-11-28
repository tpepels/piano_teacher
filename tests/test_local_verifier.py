"""Exercise the actual one-command runner without a Godot installation."""
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest


@pytest.mark.parametrize("args,expected", [
    ([], {"regression", "native", "visual", "pacing"}),
    (["--quick"], {"regression"}),
    (["--visual"], {"visual", "pacing"}),
])
@pytest.mark.parametrize("regression_status", [0, 7])
def test_local_runner_collects_all_selected_results(tmp_path, args, expected, regression_status):
    source = Path(__file__).resolve().parents[1] / "scripts" / "verify.sh"
    root = tmp_path / "repo"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(source, scripts / "verify.sh")
    (scripts / "test.sh").write_text('echo regression; exit "$REGRESSION_STATUS"\n')
    (scripts / "verify-embedded-production-local.sh").write_text(
        'if [[ ${1:-} == --visual-only ]]; then\n'
        '  mkdir -p "$PIANO_VISUAL_RESULTS"\n'
        '  echo "$PIANO_VISUAL_FPS/$PIANO_VISUAL_PACING_ONLY" > "$PIANO_VISUAL_RESULTS/report.txt"\n'
        'fi\necho native\n')
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Test",
                    "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
    results = tmp_path / "results"
    env = dict(os.environ, PIANO_TEST_RESULTS=str(results), REGRESSION_STATUS=str(regression_status))
    completed = subprocess.run(["bash", str(scripts / "verify.sh"), *args],
                               env=env, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert completed.returncode == int(bool(regression_status and "regression" in expected)), completed.stderr
    archives = list(results.glob("*.zip"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as z:
        names = {Path(name).name for name in z.namelist()}
        assert {name.removesuffix(".log") for name in names if name.endswith(".log")} == expected
        assert {"revision.txt", "git-status.txt", "summary.txt"} <= names
        assert not any("scratch." in name for name in z.namelist())
        if "visual" in expected:
            for folder, value in [("visual-full", "30/0"), ("visual-pacing", "60/1")]:
                name = next(name for name in z.namelist() if name.endswith(f"{folder}/report.txt"))
                assert z.read(name).decode().strip() == value
