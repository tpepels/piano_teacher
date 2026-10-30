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


@pytest.fixture(scope="module", params=["default", "separated"])
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
    # Keep the exact crossing RH slurs in both cases. The aggressive
    # default also ties their shared endpoint, while the separated case
    # uses the same barline-tie rhythm in the other hand. This distinguishes
    # a missing slur from contour interference at one notehead.
    lower = lh.find("measure").findall("note")
    lower_later = lh.findall("measure")[1].findall("note")
    _mark(lower[0], "start", slur=1)
    if request.param == "default":
        later[0].find("pitch/step").text = "F"
        ET.SubElement(upper[3], "tie", type="start")
        ET.SubElement(upper[3].find("notations"), "tied", type="start")
        ET.SubElement(later[0], "tie", type="stop")
        _mark(later[0], "stop")
        ET.SubElement(later[0].find("notations"), "tied", type="stop")
        _mark(lower[3], "stop", slur=1)
    else:
        _mark(lower[2], "stop", slur=1)
        ET.SubElement(lower[3], "tie", type="start")
        _mark(lower[3], "start")
        ET.SubElement(lower[3].find("notations"), "tied", type="start")
        ET.SubElement(lower_later[0], "tie", type="stop")
        _mark(lower_later[0], "stop")
        ET.SubElement(lower_later[0].find("notations"), "tied", type="stop")
    xml_file = folder/"source.musicxml"
    xml_file.write_text(ET.tostring(source.getroot(), encoding="unicode"))
    payload, _ = fixture(AuditCase(
        "simultaneous-connector-overlap", str(xml_file), 1, 2, "both"))
    assert payload["source_errors"] == []
    assert payload["assets"]["native_slurs_complete"]
    assert {tuple(pair) for pair in payload["assets"]["native_required_slur_pairs"]} == (
        set(slur_pairs_from_xml(payload["xml"])))
    payload["sample_beats"] = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    payload["slur_ablation_at"] = 2.0  # one stationary frame, not a corpus run
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
    return request.param, payload["xml"], folder


def test_source_derived_overlapping_slurs_and_tie_keep_independent_pixel_ownership(overlap_native):
    case, xml, folder = overlap_native
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
    # Competing whole-frame curves cannot lend one another ink. The
    # independent causal oracle must prove each source with its own actual
    # rendered suppression, endpoint contours, curvature and exclusive pixels.
    assert report["coverage"]["expected"] == report["coverage"]["verified"] == 4, details
    assert report["complete"], details
    assert sum(row["evidence"].get("method") == "causal-framebuffer-difference"
               for row in report["observations"]) == 3, details
    assert report["observations"][0]["evidence"].get("method") != "causal-framebuffer-difference"



@pytest.mark.parametrize("damage", ["missing", "unchanged-control", "drifting-repeat"])
def test_intervention_cannot_authorize_missing_or_fake_slur(overlap_native, tmp_path, damage):
    import shutil
    _case, xml, folder = overlap_native
    for item in folder.glob("*.png"):
        shutil.copyfile(item, tmp_path/item.name)
    manifest = json.loads((folder/"native-overlay-report.json").read_text())
    (tmp_path/"native-overlay-report.json").write_text(json.dumps(manifest))
    if damage == "missing":
        (tmp_path/manifest["slur_difference_controls"][1]["file"]).unlink()
    elif damage == "unchanged-control":
        control = manifest["slur_difference_controls"][1]
        shutil.copyfile(folder/control["baseline_file"],tmp_path/control["file"])
    else:
        from PIL import Image, ImageDraw
        path = tmp_path/manifest["slur_difference_frames"][0]["repeat_file"]
        with Image.open(path) as image:
            changed = image.convert("RGB")
        ImageDraw.Draw(changed).rectangle((5,5,70,70),fill="white")
        changed.save(path)
    result = verify_connector_pixels(xml,tmp_path,hand="both",constructs=("slur","tie"))
    assert not result["complete"], (damage,result["observations"])
    assert result["coverage"]["verified"] < result["coverage"]["expected"]


