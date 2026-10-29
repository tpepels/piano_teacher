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

VERSION = 5


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
            png = cairosvg.svg2png(bytestring=filtered.encode(),output_width=1600)
            with Image.open(BytesIO(png)) as decoded:
                rgba = decoded.convert("RGBA")
            alpha = rgba.getchannel("A")
            bbox = alpha.getbbox()
            if bbox is None:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_EMPTY_IMAGE:",ids)
                continue
            staff_space = (lines[1]-lines[0])*rgba.height
            span = (x1-x0)*rgba.width
            if not 4 < staff_space < 300 or span < 4:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_BAD_SCALE:",ids,staff_space,span)
                continue
            left,top,right,bottom = bbox
            # Reject page-spanning or mistaken template geometry.
            if (right-left) > span*2.2:
                if os.environ.get("PIANO_TEACHER_BEAM_DEBUG") == "1":
                    print("VEROVIO_BEAM_TOO_WIDE:",ids,right-left,span)
                continue
            # Locate the original Verovio beam edge at each stem attachment.
            # These offsets let Godot finish each native stem exactly on the
            # REAL exported beam polygon, rather than a guessed line.
            beam_centre = (top+bottom)*.5
            up = beam_centre < y0*rgba.height
            edges = []
            for index,(note_x,note_y,_) in enumerate(anchors):
                # Beamed chords attach to the outermost actual Verovio
                # notehead. The leader may be an inner chord tone.
                source_heads = [geom.elements[id] for id in chord_ids[index]]
                reference_y = (max(head[1] for head in source_heads) if up
                               else min(head[1] for head in source_heads))
                actual_stem = getattr(geom, "stem_x", {}).get(ids[index])
                stem_x = (actual_stem*rgba.width if actual_stem is not None else
                          note_x*rgba.width + (.54 if up else -.54)*staff_space)
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
                edges.append((edge_y-reference_y*rgba.height)*250/staff_space)
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
                "note_ids":list(ids), "chord_note_ids":[list(g) for g in chord_ids],
                "stem_up":up, "tip_offsets":edges,
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
