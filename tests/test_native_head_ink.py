"""Bounded head-count and absent-flag probes on fresh native framebuffers.

No reference fixtures are rewritten. PracticeEngine prepares the authentic
atlas, and a real GL viewport renders the production native view. Mutations
change actual captured ink without changing the source MusicXML expectations.
"""
from copy import deepcopy
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess

from PIL import Image
import pytest

from piano_teacher.notation.pixel_proof import detect_staff_lines, expected_y
from piano_teacher.notation.raster_matching import _joint_candidates
from piano_teacher.notation.reference_font import reference_glyphs
from piano_teacher.notation.symbol_pixel_proof import bright
from piano_teacher.server import PracticeEngine

ROOT = Path(__file__).resolve().parents[1]


def _score(kind, *, down=False, voices=False):
    def note(step, octave, voice="1", chord=False):
        duration = 2 if kind == "eighth" else 4
        return (f'<note>{"<chord/>" if chord else ""}<pitch><step>{step}</step>'
                f'<octave>{octave}</octave></pitch><duration>{duration}</duration>'
                f'<voice>{voice}</voice><type>{kind}</type></note>')

    def rest(voice="1"):
        duration, dots = (14, "<dot/><dot/>") if kind == "eighth" else (12, "<dot/>")
        return (f'<note><rest/><duration>{duration}</duration><voice>{voice}</voice>'
                f'<type>half</type>{dots}</note>')

    notes = note("D", 5) if down else note("E", 4)
    if voices:
        notes += note("G", 4, chord=True)
    notes += rest()
    if voices:
        notes += '<backup><duration>16</duration></backup>' + note("D", 5, "2") + rest("2")
    return ('<score-partwise version="4.0"><part-list>'
            '<score-part id="RH"><part-name>Right Hand</part-name></score-part>'
            '<score-part id="LH"><part-name>Left Hand</part-name></score-part>'
            '</part-list><part id="RH"><measure number="1">'
            '<attributes><divisions>4</divisions><key><fifths>0</fifths></key>'
            '<time><beats>4</beats><beat-type>4</beat-type></time>'
            '<clef><sign>G</sign><line>2</line></clef></attributes>' + notes +
            '</measure></part><part id="LH"><measure number="1">'
            '<attributes><divisions>4</divisions><time><beats>4</beats><beat-type>4</beat-type>'
            '</time><clef><sign>F</sign><line>4</line></clef></attributes>'
            '<note><rest measure="yes"/><duration>16</duration><type>whole</type></note>'
            '</measure></part></score-partwise>')


@pytest.fixture(scope="module")
def captures(tmp_path_factory):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not os.environ.get("DISPLAY"):
        pytest.skip("Real native framebuffer checks require Godot 4 and DISPLAY")
    folder = tmp_path_factory.mktemp("native-head-ink")
    engine = PracticeEngine(folder / "cache", enable_midi=False)
    payloads, sources = [], {}
    try:
        for name, kind, down, voices in (
                ("quarter-up", "quarter", False, False),
                ("quarter-down", "quarter", True, False),
                ("quarter-voices", "quarter", False, True),
                ("eighth-up", "eighth", False, False),
                ("eighth-down", "eighth", True, False)):
            xml = _score(kind, down=down, voices=voices)
            source = folder / f"{name}.musicxml"
            source.write_text(xml)
            engine.load(str(source))
            engine.plan.restore_location(kind="learn", first_bar=1, last_bar=1,
                                         hand="right", level="original")
            baseline = {"model": engine.semantic_score(),
                        "layout": engine.geometry(native_notes=True)}
            assert sum(e["kind"] == "note" for e in baseline["model"]["notation_events"]) == (3 if voices else 1)
            mutations = ["baseline", "extra-head", "missing-head"]
            if not voices:
                mutations += ["wrong-flag"]
            for mutation in mutations:
                item = deepcopy(baseline)
                item["name"] = f"{name}-{mutation}"
                item["extra_head"] = mutation == "extra-head"
                templates = item["layout"]["native_note_templates"]
                if mutation == "wrong-flag":
                    other = "eighth" if kind == "quarter" else "quarter"
                    for direction in ("up", "down"):
                        templates[f"{kind}_{direction}"] = deepcopy(templates[f"{other}_{direction}"])
                elif mutation == "missing-head":
                    if voices:
                        # Delete one visible chord tone without changing source expectations.
                        events = item["model"]["notation_events"]
                        events[:] = [e for e in events if not e.get("chord", False)]
                    else:
                        for direction in ("up", "down"):
                            entry = templates[f"{kind}_{direction}"]
                            image = Image.open(BytesIO(base64.b64decode(entry["png_base64"]))).convert("RGBA")
                            image.putalpha(0)
                            stream = BytesIO()
                            image.save(stream, format="PNG")
                            entry["png_base64"] = base64.b64encode(stream.getvalue()).decode()
                payloads.append(item)
                sources[item["name"]] = xml
    finally:
        engine.db.close()
    fixture = folder / "fixture.json"
    fixture.write_text(json.dumps(payloads))
    proc = subprocess.run([binary, "--path", str(ROOT / "godot"),
                           "--rendering-method", "gl_compatibility", "--script",
                           str(ROOT / "tests/godot/native_head_ink.gd"), "--",
                           str(fixture), str(folder)],
                          env={**os.environ, "LIBGL_ALWAYS_SOFTWARE": "1"},
                          capture_output=True, text=True, timeout=90)
    output = proc.stdout + proc.stderr
    (folder / "godot.log").write_text(output)
    assert proc.returncode == 0, output
    assert f"NATIVE_HEAD_INK_CAPTURES:{len(payloads)}" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    measurements = {}
    for name in sources:
        with Image.open(folder / name / "native-0.00000.png") as picture:
            measurements[name] = _measure(picture, down="down" in name)
    (folder / "head-ink-report.json").write_text(json.dumps(measurements, indent=2) + "\n")
    return measurements


