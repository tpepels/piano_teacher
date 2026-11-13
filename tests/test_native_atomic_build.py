"""Failed/interrupted builds must not truncate a loaded extension inode."""
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def test_failed_and_interrupted_build_preserve_installed_binary(tmp_path):
    import shutil
    for interrupted in (False, True):
        project = tmp_path / str(interrupted)
        (project / "scripts").mkdir(parents=True)
        (project / "native/godot-cpp").mkdir(parents=True)
        (project / "native/godot-cpp/SConstruct").touch()
        (project / "godot/native/bin").mkdir(parents=True)
        shutil.copy(ROOT / "scripts/build-inprocess.sh", project / "scripts")
        binary = project / "godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so"
        binary.write_bytes(b"mapped-old-binary")
        inode = binary.stat().st_ino
        commands = project / "commands"
        commands.mkdir()
        fake = commands / "scons"
        fake.write_text("#!/bin/bash\nset -eu\nout='../godot/native/bin'\nfor arg in \"$@\"; do case \"$arg\" in piano_output_dir=*) out=${arg#*=};; esac; done\nmkdir -p \"$out\"\nprintf partial > \"$out/libpiano_bridge.linux.template_release.x86_64.so\"\n" + ("touch ../started\nsleep 30\n" if interrupted else "exit 9\n"))
        fake.chmod(0o755)
        env = {**os.environ, "PATH": str(commands)+":"+os.environ["PATH"], "PIANO_PYTHON": str(ROOT / ".venv/bin/python"), "PIANO_SKIP_NATIVE_SMOKE": "1"}
        process = subprocess.Popen(["bash", "scripts/build-inprocess.sh"], cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        if interrupted:
            deadline = time.monotonic()+5
            while not (project / "started").exists() and time.monotonic() < deadline:
                time.sleep(.01)
            assert (project / "started").exists()
            os.killpg(process.pid, signal.SIGTERM)
        process.communicate(timeout=5)
        assert process.returncode != 0
        assert binary.read_bytes() == b"mapped-old-binary"
        assert binary.stat().st_ino == inode
