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

VERSION = 4


def _slur_sources_from_xml(musicxml: str) -> dict[tuple[str,str], str | None]:
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
                        started[key]=(identifier,mark.get("id"))
                    elif kind=="stop":
                        if key not in started:
                            # A voice can carry a slur across piano staves.
                            # Keep concurrent voices separate and accept
                            # only one unambiguous open source number.
                            matches=[candidate for candidate in started
                                     if candidate[1:]==key[1:]]
                            if len(matches)!=1:
                                continue
                            key=matches[0]
                        first,source=started.pop(key)
                        if first != identifier:
                            pairs.append(((first,identifier),source))
    # Multiple slurs between identical endpoints cannot be distinguished
    # from the SVG without extra source IDs. Refuse ambiguous duplicates.
    endpoints=[pair for pair,_ in pairs]
    return {pair:source for pair,source in pairs if endpoints.count(pair)==1}


def slur_pairs_from_xml(musicxml: str) -> tuple[tuple[str,str], ...]:
    return tuple(_slur_sources_from_xml(musicxml))


def _classes(node):
    return set(node.get("class","").split())


def extract_slurs(svgs, musicxml: str, model: dict) -> dict:
    notes = {str(event["id"]) for event in model.get("notation_events", ())
             if event.get("kind") == "note" and event.get("id")}
    desired = {pair: source for pair, source in _slur_sources_from_xml(musicxml).items()
               if all(endpoint in notes for endpoint in pair)}
    found = _page_slurs(svgs, desired)
    missing = {pair: source for pair, source in desired.items() if "|".join(pair) not in found}
    if missing:
        found.update(_unbroken_slurs(musicxml, missing))
    return found


def _unbroken_slurs(musicxml, missing):
    """Re-engrave the original measures together across printed system breaks."""
    from .runtime import measure_excerpt, unbroken_toolkit

    root = ET.fromstring(musicxml)
    toolkit = unbroken_toolkit()
    found = {}
    for part in root.findall("part"):
        measures = part.findall("measure")
        positions = {note.get("id"): index for index, measure in enumerate(measures)
                     for note in measure.findall("note")}
        for pair, source in missing.items():
            first, last = pair
            if first not in positions or last not in positions:
                continue
            start, end = positions[first], positions[last]
            subset = measure_excerpt(root, part, start, end)
            _retain_slur(subset, first, last, source)
            if toolkit.loadData(ET.tostring(subset, encoding="unicode")):
                page = toolkit.renderToSVG(1)
                fragment = _identified_slur(page, pair, source)
                if fragment:
                    found["|".join(pair)] = fragment
    return found


def _retain_slur(subset, first, last, source):
    # Other spans may start outside this excerpt or reuse the same
    # MusicXML number in a simultaneous worksheet voice.
    start_number = None
    for note in subset.findall("part/measure/note"):
        for mark in note.findall("notations/slur"):
            if note.get("id") == first and mark.get("type") == "start" and mark.get("id") == source:
                start_number = mark.get("number", "1")
            elif not (note.get("id") == last and mark.get("type") == "stop"
                      and mark.get("number", "1") == start_number):
                note.find("notations").remove(mark)


def _identified_slur(page, pair, source):
    from ...source_svg import isolate, parse_svg_geometry
    from .vector_art import local_vector_art

    root = ET.fromstring(page)
    marks = [node for node in root.iter() if node.get("id") == source
             and "slur" in _classes(node)]
    geometry = parse_svg_geometry(root)
    if len(marks) != 1 or not all(endpoint in geometry.elements for endpoint in pair):
        return None
    x0, y0, system = geometry.elements[pair[0]]
    x1, y1, last_system = geometry.elements[pair[1]]
    lines = geometry.staff_systems[system]["staff_lines"]
    if system != last_system or x1 <= x0 or len(lines) < 5:
        return None
    space = lines[1] - lines[0]
    art = local_vector_art(isolate(root, marks[0]), space, (x0, y0), "verovio-engraved-slur")
    if art:
        art.update(note_ids=list(pair), span=(x1-x0)*geometry.width/geometry.height*250/space,
                   original_end_y=(y1-y0)*250/space)
    return art


