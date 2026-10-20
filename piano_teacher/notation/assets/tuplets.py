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
import math
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 6


def classes(node: ET.Element) -> set[str]:
    return set(node.get("class","").split())


def source_ids(node: ET.Element) -> tuple[str,...]:
    return tuple(el.get("id") for el in node.iter()
                 if classes(el) & {"note", "rest", "mRest"}
                 and not classes(el) & {"bounding-box","content-bounding-box"}
                 and el.get("id"))


def _owned_art(node: ET.Element):
    """Visit this tuplet's graphics without entering a nested tuplet."""
    for child in node:
        if classes(child) & {"tuplet","bounding-box","content-bounding-box"}:
            continue
        yield child
        yield from _owned_art(child)


def _display_number(node: ET.Element | None) -> str | None:
    """Read the numeral Verovio actually emitted, rather than its endpoints."""
    if node is None:
        return None
    digits = []
    for use in node.iter():
        if use.tag.rsplit("}", 1)[-1] != "use":
            continue
        href = use.get("{http://www.w3.org/1999/xlink}href", use.get("href", ""))
        code = href.removeprefix("#").split("-", 1)[0].upper()
        if code == "E88A":
            digits.append(":")
        elif len(code) == 4 and "E880" <= code <= "E889":
            digits.append(str(int(code, 16) - 0xE880))
        else:
            return None
    return "".join(digits) if digits else "".join(node.itertext()).strip() or None


def _semantic_groups(model: dict) -> list[dict]:
    """Normalize explicit group identities; legacy marks are a fallback only.

    Explicit event_ids name attacks, including rests, in musical order.
    attributes.source_id optionally names the original SVG tuplet object.
    The presence of groups (even an empty list) disables mark inference.
    """
    events = {str(e["id"]): e for e in model.get("notation_events", [])
              if e.get("id") and e.get("kind") in {"note", "rest"}}
    if "groups" in model:
        supplied = model["groups"]
        if isinstance(supplied, dict):
            supplied = supplied.values()
        result, seen = [], set()
        for group in supplied or []:
            if group.get("kind") != "tuplet":
                continue
            identifier = str(group.get("id", ""))
            if not identifier:
                continue
            if identifier in seen:
                raise ValueError(f"Duplicate semantic tuplet ID: {identifier}")
            seen.add(identifier)
            ids = [str(i) for i in group.get("event_ids", [])]
            if len(set(ids)) != len(ids) or any(i not in events for i in ids):
                continue
            ids = [i for i in ids if not events[i].get("chord")]
            if len(ids) < 2:
                continue
            result.append({**group, "id": identifier, "event_ids": ids,
                           "attributes": dict(group.get("attributes") or {})})
        return result

    lanes = defaultdict(list)
    for event in events.values():
        if not event.get("chord"):
            lanes[(event.get("staff", "right"),
                   str(event.get("voice", "1")))].append(event)
    result = []
    for (staff, voice), lane in lanes.items():
        lane.sort(key=lambda e: float(e["beat"]))
        opened = {}
        for event in lane:
            for mark in event.get("tuplet_marks", []):
                if mark.get("type") == "start":
                    number = str(mark.get("number", "1"))
                    opened[number] = {"events": [], "mark": mark}
            for group in opened.values():
                group["events"].append(event)
            for mark in event.get("tuplet_marks", []):
                if mark.get("type") != "stop":
                    continue
                number = str(mark.get("number", "1"))
                group = opened.pop(number, None)
                if group is None or len(group["events"]) < 2:
                    continue
                members = group["events"]
                ids = [str(e["id"]) for e in members]
                source = group["mark"].get("source_id") or group["mark"].get("id")
                result.append({
                    "id": str(source or f"tuplet:{staff}:{voice}:{number}:{ids[0]}:{ids[-1]}"),
                    "kind": "tuplet", "event_ids": ids, "staff": staff, "voice": voice,
                    "start_beat": float(members[0]["beat"]),
                    "end_beat": float(event["beat"]) + float(event.get("duration_beats", 0)),
                    "attributes": {**group["mark"], "source_id": source},
                    "_legacy_key": tuple(ids)})
    return result


def semantic_tuplets(model: dict) -> dict:
    """Expose distinct explicit IDs while preserving unambiguous legacy keys."""
    groups = _semantic_groups(model)
    counts = defaultdict(int)
    for group in groups:
        counts[tuple(group["event_ids"])] += 1
    return {
        (group["_legacy_key"] if "_legacy_key" in group and
         counts[tuple(group["event_ids"])] == 1 else group["id"]):
        ({"staff": group["staff"]} if "_legacy_key" in group and
         counts[tuple(group["event_ids"])] == 1 else group)
        for group in groups}


