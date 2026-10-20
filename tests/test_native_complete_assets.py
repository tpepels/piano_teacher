"""Real engravings for extended durations, clefs and semantic tuplet identities."""
import base64
from copy import deepcopy
from io import BytesIO
import xml.etree.ElementTree as ET

from PIL import Image
import pytest


def ink(item):
    with Image.open(BytesIO(base64.b64decode(item["png_base64"]))) as image:
        assert image.getchannel("A").getbbox()


def test_128th_font_rest_and_flags_have_original_verovio_contours():
    from piano_teacher.notation.assets.glyphs import native_glyphs
    atlas = native_glyphs()
    for name, code in (("rest_128th", "E4EA"), ("flag_up_5", "E248"),
                       ("flag_down_5", "E249")):
        assert name in atlas, f"Missing genuine {name}"
        assert atlas[name]["code"] == code
        assert atlas[name]["source"] == "verovio"
        assert "<path" in atlas[name]["svg"]
        assert atlas[name]["bounds"][2] > 0


def test_128th_complete_notes_have_flags_and_separate_flag_free_stems():
    from piano_teacher.notation.assets.notes import note_templates, _one_note_xml
    atlas = note_templates()
    for direction in ("up", "down"):
        name = f"128th_{direction}"
        assert name in atlas, "128th attacks must never fall back to quarter artwork"
        ink(atlas[name])
        ink(atlas[name]["stem_only"])
        assert atlas[name]["png_base64"] != atlas[f"64th_{direction}"]["png_base64"]
        note = ET.fromstring(_one_note_xml("128th", direction)).find(".//note")
        assert note.findtext("duration") == "315"
        assert note.findtext("type") == "128th"
        assert note.findtext("stem") == direction


@pytest.mark.parametrize("direction,octave", [("up", 4), ("down", 5)])
def test_128th_chord_keeps_original_heads_stems_and_five_flags(direction, octave):
    from piano_teacher.notation.assets.chords import chord_templates
    events = [{"id": f"n{i}", "kind": "note", "staff": "right", "voice": "1",
               "measure": 1, "beat": 0, "note_type": "128th", "chord": bool(i),
               "spelling": {"step": step, "octave": octave}}
              for i, step in enumerate("CE")]
    atlas = chord_templates({"notation_events": events, "measures": [{"number": 1}]},
                            stem_directions={"n0": direction == "up"})
    key = f"128th|{direction}|0,2"
    assert key in atlas, "128th chord geometry must be genuinely engraved"
    for component in (atlas[key], atlas[key]["heads_only"], atlas[key]["stem_only"]):
        ink(component)
    assert len(atlas[key]["head_positions"]) == 2


def events():
    return [{"id": name, "kind": "rest" if name == "r" else "note",
             "staff": "right", "voice": "1", "measure": 1 if i < 2 else 2,
             "beat": i / 3, "duration_beats": 1 / 3, "chord": False,
             "tuplet_marks": []} for i, name in enumerate(("a", "r", "b"))]


def explicit_groups():
    return [{"id": name, "kind": "tuplet", "event_ids": ["a", "r", "b"],
             "start_beat": 0, "end_beat": 1, "staff": "right", "voice": "1",
             "attributes": {"source_id": name, "number": number}}
            for name, number in (("outer", "1"), ("inner", "2"))]


def test_explicit_tuplet_groups_preserve_distinct_ids_and_rest_membership():
    from piano_teacher.notation.assets.tuplets import semantic_tuplets
    model = {"notation_events": events(), "groups": explicit_groups()}
    before = deepcopy(model)
    groups = semantic_tuplets(model)
    assert set(groups) == {"outer", "inner"}
    for name in groups:
        assert groups[name]["event_ids"] == ["a", "r", "b"]
        assert groups[name]["attributes"]["source_id"] == name
    assert model == before


def test_explicit_empty_groups_disable_legacy_inference():
    from piano_teacher.notation.assets.tuplets import semantic_tuplets
    lane = events()
    lane[0]["tuplet_marks"] = [{"type": "start", "number": "1"}]
    lane[-1]["tuplet_marks"] = [{"type": "stop", "number": "1"}]
    assert semantic_tuplets({"notation_events": lane, "groups": []}) == {}


