#!/usr/bin/env python3
"""Conservative static reachability audit for the embedded desktop application.

No automatic deletion decisions: runtime imports, Godot class_name references,
generated bindings and data-driven resources can escape static resolution.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict, deque
from pathlib import Path
import re
import sys

RESOURCE = re.compile(r'["\']res://([^"\']+)["\']')
GD_CLASS = re.compile(r'^\s*class_name\s+(\w+)', re.MULTILINE)
PY_NATIVE = re.compile(r'PyImport_ImportModule\("(piano_teacher(?:\.\w+)*)"\)')
PROJECT_SCENE = re.compile(r'^\s*run/main_scene\s*=\s*"res://([^"]+)"', re.MULTILINE)


def py_module_path(module: str, known: set[str]) -> str | None:
    path = module.replace('.', '/')
    for target in (path + '.py', path + '/__init__.py'):
        if target in known:
            return target
    return None


def py_imports(path: str, source: str, known: set[str]) -> tuple[set[str], list[str]]:
    edges: set[str] = set()
    unresolved: list[str] = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as exc:
        return edges, ['syntax error: ' + str(exc)]
    pkg = path[:-3].replace('/', '.').split('.')[:-1]
    if path.endswith('/__init__.py'):
        pkg = path[:-12].replace('/', '.').split('.')
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # level 1 is this package; level 2 is its parent.
                depth = len(pkg) - node.level + 1
                if depth < 1:
                    unresolved.append('invalid relative import at line ' + str(node.lineno))
                    continue
                base = '.'.join(pkg[:depth])
                if node.module:
                    base += '.' + node.module
            else:
                base = node.module or ''
            modules.append(base)
            modules.extend(base + '.' + alias.name for alias in node.names if alias.name != '*')
        elif isinstance(node, ast.Call):
            func = node.func
            dynamic = (isinstance(func, ast.Name) and func.id == '__import__') or (
                isinstance(func, ast.Attribute) and func.attr == 'import_module'
                and isinstance(func.value, ast.Name) and func.value.id == 'importlib')
            if dynamic:
                if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    modules.append(node.args[0].value)
                else:
                    unresolved.append('dynamic Python import at line ' + str(node.lineno))
        for module in modules:
            target = py_module_path(module, known)
            if target is not None:
                edges.add(target)
    return edges, unresolved


def gather(root: Path) -> tuple[set[str], dict[str, str]]:
    known: set[str] = set()
    texts: dict[str, str] = {}
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith(('godot/addons/', 'godot/.godot/', '.git/', '.venv/', 'dist/')):
            continue
        if path.suffix not in {'.py', '.gd', '.tscn', '.tres', '.godot', '.cpp', '.hpp', '.sh', '.gdextension'}:
            continue
        try:
            texts[rel] = path.read_text(encoding='utf-8')
            known.add(rel)
        except (OSError, UnicodeDecodeError):
            pass
    return known, texts


def walk(roots: set[str], edges: dict[str, set[str]]) -> set[str]:
    reached = set(roots)
    pending = deque(sorted(roots))
    while pending:
        for target in sorted(edges.get(pending.popleft(), set()) - reached):
            reached.add(target)
            pending.append(target)
    return reached


def audit(root: Path) -> dict:
    known, texts = gather(root)
    py = {p for p in known if p.startswith('piano_teacher/') and p.endswith('.py')}
    gd = {p for p in known if p.startswith('godot/') and p.endswith('.gd')}
    scenes = {p for p in known if p.startswith('godot/') and p.endswith(('.tscn', '.tres'))}
    sources = py | gd | scenes
    edges: dict[str, set[str]] = defaultdict(set)
    dynamic: dict[str, list[str]] = defaultdict(list)
    class_names = {match.group(1): path for path in gd
                   for match in [GD_CLASS.search(texts[path])] if match}
    for path in sorted(sources):
        source = texts[path]
        if path in py:
            imported, unresolved = py_imports(path, source, py)
            edges[path].update(imported)
            dynamic[path].extend(unresolved)
            continue
        for res in RESOURCE.findall(source):
            dest = 'godot/' + res
            if dest in sources:
                edges[path].add(dest)
        if path in gd:
            own = GD_CLASS.search(source)
            own_name = own.group(1) if own else ''
            for name, dest in class_names.items():
                if name != own_name and re.search(r'\b' + re.escape(name) + r'\b', source):
                    edges[path].add(dest)
            if re.search(r'\b(?:load|preload)\s*\(\s*(?!["\'])', source):
                dynamic[path].append('computed resource path')
    project = texts.get('godot/project.godot', '')
    roots: set[str] = {'piano_teacher/inprocess.py', 'godot/main.tscn'} & sources
    match = PROJECT_SCENE.search(project)
    if match and 'godot/' + match.group(1) in sources:
        roots.add('godot/' + match.group(1))
    for path, source in texts.items():
        if path.startswith('native/') and path.endswith(('.cpp', '.hpp')):
            for module in PY_NATIVE.findall(source):
                resolved = py_module_path(module, py)
                if resolved:
                    roots.add(resolved)
    for res in RESOURCE.findall(project):
        target = 'godot/' + res
        if target in sources:
            roots.add(target)
    if 'piano_teacher/__main__.py' in sources:
        roots.add('piano_teacher/__main__.py')
    # Standalone entry points explicitly invoked by project scripts.
    for path, source in texts.items():
        if path.startswith('scripts/') and path.endswith('.sh'):
            for candidate in py:
                if candidate in source:
                    roots.add(candidate)
    # Test references are reported separately, not used as production roots.
    tests = {p for p in known if p.startswith('tests/') and p.endswith(('.py', '.gd'))}
    for path in tests:
        source = texts[path]
        if path.endswith('.py'):
            imported, _ = py_imports(path, source, py)
            edges[path].update(imported)
        else:
            for res in RESOURCE.findall(source):
                if 'godot/' + res in sources:
                    edges[path].add('godot/' + res)
    test_used = walk(tests, edges) & sources
    runtime_used = walk(roots, edges) & sources
    return {
        'runtime_roots': sorted(roots),
        'counts': {'python': len(py), 'godot_scripts': len(gd),
                   'godot_resources': len(scenes)},
        'statically_reachable': sorted(runtime_used),
        'statically_unreached': sorted(sources - runtime_used),
        'unreached_test_referenced': sorted((sources - runtime_used) & test_used),
        'unresolved_dynamic_loads': {p: v for p, v in sorted(dynamic.items()) if v},
        'edges': {p: sorted(v) for p, v in sorted(edges.items()) if v},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--json', action='store_true', help='Full machine-readable graph')
    parser.add_argument('--output', type=Path, help='Write instead of printing')
    args = parser.parse_args()
    data = audit(args.root.resolve())
    if args.json:
        import json
        report = json.dumps(data, indent=2, sort_keys=True) + '\n'
    else:
        out = ['# A0 conservative static reachability report', '',
               'Unreached means no proven static dependency path from known roots;',
               '**never delete a file based on this result alone**. Check dynamic',
               'loading, reflection, Godot class_name and tests/package usage.', '',
               f'Python: {data["counts"]["python"]}; '
               f'Godot scripts: {data["counts"]["godot_scripts"]}; '
               f'Godot scene/resources: {data["counts"]["godot_resources"]}.', '',
               '## Runtime entry roots']
        out += ['- ' + p for p in data['runtime_roots']]
        out += ['', '## Unreached candidates requiring review']
        out += ['- ' + p + (' (test-referenced)' if p in data['unreached_test_referenced'] else '')
                for p in data['statically_unreached']]
        out += ['', '## Dynamic loading requiring manual resolution']
        for path, issues in data['unresolved_dynamic_loads'].items():
            out.append('- ' + path + ': ' + '; '.join(issues))
        report = '\n'.join(out) + '\n'
    if args.output:
        args.output.write_text(report, encoding='utf-8')
    else:
        sys.stdout.write(report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
