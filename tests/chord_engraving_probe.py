"""G1 chord probe: push adversarial chords through a user's import path.

Each fixture file goes through import_piece -> ScoreArtifacts (lesson XML,
Verovio page engraving, native asset preparation) exactly as the app prepares
a selected exercise, then through the production Godot native view. Every
chord is classified:

- drawn:   the native view painted every head, each where Verovio put it;
- refused: the score did not load, or a head was not painted;
- wrong:   painted, but a head's displacement, or the stem's side, centre
           line or tip, differs from Verovio's own SVG render of the same
           measure (relative to the chord's leader head, in staff spaces).

Not a test module: tests/test_chord_engraving_probe.py drives it.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "g1_chords"
LAYOUT_KEYS = ("native_glyphs", "native_note_templates", "native_tie_templates",
               "native_chord_templates", "native_beam_fragments",
               "native_tuplet_fragments", "native_slur_fragments",
               "native_required_slur_pairs", "native_slurs_complete",
               "native_required_beam_groups", "native_beams_complete")
TOLERANCE = .2  # staff spaces
STEM_SIDE = .15  # staff spaces, stem centre line from the leader's head centre
STEM_TIP = .3    # staff spaces, the stem's far end


def _verovio_heads(pages) -> dict:
    """Note id -> (x, y, staff space) in the page's own viewBox units."""
    from piano_teacher.source_svg import parse_svg_geometry
    found = {}
    for page in pages:
        geometry = parse_svg_geometry(page)
        for ident, (x, y, system) in geometry.elements.items():
            lines = geometry.staff_systems.get(system, {}).get("staff_lines", [])
            gaps = [b - a for a, b in zip(lines, lines[1:]) if b - a > 1e-7]
            if gaps:
                found[ident] = (x * geometry.width, y * geometry.height,
                                min(gaps) * geometry.height)
    return found


_NUMBER = r"-?\d+(?:\.\d+)?"


def _verovio_stems(pages) -> dict:
    """Note id -> its chord's Verovio stem relative to that note's head, in
    staff spaces: up, centre-line dx from the head centre, far end (tip)."""
    import re
    import xml.etree.ElementTree as ET
    from piano_teacher.notation.assets.glyphs import native_glyphs

    def classes(node):
        return set(node.get("class", "").split())

    glyphs = native_glyphs()
    found = {}
    for page in pages:
        root = ET.fromstring(page)
        parents = {child: parent for parent in root.iter() for child in parent}
        for chord in root.iter():
            if "chord" not in classes(chord) or classes(chord) & {"bounding-box", "content-bounding-box"}:
                continue
            staff = parents.get(chord)
            while staff is not None and "staff" not in classes(staff):
                staff = parents.get(staff)
            lines = sorted(float(m.group(2)) for item in (staff if staff is not None else [])
                           if (m := re.fullmatch(r"\s*M\s*(%s)[,\s]+(%s)\s*L.*" % (_NUMBER, _NUMBER),
                                                 item.get("d", "") or "")))
            gaps = [b - a for a, b in zip(lines, lines[1:]) if b - a > 1e-6]
            stem = None
            heads = {}
            for node in chord.iter():
                if classes(node) & {"bounding-box", "content-bounding-box"}:
                    continue
                if "stem" in classes(node) and stem is None:
                    for path in node.iter():
                        m = re.fullmatch(r"\s*M\s*(%s)[,\s]+(%s)\s*L\s*(%s)[,\s]+(%s)\s*"
                                         % ((_NUMBER,) * 4), path.get("d", "") or "")
                        if m:
                            stem = (float(m.group(1)), float(m.group(2)), float(m.group(4)))
                            break
                if "note" in classes(node) and node.get("id"):
                    use = next((u for u in node.iter() if u.tag.endswith("use")), None)
                    move = re.search(r"translate\(\s*(%s)[,\s]+(%s)" % (_NUMBER, _NUMBER),
                                     use.get("transform", "")) if use is not None else None
                    if move:
                        heads[node.get("id")] = (float(move.group(1)), float(move.group(2)))
            if stem is None or not gaps or not heads:
                continue
            space = min(gaps)
            ys = [y for _, y in heads.values()]
            up = min(ys) - min(stem[1:]) > max(stem[1:]) - max(ys)
            tip = min(stem[1:]) if up else max(stem[1:])
            for ident, (x, y) in heads.items():
                found[ident] = {"up": up, "x": stem[0], "tip": tip, "head": (x, y),
                                "space": space}
    return found