def test_legacy_tuplet_marks_continue_across_measures_and_include_rests():
    from piano_teacher.notation.assets.tuplets import semantic_tuplets
    lane = events()
    lane[0]["tuplet_marks"] = [{"type": "start", "number": "1"}]
    lane[-1]["tuplet_marks"] = [{"type": "stop", "number": "1"}]
    groups = semantic_tuplets({"notation_events": lane})
    assert ("a", "r", "b") in groups


def test_rest_svg_ids_are_semantic_tuplet_members():
    from piano_teacher.notation.assets.tuplets import source_ids
    svg = ET.fromstring('<g><g class="note" id="a"/><g class="rest" id="r"/>'
                        '<g class="rest content-bounding-box" id="cbbox-r"/>'
                        '<g class="note" id="b"/></g>')
    assert source_ids(svg) == ("a", "r", "b")


MEI = '''<mei xmlns="http://www.music-encoding.org/ns/mei" meiversion="5.0">
<meiHead><fileDesc><titleStmt><title>Tuplets</title></titleStmt><pubStmt/></fileDesc></meiHead>
<music><body><mdiv><score><scoreDef meter.count="4" meter.unit="4"><staffGrp>
<staffDef n="1" lines="5" clef.shape="G" clef.line="2"/></staffGrp></scoreDef>
<section><measure n="1"><staff n="1"><layer n="1">
<tuplet xml:id="outer" num="3" numbase="2" bracket.visible="true">
<tuplet xml:id="inner" num="5" numbase="4" bracket.visible="true">
<note xml:id="a" pname="c" oct="5" dur="8"/>
<rest xml:id="r" dur="8"/>
<note xml:id="b" pname="e" oct="5" dur="8"/>
</tuplet></tuplet></layer></staff></measure></section>
</score></mdiv></body></music></mei>'''


def engrave(xml):
    import verovio
    from piano_teacher.notation.assets.runtime import _create_verovio_toolkit
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"svgViewBox": True, "svgBoundingBoxes": True,
        "svgContentBoundingBoxes": True, "breaks": "none", "pageWidth": 1800})
    assert toolkit.loadData(xml)
    return toolkit.renderToSVG(1)


def test_authored_nested_rest_tuplets_keep_both_same_endpoint_source_objects():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    model = {"notation_events": events(), "groups": explicit_groups()}
    atlas = extract_tuplets([engrave(MEI)], model)
    assert set(atlas) == {"outer", "inner"}
    for name, item in atlas.items():
        assert item["group_id"] == name
        assert item["source_id"] == name
        assert item["event_ids"] == ["a", "r", "b"]
        ink(item["number"])
        ink(item["bracket"])
    assert atlas["outer"]["number"]["png_base64"] != atlas["inner"]["number"]["png_base64"]


def test_normalized_rest_id_resolves_its_original_svg_rest_anchor():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    lane, groups = events(), explicit_groups()
    lane[1].update(id="normalized-rest", source_id="r")
    for group in groups:
        group["event_ids"][1] = "normalized-rest"
    atlas = extract_tuplets([engrave(MEI)], {"notation_events": lane, "groups": groups})
    assert set(atlas) == {"outer", "inner"}
    assert atlas["outer"]["event_ids"] == ["a", "normalized-rest", "b"]


def test_tuplet_cache_identity_includes_explicit_group_ids(tmp_path):
    from piano_teacher.preprocessing_cache import PreprocessingCache
    from piano_teacher.notation.assets.tuplets import tuplet_fragments
    svg = engrave(MEI)
    model = {"notation_events": events(), "groups": explicit_groups()}
    cache = PreprocessingCache(tmp_path)
    assert set(tuplet_fragments([svg], model, cache, "same-score")) == {"outer", "inner"}
    renamed = deepcopy(model)
    renamed["groups"][0]["id"] = "renamed-outer"
    assert set(tuplet_fragments([svg], renamed, cache, "same-score")) == {"renamed-outer", "inner"}


def test_missing_precomposed_font_clef_extracts_real_verovio_compound(monkeypatch):
    from pathlib import Path
    from piano_teacher.notation.assets.glyphs import native_glyphs
    original = Path.is_file
    def available(path):
        return False if path.name == "E051.xml" else original(path)
    native_glyphs.cache_clear()
    monkeypatch.setattr(Path, "is_file", available)
    try:
        glyph = native_glyphs()["clef_g_15mb"]
        assert glyph["source"] == "verovio"
        assert glyph["extraction"] == "engraved-clef"
        assert glyph["bounds"][2] > 0 and glyph["bounds"][3] > 0
        assert "<path" in glyph["svg"]
        assert "E051" in glyph["svg"]
    finally:
        native_glyphs.cache_clear()



