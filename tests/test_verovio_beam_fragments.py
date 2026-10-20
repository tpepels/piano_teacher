"""Extract the original Verovio beam ink without copying source noteheads."""
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.verovio_beam_fragments import (
    _filter_beam_svg, beam_fragments, extract_beam_fragments,
    expected_beam_groups,
)


SVG = '''<svg xmlns="http://www.w3.org/2000/svg" width="800" height="200"
 viewBox="0 0 800 200">
 <defs><path id="a" d="M0 0L2 0" /></defs>
 <g class="beam" id="b1">
  <polygon points="111,25 420,25 420,32 111,32" fill="#fff"/>
  <g class="note" id="n1"><circle cx="100" cy="100" r="8"/></g>
  <g class="note" id="n2"><circle cx="400" cy="100" r="8"/></g>
 </g>
 <g class="staff"><line x1="10" x2="790" y1="85" y2="85"/></g>
 </svg>'''

MODEL = {"notation_events": [
    {"id":"n1","kind":"note","staff":"right","voice":"1","measure":1,
     "beat":0.0,"chord":False},
    {"id":"n2","kind":"note","staff":"right","voice":"1","measure":1,
     "beat":0.5,"chord":False},
]}


def test_extract_exactly_beam_ink_not_heads_or_staff():
    svg=_filter_beam_svg(SVG,("n1","n2"))
    assert svg is not None
    root=ET.fromstring(svg)
    all_classes=[n.get("class","") for n in root.iter()]
    assert "beam" in all_classes
    assert "note" not in all_classes
    assert "staff" not in all_classes
    assert any(n.tag.endswith("polygon") for n in root.iter())
    assert _filter_beam_svg(SVG,("n2","n1")) is None


def test_original_two_anchors_and_measured_stem_tips(monkeypatch,tmp_path):
    import piano_teacher.notation.assets.svg_geometry as geometry
    def model_geometry(svg):
        return SimpleNamespace(
            elements={"n1":(.125,.5,"s1"),"n2":(.5,.5,"s1")},
            staff_systems={"s1":{"staff_lines":[.35,.45,.55,.65,.75]}})
    monkeypatch.setattr(geometry,"parse_svg_geometry",model_geometry)
    fragments=extract_beam_fragments([SVG],MODEL)
    assert list(fragments)==["n1|n2"]
    item=fragments["n1|n2"]
    assert item["source"]=="verovio-engraved-beam"
    assert item["note_ids"]==["n1","n2"]
    assert item["stem_up"] is True
    assert item["span"]>0 and len(item["bounds"])==4
    assert len(item["tip_offsets"])==2
    assert all(offset < -600 for offset in item["tip_offsets"])

    from piano_teacher.notation.assets import beams as native
    cache=PreprocessingCache(tmp_path)
    first=beam_fragments([SVG],MODEL,cache,"same-score-revision")
    assert first==fragments
    monkeypatch.setattr(native,"extract_beam_fragments",
                        lambda *args: (_ for _ in ()).throw(
                            AssertionError("Versioned beam cache miss")))
    assert beam_fragments([SVG],MODEL,
                          PreprocessingCache(tmp_path),"same-score-revision")==first

 
def test_source_beams_are_authoritative_not_inferred_from_meter():
    assert expected_beam_groups([SVG], MODEL) == ["n1|n2"]
    other = {"notation_events":[{**event, "id":"renamed"} if
             event["id"] == "n2" else event for event in MODEL["notation_events"]]}
    assert expected_beam_groups([SVG], other) == []


def test_beam_mismatch_does_not_invent_a_symbol():
    altered={"notation_events":[{**MODEL["notation_events"][0],"id":"different"},
                                MODEL["notation_events"][1]]}
    assert extract_beam_fragments([SVG],altered)=={}
    assert _filter_beam_svg(SVG,("not-there","n2")) is None


def test_three_note_beam_has_every_original_musical_anchor(monkeypatch):
    """The middle note must not inherit Verovio's printed page spacing."""
    import piano_teacher.notation.assets.svg_geometry as geometry

    multi_svg=SVG.replace(
        '<g class="note" id="n2">',
        '<g class="note" id="n3"><circle cx="310" cy="100" r="8"/></g>'
        '<g class="note" id="n2">')
    multi_model={"notation_events":[
        MODEL["notation_events"][0],
        {"id":"n3","kind":"note","staff":"right","voice":"1",
         "measure":1,"beat":0.25,"chord":False},
        MODEL["notation_events"][1]
    ]}
    monkeypatch.setattr(geometry,"parse_svg_geometry",lambda svg:SimpleNamespace(
        elements={"n1":(.125,.5,"s1"),"n3":(.3875,.5,"s1"),
                  "n2":(.5,.5,"s1")},
        staff_systems={"s1":{"staff_lines":[.35,.45,.55,.65,.75]}}))
    atlas=extract_beam_fragments([multi_svg],multi_model)
    assert list(atlas)==["n1|n3|n2"]
    result=atlas["n1|n3|n2"]
    assert result["note_ids"]==["n1","n3","n2"]
    assert len(result["tip_offsets"])==3
    assert len(result["head_offsets"])==3
    assert result["head_offsets"][0] == 0
    assert 0 < result["head_offsets"][1] < result["head_offsets"][2]
    # The native renderer will map three original image anchors to the
    # three independent timestamps (0, .25, .5), not stretch the whole PNG.


