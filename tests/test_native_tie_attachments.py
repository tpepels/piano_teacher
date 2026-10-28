"""Native tie endpoints retain the clearances in actual Verovio contour ink."""
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image
import numpy as np
import pytest

from piano_teacher.notation.symbol_pixel_proof import verify_connector_pixels

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def reference_clearances():
    """Measure reference head/curve pixels, without a native atlas or model."""
    import cairosvg
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    from piano_teacher.notation.assets.svg import isolate

    xml = """<score-partwise version="4.0"><part-list><score-part id="P">
      <part-name>Piano</part-name></score-part></part-list><part id="P">
      <measure number="1"><attributes><divisions>1</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>B</step><octave>4</octave></pitch><duration>2</duration>
      <type>half</type><stem>up</stem><tie type="start"/>
      <notations><tied type="start"/></notations></note>
      <note><pitch><step>B</step><octave>4</octave></pitch><duration>2</duration>
      <type>half</type><stem>up</stem><tie type="stop"/>
      <notations><tied type="stop"/></notations></note>
      </measure></part></score-partwise>"""
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom": "xml", "scale": 48,
        "pageWidth": 900, "pageHeight": 650, "adjustPageHeight": True,
        "svgViewBox": True})
    assert toolkit.loadData(xml)
    tree = ET.fromstring(toolkit.renderToSVG(1))

    def box(node):
        png = cairosvg.svg2png(bytestring=isolate(tree, node).encode(), output_width=1600)
        return Image.open(BytesIO(png)).getchannel("A").getbbox()

    heads = [box(n) for n in tree.iter() if "notehead" in n.get("class", "").split()]
    curve, = [box(n) for n in tree.iter() if "tie" in n.get("class", "").split()]
    # The actual staff pixels supply scale, including the SVG's page transform.
    staff = next(n for n in tree.iter() if "staff" in n.get("class", "").split())
    rails = [box(n) for n in staff if n.tag.endswith("path")]
    gap = rails[1][1] - rails[0][1]
    assert gap > 10 and len(heads) == 2
    return ((curve[0]-heads[0][2])/gap, (heads[1][0]-curve[2])/gap)


