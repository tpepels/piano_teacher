"""Verovio-engraved chord sprites, one per chord shape of a prepared score.

Every chord is engraved by Verovio itself, from the score's own Verovio
pages. Each chord gets an *instance* template at its real clef, staff
position and spelling, with the stem Verovio gave it on those pages; each
head is bound to its notation event by the template's note element order
(``leaders``: leader id -> member ids in template note order). Verovio's head
arrangement depends on all of those: seconds flip sides with the stem, whole
notes take a virtual stem from their position, and a far ledger head can
join the displaced column. There is no position-free or rule-derived chord.

All templates a stage needs are engraved in one Verovio document and each
chord is cut out of it by its note ids. Head positions are relative to the
lowest head (template note 0); the native view re-anchors them on the
chord's leader when it loads the atlas.

The atlas stores exact notehead positions for independent dots, ledger lines
and accidentals. Rhythmic timing never comes from SVG positions.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from copy import deepcopy
from io import BytesIO
import math
import re
import xml.etree.ElementTree as ET

from PIL import Image

VERSION = 10
_STEPS = {"C":0,"D":1,"E":2,"F":3,"G":4,"A":5,"B":6}
_LETTERS = "CDEFGAB"
_BEATS = {"whole":4.0,"half":2.0,"quarter":1.0,"eighth":.5,
          "16th":.25,"32nd":.125,"64th":.0625,"128th":.03125}
_PITCHED_CLEFS = {"G", "F", "C"}
# MusicXML octaves 0..9: diatonic indices 0..69 can be written in a template.
_LOWEST, _HIGHEST = 0, 69
# Raster scale of every sprite: 1600 px across Verovio's 900-wide page.
_PAGE_PIXELS = 1600
_OPTIONS = {"inputFrom":"xml","scale":48,"pageWidth":900,"pageHeight":2000,
            "svgViewBox":True,"adjustPageHeight":True,"svgBoundingBoxes":True,
            "svgContentBoundingBoxes":True}


def diatonic(spelling: dict) -> int:
    return int(spelling["octave"])*7+_STEPS[spelling["step"]]


def _alter(note: dict) -> int:
    return int(note["spelling"].get("alter") or 0)


def head_order(notes: list[dict]) -> list[dict]:
    """Template note order: bottom to top by staff position, then sounding
    pitch, then event id. The native view never re-derives it."""
    return sorted(notes, key=lambda n: (diatonic(n["spelling"]),
                                        int(n.get("midi_pitch") or 0), str(n.get("id", ""))))


def _head_count(key: str) -> int:
    return len(key.split("|")[3].split(","))


def _clef(leader: dict, measure: dict) -> tuple[str, int, int]:
    staff = leader.get("staff","right")
    clef = measure.get("clefs",{}).get(staff,{})
    sign = str(clef.get("sign","G" if staff=="right" else "F"))
    line = int(clef.get("line",2 if staff=="right" else 4))
    return sign, line, int(clef.get("octave_change",0))


def chord_lanes(model: dict):
    """(leader, members, measure) of every chord: the notes of one staff,
    voice, measure and beat with exactly one MusicXML leader (a note without
    <chord/>). The native view's Geometry.chord_members uses the same rule."""
    measures = {int(m["number"]):m for m in model.get("measures",[])}
    lanes = defaultdict(list)
    for e in model.get("notation_events",[]):
        if e.get("kind")=="note":
            lanes[(e.get("staff"),str(e.get("voice","1")),int(e.get("measure",0)),
                   round(float(e.get("beat",0)),6))].append(e)
    for (_,_,measure_id,_), notes in sorted(lanes.items(), key=lambda item: (
            item[0][2], item[0][3], str(item[0][0]), item[0][1])):
        leaders = [n for n in notes if not n.get("chord")]
        if len(leaders)==1 and len(notes)>=2 and measure_id in measures:
            yield leaders[0], notes, measures[measure_id]


