"""Short chord stems must not merge an authentic tie into their flag.

Regression from Bill Evans bars 12–13, MIDI t1/e57 (B-flat 2).
The original independent connected-curve test must accept the real PNG;
the former single-note clearance is retained as a corrupted control.
"""
import json
from pathlib import Path

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r'''extends SceneTree
class FixedStaffLayout extends "res://notation/native/score_layout.gd":
    func staff_center(hand: String) -> float:
        return 110.0 if hand=="right" else 280.0
class LegacyTieGeometry extends "res://notation/native/connector_geometry.gd":
    var old := false
    func tie_contour_rect(first: Dictionary,last: Dictionary,place: Dictionary,gap: float) -> Rect2:
        if not old:
            return super.tie_contour_rect(first,last,place,gap)
        # Former placement: the single-note template's endpoint margins.
        var data: Dictionary = score.glyphs.tie_metadata[tie_template_key(first,last,place,gap)]
        var box: Array = data["bounds"]
        var centers: Array = data["head_centers"]
        var unit: float = gap/250.0
        var left: float = float(place["x0"])+(float(box[0])-float(centers[0]))*unit
        var right: float = float(place["x1"])+(float(box[0])+float(box[2])-float(data["span"])-float(centers[1]))*unit
        return Rect2(left,float(place["y"])+float(box[1])*unit,right-left,float(box[3])*unit)

class Probe extends "res://notation/native/view.gd":
    var spec: Dictionary
    func _init() -> void:
        layout = FixedStaffLayout.new(timeline,glyphs)
        symbols.connector_geometry = LegacyTieGeometry.new(layout)
    func _draw() -> void:
        layout.set_viewport(size)
        symbols.connector_geometry.old = bool(spec.get("old",false))
        var gap := 21.875
        draw_rect(Rect2(Vector2.ZERO,size),Design.STAGE)
        for center in [110.0,280.0]:
            for rail in range(-2,3):
                draw_line(Vector2(0,center+rail*gap),Vector2(size.x,center+rail*gap),Color(NOTE_INK,.34),1.0)
        var events: Array = spec["events"]
        var measure: Dictionary = spec["measure"]
        layout.ordered_events = events
        layout.measure_by_number = {1:measure}
        timeline.measures = [measure]
        layout.chord_members = {"a0":[events[0],events[1]],"b0":[events[2],events[3]]}
        var first: Dictionary = events[int(spec["tone"])]
        var last: Dictionary = events[2+int(spec["tone"])]
        symbols.paint_engraved_chord(self,RenderPass.new(),events[0],100.0,gap,NOTE_INK)
        symbols.paint_engraved_chord(self,RenderPass.new(),events[2],181.0,gap,NOTE_INK)
        symbols.paint_tie_contour(self,RenderPass.new(),first,last,connector_geometry.tie_placement(first,last,100.0,181.0,gap),gap)
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var args := OS.get_cmdline_user_args()
    var f: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
    var vp := SubViewport.new()
    vp.size = Vector2i(420,400)
    vp.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(vp)
    var v := Probe.new()
    v.size = Vector2(vp.size)
    vp.add_child(v)
    assert(v.glyphs.load_font(f["glyphs"]))
    assert(v.glyphs.load_note_templates(f["notes"]))
    assert(v.glyphs.load_tie_templates(f["ties"]))
    assert(v.glyphs.load_chord_templates(f["chords"]))
    for spec in f["cases"]:
        v.spec = spec
        v.queue_redraw()
        await process_frame
        await process_frame
        await RenderingServer.frame_post_draw
        vp.get_texture().get_image().save_png(args[1].path_join(spec["name"]+".png"))
    quit()
'''