# Compatibility import for existing extraction callers.
from .svg import isolate


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


def _group_template(group: dict, events: dict, companions: list[dict]) -> str | None:
    """Ask Verovio to engrave a cross-bar compound its XML importer drops.

    This is the same isolated-template approach used for chords and notes;
    neither the model nor its source durations/identities are rewritten.
    """
    import verovio
    from .runtime import _create_verovio_toolkit

    attributes = group.get("attributes", {})
    first = events[group["event_ids"][0]]
    ratio = first.get("time_modification") or {}
    actual = int(attributes.get("actual", ratio.get("actual", 0)))
    normal = int(attributes.get("normal", ratio.get("normal", 0)))
    durations = {"whole": "1", "half": "2", "quarter": "4", "eighth": "8",
                 "16th": "16", "32nd": "32", "64th": "64", "128th": "128"}
    if actual <= 0 or normal <= 0:
        return None
    root = ET.fromstring('''<mei xmlns="http://www.music-encoding.org/ns/mei"
      meiversion="5.0"><meiHead><fileDesc><titleStmt><title>Tuplet</title></titleStmt>
      <pubStmt/></fileDesc></meiHead><music><body><mdiv><score><scoreDef>
      <staffGrp><staffDef n="1" lines="5" clef.shape="G" clef.line="2"/>
      </staffGrp></scoreDef><section><measure n="1"><staff n="1"><layer n="1"/>
      </staff></measure></section></score></mdiv></body></music></mei>''')
    ns = "{http://www.music-encoding.org/ns/mei}"
    layer = root.find(f".//{ns}layer")
    positions = {identifier: index for index, identifier in enumerate(group["event_ids"])}
    openings = defaultdict(list)
    for semantic in companions:
        ids = semantic["event_ids"]
        indices = [positions[i] for i in ids]
        if indices != list(range(indices[0], indices[-1]+1)):
            return None
        openings[indices[0]].append((indices[-1], semantic))
    for index, entries in openings.items():
        marks = [str(m.get("number", "1")) for m in
                 events[group["event_ids"][index]].get("tuplet_marks", [])
                 if m.get("type") == "start"]
        def order(entry):
            end, semantic = entry
            number = str(semantic.get("attributes", {}).get("number", "1"))
            return (-end, marks.index(number) if number in marks else 0)
        entries.sort(key=order)
    stack = []
    for index, identifier in enumerate(group["event_ids"]):
        for end, semantic in openings[index]:
            if stack and end > stack[-1][0]:
                return None  # Crossing spans cannot be represented as nesting.
            attrs_source = semantic.get("attributes", {})
            attrs = {"{http://www.w3.org/XML/1998/namespace}id": semantic["id"],
                     "num": str(attrs_source.get("actual", actual)),
                     "numbase": str(attrs_source.get("normal", normal)),
                     "bracket.visible": "false" if attrs_source.get("bracket") == "no" else "true"}
            if attrs_source.get("placement") in {"above", "below"}:
                attrs["bracket.place"] = attrs_source["placement"]
            if attrs_source.get("show-number") == "both":
                attrs["num.format"] = "ratio"
            elif attrs_source.get("show-number", attrs_source.get("show_number")) == "none":
                attrs["num.visible"] = "false"
            compound = ET.SubElement(stack[-1][1] if stack else layer, ns+"tuplet", attrs)
            stack.append((end, compound))
        event = events[identifier]
        duration = durations.get(event.get("note_type"))
        if duration is None:
            return None
        attrs = {"{http://www.w3.org/XML/1998/namespace}id": identifier,
                 "dur": duration, "dots": str(int(event.get("dots", 0)))}
        kind = event["kind"]
        if kind == "note":
            pitch = event.get("spelling") or {}
            if "step" not in pitch or "octave" not in pitch:
                return None
            attrs.update(pname=pitch["step"].lower(), oct=str(pitch["octave"]))
        ET.SubElement(stack[-1][1] if stack else layer, ns+kind, attrs)
        while stack and stack[-1][0] == index:
            stack.pop()
    # The installed importer expects MEI's default namespace, not ns0 tags.
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    root.set("xmlns", ns[1:-1])
    toolkit = _create_verovio_toolkit(verovio)
    if not toolkit.setOptions({"inputFrom": "mei", "svgViewBox": True, "svgBoundingBoxes": True,
            "svgContentBoundingBoxes": True, "breaks": "none", "pageWidth": 1800}):
        raise RuntimeError("Verovio rejected cross-measure tuplet options")
    if not toolkit.loadData(ET.tostring(root, encoding="unicode")):
        raise RuntimeError("Verovio rejected cross-measure tuplet compound")
    return toolkit.renderToSVG(1)


