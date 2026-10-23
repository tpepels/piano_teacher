#!/usr/bin/env python3
"""Package Phase3 bytes without rerendering or promoting verification results.

``package_evidence(reports_root, raw_root, out, revision)`` returns the exact
schema-version-1 object written to evidence-manifest.json. ``complete`` means
artifact integrity/availability, NEVER notation readiness. The caller-supplied
revision identifies packaging; producer provenance is retained verbatim and is
independently enforced by the release gate. Historical reports gain no invented
provenance. Outputs must be new/empty and cannot overlap either input tree.

``validate_manifest(manifest_path, reports_root, revision)`` returns
``{complete, errors, cases}``, independently checking the pinned 102 identities,
exact compact report bytes, packaged hashes, roles and per-window requirements.
Neither entry point runs a renderer. Only the bounded derived diagnostics need
the optional image/font dependencies; original evidence is always retained.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.aggregate_phase3_corpus import HANDS, PINNED_SOURCES


def capture_dependency_hash(root):
    """Use the capture runner's complete theme/resource version boundary."""
    from scripts.check_native_verovio_overlay import capture_dependency_hash as current_hash
    return current_hash(root)


def capture_protocol_hash(root):
    """Same ordered protocol bytes as the runner, without running Godot."""
    sources = [root / "tests/godot/native_verovio_overlay.gd",
               *sorted((root / "godot/notation").rglob("*.gd"))]
    return sha256(b"".join(path.relative_to(root).as_posix().encode() + path.read_bytes()
                           for path in sources)).hexdigest()


def _capture_versions():
    try:
        return dict(dependencies=capture_dependency_hash(ROOT), protocol=capture_protocol_hash(ROOT))
    except (ImportError, OSError, ValueError) as exc:
        return dict(error=f"current capture version hashes unavailable: {exc}")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise ValueError(f"nonfinite JSON value: {value}")


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object,
                      parse_constant=_constant)


def _digest(path):
    with path.open("rb") as stream:
        value = sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _json(path, errors, label):
    try:
        data = _load(path)
        if not isinstance(data, dict):
            raise ValueError("expected JSON object")
        return data
    except (OSError, ValueError, RecursionError) as exc:
        errors.append(f"{label}: missing/unreadable: {exc}")
        return {}


