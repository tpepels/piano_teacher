"""Image-space pitch proof for the REAL native Godot renderer.

No renderer-provided notehead coordinates, staff centers, Y positions or staff
scale are used. This deliberately limited probe checks one quarter-note per
hand at a fixed playhead and derives the ten staff lines from PNG pixels.
Expected written pitches/clefs come from the original MusicXML via the
independent Phase 1 oracle. It does NOT certify chords, rests, beams, ties,
accidental shapes, or arbitrary dense layouts; later coverage must.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from piano_teacher.notation.proof import read_written_score

DIATONIC = {letter: i for i, letter in enumerate("CDEFGAB")}
PLAYHEAD_FRACTION = 0.42  # Public fixed-playhead interaction requirement.


@dataclass(frozen=True)
class RasterStaff:
    hand: str
    lines: tuple[float, ...]  # upper to lower
    gap: float

    @property
    def bottom(self) -> float:
        return self.lines[-1]


def _staff_row_values(brightness: np.ndarray) -> list[float]:
    """Require long horizontal ink across the viewport, including its middle.

    Long ties can occupy both edges at the same Y while leaving the middle
    clear. Sampling only those edges promotes the curves into rail peaks and
    hides nearby gray rules behind their bright shoulders. Require the lower
    quartile in *each* viewport quarter: a central shallow curve must not
    substitute for a missing rail either. Taking the minimum retains only
    horizontal ink supported across all four regions. No lattice can supply
    an absent row.
    """
    regions = np.array_split(brightness, min(4, brightness.shape[1]), axis=1)
    values = []
    for region in regions:
        quartile = region.shape[1] // 4
        values.append(np.partition(region, quartile, axis=1)[:, quartile])
    return np.minimum.reduce(values).astype(float).tolist()


def _staff_stroke_ink(brightness: np.ndarray, center: float) -> int:
    """Measure a rule's vertical ink from pixels before reducing across X.

    Integrating first preserves a curved stroke's bright core even when its
    antialiased edge alone makes the row-profile peak. A seven-row strip fits
    inside the minimum 8px rail gap. Each column supplies its own background;
    the least contaminated region supplies the gray rule's stroke weight.
    """
    y = round(center)
    strip = brightness[y - 3:y + 4].astype(np.int16)
    contrast = strip - strip.min(axis=0)
    ink = contrast.sum(axis=0)
    regions = np.array_split(ink, min(4, len(ink)))
    weights = []
    for region in regions:
        # A flat bright glyph can cover the entire strip in a column. Such
        # columns provide no vertical rail contrast, not a zero-weight rule.
        visible = region[region > 0]
        if not len(visible):
            return 0
        quartile = len(visible) // 4
        weights.append(int(np.partition(visible, quartile)[quartile]))
    reference = min(weights)
    # Equal curves can agree in stroke weight and form a regular lattice.
    # Require a common thin horizontal core at the candidate row as well.
    # Adjacent bright ties need not be absent: they must not replace that core.
    core = strip[3]
    equal = strip == core[None, :]
    run = np.ones(len(core), dtype=np.int16)
    above = below = np.ones(len(core), dtype=bool)
    for step in range(1, 4):
        above = above & equal[3-step]
        below = below & equal[3+step]
        run += above.astype(np.int16) + below.astype(np.int16)
    thin = (run <= 2) & (core - strip.min(axis=0) >= 5)
    common = []
    for colors, usable, visible in zip(np.array_split(core, len(regions)),
                                       np.array_split(thin, len(regions)),
                                       np.array_split(ink > 0, len(regions))):
        # Flat occluding heads supply no vertical evidence. Among columns
        # that do, a majority in every region must agree on the same core.
        # A tapered curve's rare level crossing cannot define a horizontal
        # rule merely because its center differs by one quantization level.
        common.append(np.bincount(colors[usable], minlength=256) / max(1, int(visible.sum())))
    if float(np.minimum.reduce(common).max()) <= .5:
        raise AssertionError('Image staff rule has no consistent thin horizontal core')
    return reference


def detect_staff_lines(picture: Image.Image) -> dict[str, RasterStaff]:
    """Detect both sets of five long horizontal rails from pixels alone.

    The line must be brighter than its neighbors several pixels above/below;
    this is independent of the native engine's stored staff gap/center.
    """
    pixels = np.asarray(picture.convert("RGB"))[:, 20:-20]
    if pixels.shape[1] == 0:
        raise AssertionError("Image too narrow to measure staff rails")
    brightness = np.maximum(np.maximum(pixels[:, :, 0], pixels[:, :, 1]),
                            pixels[:, :, 2])
    values = _staff_row_values(brightness)
    peaks = []
    for y in range(20, picture.height - 20):
        shoulder = (values[y - 4] + values[y + 4]) / 2
        if values[y] - shoulder >= 5:
            peaks.append(y)
    clusters: list[list[int]] = []
    for y in peaks:
        if not clusters or y - clusters[-1][-1] > 3:
            clusters.append([y])
        else:
            clusters[-1].append(y)
    candidates = [sum(group) / len(group) for group in clusters]

    # Recover two *five-line regular lattices*. Line candidates outside those
    # lattices may be notation marks or antialiasing and must not count as
    # staves. A deleted real rule leaves no complete five-line lattice.
    quintets = []
    for first in candidates:
        for fifth in candidates:
            gap = (fifth - first) / 4
            if not 8 <= gap <= 32:
                continue
            selected = []
            for index in range(5):
                location = first + gap * index
                nearby = [v for v in candidates if abs(v - location) <= 2]
                if not nearby:
                    break
                selected.append(min(nearby, key=lambda v: abs(v - location)))
            if len(selected) == 5 and len(set(selected)) == 5:
                variation = sum(abs((selected[i+1] - selected[i]) - gap)
                                for i in range(4))
                quintets.append((variation, tuple(selected)))
    quintets.sort(key=lambda q: q[0])
    chosen = None
    for _error, upper in quintets:
        for _error2, lower in quintets:
            if lower[0] - upper[-1] >= 2 * ((upper[-1] - upper[0]) / 4):
                chosen = (upper, lower)
                break
        if chosen is not None:
            break
    if chosen is None:
        raise AssertionError(
            f"Image has no two complete five-line staff rails: {candidates}")
    # Each staff must support its own shared gray stroke, including minority
    # evidence. Active and inactive staves can have different ink strengths.
    # A majority of bright ties cannot redefine a staff's remaining gray ink.
    # Integrated ink tolerates subpixel phase and 8-bit rounding; foreground
    # contours with inconsistent stroke weight leave the image unverified.
    for staff in chosen:
        rail_ink = [_staff_stroke_ink(brightness, y) for y in staff]
        if min(rail_ink) <= 0 or max(rail_ink) >= 2 * min(rail_ink):
            raise AssertionError("Image staff rails have inconsistent gray stroke ink")
    result = {}
    for hand, selected in zip(("right", "left"), chosen):
        spacings = [b - a for a, b in zip(selected, selected[1:])]
        gap = sum(spacings) / 4
        if not 8 <= gap <= 32 or any(abs(s - gap) > 2.0 for s in spacings):
            raise AssertionError(
                f"Image {hand} rails do not form a five-line staff: {selected}")
        result[hand] = RasterStaff(hand, tuple(selected), gap)
    if result["left"].lines[0] - result["right"].lines[-1] < 2 * result["right"].gap:
        raise AssertionError("Image staves overlap")
    return result


def expected_y(staff: RasterStaff, spelling: tuple[str, int, int],
               clef: tuple[str, int, int]) -> float:
    """Independent diatonic staff-step calculation, no Godot geometry calls."""
    sign, line, octave_change = clef
    # Independent clef references from conventional Western staff notation:
    # the G clef wraps G4, the F clef brackets F3, and a C clef identifies
    # middle C (C4). The declared line can vary across all five staff lines;
    # octave-change clefs sound one or two octaves above/below their glyph.
    anchors={"G":("G",4),"F":("F",3),"C":("C",4)}
    if sign not in anchors or not 1 <= line <= 5 or not -2 <= octave_change <= 2:
        raise ValueError(f"Unsupported written clef {clef!r}")
    reference_step,reference_octave=anchors[sign]
    reference_octave+=octave_change
    step,_alter,octave=spelling
    if step not in DIATONIC:
        raise ValueError(f"Unknown written pitch step {step!r}")
    ref_index=7*reference_octave+DIATONIC[reference_step]
    written_index=7*octave+DIATONIC[step]
    origin=staff.bottom-(line-1)*staff.gap
    return origin-(written_index-ref_index)*staff.gap/2


def ink_row_profile(picture: Image.Image, x: int, lo: int, hi: int) -> list[int]:
    """Count bright NOTE ink in each image row near the physical playhead.

    Staff lines are intentionally darker than solid active-hand noteheads.
    A one-pixel stem cannot alone produce the required broad horizontal ink.
    """
    pixels = picture.convert("RGB").load()
    return [sum(1 for xx in range(x - 13, x + 14)
                if all(v >= t for v, t in zip(pixels[xx, yy], (145, 155, 140))))
            for yy in range(lo, hi)]


def observed_notehead_ys(image: Image.Image, hand: str,
                         staff: RasterStaff) -> list[float]:
    x = round(image.width * PLAYHEAD_FRACTION)
    if x - 13 < 0 or x + 13 >= image.width:
        raise AssertionError("Playhead outside captured frame")
    # The two staff zones are disjoint; one notehead must be identifiable at
    # playhead in the current staff, even for a note on a ledger line.
    if hand == "right":
        lo, hi = 30, round((image.height * .52))
    else:
        lo, hi = round((image.height * .52)), image.height - 30
    row_counts = ink_row_profile(image, x, lo, hi)
    peak_width = max(row_counts, default=0)
    if peak_width < 9:
        raise AssertionError(f"{hand}: no measurable notehead ink at the playhead")
    # Tertian chord noteheads can TOUCH vertically (head height can exceed
    # their one-staff-space separation). Split peaks of *horizontal notehead
    # width* instead of grouping all connected bright rows. A narrow stem
    # cannot create such a wide plateau.
    high_ink = max(7, int(peak_width * .82 + .999))
    rows = [lo + i for i, n in enumerate(row_counts) if n >= high_ink]
    groups: list[list[int]] = []
    for y in rows:
        if not groups or y - groups[-1][-1] > 2:
            groups.append([y])
        else:
            groups[-1].append(y)
    candidates = [(sum(g) / len(g), max(row_counts[y - lo] for y in g))
                  for g in groups if len(g) >= 3]
    if not candidates:
        raise AssertionError(
            f"{hand}: no measurable notehead ink at the playhead")
    return sorted(y for y, _strength in candidates)


def observed_notehead_y(image: Image.Image, hand: str,
                        staff: RasterStaff) -> tuple[float, list[tuple[float, int]]]:
    """Backward-compatible strict singleton helper used by mutation tests."""
    all_ys = observed_notehead_ys(image, hand, staff)
    if len(all_ys) != 1:
        raise AssertionError(
            f"{hand}: expected one isolated quarter-note head at playhead, "
            f"detected {len(all_ys)} candidates: {all_ys}")
    return all_ys[0], [(all_ys[0], 1)]


def verify_pixel_frames(original_xml: str, screenshots: dict[float, Path],
                        *, tolerance_staff_steps: float = .42) -> dict:
    """Probe original score expected pitches directly against screenshot ink.

    A broken or missing image is an error, not an ignored/skipped test.
    """
    reference = read_written_score(original_xml)
    notes = [s for s in reference.symbols if s["kind"] == "note"]
    by_beat: dict[float, dict] = defaultdict(lambda: defaultdict(list))
    for symbol in notes:
        beat = float(symbol["beat"])
        hand = symbol["staff"]
        if symbol["note_type"] != "quarter" or symbol["spelling"] is None:
            raise ValueError("Pixel probe supports written quarter-note heads only")
        by_beat[beat][hand].append(symbol)
    if set(by_beat) != set(screenshots):
        raise AssertionError(f"Missing or extra frame beats: expected {sorted(by_beat)}, got {sorted(screenshots)}")
    clefs = {}
    for _bar, hand, sign, line, octave in reference.clefs:
        if hand in clefs and clefs[hand] != (sign, line, octave):
            raise ValueError("Mid-score clef changes require a different probe")
        clefs[hand] = (sign, line, octave)
    checked = []
    failures = []
    for beat, path in sorted(screenshots.items()):
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        try:
            staves = detect_staff_lines(image)
        except AssertionError as exc:
            failures.append(f"{beat}: {exc}")
            continue
        for hand, symbols in by_beat[beat].items():
            try:
                if hand not in clefs:
                    raise ValueError(f"Missing source clef for {hand}")
                targets = sorted((expected_y(staves[hand], item["spelling"], clefs[hand]),
                                  item["spelling"]) for item in symbols)
                measured = observed_notehead_ys(image, hand, staves[hand])
                if len(targets) != len(measured):
                    raise AssertionError(
                        f"{hand}: {len(measured)} image-space notehead centres for "
                        f"{len(targets)} written notes; centres={measured}")
                for (target, spelling), actual in zip(targets, measured):
                    difference = abs(actual - target)
                    error_in_steps = difference / (staves[hand].gap / 2)
                    result = {"beat": beat, "hand": hand, "spelling": spelling,
                              "expected_y": round(target, 2), "actual_y": round(actual, 2),
                              "staff_gap": round(staves[hand].gap, 2),
                              "error_staff_steps": round(error_in_steps, 3)}
                    checked.append(result)
                    if error_in_steps > tolerance_staff_steps:
                        failures.append(f"{beat} {hand}: actual head at y={actual:.1f}, "
                                        f"written pitch requires y={target:.1f}; "
                                        f"error={error_in_steps:.2f} staff steps")
            except (AssertionError, ValueError) as exc:
                failures.append(f"{beat} {hand}: {exc}")
    expected_count = sum(len(notes) for hands in by_beat.values()
                         for notes in hands.values())
    if len(checked) != expected_count:
        failures.append(f"Only {len(checked)}/{expected_count} noteheads independently measured")
    return {
        "passed": not failures, "notes_expected": expected_count,
        "notes_checked_from_pixels": len(checked), "frames": len(screenshots),
        "measured": checked, "failures": failures,
        "method": "Original MusicXML diatonic pitch vs image-detected ten staff rails and image-detected wide notehead ink; fixed physical playhead; no renderer notehead/staff geometry",
        "not_verified": ["glyph shapes", "stems/beams", "ties", "rests", "accidental symbols", "dense passages", "whole-piece coverage"],
    }
