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
import math
import os
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 6


def _classes(node: ET.Element) -> set[str]:
    return set(node.get("class", "").split())


def _note_ids(group: ET.Element) -> tuple[str, ...]:
    # With svgBoundingBoxes enabled, Verovio adds diagnostic groups
    # `class="note bounding-box"` and `note content-bounding-box`.
    # Those are not score notes and must never become musical anchors.
    return tuple(node.get("id", "") for node in group.iter()
                 if "note" in _classes(node)
                 and not _classes(node) & {"bounding-box","content-bounding-box"}
                 and node.get("id"))


def _filter_beam_svg(svg: str, selected: tuple[str, ...]) -> str | None:
    """Leave original beam ink and required SVG <defs>, not individual notes."""
    root = ET.fromstring(svg)
    candidate = next((node for node in root.iter()
                      if "beam" in _classes(node)
                      and _note_ids(node) == selected), None)
    if candidate is None:
        return None
    # Even a beam without an XML id has a unique position among candidates.
    siblings = [node for node in root.iter()
                if "beam" in _classes(node) and _note_ids(node) == selected]
    if len(siblings) != 1:
        return None

    def strip_notes(node: ET.Element) -> None:
        for child in list(node):
            classes = _classes(child)
            if classes & {"note", "chord", "rest", "stem", "flag",
                          "tupletNum", "tupletBracket", "bounding-box",
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
    # Verovio's reference pages can fade the non-selected staff with a
    # 0.48 ancestor opacity. Native Godot applies that presentation fade
    # based on its active-hand selection; keeping it in a fragment would
    # bake an irreversible double fade into source beam pixels.
    for ancestor in root.iter():
        if ancestor.get("opacity") == "0.48":
            del ancestor.attrib["opacity"]
    # A beam is a polygon/path; never accept a fallback notehead shape.
    shape_count = sum(1 for node in candidate.iter()
                      if node.tag.rsplit("}",1)[-1] in {"path","polygon","polyline"})
    if not shape_count:
        return None
    return ET.tostring(root, encoding="unicode")


def expected_beam_groups(svgs, model: dict) -> list[str]:
    """Enumerate genuine beam source groups, not meter-based guesses.

    Extraction may reject or fail a group, but Godot must never silently
    invent an alternative contour if Verovio did engrave a beam.
    """
    events={str(e["id"]):e for e in model.get("notation_events",[])
            if e.get("kind")=="note" and e.get("id")}
    found=set()
    for page in svgs:
        root=ET.fromstring(page)
        for group in root.iter():
            if "beam" not in _classes(group) or _classes(group) & {
                    "bounding-box","content-bounding-box"}:
                continue
            source=_note_ids(group)
            if len(source)<2 or any(i not in events for i in source):
                continue
            leaders=[events[i] for i in source if not events[i].get("chord")]
            if len(leaders)<2:
                continue
            lane={(e.get("staff"),e.get("voice"),e.get("measure"))
                  for e in leaders}
            if len(lane)!=1 or any(
                    float(a.get("beat",0))>=float(b.get("beat",0))
                    for a,b in zip(leaders,leaders[1:])):
                continue
            found.add("|".join(str(e["id"]) for e in leaders))
    return sorted(found)


def extract_beam_fragments(svgs: list[str] | tuple[str,...],
                           model: dict) -> dict:
    """Return source-accurate beam masks with an anchor for EVERY note.

    Chord tones retain their source IDs and share one attack anchor. No
    tempo-dependent page positions replace source-beat timing.
    """
    import cairosvg
    from ...source_svg import parse_svg_geometry

    # Every source attack gets its own anchor, including long beam groups.
    events = {e.get("id"):e for e in model.get("notation_events",[])
              if e.get("kind")=="note" and e.get("id")}
    eligible: dict[tuple[str,...],tuple[str,tuple[str,...],tuple[tuple[str,...],...]]] = {}
    for page in svgs:
        root = ET.fromstring(page)
        for node in root.iter():
            if "beam" not in _classes(node):
                continue
            full_ids = _note_ids(node)
            if len(full_ids) < 2 or any(i not in events for i in full_ids):
                continue
            full = [events[i] for i in full_ids]
            if any((e.get("staff"),e.get("voice"),e.get("measure")) !=
                   (full[0].get("staff"),full[0].get("voice"),
                    full[0].get("measure")) for e in full):
                continue
            attacks = []
            chord_ids = []
            for event in full:
                if event.get("chord"):
                    if not chord_ids or float(events[chord_ids[-1][0]]["beat"]) != float(event["beat"]):
                        break
                    chord_ids[-1].append(str(event["id"]))
                else:
                    attacks.append(event)
                    chord_ids.append([str(event["id"])])
            else:
                ids = tuple(str(event["id"]) for event in attacks)
                if (len(ids) >= 2 and
                    all(float(a["beat"]) < float(b["beat"])
                        for a,b in zip(attacks,attacks[1:]))):
                    eligible[ids] = page,full_ids,tuple(tuple(g) for g in chord_ids)
    if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
        print("VEROVIO_BEAM_CANDIDATES:",len(eligible),
              [(ids, len(pair[0])) for ids,pair in eligible.items()])
    output = {}
    page_geometry = {}
    for ids,(page,full_ids,chord_ids) in eligible.items():
        try:
            if page not in page_geometry:
                page_geometry[page] = parse_svg_geometry(page)
            geom = page_geometry[page]
            if not all(i in geom.elements for i in ids):
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_MISSING_ANCHORS:",ids)
                continue
            anchors = [geom.elements[i] for i in ids]
            x0,y0,system = anchors[0]
            x1 = anchors[-1][0]
            if (any(e[2] != system for e in anchors) or
                    any(a[0] >= b[0] for a,b in zip(anchors,anchors[1:]))):
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_INVALID_ORDER:",ids,anchors)
                continue
            lines = geom.staff_systems[system]["staff_lines"]
            if len(lines) < 5:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_MISSING_STAFF:",ids,lines)
                continue
            filtered = _filter_beam_svg(page,full_ids)
            if filtered is None:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_NO_STANDALONE_SHAPE:",ids)
                continue
            # SVG layout anchors are normalized separately by viewport
            # width/height. Convert X via width/height before expressing it
            # in staff-space units; Y already uses normalized viewport height.
            viewport = [float(value) for value in
                        ET.fromstring(page).get("viewBox","").replace(","," ").split()]
            if len(viewport) != 4 or min(viewport[2:]) <= 0:
                continue
            aspect = viewport[2]/viewport[3]
            # Rasterize the ACTUAL isolated Verovio beam polygon, at a
            # bounded local scale. A 1600px full-page screenshot previously
            # yielded a 63x3 source mask that was enlarged fivefold in
            # practice, leaving gray antialias gaps and false beam levels.
            # Recording the vector paths locally keeps complete authentic
            # beam ink without allocating a 24k-wide whole-page surface.
            from .tuplets import _local_vector_art
            space = lines[1]-lines[0]
            art = _local_vector_art(
                filtered,space,(x0,y0),"verovio-engraved-beam")
            if art is None:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_NO_BOUNDED_VECTOR_ART:",ids)
                continue
            bounds = [float(number) for number in art["bounds"]]
            if (len(bounds) != 4 or min(bounds[2:]) <= 0.0
                    or not all(math.isfinite(n) for n in bounds)):
                continue
            with Image.open(BytesIO(base64.b64decode(art["png_base64"]))) as decoded:
                rgba = decoded.convert("RGBA")
            alpha = rgba.getchannel("A")
            intrinsic_span = (x1-x0)*aspect*250/space
            if (intrinsic_span <= 4 or bounds[2] > intrinsic_span*2.2
                    or rgba.width <= 1 or rgba.height <= 1):
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_BAD_BOUNDED_SCALE:",ids,bounds,intrinsic_span)
                continue
            # The same normalized page coordinates supply the source
            # musical anchors and physical reference-stem positions.
            # Convert them to the bounded raster via its measured extent,
            # never by assuming the image is a resized whole SVG page.
            x_scale = rgba.width/bounds[2]
            y_scale = rgba.height/bounds[3]
            up = bounds[1]+bounds[3]*.5 < 0
            edges = []
            for index,(note_x,note_y,_) in enumerate(anchors):
                source_heads = [geom.elements[ident] for ident in chord_ids[index]]
                reference_y = (max(head[1] for head in source_heads) if up
                               else min(head[1] for head in source_heads))
                source_stem = getattr(geom,"stem_x",{}).get(ids[index])
                stem_units = (((source_stem-x0)*aspect*250/space)
                    if source_stem is not None else
                    (note_x-x0)*aspect*250/space+(.54 if up else -.54)*250)
                position = round((stem_units-bounds[0])*x_scale)
                sample = []
                for distance in range(round(1.1*250*x_scale)+1):
                    columns = (position-distance,position+distance) if distance else (position,)
                    for column in columns:
                        if not 0 <= column < rgba.width:
                            continue
                        sample = [row for row in range(rgba.height)
                                  if alpha.getpixel((column,row)) > 50]
                        if sample:
                            break
                    if sample:
                        break
                if not sample:
                    break
                edge_y = min(sample) if up else max(sample)
                edge_units = bounds[1]+(edge_y+.5)/y_scale
                reference_units = (reference_y-y0)*250/space
                edges.append(edge_units-reference_units)
            if len(edges) != len(anchors):
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_STEM_EDGE_MISSING:",
                          ids,len(edges),len(anchors))
                continue
            output["|".join(ids)] = {
                "source":"verovio-engraved-beam","units_per_space":250,
                "bounds":bounds, "span":intrinsic_span,
                "note_ids":list(ids), "chord_note_ids":[list(g) for g in chord_ids],
                "stem_up":up, "tip_offsets":edges,
                "head_offsets":[(x-x0)*aspect*250/space for x,_,_ in anchors],
                "png_base64":art["png_base64"],
            }
        except (KeyError,ValueError,TypeError,ET.ParseError,RuntimeError,
                OverflowError) as exc:
            if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                print("VEROVIO_BEAM_FAILED:",ids,type(exc).__name__,exc)
            # A missing/ambiguous contour is not a licence to reposition any
            # notes. Keep the existing group renderer for that passage.
            continue
    return output


BASE_RASTER_WIDTH = 1600
MIN_STAFF_SPACE_PX = 4.5     # below this a rasterized beam is not legible
TARGET_STAFF_SPACE_PX = 8.0
MAX_RASTER_WIDTH = 24000


class BeamExtractionError(Exception):
    """A required beam cannot be extracted; never publish a silent empty atlas."""


def beam_fragments(svgs, model, cache=None, cache_identity="") -> dict:
    key = (cache.key("real-verovio-beams",VERSION,cache_identity)
           if cache is not None and cache_identity else None)
    if key:
        stored=cache.read_json("verovio-beams",key)
        if isinstance(stored,dict) and stored and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-beam" and
                len(v.get("note_ids",[])) >= 2 and
                len(v.get("head_offsets",[]))==len(v.get("note_ids",[]))
                for v in stored.values()):
            return stored
    result=extract_beam_fragments(svgs,model)
    # Do not persist an empty atlas while a Verovio version might be
    # missing an SVG class/shape. A corrected extractor must retry.
    if key and result:
        cache.write_json("verovio-beams",key,result)
    return result
