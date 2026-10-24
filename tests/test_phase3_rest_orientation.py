"""Whole/half identity comes from actual ink relative to detected staff rails."""
from io import BytesIO
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

import numpy as np
import cairosvg
from PIL import Image
import pytest

from piano_teacher.notation.phase3_pixels import verify_all_rest_pixels
from piano_teacher.notation.assets.glyphs import native_glyphs
from test_phase3_rest_differences import _captures


REAL = Path(__file__).parent / "fixtures/rest_orientation_native"


def test_retained_native_whole_rest_is_identified_below_its_detected_rail():
    # Actual Godot baseline: rectangle [632,337,657,347], rail y=336.5.
    report = verify_all_rest_pixels((REAL / "score.musicxml").read_text(), REAL)
    assert report["complete"], report
    assert report["image_rest_glyphs_verified"] == 1
    row = report["measured"][0]
    assert row["required_rest"] == row["observed_rest"] == "whole"
    assert row["observed_box"] == [632, 337, 657, 347]
    assert row["type_ambiguity"] is False


@pytest.mark.parametrize("kind", ["whole", "half"])
@pytest.mark.parametrize("spaces", [-3, 0, 3])
@pytest.mark.parametrize("gap", [8, 20, 32])
def test_rectangular_rests_keep_identity_across_whole_space_voice_displacements(tmp_path, kind, spaces, gap):
    xml = _captures(tmp_path, kind=kind, shift=spaces*gap, gap=gap)
    report = verify_all_rest_pixels(xml, tmp_path)
    assert report["complete"], report
    assert report["measured"][0]["observed_rest"] == kind


@pytest.mark.parametrize("kind,other", [("whole", "half"), ("half", "whole")])
def test_opposite_rest_orientation_is_a_mismatch_even_when_rectangles_match(tmp_path, kind, other):
    xml = _captures(tmp_path, kind=kind)
    xml = xml.replace(f"<type>{kind}</type>", f"<type>{other}</type>")
    report = verify_all_rest_pixels(xml, tmp_path)
    assert not report["passed"], report
    assert report["coverage"]["mismatch"] == 1
    assert report["measured"][0]["observed_rest"] == kind


@pytest.mark.parametrize("kind", ["whole", "half"])
def test_quarter_space_offset_cannot_establish_rectangular_rest_identity(tmp_path, kind):
    report = verify_all_rest_pixels(_captures(tmp_path, kind=kind, shift=5), tmp_path)
    assert report["coverage"]["ambiguous"] == 1
    assert not report["complete"]


def test_real_whole_rest_shifted_half_a_space_is_not_still_blessed_as_whole(tmp_path):
    shutil.copytree(REAL, tmp_path, dirs_exist_ok=True)
    suppressed = np.array(Image.open(tmp_path / "rest-without-0-0.00000.png"))
    original = np.array(Image.open(tmp_path / "native-0.00000.png"))
    delta = np.max(abs(original.astype(int)-suppressed.astype(int)), axis=2) >= 10
    # Move only the actual rest ink by half the measured 21.875px space;
    # keep all staff rails and unrelated ink at their original positions.
    ys, xs = np.nonzero(delta)
    moved = suppressed.copy()
    moved[ys+11, xs] = original[ys, xs]
    for name in ("native", "repeat", "restored"):
        Image.fromarray(moved).save(tmp_path / f"{name}-0.00000.png")
    report = verify_all_rest_pixels((tmp_path / "score.musicxml").read_text(), tmp_path)
    assert not report["passed"], report
    row = report["measured"][0]
    assert row["status"] == "mismatch"
    assert row["observed_rest"] == "half"


def test_rest_dot_cannot_be_certified_from_an_undotted_suppression_delta(tmp_path):
    xml = _captures(tmp_path)
    root = ET.fromstring(xml)
    ET.SubElement(root.find("part/measure/note"), "dot")
    report = verify_all_rest_pixels(ET.tostring(root, encoding="unicode"), tmp_path)
    assert not report["complete"], report
    assert report["image_rest_glyphs_verified"] == 0


def test_real_repeat_drift_still_invalidates_orientation_evidence(tmp_path):
    shutil.copytree(REAL, tmp_path, dirs_exist_ok=True)
    frame = tmp_path / "repeat-0.00000.png"
    image = Image.open(frame).convert("RGB")
    image.putpixel((1000, 100), (255, 255, 255))
    image.save(frame)
    report = verify_all_rest_pixels((tmp_path / "score.musicxml").read_text(), tmp_path)
    assert not report["passed"]
    assert report["coverage"]["unverified"] == 1


def _dotted_capture(folder, *, kind="quarter", written=1, drawn=1, mutation=None):
    root = ET.fromstring(_captures(folder, kind=kind))
    for _ in range(written):
        ET.SubElement(root.find("part/measure/note"), "dot")
    glyph = native_glyphs()["augmentation_dot"]
    bounds = glyph["bounds"]
    dot = Image.open(BytesIO(cairosvg.svg2png(bytestring=glyph["svg"].encode(),
        output_width=round(bounds[2]*20/250),
        output_height=round(bounds[3]*20/250)))).convert("RGBA")
    # Remove the unchanged neighboring note so double dots remain isolated.
    for name in ("native-0.00000", "repeat-0.00000", "restored-0.00000", "without"):
        path = folder / f"{name}.png"
        image = Image.open(path).convert("RGBA")
        image.paste((16, 41, 35, 255), (660, 145, 710, 175))
        if name != "without" or mutation == "unchanged-neighbor":
            for i in range(drawn):
                # Authored spatial relation: detached dots to the right of
                # the body, separated by .65 staff spaces.
                y = 165 if kind == "whole" else 155
                x = 666 + i*13
                if mutation == "wrong-shape":
                    image.paste((235, 242, 234, 255), (x-1, y-6, x+1, y+6))
                else:
                    image.alpha_composite(dot, (x-dot.width//2, y-dot.height//2))
        image.convert("RGB").save(path)
    return ET.tostring(root, encoding="unicode")


@pytest.mark.parametrize("kind", ["quarter", "whole", "half"])
@pytest.mark.parametrize("count", [1, 2])
def test_rest_dots_require_distinct_isolated_suppressed_contours(tmp_path, kind, count):
    report = verify_all_rest_pixels(_dotted_capture(tmp_path, kind=kind,
        written=count, drawn=count), tmp_path)
    assert report["complete"], report
    evidence = report["measured"][0]["dot_evidence"]
    assert evidence["status"] == "verified"
    assert evidence["observed_count"] == count


@pytest.mark.parametrize("written,drawn,mutation", [
    (1, 0, None), (2, 1, None), (1, 2, None), (0, 1, None),
    (1, 1, "wrong-shape"), (1, 1, "unchanged-neighbor"),
])
def test_wrong_missing_extra_or_unchanged_neighbor_dots_do_not_receive_credit(tmp_path, written, drawn, mutation):
    report = verify_all_rest_pixels(_dotted_capture(tmp_path, written=written,
        drawn=drawn, mutation=mutation), tmp_path)
    assert not report["complete"], report
    assert report["image_rest_glyphs_verified"] == 0