def _shape_or_reason(leader: dict, notes: list[dict], measure: dict):
    """(shape, None) for a chord, else (None, why the input is not a chord).

    Any number of heads, any span, any number of heads on one staff
    position and identical heads are chords: Verovio engraves them all.
    """
    kind = str(leader.get("note_type",""))
    if kind not in _BEATS:
        return None, f"note value {kind!r} has no engraving"
    if any(n.get("note_type") != kind for n in notes):
        # MusicXML chord tones share one duration; heads of different values
        # at one onset belong to different voices. Import never merges them.
        return None, "heads of different note values are separate voices, not one chord"
    try:
        for n in notes:
            diatonic(n["spelling"]), _alter(n)
    except (KeyError,TypeError,ValueError):
        return None, "a head has no readable pitch spelling"
    sign, line, octave_change = _clef(leader, measure)
    if sign not in _PITCHED_CLEFS:
        return None, f"clef {sign} is not a pitched staff"
    return {"kind": kind, "clef": (sign, line, octave_change)}, None


def chord_refusal(leader: dict, notes: list[dict], measure: dict) -> str | None:
    """Why simultaneous heads are not one chord, naming measure and staff."""
    reason = _shape_or_reason(leader, notes, measure)[1]
    if reason is None:
        return None
    return (f"measure {int(leader.get('measure', measure.get('number', 0)))}, "
            f"{leader.get('staff', 'right')} staff: {reason}")


def refused_chords(model: dict) -> list[str]:
    """Readable refusal for every multi-head lane that is not one chord."""
    return [reason for leader, notes, measure in chord_lanes(model)
            if (reason := chord_refusal(leader, notes, measure))]


def _only_original_chord_heads(svg: str) -> str:
    """Keep Verovio's chord notehead ink and collisions, omitting stems.

    The original SVG coordinates and notehead displacement are unchanged.
    This can be overlaid on an independently positioned source beam.
    """
    root=ET.fromstring(svg)
    omitted={"stem","flag","beam","dots","dot","accid","artic",
             "tie","slur","tuplet","ledgerLines","ledgerLine","ledger",
             "bounding-box","content-bounding-box"}
    def visit(parent):
        for child in list(parent):
            if set(child.get("class","").split()) & omitted:
                parent.remove(child)
            else:
                visit(child)
    visit(root)
    return ET.tostring(root,encoding="unicode")


def _only_original_chord_stems(svg: str) -> str:
    """Extract original Verovio stem ink, not a synthetic rectangle."""
    root=ET.fromstring(svg)
    def prune(node):
        if "stem" in node.get("class","").split():
            for parent in node.iter():
                for child in list(parent):
                    if "flag" in child.get("class", "").split():
                        parent.remove(child)
            return True
        if node.tag.rsplit("}",1)[-1] in {"defs","style"}:
            return True
        retained=False
        for child in list(node):
            if prune(child):
                retained=True
            else:
                node.remove(child)
        return retained
    prune(root)
    return ET.tostring(root,encoding="unicode")


def _valid_asset(value: object, pattern: str) -> bool:
    """A partial disk atlas must be regenerated before Godot requests it."""
    def box(item):
        if not isinstance(item, dict):
            return False
        bounds = item.get("bounds")
        valid = (isinstance(bounds, list) and len(bounds) == 4 and
                all(isinstance(n, (int, float)) and math.isfinite(n) for n in bounds) and
                bounds[2] > 0 and bounds[3] > 0 and
                isinstance(item.get("png_base64"), str) and
                item["png_base64"].startswith("iVBORw0KGgo"))
        if not valid:
            return False
        try:
            data = base64.b64decode(item["png_base64"], validate=True)
            with Image.open(BytesIO(data)) as image:
                if image.format != "PNG":
                    return False
                image.verify()
        except (ValueError, OSError, SyntaxError):
            return False
        return True

    if not (box(value) and value.get("source") == "verovio-engraved-chord" and
            value.get("units_per_space") == 250):
        return False
    positions = value.get("head_positions")
    if not (isinstance(positions, list) and
            len(positions) == _head_count(pattern) and
            all(isinstance(p, list) and len(p) == 2 and
                all(isinstance(n, (int, float)) and math.isfinite(n) for n in p)
                for p in positions)):
        return False
    heads = value.get("heads_only")
    if not box(heads) or heads.get("source") != "verovio-engraved-chord-heads":
        return False
    if value.get("stem") not in {"up", "down"}:
        return False
    stem = value.get("stem_only")
    return (pattern.startswith("whole|") or
            (box(stem) and stem.get("source") == "verovio-engraved-chord-stem"))


_NUMBER = r"-?\d+(?:\.\d+)?"


def _classes(node) -> set[str]:
    return set(node.get("class", "").split())


