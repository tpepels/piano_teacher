"""Identity-bound, authentic Verovio annotation art for the linear native axis.

Each required mark must resolve to one original SVG group. Raster masks are
cropped from that group; the SVG contours, inherited transforms and definitions
are retained for inspection. Fixed text/glyphs and stretchable spans are separate
parts. Bounds use 250 units per staff space, relative to the semantic beat X and
the top staff line Y. A complete grace beam is shared by its individual IDs.
"""
from __future__ import annotations

import base64
import copy
import hashlib
from io import BytesIO
import json
import math
import xml.etree.ElementTree as ET

from PIL import Image

from .svg import isolate
from .svg_geometry import parse_svg_geometry

VERSION = 2
_DIAGNOSTIC = {"bounding-box", "content-bounding-box"}
_KINDS = {
    "dynamic": {"dynam"}, "dynamics": {"dynam"},
    "hairpin": {"hairpin"}, "articulation": {"artic"},
    "ornament": {"trill", "mordent", "turn", "ornam", "ornament"},
    "pedal": {"pedal"}, "volta": {"ending"}, "grace": {"note", "graceGrp"},
}
_KINDS.update({"wedge": _KINDS["hairpin"], "articulations": _KINDS["articulation"],
               "ornaments": _KINDS["ornament"], "ending": _KINDS["volta"]})
_SPANS = {"hairpin", "wedge", "pedal", "volta", "ending"}
_SHAPES = {"path", "line", "polyline", "polygon", "rect", "circle", "ellipse"}


def _classes(node):
    return set(node.get("class", "").split())


def _required(model):
    desired = [event for event in model.get("annotations", [])
               if event.get("kind") not in {"slur", "slurs"}] + [
        event for event in model.get("visual_events", []) if event.get("kind") == "grace"]
    result = {}
    events = {str(e["id"]): e for e in model.get("notation_events", []) if e.get("id")}
    for item in desired:
        ident = item.get("id")
        kind = item.get("kind")
        if not isinstance(ident, str) or not ident or ident in result:
            raise ValueError(f"Missing or duplicate annotation identity: {ident}")
        if kind not in _KINDS:
            raise ValueError(f"Unsupported required annotation {ident}: {kind}")
        if not math.isfinite(float(item.get("beat", math.nan))):
            raise ValueError(f"Invalid annotation beat: {ident}")
        if item.get("staff") not in model.get("staff_order", ["right", "left"]):
            raise ValueError(f"Unknown annotation staff: {ident}")
        for event_id in item.get("event_ids", []):
            if event_id not in events:
                raise ValueError(f"Unknown annotation event {event_id}: {ident}")
        if kind == "grace":
            anchor = events.get(item.get("anchor_id"))
            if anchor is None or anchor.get("staff") != item.get("staff") or str(
                    anchor.get("voice", "1")) != str(item.get("voice", "1")):
                raise ValueError(f"Unknown or incompatible grace anchor: {ident}")
            layout_beat = float(item.get("layout_beat", item["beat"]))
            if (not math.isfinite(layout_beat) or
                    abs(layout_beat-float(anchor["beat"])) > 1e-7):
                raise ValueError(f"Invalid grace layout beat for source anchor: {ident}")
        if "end_beat" in item and (not math.isfinite(float(item["end_beat"])) or
                                  float(item["end_beat"]) <= float(item["beat"])):
            raise ValueError(f"Invalid annotation span: {ident}")
        if kind in {"hairpin", "wedge", "volta", "ending"} and "end_beat" not in item:
            raise ValueError(f"Missing annotation end beat: {ident}")
        result[ident] = item
    return result, events