def model_chords(model: dict) -> list[dict]:
    """Every multi-head attack, grouped like the native view's chord_members."""
    lanes = defaultdict(list)
    for event in model["notation_events"]:
        if event.get("kind") == "note":
            lanes[(event["staff"], str(event.get("voice", "1")), int(event["measure"]),
                   round(float(event["beat"]), 6))].append(event)
    starts = {int(m["number"]): float(m["start_beat"]) for m in model["measures"]}
    result = []
    for (staff, voice, measure, beat), notes in lanes.items():
        leaders = [n for n in notes if not n.get("chord")]
        if len(notes) < 2 or len(leaders) != 1:
            continue
        result.append({"leader": leaders[0]["id"], "beat": beat, "staff": staff,
                       "kind": leaders[0].get("note_type", ""),
                       "voice": voice, "measure": measure,
                       "bar_beat": round(beat - starts[measure], 6),
                       "members": [n["id"] for n in notes],
                       "names": [_name(n["spelling"]) for n in notes],
                       "pitches": [n.get("midi_pitch") for n in notes]})
    return sorted(result, key=lambda c: (c["beat"], c["staff"], c["voice"]))


def _name(spelling: dict) -> str:
    accidental = {-2: "bb", -1: "b", 0: "", 1: "#", 2: "x"}[int(spelling.get("alter") or 0)]
    return f"{spelling['step']}{accidental}{spelling['octave']}"


def prepare(path: Path, cache: Path) -> list[dict]:
    """One native-view item per imported exercise phrase of a fixture file."""
    from piano_teacher.application.score_artifacts import ScoreArtifacts, ScoreSelection
    from piano_teacher.importing.pieces import import_piece
    from piano_teacher.preprocessing_cache import PreprocessingCache

    piece, _ = import_piece(path)
    artifacts = ScoreArtifacts(PreprocessingCache(cache))
    items = []
    for phrase in piece.phrases:
        selected = ScoreSelection(piece, phrase, "both", "g1-chord-probe", 1, path.name)
        layout = artifacts.geometry(selected)
        model = artifacts.semantic_score(selected)
        pages = artifacts.engraving(selected).pages
        heads = _verovio_heads(pages)
        stems = _verovio_stems(pages)
        chords = model_chords(model)
        for chord in chords:
            lx, ly, space = heads.get(chord["leader"], (0.0, 0.0, 0.0))
            chord["verovio"] = {
                ident: [(heads[ident][0] - lx) / space, (heads[ident][1] - ly) / space]
                for ident in chord["members"] if ident in heads and space > 0}
            stem = stems.get(chord["leader"])
            if stem is not None:
                from piano_teacher.notation.assets.glyphs import native_glyphs
                kind = chord["kind"]
                box = native_glyphs()["head_" + (kind if kind in {"whole", "half"} else "black")]["bounds"]
                # Verovio places a head by its glyph origin (left edge); the
                # native view by its centre. The Leipzig box has 12 units of
                # padding on each side at 250 units per space.
                half = (box[2] * .5 - 12) / 250
                hx, hy = stem["head"]
                chord["verovio_stem"] = {"up": stem["up"],
                                         "dx": (stem["x"] - hx) / stem["space"] - half,
                                         "tip": (stem["tip"] - hy) / stem["space"]}
        items.append({"name": f"{path.name}-bars{phrase.first_bar}-{phrase.last_bar}",
                      "source": path.name, "first_bar": phrase.first_bar,
                      "layout": {key: layout[key] for key in LAYOUT_KEYS},
                      "model": model, "chords": chords, "pages": list(pages)})
    return items


def run_godot(items: list[dict], work: Path, capture: Path | None = None,
              env: dict | None = None) -> list[dict]:
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        raise RuntimeError("Godot 4 unavailable")
    payload = [{key: item[key] for key in ("name", "layout", "model", "chords")}
               for item in items]
    source, output = work / "probe-input.json", work / "probe-output.json"
    source.write_text(json.dumps(payload))
    command = [binary, "--path", str(ROOT / "godot")]
    if capture is None:
        command.append("--headless")
    else:
        command += ["--rendering-method", "gl_compatibility"]
    command += ["--script", str(ROOT / "tests/godot/chord_engraving_probe.gd"), "--",
                str(source), str(output)] + ([str(capture)] if capture else [])
    proc = subprocess.run(command, capture_output=True, text=True, timeout=600,
                          env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
                               **(env or {})})
    log = proc.stdout + proc.stderr
    (work / "godot.log").write_text(log)
    if proc.returncode != 0 or "SCRIPT ERROR" in log or "Parse Error" in log:
        raise RuntimeError(log[-4000:])
    return json.loads(output.read_text())