def _case(staff, pitches, first_kind, last_kind, stem, tone, name):
    clef = dict(sign="F", line=4) if staff == "left" else dict(sign="G", line=2)
    measure = dict(number=1, start_beat=0, end_beat=4, clefs={staff: clef})
    events = []
    notes = []
    for prefix, beat, kind, tie in (("a", 0, first_kind, "start"), ("b", .4, last_kind, "stop")):
        for i, (step, alter, octave) in enumerate(pitches):
            events.append(dict(id=f"{prefix}{i}", kind="note", staff=staff, voice="1", hand=staff,
                measure=1, beat=beat, note_type=kind, chord=bool(i), stem=stem,
                spelling=dict(step=step, alter=alter, octave=octave), dots=0))
            tie_xml = f'<tie type="{tie}"/>' if i == tone else ""
            notes.append(f'<note id="{prefix}{i}">{"<chord/>" if i else ""}<pitch>'
                         f'<step>{step}</step><alter>{alter}</alter><octave>{octave}</octave></pitch>'
                         f'<duration>4</duration><voice>1</voice><type>{kind}</type><stem>{stem}</stem>'
                         f'{tie_xml}</note>')
    part = "LH" if staff == "left" else "RH"
    xml = (f'<score-partwise><part-list><score-part id="{part}"><part-name>{staff.title()}</part-name>'
           f'</score-part></part-list><part id="{part}"><measure number="1"><attributes><divisions>10</divisions>'
           f'<clef><sign>{clef["sign"]}</sign><line>{clef["line"]}</line></clef></attributes>'
           + ''.join(notes) + '</measure></part></score-partwise>')
    return dict(name=name, events=events, measure=measure, tone=tone), xml


@pytest.fixture(scope="module")
def chord_frames(tmp_path_factory):
    from piano_teacher.notation.assets.glyphs import native_glyphs
    from piano_teacher.notation.assets.notes import note_templates
    from piano_teacher.notation.assets.ties import tie_templates
    from piano_teacher.notation.assets.chords import chord_templates
    from test_native_fingering import _godot, _run_godot

    folder = tmp_path_factory.mktemp("chord-flag-ties")
    cases = [
        _case("left", [("E", -1, 2), ("B", -1, 2)], "eighth", "quarter", "up", 1, "bass-start"),
        _case("left", [("B", -1, 2), ("E", -1, 2)], "eighth", "quarter", "up", 0, "bass-upper-leader"),
        _case("right", [("B", 0, 4), ("F", 0, 5)], "quarter", "eighth", "down", 0, "treble-end"),
    ]
    assets = {}
    for case, _ in cases:
        assets.update(chord_templates(dict(measures=[case["measure"]], notation_events=case["events"])))
    rendered = []
    for case, _ in cases:
        rendered.extend([case, {**case, "name":case["name"]+"-old", "old":True}])
    payload = dict(cases=rendered, glyphs=native_glyphs(), notes=note_templates(), ties=tie_templates(), chords=assets)
    (folder/"fixture.json").write_text(json.dumps(payload))
    (folder/"probe.gd").write_text(HARNESS)
    result = _run_godot([*_godot(), "--path", str(ROOT/"godot"), "--audio-driver", "Dummy",
        "--rendering-method", "gl_compatibility", "--script", str(folder/"probe.gd"), "--",
        str(folder/"fixture.json"), str(folder)], timeout=45)
    output = result.stdout+result.stderr
    (folder/"godot.log").write_text(output)
    assert result.returncode == 0 and "SCRIPT ERROR" not in output, output
    return folder, cases


def _proof(folder, case, xml, suffix=""):
    from piano_teacher.notation.proof import read_written_score
    from piano_teacher.notation.symbol_pixel_proof import _connector_curve, _connector_head
    written = read_written_score(xml)
    notes = [n for n in written.symbols if n["kind"] == "note"]
    picture = Image.open(folder/(case["name"]+suffix+".png")).convert("RGB")
    heads = [_connector_head(picture, written, notes[i], x)
             for i, x in ((case["tone"], 100.), (case["tone"]+2, 181.))]
    assert all(heads), heads
    return _connector_curve(picture, heads, "tie", "above" if case["name"].startswith("bass-") else "below")


@pytest.mark.parametrize("name", ["bass-start", "bass-upper-leader", "treble-end"])
def test_chord_flag_does_not_absorb_source_owned_tie(chord_frames, name):
    folder, cases = chord_frames
    case, xml = next((case, xml) for case, xml in cases if case["name"] == name)
    assert _proof(folder, case, xml)["status"] == "verified"


def test_former_single_note_clearance_rejects_chord_flag_collision(chord_frames):
    folder, cases = chord_frames
    case, xml = cases[0]
    assert _proof(folder, case, xml, "-old")["status"] != "verified"
