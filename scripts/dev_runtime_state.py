#!/usr/bin/env python3
"""Developer launcher fingerprints for the embedded Godot/CPython bridge.

A source-only git pull requires a new embedded-runtime smoke, but a C++ rebuild
is needed only when native inputs, output files, architecture or Python ABI
change. Stamps describe files, never a commit number or a timestamp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NATIVE_STAMP = Path("godot/native/build-inputs.json")
BINARY = Path("godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so")
MANIFEST = Path("godot/native/piano_bridge.gdextension")
ABI_FILE = Path("godot/native/python-abi.txt")
NATIVE_INPUTS = (
    Path("native/SConstruct"),
    Path("native/piano_bridge.gdextension.in"),
    Path("scripts/build-inprocess.sh"),
)
RUNTIME_FILES = (
    Path("run.sh"), Path("pyproject.toml"),
    Path("scripts/verify-native-bridge.sh"),
    Path("scripts/dev_runtime_state.py"),
)
PACKAGES = ("mido", "python-rtmidi", "music21", "verovio", "CairoSVG", "Pillow")


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_tree(root: Path, files: list[Path]) -> str:
    h = hashlib.sha256()
    for relative in sorted(set(files), key=str):
        source = root / relative
        if not source.is_file():
            raise FileNotFoundError(f"Required runtime input missing: {relative}")
        h.update(relative.as_posix().encode("utf-8") + b"\0")
        h.update(bytes.fromhex(_hash_file(source)))
    return h.hexdigest()


def native_inputs(root: Path = ROOT) -> str:
    source = root / "native/src"
    if not source.is_dir():
        raise FileNotFoundError("Missing native/src bridge sources")
    files = list(NATIVE_INPUTS)
    files.extend(p.relative_to(root) for p in source.rglob("*") if p.is_file())
    return _hash_tree(root, files)


def native_state(root: Path = ROOT) -> dict:
    binary = root / BINARY
    manifest = root / MANIFEST
    abi_file = root / ABI_FILE
    if not binary.is_file() or binary.stat().st_size == 0:
        raise FileNotFoundError(f"Native bridge is missing: {BINARY}")
    if not manifest.is_file() or manifest.stat().st_size == 0:
        raise FileNotFoundError(f"Native manifest is missing: {MANIFEST}")
    if not abi_file.is_file():
        raise FileNotFoundError(f"Native ABI marker is missing: {ABI_FILE}")
    abi = f"{sys.version_info.major}.{sys.version_info.minor}"
    saved_abi = abi_file.read_text(encoding="utf-8").strip()
    if saved_abi != abi:
        raise ValueError(f"Native bridge uses CPython {saved_abi}, current interpreter is {abi}")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("The current development bridge requires Linux x86_64")
    return {
        "schema": 1,
        "abi": abi,
        "architecture": platform.machine(),
        "native_inputs": native_inputs(root),
        "binary_sha256": _hash_file(binary),
        "manifest_sha256": _hash_file(manifest),
    }


def check_native(root: Path = ROOT) -> bool:
    try:
        recorded = json.loads((root / NATIVE_STAMP).read_text(encoding="utf-8"))
        actual = native_state(root)
        if recorded != actual:
            print("Native build inputs or binary differ from the installed bridge",
                  file=sys.stderr)
            return False
    except (FileNotFoundError, OSError, ValueError, TypeError) as exc:
        print(f"Native bridge needs a build: {exc}", file=sys.stderr)
        return False
    return True


def record_native(root: Path = ROOT) -> None:
    state = native_state(root)
    target = root / NATIVE_STAMP
    target.parent.mkdir(parents=True, exist_ok=True)
    # A crashed build must not leave a partly-written success marker.
    descriptor, name = tempfile.mkstemp(prefix=".build-inputs-", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(state, stream, sort_keys=True, indent=2)
            stream.write("\n")
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def runtime_signature(godot: Path, root: Path = ROOT) -> str:
    """Only verified input changes invalidate the previous Godot smoke."""
    files = list(RUNTIME_FILES)
    for relative_dir, endings in (
        ("piano_teacher", (".py", ".json", ".cjs")),
        ("godot", (".gd", ".gdextension", ".tscn", ".tres", ".gdshader", ".gd.uid")),
    ):
        directory = root / relative_dir
        for item in directory.rglob("*"):
            if not item.is_file():
                continue
            relative = item.relative_to(root)
            if any(part in {".godot", "addons", "__pycache__"} for part in relative.parts):
                continue
            if item.name.endswith(endings):
                files.append(relative)
    files.extend((BINARY, MANIFEST, ABI_FILE, NATIVE_STAMP))
    h = hashlib.sha256()
    h.update(_hash_tree(root, files).encode("ascii"))
    h.update(sys.executable.encode("utf-8"))
    h.update(sys.prefix.encode("utf-8"))
    h.update(sys.version.encode("utf-8"))
    h.update(str(godot.resolve()).encode("utf-8"))
    info = godot.stat()
    h.update(f"{info.st_mtime_ns}:{info.st_size}".encode("ascii"))
    for package in PACKAGES:
        try:
            version = metadata.version(package)
        except metadata.PackageNotFoundError:
            version = "NOT_INSTALLED"
        h.update(f"{package}={version}\n".encode("utf-8"))
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check-native", "record-native", "runtime-signature"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--godot", type=Path)
    args = parser.parse_args()
    if args.action == "check-native":
        return 0 if check_native(args.root) else 1
    try:
        if args.action == "record-native":
            record_native(args.root)
        else:
            if args.godot is None:
                parser.error("--godot is required for runtime-signature")
            print(runtime_signature(args.godot, args.root))
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"Could not inspect native runtime: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