def verovio_chord_stems(pages) -> dict[str, bool]:
    """Note id -> stem up, for every stemmed chord of Verovio's own pages.

    Verovio's stem rule (the head farthest from the middle line, voices,
    beams) differs from a mean-position rule, and the side of every second
    follows the stem: the score's real direction is read, not re-derived.
    """
    result: dict[str, bool] = {}
    for page in pages or ():
        root = ET.fromstring(page)
        for chord in root.iter():
            classes = _classes(chord)
            if "chord" not in classes or classes & {"bounding-box", "content-bounding-box"}:
                continue
            stem_ys, head_ys, ids = [], [], []
            for node in chord.iter():
                kinds = _classes(node)
                if kinds & {"bounding-box", "content-bounding-box"}:
                    continue
                if "note" in kinds and node.get("id"):
                    ids.append(node.get("id"))
                if "stem" in kinds and not stem_ys:
                    for path in node.iter():
                        match = re.fullmatch(r"\s*M\s*(%s)[,\s]+(%s)\s*L\s*(%s)[,\s]+(%s)\s*"
                                             % ((_NUMBER,) * 4), path.get("d", "") or "")
                        if match:
                            stem_ys = [float(match.group(2)), float(match.group(4))]
                            break
                if "notehead" in kinds:
                    for use in node.iter():
                        if use.tag.rsplit("}", 1)[-1] != "use":
                            continue
                        move = re.search(r"translate\(\s*(%s)[,\s]+(%s)" % (_NUMBER, _NUMBER),
                                         use.get("transform", ""))
                        head_ys.append(float(move.group(2)) if move else float(use.get("y", "0")))
                        break
            if not stem_ys or not head_ys:
                continue
            up = min(head_ys)-min(stem_ys) > max(stem_ys)-max(head_ys)
            for ident in ids:
                result[ident] = up
    return result


def chord_instances(model: dict, pages, *,
                    stem_directions: dict[str, bool] | None = None) -> dict[str, dict]:
    """Leader id -> the instance template that engraves exactly that chord.

    Direction: a source beam's, else Verovio's own stem on the page. Whole
    notes have no visible stem: their template writes none, so Verovio's
    virtual stem comes from the same staff position it had in the score.
    """
    stems = verovio_chord_stems(pages)
    beams = stem_directions or {}
    result: dict[str, dict] = {}
    for leader, notes, measure in chord_lanes(model):
        shape, _ = _shape_or_reason(leader, notes, measure)
        if shape is None:
            continue
        ordered = head_order(notes)
        leader_id = str(leader.get("id", ""))
        page = next((stems[str(n.get("id"))] for n in notes if str(n.get("id")) in stems), None)
        if shape["kind"] == "whole":
            direction = "auto"
        elif leader_id in beams:
            direction = "up" if beams[leader_id] else "down"
        elif page is not None:
            direction = "up" if page else "down"
        else:
            raise ValueError(
                f"Verovio engraved no stem for the chord at measure "
                f"{leader.get('measure')}, {leader.get('staff')} staff: {leader_id}")
        heads = [(diatonic(n["spelling"]), _alter(n)) for n in ordered]
        shift = 0
        while min(i for i, _ in heads)+shift < _LOWEST:
            shift += 7
        while max(i for i, _ in heads)+shift > _HIGHEST:
            shift -= 7
        heads = [(index+shift, alter) for index, alter in heads]
        sign, line, octave_change = shape["clef"]
        spelled = ",".join(f"{index}{'s'*alter if alter > 0 else 'f'*-alter}"
                           for index, alter in heads)
        key = f"{shape['kind']}|{direction}|{sign}{line}{octave_change:+d}|{spelled}"
        result[leader_id] = {"key": key,
                             "spec": (shape["kind"], direction, tuple(heads), shape["clef"]),
                             "heads": [str(n.get("id", "")) for n in ordered]}
    return result


