"""Stage only production entry points, reachable application modules and wheel records."""

import base64
import hashlib
import json
import re
import runpy
import shutil
import sys
import sysconfig
from importlib.metadata import distribution
from pathlib import Path

import tomllib
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
GODOT_ROOTS = (
    "project.godot", "main.tscn", "native/piano_bridge.gdextension", "native/python-abi.txt",
    "assets/countin/README.md", *(f"assets/countin/{word}.ogg{suffix}"
    for word in ("ichi", "ni", "san", "shi") for suffix in ("", ".import")),
)
ENGINE_ROOTS = (
    "piano_teacher/inprocess.py", "piano_teacher/application/score_worker.py",
    "piano_teacher/fingering/worker.py", "piano_teacher/__init__.py",
)
WHEEL_OWNERS = {
    "numpy": "Fingering tensors and sampled piano PCM",
    "mido": "MIDI file import and device messages",
    "python-rtmidi": "MIDI driver discovery and input",
    "music21": "MusicXML import",
    "onnxruntime": "CPU fingering inference",
    "verovio": "Notation engraving and music fonts",
    "cairosvg": "Rasterization of engraved score fragments",
    "pillow": "Score ink and atlas images",
}
ENGINE_ASSETS = (
    "piano_teacher/soundfonts/UprightPianoKW-small.sf2", "piano_teacher/soundfonts/NOTICE.txt",
    "piano_teacher/lesson_settings.json", "piano_teacher/fingering/THIRD_PARTY_NOTICES.md",
    *(f"piano_teacher/fingering/models/fingering_transformer_{hand}.onnx" for hand in ("left", "right")),
)


def copy(source, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def stage_application(stage):
    audit = runpy.run_path(str(ROOT / "scripts/audit-a0-reachability.py"))
    known = {p.relative_to(ROOT).as_posix() for p in (ROOT / "piano_teacher").rglob("*.py")}
    pending = list(ENGINE_ROOTS)
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        imports, unresolved = audit["py_imports"](path, (ROOT / path).read_text(), known)
        if unresolved:
            raise ValueError(f"Review dynamic imports in {path}: {unresolved}")
        pending.extend(imports)
        for parent in Path(path).parents:
            marker = str(parent / "__init__.py")
            if marker in known:
                pending.append(marker)
    for path in (*visited, *ENGINE_ASSETS):
        copy(ROOT / path, stage / path)


def stage_godot(stage):
    pending = list(GODOT_ROOTS)
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        source = ROOT / "godot" / path
        copy(source, stage / "godot" / path)
        if source.suffix in {".gd", ".gdextension", ".godot", ".tscn", ".gdshader"}:
            for target in re.findall(r'"res://([^"]+)"', source.read_text()):
                if "%" not in target:
                    pending.append(target)


def requirements():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    pending = list(project["dependencies"] + project["optional-dependencies"]["godot"])
    resolved = {}
    while pending:
        req = Requirement(pending.pop())
        key = canonicalize_name(req.name)
        if req.marker and not req.marker.evaluate():
            continue
        dist = distribution(req.name)
        if not req.specifier.contains(dist.version):
            raise ValueError(f"{dist.version} does not satisfy {req}")
        if req.extras:
            raise ValueError(f"Review release dependency extras for {req}")
        if key not in resolved:
            resolved[key] = dist
            pending.extend(dist.requires or ())
    return resolved


def wheel_runtime(path):
    parts = path.parts
    if ".." in parts or path.is_absolute() or "__pycache__" in parts:
        return False
    if path.suffix in {".pyc", ".a", ".h", ".hpp", ".c", ".cpp", ".pyx", ".pxd"}:
        return False
    if parts == ("verovio", "data", "Liberation.css"):
        # fontTextLiberation defaults to false throughout our engraving pipeline.
        return False
    if parts[0] == "music21":
        # Importer code and its schema. Upstream's optional corpus, Scala scales
        # and format samples carry independent rights and have no app consumer.
        return (path.suffix == ".py"
                or path.name.lower() in {"license", "license.txt"}
                or parts == ("music21", "musicxml", "musicxml.xsd"))
    if parts[0] == "onnxruntime" and len(parts) > 2 and parts[1] != "capi":
        return False
    return not {"tests", "benchmarks", "sample_data"} & set(parts)


def stage_python(stage):
    prefix = stage / "runtime/python"
    stdlib = Path(sysconfig.get_path("stdlib"))
    target = prefix / "lib" / stdlib.name
    copy(Path(sys.executable), prefix / "bin/python3")
    libdir = Path(sys.base_prefix) / "lib"
    soname = sysconfig.get_config_var("INSTSONAME")
    copy(libdir / soname, prefix / "lib" / soname)
    alias = f"libpython{sys.version_info.major}.{sys.version_info.minor}.so"
    if alias != soname:
        (prefix / "lib" / alias).symlink_to(soname)
    excluded = {"site-packages", "dist-packages", "Tools", "test", "tests", "idlelib",
                "turtledemo", "turtle.py", "tkinter", "_tkinter*.so", "ensurepip", "venv", "__pycache__"}
    shutil.copytree(stdlib, target, ignore=shutil.ignore_patterns(
        *excluded, "*.pyc", "config-*", "_test*.so", "_xxtest*.so"))
    report = {}
    resolved = requirements()
    for name, dist in sorted(resolved.items()):
        size = 0
        notices = []
        for path in dist.files or ():
            if wheel_runtime(path):
                source = Path(dist.locate_file(path))
                if path.parts[:2] == ("verovio", "data"):
                    digest = base64.urlsafe_b64encode(hashlib.sha256(source.read_bytes()).digest())
                    if not path.hash or path.hash.mode != "sha256" or path.hash.value != digest.decode().rstrip("="):
                        raise ValueError(f"Verovio wheel resource differs from its RECORD: {path}")
                copy(source, target / "site-packages" / path)
                size += source.stat().st_size
                if ("licenses" in path.parts or path.name.lower().startswith(
                        ("license", "copying", "notice", "thirdpartynotice", "copyright"))):
                    notices.append(str(path))
        if not size:
            raise ValueError(f"Missing installed wheel records for {name}")
        requirements_used = [Requirement(spec) for spec in dist.requires or ()]
        dependencies = sorted({canonicalize_name(req.name) for req in requirements_used
                               if not req.marker or req.marker.evaluate()})
        report[name] = {"version": dist.version, "bytes": size, "requires": dependencies,
                        "notice_paths_in_site_packages": sorted(notices),
                        "role": WHEEL_OWNERS.get(name, "Transitive wheel dependency")}

    (stage / "wheel-inventory.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    stage_application(directory)
    stage_godot(directory)
    stage_python(directory)
