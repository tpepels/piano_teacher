"""Two-bar source-derived overlap stress: nested slurs, voices and a barline tie.

This deliberately adds authored expressive marks to a retained MusicXML score
fixture; it is not claimed as an unmodified historical performance. Assets
must come from actual Verovio SVGs and ink from the production Godot renderer.
"""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from piano_teacher.notation.assets.slurs import slur_pairs_from_xml
from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels

ROOT = Path(__file__).resolve().parents[1]


def _mark(note, kind, *, slur=None):
    notations = note.find("notations")
    if notations is None:
        notations = ET.SubElement(note, "notations")
    if kind in ("start", "stop") and slur is not None:
        ET.SubElement(notations, "slur", type=kind, number=str(slur))


@pytest.fixture(scope="module", params=[
    pytest.param("default", marks=pytest.mark.xfail(
        strict=True, reason="Overlapping RH slur ink not yet uniquely owned by independent pixel proof")),
    "separated",
])
def overlap_native(tmp_path_factory, request):
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    from test_native_fingering import _godot, _run_godot

    folder = tmp_path_factory.mktemp("overlap-connector-sources")
    source = ET.parse(ROOT/"tests/fixtures/native_pixel_slur_probe.musicxml")
    rh = source.find("part[@id='RH']")
    lh = source.find("part[@id='LH']")
    assert rh is not None and lh is not None
    first, second = rh.findall("measure")
    upper = [n for n in first.findall("note") if n.find("pitch") is not None]
    later = [n for n in second.findall("note") if n.find("pitch") is not None]
    # Original slur #1 spans RH C4 to F4. Slur #2 begins inside it
    # (D4) and crosses into the second bar (A4).
    _mark(upper[1], "start", slur=2)
    _mark(later[1], "stop", slur=2)
    if request.param == "separated":
        # Keep the exact source notes and beat spans but make the two
        # intersecting RH curves explicitly occupy opposite sides.
        upper[0].find("notations/slur[@number='1']").set("placement", "below")
        upper[3].find("notations/slur[@number='1']").set("placement", "below")
        upper[1].find("notations/slur[@number='2']").set("placement", "above")
        later[1].find("notations/slur[@number='2']").set("placement", "above")
    # The F4 at the end of measure 1 sustains into measure 2. MusicXML
    # importer must merge its sounding note while preserving two written
    # tie endpoints underneath the crossing slur.
    later[0].find("pitch/step").text = "F"
    ET.SubElement(upper[3], "tie", type="start")
    ET.SubElement(upper[3].find("notations"), "tied", type="start")
    ET.SubElement(later[0], "tie", type="stop")
    _mark(later[0], "stop")
    ET.SubElement(later[0].find("notations"), "tied", type="stop")
    # The other staff may legitimately reuse slur number 1 independently.
    lower = lh.find("measure").findall("note")
    _mark(lower[0], "start", slur=1)
    _mark(lower[3], "stop", slur=1)
    xml_file = folder/"source.musicxml"
    xml_file.write_text(ET.tostring(source.getroot(), encoding="unicode"))
    payload, _ = fixture(AuditCase(
        "simultaneous-connector-overlap", str(xml_file), 1, 2, "both"))
    assert payload["source_errors"] == []
    assert payload["assets"]["native_slurs_complete"]
    assert {tuple(pair) for pair in payload["assets"]["native_required_slur_pairs"]} == (
        set(slur_pairs_from_xml(payload["xml"])))
    payload["sample_beats"] = [0.0, 1.0, 3.0, 4.0, 5.0]
    payload_path = folder/"fixture.json"
    payload_path.write_text(json.dumps(payload))
    command = [*_godot(), "--path", str(ROOT/"godot"),
        "--audio-driver", "Dummy", "--rendering-method", "gl_compatibility",
        "--script", str(ROOT/"tests/godot/native_verovio_overlay.gd"),
        "--", str(payload_path), str(folder)]
    run = _run_godot(command, timeout=45)
    stdout = run.stdout + run.stderr
    assert run.returncode == 0 and "NATIVE_VEROVIO_OVERLAY_FAILURES:0" in stdout, stdout[-4000:]
    assert "SCRIPT ERROR" not in stdout, stdout[-4000:]
    return payload["xml"], folder


def test_source_derived_overlapping_slurs_and_tie_keep_independent_pixel_ownership(overlap_native):
    xml, folder = overlap_native
    from piano_teacher.notation.proof import read_written_score
    written = read_written_score(xml)
    from piano_teacher.notation.symbol_pixel_proof import _connector_pairs
    slurs = _connector_pairs(xml, written, ("slur",), "both")
    ties = _connector_pairs(xml, written, ("tie",), "both")
    assert len(slurs) == 3
    assert len(ties) == 1
    report = verify_connector_pixels(xml, folder, hand="both",
                                     constructs=("slur", "tie"))
    (folder/"overlap-proof.json").write_text(json.dumps(report, indent=2))
    assert report["coverage"]["expected"] == 4, report
    details = [
        (row["construct"], row["source_ids"], row["status"],
         row.get("evidence", {}).get("reason"))
        for row in report["observations"]]
    print("OVERLAP_CONNECTOR_STATUS=" + json.dumps(details))
    assert report["complete"], json.dumps(details)


def test_overlap_source_independent_score_retains_sound_tie_and_both_slurs(overlap_native):
    xml, folder = overlap_native
    assert len(slur_pairs_from_xml(xml)) == 3
    from piano_teacher.importing.musicxml import load_musicxml
    piece = load_musicxml(folder/"source.musicxml", bpm=80)
    assert len(piece.notes) == 15  # Sixteen written heads, one sustained pair.
    sustained = [note for note in piece.notes
                 if note.hand == "right" and note.pitch == 65
                 and abs(note.start - 3) < 1e-8]
    assert len(sustained) == 1 and sustained[0].end == 5.0
    root = ET.fromstring(xml)
    assert len(root.findall(".//notations/tied[@type='start']")) == 1
    assert len(root.findall(".//notations/tied[@type='stop']")) == 1
