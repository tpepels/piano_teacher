#!/usr/bin/env python3
"""Fail closed on removed runtime modules and missing relative Python imports.

Runs on source and on an assembled standalone release directory. It does not
import the application or need optional MIDI, Godot, ML or Verovio packages.
"""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

REMOVED = (
    "piano_teacher/score.py",
    "piano_teacher/score_geometry.py",
    "piano_teacher/raster.py",
    "piano_teacher/rendering/legacy",
    "piano_teacher/ui",
    "piano_teacher/qt_ui",
)
REMOVED_IMPORTS = (
    "piano_teacher.score_geometry", "piano_teacher.raster",
    "piano_teacher.rendering.legacy",
)
DEV_ONLY_GODOT_PATHS = (
    "godot/native_bridge_smoke.gd",
    "godot/production_ui_smoke.gd",
    "godot/ui_layout_smoke.gd",
    "godot/tests",
)


def audit_tree(root: Path, *, package: bool = False) -> list[str]:
    root = Path(root).resolve()
    result: list[str] = []
    source = root / "piano_teacher"
    if not (source / "__init__.py").is_file():
        return ["Missing canonical piano_teacher package"]
    for name in REMOVED:
        if (root / name).exists():
            result.append(f"Removed compatibility module was bundled: {name}")
    for file in sorted(source.rglob("*.py")):
        try:
            module = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except (OSError, UnicodeError, SyntaxError) as exc:
            result.append(f"{file.relative_to(root)}: {exc}")
            continue
        relative = file.relative_to(root)
        parts = relative.parts[:-1]
        if file.name == "__init__.py":
            parts = relative.parts[:-1]
        for node in ast.walk(module):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(REMOVED_IMPORTS):
                        result.append(f"{relative}:{node.lineno}: removed import {alias.name}")
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module and any(
                node.module == old or node.module.startswith(old + ".")
                for old in REMOVED_IMPORTS
            ):
                result.append(f"{relative}:{node.lineno}: removed import {node.module}")
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
        for path in (
            "PianoTeacher", "bin/godot", "bin/node",
            "godot/project.godot", "godot/native/piano_bridge.gdextension",
            "godot/native/bin/libpiano_bridge.linux.template_release.x86_64.so",
            "runtime/python/bin/python3",
        ):
            if not (root / path).is_file():
                result.append(f"Package missing required asset: {path}")
        if (root / "godot/addons/godot_mcp_toolkit").exists():
            result.append("Package includes a development-only MCP server")
        if (root / "godot/.godot").exists():
            result.append("Package includes the Godot editor cache")
        for path in DEV_ONLY_GODOT_PATHS:
            if (root / path).exists():
                result.append(f"Package includes developer-only Godot fixture: {path}")
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
    print("PHASE5_ARCHITECTURE_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
