"""Complex original Verovio slurs must preserve paired note identity."""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.verovio_slur_fragments import (
    slur_pairs_from_xml,extract_slurs,slur_fragments,
)

PART = """<score-partwise version="4.0"><part-list><score-part id="P1">
<part-name>Piano</part-name></score-part></part-list>
<part id="P1"><measure number="1"><attributes>
<divisions>10080</divisions><time><beats>4</beats><beat-type>4</beat-type>
</time><clef><sign>G</sign><line>2</line></clef></attributes>
<note id="a"><pitch><step>G</step><octave>4</octave></pitch>
<duration>10080</duration><type>quarter</type><notations>
<slur number="1" type="start"/></notations></note>
<note id="b"><pitch><step>A</step><octave>4</octave></pitch>
<duration>10080</duration><type>quarter</type></note>
<note id="c"><pitch><step>B</step><octave>4</octave></pitch>
<duration>10080</duration><type>quarter</type><notations>
<slur number="1" type="stop"/></notations></note>
<note><rest/><duration>10080</duration><type>quarter</type></note>
</measure></part></score-partwise>"""

MODEL={"notation_events":[
    {"kind":"note","id":c,"beat":i,"staff":"right","voice":"1",
     "measure":1} for i,c in enumerate(("a","b","c"))
]}
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"
 viewBox="0 0 800 400">
 <g class="slur" id="slur-x"><path d="M100 142Q260 108 420 142
 Q260 120 100 142" fill="#111"/></g></svg>"""


def fake_geometry(_):
    return SimpleNamespace(elements={
        "a":(.125,.5,"s1"),"b":(.325,.475,"s1"),
        "c":(.525,.5,"s1")},
        staff_systems={"s1":{"staff_lines":[.55,.575,.6,.625,.65]}})


def test_explicit_musicxml_slur_pair_is_not_inferred_from_time():
    assert slur_pairs_from_xml(PART)==(("a","c"),)
    xml=PART.replace('<slur number="1" type="start"/>',"")
    assert slur_pairs_from_xml(xml)==()


def test_extract_only_genuine_slur_and_reuse_cache(tmp_path,monkeypatch):
    import piano_teacher.score_geometry as geometry
    monkeypatch.setattr(geometry,"parse_svg_geometry",fake_geometry)
    result=extract_slurs([SVG],PART,MODEL)
    assert list(result)==["a|c"]
    slur=result["a|c"]
    assert slur["source"]=="verovio-engraved-slur"
    assert slur["note_ids"]==["a","c"]
    assert len(slur["bounds"])==4
    assert slur["span"]>0
    assert abs(slur["original_end_y"])<.01
    cache=PreprocessingCache(tmp_path)
    assert slur_fragments([SVG],PART,MODEL,cache,"slur-piece")==result
    monkeypatch.setattr(
        "piano_teacher.verovio_slur_fragments.extract_slurs",
        lambda *_: (_ for _ in ()).throw(
            AssertionError("A previously saved slur should not rerender")))
    assert slur_fragments([SVG],PART,MODEL,
                          PreprocessingCache(tmp_path),"slur-piece")==result


def test_ambiguous_slurs_refuse_to_guess(monkeypatch):
    import piano_teacher.score_geometry as geometry
    monkeypatch.setattr(geometry,"parse_svg_geometry",fake_geometry)
    doubled=SVG.replace("</svg>",
        '<g class="slur" id="another">'
        '<path d="M100 142Q260 108 420 142Q260 120 100 142"/></g></svg>')
    assert extract_slurs([doubled],PART,MODEL)=={}


def test_real_verovio_source_slur_export():
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    from piano_teacher.score_geometry import parse_svg_geometry
    kit=_create_verovio_toolkit(verovio)
    assert kit.setOptions({"inputFrom":"xml","scale":48,
        "pageWidth":900,"pageHeight":650,"svgViewBox":True,
        "svgBoundingBoxes":True,"svgContentBoundingBoxes":True})
    assert kit.loadData(PART)
    svg=kit.renderToSVG(1)
    assert {"a","c"}.issubset(parse_svg_geometry(svg).elements)
    slurs=extract_slurs([svg],PART,MODEL)
    if not slurs:
        print("ACTUAL_VEROVIO_SLUR_CLASSES",[
            (el.get("class"),el.get("id"))
            for el in ET.fromstring(svg).iter()
            if "slur" in el.get("class","")][:20])
    assert "a|c" in slurs
