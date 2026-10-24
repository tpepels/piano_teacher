"""Signatures and measure boundaries must be identified in actual native ink."""
from pathlib import Path
from shutil import copytree

from PIL import Image, ImageDraw

from piano_teacher.notation import feature_pixels
from piano_teacher.notation.visual_coverage import visual_elements

SOURCE = Path(__file__).parent / "fixtures/native_structure"


def check(folder):
    xml = (folder/"score.musicxml").read_text()
    elements = visual_elements(None, xml, {}, {}, hand="both")
    return feature_pixels.verify_structure_pixels(xml, folder, elements, hand="both")


def test_real_native_clefs_meter_and_terminal_barline_have_independent_pixel_evidence():
    rows = check(SOURCE)
    assert rows
    assert {r["construct"] for r in rows} == {"clef", "meter", "barline", "measure"}
    assert all(r["status"] == "verified" for r in rows), rows


def test_erased_clef_or_meter_cannot_use_another_staff_header(tmp_path):
    for kind, box in (("clef", (300, 70, 480, 280)),
                      ("meter", (450, 100, 600, 270))):
        folder = tmp_path/kind
        copytree(SOURCE, folder)
        path = folder/"native-0.00000.png"
        image = Image.open(path).convert("RGB")
        ImageDraw.Draw(image).rectangle(box, fill="#102923")
        image.save(path)
        rows = check(folder)
        assert any(r["construct"] == kind and r["status"] != "verified" for r in rows)


def test_erased_terminal_barline_is_unverified(tmp_path):
    copytree(SOURCE, tmp_path, dirs_exist_ok=True)
    path = tmp_path/"native-4.00000.png"
    image = Image.open(path).convert("RGB")
    ImageDraw.Draw(image).rectangle((555, 100, 735, 430), fill="#102923")
    image.save(path)
    assert any(r["construct"] == "barline" and r["status"] != "verified" for r in check(tmp_path))


def test_initial_key_signature_has_all_required_accidentals_before_the_meter(tmp_path):
    source = SOURCE.with_name("native_structure_key")
    rows = [r for r in check(source) if r["construct"] == "key"]
    assert len(rows) == 2
    assert all(r["status"] == "verified" for r in rows), rows
    copytree(source, tmp_path, dirs_exist_ok=True)
    path = tmp_path/"native-0.00000.png"
    image = Image.open(path).convert("RGB")
    ImageDraw.Draw(image).rectangle((427, 85, 475, 265), fill="#102923")
    image.save(path)
    assert any(r["construct"] == "key" and r["status"] != "verified" for r in check(tmp_path))