def _relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError(f"unsafe relative path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("..", ".") for part in name.split("/")):
        raise ValueError(f"unsafe relative path: {name!r}")
    return path


def _safe_file(root, name):
    parts = _relative(name).parts
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError(f"symlink evidence is not allowed: {name}")
    if not path.is_file():
        raise ValueError(f"missing file: {name}")
    return path


def _role(path):
    name = path.name
    if name == "summary.json":
        return "raw_report"
    if name.startswith("original."):
        return "original"
    if name in ("score.musicxml", "generated.musicxml"):
        return "generated"
    if name in ("fixture.json", "model.json"):
        return "model"
    if name.startswith("verovio-") and path.suffix in (".svg", ".png"):
        return "reference_svg" if path.suffix == ".svg" else "reference_png"
    if name.startswith("native-") and path.suffix == ".png":
        return "native_png"
    if name == "independent-pixels.json":
        return "independent_pixels"
    if name == "independent-rests.json":
        return "independent_rests"
    if name == "capture-manifest.json":
        return "capture_manifest"
    if path.suffix == ".log":
        return "log"
    if path.suffix == ".png":
        return "control_png"
    return "raw"


def _entry_role(relative):
    if relative == PurePosixPath("report/summary.json"):
        return "report"
    if relative.parts[0] == "original":
        return "original"
    if relative.parts[0] in ("raw", "compact"):
        return _role(relative)
    if relative.parts[0] == "diagnostics":
        return "glyph_reference" if relative.suffix == ".svg" else "diagnostic"
    raise ValueError(f"unknown evidence path: {relative}")


def _expected():
    for index, source in enumerate(PINNED_SOURCES):
        for kind in ("semantic", "visual"):
            for hand in HANDS:
                yield kind, index, source, hand


def _case_dir(kind, index, hand):
    return Path("cases") / f"{kind}-{index}-{hand}"


def _report_path(reports, kind, index, hand):
    prefix = "phase3-semantic-report" if kind == "semantic" else "phase3-report"
    return reports / f"{prefix}-{index}-{hand}" / "summary.json"


def _source_path(source):
    return ROOT / (source if "/" in source else "midi/" + source)


def _identity(data, case, errors):
    if (type(data.get("schema_version")) is not int or data["schema_version"] != 1
            or type(data.get("source_index")) is not int
            or any(data.get(key) != case[key] for key in
                   ("source_index", "source", "hand", "verification_kind"))):
        errors.append("report identity does not match pinned schema/source/index/kind/hand")
    if case["source_sha256"] is None or data.get("source_sha256") != case["source_sha256"]:
        errors.append("report source_sha256 does not match actual pinned original hash")


def _hash_match(path, expected, errors, label):
    try:
        if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
            raise ValueError("missing/malformed expected sha256")
        if _digest(path) != expected:
            raise ValueError("sha256 hash mismatch")
    except (OSError, ValueError) as exc:
        errors.append(f"{label}: {exc}")


def _require(folder, name, role, errors, label):
    try:
        return _safe_file(folder, name)
    except ValueError as exc:
        errors.append(f"{label}: missing required {role}: {exc}")
        return None


def _check_semantic(raw, data, case, errors):
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    for key, name, role in (("original", "original" + Path(case["source"]).suffix, "original"),
                            ("generated", "generated.musicxml", "generated"),
                            ("native", "model.json", "model")):
        path = _require(raw, name, role, errors, "semantic")
        record = artifacts.get(key)
        if not isinstance(record, dict) or record.get("path") != name:
            errors.append(f"semantic: missing/wrong {role} artifact declaration")
            continue
        if path:
            _hash_match(path, record.get("sha256"), errors, f"semantic {role}")
            if key == "original":
                _hash_match(path, case["source_sha256"], errors, "semantic original")
    if "generated_musicxml_sha256" in data:
        _hash_match(raw / "generated.musicxml", data["generated_musicxml_sha256"], errors, "semantic generated")


def _check_window(folder, window, case, errors, versions, godot):
    label = f"window {window['first_bar']}-{window['last_bar']}"
    required = (("fixture.json", "model"), ("score.musicxml", "generated"),
                ("independent-pixels.json", "independent_pixels"),
                ("independent-rests.json", "independent_rests"),
                ("capture-manifest.json", "capture_manifest"),
                ("native-overlay-report.json", "capture data"), ("audit.json", "window audit"),
                ("godot.log", "log"))
    present = {}
    for name, role in required:
        present[name] = _require(folder, name, role, errors, label)
    for suffix, role in (("svg", "reference_svg"), ("png", "reference_png")):
        names = list(folder.glob(f"verovio-*.{suffix}"))
        if not names:
            errors.append(f"{label}: missing required {role}")
        for path in names:
            _require(folder, path.name, role, errors, label)
            counterpart = path.with_suffix(".png" if suffix == "svg" else ".svg")
            _require(folder, counterpart.name, "paired reference", errors, label)
    fixture = _json(folder / "fixture.json", errors, f"{label} model")
    if (fixture.get("first_bar") != window["first_bar"] or fixture.get("last_bar") != window["last_bar"]
            or fixture.get("hand") != case["hand"] or not isinstance(fixture.get("model"), dict)
            or fixture["model"].get("active_hand") != case["hand"]):
        errors.append(f"{label}: model/window/hand identity mismatch")
    expected_frames = set()
    beats = fixture.get("sample_beats")
    if not isinstance(beats, list) or not beats:
        errors.append(f"{label}: missing native sample_beats capture schedule")
        beats = []
    for beat in beats:
        if type(beat) not in (int, float) or not math.isfinite(beat) or beat < 0:
            errors.append(f"{label}: invalid native capture beat")
        else:
            expected_frames.add(f"native-{beat:.5f}.png")
    witness = window.get("whole_window_coverage", {})
    audit = _json(folder / "audit.json", errors, f"{label} audit")
    source_label = f"{case['source']}, measures {window['first_bar']}-{window['last_bar']}, {case['hand']}"
    if audit.get("source") != source_label:
        errors.append(f"{label}: audit source/window/hand identity differs from pinned case")
    audit_witness = audit.get("whole_window_coverage")
    expected_witness = witness
    # audit_source attaches the canonical source ledger *after* run() writes
    # audit.json. Earlier capture-stage files may omit that later field; all
    # capture facts must still match exactly, and present ledgers must match.
    if isinstance(audit_witness, dict) and "elements" not in audit_witness and isinstance(witness, dict):
        expected_witness = {key: value for key, value in witness.items() if key != "elements"}
    if audit_witness != expected_witness:
        errors.append(f"{label}: raw audit witness differs from exact compact report window")
    count = witness.get("screenshot_count") if isinstance(witness, dict) else None
    if type(count) is not int or count != len(expected_frames):
        errors.append(f"{label}: native capture schedule disagrees with exact report screenshot_count")
    capture = _json(folder / "capture-manifest.json", errors, f"{label} capture_manifest")
    if capture.get("capture_protocol_sha256") != fixture.get("capture_protocol_sha256"):
        errors.append(f"{label}: capture protocol hash differs from fixture")
    for key in ("capture_protocol_sha256", "renderer_dependencies_sha256"):
        if not isinstance(capture.get(key), str) or not re.fullmatch("[0-9a-f]{64}", capture[key]):
            errors.append(f"{label}: missing/invalid {key}")
    if versions.get("error"):
        errors.append(f"{label}: {versions['error']}")
    if capture.get("renderer_dependencies_sha256") != versions.get("dependencies"):
        errors.append(f"{label}: capture differs from current renderer dependencies hash")
    if capture.get("capture_protocol_sha256") != versions.get("protocol"):
        errors.append(f"{label}: capture differs from current capture protocol hash")
    if not isinstance(godot, str) or not godot or capture.get("godot") != godot:
        errors.append(f"{label}: capture Godot version does not match report environment.godot")
    screenshots = capture.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots:
        errors.append(f"{label}: missing capture_manifest screenshots")
        screenshots = []
    captured = set()
    for row in screenshots:
        try:
            if not isinstance(row, dict):
                raise ValueError("malformed screenshot entry")
            name = row.get("file")
            if len(_relative(name).parts) != 1 or not name.endswith(".png"):
                raise ValueError("capture path must name a window PNG")
            if name in captured:
                errors.append(f"{label}: duplicate capture {name}")
            captured.add(name)
            path = _safe_file(folder, name)
            _hash_match(path, row.get("sha256"), errors, f"{label} capture {name}")
        except ValueError as exc:
            errors.append(f"{label}: native/control capture: {exc}")
    overlay = _json(folder / "native-overlay-report.json", errors, f"{label} capture data")
    frames = overlay.get("frames")
    if not isinstance(frames, list) or not frames:
        errors.append(f"{label}: missing native capture frames")
        frames = []
    if {row.get("file") for row in frames if isinstance(row, dict)} != expected_frames:
        errors.append(f"{label}: native frames disagree with expected capture schedule")
    referenced = set(expected_frames)
    for key, fields in (("rest_difference_controls", ("file",)),
                        ("rest_difference_frames", ("repeat_file", "restored_file"))):
        rows = overlay.get(key, [])
        if not isinstance(rows, list):
            errors.append(f"{label}: malformed {key}")
            continue
        for row in rows:
            for field in fields:
                name = row.get(field) if isinstance(row, dict) else None
                if isinstance(name, str):
                    referenced.add(name)
                else:
                    errors.append(f"{label}: missing {key}.{field}")
    actual_native = {p.name for p in folder.glob("native-*.png")}
    if actual_native != expected_frames:
        errors.append(f"{label}: native PNG set differs from expected window frames")
    for name in sorted(referenced):
        _require(folder, name, "native/control PNG", errors, label)
        if name not in captured:
            errors.append(f"{label}: capture_manifest missing hash for {name}")
    for name in ("independent-pixels.json", "independent-rests.json"):
        proof = _json(folder / name, errors, f"{label} {name}")
        key = "independent_image_pitch" if name == "independent-pixels.json" else "independent_image_rests"
        if isinstance(witness, dict) and key in witness:
            if {key: value for key, value in proof.items() if key != "measured"} != witness[key]:
                errors.append(f"{label}: {name} differs from exact compact report independent witness")
        rows = proof.get("measured")
        if not isinstance(rows, list) or not isinstance(proof.get("failures"), list):
            errors.append(f"{label}: malformed symbol rows/failures in {name}")
            continue
        expected_count = "written_active_noteheads" if name == "independent-pixels.json" else "written_active_rests"
        canonical = witness.get(key, {}) if isinstance(witness, dict) else {}
        if isinstance(canonical, dict) and expected_count in canonical:
            count = canonical[expected_count]
            if type(count) is not int or count < 0 or len(rows) != count:
                errors.append(f"{label}: symbol observation count in {name} differs from compact witness")
        statuses = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")
        counts = Counter(row.get("status") for row in rows if isinstance(row, dict)
                         and isinstance(row.get("status"), str))
        if any(not isinstance(row, dict) or row.get("status") not in statuses for row in rows):
            errors.append(f"{label}: invalid symbol observation status in {name}")
        coverage = canonical.get("coverage") if isinstance(canonical, dict) else None
        if isinstance(coverage, dict) and any(type(coverage.get(status)) is not int or
                coverage[status] != (len(rows) if status == "expected" else counts[status])
                for status in ("expected", *statuses)):
            errors.append(f"{label}: symbol observation statuses/counts in {name} differ from compact coverage")
        bindings = [json.dumps({field: row.get(field) for field in
                    ("source_id", "measure", "beat", "staff", "voice")}, sort_keys=True)
                    for row in rows if isinstance(row, dict)]
        if len(set(bindings)) != len(bindings):
            errors.append(f"{label}: duplicated symbol observation identity in {name}")
        observed = {json.dumps(row, sort_keys=True) for row in rows if isinstance(row, dict)}
        for element in window.get("visual_elements", []):
            evidence = element.get("evidence") if isinstance(element, dict) else None
            pixel = evidence.get("pixel") if isinstance(evidence, dict) else None
            if isinstance(pixel, dict) and bool("required_rest" in pixel) == (name == "independent-rests.json"):
                if json.dumps(pixel, sort_keys=True) not in observed:
                    errors.append(f"{label}: canonical pixel observation missing/changed in {name}")
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{label}: malformed symbol row in {name}")
                continue
            beat = row.get("beat")
            if type(beat) not in (int, float) or not math.isfinite(beat):
                errors.append(f"{label}: invalid symbol-to-frame beat in {name}")
            elif f"native-{beat:.5f}.png" not in expected_frames:
                errors.append(f"{label}: symbol frame outside expected window in {name}")
            delta = row.get("delta_file")
            if delta is not None and delta not in captured:
                errors.append(f"{label}: capture_manifest missing symbol delta hash {delta}")


def _check_visual(raw, data, case, errors, versions):
    scores = data.get("scores")
    if not isinstance(scores, list) or len(scores) != 1 or not isinstance(scores[0], dict):
        errors.append("visual: missing required single whole-score report/windows")
        return []
    score = scores[0]
    if score.get("piece") != case["source"] or score.get("hand") != case["hand"]:
        errors.append("visual: whole-score identity mismatch")
    windows = score.get("windows")
    if not isinstance(windows, list) or not windows:
        errors.append("visual: missing expected window list")
        return []
    folders = []
    seen = set()
    for window in windows:
        if (not isinstance(window, dict) or type(window.get("first_bar")) is not int
                or type(window.get("last_bar")) is not int
                or not 1 <= window["first_bar"] <= window["last_bar"]):
            errors.append("visual: malformed expected window identity")
            continue
        first, last = window["first_bar"], window["last_bar"]
        if (first, last) in seen:
            errors.append(f"visual: duplicate expected window {first}-{last}")
        seen.add((first, last))
        folder = raw / Path(case["source"]).stem / f"measures-{first:03}-{last:03}"
        folders.append(folder)
        if folder.is_symlink():
            errors.append(f"window {first}-{last}: symlink window forbidden")
            continue
        environment = data.get("environment")
        godot = environment.get("godot") if isinstance(environment, dict) else None
        _check_window(folder, window, case, errors, versions, godot)
    return folders


def _check_content(base, data, case, errors, versions):
    original = base / "original" / ("original" + Path(case["source"]).suffix)
    _hash_match(original, case["source_sha256"], errors, "packaged original hash")
    raw = base / "raw"
    if (raw / "summary.json").exists():
        _hash_match(raw / "summary.json", case["report_sha256"], errors, "raw/compact report digest")
    if case["verification_kind"] == "semantic":
        _check_semantic(raw, data, case, errors)
        return []
    return _check_visual(raw, data, case, errors, versions)


def _copy_file(source, target, out, case):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)  # Independent bytes, no mutable hardlinks/symlinks.
    relative = target.relative_to(out)
    within_case = target.relative_to(out / _case_dir(case["verification_kind"], case["source_index"], case["hand"]))
    case["files"].append(dict(path=relative.as_posix(), sha256=_digest(target), role=_entry_role(PurePosixPath(within_case.as_posix()))))


