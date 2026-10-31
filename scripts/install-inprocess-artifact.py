#!/usr/bin/env python3
"""Install a matching GitHub Actions GDExtension ZIP using stdlib only.

Downloads are handled outside the application. This installer never runs
compilers, SCons, pip, git, or network calls.
"""
from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
BINARY = "godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so"
MANIFEST = "godot/native/piano_bridge.gdextension"
ABI = "godot/native/python-abi.txt"
REVISION = "godot/native/source-revision.txt"
EXPECTED = {BINARY, MANIFEST, ABI, REVISION}


def install(archive: Path, *, root: Path = ROOT, local_revision: str | None = None,
            python_abi: str | None = None, architecture: str | None = None) -> list[Path]:
    if local_revision is None:
        local_revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if python_abi is None:
        python_abi = f"{sys.version_info.major}.{sys.version_info.minor}"
    if architecture is None:
        architecture = platform.machine()
    if architecture != "x86_64":
        raise ValueError("Binary is for Linux x86_64; this machine is " + architecture)
    with ZipFile(archive) as bundle:
        paths = set(bundle.namelist())
        if not EXPECTED.issubset(paths):
            raise ValueError(f"Artifact is missing: {sorted(EXPECTED - paths)}")
        for path in paths:
            name = PurePosixPath(path)
            if name.is_absolute() or ".." in name.parts:
                raise ValueError("Unsafe ZIP member: " + path)
        remote = bundle.read(REVISION).decode().strip()
        abi = bundle.read(ABI).decode().strip()
        if remote != local_revision:
            raise ValueError(
                f"Artifact built from {remote[:12]} but checkout is "
                f"{local_revision[:12]}. Download the artifact for this commit.")
        if abi != python_abi:
            raise ValueError(
                f"Artifact is for CPython {abi}, but local Python is "
                f"{python_abi}. Use matching Python or a matching build.")
        outputs = []
        for name in sorted(EXPECTED):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(name))
            outputs.append(target)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path, help="ZIP from GitHub Actions")
    args = parser.parse_args()
    try:
        outputs = install(args.artifact)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Could not install compiled extension: {exc}\n")
    print("Installed verified native files:")
    for path in outputs:
        print(" ", path.relative_to(ROOT))
    print("Run ./run.sh (no build tools needed).")


if __name__ == "__main__":
    main()