def test_opening_marker_id_is_used_as_explicit_source_object_identity():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    groups = explicit_groups()
    for group in groups:
        group["attributes"]["id"] = group["attributes"].pop("source_id")
        group["id"] = "semantic-" + group["id"]
    atlas = extract_tuplets([engrave(MEI)], {"notation_events": events(), "groups": groups})
    assert set(atlas) == {"semantic-outer", "semantic-inner"}


def cross_measure_xml():
    return '''<score-partwise version="4.0"><part-list><score-part id="P">
    <part-name>Piano</part-name></score-part></part-list><part id="P">
    <measure number="1" implicit="yes"><attributes><divisions>3</divisions>
    <time><beats>1</beats><beat-type>4</beat-type></time>
    <clef><sign>G</sign><line>2</line></clef></attributes>
    <note id="a"><pitch><step>C</step><octave>5</octave></pitch><duration>1</duration>
    <type>eighth</type><time-modification><actual-notes>3</actual-notes>
    <normal-notes>2</normal-notes></time-modification><notations>
    <tuplet id="opening" type="start" number="1" bracket="yes"/></notations></note>
    <note id="r"><rest/><duration>1</duration><type>eighth</type><time-modification>
    <actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification></note>
    </measure><measure number="2"><note id="b"><pitch><step>E</step><octave>5</octave>
    </pitch><duration>1</duration><type>eighth</type><time-modification>
    <actual-notes>3</actual-notes><normal-notes>2</normal-notes></time-modification>
    <notations><tuplet type="stop" number="1"/></notations></note></measure>
    </part></score-partwise>'''


def test_authored_cross_measure_rest_tuplet_has_real_engine_compound_ink():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    lane = events()
    for event in lane:
        event.update(note_type="eighth", time_modification={"actual": 3, "normal": 2})
        if event["kind"] == "note":
            event["spelling"] = {"step": "C" if event["id"] == "a" else "E", "octave": 5}
    group = {**explicit_groups()[0], "attributes": {
        "id": "opening", "type": "start", "number": "1", "bracket": "yes"}}
    model = {"notation_events": lane, "groups": [group]}
    before = deepcopy(model)
    atlas = extract_tuplets([engrave(cross_measure_xml())], model)
    assert set(atlas) == {"outer"}
    assert atlas["outer"]["event_ids"] == ["a", "r", "b"]
    ink(atlas["outer"]["number"])
    ink(atlas["outer"]["bracket"])
    assert model == before, "Template engraving cannot change source timing or identities"



