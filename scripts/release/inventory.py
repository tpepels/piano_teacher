"""Inventory the assembled bytes, wheel owners, font hashes, and ELF requirements."""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def inspect_elf(path):
    header = subprocess.check_output(["readelf", "-d", path], text=True)
    return re.findall(r"\(NEEDED\).*?\[(.*?)\]", header)


def linked_host_libraries(root, libraries, supplied, environment):
    host = set()
    for name in libraries:
        linked = subprocess.check_output(["ldd", root / name], env=environment, text=True)
        for line in linked.splitlines():
            library, separator, target = line.partition(" => ")
            if not separator:
                continue
            library = library.strip()
            if library in supplied:
                # The top-level extension resolves its libpython through the launcher.
                # Wheel-private siblings can rely on their parent's loader/RPATH.
                if library.startswith("libpython") and str(root / "runtime/python/lib") not in target:
                    raise ValueError(f"{name} linked to external CPython: {line}")
            elif "not found" in target:
                raise ValueError(f"Missing host library for {name}: {line}")
            else:
                host.add(library)
    return host


def inventory(root):
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    if any(path.is_symlink() and not path.resolve().is_relative_to(root) for path in paths):
        raise ValueError("Release contains an external symlink")
    libraries = {}
    assets = {}
    sizes = {}
    for path in paths:
        name = str(path.relative_to(root))
        sizes[name] = path.stat().st_size
        with path.open("rb") as source:
            if source.read(4) == b"\x7fELF":
                libraries[name] = inspect_elf(path)
        if "/verovio/data/" in name or path.suffix == ".onnx":
            assets[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    supplied = {Path(name).name for name in libraries}
    needed = {lib for libs in libraries.values() for lib in libs}
    environment = os.environ | {"LD_LIBRARY_PATH": str(root / "runtime/python/lib")}
    host = linked_host_libraries(root, libraries, supplied, environment)
    return {"godot": subprocess.check_output([root / "bin/godot", "--version"], text=True).strip(),
            "cpython": subprocess.check_output([root / "runtime/python/bin/python3", "-V"],
                                              env=environment, text=True).strip(),
            "wheels": json.loads((root / "wheel-inventory.json").read_text()),
            "bytes_by_path": sizes, "elf_needed": libraries, "asset_sha256": assets,
            "external_elf_sonames": sorted(needed - supplied), "resolved_host_sonames": sorted(host),
            "dynamic_host_libraries": {"libcairo.so.2": "CairoSVG engraving rasterization",
                                       "libfluidsynth": "Sampled Listen with optional SF2 bank"},
            "device_requirements": "Host MIDI sequencer, display and audio drivers"}


if __name__ == "__main__":
    release = Path(sys.argv[1]).resolve()
    print(json.dumps(inventory(release), indent=2, sort_keys=True))