def _document_xml(chords: list[tuple]) -> str:
    """One Verovio document: each chord alone in its own measure.

    ``chords`` holds (id prefix, note value, direction, heads, clef). Notes
    are ids <prefix>c0, c1, ... in head order. An alter is written without
    an <accidental>, so Verovio knows the pitch but prints no accidental:
    native accidentals are placed separately. Direction "auto" writes no
    stem, so Verovio chooses it from the staff position as in the score.
    """
    measures = []
    for number, (prefix, kind, direction, heads, clef) in enumerate(chords, 1):
        sign, line, octave_change = clef
        shift = (f"<clef-octave-change>{octave_change}</clef-octave-change>"
                 if octave_change else "")
        opening = ("<divisions>10080</divisions><time><beats>4</beats>"
                   "<beat-type>4</beat-type></time>") if number == 1 else ""
        notes = []
        duration = round(_BEATS[kind]*10080)
        for i, (index, alter) in enumerate(heads):
            octave, step = divmod(index, 7)
            stem = (f"<stem>{direction}</stem>"
                    if i == 0 and direction in {"up","down"} else "")
            written = f"<alter>{alter}</alter>" if alter else ""
            notes.append(f'<note id="{prefix}c{i}">{"<chord/>" if i else ""}'
                         f'<pitch><step>{_LETTERS[step]}</step>{written}'
                         f'<octave>{octave}</octave></pitch><duration>{duration}</duration>'
                         f'<type>{kind}</type>{stem}</note>')
        measures.append(f'<measure number="{number}"><attributes>{opening}'
                        f'<clef><sign>{sign}</sign><line>{line}</line>{shift}</clef>'
                        f'</attributes>{"".join(notes)}</measure>')
    return ('<score-partwise version="4.0"><work><work-title> </work-title></work>'
            '<movement-title> </movement-title><part-list><score-part id="P1">'
            '<part-name>Piano</part-name></score-part></part-list>'
            f'<part id="P1">{"".join(measures)}</part></score-partwise>')


def _tag(node) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _isolate(root, parents: dict, target, crop: tuple[float, float, float, float],
             page: tuple[float, float, float, float]) -> str:
    """The page reduced to one chord: its ancestor chain (transforms and
    nested viewports kept), glyph definitions, and the chord itself, with
    the outer viewBox cropped around it."""
    chain = []
    node = target
    while node is not None:
        chain.append(node)
        node = parents.get(node)
    chain.reverse()
    copies = {}
    for depth, original in enumerate(chain[:-1]):
        clone = ET.Element(original.tag, dict(original.attrib))
        if depth and _tag(original) == "svg":
            # A nested viewport is 100% of its parent's: pin it to the page
            # size so cropping the outer viewBox does not rescale it.
            clone.set("width", f"{page[2]:.3f}")
            clone.set("height", f"{page[3]:.3f}")
        for child in original:
            if _tag(child) in {"defs", "style"}:
                clone.append(deepcopy(child))
        if depth:
            copies[chain[depth-1]].append(clone)
        copies[original] = clone
    chord = deepcopy(target)
    for parent in chord.iter():
        for child in list(parent):
            if _classes(child) & {"bounding-box", "content-bounding-box"}:
                parent.remove(child)
    copies[chain[-2]].append(chord)
    top = copies[chain[0]]
    top.set("viewBox", " ".join(f"{v:.3f}" for v in crop))
    return ET.tostring(top, encoding="unicode")


def _sprite(svg: str, width: int):
    import cairosvg
    with Image.open(BytesIO(cairosvg.svg2png(bytestring=svg.encode(),
                                             output_width=width))) as image:
        return image.convert("RGBA")


