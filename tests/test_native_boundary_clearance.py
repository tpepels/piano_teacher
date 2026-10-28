"""Hanon 197–200: outgoing authentic flags must clear moving boundaries."""
import json
from pathlib import Path

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/hanon_boundary_clearance"

HARNESS = r'''extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var args := OS.get_cmdline_user_args()
    var f: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var reports: Array = []
    for width in [1024,1536,1920]:
        var vp := SubViewport.new()
        vp.size = Vector2i(width,520)
        vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
        root.add_child(vp)
        var v = load("res://notation/native/view.gd").new()
        v.size = Vector2(vp.size)
        vp.add_child(v)
        var a: Dictionary = f["assets"]
        assert(v.set_verovio_glyphs(a["native_glyphs"],a["native_note_templates"],a["native_tie_templates"],a["native_chord_templates"],a["native_beam_fragments"],a["native_tuplet_fragments"],a["native_slur_fragments"],a["native_required_slur_pairs"],a["native_slurs_complete"],a["native_required_beam_groups"],a["native_beams_complete"]))
        assert(v.load_score(f["model"]),v.failure_reason)
        v.set_fingering_annotations_enabled(false)
        v.set_transport_overlay_enabled(false)
        for spec in f.get("boundary_samples",[{"beat":2.0},{"beat":4.0},{"beat":6.0},{"beat":8.0},
                {"beat":8.0,"loop":true},{"beat":18.0,"loop":true}]):
            var looped: bool = spec.get("loop",false)
            var beat: float = spec["beat"]
            v.present({"running":true,"paused":false,"bpm":40.0,"hand":"both",
                "transport_id":19,"count_in_beats":0.0,"play_from_beat":0.0,
                "score_loop_enabled":looped,"practice_timeline":f["model"]["practice_timeline"]},beat)
            await process_frame
            await process_frame
            await RenderingServer.frame_post_draw
            var name: String = "%d-%.2f-%s.png" % [width,beat,"loop" if looped else "source"]
            vp.get_texture().get_image().save_png(args[1].path_join(name))
            reports.append({"file":name,"width":width,"beat":beat,"loop":looped,
                "density":v.timeline.pixels_per_beat,"gap":v._gap(),"witness":v.selected_density_witness,
                "model":v.timeline.model})
        vp.queue_free()
        await process_frame
    FileAccess.open(args[1].path_join("report.json"),FileAccess.WRITE).store_string(JSON.stringify(reports))
    quit()
'''


def _assert_flag_clearance(image):
    """Locate the actual full staff rule, then reject bright glyph contact.

    Uses only PNG rails, continuous strokes and the public common lead.
    Renderer rectangles/atlas positions cannot authorize a pass.
    """
    from piano_teacher.notation.measure_pixels import detect_barline_strokes
    from piano_teacher.notation.pixel_ink import bright
    found = detect_barline_strokes(image)
    assert found["passed"], found
    target = image.width * .42 - 1.35 * found["staff_gap"]
    strokes = [s for s in found["strokes"] if abs(s["center"] - target) < 2]
    assert len(strokes) == 1, (target, found)
    stroke, = strokes
    pixels = bright(image)
    contact = int(pixels[stroke["top"]:stroke["bottom"]+1, stroke["cols"]].sum())
    assert contact == 0, f"Outgoing glyph touches actual boundary ({contact} bright pixels)"
    return dict(center=stroke["center"], gap=found["staff_gap"], contact=contact)


def _capture(source, out):
    from test_native_fingering import _godot, _run_godot
    script = out / "capture.gd"
    script.write_text(HARNESS)
    run = _run_godot([*_godot(), "--path", str(ROOT/"godot"), "--audio-driver", "Dummy",
        "--rendering-method", "gl_compatibility", "--script", str(script), "--",
        str(source), str(out)], timeout=60)
    output = run.stdout+run.stderr
    (out/"godot.log").write_text(output)
    assert run.returncode == 0 and "SCRIPT ERROR" not in output, output
    return out, json.loads((out/"report.json").read_text())


@pytest.fixture(scope="module")
def boundary_frames(tmp_path_factory):
    return _capture(FIXTURE/"fixture.json",tmp_path_factory.mktemp("boundary-clearance"))


