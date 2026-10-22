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


def _staff_row_values(picture: Image.Image) -> list[float]:
    """A rail spans the viewport; score symbols affect few sampled columns."""
    im = picture.convert("RGB")
    width, height = im.size
    columns = list(range(20, min(150, width // 4), 12))
    columns += list(range(max(width - 160, width * 3 // 4), width - 20, 12))
    pixels = im.load()
    # A real rule crosses nearly every sampled X; localized clef/accidental
    # ink does not. Use the lower quartile rather than the mean so a bright
    # symbol in one part of the viewport cannot masquerade as a staff rail.
    return [sorted(max(pixels[x, y]) for x in columns)[len(columns) // 4]
            for y in range(height)]


def detect_staff_lines(picture: Image.Image) -> dict[str, RasterStaff]:
    """Detect both sets of five long horizontal rails from pixels alone.

    The line must be brighter than its neighbors several pixels above/below;
    this is independent of the native engine's stored staff gap/center.
    """
    values = _staff_row_values(picture)
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
    if (sign, line, octave_change) == ("G", 2, 0):
        bottom_letter, bottom_octave = "E", 4
    elif (sign, line, octave_change) == ("F", 4, 0):
        bottom_letter, bottom_octave = "G", 2
    else:
        raise ValueError(f"Pixel probe does not certify clef {clef!r}")
    step, _alter, octave = spelling
    steps = (octave - bottom_octave) * 7 + DIATONIC[step] - DIATONIC[bottom_letter]
    return staff.bottom - (steps * staff.gap / 2)


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
    rows = [lo + i for i, n in enumerate(row_counts) if n >= 7]
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
