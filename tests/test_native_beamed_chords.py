"""Source beams override isolated chord directions, using real Verovio assets."""
import json
import os
from copy import deepcopy
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _authored_beamed_chords():
    """Low thirds forced down and high thirds forced up in authored XML."""
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    from piano_teacher.verovio_beam_fragments import extract_beam_fragments
    from piano_teacher.verovio_chord_templates import chord_templates
    from piano_teacher.verovio_note_templates import note_templates
    from piano_teacher.verovio_tie_templates import tie_templates
    from piano_teacher.notation_symbols import native_glyphs

    measures, events, xml_measures = [], [], []
    for number, octave, steps, direction, ids in (
            (1, 4, "GBA", "down", ("a", "ac", "b")),
            (2, 5, "CED", "up", ("c", "cc", "d"))):
        start = float((number - 1) * 4)
        measures.append({"number": number, "start_beat": start,
            "end_beat": start + 4, "meter": [4, 4],
            "keys": {"right": 0, "left": 0},
            "clefs": {"right": {"sign": "G", "line": 2},
                      "left": {"sign": "F", "line": 4}}})
        xml_notes = []
        for i, (identifier, step) in enumerate(zip(ids, steps)):
            chord = i == 1
            beam = "" if chord else (
                '<beam number="1">begin</beam>' if i == 0 else
                '<beam number="1">end</beam>')
            xml_notes.append(f'<note id="{identifier}">'
                f'{"<chord/>" if chord else ""}'
                f'<pitch><step>{step}</step><octave>{octave}</octave></pitch>'
                f'<duration>2</duration><voice>1</voice><type>eighth</type>'
                f'<stem>{direction}</stem>{beam}</note>')
            events.append({"id": identifier, "source_id": identifier,
                "kind": "note", "staff": "right", "voice": "1",
                "measure": number, "beat": start + (.5 if i == 2 else 0),
                "duration_beats": .5, "note_type": "eighth", "dots": 0,
                "chord": chord, "spelling": {"step": step, "octave": octave}})
        attributes = ('<attributes><divisions>4</divisions>'
            '<time><beats>4</beats><beat-type>4</beat-type></time>'
            '<clef><sign>G</sign><line>2</line></clef></attributes>') if number == 1 else ""
        xml_measures.append(f'<measure number="{number}">{attributes}'
            f'{"".join(xml_notes)}<note><rest/><duration>12</duration>'
            '<voice>1</voice><type>half</type><dot/></note></measure>')
    xml = ('<score-partwise version="4.0"><work><work-title> </work-title></work>'
        '<movement-title> </movement-title><part-list><score-part id="P">'
        '<part-name>Piano</part-name></score-part></part-list><part id="P">'
        f'{"".join(xml_measures)}</part></score-partwise>')
    model = {"schema": "piano-teacher-score-model-v1", "revision": 1,
        "beat_unit": "quarter", "duration_beats": 8.0,
        "measures": measures, "notation_events": events,
        "notes": [{"id": e["source_id"], "onset_beats": e["beat"],
                   "duration_beats": .5, "midi_pitch": 60, "hand": "right"}
                  for e in events]}
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48,
        "pageWidth": 900, "pageHeight": 650, "svgViewBox": True,
        "svgBoundingBoxes": True, "svgContentBoundingBoxes": True})
    assert toolkit.loadData(xml)
    beams = extract_beam_fragments(
        [toolkit.renderToSVG(p) for p in range(1, toolkit.getPageCount() + 1)], model)
    assert set(beams) == {"a|b", "c|d"}
    assert beams["a|b"]["stem_up"] is False
    assert beams["c|d"]["stem_up"] is True
    directions = {identifier: fragment["stem_up"]
                  for fragment in beams.values() for identifier in fragment["note_ids"]}
    chords = chord_templates(model, stem_directions=directions)
    # Both local directions occur naturally in this model. Each of those
    # two genuine templates is required in the opposite source beam too.
    assert {"eighth|up|0,2", "eighth|down|0,2"} <= chords.keys()
    return {"model": model, "glyphs": native_glyphs(), "beams": beams,
            "notes": note_templates(), "ties": tie_templates(), "chords": chords}


@pytest.fixture(scope="module")
def authored_assets():
    return _authored_beamed_chords()


def test_authentic_beamed_chords_select_source_direction_before_validation(tmp_path, authored_assets):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    fixture = tmp_path / "beamed-chords.json"
    fixture.write_text(json.dumps(authored_assets))
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/native_beamed_chords.gd"),
         "--", str(fixture)],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        text=True, capture_output=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_BEAMED_CHORD_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output


def test_authentic_beamed_stem_masks_exclude_nested_flags(authored_assets):
    # A bare Leipzig stem occupies far less than half a staff space. Flags
    # nested inside Verovio's stem group widen the crop to a full space.
    for name, item in authored_assets["notes"].items():
        if name != "whole":
            assert item["stem_only"]["bounds"][2] < 80, (name, item["stem_only"]["bounds"])
    for name, item in authored_assets["chords"].items():
        assert item["stem_only"]["bounds"][2] < 80, (name, item["stem_only"]["bounds"])


def test_authentic_beams_contact_measured_stems_at_multiple_densities(tmp_path, authored_assets):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not os.environ.get("DISPLAY"):
        pytest.skip("Godot with a display is required for beam pixel verification")
    fixture = tmp_path / "beams.json"
    fixture.write_text(json.dumps(authored_assets))
    result = subprocess.run(
        [binary, "--path", str(ROOT / "godot"), "--windowed",
         "--resolution", "640x240", "--rendering-method", "gl_compatibility",
         "--script", str(ROOT / "tests/godot/native_beam_contact.gd"),
         "--", str(fixture)],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        text=True, capture_output=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_BEAM_CONTACT_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output


@pytest.mark.parametrize("vertically_separated", [False, True])
def test_packed_accidental_ink_clears_previous_onset_at_one_global_scale(
        tmp_path, authored_assets, vertically_separated):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot 4 unavailable")
    from piano_teacher.verovio_chord_templates import chord_templates

    data = deepcopy(authored_assets)
    model = data["model"]
    model["duration_beats"] = 4.0
    model["measures"] = model["measures"][:1]
    prior = {**model["notation_events"][0], "id": "prior", "source_id": "prior",
             "note_type": "quarter", "duration_beats": 1.0,
             "spelling": {"step": "E", "octave": 4}}
    events = [prior]
    for i, step in enumerate("CDEFGAB"):
        events.append({**prior, "id": f"sharp_{step}", "source_id": f"sharp_{step}",
            "beat": 1.0, "chord": i != 0, "accidental": "sharp",
            "spelling": {"step": step, "octave": 4, "alter": 1}})
    if vertically_separated:
        events = [prior, {**prior, "id": "high", "source_id": "high",
            "beat": .002, "voice": "2", "spelling": {"step": "C", "octave": 7}}]
    data["vertically_separated"] = vertically_separated
    model["notation_events"] = events
    model["notes"] = [{"id": e["id"], "onset_beats": e["beat"],
                       "duration_beats": 1.0, "midi_pitch": 60, "hand": "right"}
                      for e in events]
    data["chords"] = chord_templates(model)
    data["beams"] = {}
    fixture = tmp_path / "accidentals.json"
    fixture.write_text(json.dumps(data))
    result = subprocess.run(
        [binary, "--headless", "--path", str(ROOT / "godot"),
         "--script", str(ROOT / "tests/godot/native_accidental_density.gd"),
         "--", str(fixture)],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1"},
        text=True, capture_output=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_ACCIDENTAL_DENSITY_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