def _slur_ink(root):
    from ...source_svg import isolate
    from .vector_art import svg_alpha

    candidates=[]
    for group in root.iter():
        if "slur" not in _classes(group) or _classes(group) & {
                "bounding-box","content-bounding-box"}:
            continue
        try:
            isolated=isolate(root,group)
            alpha = svg_alpha(isolated, 1600)
            rect = alpha.getbbox()
            if rect:
                # Retain only contour pixels, never one full-page raster
                # image for every slur in a complete performance.
                candidates.append((group.get("id"),alpha.crop(rect),rect,alpha.size))
        except (ValueError,RuntimeError,OverflowError,ET.ParseError):
            continue
    return candidates


def _matches_endpoints(cut, rect, size, first, last, space):
    x0, y0 = first
    x1, y1 = last
    left,top,right,bottom=rect
    width,height=size
    pxspace=space*height
    # Check both engraved endpoints, not just the overall
    # bounding box: a different voice may share the same X
    # interval yet curve towards another final pitch.
    if (abs(left-x0*width)>pxspace*2.6 or
            abs(right-x1*width)>pxspace*2.6 or
            right-left<pxspace*.5 or pxspace<=4):
        return False
    edge=max(2,min(int(pxspace*.8),int((right-left)*.08)))
    start_box=cut.crop((0,0,edge,cut.height)).getbbox()
    end_box=cut.crop((cut.width-edge,0,cut.width,cut.height)).getbbox()
    if start_box is None or end_box is None:
        return False
    start_y=top+(start_box[1]+start_box[3])*.5
    end_y=top+(end_box[1]+end_box[3])*.5
    if (abs(start_y-y0*height)>pxspace*7.0 or
            abs(end_y-y1*height)>pxspace*7.0):
        return False
    return True


def _fragment(pair, matched, first_point, last_point, space):
    first, last = pair
    x0, y0 = first_point
    x1, y1 = last_point
    cut,rect,(width,height)=matched
    pxspace=space*height
    if pxspace<=4:
        return None
    left,top,right,bottom=rect
    white=Image.new("RGBA",cut.size,(255,255,255,255))
    white.putalpha(cut)
    mem=BytesIO()
    white.save(mem,format="PNG",optimize=True)
    bounds=[(left-x0*width)*250/pxspace,
            (top-y0*height)*250/pxspace,
            (right-left)*250/pxspace,(bottom-top)*250/pxspace]
    span=(x1-x0)*width*250/pxspace
    change=(y1-y0)*height*250/pxspace
    if all(math.isfinite(v) for v in bounds+[span,change]) and span>0:
        return {"source":"verovio-engraved-slur",
                  "units_per_space":250,
                  "note_ids":[first,last],"bounds":bounds,
                  "span":span,"original_end_y":change,
                  "png_base64":base64.b64encode(mem.getvalue()).decode()}
    return None


def _page_slurs(svgs, desired):
    from ...source_svg import parse_svg_geometry

    out = {}
    if not desired:
        return out
    for page in svgs:
        root = ET.fromstring(page)
        geom = parse_svg_geometry(root)
        candidates = _slur_ink(root)
        for pair, source_id in desired.items():
            key = "|".join(pair)
            if key in out or not all(i in geom.elements for i in pair):
                continue
            x0, y0, system = geom.elements[pair[0]]
            x1, y1, end_system = geom.elements[pair[1]]
            lines = geom.staff_systems[system]["staff_lines"]
            if x1 <= x0 or system != end_system or len(lines) < 5:
                continue
            space = lines[1] - lines[0]
            matches = [(cut, rect, size) for source, cut, rect, size in candidates
                       if (not source_id or source_id == source)
                       and _matches_endpoints(cut, rect, size, (x0,y0), (x1,y1), space)]
            if len(matches) == 1:
                art = _fragment(pair, matches[0], (x0, y0), (x1, y1), space)
                if art:
                    out[key] = art
    return out


def slur_fragments(svgs, musicxml, model, cache=None,identity="") -> dict:
    key=cache.key("real-verovio-slurs",VERSION,identity) if (
        cache is not None and identity) else None
    if key:
        stored=cache.read_json("verovio-slurs",key)
        if isinstance(stored,dict) and stored and all(
                isinstance(item,dict) and
                item.get("source")=="verovio-engraved-slur"
                for item in stored.values()):
            return stored
    result=extract_slurs(svgs,musicxml,model)
    if key and result:
        cache.write_json("verovio-slurs",key,result)
    return result