def _run_native_asset_draw(tmp_path, glyph_overrides=None):
    import json
    import os
    from pathlib import Path
    import shutil
    import subprocess
    from piano_teacher.notation.assets.glyphs import native_glyphs, _engraved_clef
    from piano_teacher.notation.assets.notes import note_templates
    from piano_teacher.notation.assets.chords import chord_templates
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot unavailable")
    glyphs = dict(native_glyphs())
    glyphs["clef_g_15mb"] = _engraved_clef(glyphs["clef_g"]["font"], "clef_g_15mb", "E051")
    glyphs.update(glyph_overrides or {})
    # Independent test-only reference: the unchanged installed ottava-8
    # contour, not the production compound or the fused E05D numeral.
    import verovio
    from piano_teacher.notation.assets.runtime import _verovio_resources
    resources = _verovio_resources(verovio)
    font = glyphs["clef_c"]["font"]
    metrics = ET.parse(resources / f"{font}.xml").getroot()
    metric = metrics.find("g[@c='E510']")
    x, y, width, height = (float(metric.get(k)) for k in ("x", "y", "w", "h"))
    box = [x-12, -y-height-12, width+24, height+24]
    reference_svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
        viewBox=" ".join(map(str, box)), width=str(box[2]), height=str(box[3]), fill="white")
    reference_svg.append(ET.parse(resources / font / "E510.xml").getroot())
    for node in reference_svg.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    eight_reference = {"svg": ET.tostring(reference_svg, encoding="unicode"),
        "source": "verovio", "code": "E510", "font": font, "bounds": box,
        "ink_bounds": [x, -y-height, width, height],
        "height_units": 233, "clearance_units": 12, "center_x_units": 303}
    chord_events = [{"id": f"c{i}", "kind": "note", "staff": "right", "voice": "1",
        "measure": 1, "beat": 0, "note_type": "128th", "chord": bool(i),
        "spelling": {"step": step, "octave": 4}} for i, step in enumerate("CE")]
    model = {"notation_events": chord_events, "measures": [{"number": 1}]}
    chords = {}
    for direction in (True, False):
        chords.update(chord_templates(model, stem_directions={"c0": direction}))
    tuplets = extract_tuplets([engrave(MEI)], {"notation_events": events(), "groups": explicit_groups()})
    hidden = extract_tuplets([engrave(MEI.replace('bracket.visible="true"',
        'bracket.visible="true" num.visible="false"'))],
        {"notation_events": events(), "groups": explicit_groups()})
    tuplets["hidden"] = hidden["outer"]
    fixture = tmp_path / "assets.json"
    fixture.write_text(json.dumps({"glyphs": glyphs, "notes": note_templates(),
        "chords": chords, "tuplets": tuplets, "octave_eight_reference": eight_reference}))
    root = Path(__file__).resolve().parents[1]
    pixels = bool(os.environ.get("DISPLAY"))
    options = ["--windowed", "--resolution", "1200x900", "--rendering-method", "gl_compatibility"] if pixels else ["--headless"]
    result = subprocess.run([binary, "--path", str(root / "godot"), *options,
        "--script", str(root / "tests/godot/native_complete_assets.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
             "PIANO_TEACHER_ASSET_FIXTURE": str(fixture),
             "PIANO_TEACHER_ASSET_PIXELS": "1" if pixels else "0",
             "PIANO_TEACHER_ASSET_PNG": str(tmp_path / "native-assets.png")},
        capture_output=True, text=True, timeout=60)
    return result, tmp_path / "native-assets.png", pixels


def test_godot_draws_extended_glyphs_compounds_and_distinct_tuplet_ids(tmp_path):
    import json
    result, png_path, pixels = _run_native_asset_draw(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_COMPLETE_ASSET_FAILURES:0" in output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output
    data = json.loads((tmp_path / "assets.json").read_text())
    reference = ET.fromstring(data["octave_eight_reference"]["svg"])
    compound = ET.fromstring(data["glyphs"]["clef_c_8va"]["svg"])
    original_paths = [n.get("d") for n in reference.iter() if n.tag.rsplit("}", 1)[-1] == "path"]
    numeral_paths = [n.get("d") for n in list(compound)[-1].iter()
                     if n.tag.rsplit("}", 1)[-1] == "path"]
    assert original_paths and numeral_paths == original_paths, "C8va must retain the original E510 contour"
    if pixels:
        assert "NATIVE_C_CLEF_PIXEL_CHECKS:3" in output, output
        with Image.open(png_path) as raster:
            assert raster.getchannel("A").getbbox()


@pytest.mark.parametrize("name,wrong_side", [
    ("clef_c_8va", "clef_c_8vb"),
    ("clef_c_15ma", "clef_c_15mb"),
    ("clef_c_15mb", "clef_c_15ma"),
])
@pytest.mark.parametrize("fault", ["missing_numeral", "wrong_side"])
def test_godot_c_clef_pixels_reject_missing_or_misplaced_numerals(tmp_path, name, wrong_side, fault):
    import os
    if not os.environ.get("DISPLAY"):
        pytest.skip("Actual Godot pixel validation requires a display")
    from piano_teacher.notation.assets.glyphs import native_glyphs
    atlas = native_glyphs()
    if fault == "wrong_side":
        corrupted = atlas[wrong_side]
    else:
        corrupted = dict(atlas[name])
        root = ET.fromstring(corrupted["svg"])
        root.remove(list(root)[-1])  # Remove only the original numeral component.
        for node in root.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        root.set("xmlns", "http://www.w3.org/2000/svg")
        corrupted["svg"] = ET.tostring(root, encoding="unicode")
    result, _, pixels = _run_native_asset_draw(tmp_path, {name: corrupted})
    output = result.stdout + result.stderr
    assert pixels
    assert result.returncode == 1, output
    side = "below" if name == "clef_c_15mb" else "above"
    assert f"NATIVE_COMPLETE_ASSET_FAIL: Expected octave numeral {side} for {name}" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output



def test_explicit_source_group_can_include_chord_followers_without_losing_attacks():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    lane, groups = events(), explicit_groups()
    lane.insert(1, {**lane[0], "id": "upper", "chord": True})
    for group in groups:
        group["event_ids"].insert(1, "upper")
    mei = MEI.replace('<note xml:id="a" pname="c" oct="5" dur="8"/>',
        '<chord dur="8"><note xml:id="a" pname="c" oct="5"/>'
        '<note xml:id="upper" pname="g" oct="5"/></chord>')
    atlas = extract_tuplets([engrave(mei)], {"notation_events": lane, "groups": groups})
    assert set(atlas) == {"outer", "inner"}
    assert atlas["outer"]["event_ids"] == ["a", "r", "b"]



def test_authored_musicxml_nested_same_endpoint_tuplets_restore_both_engine_compounds():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    lane, groups = events(), explicit_groups()
    for event in lane:
        event.update(measure=1, note_type="eighth", time_modification={"actual": 15, "normal": 8})
        if event["kind"] == "note":
            event["spelling"] = {"step": "C" if event["id"] == "a" else "E", "octave": 5}
    lane[0]["tuplet_marks"] = [{"type": "start", "number": "1"}, {"type": "start", "number": "2"}]
    lane[-1]["tuplet_marks"] = [{"type": "stop", "number": "2"}, {"type": "stop", "number": "1"}]
    for group, actual, normal in zip(groups, (3, 5), (2, 4)):
        group["attributes"].update(actual=actual, normal=normal, bracket="yes")
        group["attributes"]["id"] = group["attributes"].pop("source_id")
    xml = cross_measure_xml().replace('</measure><measure number="2">', '')
    root = ET.fromstring(xml)
    first = root.find('.//note/notations')
    first.append(ET.fromstring('<tuplet type="start" number="2" bracket="yes">'
        '<tuplet-actual><tuplet-number>5</tuplet-number><tuplet-type>eighth</tuplet-type></tuplet-actual>'
        '<tuplet-normal><tuplet-number>4</tuplet-number><tuplet-type>eighth</tuplet-type></tuplet-normal></tuplet>'))
    last = root.findall('.//note')[-1].find('notations')
    last.insert(0, ET.fromstring('<tuplet type="stop" number="2"/>'))
    # MusicXML's importer currently emits only one group; reconstruction
    # must use each explicit source ratio rather than the combined 15:8.
    atlas = extract_tuplets([engrave(ET.tostring(root, encoding="unicode"))],
                            {"notation_events": lane, "groups": groups})
    assert set(atlas) == {"outer", "inner"}
    assert atlas["outer"]["number"]["png_base64"] != atlas["inner"]["number"]["png_base64"]
    assert abs(atlas["outer"]["number"]["bounds"][1] - atlas["inner"]["number"]["bounds"][1]) > 100



def test_visual_grace_inside_tuplet_does_not_erase_its_timed_group():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    mei = MEI.replace('<note xml:id="a"',
        '<note xml:id="grace" pname="d" oct="5" dur="8" grace="unacc"/>'
        '<note xml:id="a"')
    atlas = extract_tuplets([engrave(mei)], {"notation_events": events(),
        "groups": explicit_groups(), "visual_events": [
            {"id": "grace", "kind": "grace", "anchor_id": "a", "beat": 0}]})
    assert set(atlas) == {"outer", "inner"}
    assert atlas["outer"]["event_ids"] == ["a", "r", "b"]



def test_source_hidden_tuplet_numeral_does_not_get_invented_by_native_assets():
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    mei = MEI.replace('bracket.visible="true"', 'bracket.visible="true" num.visible="false"')
    atlas = extract_tuplets([engrave(mei)], {"notation_events": events(), "groups": explicit_groups()})
    assert set(atlas) == {"outer", "inner"}
    for item in atlas.values():
        assert item["number"] is None
        ink(item["bracket"])



def test_legacy_same_endpoint_nested_groups_keep_separate_stable_ids():
    from piano_teacher.notation.assets.tuplets import extract_tuplets, semantic_tuplets
    lane = events()
    for event in lane:
        event["measure"] = 1
    lane[0]["tuplet_marks"] = [{"type": "start", "number": "1"}, {"type": "start", "number": "2"}]
    lane[-1]["tuplet_marks"] = [{"type": "stop", "number": "2"}, {"type": "stop", "number": "1"}]
    model = {"notation_events": lane}
    expected = {"tuplet:right:1:1:a:b", "tuplet:right:1:2:a:b"}
    assert set(semantic_tuplets(model)) == expected
    atlas = extract_tuplets([engrave(MEI)], model)
    assert set(atlas) == expected
    assert atlas["tuplet:right:1:1:a:b"]["number"]["png_base64"] != atlas["tuplet:right:1:2:a:b"]["number"]["png_base64"]



@pytest.mark.parametrize("fixture_name", ["xml_nested_cross_measure_tuplets.musicxml",
                                         "xml_rest_tuplets.musicxml"])
def test_projected_nested_cross_measure_fixture_uses_its_actual_numerals(fixture_name):
    import runpy
    from pathlib import Path
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    compile_fixture = runpy.run_path(str(Path(__file__).with_name(
        "test_advanced_source_notation.py")))["compile_fixture"]
    _, score, model = compile_fixture(fixture_name)
    groups = [g for g in model["groups"] if g["kind"] == "tuplet" and len(g["event_ids"]) > 1]
    atlas = extract_tuplets([engrave(score.musicxml)], model)
    assert set(atlas) == {g["id"] for g in groups}
    for group in groups:
        fragment = atlas[group["id"]]
        assert fragment["display_number"] == "3"
        assert fragment["event_ids"] == group["event_ids"]
        ink(fragment["number"])
        ink(fragment["bracket"])
    outer = max(groups, key=lambda g: len(g["event_ids"]))
    inner = min(groups, key=lambda g: len(g["event_ids"]))
    assert abs(atlas[outer["id"]]["number"]["bounds"][1] - atlas[inner["id"]]["number"]["bounds"][1]) > 100



@pytest.mark.parametrize("fixture_name", ["xml_nested_cross_measure_tuplets.musicxml",
                                         "xml_rest_tuplets.musicxml"])
def test_native_tuplets_layout_uses_projected_ids_rests_and_one_linear_axis(tmp_path, fixture_name):
    import json
    import os
    from pathlib import Path
    import runpy
    import shutil
    import subprocess
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    binary = shutil.which("godot") or shutil.which("godot4")
    if not binary:
        pytest.skip("Godot unavailable")
    compile_fixture = runpy.run_path(str(Path(__file__).with_name(
        "test_advanced_source_notation.py")))["compile_fixture"]
    _, score, model = compile_fixture(fixture_name)
    fixture = tmp_path / "tuplets.json"
    fixture.write_text(json.dumps({"model": model,
        "expected_rest_members": 8 if fixture_name == "xml_rest_tuplets.musicxml" else 2,
        "tuplets": extract_tuplets([engrave(score.musicxml)], model)}))
    root = Path(__file__).resolve().parents[1]
    pixels = bool(os.environ.get("DISPLAY"))
    options = ["--windowed", "--resolution", "640x520", "--rendering-method", "gl_compatibility"] if pixels else ["--headless"]
    result = subprocess.run([binary, *options, "--path", str(root / "godot"),
        "--script", str(root / "tests/godot/native_tuplets_layout.gd")],
        env={**os.environ, "PIANO_TEACHER_NATIVE_NOTATION": "1",
             "PIANO_TEACHER_TUPLETS_PIXELS": "1" if pixels else "0",
             "PIANO_TEACHER_TUPLETS_FIXTURE": str(fixture)},
        capture_output=True, text=True, timeout=60)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "NATIVE_TUPLETS_LAYOUT_FAILURES:0" in output, output
    assert "SCRIPT ERROR" not in output and "Parse Error" not in output, output



def test_missing_crossbar_outer_restores_the_entire_source_bound_nested_compound():
    import runpy
    from pathlib import Path
    from piano_teacher.notation.assets.tuplets import extract_tuplets
    compile_fixture = runpy.run_path(str(Path(__file__).with_name(
        "test_advanced_source_notation.py")))["compile_fixture"]
    _, score, model = compile_fixture("xml_nested_cross_measure_tuplets.musicxml")
    groups = [g for g in model["groups"] if len(g["event_ids"]) > 1]
    atlas = extract_tuplets([engrave(score.musicxml)], model)
    outer = max(groups, key=lambda group: len(group["event_ids"]))
    assert set(atlas) == {group["id"] for group in groups}
    assert {item.get("engraving") for item in atlas.values()} == {"group-template"}
    assert {item.get("compound_id") for item in atlas.values()} == {outer["id"]}