def restore_annotation_ids(toolkit, model) -> int:
    """Restore IDs discarded by Verovio's MusicXML importer before rendering.

    Call after loadData(musicxml), before renderToSVG/timemap. The importer
    retains note IDs and MEI staff/timestamps. Those semantic anchors identify
    exactly one original MEI element; ambiguity raises instead of assigning a
    nearby graphic. Only xml:id changes; Verovio still owns all engraving.
    The toolkit is reloaded with its own MEI, retaining its rendering options.
    """
    desired, _ = _required(model)
    if not desired:
        return 0
    root = ET.fromstring(toolkit.getMEI())
    xml_id = "{http://www.w3.org/XML/1998/namespace}id"
    nodes = list(root.iter())
    parents = {child: parent for parent in nodes for child in parent}
    measures = [node for node in nodes if node.tag.rsplit("}", 1)[-1] == "measure"]
    model_measures = model.get("measures", [])
    if len(measures) != len(model_measures):
        raise ValueError("Verovio MEI measure identities differ from semantic score")
    used = set()
    for ident, item in desired.items():
        if item["kind"] == "grace":
            found = [node for node in nodes if node.get(xml_id) == ident]
            if len(found) != 1:
                raise ValueError(f"Verovio lost grace source identity: {ident}")
            continue
        source_ids = set(item.get("event_ids", []))
        staff_number = str(model.get("staff_order", ["right", "left"]).index(item["staff"])+1)
        beat = float(item["beat"])
        measure_index = next((i for i, measure in enumerate(model_measures)
                              if float(measure["start_beat"]) <= beat < float(measure["end_beat"])),
                             len(model_measures)-1)
        measure = model_measures[measure_index]
        denominator = float(measure.get("meter", [4, 4])[1])
        timestamp = 1+(beat-float(measure["start_beat"]))*denominator/4
        candidates = []
        for node in nodes:
            if node in used or node.tag.rsplit("}", 1)[-1] not in _KINDS[item["kind"]]:
                continue
            if node.get(xml_id) == ident:
                candidates = [node]
                break
            if item["kind"] in {"volta", "ending"}:
                contained = list(node.iter())
                wrapped = [measure for measure in measures if measure in contained]
                if not wrapped:
                    continue
                first, last = measures.index(wrapped[0]), measures.index(wrapped[-1])
                if (float(model_measures[first]["start_beat"]) != beat or
                        float(model_measures[last]["end_beat"]) != float(item["end_beat"])):
                    continue
                if not source_ids <= {child.get(xml_id) for child in contained}:
                    continue
            elif source_ids and item["kind"] in {"articulation", "articulations", "ornament", "ornaments"}:
                references = set(node.get("startid", "").replace("#", "").split())
                owner = parents.get(node)
                while owner is not None and owner.tag.rsplit("}", 1)[-1] != "note":
                    owner = parents.get(owner)
                if owner is not None:
                    references.add(owner.get(xml_id))
                if not references & source_ids:
                    continue
            else:
                owner = parents.get(node)
                while owner is not None and owner.tag.rsplit("}", 1)[-1] != "measure":
                    owner = parents.get(owner)
                if owner is not measures[measure_index] or staff_number not in node.get("staff", "").split():
                    continue
                source_stamp = float(node.get("tstamp", "nan"))
                if not math.isfinite(source_stamp) or abs(source_stamp-timestamp) > .0001:
                    continue
                if item["kind"] == "pedal" and node.get("dir") == "up":
                    continue
            candidates.append(node)
        if len(candidates) != 1:
            raise ValueError(f"Unresolved original MEI annotation identity: {ident}")
        candidates[0].set(xml_id, ident)
        used.add(candidates[0])
        if item["kind"] == "pedal" and item.get("end_id"):
            endpoint = float(item["end_beat"])
            end_index = next((i for i, bar in enumerate(model_measures)
                              if float(bar["start_beat"]) <= endpoint < float(bar["end_beat"])),
                             len(model_measures)-1)
            end_bar = model_measures[end_index]
            end_stamp = 1+(endpoint-float(end_bar["start_beat"]))*float(
                end_bar.get("meter", [4, 4])[1])/4
            releases = []
            for node in nodes:
                if node.tag.rsplit("}", 1)[-1] != "pedal" or node.get("dir") != "up":
                    continue
                owner = parents.get(node)
                while owner is not None and owner.tag.rsplit("}", 1)[-1] != "measure":
                    owner = parents.get(owner)
                if owner is measures[end_index] and staff_number in node.get("staff", "").split():
                    releases.append(node)
            if len(releases) > 1:
                # Prefer its exact timestamp when concurrent pedal scopes
                # share a measure. A sole same-staff release is unambiguous
                # even when Verovio has normalized its offset at a barline.
                releases = [node for node in releases if abs(float(
                    node.get("tstamp", "nan"))-end_stamp) <= .10001]
            if len(releases) != 1:
                raise ValueError(f"Unresolved original MEI pedal release: {item['end_id']}")
            releases[0].set(xml_id, item["end_id"])
    # Verovio's MEI reader expects the default namespace, rather than ElementTree's
    # generated ns0:music prefix. This normalization changes no score content.
    for node in nodes:
        node.tag = node.tag.rsplit("}", 1)[-1]
    root.set("xmlns", "http://www.music-encoding.org/ns/mei")
    old_input = toolkit.getOptions().get("inputFrom", "auto")
    toolkit.setOptions({"inputFrom": "mei"})
    try:
        if not toolkit.loadData(ET.tostring(root, encoding="unicode")):
            raise ValueError("Verovio could not restore original annotation identities")
    finally:
        toolkit.setOptions({"inputFrom": old_input})
    return len(desired)