@pytest.mark.parametrize("span,pitch,octave,placement", [
    (2, "G", "4", None), (4, "G", "4", None),
    (2, "C", "5", None), (4, "C", "5", None), (2, "C", "5", "below"),
])
def test_native_tie_clearance_does_not_stretch_with_beat_distance(
        tmp_path, reference_clearances, span, pitch, octave, placement):
    """Catch origin/centre confusion and scaling of the endpoint margins."""
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Actual native framebuffer needs Godot and a desktop")
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    tree = ET.parse(ROOT/"tests/fixtures/native_pixel_tie_probe.musicxml")
    first = tree.find("part[@id='RH']/measure/note")
    if span == 2:
        first.find("duration").text = "16"
        first.find("type").text = "half"
        opening = ET.fromstring("<note><rest/><duration>16</duration>"
                                "<voice>1</voice><type>half</type></note>")
        tree.find("part[@id='RH']/measure").insert(1, opening)
    for note in tree.findall("part[@id='RH']/measure/note[pitch]"):
        note.find("pitch/step").text = pitch
        note.find("pitch/octave").text = octave
        if placement:
            note.find('notations/tied').set('placement', placement)
    xml = ET.tostring(tree.getroot(), encoding="unicode")
    source = tmp_path/"source.musicxml"
    source.write_text(xml)
    data, _ = fixture(AuditCase("tie-attachment", str(source), 1, 2, "right"))
    if placement:
        # The general import/lesson fixture currently regenerates tied marks
        # without placement. Keep this controlled VIEW fixture faithful to
        # the authored XML, without changing importer behavior in this task.
        for event in data['model']['notation_events']:
            if event['staff'] == 'right':
                for attributes in event.get('tied_marks', []):
                    attributes.append(['placement', placement])
    data["sample_beats"] = [4-span, 4]
    payload = tmp_path/"fixture.json"
    payload.write_text(json.dumps(data))
    result = subprocess.run([binary, "--path", str(ROOT/"godot"), "--audio-driver", "Dummy",
        "--rendering-method", "gl_compatibility", "--script",
        str(ROOT/"tests/godot/native_verovio_overlay.gd"), "--", str(payload), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    (tmp_path/"godot.log").write_text(result.stdout+result.stderr)
    assert result.returncode == 0, (result.stdout+result.stderr)[-4000:]
    assert "NATIVE_VEROVIO_OVERLAY_FAILURES:0" in result.stdout
    proof = verify_connector_pixels(xml, tmp_path, hand="right", constructs=("tie",))
    (tmp_path/"connector-proof.json").write_text(json.dumps(proof, indent=2))
    assert proof["coverage"]["expected"] == 1
    assert proof["complete"], proof
    evidence = proof["observations"][0]["evidence"]
    left, right = evidence["heads"]
    # Both actual head-edge clearances and independent source ownership must
    # hold, including for whole heads wider than ordinary filled/half heads.
    from piano_teacher.notation.pixel_ink import bright
    from piano_teacher.notation.symbol_pixel_proof import _connector_components
    picture = Image.open(tmp_path/evidence["frame"]).convert("RGB")
    x0, x1 = left["bbox"][2], right["bbox"][0]
    y0 = round(min(left["y"], right["y"])-1.5*left["gap"])
    y1 = round(max(left["y"], right["y"])+1.5*left["gap"])
    components = list(_connector_components(bright(picture)[y0:y1, x0:x1]))
    assert len(components) == 1, "The isolated source pair needs one connected curve"
    xy = np.asarray(components[0])
    xs, ys = xy[:, 1], xy[:, 0]
    curve = [x0+xs.min(), y0+ys.min(), x0+xs.max()+1, y0+ys.max()+1]
    centers = [np.median(ys[xs == x]) for x in range(xs.min(), xs.max()+1)]
    sag = np.max(np.abs(centers-np.linspace(centers[0], centers[-1], len(centers))))
    assert sag/left["gap"] > .16, "A straight stroke cannot stand in for a tie"
    if placement == 'below':
        assert curve[1] > max(left['y'], right['y']), 'Written below placement must override the pitch/stem rule'
    measured = ((curve[0]-left["bbox"][2])/left["gap"],
                (right["bbox"][0]-curve[2])/right["gap"])
    assert measured == pytest.approx(reference_clearances, abs=.16)


@pytest.mark.parametrize("last_kind", ["whole", "quarter"])
def test_compressed_tie_does_not_collapse_to_missing_or_vertical_ink(tmp_path, last_kind):
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Actual native framebuffer needs Godot and a desktop")
    from piano_teacher.notation.assets.glyphs import native_glyphs
    from piano_teacher.notation.assets.ties import tie_templates

    payload = tmp_path/"tie.json"
    payload.write_text(json.dumps(dict(glyphs=native_glyphs(), ties=tie_templates(), last_kind=last_kind)))
    target = tmp_path/"compressed.png"
    result = subprocess.run([binary, "--path", str(ROOT/"godot"), "--audio-driver", "Dummy",
        "--rendering-method", "gl_compatibility", "--script",
        str(ROOT/"tests/godot/native_tie_pixels.gd"), "--", str(payload), str(target)],
        capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout+result.stderr
    rgba = np.asarray(Image.open(target).convert("RGBA"))
    assert np.count_nonzero(rgba[:, :, 3] > 128) > 30, "A tight native span must not erase or collapse the tie"


@pytest.mark.parametrize("explicit_placement", [False, True])
def test_chord_ties_face_outward_and_preserve_written_placement(tmp_path, explicit_placement):
    from copy import deepcopy
    from scripts.check_native_verovio_overlay import AuditCase, fixture

    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        pytest.skip("Actual native framebuffer needs Godot and a desktop")
    tree = ET.parse(ROOT/"tests/fixtures/native_pixel_tie_probe.musicxml")
    part = tree.find("part[@id='RH']")
    for measure in part.findall('measure'):
        low = measure.find('note')
        low.find('pitch/step').text = 'C'
        low.find('pitch/octave').text = '5'
        low.find('duration').text = '16'
        low.find('type').text = 'half'
        high = deepcopy(low)
        high.insert(0, ET.Element('chord'))
        high.find('pitch/step').text = 'E'
        if explicit_placement:
            low.find('notations/tied').set('placement', 'below')
            high.find('notations/tied').set('placement', 'above')
        measure.insert(list(measure).index(low)+1, high)
    part[0].insert(1, ET.fromstring('<note><rest/><duration>16</duration>'
                                   '<voice>1</voice><type>half</type></note>'))
    xml = ET.tostring(tree.getroot(), encoding='unicode')
    source = tmp_path/'source.musicxml'
    source.write_text(xml)
    data, _ = fixture(AuditCase('chord-tie-directions', str(source), 1, 2, 'right'))
    if explicit_placement:
        for event in data['model']['notation_events']:
            if event['staff'] == 'right' and event['kind'] == 'note':
                placement = 'below' if event['spelling']['step'] == 'C' else 'above'
                for attributes in event.get('tied_marks', []):
                    attributes.append(['placement', placement])
    data['sample_beats'] = [2, 4]
    payload = tmp_path/'fixture.json'
    payload.write_text(json.dumps(data))
    result = subprocess.run([binary, '--path', str(ROOT/'godot'), '--audio-driver', 'Dummy',
        '--rendering-method', 'gl_compatibility', '--script',
        str(ROOT/'tests/godot/native_verovio_overlay.gd'), '--', str(payload), str(tmp_path)],
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout+result.stderr
    proof = verify_connector_pixels(xml, tmp_path, hand='right', constructs=('tie',))
    (tmp_path/'connector-proof.json').write_text(json.dumps(proof, indent=2))
    assert proof['coverage']['expected'] == 2
    assert proof['complete'], proof
    low, high = proof['observations']
    assert low['evidence']['component_bbox'][1] > low['evidence']['heads'][0]['y']
    assert high['evidence']['component_bbox'][3] < high['evidence']['heads'][0]['y']