def _measure(picture, *, down):
    """Count every black-head silhouette in the probe's timed staff column.

    The bounded region includes all five staff lines, rather than only the
    requested source pitches; extra heads can therefore invalidate the count.
    Scale/rails come from PNG pixels, outlines from the external Leipzig font.
    No fixture atlas or renderer head coordinates supply expected geometry.
    These spaced thirds/voices do not claim to separate touching seconds.
    """
    pixels = bright(picture)
    staff = detect_staff_lines(picture)["right"]
    gap, x = staff.gap, picture.width * .42
    request = dict(glyph=reference_glyphs()["head_black"], gap=gap,
                   origin_y=staff.lines[0], dxs=range(-round(3*gap), round(3*gap)+1))
    candidates = _joint_candidates(pixels, request, x,
                                   range(-round(gap), round(6*gap)), .79)
    heads = []
    for row in candidates:
        if all(abs(row["x"]-head["x"]) > .7*gap or
               abs(row["y"]-head["y"]) > .5*gap for head in heads):
            heads.append(row)
    y = expected_y(staff, ("D", 0, 5) if down else ("E", 0, 4), ("G", 2, 0))
    top, bottom = (y+.8*gap, y+4.2*gap) if down else (y-4.2*gap, y-.8*gap)
    # Stay beside the stem: the next written rest begins only half a beat
    # after an eighth, so a wider rectangle would count unrelated rest ink.
    left, right = (-.2, .9) if down else (.82, 1.3)
    flag_ink = int(pixels[round(top):round(bottom),
                          round(x+left*gap):round(x+right*gap)].sum())
    return dict(head_count=len(heads), flag_ink=flag_ink,
                head_matches=[round(h["score"], 4) for h in heads])


@pytest.mark.parametrize("name,count", [
    ("quarter-up", 1), ("quarter-down", 1), ("quarter-voices", 3),
    ("eighth-up", 1), ("eighth-down", 1),
])
def test_native_quarter_and_voice_head_inventory(captures, name, count):
    assert captures[f"{name}-baseline"]["head_count"] == count
    assert captures[f"{name}-extra-head"]["head_count"] == count + 1
    assert captures[f"{name}-missing-head"]["head_count"] == count - 1


@pytest.mark.parametrize("direction", ["up", "down"])
def test_quarters_have_no_flag_but_authentic_eighths_do(captures, direction):
    quarter = captures[f"quarter-{direction}-baseline"]
    eighth = captures[f"eighth-{direction}-baseline"]
    assert quarter["flag_ink"] < 30, quarter
    assert eighth["flag_ink"] >= 30, eighth
    # A genuine flagged sprite wrongly substituted on a quarter must fail
    # the same negative flag condition, although the head count still matches.
    wrong = captures[f"quarter-{direction}-wrong-flag"]
    assert wrong["head_count"] == 1
    assert wrong["flag_ink"] >= 30, wrong
    missing = captures[f"eighth-{direction}-wrong-flag"]
    assert missing["head_count"] == 1
    assert missing["flag_ink"] < 30, missing
