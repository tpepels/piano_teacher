"""Bind evidence to immutable source and verification inputs (stdlib only)."""
from hashlib import sha256
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ("piano_teacher", "godot", "scripts", "tests", ".github", "pyproject.toml", "midi")


def current_provenance() -> dict:
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT)
    revision = git("rev-parse", "HEAD").decode().strip()
    paths = sorted(p for p in git("ls-files", "-z", "--", *INPUTS).decode().split("\0")
                   if p and not p.startswith("godot/.godot/"))
    digest = sha256()
    for name in paths:
        digest.update(name.encode() + b"\0")
        digest.update(sha256((ROOT / name).read_bytes()).digest())
    changed = set(git("diff", "--name-only", "HEAD", "--", *INPUTS).decode().splitlines())
    untracked = set(git("ls-files", "--others", "--exclude-standard", "--", *INPUTS).decode().splitlines())
    relevant = sorted(p for p in changed | untracked if not p.startswith("godot/.godot/")
                      and not p.endswith(".uid"))
    return {"revision": revision, "inputs_sha256": digest.hexdigest(), "clean": not relevant}