def _white(rgba, bbox) -> str:
    cut = rgba.crop(bbox)
    ink = Image.new("RGBA", cut.size, (255, 255, 255, 255))
    ink.putalpha(cut.getchannel("A"))
    stream = BytesIO()
    ink.save(stream, format="PNG", optimize=True)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def _cut(root, parents, chord, geometry, names, kind, box) -> dict:
    """One instance asset, in 250 units per staff space, origin at the
    centre of the lowest head (template note 0)."""
    from .glyphs import native_glyphs
    bx, by, width, height = box
    scale = _PAGE_PIXELS/width
    anchor = geometry.elements[names[0]]
    rails = geometry.staff_systems[anchor[2]]["staff_lines"]
    space = (rails[1]-rails[0])*height
    if space*scale <= 2:
        raise ValueError("Invalid chord staff spacing")
    heads = [(geometry.elements[n][0]*width, geometry.elements[n][1]*height) for n in names]
    left = min(x for x, _ in heads)-6*space
    right = max(x for x, _ in heads)+6*space
    top = min(min(y for _, y in heads), rails[0]*height)-8*space
    bottom = max(max(y for _, y in heads), rails[-1]*height)+8*space
    # Snap the crop to whole pixels measured from the chord's own lowest
    # head, so a key's raster is the same whatever shares its document. The
    # head's glyph origin sits a quarter pixel into its pixel: on a pixel
    # edge (or at its centre) status ink's recolored contour measured just
    # over its limit (test_note_status_framebuffer); .25, .4 and .75 pass.
    origin_x, origin_y = heads[0]
    left = origin_x-(math.ceil((origin_x-left)*scale)+.25)/scale
    top = origin_y-(math.ceil((origin_y-top)*scale)+.25)/scale
    pixels = max(1, math.ceil((right-left)*scale))
    right = left+pixels/scale
    bottom = top+math.ceil((bottom-top)*scale)/scale
    full = _isolate(root, parents, chord, (bx+left, by+top, right-left, bottom-top), box)
    rgba = _sprite(full, pixels)
    heads_rgba = _sprite(_only_original_chord_heads(full), pixels)
    stems_rgba = _sprite(_only_original_chord_stems(full), pixels)
    staff = space*scale
    head = native_glyphs()["head_" + (kind if kind in {"whole", "half"} else "black")]["bounds"]
    dx = (head[0]+head[2]*.5)*staff/250
    note_x = (heads[0][0]-left)*scale+dx
    note_y = (heads[0][1]-top)*scale
    unit = 250/staff

    def bounds(bbox):
        l, t, r, b = bbox
        return [(l-note_x)*unit, (t-note_y)*unit, (r-l)*unit, (b-t)*unit]

    bbox = rgba.getchannel("A").getbbox()
    if not bbox:
        raise ValueError("Empty genuine chord sprite")
    positions = [[(x-heads[0][0])*scale*unit, (y-heads[0][1])*scale*unit] for x, y in heads]
    result = {"source": "verovio-engraved-chord", "bounds": bounds(bbox),
              "units_per_space": 250, "head_positions": positions,
              "png_base64": _white(rgba, bbox)}
    if not all(math.isfinite(v) for v in result["bounds"]+[c for p in positions for c in p]):
        raise ValueError("Nonfinite Verovio chord geometry")
    head_bbox = heads_rgba.getchannel("A").getbbox()
    if head_bbox:
        result["heads_only"] = {"source": "verovio-engraved-chord-heads",
                                "bounds": bounds(head_bbox),
                                "png_base64": _white(heads_rgba, head_bbox)}
    stem_bbox = stems_rgba.getchannel("A").getbbox()
    if stem_bbox:
        result["stem_only"] = {"source": "verovio-engraved-chord-stem",
                               "bounds": bounds(stem_bbox),
                               "png_base64": _white(stems_rgba, stem_bbox)}
    return result


def _engrave_document(toolkit, specs: dict[str, tuple]) -> tuple[dict, dict]:
    """(key -> asset, key -> why it failed) for chords engraved together in
    one Verovio document, each cut out of its page by its own note ids."""
    from ...source_svg import parse_svg_geometry
    keys = sorted(specs)
    prefixes = {f"k{j}": key for j, key in enumerate(keys)}
    if not toolkit.loadData(_document_xml(
            [(prefix, *specs[key]) for prefix, key in prefixes.items()])):
        raise ValueError("Verovio refused the chord document")
    result, failed = {}, {}
    for page in range(1, toolkit.getPageCount()+1):
        svg = toolkit.renderToSVG(page)
        geometry = parse_svg_geometry(svg)
        root = ET.fromstring(svg)
        box = tuple(float(v) for v in re.findall(_NUMBER, root.get("viewBox", "")))
        parents = {child: parent for parent in root.iter() for child in parent}
        for chord in root.iter():
            if "chord" not in _classes(chord) or \
                    _classes(chord) & {"bounding-box", "content-bounding-box"}:
                continue
            ident = next((n.get("id") for n in chord.iter()
                          if "note" in _classes(n) and n.get("id")), "")
            key = prefixes.get(ident.split("c", 1)[0])
            if key is None:
                continue
            names = [f"{ident.split('c', 1)[0]}c{i}" for i in range(len(specs[key][2]))]
            try:
                if not set(names) <= set(geometry.elements):
                    raise ValueError("Verovio chord notehead IDs missing")
                result[key] = _cut(root, parents, chord, geometry, names, specs[key][0], box)
            except (ValueError, KeyError, IndexError, ZeroDivisionError) as exc:
                failed[key] = f"{type(exc).__name__}: {exc}"
    for key in keys:
        if key not in result and key not in failed:
            failed[key] = "Verovio engraved no chord for it"
    return result, failed