def test_two_real_musicxml_eighths_produce_native_verovio_beam(monkeypatch):
    monkeypatch.setenv("PIANO_TEACHER_BEAM_DEBUG","1")
    """A real Verovio wheel must export the SVG classes we extract."""
    import verovio
    from piano_teacher.score import _create_verovio_toolkit

    notation = """<score-partwise version="4.0"><work><work-title> </work-title></work>
      <movement-title> </movement-title><part-list>
      <score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
      <part id="P1"><measure number="1"><attributes><divisions>10080</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note id="n1"><pitch><step>G</step><octave>4</octave></pitch>
      <duration>5040</duration><type>eighth</type><stem>up</stem>
      <beam number="1">begin</beam></note>
      <note id="n2"><pitch><step>B</step><octave>4</octave></pitch>
      <duration>5040</duration><type>eighth</type><stem>up</stem>
      <beam number="1">end</beam></note>
      <note><rest/><duration>30240</duration><type>half</type><dot/></note>
      </measure></part></score-partwise>"""
    toolkit = _create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom":"xml","scale":48,"pageWidth":900,
                               "pageHeight":650,"svgViewBox":True,
                               "svgBoundingBoxes":True,
                               "svgContentBoundingBoxes":True})
    assert toolkit.loadData(notation)
    page = toolkit.renderToSVG(1)
    from piano_teacher.score_geometry import parse_svg_geometry
    page_geometry = parse_svg_geometry(page)
    assert {"n1","n2"}.issubset(page_geometry.elements)
    result = extract_beam_fragments([page], MODEL)
    if "n1|n2" not in result:
        print("SOURCE_BEAM_CLASSES:", [
            (el.get("class",""),el.get("id",""))
            for el in ET.fromstring(page).iter()
            if ("beam" in el.get("class","").lower()
                or "note" in el.get("class","").split())][:20])
    assert "n1|n2" in result, (
        "Genuine Verovio beam group could not be detached as a graphic")
    assert result["n1|n2"]["note_ids"] == ["n1","n2"]
    assert len(result["n1|n2"]["head_offsets"]) == 2
    assert len(result["n1|n2"]["tip_offsets"]) == 2


def test_diagnostic_svg_bounding_boxes_do_not_create_fake_notes():
    # Verovio's real svgBoundingBoxes output uses e.g. class="note
    # content-bounding-box" alongside each genuine note.
    from piano_teacher.verovio_beam_fragments import _note_ids
    group = ET.fromstring('''<g class="beam">
      <g class="note" id="n1"/>
      <g class="note content-bounding-box" id="cbbox-n1"/>
      <g class="note bounding-box" id="bbox-n1"/>
      <g class="note" id="n2"/>
      <g class="note content-bounding-box" id="cbbox-n2"/>
    </g>''')
    assert _note_ids(group) == ("n1","n2")


def test_verovio_beamed_chord_keeps_one_attack_and_all_pitches(monkeypatch):
    import piano_teacher.notation.assets.svg_geometry as geometry
    svg=SVG.replace(
        '<g class="note" id="n1"><circle cx="100" cy="100" r="8"/></g>',
        '<g class="chord"><g class="note" id="n1">'
        '<circle cx="100" cy="100" r="8"/></g>'
        '<g class="note" id="n1upper">'
        '<circle cx="100" cy="80" r="8"/></g></g>')
    score={"notation_events":[
        MODEL["notation_events"][0],
        {**MODEL["notation_events"][0],"id":"n1upper",
         "chord":True},
        MODEL["notation_events"][1]]}
    monkeypatch.setattr(geometry,"parse_svg_geometry",lambda _:SimpleNamespace(
        elements={"n1":(.125,.50,"s1"),"n1upper":(.125,.45,"s1"),
                  "n2":(.5,.5,"s1")},
        staff_systems={"s1":{"staff_lines":[.35,.45,.55,.65,.75]}}))
    fragment=extract_beam_fragments([svg],score)
    assert list(fragment)==["n1|n2"]
    item=fragment["n1|n2"]
    assert item["note_ids"]==["n1","n2"]
    assert item["chord_note_ids"]==[["n1","n1upper"],["n2"]]
    assert len(item["tip_offsets"])==2
    assert len(item["head_offsets"])==2


def test_original_verovio_beamed_chord_has_only_two_time_anchors():
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    score = """<score-partwise version="4.0"><work><work-title> </work-title></work>
      <movement-title> </movement-title><part-list><score-part id="P1">
      <part-name>Piano</part-name></score-part></part-list>
      <part id="P1"><measure number="1"><attributes><divisions>10080</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>
      <note id="n1"><pitch><step>G</step><octave>4</octave></pitch>
      <duration>5040</duration><type>eighth</type><stem>up</stem>
      <beam number="1">begin</beam></note>
      <note id="n1upper"><chord/><pitch><step>B</step><octave>4</octave></pitch>
      <duration>5040</duration><type>eighth</type></note>
      <note id="n2"><pitch><step>C</step><octave>5</octave></pitch>
      <duration>5040</duration><type>eighth</type><stem>up</stem>
      <beam number="1">end</beam></note>
      <note><rest/><duration>30240</duration><type>half</type><dot/></note>
      </measure></part></score-partwise>"""
    model={"notation_events":[
        MODEL["notation_events"][0],
        {**MODEL["notation_events"][0], "id":"n1upper",
         "chord":True},
        MODEL["notation_events"][1]]}
    toolkit=_create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom":"xml","scale":48,"pageWidth":900,
          "pageHeight":650,"svgViewBox":True,"svgBoundingBoxes":True,
          "svgContentBoundingBoxes":True})
    assert toolkit.loadData(score)
    page=toolkit.renderToSVG(1)
    found=extract_beam_fragments([page],model)
    assert "n1|n2" in found
    assert found["n1|n2"]["chord_note_ids"]==[
        ["n1","n1upper"],["n2"]]
