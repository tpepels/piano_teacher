"""Preserve real Verovio slur contours with explicit MusicXML note identity.

Slurs are NOT inferred from timing or pitch. The original MusicXML start/stop
notations provide endpoint IDs. Only an unambiguous Verovio contour on the
same engraved system is accepted. Godot can then adapt both endpoints to the
independent native beat/pitch positions without constructing a curve.
"""
from __future__ import annotations

import base64
from io import BytesIO
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 2


def slur_pairs_from_xml(musicxml: str) -> tuple[tuple[str,str], ...]:
    root=ET.fromstring(musicxml)
    pairs=[]
    for part in root.findall("part"):
        started={}
        for measure in part.findall("measure"):
            for note in measure.findall("note"):
                identifier=note.get("id")
                if not identifier:
                    continue
                # Slur numbers are local to a voice/staff, not a part.
                # Two simultaneous voices may both use number="1".
                lane=(note.findtext("staff","1"),note.findtext("voice","1"))
                for mark in note.findall("notations/slur"):
                    key=(*lane,mark.get("number","1"))
                    kind=mark.get("type")
                    if kind=="start":
                        started[key]=identifier
                    elif kind=="stop" and key in started:
                        first=started.pop(key)
                        if first != identifier:
                            pairs.append((first,identifier))
    # Multiple slurs between identical endpoints cannot be distinguished
    # from the SVG without extra source IDs. Refuse ambiguous duplicates.
    return tuple(pair for pair in dict.fromkeys(pairs)
                 if pairs.count(pair)==1)


def _classes(node):
    return set(node.get("class","").split())


def extract_slurs(svgs, musicxml: str, model: dict) -> dict:
    import cairosvg
    from .score_geometry import parse_svg_geometry
    from .verovio_tuplet_fragments import isolate

    notes={str(e["id"]):e for e in model.get("notation_events",[])
           if e.get("kind")=="note" and e.get("id")}
    desired=[p for p in slur_pairs_from_xml(musicxml)
             if all(id in notes for id in p)]
    if not desired:
        return {}
    out={}
    for page in svgs:
        geom=parse_svg_geometry(page)
        root=ET.fromstring(page)
        candidates=[]
        for group in root.iter():
            if "slur" not in _classes(group) or _classes(group) & {
                    "bounding-box","content-bounding-box"}:
                continue
            try:
                isolated=isolate(root,group)
                png=cairosvg.svg2png(bytestring=isolated.encode(),
                                    output_width=1600)
                with Image.open(BytesIO(png)) as image:
                    rgba=image.convert("RGBA")
                rect=rgba.getchannel("A").getbbox()
                if rect:
                    candidates.append((rgba,rect))
            except (ValueError,RuntimeError,OverflowError,ET.ParseError):
                continue
        for first,last in desired:
            key=f"{first}|{last}"
            if key in out or not all(i in geom.elements for i in (first,last)):
                continue
            x0,y0,staffid=geom.elements[first]
            x1,y1,end_staff=geom.elements[last]
            if x1<=x0 or staffid != end_staff:
                continue
            lines=geom.staff_systems[staffid]["staff_lines"]
            if len(lines)<5:
                continue
            space=lines[1]-lines[0]
            accepted=[]
            for rgba,rect in candidates:
                left,top,right,bottom=rect
                pxspace=space*rgba.height
                # Check both engraved endpoints, not just the overall
                # bounding box: a different voice may share the same X
                # interval yet curve towards another final pitch.
                if (abs(left/rgba.width-x0)>space*2.6 or
                        abs(right/rgba.width-x1)>space*2.6 or
                        (right-left)/rgba.width<space*.5 or pxspace<=4):
                    continue
                edge=max(2,min(int(pxspace*.8),int((right-left)*.08)))
                alpha=rgba.getchannel("A")
                start_box=alpha.crop((left,top,left+edge,bottom)).getbbox()
                end_box=alpha.crop((right-edge,top,right,bottom)).getbbox()
                if start_box is None or end_box is None:
                    continue
                start_y=top+(start_box[1]+start_box[3])*.5
                end_y=top+(end_box[1]+end_box[3])*.5
                if (abs(start_y-y0*rgba.height)>pxspace*7.0 or
                        abs(end_y-y1*rgba.height)>pxspace*7.0):
                    continue
                accepted.append((rgba,rect))
            if len(accepted)!=1:
                continue
            rgba,rect=accepted[0]
            pxspace=space*rgba.height
            if pxspace<=4:
                continue
            left,top,right,bottom=rect
            cut=rgba.crop(rect)
            white=Image.new("RGBA",cut.size,(255,255,255,255))
            white.putalpha(cut.getchannel("A"))
            mem=BytesIO()
            white.save(mem,format="PNG",optimize=True)
            bounds=[(left-x0*rgba.width)*250/pxspace,
                    (top-y0*rgba.height)*250/pxspace,
                    (right-left)*250/pxspace,(bottom-top)*250/pxspace]
            span=(x1-x0)*rgba.width*250/pxspace
            change=(y1-y0)*rgba.height*250/pxspace
            if all(math.isfinite(v) for v in bounds+[span,change]) and span>0:
                out[key]={"source":"verovio-engraved-slur",
                          "units_per_space":250,
                          "note_ids":[first,last],"bounds":bounds,
                          "span":span,"original_end_y":change,
                          "png_base64":base64.b64encode(mem.getvalue()).decode()}
    return out


def slur_fragments(svgs, musicxml, model, cache=None,identity="") -> dict:
    key=cache.key("real-verovio-slurs",VERSION,identity) if (
        cache is not None and identity) else None
    if key:
        stored=cache.read_json("verovio-slurs",key)
        if isinstance(stored,dict) and all(
                isinstance(item,dict) and
                item.get("source")=="verovio-engraved-slur"
                for item in stored.values()):
            return stored
    result=extract_slurs(svgs,musicxml,model)
    if key:
        cache.write_json("verovio-slurs",key,result)
    return result
