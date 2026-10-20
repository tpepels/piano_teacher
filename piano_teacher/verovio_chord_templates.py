"""Actual Verovio-rendered chord sprites indexed by diatonic interval pattern.

Only isolated chord attacks (not a beat shared with a beam group) can use a
fixed sprite. The atlas stores exact notehead positions for independent dots,
ledger lines and accidentals. Rhythmic timing never comes from SVG positions.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from io import BytesIO
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 5
MAX_PATTERNS = 256
_STEPS = {"C":0,"D":1,"E":2,"F":3,"G":4,"A":5,"B":6}
_LETTERS = "CDEFGAB"
_BEATS = {"whole":4.0,"half":2.0,"quarter":1.0,"eighth":.5,
          "16th":.25,"32nd":.125,"64th":.0625}


def diatonic(spelling: dict) -> int:
    return int(spelling["octave"])*7+_STEPS[spelling["step"]]


def chord_pattern(leader: dict, notes: list[dict], measure: dict) -> str | None:
    if not 2 <= len(notes) <= 10:
        return None
    kind = str(leader.get("note_type",""))
    if kind not in _BEATS or any(n.get("note_type") != kind for n in notes):
        return None
    try:
        absolute = [diatonic(n["spelling"]) for n in notes]
    except (KeyError,TypeError,ValueError):
        return None
    if len(set(absolute)) != len(absolute) or max(absolute)-min(absolute)>28:
        return None
    staff = leader.get("staff","right")
    clef = measure.get("clefs",{}).get(staff,{})
    sign = clef.get("sign","G" if staff=="right" else "F")
    line = int(clef.get("line",2 if staff=="right" else 4))
    octave_change = int(clef.get("octave_change",0))
    anchor = {"G":32,"F":24,"C":28}.get(sign)
    if anchor is None:
        return None
    bottom = anchor-(line-1)*2+octave_change*7
    up = sum(p-bottom for p in absolute)/len(absolute)<4
    direction = "up" if up else "down"
    differences = sorted(p-diatonic(leader["spelling"]) for p in absolute)
    return f"{kind}|{direction}|{','.join(map(str,differences))}"


def patterns_from_model(model: dict) -> list[str]:
    measures = {int(m["number"]):m for m in model.get("measures",[])}
    lanes = defaultdict(list)
    for e in model.get("notation_events",[]):
        if e.get("kind")=="note":
            key=(e.get("staff"),str(e.get("voice","1")),int(e.get("measure",0)),
                 round(float(e.get("beat",0)),6))
            lanes[key].append(e)
    patterns = set()
    for (_,_,measure_id,_), notes in lanes.items():
        leaders = [n for n in notes if not n.get("chord")]
        if len(leaders)!=1 or len(notes)<2 or measure_id not in measures:
            continue
        pattern = chord_pattern(leaders[0],notes,measures[measure_id])
        if pattern:
            patterns.add(pattern)
    if len(patterns) > MAX_PATTERNS:
        raise ValueError("Too many distinct source chord patterns for native engraving")
    return sorted(patterns)


def _xml(pattern: str) -> str:
    kind,direction,relative = pattern.split("|")
    offsets = [int(n) for n in relative.split(",")]
    # B4 is a neutral reference with no key signature or accidentals.
    base = 34
    duration = round(_BEATS[kind]*10080)
    notes = []
    for i,offset in enumerate(offsets):
        index = base+offset
        octave,step = divmod(index,7)
        extra = "<chord/>" if i else ""
        stem = f"<stem>{direction}</stem>" if i==0 and kind!="whole" else ""
        notes.append(f'<note id="c{i}">{extra}<pitch><step>{_LETTERS[step]}</step>'
                     f'<octave>{octave}</octave></pitch>'
                     f'<duration>{duration}</duration><type>{kind}</type>{stem}</note>')
    notes_xml="".join(notes)
    return (f'<score-partwise version="4.0"><work><work-title> </work-title></work>'
            f'<movement-title> </movement-title><part-list><score-part id="P1">'
            f'<part-name>Piano</part-name></score-part></part-list>'
            f'<part id="P1"><measure number="1"><attributes>'
            f'<divisions>10080</divisions><time><beats>4</beats>'
            f'<beat-type>4</beat-type></time><clef><sign>G</sign>'
            f'<line>2</line></clef></attributes>{notes_xml}</measure></part>'
            f'</score-partwise>')


def _extract_chord(svg: str, ids: set[str]) -> str:
    root=ET.fromstring(svg)
    target=next((node for node in root.iter()
                 if "chord" in node.get("class","").split() and
                 ids.issubset({c.get("id") for c in node.iter()})),None)
    if target is None:
        raise ValueError("Verovio chord enclosure missing (refuse fake engraving)")

    def trim(node):
        if node is target:
            for parent in node.iter():
                for child in list(parent):
                    if set(child.get("class","").split()) & {
                            "bounding-box","content-bounding-box"}:
                        parent.remove(child)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        keep=False
        for child in list(node):
            if trim(child):
                keep=True
            else:
                node.remove(child)
        return keep
    trim(root)
    return ET.tostring(root,encoding="unicode")


def _only_original_chord_heads(svg: str) -> str:
    """Keep Verovio's chord notehead ink and collisions, omitting stems.

    The original SVG coordinates and notehead displacement are unchanged.
    This can be overlaid on an independently positioned source beam.
    """
    root=ET.fromstring(svg)
    omitted={"stem","flag","beam","dots","dot","accid","artic",
             "tie","slur","tuplet","ledgerLines","ledgerLine","ledger",
             "bounding-box","content-bounding-box"}
    def visit(parent):
        for child in list(parent):
            if set(child.get("class","").split()) & omitted:
                parent.remove(child)
            else:
                visit(child)
    visit(root)
    return ET.tostring(root,encoding="unicode")


def _only_original_chord_stems(svg: str) -> str:
    """Extract original Verovio stem ink, not a synthetic rectangle."""
    root=ET.fromstring(svg)
    def prune(node):
        if "stem" in node.get("class","").split():
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        retained=False
        for child in list(node):
            if prune(child):
                retained=True
            else:
                node.remove(child)
        return retained
    prune(root)
    return ET.tostring(root,encoding="unicode")


def _render(toolkit,pattern: str) -> dict:
    import cairosvg
    from .score_geometry import parse_svg_geometry
    if not toolkit.loadData(_xml(pattern)):
        raise ValueError("Verovio refused chord sample")
    svg = toolkit.renderToSVG(1)
    g = parse_svg_geometry(svg)
    names={f"c{index}" for index in range(len(pattern.split("|")[2].split(",")))}
    if not names.issubset(g.elements):
        raise ValueError("Verovio chord notehead anchor IDs missing")
    # Normalization is relative to the actual MusicXML chord leader.
    # It need not be the lowest note: preserve the zero-offset head.
    offsets=[int(n) for n in pattern.split("|")[2].split(",")]
    anchor=g.elements[f"c{offsets.index(0)}"]
    rails=g.staff_systems[anchor[2]]["staff_lines"]
    filtered=_extract_chord(svg,names)
    with Image.open(BytesIO(cairosvg.svg2png(
            bytestring=filtered.encode(),output_width=1600))) as image:
        rgba=image.convert("RGBA")
    # A second asset contains ONLY the complete, displaced original
    # Verovio chord heads, with stems/flags removed. Beamed attacks use
    # this asset so the source Verovio beam can be rendered separately.
    heads_svg=_only_original_chord_heads(filtered)
    with Image.open(BytesIO(cairosvg.svg2png(
            bytestring=heads_svg.encode(),output_width=1600))) as image:
        heads_rgba=image.convert("RGBA")
    with Image.open(BytesIO(cairosvg.svg2png(
            bytestring=_only_original_chord_stems(filtered).encode(),
            output_width=1600))) as image:
        stems_rgba=image.convert("RGBA")
    bbox=rgba.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty genuine chord sprite")
    staff=(rails[1]-rails[0])*rgba.height
    if staff<=2:
        raise ValueError("Invalid chord staff spacing")
    from .notation_symbols import native_glyphs
    head=native_glyphs()["head_black"]["bounds"]
    dx=(head[0]+head[2]*.5)*staff/250
    note_x=anchor[0]*rgba.width+dx
    note_y=anchor[1]*rgba.height
    left,top,right,bottom=bbox
    bitmap=rgba.crop(bbox)
    white=Image.new("RGBA",bitmap.size,(255,255,255,255))
    white.putalpha(bitmap.getchannel("A"))
    stream=BytesIO()
    white.save(stream,format="PNG",optimize=True)
    box=[(left-note_x)*250/staff,(top-note_y)*250/staff,
         (right-left)*250/staff,(bottom-top)*250/staff]
    positions=[]
    for name in sorted(names,key=lambda i:int(i[1:])):
        x,y,_=g.elements[name]
        positions.append([(x*rgba.width+dx-note_x)*250/staff,
                          (y*rgba.height-note_y)*250/staff])
    if not all(math.isfinite(v) for v in box+[
            coordinate for pos in positions for coordinate in pos]):
        raise ValueError("Nonfinite Verovio chord geometry")
    result={"source":"verovio-engraved-chord","bounds":box,
            "units_per_space":250,"head_positions":positions,
            "png_base64":base64.b64encode(stream.getvalue()).decode("ascii")}
    head_bbox=heads_rgba.getchannel("A").getbbox()
    if head_bbox:
        hx,hy,hr,hb=head_bbox
        cropped=heads_rgba.crop(head_bbox)
        head_ink=Image.new("RGBA",cropped.size,(255,255,255,255))
        head_ink.putalpha(cropped.getchannel("A"))
        head_bytes=BytesIO()
        head_ink.save(head_bytes,format="PNG",optimize=True)
        result["heads_only"]={
            "source":"verovio-engraved-chord-heads",
            "bounds":[(hx-note_x)*250/staff,(hy-note_y)*250/staff,
                      (hr-hx)*250/staff,(hb-hy)*250/staff],
            "png_base64":base64.b64encode(head_bytes.getvalue()).decode("ascii")}
    stem_bbox=stems_rgba.getchannel("A").getbbox()
    if stem_bbox:
        sx,sy,sr,sb=stem_bbox
        cut=stems_rgba.crop(stem_bbox)
        white_stem=Image.new("RGBA",cut.size,(255,255,255,255))
        white_stem.putalpha(cut.getchannel("A"))
        stem_bytes=BytesIO()
        white_stem.save(stem_bytes,format="PNG",optimize=True)
        result["stem_only"]={
            "source":"verovio-engraved-chord-stem",
            "bounds":[(sx-note_x)*250/staff,(sy-note_y)*250/staff,
                      (sr-sx)*250/staff,(sb-sy)*250/staff],
            "png_base64":base64.b64encode(stem_bytes.getvalue()).decode("ascii")}
    return result


def chord_templates(model: dict,cache=None) -> dict:
    patterns=patterns_from_model(model)
    if not patterns:
        return {}
    import verovio
    from .notation_symbols import native_glyphs
    font=native_glyphs()["head_black"]["font"]
    ver=getattr(verovio,"__version__","unknown")
    from .notation.assets.runtime import _create_verovio_toolkit
    toolkit=None
    result={}
    for pattern in patterns:
        key=cache.key("verovio-chords",VERSION,font,ver,pattern) if cache else None
        value=cache.read_json("verovio-chord",key) if key else None
        if not (isinstance(value,dict) and
                value.get("source")=="verovio-engraved-chord" and
                isinstance(value.get("head_positions"),list)):
            if toolkit is None:
                toolkit=_create_verovio_toolkit(verovio)
                if not toolkit.setOptions({"inputFrom":"xml","scale":48,
                        "pageWidth":900,"pageHeight":650,"svgViewBox":True,
                        "adjustPageHeight":True,"svgBoundingBoxes":True,
                        "svgContentBoundingBoxes":True}):
                    raise RuntimeError("Verovio rejected chord engraving options")
            try:
                value=_render(toolkit,pattern)
            except (ValueError,RuntimeError) as exc:
                # Keep the original complete Verovio score available, but
                # report precisely which source chord failed to engrave.
                # A quiet skip here used to cause opaque 'Missing chord' UI.
                print("VEROVIO_CHORD_PATTERN_UNAVAILABLE:",
                      pattern,type(exc).__name__,str(exc))
                continue
            if key:
                cache.write_json("verovio-chord",key,value)
        result[pattern]=value
    return result
