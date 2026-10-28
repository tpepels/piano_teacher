"""Framebuffer ink checks, editorial budgets and diagnostic overlays."""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw

from .case_types import AuditCase
from .case_catalog import AUTUMN_FILE, MAX_AUTUMN_DENSITY

def visible_ink(image: Image.Image, x: float, y: float, radius: int = 11) -> int:
    """Count actual pale notation pixels, excluding dark/grey staff lines."""
    image = image.convert("RGB")
    px = image.load()
    matches = 0
    for yy in range(max(0, round(y)-radius),
                    min(image.height,round(y)+radius+1)):
        for xx in range(max(0, round(x)-radius),
                        min(image.width,round(x)+radius+1)):
            r, g, b = px[xx, yy]
            if r > 154 and g > 165 and b > 150:
                matches += 1
    return matches


def feature_errors(model: dict, case: AuditCase) -> list[str]:
    """Independently assert that each named challenging fixture tests its goal."""
    if not case.features:
        return []
    events = model["notation_events"]
    notes = [e for e in events if e["kind"] == "note"]
    from collections import Counter
    simultaneous = Counter((e.get("staff"), e.get("beat"), e.get("voice"))
                           for e in notes)
    measures = model.get("measures", [])
    pitched = sorted((e for e in notes if e.get("staff") == "right"),
                     key=lambda e:float(e.get("beat",0)))
    def matched_turn():
        for i in range(len(pitched)-2):
            group = pitched[i:i+3]
            if not all(e.get("note_type") == "32nd" and
                       (e.get("time_modification") or {}).get("actual") == 3 and
                       (e.get("time_modification") or {}).get("normal") == 2
                       for e in group):
                continue
            if all(abs(float(group[j+1]["beat"])-float(group[j]["beat"])
                       -1.0/12.0) < 2e-6 for j in (0,1)):
                return True
        return False
    source_onsets = {e["id"]:float(e.get("onset_beats",0.0))
                     for e in model.get("notes",[])}
    swung = sum(1 for e in notes if e.get("is_attack") and
                e.get("source_id") in source_onsets
                and abs((source_onsets[e["source_id"]] % 1.0)-.6)<.015
                and abs(float(e.get("beat",0.0))-
                        source_onsets[e["source_id"]]) < .004)
    observed = {
        "aligned_swing": swung >= 2,
        "chords": any(count > 1 for count in simultaneous.values()),
        "ties": any(not e.get("is_attack", True) for e in notes),
        "tuplets": any(e.get("time_modification") for e in notes),
        "grandstaff": {"left", "right"} <= {e.get("staff") for e in notes},
        "key_change": len({tuple(sorted(m["keys"].items())) for m in measures}) > 1,
        "rests": sum(e["kind"] == "rest" for e in events) >= 2,
        "triplet_turn": matched_turn() if "triplet_turn" in case.features else False,
    }
    return [f"{case.name} stopped exercising required {feature} notation"
            for feature in case.features if not observed.get(feature, False)]


# The generic readability checks must also work with tiny synthetic unit-test
# models; feature-presence requirements belong only to explicitly selected
# real passages, not to every call of the shared checker.
GENERIC_CASE = AuditCase("generic", AUTUMN_FILE, 7, 8,
                         max_density=MAX_AUTUMN_DENSITY, max_tiny_rests=2)


