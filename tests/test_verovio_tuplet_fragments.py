"""Original Verovio tuplet graphics, source IDs and independent time anchors."""
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.verovio_tuplet_fragments import (
    semantic_tuplets, extract_tuplets, tuplet_fragments, isolate, source_ids,
)

XML = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="400"
viewBox="0 0 800 400">
<g class="tuplet" id="triplet1">
 <g class="tupletBracket"><path d="M100 60L100 50L420 50L420 60"
      fill="none" stroke="black" stroke-width="3"/></g>
 <g class="tupletNum"><text x="256" y="45" font-size="18">3</text></g>
 <g class="note" id="n1"><circle cx="100" cy="200" r="10"/></g>
 <g class="note content-bounding-box" id="cbbox-n1"/>
 <g class="note" id="n2"><circle cx="250" cy="190" r="10"/></g>
 <g class="note" id="n3"><circle cx="420" cy="200" r="10"/></g>
</g><path class="staff" d="M0 250L800 250"/></svg>"""

MODEL = {"notation_events":[
    {"kind":"note","staff":"right","voice":"1","measure":1,
     "beat":i/3,"id":f"n{i+1}","chord":False,
     "tuplet_marks":(
         [{"type":"start","number":"1"}] if i==0 else
         [{"type":"stop","number":"1"}] if i==2 else [])}
    for i in range(3)
]}


def test_extract_separate_genuine_tuplet_bracket_and_number(tmp_path,monkeypatch):
    import piano_teacher.score_geometry as geometry
    monkeypatch.setattr(geometry,"parse_svg_geometry",lambda _:SimpleNamespace(
        elements={"n1":(.125,.5,"staff1"),"n2":(.3125,.475,"staff1"),
                  "n3":(.525,.5,"staff1")},
        staff_systems={"staff1":{"staff_lines":[.55,.575,.6,.625,.65]}}))
    atlas=extract_tuplets([XML],MODEL)
    assert list(atlas)==["n1|n2|n3"]
    item=atlas["n1|n2|n3"]
    assert item["note_ids"]==["n1","n2","n3"]
    assert item["span"]>0
    for kind in ("number","bracket"):
        assert item[kind]["source"]==f"verovio-tuplet-{kind}"
        assert len(item[kind]["bounds"])==4
        assert len(item[kind]["png_base64"])>80
    assert item["number"]["png_base64"] != item["bracket"]["png_base64"]
    assert semantic_tuplets(MODEL)=={("n1","n2","n3"):{"staff":"right"}}
    cache=PreprocessingCache(tmp_path)
    assert tuplet_fragments([XML],MODEL,cache,"example")==atlas
    monkeypatch.setattr(
        "piano_teacher.notation.assets.tuplets.extract_tuplets",
        lambda *_: (_ for _ in ()).throw(AssertionError("re-engraved cached tuplet")))
    assert tuplet_fragments([XML],MODEL,
                             PreprocessingCache(tmp_path),"example")==atlas


def test_diagnostic_bbox_not_a_source_note():
    root=ET.fromstring(XML)
    target=next(n for n in root.iter() if "tuplet" in
                n.get("class","").split())
    assert source_ids(target)==("n1","n2","n3")
    number=next(n for n in target.iter() if "tupletNum" in
                n.get("class","").split())
    xml=isolate(root,number)
    assert "tupletNum" in xml
    assert 'id="n1"' not in xml
    assert "tupletBracket" not in xml


def test_tuplets_require_explicit_musicxml_boundaries():
    unknown={"notation_events":[{**n,"tuplet_marks":[]} for n in
                                MODEL["notation_events"]]}
    assert semantic_tuplets(unknown)=={}
    assert extract_tuplets([XML],unknown)=={}


def test_real_verovio_exports_explicit_triplet_bracket():
    """Catches mistaken assumptions about SVG classes in installed Verovio."""
    import verovio
    from piano_teacher.score import _create_verovio_toolkit
    from piano_teacher.score_geometry import parse_svg_geometry
    notes=[]
    for i in range(3):
        marks=(f'<notations><tuplet type="{"start" if i==0 else "stop"}"'
               ' number="1" bracket="yes" show-number="actual"/></notations>'
               if i in (0,2) else '')
        notes.append(f'<note id="n{i+1}"><pitch><step>'
          f'{"CDE"[i]}</step><octave>5</octave></pitch><duration>3360</duration>'
          f'<type>eighth</type><time-modification>'
          f'<actual-notes>3</actual-notes><normal-notes>2</normal-notes>'
          f'</time-modification>{marks}</note>')
    score=('''<score-partwise version="4.0"><work><work-title> </work-title></work>
      <movement-title> </movement-title><part-list>
      <score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
      <part id="P1"><measure number="1"><attributes><divisions>10080</divisions>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>G</sign><line>2</line></clef></attributes>'''
      + "".join(notes) +
      '''<note><rest/><duration>30240</duration><type>half</type><dot/></note>
      </measure></part></score-partwise>''')
    toolkit=_create_verovio_toolkit(verovio)
    assert toolkit.setOptions({"inputFrom":"xml","scale":48,
        "pageWidth":900,"pageHeight":650,"svgViewBox":True,
        "svgBoundingBoxes":True,"svgContentBoundingBoxes":True})
    assert toolkit.loadData(score)
    original=toolkit.renderToSVG(1)
    assert {"n1","n2","n3"}.issubset(parse_svg_geometry(original).elements)
    atlas=extract_tuplets([original],MODEL)
    if not atlas:
        classes=[(n.get("class"),n.get("id")) for n in
                 ET.fromstring(original).iter()
                 if "tuplet" in n.get("class","").lower()]
        print("ACTUAL_VEROVIO_TUPLET_CLASSES",classes[:20])
        from piano_teacher.verovio_tuplet_fragments import crop_art
        from piano_teacher.score_geometry import parse_svg_geometry
        geom=parse_svg_geometry(original)
        first=geom.elements["n1"]
        last=geom.elements["n3"]
        space=geom.staff_systems[first[2]]["staff_lines"]
        print("ACTUAL_TUPLET_ANCHORS",first,last,"staff",space)
        from piano_teacher.verovio_tuplet_fragments import isolate, source_ids
        tree=ET.fromstring(original)
        for node in tree.iter():
            if node.get("class")=="tuplet":
                print("TUPLET_NESTED_IDS",source_ids(node))
                for element in node.iter():
                    if element.get("class") in ("tupletNum","tupletBracket"):
                        try:
                            raster=crop_art(isolate(tree,element),
                                space[1]-space[0],(first[0],first[1]),
                                element.get("class"))
                            print("TUPLET_REAL_ART",element.get("class"),
                                  raster and raster["bounds"])
                        except Exception as err:
                            print("TUPLET_ART_ERROR",type(err).__name__,str(err))
    assert "n1|n2|n3" in atlas
    assert atlas["n1|n2|n3"]["number"]
