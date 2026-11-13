"""Independent photographic ownership of full-meter practice silence.

The generated MusicXML ends before the two legitimate practice-gap rests.
They must remain in the framebuffer, but an unexpected-symbol proof must not
call them *invented source rests*. Infer their expected meter/clock from
independently parsed written MusicXML, their longitudinal translation from
successive actual photographs, and their Y from five photographed staff rules.

Only two complete, stable, source-independent whole-rest contours, one per
staff, can receive this ownership. No framebuffer or native telemetry supplies
a position. Other rests, missing glyphs, source notes and unresolved ink retain
their original strict classifications.
"""
from __future__ import annotations

from collections import Counter
from math import isfinite
from statistics import median


def _source_gap_duration(written) -> float | None:
    if len(written.bars) < 2 or written.bars[0] != 0.0:
        return None
    at_start = {tuple(meter) for index, meter in written.meter if index == 0}
    if len(at_start) != 1:
        return None
    numerator, denominator = next(iter(at_start))
    if (type(numerator) is not int or type(denominator) is not int
            or numerator < 1 or denominator < 1):
        return None
    full = 4.0*numerator/denominator
    if (not isfinite(full) or not 0 < full <= 24.0
            or abs(written.bars[1]-full) > 1e-6):
        # A pickup/irregular opening has different canonical preparation
        # semantics; its ink is not certified by this narrow full-bar probe.
        return None
    return full


def _photographic_density(snapshots) -> float | None:
    """A source-screen translation from retained PNG registrations only."""
    valid = [s for s in snapshots if "error" not in s and s.get("travel") is not None]
    if len(valid) < 3 or any("error" in s for s in snapshots):
        return None
    first, last = valid[0], valid[-1]
    elapsed = float(last["clock"])-float(first["clock"])
    if elapsed <= 0:
        return None
    density = (float(first["travel"])-float(last["travel"]))/elapsed
    if not 1 <= density <= 5000 or not isfinite(density):
        return None
    # Every photographed equal-time transition must agree with the measured
    # global density within its own registration error interval.
    for before, after in zip(valid, valid[1:]):
        delta = float(after["clock"])-float(before["clock"])
        if delta <= 0 or after.get("motion") is None:
            return None
        prediction = -delta*density
        tolerance = max(2.0, float(after["motion"].get("position_error", 0.0))*2.0)
        if after.get("shift") is None or abs(float(after["shift"])-prediction) > tolerance:
            return None
    return density


def _pair_at(snapshot, *, source_end: float, gap_beats: float,
             density: float):
    """Two independently photographed glyphs on the same moving rest onset."""
    staves = snapshot.get("staves")
    camera = snapshot.get("camera")
    if not staves or camera is None or not isfinite(camera):
        return ()
    if set(staves) != {"left", "right"}:
        return ()
    expected_x = camera + (source_end+gap_beats*.5-float(snapshot["clock"]))*density
    matches = []
    for hand in ("right", "left"):
        staff = staves[hand]
        if len(staff.lines) != 5 or not 0 < staff.gap <= 32:
            return ()
        expected_y = staff.lines[2]-.75*staff.gap
        choices = []
        for obj in snapshot["objects"]:
            if (obj.get("family") != "rest"
                    or obj.get("name") != "rest_whole"
                    or float(obj.get("score",0.0)) < .90):
                continue
            x0,y0,x1,y1 = obj["bbox"]
            center_x,center_y = (x0+x1)*.5,(y0+y1)*.5
            # A shape near the midpoint must still lie strictly AFTER
            # occupied source music and within this one full-meter gap.
            source_x = camera+(source_end-float(snapshot["clock"]))*density
            if (source_x < x0 and x1 < source_x+gap_beats*density
                    and abs(center_y-expected_y) <= .3*staff.gap
                    and abs(center_x-expected_x) <= 2.0*staff.gap):
                choices.append(obj)
        if len(choices) != 1:
            return ()
        matches.append(choices[0])
    if abs(sum(matches[0]["bbox"][::2])/2 -
           sum(matches[1]["bbox"][::2])/2) > 3.0:
        return ()
    if matches[0]["track"] == matches[1]["track"]:
        return ()
    return tuple(matches)


def confirmed_gap_tracks(written, snapshots) -> dict:
    """Require repeated stable genuine two-staff rests, never a single ghost."""
    duration = _source_gap_duration(written)
    density = _photographic_density(snapshots)
    if duration is None or density is None:
        return {}
    source_end = float(written.bars[-1])
    observations = []
    for index, snapshot in enumerate(snapshots):
        if "error" in snapshot:
            continue
        matched = _pair_at(snapshot,source_end=source_end,
                           gap_beats=duration,density=density)
        if matched:
            # Register contours on the independently measured source axis.
            centers = tuple((obj["bbox"][0]+obj["bbox"][2])*.5
                            -snapshot["camera"]+snapshot["clock"]*density
                            for obj in matched)
            observations.append((index, tuple(obj["track"] for obj in matched), centers))
    counts = Counter(pair for _, pair, _ in observations)
    stable = {pair for pair, count in counts.items() if count >= 3}
    if not stable:
        return {}
    anchors = [row for row in observations if row[1] in stable]
    axis = tuple(median(row[2][hand] for row in anchors) for hand in (0,1))
    # Track IDs are local contour registrations, not musical identities.
    # Strong fragments must all describe the SAME physical rest pair.
    if any(abs(row[2][hand]-axis[hand]) > 3.0
           for row in anchors for hand in (0,1)):
        return {}
    accepted = set(stable)
    first, last = anchors[0][0], anchors[-1][0]
    for pair in counts.keys()-stable:
        rows = [row for row in observations if row[1] == pair]
        # A brief loss of contour registration can split both tracks.
        # Bridge only an interior fragment of the already proven pair;
        # a changing single track or new trajectory has no ownership.
        if (all(first < row[0] < last for row in rows)
                and all(set(pair).isdisjoint(anchor) for anchor in stable)
                and all(abs(row[2][hand]-axis[hand]) <= 3.0
                        for row in rows for hand in (0,1))):
            accepted.add(pair)
    return dict(tracks=frozenset(track for pair in accepted for track in pair),
                pairs=frozenset(accepted), source_end=source_end,
                gap_beats=duration, density=density, axis=axis)


def verified_procedural_pair(snapshot, confirmed):
    """Repeat all source/photo geometry checks at each frame before credit."""
    if not confirmed or "error" in snapshot:
        return ()
    pair = _pair_at(snapshot,source_end=confirmed["source_end"],
                    gap_beats=confirmed["gap_beats"],
                    density=confirmed["density"])
    if not pair or tuple(obj["track"] for obj in pair) not in confirmed["pairs"]:
        return ()
    for hand, obj in enumerate(pair):
        center = (obj["bbox"][0]+obj["bbox"][2])*.5-snapshot["camera"]+(
            snapshot["clock"]*confirmed["density"])
        if abs(center-confirmed["axis"][hand]) > 3.0:
            return ()
    return pair
