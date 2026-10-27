"""Extract original Verovio tuplet number and bracket ink independently.

Musical positions belong to Piano Teacher's fixed beat axis. The two masks
retain their original Verovio staff-space Y/height, while the bracket's two
halves may span the source group's independently positioned endpoints. The
number remains at native scale, never stretched as part of a page strip.
Singletons retain the original masks at their sole source event; their span
is artwork width. The legacy ``note_ids`` field also accepts source rest IDs.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from io import BytesIO
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 6
MAX_RASTER_PIXELS = 8_000_000


def classes(node: ET.Element) -> set[str]:
    return set(node.get("class","").split())


def source_ids(node: ET.Element) -> tuple[str,...]:
    return tuple(el.get("id") for el in node.iter()
                 if classes(el) & {"note", "rest", "mRest", "multiRest"}
                 and not classes(el) & {"bounding-box","content-bounding-box"}
                 and el.get("id"))


def _owned_art(node: ET.Element):
    """Visit this tuplet's graphics without entering a nested tuplet."""
    for child in node:
        if classes(child) & {"tuplet","bounding-box","content-bounding-box"}:
            continue
        yield child
        yield from _owned_art(child)


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
                group.append(str(event.get("id") or ""))
            for mark in event.get("tuplet_marks",[]):
                if mark.get("type") == "stop":
                    key = str(mark.get("number","1"))
                    ids = tuple(opened.pop(key,[]))
                    if ids and all(ids):
                        groups[ids]={"staff":event.get("staff","right")}
    return groups


# Compatibility import for existing extraction callers.
from .svg import isolate


def crop_art(svg: str, staff_space: float,
             origin: tuple[float,float], source: str) -> dict | None:
    import cairosvg
    viewport = [float(v) for v in ET.fromstring(svg).get('viewBox', '').replace(',', ' ').split()]
    if (len(viewport) != 4 or not all(math.isfinite(v) for v in viewport)
            or min(viewport[2:]) <= 0 or not math.isfinite(staff_space)
            or staff_space <= 0):
        return None
    width = 1600
    height = width*viewport[3]/viewport[2]
    if staff_space*round(height) <= 4:
        # A long continuous score can make genuine tuplet ink subpixel at
        # the ordinary page width. Raise source resolution, retaining its
        # vector aspect ratio and the original physical staff-space units.
        width = math.ceil(width*8/(staff_space*height))
        height = width*viewport[3]/viewport[2]
    if width*math.ceil(height) > MAX_RASTER_PIXELS:
        return None
    png=cairosvg.svg2png(bytestring=svg.encode(),output_width=width)
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


def _canonical_rest_aliases(pages, model: dict) -> dict[str, str]:
    """Bind generated rest IDs by the complete source document inventory.

    The canonical model names rests by staff/measure/global symbol ordinal;
    MusicXML does not preserve those IDs and Verovio assigns opaque ones.
    Match explicit staff order and measure order, every symbol kind and every
    retained pitched ID before accepting any rest alias. This is structural
    correspondence, never a nearest-glyph or nearest-onset search.
    """
    if model.get("schema") != "piano-teacher-score-model-v1":
        return {}
    order, measures = model.get("staff_order"), model.get("measures")
    if (not isinstance(order, list) or not order or len(order) != len(set(order))
            or any(hand not in {"right", "left"} for hand in order)
            or not isinstance(measures, list) or not measures):
        return {}
    expected = defaultdict(list)
    events = model.get("notation_events", [])
    identifiers = [e.get("id") for e in events]
    if len(identifiers) != len(set(identifiers)):
        return {}
    for ordinal, event in enumerate(events):
        expected[event.get("measure"), event.get("staff")].append((ordinal, event))
    source_measures = [(measure, geom) for root, geom in pages for measure in root.iter()
                       if "measure" in classes(measure) and not classes(measure) & {
                           "bounding-box", "content-bounding-box"}]
    if len(source_measures) != len(measures):
        return {}
    aliases, seen = {}, set()
    for (measure, geom), original in zip(source_measures, measures):
        staves = [n for n in measure if "staff" in classes(n) and not classes(n) & {
            "bounding-box", "content-bounding-box"}]
        if len(staves) != len(order):
            return {}
        for staff, hand in zip(staves, order):
            symbols = [n for n in staff.iter()
                       if classes(n) & {"note", "rest", "mRest", "multiRest"}
                       and not classes(n) & {"bounding-box", "content-bounding-box"}
                       and n.get("id") in geom.elements]
            required = expected[original["number"], hand]
            if len(symbols) != len(required):
                return {}
            for source, (ordinal, event) in zip(symbols, required):
                identifier = source.get("id")
                kind = "note" if "note" in classes(source) else "rest"
                if identifier in seen or kind != event.get("kind"):
                    return {}
                seen.add(identifier)
                if identifier == event.get("id"):
                    continue
                canonical = f"rest:{hand}:{original['number']}:{ordinal}"
                if (kind != "rest" or event.get("id") != canonical
                        or identifier in identifiers):
                    return {}
                aliases[identifier] = canonical
    if sum(len(rows) for rows in expected.values()) != len(seen):
        return {}
    return aliases