@pytest.fixture(scope="module")
def ordinary_repeat_frames(tmp_path_factory):
    from xml.etree import ElementTree as ET
    from scripts.check_native_verovio_overlay import AuditCase, fixture
    folder = tmp_path_factory.mktemp("ordinary-boundary-clearance")
    root = ET.parse(ROOT/"tests/fixtures/continuous_repetition_context.musicxml")
    for part in root.findall("part"):
        # Constant 4/4/context: this is an already-clear 96-density control,
        # independent of the separate same-clock header placement problem.
        first, last = part.findall("measure")
        first.find("attributes/time/beats").text = "4"
        first.find("note/duration").text = "16"
        first.find("note/type").text = "whole"
        first.find("note").remove(first.find("note/dot"))
        last.remove(last.find("attributes"))
        if part.get("id") == "RH":
            last.find("note/pitch/step").text = "C"
            last.find("note/pitch/octave").text = "5"
        barline = ET.SubElement(part.findall("measure")[-1],"barline",location="right")
        ET.SubElement(barline,"bar-style").text = "light-heavy"
        ET.SubElement(barline,"repeat",direction="backward")
    source = folder/"source.musicxml"
    root.write(source)
    data, _ = fixture(AuditCase("ordinary-repeat",str(source),1,2,"both"))
    data["boundary_samples"] = [dict(beat=4),dict(beat=8),dict(beat=8,loop=True),
                                dict(beat=12,loop=True),dict(beat=20,loop=True)]
    payload = folder/"fixture.json"
    payload.write_text(json.dumps(data))
    return _capture(payload,folder)


def test_real_hanon_source_and_preparation_rules_clear_outgoing_flags(boundary_frames):
    folder, frames = boundary_frames
    for frame in frames:
        _assert_flag_clearance(Image.open(folder/frame["file"]).convert("RGB"))


def test_retained_old_placement_cannot_pass_flag_clearance():
    with pytest.raises(AssertionError, match="Outgoing glyph touches actual boundary"):
        _assert_flag_clearance(Image.open(FIXTURE/"before-terminal.png").convert("RGB"))


def test_density_is_global_and_source_model_is_unchanged(boundary_frames):
    _, frames = boundary_frames
    assert len(frames) == 18
    assert {frame["width"] for frame in frames} == {1024,1536,1920}
    source = json.loads((FIXTURE/"fixture.json").read_text())["model"]
    for frame in frames:
        assert frame["model"] == source
    assert len({frame["density"] for frame in frames}) == 1


def test_written_outgoing_heads_and_photographed_flags_are_preserved(boundary_frames):
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_head
    from piano_teacher.notation.pixel_ink import bright
    folder, frames = boundary_frames
    written = read_written_score((FIXTURE/"score.musicxml").read_text())
    before = Image.open(FIXTURE/"before-terminal.png").convert("RGB")

    def flag_pixels(picture, head):
        x,y,gap = head["x"],head["y"],head["gap"]
        # To the right of the shaft, above the head: the two eighth-flag
        # lobes of each final written sixteenth, never its head or ledger.
        return int(bright(picture)[round(y-3.8*gap):round(y-.6*gap),
                                  round(x+.8*gap):round(x+2.1*gap)].sum())

    for frame in frames:
        picture = Image.open(folder/frame["file"]).convert("RGB")
        boundary = 8 if frame["loop"] else frame["beat"]
        notes = [n for n in written.symbols if n["kind"] == "note" and n["beat"] == boundary-.25]
        assert len(notes) == 2
        for note in notes:
            head = _connector_head(picture,written,note,picture.width*.42-.25*frame["density"])
            assert head, (frame["file"],note)
            if boundary == 8:
                # 582.8 is the retained PNG's independently observed final
                # head anchor. The old picture supplies ink, not an atlas.
                old_head = _connector_head(before,written,note,582.8)
                assert old_head
                retained = flag_pixels(before,old_head)
                assert retained > 150
                assert flag_pixels(picture,head) >= .85*retained


def test_ordinary_repeat_keeps_96_and_common_boundary_phase(ordinary_repeat_frames):
    folder, frames = ordinary_repeat_frames
    for frame in frames:
        assert frame["density"] == 96
        _assert_flag_clearance(Image.open(folder/frame["file"]).convert("RGB"))
