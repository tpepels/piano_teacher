#!/usr/bin/env python3
"""Validate import closure and the assembled application's required assets.

Runs on source and on an assembled standalone release directory. It does not
import the application or need optional MIDI, Godot, ML or Verovio packages.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from importlib.metadata import distributions
from pathlib import Path

DEVELOPMENT_PATHS = (
    "godot/addons",
    "godot/.mcp.json",
    "midi",
    "godot/tests",
    "piano_teacher/research",
    "godot/native_bridge_smoke.gd",
    "godot/production_ui_smoke.gd",
    "godot/production_session_journey.gd",
    "godot/production_fake_midi_journey.gd",
)


def audit_fingering_assets(root: Path) -> list[str]:
    fingering = root / "piano_teacher/fingering"
    required = [
        fingering / "worker.py",
        fingering / "THIRD_PARTY_NOTICES.md",
        *(fingering / f"models/fingering_transformer_{hand}.onnx" for hand in ("left", "right")),
    ]
    errors = [
        f"Package missing required asset: {path.relative_to(root)}"
        for path in required if not path.is_file() or not path.stat().st_size
    ]
    for notice in ("LICENSE", "ThirdPartyNotices.txt"):
        pattern = f"runtime/python/lib/python*/site-packages/onnxruntime/{notice}"
        if not any(path.is_file() and path.stat().st_size for path in root.glob(pattern)):
            errors.append(f"Package missing ONNX Runtime notice: {notice}")
    legacy_paths = (
        root / "bin/node",
        fingering / "lumikey_runtime",
        *root.glob("runtime/python/lib/python*/site-packages/piano_teacher/fingering/lumikey_runtime"),
    )
    if any(path.exists() for path in legacy_paths):
        errors.append("Package includes the retired Node fingering runtime")
    return errors


def audit_dependencies(root: Path) -> list[str]:
    sites = list(root.glob("runtime/python/lib/python*/site-packages"))
    inventory = root / "wheel-inventory.json"
    if not inventory.is_file() or len(sites) != 1:
        return ["Package missing wheel inventory or Python site-packages"]
    versions = {re.sub(r"[-_.]+", "-", d.metadata["Name"]).lower(): d.version
                for d in distributions(path=[str(sites[0])])}
    expected = {name: data["version"] for name, data in json.loads(inventory.read_text()).items()}
    errors = []
    if versions != expected:
        errors.append("Installed wheel versions differ from the resolved runtime inventory")
    forbidden = {"pip", "pytest", "scons", "coverage", "ruff", "gdtoolkit", "setuptools"}
    if unexpected := versions.keys() & forbidden:
        errors.append(f"Development wheels installed: {sorted(unexpected)}")
    if next(root.rglob("__pycache__"), None) or next(root.rglob("*.pyc"), None):
        errors.append("Package includes compiled Python caches")
    for notice in ("Library-sources.txt", "FlatBuffers-LICENSE.txt", "Godot.txt", "Verovio-fonts.txt", "godot-cpp-LICENSE.md"):
        if not (root / "licenses" / notice).is_file() or not (root / "licenses" / notice).stat().st_size:
            errors.append(f"Empty release license: {notice}")
    return errors


def audit_tree(root: Path, *, package: bool = False) -> list[str]:
    root = Path(root).resolve()
    result: list[str] = []
    source = root / "piano_teacher"
    if not (source / "__init__.py").is_file():
        return ["Missing canonical piano_teacher package"]
    for file in sorted(source.rglob("*.py")):
        try:
            module = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (OSError, UnicodeError, SyntaxError) as exc:
            result.append(f"{file.relative_to(root)}: {exc}")
            continue
        relative = file.relative_to(root)
        parts = relative.parts[:-1]
        for node in ast.walk(module):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.level:
                continue
            if node.level > len(parts):
                result.append(f"{relative}:{node.lineno}: relative import escapes package")
                continue
            prefix = parts[:len(parts) - node.level + 1]
            target = prefix + tuple(node.module.split(".") if node.module else ())
            base = root.joinpath(*target)
            if not (base.with_suffix(".py").is_file() or base.is_dir()):
                result.append(f"{relative}:{node.lineno}: missing relative import {'.'.join(target)}")
    if package:
        result.extend(audit_runtime_files(root))
    return result


def audit_godot_imports(root):
    result = []
    import_dir = root / "godot/.godot"
    if not import_dir.is_dir():
        result.append("Missing imported Godot runtime resources")
    else:
        # A source distribution of a Godot app MUST carry its imported
        # runtime audio/graphics. Never ship editor layouts, filesystem
        # caches, editor plugins or test-generated scene data.
        unexpected = sorted(p.name for p in import_dir.iterdir()
                            if p.name != "imported")
        if unexpected:
            result.append("Package includes the Godot editor cache: " +
                          ", ".join(unexpected))
        prebuilt = import_dir / "imported"
        if not prebuilt.is_dir() or not any(prebuilt.iterdir()):
            result.append("Package has no compiled Godot imported runtime assets")
        for word in ("ichi", "ni", "san", "shi"):
            declared = root / "godot" / "assets" / "countin" / f"{word}.ogg.import"
            source = root / "godot" / "assets" / "countin" / f"{word}.ogg"
            if not declared.is_file() or not source.is_file():
                result.append(f"Package missing count-in source/import: {word}")
                continue
            record = declared.read_text()
            paths = re.findall(r'^path="res://([^"]+)"' + r'$', record, flags=re.M)
            if len(paths) != 1 or not (root / "godot" / paths[0]).is_file():
                result.append(f"Package missing compiled count-in audio: {word}")
    return result


def audit_runtime_files(root):
    result = audit_godot_imports(root)
    for path in (
        "PianoTeacher", "bin/godot", "runtime/lib/libfluidsynth.so.3",
        "piano_teacher/soundfonts/NOTICE.txt", "piano_teacher/soundfonts/UprightPianoKW-small.sf2",
        "godot/project.godot", "godot/native/piano_bridge.gdextension",
        "godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so",
        "runtime/python/bin/python3",
        "piano_teacher/application/score_worker.py",
    ):
        if not (root / path).is_file():
            result.append(f"Package missing required asset: {path}")
    result.extend(audit_fingering_assets(root))
    result.extend(audit_dependencies(root))
    for path in DEVELOPMENT_PATHS:
        if (root / path).exists():
            result.append(f"Package includes development files: {path}")
        if path.endswith(".gd") and (root / (path+".uid")).exists():
            result.append(f"Package includes developer-only Godot UID: {path}.uid")
    project = root / "godot/project.godot"
    if project.is_file() and ("MCPRuntimeServer" in project.read_text()
                              or "godot_mcp_toolkit" in project.read_text()):
        result.append("Package still starts a development-only runtime")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--package", action="store_true")
    args = parser.parse_args()
    errors = audit_tree(args.root, package=args.package)
    if errors:
        print("\n".join(errors))
        return 1
    print("PACKAGE_CONTENTS_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
