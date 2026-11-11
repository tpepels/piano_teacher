"""Actual Verovio-rendered chord sprites.

Every chord is engraved by Verovio itself. A score prepared from its own
Verovio pages gets one *instance* template per chord shape at the chord's
real staff position, clef, spelling and Verovio's own stem direction, and
each head is bound to its notation event by the template's note element id
(``leaders``: leader id -> member ids in template note order). Verovio's
head arrangement depends on all of those: seconds flip sides with the stem,
whole notes take a virtual stem from their position, and a far ledger head
can join the displaced column. Without pages (hand-built models), a
position-free *generic* template keyed by diatonic intervals is used and the
native view derives the same key itself.

The atlas stores exact notehead positions for independent dots, ledger lines
and accidentals. Rhythmic timing never comes from SVG positions.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
import math
import re
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 8
_STEPS = {"C":0,"D":1,"E":2,"F":3,"G":4,"A":5,"B":6}
_LETTERS = "CDEFGAB"
_BEATS = {"whole":4.0,"half":2.0,"quarter":1.0,"eighth":.5,
          "16th":.25,"32nd":.125,"64th":.0625,"128th":.03125}
_CLEF_ANCHORS = {"G":32,"F":24,"C":28}
# MusicXML octaves 0..9: diatonic indices 0..69 can be written in a template.
_LOWEST, _HIGHEST = 0, 69


def diatonic(spelling: dict) -> int:
    return int(spelling["octave"])*7+_STEPS[spelling["step"]]


def _alter(note: dict) -> int:
    return int(note["spelling"].get("alter") or 0)


def head_order(notes: list[dict]) -> list[dict]:
    """Template note order, identical to the native view's head_order_less:
    bottom to top by staff position, then sounding pitch, then event id."""
    return sorted(notes, key=lambda n: (diatonic(n["spelling"]),
                                        int(n.get("midi_pitch") or 0), str(n.get("id", ""))))


def _clef(leader: dict, measure: dict) -> tuple[str, int, int]:
    staff = leader.get("staff","right")
    clef = measure.get("clefs",{}).get(staff,{})
    sign = str(clef.get("sign","G" if staff=="right" else "F"))
    line = int(clef.get("line",2 if staff=="right" else 4))
    return sign, line, int(clef.get("octave_change",0))


def _shape_or_reason(leader: dict, notes: list[dict], measure: dict):
    """(shape, None) for a chord, else (None, why the input is not a chord).

    Any number of heads, any span, any number of heads on one staff
    position and identical heads are chords: Verovio engraves them all.
    """
    if len(notes) < 2:
        return None, f"{len(notes)} head: a chord has two or more"
    kind = str(leader.get("note_type",""))
    if kind not in _BEATS:
        return None, f"note value {kind!r} has no engraving"
    if any(n.get("note_type") != kind for n in notes):
        # MusicXML chord tones share one duration; heads of different values
        # at one onset belong to different voices. Import never merges them.
        return None, "heads of different note values are separate voices, not one chord"
    try:
        absolute = [diatonic(n["spelling"]) for n in notes]
        alters = [_alter(n) for n in notes]
    except (KeyError,TypeError,ValueError):
        return None, "a head has no readable pitch spelling"
    sign, line, octave_change = _clef(leader, measure)
    if sign not in _CLEF_ANCHORS:
        return None, f"clef {sign} is not a pitched staff"
    bottom = _CLEF_ANCHORS[sign]-(line-1)*2+octave_change*7
    # One chord has one stem: the first declared direction in source order
    # (the leader's, when it declares one) is the chord's.
    declared = next((n["stem"] for n in notes if n.get("stem") in {"up","down"}), None)
    return {"kind": kind, "absolute": absolute, "alters": alters,
            "clef": (sign, line, octave_change), "bottom": bottom,
            "declared": declared}, None


def _pattern_or_reason(leader: dict, notes: list[dict], measure: dict):
    """(generic pattern, None) for a chord, else (None, refusal reason)."""
    shape, reason = _shape_or_reason(leader, notes, measure)
    if shape is None:
        return None, reason
    absolute, bottom = shape["absolute"], shape["bottom"]
    up = sum(p-bottom for p in absolute)/len(absolute)<4
    direction = shape["declared"] or ("up" if up else "down")
    differences = sorted(p-diatonic(leader["spelling"]) for p in absolute)
    return f"{shape['kind']}|{direction}|{','.join(map(str,differences))}", None


def chord_pattern(leader: dict, notes: list[dict], measure: dict) -> str | None:
    return _pattern_or_reason(leader, notes, measure)[0]


def chord_refusal(leader: dict, notes: list[dict], measure: dict) -> str | None:
    """Why simultaneous heads are not one chord, naming measure and staff."""
    reason = _pattern_or_reason(leader, notes, measure)[1]
    if reason is None:
        return None
    return (f"measure {int(leader.get('measure', measure.get('number', 0)))}, "
            f"{leader.get('staff', 'right')} staff: {reason}")


def refused_chords(model: dict) -> list[str]:
    """Readable refusal for every chord of the model that has no sprite."""
    measures = {int(m["number"]):m for m in model.get("measures",[])}
    lanes = defaultdict(list)
    for e in model.get("notation_events",[]):
        if e.get("kind")=="note":
            lanes[(e.get("staff"),str(e.get("voice","1")),int(e.get("measure",0)),
                   round(float(e.get("beat",0)),6))].append(e)
    refused = []
    for (staff,_,measure_id,beat), notes in sorted(lanes.items(),
            key=lambda item: (item[0][2], item[0][3], str(item[0][0]))):
        leaders = [n for n in notes if not n.get("chord")]
        if len(leaders)!=1 or len(notes)<2 or measure_id not in measures:
            continue
        reason = chord_refusal(leaders[0],notes,measures[measure_id])
        if reason:
            refused.append(reason)
    return refused


def patterns_from_model(model: dict, *, stem_directions: dict[str, bool] | None = None) -> list[str]:
    measures = {int(m["number"]):m for m in model.get("measures",[])}
    lanes = defaultdict(list)
    simultaneous = defaultdict(set)
    for e in model.get("notation_events",[]):
        if e.get("kind")=="note":
            key=(e.get("staff"),str(e.get("voice","1")),int(e.get("measure",0)),
                 round(float(e.get("beat",0)),6))
            lanes[key].append(e)
            if not e.get("chord"):
                simultaneous[(key[0],key[2],key[3])].add(key[1])
    patterns = set()
    for (staff,_,measure_id,beat), notes in lanes.items():
        leaders = [n for n in notes if not n.get("chord")]
        if len(leaders)!=1 or len(notes)<2 or measure_id not in measures:
            continue
        pattern = chord_pattern(leaders[0],notes,measures[measure_id])
        if pattern:
            patterns.add(pattern)
            # Independent simultaneous voices may need the opposite shaft
            # side from an isolated pitch default. Provide authentic ink for
            # both choices; native voice layout selects it without changing
            # written source directions or borrowing another chord's stem.
            if (len(simultaneous[(staff,measure_id,beat)]) > 1 and
                    not pattern.startswith("whole|") and
                    not any(n.get("stem") in {"up","down"} for n in notes)):
                kind, direction, relative = pattern.split("|")
                patterns.add(f"{kind}|{'down' if direction == 'up' else 'up'}|{relative}")
            leader_id = str(leaders[0].get("id", ""))
            if stem_directions is not None and leader_id in stem_directions:
                kind, _, relative = pattern.split("|")
                direction = "up" if stem_directions[leader_id] else "down"
                patterns.add(f"{kind}|{direction}|{relative}")
    return sorted(patterns)


def _score_xml(kind: str, direction: str, heads: list[tuple[int, int]],
               clef: tuple[str, int, int] = ("G", 2, 0)) -> str:
    """One chord measure; heads are (diatonic index, alter) in note order.

    Notes are ids c0, c1, ... in the given order. An alter is written without
    an <accidental>, so Verovio knows the pitch but prints no accidental:
    native accidentals are placed separately. ``direction`` "auto" writes no
    stem, so Verovio chooses it from the staff position as in a real score.
    A whole note's stem is invisible yet still decides its head arrangement.
    """
    duration = round(_BEATS[kind]*10080)
    notes = []
    for i,(index,alter) in enumerate(heads):
        octave,step = divmod(index,7)
        extra = "<chord/>" if i else ""
        stem = f"<stem>{direction}</stem>" if i==0 and direction in {"up","down"} else ""
        written = f"<alter>{alter}</alter>" if alter else ""
        notes.append(f'<note id="c{i}">{extra}<pitch><step>{_LETTERS[step]}</step>'
                     f'{written}<octave>{octave}</octave></pitch>'
                     f'<duration>{duration}</duration><type>{kind}</type>{stem}</note>')
    notes_xml="".join(notes)
    sign, line, octave_change = clef
    shift = (f"<clef-octave-change>{octave_change}</clef-octave-change>"
             if octave_change else "")
    return (f'<score-partwise version="4.0"><work><work-title> </work-title></work>'
            f'<movement-title> </movement-title><part-list><score-part id="P1">'
            f'<part-name>Piano</part-name></score-part></part-list>'
            f'<part id="P1"><measure number="1"><attributes>'
            f'<divisions>10080</divisions><time><beats>4</beats>'
            f'<beat-type>4</beat-type></time><clef><sign>{sign}</sign>'
            f'<line>{line}</line>{shift}</clef></attributes>{notes_xml}</measure></part>'
            f'</score-partwise>')


def _xml(pattern: str) -> str:
    """Generic template: the leader at B4, a neutral treble reference with no
    key signature or accidentals, moved by whole octaves only when a very
    wide chord would leave the writable MusicXML range."""
    kind,direction,relative = pattern.split("|")
    offsets = [int(n) for n in relative.split(",")]
    base = 34
    while base+min(offsets) < _LOWEST:
        base += 7
    while base+max(offsets) > _HIGHEST and base+min(offsets)-7 >= _LOWEST:
        base -= 7
    return _score_xml(kind, direction, [(base+offset, 0) for offset in offsets])


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
            for parent in node.iter():
                for child in list(parent):
                    if "flag" in child.get("class", "").split():
                        parent.remove(child)
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
    """Generic template: the leader is the first zero-offset head."""
    offsets=[int(n) for n in pattern.split("|")[2].split(",")]
    return _render_xml(toolkit, _xml(pattern), len(offsets), offsets.index(0),
                       pattern.split("|", 1)[0])


def _render_xml(toolkit, xml: str, count: int, anchor_index: int, kind: str) -> dict:
    import cairosvg
    from ...source_svg import parse_svg_geometry
    if not toolkit.loadData(xml):
        raise ValueError("Verovio refused chord sample")
    svg = toolkit.renderToSVG(1)
    g = parse_svg_geometry(svg)
    names={f"c{index}" for index in range(count)}
    if not names.issubset(g.elements):
        raise ValueError("Verovio chord notehead anchor IDs missing")
    # Normalization is relative to the actual MusicXML chord leader.
    # It need not be the lowest note: preserve the leader's head.
    anchor=g.elements[f"c{anchor_index}"]
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
    from .glyphs import native_glyphs
    head=native_glyphs()["head_" + (
        kind if kind in {"whole", "half"} else "black")]["bounds"]
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


def _valid_asset(value: object, pattern: str) -> bool:
    """A partial disk atlas must be regenerated before Godot requests it."""
    def box(item):
        if not isinstance(item, dict):
            return False
        bounds = item.get("bounds")
        valid = (isinstance(bounds, list) and len(bounds) == 4 and
                all(isinstance(n, (int, float)) and math.isfinite(n) for n in bounds) and
                bounds[2] > 0 and bounds[3] > 0 and
                isinstance(item.get("png_base64"), str) and
                item["png_base64"].startswith("iVBORw0KGgo"))
        if not valid:
            return False
        try:
            data = base64.b64decode(item["png_base64"], validate=True)
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    return False
                image.verify()
        except (ValueError, OSError, SyntaxError):
            return False
        return True

    if not (box(value) and value.get("source") == "verovio-engraved-chord" and
            value.get("units_per_space") == 250):
        return False
    positions = value.get("head_positions")
    if not (isinstance(positions, list) and
            len(positions) == len(pattern.split("|")[2].split(",")) and
            all(isinstance(p, list) and len(p) == 2 and
                all(isinstance(n, (int, float)) and math.isfinite(n) for n in p)
                for p in positions)):
        return False
    heads = value.get("heads_only")
    if not box(heads) or heads.get("source") != "verovio-engraved-chord-heads":
        return False
    stem = value.get("stem_only")
    return (pattern.startswith("whole|") or
            (box(stem) and stem.get("source") == "verovio-engraved-chord-stem"))


_NUMBER = r"-?\d+(?:\.\d+)?"


def _classes(node) -> set[str]:
    return set(node.get("class", "").split())


def verovio_chord_stems(pages) -> dict[str, bool]:
    """Note id -> stem up, for every stemmed chord of Verovio's own pages.

    Verovio's stem rule (the head farthest from the middle line, voices,
    beams) differs from a mean-position rule, and the side of every second
    follows the stem: the score's real direction is read, not re-derived.
    """
    result: dict[str, bool] = {}
    for page in pages or ():
        root = ET.fromstring(page)
        for chord in root.iter():
            classes = _classes(chord)
            if "chord" not in classes or classes & {"bounding-box", "content-bounding-box"}:
                continue
            stem_ys, head_ys, ids = [], [], []
            for node in chord.iter():
                kinds = _classes(node)
                if kinds & {"bounding-box", "content-bounding-box"}:
                    continue
                if "note" in kinds and node.get("id"):
                    ids.append(node.get("id"))
                if "stem" in kinds and not stem_ys:
                    for path in node.iter():
                        match = re.fullmatch(r"\s*M\s*(%s)[,\s]+(%s)\s*L\s*(%s)[,\s]+(%s)\s*"
                                             % ((_NUMBER,) * 4), path.get("d", "") or "")
                        if match:
                            stem_ys = [float(match.group(2)), float(match.group(4))]
                            break
                if "notehead" in kinds:
                    for use in node.iter():
                        if use.tag.rsplit("}", 1)[-1] != "use":
                            continue
                        move = re.search(r"translate\(\s*(%s)[,\s]+(%s)" % (_NUMBER, _NUMBER),
                                         use.get("transform", ""))
                        head_ys.append(float(move.group(2)) if move else float(use.get("y", "0")))
                        break
            if not stem_ys or not head_ys:
                continue
            up = min(head_ys)-min(stem_ys) > max(stem_ys)-max(head_ys)
            for ident in ids:
                result[ident] = up
    return result


def _chord_lanes(model: dict):
    """Leader, members and measure of every chord, like the native index."""
    measures = {int(m["number"]):m for m in model.get("measures",[])}
    lanes = defaultdict(list)
    for e in model.get("notation_events",[]):
        if e.get("kind")=="note":
            lanes[(e.get("staff"),str(e.get("voice","1")),int(e.get("measure",0)),
                   round(float(e.get("beat",0)),6))].append(e)
    for (_,_,measure_id,_), notes in lanes.items():
        leaders = [n for n in notes if not n.get("chord")]
        if len(leaders)==1 and len(notes)>=2 and measure_id in measures:
            yield leaders[0], notes, measures[measure_id]


def chord_instances(model: dict, pages, *,
                    stem_directions: dict[str, bool] | None = None) -> dict[str, dict]:
    """Leader id -> the instance template that engraves exactly that chord.

    Direction: a source beam's, else Verovio's own stem on the page, else a
    declared stem, else the mean-position rule. Whole notes have no visible
    stem: their template writes none, so Verovio's virtual stem comes from
    the same staff position it had in the score.
    """
    stems = verovio_chord_stems(pages)
    beams = stem_directions or {}
    result: dict[str, dict] = {}
    for leader, notes, measure in _chord_lanes(model):
        shape, _ = _shape_or_reason(leader, notes, measure)
        if shape is None:
            continue
        ordered = head_order(notes)
        anchor = next(i for i, n in enumerate(ordered) if n is leader)
        leader_id = str(leader.get("id", ""))
        page = next((stems[str(n.get("id"))] for n in notes if str(n.get("id")) in stems), None)
        if shape["kind"] == "whole":
            direction = "auto"
        elif leader_id in beams:
            direction = "up" if beams[leader_id] else "down"
        elif page is not None:
            direction = "up" if page else "down"
        elif shape["declared"]:
            direction = shape["declared"]
        else:
            bottom = shape["bottom"]
            mean = sum(p-bottom for p in shape["absolute"])/len(notes)
            direction = "up" if mean < 4 else "down"
        heads = [(diatonic(n["spelling"]), _alter(n)) for n in ordered]
        sign, line, octave_change = shape["clef"]
        shift = 0
        while min(i for i, _ in heads)+shift < _LOWEST:
            shift += 7
        while max(i for i, _ in heads)+shift > _HIGHEST:
            shift -= 7
        heads = [(index+shift, alter) for index, alter in heads]
        origin = heads[anchor][0]
        relative = ",".join(str(index-origin) for index, _ in heads)
        spelled = ",".join(f"{index}{'s'*alter if alter > 0 else 'f'*-alter}"
                           for index, alter in heads)
        key = (f"{shape['kind']}|{direction}|{relative}|{sign}{line}{octave_change:+d}"
               f"|{spelled}|a{anchor}")
        result[leader_id] = {"key": key, "kind": shape["kind"], "anchor": anchor,
                             "xml": _score_xml(shape["kind"], direction, heads, shape["clef"]),
                             "heads": [str(n.get("id", "")) for n in ordered]}
    return result


def _render_templates(cache, specs: dict[str, tuple]) -> dict:
    """key -> asset for key -> (xml, head count, anchor index, note value)."""
    if not specs:
        return {}
    import verovio
    from .glyphs import native_glyphs
    font=native_glyphs()["head_black"]["font"]
    ver=getattr(verovio,"__version__","unknown")
    from .runtime import _create_verovio_toolkit
    toolkit=None
    result={}
    for pattern, (xml, count, anchor, kind) in sorted(specs.items()):
        key=cache.key("verovio-chords",VERSION,font,ver,pattern) if cache else None
        value=cache.read_json("verovio-chord",key) if key else None
        if not _valid_asset(value, pattern):
            if toolkit is None:
                toolkit=_create_verovio_toolkit(verovio)
                if not toolkit.setOptions({"inputFrom":"xml","scale":48,
                        "pageWidth":900,"pageHeight":650,"svgViewBox":True,
                        "adjustPageHeight":True,"svgBoundingBoxes":True,
                        "svgContentBoundingBoxes":True}):
                    raise RuntimeError("Verovio rejected chord engraving options")
            try:
                value=_render_xml(toolkit, xml, count, anchor, kind)
                if not _valid_asset(value, pattern):
                    raise ValueError("Incomplete genuine chord components")
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


def chord_templates(model: dict,cache=None, *,
                    stem_directions: dict[str, bool] | None = None,
                    pages=None) -> dict:
    """Verovio chord atlas for a model.

    With the score's own Verovio ``pages``, every chord gets an instance
    template and the asset lists it under ``leaders`` (leader id -> member
    ids in template note order), which the native view uses instead of
    deriving a key. Without pages, generic interval templates are made.
    """
    for refusal in refused_chords(model):
        print("VEROVIO_CHORD_REFUSED:",refusal)
    if pages is not None:
        instances = chord_instances(model, pages, stem_directions=stem_directions)
        rendered = _render_templates(cache, {
            item["key"]: (item["xml"], len(item["heads"]), item["anchor"], item["kind"])
            for item in instances.values()})
        result = {key: deepcopy(value) for key, value in rendered.items()}
        for leader_id, item in sorted(instances.items()):
            if item["key"] in result:
                result[item["key"]].setdefault("leaders", {})[leader_id] = item["heads"]
        return result
    patterns=patterns_from_model(model, stem_directions=stem_directions)
    return _render_templates(cache, {
        pattern: (_xml(pattern), len(pattern.split("|")[2].split(",")),
                  [int(n) for n in pattern.split("|")[2].split(",")].index(0),
                  pattern.split("|", 1)[0])
        for pattern in patterns})
