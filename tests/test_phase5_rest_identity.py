"""Independent rest identities require distinct ink in the same full frame."""
from copy import deepcopy
import json
from xml.etree import ElementTree as ET

import numpy as np
import pytest
from PIL import Image

from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels
from test_phase3_rest_differences import _captures


def _two_rests(folder, *, clock=0, second_shift=None, overlap=False):
    xml = _captures(folder, shift=-second_shift if second_shift is not None else 0)
    root = ET.fromstring(xml)
    measure = root.find("part/measure")
    first = measure.find("note")
    first.find("duration").text = "1"
    second = deepcopy(first)
    second.set("id", "second-rest")
    second.find("voice").text = "2"
    if clock == 0:
        backup = ET.SubElement(measure, "backup")
        ET.SubElement(backup, "duration").text = "1"
    measure.append(second)
    path = folder / "native-overlay-report.json"
    data = json.loads(path.read_text())
    control = data["rest_difference_controls"][0]
    control["id"] = "source-rest"
    other = dict(control, id="second-rest", voice="2", clock=clock,
                 file="independently-named-without.png")
    data["rest_difference_controls"].append(other)
    original = np.array(Image.open(folder / "native-0.00000.png"))
    suppressed = np.array(Image.open(folder / "without.png"))
    other_suppressed = suppressed.copy()
    if second_shift is not None:
        shifted = folder / "shifted"
        shifted.mkdir()
        _captures(shifted, shift=second_shift)
        second_original = np.array(Image.open(shifted / "native-0.00000.png"))
        second_ink = np.any(second_original != suppressed, axis=2)
        combined = np.where(second_ink[:, :, None], second_original, original)
        for name in ("native", "repeat", "restored"):
            Image.fromarray(combined).save(folder / f"{name}-0.00000.png")
        Image.fromarray(second_original).save(folder / "without.png")
        other_suppressed = original
    elif overlap:
        # A one-pixel difference defeats exact-mask hashing but still reuses
        # the same physical rest. Preserve one changed original ink pixel.
        ys, xs = np.nonzero(np.max(np.abs(original.astype("int16") - suppressed.astype("int16")), axis=2) >= 10)
        other_suppressed[ys[0], xs[0]] = original[ys[0], xs[0]]
    Image.fromarray(other_suppressed).save(folder / other["file"])
    if clock:
        for name in ("native", "repeat", "restored"):
            Image.fromarray(original).save(folder / f"{name}-{clock:.5f}.png")
        data["rest_difference_frames"].append({
            "clock": clock, "repeat_file": f"repeat-{clock:.5f}.png",
            "restored_file": f"restored-{clock:.5f}.png"})
    path.write_text(json.dumps(data))
    return ET.tostring(root, encoding="unicode")


@pytest.mark.parametrize("overlap", [False, True], ids=["identical", "overlapping"])
def test_same_frame_one_glyph_cannot_verify_two_independently_named_rests(tmp_path, overlap):
    xml = _two_rests(tmp_path, overlap=overlap)
    report = verify_all_rest_pixels(xml, tmp_path)
    assert report["coverage"] == dict(expected=2, verified=0, ambiguous=2,
                                      unsupported=0, unverified=0, mismatch=0), report
    assert not report["passed"]
    assert not report["complete"]
    assert report["image_rest_glyphs_verified"] == 0
    assert report["intrinsically_indistinguishable_half_whole"] == 0
    assert {row["source_id"] for row in report["measured"]} == {"source-rest", "second-rest"}
    assert len({row["delta_file"] for row in report["measured"]}) == 2
    counts = [row["changed_pixels"] for row in report["measured"]]
    assert counts[0] - counts[1] == int(overlap)
    assert all(row["changed_pixels"] >= 12 and row["shape_match"] >= .65
               for row in report["measured"])


@pytest.mark.parametrize("shift", [-45, 45])
def test_same_frame_equal_contours_at_distinct_displaced_positions_remain_verified(tmp_path, shift):
    report = verify_all_rest_pixels(_two_rests(tmp_path, second_shift=shift), tmp_path)
    assert report["passed"], report
    assert report["complete"]
    assert report["coverage"]["verified"] == 2
    assert len({tuple(row["observed_box"]) for row in report["measured"]}) == 2


def test_different_clocks_can_reuse_identical_playhead_pixels(tmp_path):
    report = verify_all_rest_pixels(_two_rests(tmp_path, clock=1), tmp_path)
    assert report["passed"], report
    assert report["complete"]
    assert report["coverage"]["verified"] == 2
    assert {row["beat"] for row in report["measured"]} == {0, 1}
    assert len({tuple(row["observed_box"]) for row in report["measured"]}) == 1


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "voice", "staff"])
def test_missing_unique_control_or_mutated_source_binding_cannot_receive_credit(tmp_path, mutation):
    xml = _two_rests(tmp_path, second_shift=45)
    path = tmp_path / "native-overlay-report.json"
    data = json.loads(path.read_text())
    controls = data["rest_difference_controls"]
    if mutation == "missing":
        controls.pop()
    elif mutation == "duplicate":
        controls.append(deepcopy(controls[-1]))
    elif mutation == "voice":
        controls[-1]["voice"] = "99"
    else:
        controls[-1]["staff"] = "left"
    path.write_text(json.dumps(data))
    report = verify_all_rest_pixels(xml, tmp_path)
    assert not report["passed"]
    assert not report["complete"]
    row = next(row for row in report["measured"] if row["source_id"] == "second-rest")
    assert row["status"] == "unverified"
    assert report["coverage"]["expected"] == 2
    assert report["coverage"]["verified"] == 1


@pytest.mark.parametrize("mutation", ["reused-control", "changed-source-id"])
def test_existing_same_voice_source_identity_guards_remain_closed(tmp_path, mutation):
    root = ET.fromstring(_two_rests(tmp_path, second_shift=45))
    first, second = root.findall("part/measure/note")
    second.find("voice").text = "1"
    path = tmp_path / "native-overlay-report.json"
    data = json.loads(path.read_text())
    controls = data["rest_difference_controls"]
    if mutation == "reused-control":
        second.set("id", first.get("id"))
        controls.pop()
    else:
        controls[-1].update(voice="1", id="unbound-source-id")
    path.write_text(json.dumps(data))
    report = verify_all_rest_pixels(ET.tostring(root, encoding="unicode"), tmp_path)
    assert not report["passed"]
    assert not report["complete"]
    assert [row["status"] for row in report["measured"]] == ["verified", "unverified"]
    assert report["coverage"] == dict(expected=2, verified=1, ambiguous=0,
                                      unsupported=0, unverified=1, mismatch=0)