def classify(items: list[dict], results: list[dict]) -> list[dict]:
    """One row per chord: outcome, template key and the offending heads."""
    by_name = {r["name"]: r for r in results}
    rows = []
    for item in items:
        result = by_name[item["name"]]
        for chord in item["chords"]:
            row = {key: chord[key] for key in ("leader", "staff", "voice", "measure",
                                               "bar_beat", "names", "pitches")}
            row["source"] = item["source"]
            drawn = result["chords"].get(chord["leader"]) if result["ready"] else None
            if drawn is None:
                row.update(outcome="refused", detail=result["failure"] or "not drawn", key="")
                rows.append(row)
                continue
            row.update(key=drawn["key"], png=drawn.get("png", ""), gap=float(drawn["gap"]),
                       members=chord["members"], native=drawn["heads"],
                       verovio=chord["verovio"], kind=chord.get("kind", ""))
            missing = [i for i in chord["members"] if i not in drawn["heads"]]
            if missing:
                row.update(outcome="refused", detail=f"{len(missing)} heads not painted")
                rows.append(row)
                continue
            gap = float(drawn["gap"])
            lx, ly = drawn["heads"][chord["leader"]]
            errors = []
            for ident in chord["members"]:
                x, y = drawn["heads"][ident]
                native = ((x - lx) / gap, (y - ly) / gap)
                expected = chord["verovio"].get(ident)
                if expected is None:
                    errors.append(f"{ident}: no Verovio head")
                    continue
                if max(abs(native[0] - expected[0]), abs(native[1] - expected[1])) > TOLERANCE:
                    errors.append("%s native (%.2f,%.2f) Verovio (%.2f,%.2f)" % (
                        row["names"][chord["members"].index(ident)], *native, *expected))
            expected_stem, native_stem = chord.get("verovio_stem"), drawn.get("stem") or {}
            row.update(verovio_stem=expected_stem, native_stem=native_stem)
            if expected_stem is not None:
                if not native_stem or native_stem.get("missing"):
                    errors.append("stem not painted")
                elif native_stem["up"] != expected_stem["up"]:
                    errors.append("stem %s, Verovio %s" % (
                        "up" if native_stem["up"] else "down", "up" if expected_stem["up"] else "down"))
                elif (abs(native_stem["dx"] - expected_stem["dx"]) > STEM_SIDE
                      or abs(native_stem["tip"] - expected_stem["tip"]) > STEM_TIP):
                    errors.append("stem native dx %.2f tip %.2f, Verovio dx %.2f tip %.2f" % (
                        native_stem["dx"], native_stem["tip"], expected_stem["dx"], expected_stem["tip"]))
            elif native_stem and row.get("kind") != "whole":
                errors.append("stem painted where Verovio has none")
            row.update(outcome="wrong" if errors else "drawn", detail="; ".join(errors))
            rows.append(row)
    return rows


def case_of(row: dict, manifest: dict) -> str:
    for case in manifest[row["source"]]:
        if case["measure"] != row["measure"]:
            continue
        if row["source"].endswith(".mid"):
            if row["bar_beat"] in case["beats"] and set(row["pitches"]) <= set(case["pitches"]):
                return case["case"]
        elif abs(row["bar_beat"] - case["beat"]) < 1e-6:
            return case["case"]
    return "?"


def _finger(item: dict, chord: dict) -> None:
    """Give each head of a chord an automatic fingering of its own hand."""
    events = {e["id"]: e for e in item["model"]["notation_events"]}
    for finger, ident in enumerate(chord["members"], 1):
        event = events[ident]
        event["fingering"] = {"finger": min(finger, 5), "hand": event.get("hand", event["staff"]),
                              "source_id": event.get("source_id") or ident, "origin": "automatic"}


def probe(capture: Path | None = None, work: Path | None = None,
          capture_cases: set[str] | None = None,
          fingering_cases: set[str] = frozenset()) -> tuple[list[dict], list[dict]]:
    """Prepare every fixture exercise, draw it natively, classify each chord.

    With ``capture``, a real viewport saves one PNG per chord of
    ``capture_cases`` (all chords when None) and only those exercises run.
    Chords of ``fingering_cases`` get a fingering on every head.
    """
    work = work or Path(tempfile.mkdtemp(prefix="g1-chord-probe-"))
    manifest = json.loads((FIXTURES / "cases.json").read_text())
    items = []
    for name in ("g1_chords.mid", "g1_chords.musicxml"):
        items += prepare(FIXTURES / name, work / "cache")
    for item in items:
        for chord in item["chords"]:
            chord["case"] = case_of({**chord, "source": item["source"]}, manifest)
            if chord["case"] in fingering_cases:
                _finger(item, chord)
            chord["capture"] = capture is not None and (
                capture_cases is None or chord["case"] in capture_cases)
    if capture is not None:
        items = [item for item in items if any(c["capture"] for c in item["chords"])]
    results = run_godot(items, work, capture)
    rows = classify(items, results)
    for row in rows:
        row["case"] = case_of(row, manifest)
    return items, rows


if __name__ == "__main__":
    import sys
    capture = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if capture:
        capture.mkdir(parents=True, exist_ok=True)
    _, rows = probe(capture)
    for row in rows:
        print(f"{row['outcome']:8} {row['case']:32} m{row['measure']:<3} {row['staff']:5} "
              f"v{row['voice']} {' '.join(row['names']):40} {row['key']:28} {row['detail']}")