def extract_tuplets(svgs: list[str] | tuple[str,...], model: dict) -> dict:
    from .svg_geometry import parse_svg_geometry
    desired=semantic_tuplets(model)
    if not desired:
        return {}
    events={str(event["id"]):event for event in model.get("notation_events",[])
            if event.get("kind") in {"note", "rest"} and event.get("id")}
    output={}
    pages=[(ET.fromstring(page),parse_svg_geometry(page)) for page in svgs]
    aliases=_canonical_rest_aliases(pages,model)
    for root,geom in pages:
        for source,canonical in aliases.items():
            if source in geom.elements:
                geom.elements[canonical]=geom.elements[source]
        viewport=[float(v) for v in root.get("viewBox","").replace(","," ").split()]
        aspect=viewport[2]/viewport[3]
        for group in root.iter():
            if "tuplet" not in classes(group) or classes(group) & {
                    "bounding-box","content-bounding-box"}:
                continue
            # Separate the genuine number and bracket ink: the number is
            # never deformed by later horizontal beat-spacing changes.
            art=list(_owned_art(group))
            number_nodes=[node for node in art if "tupletNum" in classes(node)]
            bracket_nodes=[node for node in art if "tupletBracket" in classes(node)]
            if len(number_nodes)!=1:
                continue
            contained=tuple(aliases.get(identifier,identifier)
                            for identifier in source_ids(group))
            if any(identifier not in events for identifier in contained):
                continue
            # A Verovio tuplet contains every pitch of its chords, while
            # semantic boundaries and horizontal anchors name attacks.
            contained=tuple(identifier for identifier in contained
                            if not events[identifier].get("chord"))
            candidates=[]
            # Verovio 5.x can place the tuplet graphic BESIDE the note
            # groups, so source IDs are sometimes absent from the tuplet
            # subtree. Match the original bracket endpoints instead.
            for ids in desired:
                if contained and contained != ids:
                    continue
                # One anchor has no independently measurable endpoint span.
                # A nearby numeral alone cannot establish singleton ownership.
                if len(ids)==1 and not contained:
                    continue
                if "|".join(ids) in output or not all(
                        note in geom.elements for note in ids):
                    continue
                anchors=[geom.elements[note] for note in ids]
                x0,y0,sys=anchors[0]
                x1,_,syslast=anchors[-1]
                if sys != syslast or (len(ids)>1 and x1<=x0) or any(
                        a[0]>=b[0] or b[2]!=sys
                        for a,b in zip(anchors,anchors[1:])):
                    continue
                staff=geom.staff_systems[sys]["staff_lines"]
                if len(staff)<5:
                    continue
                space=staff[1]-staff[0]
                if not 0 < space < 1:
                    continue
                try:
                    numeric=crop_art(isolate(root,number_nodes[0]),
                        space,(x0,y0),"verovio-tuplet-number")
                    bracket=(crop_art(isolate(root,bracket_nodes[0]),
                        space,(x0,y0),"verovio-tuplet-bracket")
                        if len(bracket_nodes)==1 else None)
                except (ValueError,RuntimeError,ET.ParseError,OverflowError):
                    continue
                if numeric is None:
                    continue
                number_box=numeric["bounds"]
                # In source staff-space units. The Verovio numeral is
                # centred in the same rhythmic group even when no note
                # nodes are descendants of its graphics group.
                number_mid=number_box[0]+number_box[2]*.5
                distance=abs(number_mid-(x1-x0)*aspect*125/space)
                if not contained and distance > 500:
                    continue
                if bracket is not None and not contained:
                    bounds=bracket["bounds"]
                    left=bounds[0]
                    right=bounds[0]+bounds[2]
                    span=(x1-x0)*aspect*250/space
                    if abs(left)>620 or abs(right-span)>620:
                        continue
                candidates.append((ids,x0,y0,space,numeric,bracket))
            # An ambiguous overlap is never converted into a graphical
            # guess. Those groups retain the earlier safe fallback.
            if len(candidates)!=1:
                continue
            ids,x0,y0,space,numeral,bracket=candidates[0]
            span=(geom.elements[ids[-1]][0]-x0)*aspect*250/space
            if len(ids)==1:
                # The sole event anchors authentic, unstretched artwork. Its
                # positive span is actual ink width, not a fabricated second
                # onset or duration-dependent horizontal interval. Consumers
                # distinguish this mode by len(note_ids)==1 and use each
                # number/bracket's original bounds relative to the one anchor.
                span=max(numeral["bounds"][2],
                         bracket["bounds"][2] if bracket is not None else 0.)
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
        if (isinstance(stored,dict) and stored and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-tuplet" and
                isinstance(v.get("number"),dict) for v in stored.values())):
            return stored
    results=extract_tuplets(svgs,model)
    if key and results:
        cache.write_json("verovio-tuplets",key,results)
    return results
