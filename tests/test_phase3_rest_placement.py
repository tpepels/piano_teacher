"""Readable rest placement uses detected rails and unchanged framebuffer ink."""
from PIL import Image, ImageDraw
import pytest

from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels
from test_phase3_rest_differences import _captures
from test_phase3_rest_orientation import REAL, _dotted_capture


def _unchanged_ink(folder, box):
    for name in ("native-0.00000.png", "repeat-0.00000.png",
                 "restored-0.00000.png", "without.png"):
        path = folder / name
        image = Image.open(path).convert("RGB")
        ImageDraw.Draw(image).rectangle(box, fill=(255, 255, 255))
        image.save(path)


def test_actual_whole_rest_has_independent_readable_placement_evidence():
    report = verify_all_rest_pixels((REAL/"score.musicxml").read_text(), REAL)
    placement = report["measured"][0]["placement_evidence"]
    assert placement["status"] == "verified", placement
    assert placement["bbox"] == [632, 337, 657, 347]
    assert len(placement["staff_lines"]) == 5
    assert abs(placement["relative_offset_spaces"] + 1) < .13
    assert placement["min_clearance_spaces"] >= placement["required_clearance_spaces"]
    assert report["placement_complete"]


@pytest.mark.parametrize("kind", ["whole", "half", "quarter", "eighth", "16th"])
@pytest.mark.parametrize("spaces", [-2, 0, 2])
def test_readable_whole_space_voice_displacements_keep_placement_credit(tmp_path, kind, spaces):
    xml = _captures(tmp_path, kind=kind, shift=spaces*20)
    report = verify_all_rest_pixels(xml, tmp_path)
    placement = report["measured"][0]["placement_evidence"]
    assert placement["status"] == "verified", placement
    assert abs(placement["relative_offset_spaces"] - spaces) < .13


@pytest.mark.parametrize("mutation", ["off-grid", "too-far", "touch-body", "overlap-body", "touch-dot"])
def test_shape_preserving_layout_mutations_never_receive_placement_credit(tmp_path, mutation):
    if mutation == "touch-dot":
        xml = _dotted_capture(tmp_path, kind="whole")
        _unchanged_ink(tmp_path, (669, 164, 671, 166))
    else:
        xml = _captures(tmp_path, kind="whole" if "body" in mutation else "quarter",
                        shift=5 if mutation == "off-grid" else 120 if mutation == "too-far" else 0)
        if mutation == "touch-body":
            _unchanged_ink(tmp_path, (657, 162, 659, 166))
        elif mutation == "overlap-body":
            _unchanged_ink(tmp_path, (644, 157, 644, 172))
    report = verify_all_rest_pixels(xml, tmp_path)
    row = report["measured"][0]
    # Contour identity remains known; layout is a distinct ledger obligation.
    assert row["status"] == "verified", row
    assert row["placement_evidence"]["status"] != "verified", row
    assert not report["placement_complete"]
    assert report["placement_coverage"]["verified"] == 0


def test_small_but_readable_clearance_is_not_a_collision(tmp_path):
    xml = _captures(tmp_path, kind="whole")
    # Three blank pixel columns separate body x<=656 from neighbor x=660.
    _unchanged_ink(tmp_path, (660, 162, 662, 166))
    row = verify_all_rest_pixels(xml, tmp_path)["measured"][0]
    assert row["placement_evidence"]["status"] == "verified", row
    assert row["placement_evidence"]["min_clearance_spaces"] == pytest.approx(.15)


def test_unresolved_orientation_cannot_authorize_placement(tmp_path):
    row = verify_all_rest_pixels(_captures(tmp_path, kind="half", shift=5), tmp_path)["measured"][0]
    assert row["placement_evidence"]["status"] != "verified"


def _isolated_capture(folder, kind, shift):
    xml = _captures(folder, kind=kind, shift=shift)
    # Keep high-order rest flags clear of the unchanged neighboring note.
    # This region is to the right of every reference rest's body, so the
    # suppression delta and authentic glyph contour remain unchanged.
    for name in ("native-0.00000.png", "repeat-0.00000.png",
                 "restored-0.00000.png", "without.png"):
        path = folder/name
        image = Image.open(path).convert("RGB")
        ImageDraw.Draw(image).rectangle((670, 155, 692, 167), fill=(16, 41, 35))
        image.save(path)
    return xml


@pytest.mark.parametrize("kind", ["quarter", "eighth", "16th", "32nd", "64th", "128th"])
@pytest.mark.parametrize("shift", [-10, 10])
def test_collision_free_nonrectangular_rests_accept_half_space_lanes(tmp_path, kind, shift):
    report = verify_all_rest_pixels(_isolated_capture(tmp_path, kind, shift), tmp_path)
    row = report["measured"][0]
    assert row["status"] == "verified", row
    assert row["placement_evidence"]["status"] == "verified", row
    assert report["placement_complete"]
    assert row["placement_evidence"]["relative_offset_spaces"] == pytest.approx(shift/20, abs=.13)


@pytest.mark.parametrize("kind", ["quarter", "eighth", "16th", "32nd", "64th", "128th"])
@pytest.mark.parametrize("shift", [-5, 5])
def test_nonrectangular_rests_still_reject_quarter_space_lanes(tmp_path, kind, shift):
    row = verify_all_rest_pixels(_isolated_capture(tmp_path, kind, shift), tmp_path)["measured"][0]
    assert row["status"] == "verified", row
    assert row["placement_evidence"]["status"] != "verified", row


@pytest.mark.parametrize("kind", ["whole", "half"])
@pytest.mark.parametrize("shift", [-10, 10])
def test_rectangular_rests_do_not_gain_half_space_placement_credit(tmp_path, kind, shift):
    row = verify_all_rest_pixels(_isolated_capture(tmp_path, kind, shift), tmp_path)["measured"][0]
    assert row["status"] == "mismatch", row
    assert row["placement_evidence"]["status"] != "verified", row


@pytest.mark.parametrize("kind", ["quarter", "eighth"])
@pytest.mark.parametrize("shift", [-10, 10])
def test_visual_ledger_accepts_actual_nonrectangular_half_space_evidence(tmp_path, kind, shift):
    from test_phase3_visual_coverage import ledger, rows
    xml = _isolated_capture(tmp_path, kind, shift)
    report = verify_all_rest_pixels(xml, tmp_path)
    result = ledger(None, xml, rests=report["measured"])
    assert rows(result, "rest_placement")[0]["status"] == "verified", result


@pytest.mark.parametrize("kind", ["quarter", "eighth"])
def test_visual_ledger_does_not_bless_forged_quarter_space_status(tmp_path, kind):
    from test_phase3_visual_coverage import ledger, rows
    xml = _isolated_capture(tmp_path, kind, 5)
    report = verify_all_rest_pixels(xml, tmp_path)
    # A producer's status/counter cannot replace measured baseline geometry.
    report["measured"][0]["placement_evidence"].update(status="verified", grid_phase_error_spaces=0.)
    result = ledger(None, xml, rests=report["measured"])
    assert rows(result, "rest_placement")[0]["status"] != "verified"
