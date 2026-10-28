"""Bounded derived illustrations of Phase3's independent symbol observations.

Never a verifier: original statuses are retained even when a new alignment has
a strong match. Expectations come from independently read MusicXML and authentic
external Leipzig SVGs, not fixture atlases or renderer geometry. Full original
PNGs/JSON remain the evidence; crops/overlays/deltas are explicitly derived.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path


def _hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _file(folder, name):
    if not isinstance(name, str) or Path(name).name != name or name in (".", ".."):
        raise ValueError("diagnostic input must be a file in the same window")
    path = folder / name
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"missing/unsafe diagnostic input: {name}")
    return path


def _mask(glyph, gap):
    import cairosvg
    import numpy as np
    from PIL import Image

    bounds = glyph["bounds"]
    width, height = max(1, round(bounds[2]*gap/250)), max(1, round(bounds[3]*gap/250))
    png = cairosvg.svg2png(bytestring=glyph["svg"].encode(), output_width=width, output_height=height)
    return np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:, :, 3] > 96


def _register(observed, template, x, y, dxs, dys):
    """Descriptive bounded registration; its score grants no verification."""
    import numpy as np

    height, width = template.shape
    best = None
    for dx in dxs:
        left = round(x + dx)
        for dy in dys:
            top = round(y + dy)
            if min(left, top) < 0 or left+width > observed.shape[1] or top+height > observed.shape[0]:
                continue
            block = observed[top:top+height, left:left+width]
            score = 2*int(np.count_nonzero(block & template))/(int(block.sum())+int(template.sum())+1e-9)
            if best is None or score > best[0]:
                best = score, left, top
    if best is None:
        raise ValueError("authentic glyph search lies outside image")
    return best


def _images(output, stem, native, observed, template, left, top):
    import numpy as np
    from PIL import Image

    height, width = template.shape
    # A bounded contextual crop; never rescale a glyph to force agreement.
    x0, y0 = max(0, left-12), max(0, top-12)
    x1, y1 = min(native.width, left+width+12), min(native.height, top+height+12)
    source = np.asarray(native)[y0:y1, x0:x1].copy()
    expected = np.zeros((y1-y0, x1-x0), dtype=bool)
    expected[top-y0:top-y0+height, left-x0:left-x0+width] = template
    actual = observed[y0:y1, x0:x1]
    overlay = source.copy()
    overlay[expected] = (255, 100, 220)
    difference = np.zeros_like(source)
    difference[actual & ~expected] = (255, 80, 70)
    difference[expected & ~actual] = (60, 210, 255)
    difference[actual & expected] = (240, 240, 240)
    names = {"crop": f"{stem}-native-crop.png", "overlay": f"{stem}-overlay.png", "delta": f"{stem}-delta.png"}
    for key, array in (("crop", source), ("overlay", overlay), ("delta", difference)):
        Image.fromarray(array).save(output / names[key])
    return names


def create_diagnostics(folder, output, *, hand="both", limit=3) -> dict:
    """Keep all measured rows; illustrate at most ``limit`` nonverified symbols.

    Failure to isolate a source glyph yields an explicit unverified diagnostic,
    never a fabricated mask. Font dependencies are loaded only for exemplars.
    """
    folder, output = Path(folder), Path(output)
    if hand not in ("both", "right", "left") or type(limit) is not int or limit < 0:
        raise ValueError("invalid diagnostic hand/limit")
    output.mkdir(parents=True, exist_ok=True)
    symbols, failures, inputs = [], [], {}
    for kind, name in (("notehead", "independent-pixels.json"), ("rest", "independent-rests.json")):
        path = _file(folder, name)
        data = json.loads(path.read_text())
        inputs[name] = _hash(path)
        symbols.extend({**row, "kind": kind} for row in data.get("measured", []) if isinstance(row, dict))
        failures.extend({"kind": kind, "failure": value} for value in data.get("failures", []))
    priority = {"mismatch": 0, "ambiguous": 1, "unverified": 2, "unsupported": 3}
    candidates = sorted((row for row in symbols if row.get("status") != "verified"
                         and (hand == "both" or row.get("staff") == hand)),
                        key=lambda row: (priority.get(row.get("status"), 4), row["kind"], str(row.get("source_id"))))
    result = dict(schema_version=1, derived=True, verification_evidence=False,
                  scope="Authentic external glyph registration and symbol-level image differences; descriptive only",
                  limitations=["Derived images cannot certify notation or override source statuses",
                               "Adjacent ink may be reused; no joint dense-symbol assignment is established",
                               "Rest contours cannot establish dots, placement or half/whole value identity"],
                  delta_legend={"white": "intersection", "red": "observed only", "cyan": "authentic glyph only"},
                  inputs_sha256=inputs, symbols=symbols, failures=failures, exemplars=[])
    selected, represented = [], set()
    while candidates and len(selected) < limit:
        position = next((i for i, row in enumerate(candidates)
                         if (row["kind"], row.get("status")) not in represented), 0)
        row = candidates.pop(position)
        represented.add((row["kind"], row.get("status")))
        selected.append(row)
    for index, row in enumerate(selected):
        exemplar = dict(kind=row["kind"], source_id=row.get("source_id"), source_status=row.get("status"),
                        diagnostic_status="unverified", derived=True, verification_evidence=False)
        result["exemplars"].append(exemplar)
        try:
            import numpy as np
            from PIL import Image
            from .pixel_proof import detect_staff_lines, expected_y
            from .proof import read_written_score
            from .reference_font import reference_glyphs
            from .pixel_ink import bright

            beat = float(row["beat"])
            native_name = f"native-{beat:.5f}.png"
            native_path = _file(folder, native_name)
            with Image.open(native_path) as image:
                native = image.convert("RGB")
            exemplar.update(native=native_name, native_sha256=_hash(native_path))
            staves = detect_staff_lines(native)
            staff = staves[row["staff"]]
            xml = _file(folder, "score.musicxml")
            written = read_written_score(xml.read_text())
            result["inputs_sha256"]["score.musicxml"] = _hash(xml)
            events = [event for event in written.symbols
                      if event["kind"] == ("note" if row["kind"] == "notehead" else "rest")
                      and abs(float(event["beat"])-beat) < 1e-7 and event["staff"] == row["staff"]
                      and event["voice"] == row["voice"]]
            exact = [event for event in events if event.get("id") == row.get("source_id")]
            if len(exact) == 1:
                event = exact[0]
            elif len(events) == 1:
                event = events[0]
            else:
                raise ValueError("ambiguous source-to-symbol diagnostic binding")
            if row["kind"] == "notehead":
                name = "head_whole" if event["note_type"] == "whole" else "head_half" if event["note_type"] == "half" else "head_black"
            else:
                name = "rest_" + event["note_type"]
            glyph = reference_glyphs().get(name)
            if glyph is None:
                raise ValueError(f"authentic external font lacks {name}")
            stem = f"symbol-{index:02}-{row['kind']}"
            reference_name = stem + "-reference.svg"
            (output / reference_name).write_text(glyph["svg"])
            exemplar.update(reference=reference_name, reference_sha256=_hash(output / reference_name),
                            font=glyph["font"], codepoint=glyph["code"], glyph=name, staff_gap=staff.gap)
            template = _mask(glyph, staff.gap)
            if row["kind"] == "notehead":
                choices = [(at, sign, line, octave) for at, which, sign, line, octave in written.clefs
                           if which == row["staff"] and at <= event["index"]]
                if not choices:
                    raise ValueError("no independently written clef")
                _, sign, line, octave = max(choices)
                target = expected_y(staff, event["spelling"], (sign, line, octave))
                observed = bright(native)
                score, left, top = _register(observed, template,
                    native.width*.42-template.shape[1]/2, target+glyph["bounds"][1]*staff.gap/250,
                    range(-32, 33), range(-4, 5))
            else:
                overlay = json.loads(_file(folder, "native-overlay-report.json").read_text())
                controls = [frame for frame in overlay.get("rest_difference_frames", [])
                            if abs(float(frame["clock"])-beat) < 1e-7]
                if overlay.get("rest_difference_protocol") != 2 or len(controls) != 1:
                    raise ValueError("unverified full-frame repeat/restore controls")
                arrays = []
                for field in ("repeat_file", "restored_file"):
                    path = _file(folder, controls[0][field])
                    with Image.open(path) as image:
                        arrays.append(np.asarray(image.convert("RGB")))
                    exemplar[field+"_sha256"] = _hash(path)
                original = np.asarray(native)
                if not all(np.array_equal(original, array) for array in arrays):
                    raise ValueError("repeat/restored frames drifted")
                path = _file(folder, row.get("delta_file"))
                with Image.open(path) as image:
                    suppressed = image.convert("RGB")
                other = np.asarray(suppressed)
                if original.shape != other.shape:
                    raise ValueError("suppressed frame changed dimensions")
                delta = np.max(np.abs(original.astype('int16')-other.astype('int16')), axis=2) >= 10
                observed = delta & bright(native) & ~bright(suppressed)
                ys, xs = np.nonzero(observed)
                if len(xs) < 12 or np.any(delta & bright(suppressed) & ~bright(native)):
                    raise ValueError("control did not exclusively remove visible original ink")
                changed_y, changed_x = np.nonzero(delta)
                if (changed_x.min() < native.width*.42-80 or changed_x.max() >= native.width*.42+80
                        or changed_x.max()-changed_x.min() > staff.gap*4 or changed_y.max()-changed_y.min() > staff.gap*9):
                    raise ValueError("uncontrolled rest intervention outside bounded onset region")
                exemplar.update(control=row["delta_file"], control_sha256=_hash(path))
                ry, rx = np.nonzero(template)
                score, left, top = _register(observed, template, xs.min()-rx.min(), ys.min()-ry.min(), range(-2, 3), range(-2, 3))
            exemplar.update(_images(output, stem, native, observed, template, left, top))
            exemplar.update(diagnostic_status="available", descriptive_dice=round(score, 4),
                            registration=[left, top], changed_pixels=int(np.count_nonzero(observed)))
        except (ImportError, OSError, ValueError, AssertionError, KeyError, TypeError, IndexError) as exc:
            exemplar["reason"] = f"{type(exc).__name__}: {exc}"
    (output / "diagnostics.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result