def readability_errors(model: dict, diagnostics: dict,
                       case: AuditCase = GENERIC_CASE) -> list[str]:
    """Fail on known engraving defects, with explicit per-passage budgets."""
    errors = feature_errors(model, case)
    if diagnostics["density"] > case.max_density:
        errors.append(f"{case.name} inflated to {diagnostics['density']:.1f} "
                      f"px/beat (max {case.max_density:.1f})")
    if case.min_lookahead_beats:
        available = float(diagnostics.get("density_witness", {}).get(
            "available_lookahead_beats", 0.0))
        if available + 1e-5 < case.min_lookahead_beats:
            errors.append(f"{case.name}: only {available:.2f} beats ahead "
                          f"(minimum {case.min_lookahead_beats:.2f})")
    if diagnostics["unavoidable_rest_overlaps"]:
        errors.append("Native rests collide with other voice ink")
    events = model["notation_events"]
    tiny_rests = [n for n in events if n["kind"] == "rest" and
                  n["note_type"] in {"32nd","64th","128th"}]
    if len(tiny_rests) > case.max_tiny_rests:
        errors.append("Excessive tiny printed rests in %s (%d; maximum %d)" %
                      (case.name, len(tiny_rests), case.max_tiny_rests))
    gap = float(diagnostics.get("staff_gap", 0.0))
    if gap <= 0.0:
        errors.append("Native staff has no valid layout scale")
    else:
        centers = diagnostics.get("staff_centers", {})
        for frame in diagnostics.get("frames", []):
            for rest in frame.get("rests", []):
                staff = str(rest.get("hand", ""))
                if staff not in centers:
                    errors.append("Rest has no native staff: "+str(rest["id"]))
                    continue
                if abs(float(rest["y"])-float(centers[staff])) > 3.2*gap:
                    errors.append("Rest displaced too far from its staff: "+
                                  str(rest["id"]))
    if any(n["kind"] == "note" and n["dots"] > case.max_dots for n in events):
        errors.append("Unconventional triple/quadruple-dot notation returned "
                      f"in {case.name}")
    note_ids = {n["id"] for n in events if n["kind"] == "note"}
    source_ids = {n["id"] for n in model["notes"]}
    graded = {n["source_id"] for n in events
              if n["kind"] == "note" and n["is_attack"]}
    if source_ids != graded:
        errors.append("Source MIDI attacks differ from visible score attacks")
    if not note_ids:
        errors.append("No native note identities found")
    return errors


def draw_overlay(reference: Image.Image, native: Image.Image,
                 verovio_notes: list[dict], heads: dict,
                 output: Path) -> int:
    """Color-register reference notehead crops by *source ID*, not print X.

    The reference (red) is overlaid on native pixels (mint) at the same
    musical note identity. Keep the full reference next to the local native
    view because rests and spacing differences can require expert review.
    """
    native = native.convert("RGBA")
    panel = native.convert("RGB")
    overlay = Image.new("RGBA", native.size, (0, 0, 0, 0))
    n = 0
    for note in verovio_notes:
        ident = str(note["id"])
        if ident not in heads or int(note.get("page",0)) != 0:
            continue
        x, y = heads[ident]
        if not (30 <= x < native.width-30 and 28 <= y < native.height-28):
            continue
        rx = round(float(note["x"]) * reference.width)
        ry = round(float(note["y"]) * reference.height)
        half = 12
        crop = reference.convert("RGBA").crop(
            (rx-half,ry-half,rx+half+1,ry+half+1))
        ink = crop.getchannel("A")
        # Reference raster may have an opaque background; compare ink alone.
        # Cairo's rendered Verovio ink has lower luminance than a white page.
        if ink.getextrema() == (255,255):
            grey = crop.convert("L")
            ink = grey.point(lambda p: 220 if p < 155 else 0)
        red = Image.new("RGBA",crop.size,(245,91,96,0))
        red.putalpha(ink.point(lambda a: round(a*.46)))
        overlay.alpha_composite(red, (round(x)-half,round(y)-half))
        n += 1
    composited = Image.alpha_composite(native,overlay).convert("RGB")
    pen = ImageDraw.Draw(composited)
    pen.text((34,14),"NATIVE + VEROVIO NOTE-ANCHOR OVERLAY (red = Verovio)",fill="white")
    composited.save(output)
    # Accompany overlay with the unwarped optical source and full native score.
    reference.thumbnail((native.width, native.height), Image.Resampling.LANCZOS)
    comparison = Image.new("RGB",(native.width,native.height*2),(19,44,35))
    comparison.paste(reference.convert("RGB"),(0,0))
    comparison.paste(panel,(0,native.height))
    comparison.save(output.with_name(output.stem+"-side-by-side.png"))
    return n

