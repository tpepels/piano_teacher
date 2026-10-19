"""Extract two-note beam *ink* from the score's real Verovio SVG pages.

Unlike synthesizing beams in Godot, this uses the existing, source-accurate
Verovio engraving. Only the <g class="beam">'s graphical children are kept:
notes, noteheads, stems and unrelated page decorations are excluded.

A fragment has two named notehead anchors and is horizontally remapped to
the SAME two source beats on the native timeline. Groups with intermediate
anchors need piecewise remapping and are deliberately left to the previous
renderer until that is implemented.
"""
from __future__ import annotations

import base64
from io import BytesIO
import copy
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 1
MAX_FRAGMENTS = 120


def _classes(node: ET.Element) -> set[str]:
    return set(node.get("class", "").split())


def _note_ids(group: ET.Element) -> tuple[str, ...]:
    return tuple(node.get("id", "") for node in group.iter()
                 if "note" in _classes(node) and node.get("id"))


def _filter_beam_svg(svg: str, selected: tuple[str, str]) -> str | None:
    """Leave original beam ink and required SVG <defs>, not individual notes."""
    root = ET.fromstring(svg)
    candidate = next((node for node in root.iter()
                      if "beam" in _classes(node)
                      and _note_ids(node) == selected), None)
    if candidate is None:
        return None
    beam_id = candidate.get("id")
    # Even a beam without an XML id has a unique position among candidates.
    siblings = [node for node in root.iter()
                if "beam" in _classes(node) and _note_ids(node) == selected]
    if len(siblings) != 1:
        return None

    def strip_notes(node: ET.Element) -> None:
        for child in list(node):
            classes = _classes(child)
            if classes & {"note", "rest", "bounding-box",
                          "content-bounding-box"}:
                node.remove(child)
            else:
                strip_notes(child)

    def prune(node: ET.Element) -> bool:
        if node is candidate:
            strip_notes(node)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        keep = False
        for child in list(node):
            if prune(child):
                keep = True
            else:
                node.remove(child)
        return keep

    if not prune(root):
        return None
    # A beam is a polygon/path; never accept a fallback notehead shape.
    shape_count = sum(1 for node in candidate.iter()
                      if node.tag.rsplit("}",1)[-1] in {"path","polygon","polyline"})
    if not shape_count:
        return None
    return ET.tostring(root, encoding="unicode")


def extract_beam_fragments(svgs: list[str] | tuple[str,...],
                           model: dict) -> dict:
    """Return native-timeline-ready beam-only masks indexed by note pair IDs.

    Deliberately conservative: only beams with two note attacks, no chord
    siblings, and matching semantic source groups are eligible. No changed
    event identity or tempo-dependent note coordinate is ever returned.
    """
    import cairosvg
    from .score_geometry import parse_svg_geometry

    # Match the two semantic attacks in order; other Verovio beam groupings
    # cannot be attached safely to this model without a full multi-anchor map.
    events = {e.get("id"):e for e in model.get("notation_events",[])
              if e.get("kind")=="note" and e.get("id")}
    eligible: dict[tuple[str,str],str] = {}
    for page in svgs:
        root = ET.fromstring(page)
        for node in root.iter():
            if "beam" not in _classes(node):
                continue
            ids = _note_ids(node)
            if len(ids) != 2 or any(i not in events for i in ids):
                continue
            a,b = (events[ids[0]],events[ids[1]])
            if (a.get("staff") != b.get("staff") or
                    a.get("voice") != b.get("voice") or
                    a.get("measure") != b.get("measure") or
                    a.get("chord") or b.get("chord") or
                    float(a["beat"]) >= float(b["beat"])):
                continue
            eligible[ids] = page
            if len(eligible) >= MAX_FRAGMENTS:
                break
        if len(eligible) >= MAX_FRAGMENTS:
            break
    output = {}
    page_geometry = {}
    for ids,page in eligible.items():
        try:
            if page not in page_geometry:
                page_geometry[page] = parse_svg_geometry(page)
            geom = page_geometry[page]
            if not all(i in geom.elements for i in ids):
                continue
            x0,y0,system = geom.elements[ids[0]]
            x1,y1,other_system = geom.elements[ids[1]]
            if other_system != system or x1 <= x0:
                continue
            lines = geom.staff_systems[system]["staff_lines"]
            if len(lines) < 5:
                continue
            filtered = _filter_beam_svg(page,ids)
            if filtered is None:
                continue
            png = cairosvg.svg2png(bytestring=filtered.encode(),output_width=1600)
            with Image.open(BytesIO(png)) as decoded:
                rgba = decoded.convert("RGBA")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None:
                continue
            staff_space = (lines[1]-lines[0])*rgba.height
            span = (x1-x0)*rgba.width
            if not 4 < staff_space < 300 or span < 4:
                continue
            left,top,right,bottom = bbox
            # Reject page-spanning or mistaken template geometry.
            if (right-left) > span*2.2:
                continue
            # Locate the Verovio beam edge at both stem attachment points.
            # These offsets let Godot finish each native stem exactly on the
            # REAL exported beam polygon, rather than a guessed line.
            beam_centre = (top+bottom)*.5
            up = beam_centre < y0*rgba.height
            edges = []
            for note_x,note_y in ((x0,y0),(x1,y1)):
                stem_x = note_x*rgba.width + (.54 if up else -.54)*staff_space
                px = round(stem_x)
                sample = []
                for col in range(max(0,px-3),min(rgba.width,px+4)):
                    for row in range(top,bottom):
                        if alpha.getpixel((col,row)) > 50:
                            sample.append(row)
                if not sample:
                    break
                edge_y = min(sample) if up else max(sample)
                edges.append((edge_y-note_y*rgba.height)*250/staff_space)
            if len(edges) != 2:
                continue
            crop = rgba.crop(bbox)
            white = Image.new("RGBA",crop.size,(255,255,255,255))
            white.putalpha(crop.getchannel("A"))
            buffer=BytesIO()
            white.save(buffer,format="PNG",optimize=True)
            bounds = [(left-x0*rgba.width)*250/staff_space,
                      (top-y0*rgba.height)*250/staff_space,
                      (right-left)*250/staff_space,
                      (bottom-top)*250/staff_space]
            intrinsic_span = span*250/staff_space
            if not all(math.isfinite(v) for v in bounds+[intrinsic_span]):
                continue
            output["|".join(ids)] = {
                "source":"verovio-engraved-beam","units_per_space":250,
                "bounds":bounds, "span":intrinsic_span,
                "note_ids":list(ids), "stem_up":up, "tip_offsets":edges,
                "png_base64":base64.b64encode(buffer.getvalue()).decode(),
            }
        except (KeyError,ValueError,TypeError,ET.ParseError,RuntimeError,
                OverflowError):
            # A missing/ambiguous contour is not a licence to reposition any
            # notes. Keep the existing group renderer for that pair.
            continue
    return output


def beam_fragments(svgs, model, cache=None, cache_identity="") -> dict:
    key = (cache.key("real-verovio-beams",VERSION,cache_identity)
           if cache is not None and cache_identity else None)
    if key:
        stored=cache.read_json("verovio-beams",key)
        if isinstance(stored,dict) and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-beam" and
                len(v.get("note_ids",[]))==2 for v in stored.values()):
            return stored
    result=extract_beam_fragments(svgs,model)
    if key:
        cache.write_json("verovio-beams",key,result)
    return result
