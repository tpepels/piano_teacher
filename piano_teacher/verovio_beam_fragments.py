"""Extract multi-note beam *ink* from the score's real Verovio SVG pages.

Unlike synthesizing beams in Godot, this uses the existing, source-accurate
Verovio engraving. Only the <g class="beam">'s graphical children are kept:
notes, noteheads, stems and unrelated page decorations are excluded.

Each fragment has every named notehead anchor. Godot draws its image in
pieces between adjacent anchors, so intermediate note positions cannot drift
or inherit Verovio's horizontal page spacing.
"""
from __future__ import annotations

import base64
from io import BytesIO
import copy
import math
import os
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 2
MAX_FRAGMENTS = 120


def _classes(node: ET.Element) -> set[str]:
    return set(node.get("class", "").split())


def _note_ids(group: ET.Element) -> tuple[str, ...]:
    return tuple(node.get("id", "") for node in group.iter()
                 if "note" in _classes(node) and node.get("id"))


def _filter_beam_svg(svg: str, selected: tuple[str, ...]) -> str | None:
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
    """Return source-accurate beam masks with an anchor for EVERY note.

    Chords, duplicate-time events and ambiguous groups remain in the existing
    renderer. No tempo-dependent page positions replace source-beat timing.
    """
    import cairosvg
    from .score_geometry import parse_svg_geometry

    # Match the two semantic attacks in order; other Verovio beam groupings
    # cannot be attached safely to this model without a full multi-anchor map.
    events = {e.get("id"):e for e in model.get("notation_events",[])
              if e.get("kind")=="note" and e.get("id")}
    eligible: dict[tuple[str,...],str] = {}
    for page in svgs:
        root = ET.fromstring(page)
        for node in root.iter():
            if "beam" not in _classes(node):
                continue
            ids = _note_ids(node)
            if not 2 <= len(ids) <= 16 or any(i not in events for i in ids):
                continue
            members = [events[i] for i in ids]
            if (any(e.get("chord") for e in members) or
                    any((e.get("staff"),e.get("voice"),e.get("measure")) !=
                        (members[0].get("staff"),members[0].get("voice"),
                         members[0].get("measure")) for e in members) or
                    any(float(a["beat"]) >= float(b["beat"]) for a,b
                        in zip(members,members[1:]))):
                continue
            eligible[ids] = page
            if len(eligible) >= MAX_FRAGMENTS:
                break
        if len(eligible) >= MAX_FRAGMENTS:
            break
    if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
        print("VEROVIO_BEAM_CANDIDATES:",len(eligible),
              [(ids, len(svg)) for ids,svg in eligible.items()])
    output = {}
    page_geometry = {}
    for ids,page in eligible.items():
        try:
            if page not in page_geometry:
                page_geometry[page] = parse_svg_geometry(page)
            geom = page_geometry[page]
            if not all(i in geom.elements for i in ids):
                continue
            anchors = [geom.elements[i] for i in ids]
            x0,y0,system = anchors[0]
            x1 = anchors[-1][0]
            if (any(e[2] != system for e in anchors) or
                    any(a[0] >= b[0] for a,b in zip(anchors,anchors[1:]))):
                continue
            lines = geom.staff_systems[system]["staff_lines"]
            if len(lines) < 5:
                continue
            filtered = _filter_beam_svg(page,ids)
            if filtered is None:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_NO_STANDALONE_SHAPE:",ids)
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
            for note_x,note_y,_ in anchors:
                stem_x = note_x*rgba.width + (.54 if up else -.54)*staff_space
                px = round(stem_x)
                sample = []
                # Verovio's stem attachment differs from the centre of
                # its notehead. Scan a full space around the approximate
                # edge, preferring the nearest actual beam pixel.
                for distance in range(round(staff_space*1.1)+1):
                    columns = (px-distance,px+distance) if distance else (px,)
                    for col in columns:
                        if col < 0 or col >= rgba.width:
                            continue
                        sample = [row for row in range(top,bottom)
                                  if alpha.getpixel((col,row)) > 50]
                        if sample:
                            break
                    if sample:
                        break
                if not sample:
                    break
                edge_y = min(sample) if up else max(sample)
                edges.append((edge_y-note_y*rgba.height)*250/staff_space)
            if len(edges) != len(anchors):
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_STEM_EDGE_MISSING:",
                          ids,len(edges),len(anchors))
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
                "head_offsets":[(x-x0)*rgba.width*250/staff_space
                                for x,_,_ in anchors],
                "png_base64":base64.b64encode(buffer.getvalue()).decode(),
            }
        except (KeyError,ValueError,TypeError,ET.ParseError,RuntimeError,
                OverflowError) as exc:
            if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                print("VEROVIO_BEAM_FAILED:",ids,type(exc).__name__,exc)
            # A missing/ambiguous contour is not a licence to reposition any
            # notes. Keep the existing group renderer for that passage.
            continue
    return output


def beam_fragments(svgs, model, cache=None, cache_identity="") -> dict:
    key = (cache.key("real-verovio-beams",VERSION,cache_identity)
           if cache is not None and cache_identity else None)
    if key:
        stored=cache.read_json("verovio-beams",key)
        if isinstance(stored,dict) and stored and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-beam" and
                2 <= len(v.get("note_ids",[])) <= 16 and
                len(v.get("head_offsets",[]))==len(v.get("note_ids",[]))
                for v in stored.values()):
            return stored
    result=extract_beam_fragments(svgs,model)
    # Do not persist an empty atlas while a Verovio version might be
    # missing an SVG class/shape. A corrected extractor must retry.
    if key and result:
        cache.write_json("verovio-beams",key,result)
    return result