def extract_tuplets(svgs: list[str] | tuple[str,...], model: dict, *,
                    _template_fallback: bool = True) -> dict:
    from .svg_geometry import parse_svg_geometry
    desired = _semantic_groups(model)
    if not desired:
        return {}
    sequence_counts = defaultdict(int)
    for semantic in desired:
        sequence_counts[tuple(semantic["event_ids"])] += 1
    events = {str(event["id"]): event for event in model.get("notation_events", [])
              if event.get("kind") in {"note", "rest"} and event.get("id")}
    visual_ids = {str(e["id"]) for e in model.get("visual_events", [])
                  if e.get("id") and e.get("kind") == "grace"}
    output = {}
    for page in svgs:
        root = ET.fromstring(page)
        geom = parse_svg_geometry(page)
        viewport = [float(v) for v in root.get("viewBox", "").replace(",", " ").split()]
        aspect = viewport[2] / viewport[3]
        # Rest event identities may be normalized separately by the model.
        # Only use an alias when its original SVG ID exists on this page.
        source_to_event = {i: i for i in events if i in geom.elements}
        for identifier, event in events.items():
            alias = str(event.get("source_id") or "")
            if identifier not in geom.elements and alias in geom.elements:
                source_to_event.setdefault(alias, identifier)
        event_to_source = {event: source for source, event in source_to_event.items()}
        tuplet_nodes = [g for g in root.iter() if "tuplet" in classes(g)
                        and not classes(g) & {"bounding-box", "content-bounding-box"}]
        parents = {child: parent for parent in root.iter() for child in parent}
        memberships = {}
        for group in tuplet_nodes:
            raw = tuple(i for i in source_ids(group) if i not in visual_ids)
            memberships[group] = (tuple(source_to_event[i] for i in raw
                if not events[source_to_event[i]].get("chord"))
                if all(i in source_to_event for i in raw) else None)
        for group in tuplet_nodes:
            art = list(_owned_art(group))
            number_nodes = [n for n in art if "tupletNum" in classes(n)]
            bracket_nodes = [n for n in art if "tupletBracket" in classes(n)]
            if len(number_nodes) > 1:
                continue
            display_number = _display_number(number_nodes[0] if number_nodes else None)
            contained = memberships[group]
            if contained is None:
                continue
            source_id = group.get("id", "")
            exact = [s for s in desired if source_id and source_id in {
                s["id"], str(s.get("attributes", {}).get("source_id") or ""),
                str(s.get("attributes", {}).get("id") or "")}]
            possible = exact or desired
            peers = [s for s in desired if tuple(s["event_ids"]) == contained]
            if not exact and len(peers) > 1 and sum(
                    members == contained for members in memberships.values()) == len(peers):
                marks = [str(m.get("number", "1")) for m in
                    events[contained[0]].get("tuplet_marks", []) if m.get("type") == "start"]
                numbers = [str(s.get("attributes", {}).get("number", "1")) for s in peers]
                if len(set(numbers)) == len(peers) and all(n in marks for n in numbers):
                    # Match actual SVG nesting to the source opening order.
                    # A partial/collapsed importer tree is never guessed.
                    rank, ancestor = 0, parents.get(group)
                    while ancestor is not None:
                        if memberships.get(ancestor) == contained:
                            rank += 1
                        ancestor = parents.get(ancestor)
                    peers.sort(key=lambda s: marks.index(str(s["attributes"].get("number", "1"))))
                    if rank < len(peers):
                        possible = [peers[rank]]
            candidates = []
            for semantic in possible:
                ids = tuple(semantic["event_ids"])
                if contained and contained != ids:
                    continue
                attributes = semantic.get("attributes", {})
                if attributes.get("actual") and display_number is not None:
                    expected = str(attributes["actual"])
                    if attributes.get("show-number", attributes.get("show_number")) in {"ratio", "both"}:
                        expected += ":" + str(attributes.get("normal", ""))
                    if display_number != expected:
                        continue
                key = ("|".join(ids) if "_legacy_key" in semantic and
                       sequence_counts[ids] == 1 else semantic["id"])
                if key in output or any(i not in event_to_source for i in ids):
                    continue
                anchors = [geom.elements[event_to_source[i]] for i in ids]
                x0, y0, system = anchors[0]
                x1, _, last_system = anchors[-1]
                if system != last_system or x1 <= x0 or any(
                        a[0] >= b[0] or b[2] != system
                        for a, b in zip(anchors, anchors[1:])):
                    continue
                staff = geom.staff_systems[system]["staff_lines"]
                if len(staff) < 5:
                    continue
                space = staff[1] - staff[0]
                if not 0 < space < 1:
                    continue
                try:
                    numeric = (crop_art(isolate(root, number_nodes[0]),
                        space, (x0, y0), "verovio-tuplet-number")
                        if number_nodes else None)
                    bracket = (crop_art(isolate(root, bracket_nodes[0]),
                        space, (x0, y0), "verovio-tuplet-bracket")
                        if len(bracket_nodes) == 1 else None)
                except (ValueError, RuntimeError, ET.ParseError, OverflowError):
                    continue
                if number_nodes and numeric is None:
                    continue
                span = (x1 - x0) * aspect * 250 / space
                if span <= 0 or not math.isfinite(span):
                    continue
                # Exact source object IDs outrank spatial guesses. For old
                # Verovio exports with detached graphics, require proximity
                # and a single semantic candidate; never borrow nested ink.
                if not contained and not exact:
                    if numeric is not None:
                        nb = numeric["bounds"]
                        if abs(nb[0] + nb[2] * .5 - span * .5) > 500:
                            continue
                    elif bracket is None:
                        continue
                    if bracket is not None:
                        box = bracket["bounds"]
                        if abs(box[0]) > 620 or abs(box[0] + box[2] - span) > 620:
                            continue
                candidates.append((key, semantic, span, numeric, bracket))
            if len(candidates) != 1:
                continue
            key, semantic, span, numeral, bracket = candidates[0]
            ids = semantic["event_ids"]
            output[key] = {
                "source": "verovio-engraved-tuplet", "units_per_space": 250,
                "group_id": semantic["id"], "source_id": source_id,
                "display_number": display_number,
                "event_ids": list(ids), "note_ids": list(ids),
                "span": span, "number": numeral, "bracket": bracket}
    if _template_fallback and svgs:
        templates = {}
        for semantic in desired:
            ids = tuple(semantic["event_ids"])
            key = ("|".join(ids) if "_legacy_key" in semantic and
                   sequence_counts[ids] == 1 else semantic["id"])
            attributes = semantic.get("attributes", {})
            per_group_ratio = attributes.get("actual") and attributes.get("normal")
            if key in output or (not per_group_ratio and
                    len({events[i].get("measure") for i in ids}) < 2):
                continue
            # Reconstruct the entire containing compound so nested number
            # and bracket Y positions are also Verovio's, not overlapping
            # independently engraved templates.
            available = [s for s in desired if s.get("attributes", {}).get("actual")
                         and s.get("attributes", {}).get("normal") and
                         s.get("staff") == semantic.get("staff") and
                         str(s.get("voice", "1")) == str(semantic.get("voice", "1"))]
            containing = [s for s in available if set(ids).issubset(s["event_ids"])]
            root_group = max(containing, key=lambda s: len(s["event_ids"])) if containing else semantic
            root_ids = set(root_group["event_ids"])
            companions = [s for s in available if set(s["event_ids"]).issubset(root_ids)] or [semantic]
            template_key = tuple(s["id"] for s in companions)
            if template_key not in templates:
                template = _group_template(root_group, events, companions)
                templates[template_key] = (extract_tuplets([template], {
                    "notation_events": list(events.values()), "groups": companions},
                    _template_fallback=False) if template is not None else {})
            fragments = templates[template_key]
            # Restore every related object from this one complete engine
            # engraving. Mixing an imported inner with a restored outer
            # loses the nested bracket/number clearance Verovio assigned.
            for companion in companions:
                if companion["id"] not in fragments:
                    continue
                member_ids = tuple(companion["event_ids"])
                asset_key = ("|".join(member_ids) if "_legacy_key" in companion and
                             sequence_counts[member_ids] == 1 else companion["id"])
                output[asset_key] = {**fragments[companion["id"]],
                    "engraving": "group-template", "compound_id": root_group["id"]}
    return output


def tuplet_fragments(svgs,model,cache=None,identity="") -> dict:
    key=cache.key("verovio-real-tuplets",VERSION,identity,
                  _semantic_groups(model)) if (
        cache is not None and identity) else None
    if key:
        stored=cache.read_json("verovio-tuplets",key)
        if (isinstance(stored,dict) and stored and all(
                isinstance(v,dict) and
                v.get("source")=="verovio-engraved-tuplet" and
                "number" in v and (v["number"] is None or
                isinstance(v["number"],dict)) for v in stored.values())):
            return stored
    results=extract_tuplets(svgs,model)
    if key and results:
        cache.write_json("verovio-tuplets",key,results)
    return results
