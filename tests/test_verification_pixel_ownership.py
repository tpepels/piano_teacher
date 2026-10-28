"""Verifier foundations cannot load proof coordinators or production recognition."""
import ast
from importlib.util import resolve_name
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTATION = ROOT / "piano_teacher/notation"
FOUNDATIONS = (
    "pixel_ink", "pixel_context", "pixel_motion", "head_registration", "captured_frames",
)
COORDINATORS = {
    "phase3_pixels", "symbol_pixel_proof", "feature_pixels", "connector_pixels",
    "extra_symbol_pixels",
}


def notation_dependencies():
    modules = {}
    for path in NOTATION.rglob("*.py"):
        parts = path.relative_to(NOTATION).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules[".".join(("piano_teacher", "notation", *parts))] = path
    graph = {name: set() for name in modules}
    for name, path in modules.items():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                targets = {item.name for item in node.names}
            elif isinstance(node, ast.ImportFrom):
                package = name if path.name == "__init__.py" else name.rpartition(".")[0]
                base = resolve_name("." * node.level + (node.module or ""), package) if node.level else node.module or ""
                targets = {base, *(base + "." + item.name for item in node.names)}
            else:
                continue
            graph[name].update(target for target in targets if target.startswith("piano_teacher."))
    return graph


def test_verification_dependencies_are_acyclic_including_function_local_imports():
    graph = notation_dependencies()
    done = set()

    def visit(name, active):
        assert name not in active, "Runtime import cycle: " + " -> ".join((*active, name))
        if name in done:
            return
        for dependency in sorted(graph.get(name, ())):
            visit(dependency, (*active, name))
        done.add(name)

    for name in sorted(COORDINATORS | {"raster_matching"}):
        visit("piano_teacher.notation." + name, ())


@pytest.mark.parametrize("name", FOUNDATIONS)
def test_pixel_foundations_are_independent_of_coordinators_and_production(name):
    graph = notation_dependencies()
    owner = "piano_teacher.notation." + name
    assert owner in graph, "Missing independent pixel owner: " + owner
    pending, visited = [owner], set()
    while pending:
        current = pending.pop()
        assert current.rsplit(".", 1)[-1] not in COORDINATORS, current
        assert not current.startswith(("piano_teacher.notation.assets", "piano_teacher.rendering",
                                       "piano_teacher.application", "piano_teacher.score",
                                       "piano_teacher.server", "piano_teacher.notation.model",
                                       "piano_teacher.notation.lesson")), current
        if current not in visited:
            visited.add(current)
            pending.extend(graph.get(current, ()))
    code = """
import importlib.abc
import sys
class RejectProductionAndCoordinators(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        prohibited = ('piano_teacher.notation.assets', 'piano_teacher.rendering',
                      'piano_teacher.application', 'piano_teacher.score', 'piano_teacher.server',
                      'piano_teacher.notation.model', 'piano_teacher.notation.lesson')
        if fullname.startswith(prohibited) or fullname.rsplit('.', 1)[-1] in %r:
            raise AssertionError('Pixel foundation imported ' + fullname)
sys.meta_path.insert(0, RejectProductionAndCoordinators())
import importlib
importlib.import_module(%r)
""" % (COORDINATORS, owner)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_separate_translation_procedures_preserve_their_opposite_signs():
    path = NOTATION / "pixel_motion.py"
    assert path.is_file(), "Missing independent translation owner"
    import numpy as np
    from PIL import Image
    from piano_teacher.notation.pixel_motion import horizontal_dice, frame_shift, register_translation

    first = np.zeros((40, 320), dtype=bool)
    first[:, 35:270] = np.random.default_rng(51).random((40, 235)) < .15
    second = np.zeros_like(first)
    second[:, :-7] = first[:, 7:]
    scores = horizontal_dice(first, second, 20)
    assert max(scores) == (1., 7)
    shift, evidence = register_translation(first, second, 12.)
    assert shift == -7 and evidence["pixels"] == -7
    assert evidence["agreement"] == 1.
    pictures = [Image.fromarray(np.repeat((mask * 230).astype(np.uint8)[:, :, None], 3, axis=2))
                for mask in (first, second)]
    assert frame_shift(*pictures) == dict(shift=7, contour_agreement=1.)
    assert frame_shift(*reversed(pictures)) == dict(shift=-7, contour_agreement=1.)


@pytest.mark.parametrize("first", sorted(COORDINATORS | {"raster_matching"}))
def test_detector_entry_points_import_in_fresh_processes(first):
    order = [first, *sorted((COORDINATORS | {"raster_matching"}) - {first})]
    code = "import importlib; " + "; ".join(
        "importlib.import_module(%r)" % ("piano_teacher.notation." + name) for name in order)
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