def _target(root, parents, node, item, desired):
    """IDs may be on either the annotation group or its original child."""
    current = node
    while current is not None:
        if _classes(current) & _KINDS[item["kind"]] and not _classes(current) & _DIAGNOSTIC:
            break
        current = parents.get(current)
    if current is None:
        raise ValueError(f"Annotation ID has no matching Verovio group: {item['id']}")
    if item["kind"] == "grace":
        ancestor = parents.get(current)
        while ancestor is not None:
            if _classes(ancestor) & {"beam", "graceGrp"}:
                ids = [n.get("id") for n in ancestor.iter() if "note" in _classes(n)
                       and not _classes(n) & _DIAGNOSTIC]
                if not ids or any(i not in desired or desired[i]["kind"] != "grace"
                                  or desired[i].get("anchor_id") != item["anchor_id"] for i in ids):
                    raise ValueError(f"Incomplete or ambiguous grace group: {item['id']}")
                current = ancestor
            if "layer" in _classes(ancestor):
                break
            ancestor = parents.get(ancestor)
    return current


def _art(root, target, role):
    # Retain inherited transforms/styles/defs. Only split original leaf art;
    # never rewrite coordinates or construct substitute contours.
    svg = ET.fromstring(isolate(root, target))
    if role != "whole":
        def trim(node):
            for child in list(node):
                tag = child.tag.rsplit("}", 1)[-1]
                if tag in {"defs", "style"}:
                    continue
                if ((role == "fixed" and tag in _SHAPES) or
                        (role == "span" and tag in {"use", "text"})):
                    node.remove(child)
                else:
                    trim(child)
        trim(svg)
    return ET.tostring(svg, encoding="unicode")


def _crop(svg, space, origin, role):
    import cairosvg
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=2200)
    with Image.open(BytesIO(png)) as source:
        image = source.convert("RGBA")
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        return None
    scale = image.height * space
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("Invalid original Verovio staff scale")
    left, top, right, bottom = bbox
    white = Image.new("RGBA", (right-left, bottom-top), "white")
    white.putalpha(image.getchannel("A").crop(bbox))
    output = BytesIO()
    white.save(output, format="PNG")
    return {"role": role, "svg": svg,
            "bounds": [(left-origin[0]*image.width)*250/scale,
                       (top-origin[1]*image.height)*250/scale,
                       (right-left)*250/scale, (bottom-top)*250/scale],
            "png_base64": base64.b64encode(output.getvalue()).decode()}


def _anchors(item, events, geom, model):
    candidates = [event for event in events.values() if event.get("staff") == item["staff"]
                  and str(event.get("voice", "1")) == str(item.get("voice", "1"))
                  and event["id"] in geom.elements]
    # Projection records retain immutable source voice IDs, while MusicXML
    # voice streams may be renumbered in the lesson. Explicit event IDs are
    # authoritative; directions without them may use a unique staff beat.
    if not candidates:
        candidates = [event for event in events.values() if event.get("staff") == item["staff"]
                      and event["id"] in geom.elements]
    if item["kind"] == "grace":
        anchor = events[item["anchor_id"]]
    else:
        if not candidates:
            raise ValueError(f"No original staff anchors: {item['id']}")
        anchor = min(candidates, key=lambda e: abs(float(e["beat"])-float(item["beat"])))
    x, _, system = geom.elements[anchor["id"]]
    lines = geom.staff_systems[system]["staff_lines"]
    index = model.get("staff_order", ["right", "left"]).index(item["staff"])
    if len(lines) == 5:
        index = 0
    staff = lines[index*5:index*5+5]
    if len(staff) != 5 or staff[1] <= staff[0]:
        raise ValueError(f"Missing original staff geometry: {item['id']}")
    space = staff[1]-staff[0]
    points = [(float(e["beat"]), geom.elements[e["id"]][0]) for e in candidates
              if geom.elements[e["id"]][2] == system]
    for measure in model.get("measures", []):
        end = float(measure["end_beat"])
        # The system's actual terminal barline is a valid source anchor only
        # for the last measure represented by these source notes.
        last = max((b for b, _ in points), default=-math.inf)
        if float(measure["start_beat"]) <= last < end and system in geom.system_ends:
            points.append((end, geom.system_ends[system]))
            break
    def at(beat):
        exact = [px for b, px in points if abs(b-beat) < 1e-7]
        if exact:
            if max(exact)-min(exact) > 1e-6:
                raise ValueError(f"Ambiguous original beat anchor: {item['id']}")
            return exact[0]
        before = sorted((b, px) for b, px in points if b < beat)
        after = sorted((b, px) for b, px in points if b > beat)
        if not before or not after:
            raise ValueError(f"Unresolved original span endpoint: {item['id']}")
        b0, x0 = before[-1]; b1, x1 = after[0]
        return x0 + (x1-x0)*(beat-b0)/(b1-b0)
    beat = float(item["beat"])
    x = geom.elements[item["anchor_id"]][0] if item["kind"] == "grace" else at(beat)
    end_x = at(float(item["end_beat"])) if "end_beat" in item else x
    span = (end_x-x)*geom.width/geom.height*250/space
    if "end_beat" in item and span <= 0:
        raise ValueError(f"Nonlinear or cross-system annotation span: {item['id']}")
    return (x, staff[0]), space, span, system