def _copy_tree(source, target, out, case):
    if not source.is_dir():
        return
    for path in sorted(source.rglob("*")):
        try:
            relative = path.relative_to(source)
            if path.is_symlink():
                raise ValueError(f"symlink raw evidence forbidden: {relative}")
            if path.is_dir():
                continue
            _safe_file(source, relative.as_posix())
            _copy_file(path, target / relative, out, case)
        except (OSError, ValueError) as exc:
            case["errors"].append(f"copy raw evidence: {exc}")


def _new_case(kind, index, source, hand):
    return dict(verification_kind=kind, source_index=index, source=source,
                source_sha256=None, hand=hand, report_sha256=None,
                complete=False, errors=[], files=[])


def package_evidence(reports_root, raw_root, out, revision) -> dict:
    """Retain all raw files and exact reports, returning the persisted manifest."""
    if not isinstance(revision, str) or not re.fullmatch("[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full lowercase 40-character Git SHA")
    reports, raw_root, out = (Path(p).resolve() for p in (reports_root, raw_root, out))
    for input_root in (reports, raw_root):
        if out == input_root or out in input_root.parents or input_root in out.parents:
            raise ValueError("output must not overlap input evidence trees")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("immutable evidence output must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    manifest = dict(schema_version=1, revision=revision, complete=False, errors=[], cases=[])
    versions = _capture_versions()
    diagnostic_candidates = []
    for kind, index, source, hand in _expected():
        case = _new_case(kind, index, source, hand)
        manifest["cases"].append(case)
        errors = case["errors"]
        source_file = _source_path(source)
        try:
            case["source_sha256"] = _digest(source_file)
        except OSError as exc:
            errors.append(f"unreadable pinned original: {exc}")
        report = _report_path(reports, kind, index, hand)
        data = _json(report, errors, "required compact report")
        try:
            case["report_sha256"] = _digest(report)
        except OSError:
            pass
        _identity(data, case, errors)
        base = out / _case_dir(kind, index, hand)
        if report.is_file():
            _copy_file(report, base / "report/summary.json", out, case)
            if source_file.is_file():
                _copy_file(source_file, base / "original" / ("original" + source_file.suffix), out, case)
        prefix = "phase3-semantic-report" if kind == "semantic" else "phase3-report"
        candidates = [raw_root / f"{prefix}-{index}-{hand}"]
        if kind == "visual":
            candidates.insert(0, raw_root / f"phase3-visual-score-{index}-{hand}")
        candidates = list(dict.fromkeys(p.resolve() for p in candidates if p.is_dir()))
        if len(candidates) > 1:
            errors.append("ambiguous raw case roots; cannot substitute unrelated windows")
        full = candidates[0] if candidates else report.parent.resolve()
        _copy_tree(full, base / "raw", out, case)
        for alternative in candidates[1:]:
            _copy_tree(alternative, base / "compact" / alternative.name, out, case)
        if report.parent.resolve() != full:
            # Compact roots can contain additional context, not just summary.
            _copy_tree(report.parent.resolve(), base / "compact", out, case)
        try:
            folders = _check_content(base, data, case, errors, versions)
            for folder in folders:
                states = set()
                for name in ("independent-pixels.json", "independent-rests.json"):
                    try:
                        proof = _load(folder / name)
                        states.update((name, row.get("status")) for row in proof.get("measured", [])
                                      if isinstance(row, dict) and row.get("status") != "verified")
                    except (OSError, ValueError, AttributeError):
                        pass
                if states:
                    diagnostic_candidates.append((case, folder, states))
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            errors.append(f"malformed required evidence: {type(exc).__name__}: {exc}")
    # Prefer diverse nonverified families/statuses, then distinct scores/hands.
    represented, chosen_cases = set(), set()
    for _ in range(min(8, len(diagnostic_candidates))):
        position = max(range(len(diagnostic_candidates)), key=lambda i: (
            len(diagnostic_candidates[i][2] - represented),
            (diagnostic_candidates[i][0]["source_index"], diagnostic_candidates[i][0]["hand"]) not in chosen_cases))
        case, folder, states = diagnostic_candidates.pop(position)
        represented.update(states)
        chosen_cases.add((case["source_index"], case["hand"]))
        base = out / _case_dir(case["verification_kind"], case["source_index"], case["hand"])
        diagnostic_out = base / "diagnostics" / folder.name
        try:
            from piano_teacher.notation.release_diagnostics import create_diagnostics
            create_diagnostics(folder, diagnostic_out, hand=case["hand"], limit=3)
            for path in sorted(diagnostic_out.iterdir()):
                case["files"].append(dict(path=path.relative_to(out).as_posix(), sha256=_digest(path),
                                          role="glyph_reference" if path.suffix == ".svg" else "diagnostic"))
        except (ImportError, OSError, ValueError, TypeError, KeyError) as exc:
            case["errors"].append(f"required symbol diagnostics unavailable: {exc}")
    for case in manifest["cases"]:
        case["files"].sort(key=lambda row: row["path"])
        case["complete"] = not case["errors"]
        manifest["errors"].extend(f"{case['verification_kind']} {case['source_index']}/{case['hand']}: {error}" for error in case["errors"])
    manifest["complete"] = not manifest["errors"]
    (out / "evidence-manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def validate_manifest(manifest_path, reports_root, revision) -> dict:
    """Recompute artifact completeness; stored success flags provide no credit."""
    manifest_path, reports = Path(manifest_path), Path(reports_root)
    errors = []
    versions = _capture_versions()
    manifest = _json(manifest_path, errors, "evidence manifest")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        errors.append("missing/unsupported evidence schema_version")
    if (not isinstance(revision, str) or not re.fullmatch("[0-9a-f]{40}", revision)
            or manifest.get("revision") != revision):
        errors.append("evidence packaging revision mismatch/invalid full SHA")
    rows = manifest.get("cases")
    if not isinstance(rows, list):
        rows = []
        errors.append("manifest cases must be a list")
    by_key = {}
    expected_keys = {(kind, index, hand) for kind, index, _, hand in _expected()}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("source_index")) is not int:
            errors.append("malformed manifest case identity")
            continue
        key = row.get("verification_kind"), row["source_index"], row.get("hand")
        try:
            if key not in expected_keys:
                errors.append(f"unexpected manifest case identity: {key}")
            by_key.setdefault(key, []).append(row)
        except TypeError:
            errors.append("malformed manifest kind/hand")
    cases = []
    out = manifest_path.parent.resolve()
    for kind, index, source, hand in _expected():
        case = _new_case(kind, index, source, hand)
        cases.append(case)
        issues = case["errors"]
        matches = by_key.get((kind, index, hand), [])
        if len(matches) != 1:
            issues.append("duplicate manifest case" if matches else "missing required manifest case")
        supplied = matches[0] if matches else {}
        if supplied.get("source") != source:
            issues.append("manifest source identity mismatch")
        try:
            case["source_sha256"] = _digest(_source_path(source))
        except OSError as exc:
            issues.append(f"unreadable actual pinned original: {exc}")
        if supplied.get("source_sha256") != case["source_sha256"]:
            issues.append("manifest original source_sha256 mismatch")
        report = _report_path(reports, kind, index, hand)
        data = _json(report, issues, "required compact report")
        try:
            case["report_sha256"] = _digest(report)
        except OSError:
            pass
        if case["report_sha256"] is None or supplied.get("report_sha256") != case["report_sha256"]:
            issues.append("exact compact report digest mismatch/missing")
        _identity(data, case, issues)
        base_relative = _case_dir(kind, index, hand)
        base = out / base_relative
        files = supplied.get("files")
        if not isinstance(files, list) or not files:
            issues.append("missing required packaged files")
            files = []
        indexed = set()
        for entry in files:
            try:
                if not isinstance(entry, dict):
                    raise ValueError("file entry must be an object")
                path = _relative(entry.get("path"))
                relative = path.relative_to(PurePosixPath(base_relative.as_posix()))
                if path.as_posix() in indexed:
                    raise ValueError(f"duplicate indexed file: {path}")
                indexed.add(path.as_posix())
                expected_role = _entry_role(relative)
                if entry.get("role") != expected_role:
                    raise ValueError(f"wrong role for {path}: expected {expected_role}")
                actual = _safe_file(out, path.as_posix())
                _hash_match(actual, entry.get("sha256"), issues, f"packaged {path}")
            except (OSError, ValueError, IndexError) as exc:
                issues.append(f"invalid packaged file: {exc}")
        case["files"] = files
        actual_paths = {p.relative_to(out).as_posix() for p in base.rglob("*") if p.is_file() or p.is_symlink()}
        if actual_paths != indexed:
            issues.append("packaged file inventory differs from manifest (missing/unindexed files)")
        _hash_match(base / "report/summary.json", case["report_sha256"], issues, "packaged exact report digest")
        try:
            _check_content(base, data, case, issues, versions)
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            issues.append(f"malformed packaged evidence: {type(exc).__name__}: {exc}")
        # Copy failures or ambiguity discovered at packaging cannot be promoted
        # merely because the surviving subset happens to satisfy file classes.
        if isinstance(supplied.get("errors"), list):
            issues.extend(e for e in supplied["errors"] if isinstance(e, str) and e not in issues)
        case["complete"] = not issues
        errors.extend(f"{kind} {index}/{hand}: {issue}" for issue in issues)
    return dict(complete=not errors, errors=errors, cases=cases)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", required=True, type=Path)
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        result = package_evidence(args.reports, args.raw, args.out, args.revision)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps({"manifest": str(args.out / "evidence-manifest.json"),
                      "complete": result["complete"], "cases": len(result["cases"]),
                      "errors": len(result["errors"])}))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
