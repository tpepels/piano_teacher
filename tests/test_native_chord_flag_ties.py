"""Short chord stems must not merge an authentic tie into their flag.

Regression from Bill Evans bars 12–13, MIDI t1/e57 (B-flat 2).
The independent connected-curve proof must accept the real PNG, and must
reject two corrupted controls of the same chords: the tie removed, and the
tie moved onto the flag beside the stem tip.
"""
import json
from pathlib import Path

from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ("no_tie", "into_flag")

HARNESS = r'''extends SceneTree
class FixedStaffLayout extends "res://notation/native/score_layout.gd":
    func staff_center(hand: String) -> float:
        return 110.0 if hand=="right" else 280.0
class Probe extends "res://notation/native/view.gd":
    var spec: Dictionary
    func _init() -> void:
        layout = FixedStaffLayout.new(timeline,glyphs)
    func _draw() -> void:
        layout.set_viewport(size)
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
        # Preserve the original 81px span on the canonical beat axis.
        assert(timeline.set_density(202.5))
        layout.chord_members = {str(events[0]["id"]):[events[0],events[1]],
            str(events[2]["id"]):[events[2],events[3]]}
        var first: Dictionary = events[int(spec["tone"])]
        var last: Dictionary = events[2+int(spec["tone"])]
        layout.tie_pairs = [{"first":first,"last":last}]
        layout._index_source_spans("ties",layout.tie_pairs)  # painters query the span index
        connector_geometry.prewarm_tie_clearances(gap)
        symbols.paint_engraved_chord(self,RenderPass.new(),events[0],100.0,gap,NOTE_INK)
        symbols.paint_engraved_chord(self,RenderPass.new(),events[2],181.0,gap,NOTE_INK)
        var control: String = str(spec.get("control",""))
        if control == "no_tie":
            return
        if control == "into_flag":
            # Corrupted control: the same tie drawn on the flag at the stem tip.
            var up: bool = str(events[0].get("stem","up")) == "up"
            draw_set_transform(Vector2(0.0,(-3.0 if up else 3.0)*gap))
        symbols.paint_ties(self,RenderPass.new(),100.0,0.0,gap)
        draw_set_transform(Vector2.ZERO)
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
            # Ids are unique per case: all cases share one chord atlas.
            events.append(dict(id=f"{name}-{prefix}{i}", kind="note", staff=staff, voice="1", hand=staff,
                measure=1, beat=beat, note_type=kind, chord=bool(i), stem=stem,
                spelling=dict(step=step, alter=alter, octave=octave), dots=0))
            tie_xml = f'<tie type="{tie}"/>' if i == tone else ""
            notes.append(f'<note id="{name}-{prefix}{i}">{"<chord/>" if i else ""}<pitch>'
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
    from verovio_test_score import verovio_pages
    for case, xml in cases:
        atlas = chord_templates(dict(measures=[case["measure"]], notation_events=case["events"]),
                                pages=verovio_pages(xml))
        for key, item in atlas.items():
            # Two cases engrave the same shape: one template names both.
            assets.setdefault(key, item)["leaders"].update(item["leaders"])
    rendered = []
    for case, _ in cases:
        rendered.extend([case] + [{**case, "name": f"{case['name']}-{control}", "control": control}
                                  for control in CONTROLS])
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


@pytest.mark.parametrize("control", CONTROLS)
@pytest.mark.parametrize("name", ["bass-start", "bass-upper-leader", "treble-end"])
def test_corrupted_tie_controls_are_rejected(chord_frames, name, control):
    folder, cases = chord_frames
    case, xml = next((case, xml) for case, xml in cases if case["name"] == name)
    assert _proof(folder, case, xml, f"-{control}")["status"] != "verified"