def _valid(atlas, desired):
    if not isinstance(atlas, dict) or set(atlas) != set(desired):
        return False
    try:
        for ident, item in atlas.items():
            if (item["id"] != ident or item["source"] != "verovio-annotation"
                    or item["units_per_space"] != 250 or not item["parts"]):
                return False
            if any(item.get(field) != value for field, value in desired[ident].items()):
                return False
            for part in item["parts"]:
                box = part["bounds"]
                if len(box) != 4 or not all(math.isfinite(v) for v in box) or min(box[2:]) <= 0:
                    return False
                ET.fromstring(part["svg"])
                with Image.open(BytesIO(base64.b64decode(part["png_base64"], validate=True))) as image:
                    if not image.convert("RGBA").getchannel("A").getbbox():
                        return False
    except (KeyError, TypeError, ValueError, OSError, ET.ParseError):
        return False
    return True


def annotation_fragments(svgs, model, cache=None, identity="") -> dict:
    """Return every required ID, or raise ValueError (no partial native atlas).

    Cache keys include semantic and actual SVG identity, so changed beats or
    contours cannot reuse an earlier atlas under the same caller identity.
    """
    desired, events = _required(model)
    if not desired:
        return {}
    svgs = tuple(svgs)
    key = None
    if cache is not None and identity:
        fingerprint = hashlib.sha256(json.dumps(model, sort_keys=True).encode())
        for svg in svgs:
            fingerprint.update(svg.encode())
        key = cache.key("verovio-annotations", VERSION, identity, fingerprint.hexdigest())
        stored = cache.read_json("verovio-annotations", key)
        if _valid(stored, desired):
            return stored
    pages = []
    matches = {ident: [] for ident in desired}
    matches.update({item["end_id"]: [] for item in desired.values()
                    if item["kind"] == "pedal" and item.get("end_id")})
    for svg in svgs:
        root = ET.fromstring(svg)
        parents = {child: parent for parent in root.iter() for child in parent}
        geom = parse_svg_geometry(svg)
        pages.append((root, parents, geom))
        for node in root.iter():
            ident = node.get("id")
            if ident in matches and not _classes(node) & _DIAGNOSTIC:
                matches[ident].append((len(pages)-1, node))
    result = {}
    shared = {}
    for ident, item in desired.items():
        if len(matches[ident]) != 1:
            raise ValueError(f"Missing or ambiguous original Verovio annotation: {ident}")
        page, node = matches[ident][0]
        root, parents, geom = pages[page]
        target = _target(root, parents, node, item, desired)
        origin, space, span, system = _anchors(item, events, geom, model)
        token = (page, target, origin)
        if token not in shared:
            if item["kind"] in _SPANS and "end_beat" in item:
                parts = [part for role in ("fixed", "span") if (
                    part := _crop(_art(root, target, role), space, origin, role))]
            else:
                part = _crop(_art(root, target, "whole"), space, origin, "fixed")
                parts = [part] if part else []
            if not parts:
                raise ValueError(f"Empty original Verovio annotation: {ident}")
            if item["kind"] == "pedal" and item.get("end_id"):
                endings = matches[item["end_id"]]
                if len(endings) != 1 or endings[0][0] != page:
                    raise ValueError(f"Missing or ambiguous original pedal release: {item['end_id']}")
                ending = endings[0][1]
                end_item = {**item, "id": item["end_id"]}
                ending = _target(root, parents, ending, end_item, desired)
                release = _crop(_art(root, ending, "whole"), space, origin, "fixed")
                if release is not None:
                    release["anchor"] = 1.0
                    parts.append(release)
            shared[token] = parts
        group_ids = ([n.get("id") for n in target.iter() if "note" in _classes(n)
                      and not _classes(n) & _DIAGNOSTIC] if item["kind"] == "grace" else [ident])
        result[ident] = {**copy.deepcopy(item), "id": ident,
                         "source": "verovio-annotation", "units_per_space": 250,
                         "origin": [0.0, 0.0], "source_origin": list(origin),
                         "source_staff_space": space, "source_system": system,
                         "group_ids": group_ids, "span": span,
                         "span_anchors": {"beat": item.get("layout_beat", item["beat"]),
                             "end_beat": item.get("end_beat", item.get("layout_beat", item["beat"])),
                             "event_ids": list(item.get("event_ids", []))},
                         "parts": shared[token]}
    if not _valid(result, desired):
        raise ValueError("Incomplete original Verovio annotation atlas")
    if key:
        cache.write_json("verovio-annotations", key, result)
    return result