def _render_batch(toolkit, specs: dict[str, tuple]) -> dict:
    """key -> asset for every chord that engraves; each failure is reported
    by its own key and never blanks the rest of the stage's atlas.

    A whole chord's stem is invisible, yet Verovio sets its heads by a
    virtual stem: the one it gives the same chord as a stemless quarter
    (checked against Verovio on 200 chords: 84 decisive, all agree). That
    twin is engraved alongside and its stem becomes the template's.
    """
    twins = {f"{key}|twin": ("quarter", "auto", spec[2], spec[3])
             for key, spec in specs.items() if spec[0] == "whole"}
    wanted = {**specs, **twins}
    try:
        engraved, failed = _engrave_document(toolkit, wanted)
    except (ValueError, RuntimeError) as exc:
        # One unreadable chord must not take the stage's other chords with
        # it: engrave each alone and name the one that fails.
        print("VEROVIO_CHORD_DOCUMENT_UNAVAILABLE:", type(exc).__name__, str(exc))
        engraved, failed = {}, {}
        for key, spec in wanted.items():
            try:
                alone, why = _engrave_document(toolkit, {key: spec})
                engraved.update(alone)
                failed.update(why)
            except (ValueError, RuntimeError) as single:
                failed[key] = f"{type(single).__name__}: {single}"
    result = {}
    for key, spec in specs.items():
        asset = engraved.get(key)
        if asset is None:
            print("VEROVIO_CHORD_PATTERN_UNAVAILABLE:", key, failed.get(key, ""))
            continue
        if spec[0] == "whole":
            twin = engraved.get(f"{key}|twin", {}).get("stem_only")
            if twin is None:
                print("VEROVIO_CHORD_PATTERN_UNAVAILABLE:", key,
                      "no virtual stem:", failed.get(f"{key}|twin", ""))
                continue
            # A rising stem ends at the lowest head (template note 0).
            asset["stem"] = "up" if twin["bounds"][1]+twin["bounds"][3] < 125 else "down"
        else:
            asset["stem"] = spec[1]
        result[key] = asset
    return result


def chord_templates(model: dict, cache=None, *, pages,
                    stem_directions: dict[str, bool] | None = None) -> dict:
    """Verovio chord atlas for a model engraved on ``pages``.

    Every chord gets an instance template; each asset lists its chords under
    ``leaders`` (leader id -> member ids in template note order), which the
    native view uses to find a chord's template and to bind each head.
    """
    for refusal in refused_chords(model):
        print("VEROVIO_CHORD_REFUSED:",refusal)
    instances = chord_instances(model, pages, stem_directions=stem_directions)
    specs = {item["key"]: item["spec"] for item in instances.values()}
    if not specs:
        return {}
    import verovio
    from .glyphs import native_glyphs
    font = native_glyphs()["head_black"]["font"]
    version = getattr(verovio, "__version__", "unknown")
    assets, missing, keys = {}, {}, {}
    for key, spec in specs.items():
        keys[key] = cache.key("verovio-chords", VERSION, font, version, key) if cache else None
        value = cache.read_json("verovio-chord", keys[key]) if keys[key] else None
        if _valid_asset(value, key):
            assets[key] = value
        else:
            missing[key] = spec
    if missing:
        from .runtime import _create_verovio_toolkit
        toolkit = _create_verovio_toolkit(verovio)
        if not toolkit.setOptions(_OPTIONS):
            raise RuntimeError("Verovio rejected chord engraving options")
        rendered = _render_batch(toolkit, missing)
        for key in missing:
            value = rendered.get(key)
            if value is None:
                continue  # _render_batch named it and why
            if not _valid_asset(value, key):
                print("VEROVIO_CHORD_PATTERN_UNAVAILABLE:", key, "incomplete asset")
                continue
            assets[key] = value
            if keys[key]:
                cache.write_json("verovio-chord", keys[key], value)
    result = {key: deepcopy(value) for key, value in assets.items()}
    for leader_id, item in sorted(instances.items()):
        if item["key"] in result:
            result[item["key"]].setdefault("leaders", {})[leader_id] = item["heads"]
    return result
