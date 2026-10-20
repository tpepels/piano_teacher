"""Legacy page timemap and raster strip geometry; not used for musical truth."""
from __future__ import annotations
from collections import defaultdict
import math

from ...notation.assets.svg_geometry import parse_svg_geometry


def layout_from_pages(svgs: list[str], timemap: list[dict], total_beats: float,
                      pitches: dict[str, int] | None = None, *, note_bindings: dict | None = None) -> dict:
    """Return exact note/rest-onset anchors for synchronized, multi-system playback.

    A system is selected by the *next onset* at a wrap. Between onsets in one
    system the playhead interpolates; across a system wrap it jumps instead of
    sweeping backwards over the wrong staff. It holds at the final onset rather
    than inventing coordinates for an unmeasured right barline.
    """
    if total_beats <= 0 or not math.isfinite(total_beats):
        raise ValueError("Invalid exercise duration")
    pages = [parse_svg_geometry(svg) for svg in svgs]
    where: dict[str, tuple[int, float, float, str]] = {}
    for i, page in enumerate(pages):
        for identifier, (x, y, system) in page.elements.items():
            where[identifier] = (i, x, y, system)
    groups = defaultdict(list)
    positioned_notes = []
    seen_note_ids = set()
    pitches = pitches or {}
    attack_map, continuation_map = {}, defaultdict(list)
    for event in timemap:
        if "qstamp" not in event:
            continue
        beat = float(event["qstamp"])
        if not (math.isfinite(beat) and -1e-5 <= beat <= total_beats + 1e-5):
            continue
        note_ids = event.get("on", [])
        rest_ids = event.get("restsOn", []) + event.get("rests", [])
        for identifier in note_ids + rest_ids:
            if identifier in where:
                page, x, y, system = where[identifier]
                binding = note_bindings.get(identifier) if note_bindings is not None else None
                if note_bindings is not None and identifier in note_ids:
                    if binding is None or pitches.get(identifier) != binding['pitch']:
                        raise ValueError(f'Engraved note identity/pitch mapping failed: {identifier}')
                    if abs(beat-binding['display_beat']) > 1/10080+1e-7:
                        raise ValueError(f'Engraved source identity has an incorrect display onset: {identifier}')
                clock_beat = binding['source_beat'] if binding and binding['is_attack'] else round(max(0,beat),7)
                groups[(page, system, clock_beat)].append(
                    (x, y, identifier in note_ids, pages[page].ink_left[identifier]))
                if identifier in pitches and identifier not in seen_note_ids:
                    glyph = {"id": identifier, "beat": round(max(0, beat), 7),
                             "pitch": pitches[identifier], "page": page,
                             "x": x, "y": y, "system": system}
                    if binding is not None:
                        glyph.update({key: binding[key] for key in ('source_id','is_attack','segment_index','source_beat','hand')})
                        if binding['is_attack']:
                            if binding['source_id'] in attack_map:
                                raise ValueError('Duplicate mapped attack for a required source identity')
                            attack_map[binding['source_id']] = identifier
                        else:
                            continuation_map[binding['source_id']].append(identifier)
                    positioned_notes.append(glyph)
                    seen_note_ids.add(identifier)
    if note_bindings is not None and set(note_bindings) != seen_note_ids:
        missing = sorted(set(note_bindings)-seen_note_ids)
        raise ValueError(f'Engraving omitted bound source-note identities: {missing[:4]}')
    if not groups:
        raise ValueError("Verovio supplied no engraved/timed note matches; cannot align playhead")
    # Each staff system is bounded by its own note positions. Even on a page
    # with two systems, the playhead never extends through the wrong one.
    system_y = defaultdict(list)
    for (page, system, _), points in groups.items():
        system_y[(page, system)].extend(y for _, y, _, _ in points)
    anchors = []
    for (page, system, beat), points in groups.items():
        ys = system_y[(page, system)]
        # bounds are the noteheads +/- a conservative staff height in SVG units
        bottom = max(ys)
        top = min(ys)
        margin = max(0.025, min(0.095, (bottom - top) * 0.45))
        staff = pages[page].staff_systems.get(system, {})
        # A full-measure rest can be centered in the inactive hand. It must
        # never pull a simultaneous required note away from the timing line.
        note_points = [(x, y) for x, y, is_note, _ in points if is_note]
        timed_points = note_points or [(x, y) for x, y, _, _ in points]
        anchors.append({"beat": beat, "page": page,
                        "system": system, "x": sum(x for x, _ in timed_points) / len(timed_points),
                        "ink_left": min(left for _, _, _, left in points),
                        "top": staff.get("top", max(0.0, top - margin)),
                        "bottom": staff.get("bottom", min(1.0, bottom + margin))})
    anchors.sort(key=lambda a: (a["beat"], a["page"], a["system"]))
    if any(anchors[i]["beat"] < anchors[i-1]["beat"] for i in range(1,len(anchors))):
        raise AssertionError("Unsorted engraving anchors")
    # Continue through a sustained final note only where the actual final
    # barline can be located. Otherwise hold at the final timed glyph.
    last = anchors[-1]
    page = pages[last["page"]]
    boundary = page.system_ends.get(last["system"])
    if (boundary is not None and last["beat"] < total_beats - 1e-7
            and boundary > last["x"] + 1e-5):
        anchors.append({**last, "beat": total_beats, "x": boundary, "terminal": True})
    systems = []
    for page_index, page in enumerate(pages):
        for identifier, bounds in page.staff_systems.items():
            beats = [a["beat"] for a in anchors
                     if a["page"] == page_index and a["system"] == identifier]
            if not beats:
                continue
            next_beats = [a["beat"] for a in anchors if a["beat"] > max(beats)
                          and (a["page"], a["system"]) != (page_index, identifier)]
            systems.append({**bounds, "page": page_index, "system": identifier,
                            "start_beat": min(beats),
                            "end_beat": min(next_beats) if next_beats else total_beats,
                            # The actual final barline, distinct from the staff
                            # path's right edge (which may extend into blank
                            # trailing page width). Needed for safe join audits.
                            "last_barline_x": page.system_ends.get(identifier, -1.0)})
    result = {"pages": len(svgs), "beats": total_beats, "anchors": anchors, "systems": systems,
            "notes": sorted(positioned_notes, key=lambda n: (n["beat"], n["pitch"], n["id"])),
            "widths": [p.width for p in pages], "heights": [p.height for p in pages]}
    if note_bindings is not None:
        result.update(mapping_schema='source-note-v1', attack_map=attack_map,
                      continuation_map=dict(continuation_map))
    return result


def locate_beat(layout: dict, beat: float) -> dict:
    """Find normalized x/y and page at musical beat. Safe across line wraps."""
    anchors = layout["anchors"]
    if not anchors:
        raise ValueError("No positioned events")
    index = 0
    for i, anchor in enumerate(anchors):
        if anchor["beat"] <= beat + 1e-9:
            index = i
        else:
            break
    left = anchors[index]
    pos = dict(left)
    if index + 1 < len(anchors):
        right = anchors[index + 1]
        if (left["page"], left["system"]) == (right["page"], right["system"]) and right["beat"] > left["beat"]:
            alpha = min(1.0, max(0.0,(beat-left["beat"])/(right["beat"]-left["beat"])))
            pos["x"] = left["x"] + alpha*(right["x"]-left["x"])
    return pos
