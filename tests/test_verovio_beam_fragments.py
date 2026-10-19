"""Extract the original Verovio beam ink without copying source noteheads."""
from types import SimpleNamespace
from xml.etree import ElementTree as ET

from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.verovio_beam_fragments import (
    _filter_beam_svg, beam_fragments, extract_beam_fragments,
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
    import piano_teacher.score_geometry as geometry
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

    import piano_teacher.verovio_beam_fragments as native
    cache=PreprocessingCache(tmp_path)
    first=beam_fragments([SVG],MODEL,cache,"same-score-revision")
    assert first==fragments
    monkeypatch.setattr(native,"extract_beam_fragments",
                        lambda *args: (_ for _ in ()).throw(
                            AssertionError("Versioned beam cache miss")))
    assert beam_fragments([SVG],MODEL,
                          PreprocessingCache(tmp_path),"same-score-revision")==first


def test_beam_mismatch_does_not_invent_a_symbol():
    altered={"notation_events":[{**MODEL["notation_events"][0],"id":"different"},
                                MODEL["notation_events"][1]]}
    assert extract_beam_fragments([SVG],altered)=={}
    assert _filter_beam_svg(SVG,("not-there","n2")) is None