def test_each_source_slur_contributes_separate_native_ink(overlap_native):
    """Source-bound causal evidence for slurs the generic overlap oracle cannot isolate.

    One stable production screenshot is re-rendered with exactly one slur
    suppressed each time. The resulting stroke must retain continuous curved
    ink, independent source-head or stem attachments, and unique pixels.
    It does not grant a pass to the generic unsuppressed-frame oracle.
    """
    import numpy as np
    from PIL import Image
    from piano_teacher.notation.pixel_ink import bright
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import (
        PLAYHEAD, _connector_head, _connector_pairs, _connector_shift,
    )

    _case, xml, folder = overlap_native
    report = json.loads((folder / "native-overlay-report.json").read_text())
    controls = report["slur_difference_controls"]
    controls_at = report["slur_difference_frames"]
    desired = {"|".join(pair) for pair in slur_pairs_from_xml(xml)}
    assert len(desired) == 3
    assert len(controls_at) == 1, controls_at
    assert len(controls) == len(desired), controls
    assert {row["key"] for row in controls} == desired, controls
    assert len({row["key"] for row in controls}) == len(controls)

    written = read_written_score(xml)
    source_pairs = _connector_pairs(xml, written, ("slur",), "both")
    keyed = {"|".join(n["id"] for n in pair["notes"]): pair for pair in source_pairs}
    assert len(keyed) == len(desired) and set(keyed) == desired

    def pixels(filename):
        with Image.open(folder / filename) as image:
            return np.asarray(image.convert("RGB"), dtype=np.int16)

    reference = controls_at[0]
    base = pixels(reference["baseline_file"])
    repeat = pixels(reference["repeat_file"])
    restored = pixels(reference["restored_file"])
    assert np.max(np.abs(base-repeat)) <= 2, "Native frame drift before suppression"
    assert np.max(np.abs(base-restored)) <= 2, "Native frame changed after restoration"

    # All note positions are recovered from real PNG contours and pixel-only
    # frame registration. Never use the renderer's head positions or slur atlas.
    registered, shift_cache = {}, {}
    with Image.open(folder / reference["baseline_file"]) as image:
        base_image = image.convert("RGB")
    luminance = bright(base_image)

    def source_head(note):
        identity = note["source"]["id"]
        if identity not in registered:
            beat = float(note["beat"])
            with Image.open(folder / f"native-{beat:.2f}.png") as frame:
                onset_image = frame.convert("RGB")
            anchor = _connector_head(onset_image, written, note,
                                     onset_image.width * PLAYHEAD)
            assert anchor is not None, identity
            if beat not in shift_cache:
                shift_cache[beat] = (
                    {"shift": 0} if abs(beat-2.0) < 1e-8 else
                    _connector_shift(base_image, onset_image)
                )
            offset = shift_cache[beat]
            assert offset is not None, (identity, beat)
            observed = _connector_head(
                base_image, written, note, anchor["x"]+offset["shift"])
            assert observed is not None, identity
            registered[identity] = observed
            onset_image.close()
        return registered[identity]

    masks, footprints = [], []
    for row in controls:
        assert row["baseline_file"] == reference["baseline_file"]
        altered = pixels(row["file"])
        assert altered.shape == base.shape
        mask = np.max(np.abs(base-altered), axis=2) >= 20
        masks.append(mask)
        ys, xs = np.nonzero(mask)
        assert len(xs) >= 30, row["key"]
        columns = np.flatnonzero(mask.any(axis=0))
        assert columns[-1]-columns[0] >= 35, row["key"]
        assert int(np.diff(columns).max()) <= 3, row["key"]
        centers = np.array([np.median(np.flatnonzero(mask[:, x]))
                            for x in columns])
        chord = np.linspace(centers[0], centers[-1], len(centers))
        sag = float(np.max(np.abs(centers-chord)))

        heads = [source_head(note) for note in keyed[row["key"]]["notes"]]
        gap = min(head["gap"] for head in heads)
        assert sag >= .20*gap, (row["key"], sag)
        assert max(int(mask[:, x].sum()) for x in columns) <= .65*gap, row["key"]
        endpoints = ((int(columns[0]), float(centers[0])),
                     (int(columns[-1]), float(centers[-1])))
        for (x, y), head in zip(endpoints, heads):
            assert abs(x-head["x"]) <= .8*gap, (row["key"], x, head)
            l, t, r, b = head["bbox"]
            distance = float(np.hypot(max(l-x, 0, x-r), max(t-y, 0, y-b)))
            if distance > 1.2*gap:
                # Authored slurs may end beside the vertical stem rather
                # than the head. Require a real stem extending to that end.
                first, last = sorted((round(y), round(head["y"])))
                assert last-first >= .9*gap, row["key"]
                stem = any(
                    abs(column-x) < .65*gap and
                    float(np.mean(luminance[first:last+1, column])) >= .88
                    for column in range(max(0, int(l)-8),
                                        min(luminance.shape[1], int(r)+8))
                )
                assert stem, (row["key"], (x,y), head, distance/gap)
        footprints.append(dict(key=row["key"], changed_pixels=int(mask.sum()),
                               curvature_spaces=round(sag/gap, 3)))
    for index, mask in enumerate(masks):
        others = np.logical_or.reduce([candidate for other, candidate in enumerate(masks)
                                       if other != index])
        assert int(np.count_nonzero(mask & ~others)) >= 24, footprints
    base_image.close()


def test_overlap_source_independent_score_retains_sound_tie_and_both_slurs(overlap_native):
    case, xml, folder = overlap_native
    assert len(slur_pairs_from_xml(xml)) == 3
    from piano_teacher.importing.musicxml import load_musicxml
    piece = load_musicxml(folder/"source.musicxml", bpm=80)
    assert len(piece.notes) == 15  # Sixteen written heads, one sustained pair.
    tied_hand = "right" if case == "default" else "left"
    tied_pitch = 65 if case == "default" else 48
    sustained = [note for note in piece.notes
                 if note.hand == tied_hand and note.pitch == tied_pitch
                 and abs(note.start - 3) < 1e-8]
    assert len(sustained) == 1 and sustained[0].end == 5.0
    root = ET.fromstring(xml)
    assert len(root.findall(".//notations/tied[@type='start']")) == 1
    assert len(root.findall(".//notations/tied[@type='stop']")) == 1
