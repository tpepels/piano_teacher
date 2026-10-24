"""Independent pixel diagnostics retain source status and reject contaminated ink."""
from hashlib import sha256
import json
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def diagnostic_captures(folder):
    from io import BytesIO
    import cairosvg
    from piano_teacher.notation.reference_font import reference_glyphs

    folder.mkdir()
    (folder / "score.musicxml").write_text('''<score-partwise><part-list>
      <score-part id="RH"><part-name>Right</part-name></score-part></part-list>
      <part id="RH"><measure number="1"><attributes><divisions>1</divisions>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note id="n"><pitch><step>C</step><octave>4</octave></pitch><duration>1</duration>
      <voice>1</voice><type>quarter</type></note>
      <note id="r"><rest/><duration>4</duration><voice>1</voice><type>whole</type></note>
      </measure></part></score-partwise>''')
    bg = Image.new("RGB", (1536, 520), (16, 41, 35))
    draw = ImageDraw.Draw(bg)
    for y in (120, 140, 160, 180, 200, 320, 340, 360, 380, 400):
        draw.line((0, y, 1535, y), fill=(73, 83, 77))
    glyphs = reference_glyphs()
    for beat, name, y in ((0, "head_black", 220), (1, "rest_whole", 160)):
        glyph = glyphs[name]; bounds = glyph["bounds"]
        width, height = round(bounds[2]*20/250), round(bounds[3]*20/250)
        mask = Image.open(BytesIO(cairosvg.svg2png(bytestring=glyph["svg"].encode(),
                         output_width=width, output_height=height))).convert("RGBA")
        image = bg.convert("RGBA")
        image.alpha_composite(mask, (round(1536*.42-width/2), round(y+bounds[1]*20/250)))
        image.convert("RGB").save(folder / f"native-{beat:.5f}.png")
        if beat == 1:
            image.convert("RGB").save(folder / "repeat.png")
            image.convert("RGB").save(folder / "restored.png")
            bg.save(folder / "without.png")
    write_json(folder / "fixture.json", {"assets": {"native_glyphs": {"head_black": "corrupt atlas"}}})
    write_json(folder / "native-overlay-report.json", {"staff_gap": 9999,
               "frames": [{"clock": 0, "noteheads": {"n": [-999, -999]}}],
               "rest_difference_protocol": 2,
               "rest_difference_frames": [{"clock": 1, "repeat_file": "repeat.png", "restored_file": "restored.png"}]})
    write_json(folder / "independent-pixels.json", {"measured": [
        {"source_id": "n", "measure": 1, "beat": 0, "staff": "right", "voice": "1",
         "spelling": ["C", 0, 4], "status": "unverified", "glyph": "head_black"}],
        "failures": ["representative failure"]})
    write_json(folder / "independent-rests.json", {"measured": [
        {"source_id": "r", "measure": 1, "beat": 1, "staff": "right", "voice": "1",
         "required_rest": "whole", "status": "ambiguous", "delta_file": "without.png"}],
        "failures": []})
    return folder


def diagnostics_module():
    path = ROOT / "piano_teacher/notation/release_diagnostics.py"
    assert path.exists(), "symbol diagnostics have not been implemented"
    from piano_teacher.notation import release_diagnostics
    return release_diagnostics


def test_authentic_glyph_diagnostics_ignore_native_atlas_and_keep_original_statuses(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    output = tmp_path / "diagnostics"
    data = diagnostics_module().create_diagnostics(folder, output, hand="both", limit=2)
    assert data["derived"] is True and data["verification_evidence"] is False
    assert len(data["symbols"]) == 2
    assert {r["status"] for r in data["symbols"]} == {"unverified", "ambiguous"}
    assert len(data["exemplars"]) == 2
    assert {r["source_status"] for r in data["exemplars"]} == {"unverified", "ambiguous"}
    for row in data["exemplars"]:
        assert row["diagnostic_status"] == "available", row
        assert row["font"] == "Leipzig"
        assert row["derived"] is True and row["verification_evidence"] is False
        assert row["reference_sha256"] == digest(output / row["reference"])
        assert row["native_sha256"] == digest(folder / row["native"])
        for name in ("reference", "overlay", "delta"):
            assert (output / row[name]).is_file()
    assert json.loads((output / "diagnostics.json").read_text()) == data


def test_missing_or_contaminated_control_never_manufactures_rest_diagnostic_proof(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    (folder / "without.png").unlink()
    data = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", hand="both", limit=1)
    row = data["exemplars"][0]
    assert row["kind"] == "rest"  # The ambiguous failure is selected ahead of a note.
    assert row["source_status"] == "ambiguous"
    assert row["diagnostic_status"] == "unverified"
    assert not row["verification_evidence"]
    assert "delta" not in row


def test_diagnostic_limit_represents_distinct_failure_kinds_and_statuses(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    notes = json.loads((folder / "independent-pixels.json").read_text())
    note = notes["measured"][0]
    notes["measured"] = [{**note, "status": "ambiguous", "source_id": str(i)} for i in range(8)]
    write_json(folder / "independent-pixels.json", notes)
    rests = json.loads((folder / "independent-rests.json").read_text())
    rests["measured"][0]["status"] = "unverified"
    write_json(folder / "independent-rests.json", rests)
    result = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", limit=2)
    assert {(row["kind"], row["source_status"]) for row in result["exemplars"]} == {
        ("notehead", "ambiguous"), ("rest", "unverified")}
    assert len(result["symbols"]) == 9


def test_dark_frame_drift_invalidates_rest_delta_diagnostic(tmp_path):
    folder = diagnostic_captures(tmp_path / "window")
    with Image.open(folder / "without.png") as image:
        control = image.convert("RGB")
    ImageDraw.Draw(control).rectangle((1000, 100, 1010, 110), fill="black")
    control.save(folder / "without.png")
    result = diagnostics_module().create_diagnostics(folder, tmp_path / "diagnostics", limit=1)
    assert result["exemplars"][0]["diagnostic_status"] == "unverified"
    assert "delta" not in result["exemplars"][0]
