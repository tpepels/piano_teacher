"""Extract original Verovio tuplet number and bracket ink independently.

Musical positions belong to Piano Teacher's fixed beat axis. The two masks
retain their original Verovio staff-space Y/height, while the bracket's two
halves may span the source group's independently positioned endpoints. The
number remains at native scale, never stretched as part of a page strip.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from io import BytesIO
import copy
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 1
MAX_FRAGMENTS = 140


def classes(node: ET.Element) -> set[str]:
    return set(node.get("class","").split())


def source_ids(node: ET.Element) -> tuple[str,...]:
    return tuple(el.get("id") for el in node.iter()
                 if "note" in classes(el)
                 and not classes(el) & {"bounding-box","content-bounding-box"}
                 and el.get("id"))


def semantic_tuplets(model: dict) -> dict[tuple[str,...],dict]:
    """Explicit start/stop marks; never infer a tuplet from note intervals."""
    lanes = defaultdict(list)
    for event in model.get("notation_events",[]):
        if event.get("chord") or event.get("kind") not in {"note","rest"}:
            continue
        lanes[(event.get("staff"),str(event.get("voice","1")),
               event.get("measure"))].append(event)
    groups = {}
    for events in lanes.values():
        events.sort(key=lambda event:float(event["beat"]))
        opened = {}
        for event in events:
            for mark in event.get("tuplet_marks",[]):
                if mark.get("type") == "start":
                    opened[str(mark.get("number","1"))] = []
            for group in opened.values():
                if event.get("kind") == "note":
                    group.append(str(event["id"]))
            for mark in event.get("tuplet_marks",[]):
                if mark.get("type") == "stop":
                    key = str(mark.get("number","1"))
                    ids = tuple(opened.pop(key,[]))
                    if len(ids)>1 and all(ids):
                        groups[ids]={"staff":event.get("staff","right")}
    return groups


def isolate(root: ET.Element, target: ET.Element) -> str:
    """Keep the original XML graphics and inherited transforms/defs."""
    clone = copy.deepcopy(root)
    # Node identity changes on deepcopy: retain the child-index path.
    path=[]
    def locate(node):
        if node is target:
            return True
        for index,child in enumerate(node):
            path.append(index)
            if locate(child):
                return True
            path.pop()
        return False
    if not locate(root):
        raise ValueError("Detached Verovio source node")
    selected=clone
    for index in path:
        selected=selected[index]

    def trim(node):
        if node is selected:
            for el in node.iter():
                for child in list(el):
                    if classes(child) & {"bounding-box","content-bounding-box"}:
                        el.remove(child)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        yes=False
        for child in list(node):
            if trim(child):
                yes=True
            else:
                node.remove(child)
        return yes
    trim(clone)
    return ET.tostring(clone,encoding="unicode")


def crop_art(svg: str, staff_space: float,
             origin: tuple[float,float], source: str) -> dict | None:
    import cairosvg
    png=cairosvg.svg2png(bytestring=svg.encode(),output_width=1600)
    with Image.open(BytesIO(png)) as img:
        image=img.convert("RGBA")
    pixels=staff_space*image.height
    if not 4 < pixels < 320:
        return None
    bbox=image.getchannel("A").getbbox()
    if not bbox:
        return None
    left,top,right,bottom=bbox
    if right-left > 1500 or bottom-top > 850:
        return None
    clipped=image.crop(bbox)
    white=Image.new("RGBA",clipped.size,(255,255,255,255))
    white.putalpha(clipped.getchannel("A"))
    encoded=BytesIO()
    white.save(encoded,format="PNG",optimize=True)
    return {"source":source,"units_per_space":250,
            "bounds":[(left-origin[0]*image.width)*250/pixels,
                      (top-origin[1]*image.height)*250/pixels,
                      (right-left)*250/pixels,(bottom-top)*250/pixels],
            "png_base64":base64.b64encode(encoded.getvalue()).decode()}


def extract_tuplets(svgs: list[str] | tuple[str,...], model: dict) -> dict:
    from .score_geometry import parse_svg_geometry
    desired=semantic_tuplets(model)
    if not desired:
        return {}
    output={}
    for page in svgs:
        root=ET.fromstring(page)
        geom=parse_svg_geometry(page)
        for group in root.iter():
            if "tuplet" not in classes(group) or classes(group) & {
                    "bounding-box","content-bounding-box"}:
                continue
            ids=source_ids(group)
            if ids not in desired or len(output)>=MAX_FRAGMENTS:
                continue
            if not all(i in geom.elements for i in ids):
                continue
            x0,y0,sys=geom.elements[ids[0]]
            x1,_,end_sys=geom.elements[ids[-1]]
            if sys != end_sys or x1<=x0:
                continue
            staff=geom.staff_systems[sys]["staff_lines"]
            if len(staff)<5:
                continue
            # Separate the genuine number and bracket ink: the number is
            # never deformed by later horizontal beat-spacing changes.
            number_nodes=[node for node in group.iter()
                          if "tupletNum" in classes(node)]
            bracket_nodes=[node for node in group.iter()
                           if "tupletBracket" in classes(node)]
            if len(number_nodes)!=1:
                continue
            try:
                numeral=crop_art(isolate(root,number_nodes[0]),
                    staff[1]-staff[0],(x0,y0),"verovio-tuplet-number")
                bracket=(crop_art(isolate(root,bracket_nodes[0]),
                    staff[1]-staff[0],(x0,y0),"verovio-tuplet-bracket")
                    if len(bracket_nodes)==1 else None)
            except (ValueError,RuntimeError,ET.ParseError,OverflowError):
                continue
            if numeral is None:
                continue
            span=(x1-x0)*250/(staff[1]-staff[0])
            if span<=0 or not math.isfinite(span):
                continue
            output["|".join(ids)]={
                "source":"verovio-engraved-tuplet","note_ids":list(ids),
                "span":span,"number":numeral,"bracket":bracket}
    return output


def tuplet_fragments(svgs,model,cache=None,identity="") -> dict:
    key=cache.key("verovio-real-tuplets",VERSION,identity) if (
        cache is not None and identity) else None
    if key:
        stored=cache.read_json("verovio-tuplets",key)
        if (isinstance(stored,dict) and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-tuplet" and
                isinstance(v.get("number"),dict) for v in stored.values())):
            return stored
    results=extract_tuplets(svgs,model)
    if key:
        cache.write_json("verovio-tuplets",key,results)
    return results
