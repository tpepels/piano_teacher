"""Phase 3 independent pitch/clef positions in every actual Godot PNG.

Written notes are read from the generated MusicXML by the independent
ElementTree oracle (NOT the native score model). For genuine source MusicXML,
Phase 1 separately compares that complete score to the ORIGINAL MusicXML.
The checker recovers actual staff lines and notehead centres from raster
pixels, without using renderer-reported head or staff coordinates.

The pixel detector intentionally fails closed on dense/unseparable notes.
Those must be fixed or reported as not yet covered, never silently counted
as verified. This currently certifies pitch positions, not all engravings.
"""
from __future__ import annotations
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
import json
import math

from PIL import Image

from .proof import read_written_score
from .pixel_proof import detect_staff_lines, expected_y
from .symbol_pixel_proof import bright
from .raster_matching import match_glyph as _match_glyph
from .raster_matching import glyph_search_components, match_glyphs_joint, photographed_playhead_columns
from .reference_font import reference_glyphs


def verify_translation_sequence(first: Image.Image, middle: Image.Image,
                                last: Image.Image) -> dict:
    """Measure two equal-time steps from pale score ink, never native telemetry.

    The playhead and quiet staff rules are excluded by the independent ink
    mask. No requested density or absolute reference-print X enters this
    measurement. Insufficient or changing contours remain unverified.
    """
    import numpy as np

    pictures = (first, middle, last)
    if len({p.size for p in pictures}) != 1:
        return dict(passed=False, status="unverified", reason="Motion framebuffer dimensions changed")
    width = first.width
    margin = max(16, round(width*.06))
    masks = [bright(p)[:, margin:width-margin] for p in pictures]
    if any(np.count_nonzero(mask) < 24 for mask in masks):
        return dict(passed=False, status="unverified", reason="Insufficient moving score ink")
    steps, scores, competing = [], [], []
    limit = min(round(width*.18), masks[0].shape[1]//3)
    for a, b in zip(masks, masks[1:]):
        left, right = a.sum(axis=0).astype(float), b.sum(axis=0).astype(float)
        candidates = []
        for shift in range(-limit, limit+1):
            aa, bb = (left[shift:], right[:-shift]) if shift > 0 else (
                (left[:shift], right[-shift:]) if shift < 0 else (left, right))
            norm = float(np.linalg.norm(aa)*np.linalg.norm(bb))
            candidates.append((float(aa.dot(bb))/norm if norm else 0, shift))
        best = None
        alternatives = []
        for _score, shift in sorted(candidates, reverse=True)[:8]:
            aa, bb = (a[:, shift:], b[:, :-shift]) if shift > 0 else (
                (a[:, :shift], b[:, -shift:]) if shift < 0 else (a, b))
            dice = float(2*np.count_nonzero(aa & bb)/(np.count_nonzero(aa)+np.count_nonzero(bb)))
            candidate = (dice, -abs(shift), shift)
            alternatives.append((dice, shift))
            if best is None or candidate > best:
                best = candidate
        scores.append(round(best[0], 4))
        steps.append(best[2])
        # Repeated musical patterns may register at more than one displacement.
        # The larger displacement must not be asserted as an actual camera
        # jump if a different alignment is nearly equally convincing.
        competing.append([shift for dice, shift in alternatives
                          if abs(shift-best[2]) > 2 and dice >= max(.80, best[0]-.01)])
    coherent = min(scores) >= .80
    forward = min(steps) > 0
    uniform = abs(steps[0]-steps[1]) <= 1
    unique = not any(competing)
    passed = coherent and forward and uniform and unique
    reason = ("Image registration has multiple plausible translations in repeated notation"
              if not unique else
              "Equal musical steps preserve forward score translation" if passed else
              "Score froze, reversed, jumped or lacked coherent image correspondence")
    return dict(passed=passed, status="verified" if passed else "unverified",
                pixel_steps=steps, contour_agreement=scores,
                competing_shifts=competing, reason=reason)


def verify_scroll_pixels(xml: str, folder: Path) -> dict:
    """Witness initial movement and every measure transition on the same view."""
    written = read_written_score(xml)
    duration = float(written.bars[-1])
    step = min(.0625, duration/4)
    centers = [step, *(float(b) for b in written.bars[1:-1])]
    measured = []
    for center in centers:
        clocks = [round(center-step, 8), round(center, 8), round(center+step, 8)]
        try:
            pictures = []
            for clock in clocks:
                with Image.open(folder/f"native-{clock:.5f}.png") as picture:
                    pictures.append(picture.convert("RGB"))
            result = verify_translation_sequence(*pictures)
        except (OSError, ValueError) as exc:
            result = dict(passed=False, status="unverified", reason=str(exc))
        measured.append(dict(clock=center, **result))
    return dict(passed=all(r["passed"] for r in measured), measured=measured,
                scope="Actual framebuffer translation at equal musical steps; fixed layout scale is unrestricted")


def _clef_at(reference, bar: int, hand: str):
    matches=[(at,sign,line,octave) for at,h,sign,line,octave in reference.clefs
             if h==hand and at<=bar]
    if not matches:
        raise ValueError(f"No explicit clef for {hand} in source window")
    _i,sign,line,octave=max(matches,key=lambda e:e[0])
    return sign,line,octave


def _ledger_context_rows(pixels, rail, written, notes):
    """Recover thin ledger rules at source-required diatonic positions.

    A line must have real continuous bright ink beyond a head's width.
    Return its measured (row,left,right) span so the matcher can require
    actual ownership at each head, rather than masking that Y everywhere.
    This recognizes permitted occluding ink, never supplies head support.
    Unrelated staff positions or broad filled regions authorize nothing.
    """
    import numpy as np
    expected=set()
    for note in notes:
        y=expected_y(rail,note["spelling"],_clef_at(written,note["index"],note["staff"]))
        step=round((rail.bottom-y)*2/rail.gap)
        steps=range(-2,step-1,-2) if step<0 else range(10,step+1,2)
        expected.update(rail.bottom-s*rail.gap/2 for s in steps)
    origin=round(pixels.shape[1]*.42)
    left,right=max(0,origin-round(3*rail.gap)),min(pixels.shape[1],origin+round(3*rail.gap))
    rows=set()
    for y in expected:
        candidates=[]
        for row in range(max(0,round(y-.13*rail.gap)),min(pixels.shape[0],round(y+.13*rail.gap)+1)):
            line=pixels[row,left:right]
            edges=np.flatnonzero(np.diff(np.r_[False,line,False].astype(int)))
            runs=[]
            for a,b in zip(edges[::2],edges[1::2]):
                if runs and a-runs[-1][1]<=min(3,math.ceil(.13*rail.gap)):
                    runs[-1]=(runs[-1][0],b)
                else:
                    runs.append((a,b))
            for a,b in runs:
                if b-a>=1.5*rail.gap:
                    candidates.append((row,left+int(a),left+int(b)))
        if candidates and max(r[0] for r in candidates)-min(r[0] for r in candidates)+1<=max(2,math.ceil(.14*rail.gap)):
            rows.update(candidates)
    return tuple(sorted(rows))


def verify_all_notehead_pixels(generated_xml: str, folder: Path,
                               *, hand: str = "both",
                               tolerance_staff_steps: float = .42) -> dict:
    """Require all active-hand written notes to match actual image-space Y.

    One frame per unique written onset. The image's own recovered five-line
    staves define the coordinate system; MusicXML pitch and clef supply its
    expected pitch position. This source-directed search does not prove the
    absence of extra symbols elsewhere in the image.
    """
    if hand not in ("both","left","right"):
        raise ValueError("Invalid hand mode")
    if not 0 <= tolerance_staff_steps < 1:
        raise ValueError("Pitch registration tolerance must be less than one staff step")
    written=read_written_score(generated_xml)
    by_clock=defaultdict(lambda:defaultdict(list))
    for symbol in written.symbols:
        if symbol["kind"]!="note" or not symbol["visible"]:
            continue
        staff=symbol["staff"]
        if hand!="both" and staff!=hand:
            continue
        by_clock[round(float(symbol["beat"]),8)][staff].append(symbol)
    glyphs=reference_glyphs()
    verified=0
    failures=[]
    details=[]
    def record(note, clock, status, **evidence):
        details.append({"source_id":note.get("id"),"measure":note["measure"],
                        "voice":note["voice"],"beat":clock,"staff":note["staff"],
                        "spelling":note["spelling"],"status":status,**evidence})
    for clock,hands in sorted(by_clock.items()):
        filename=folder/f"native-{clock:.5f}.png"
        if not filename.is_file():
            failures.append(f"{clock}: screenshot missing")
            for notes in hands.values():
                for note in notes:
                    record(note,clock,"unverified",reason="screenshot missing")
            continue
        with Image.open(filename) as raw:
            image=raw.convert("RGB")
        try:
            staves=detect_staff_lines(image)
        except AssertionError as exc:
            failures.append(f"{clock}: five-line staff detection failed: {exc}")
            for notes in hands.values():
                for note in notes:
                    record(note,clock,"unverified",reason=str(exc))
            continue
        raster=bright(image)
        occlusion_columns=photographed_playhead_columns(image)
        xpos=round(image.width*.42)
        requests=[]
        for staff,notes in hands.items():
            try:
                ledger_rows=_ledger_context_rows(raster,staves[staff],written,notes)
                pitches=sorted([
                    (expected_y(staves[staff],note["spelling"],
                        _clef_at(written,note["index"],staff)),note)
                    for note in notes
                ],key=lambda pair:pair[0])
                # Use the source type to select the original independent
                # Verovio notehead outline. Hollow heads cannot be counted
                # as filled peaks; closely touching filled heads can merge.
                # Compare each actual head silhouette in native PNG pixels
                # at its MusicXML-derived diatonic position.
                for target,note in pitches:
                    kind=note["note_type"]
                    glyph=("head_whole" if kind=="whole" else
                           "head_half" if kind=="half" else "head_black")
                    # Seconds in a chord are deliberately displaced
                    # horizontally by the engraver; they may also overlap
                    # another head mask and lower silhouette agreement.
                    # A second moves members of its common stem group,
                    # including more distant chord tones. Infer that search
                    # region from the written voice/chord, never native X.
                    group=[(y,n) for y,n in pitches if n["voice"]==note["voice"]]
                    displaced_group=any(
                        a is not b and abs(ay-by)<=1.05*staves[staff].gap
                        for ay,a in group for by,b in group)
                    x_search=range(-32,33) if displaced_group else range(-16,17)
                    requests.append(dict(note=note,glyph=glyphs[glyph],name=glyph,
                        gap=staves[staff].gap,origin_y=target,dxs=x_search,
                        alternatives=tuple((name,glyphs[name]) for name in ("head_black","head_half","head_whole") if name!=glyph),
                        background_rows=ledger_rows if glyph!="head_black" else (),
                        occlusion_columns=occlusion_columns,
                        unison=sum(abs(y-target)<.001 for y,_ in pitches)>1))
            except (ValueError,AssertionError,TypeError) as exc:
                failures.append(f"{clock} {staff}: {exc}")
                for note in notes:
                    if not any(r.get("source_id")==note.get("id") and
                               r["beat"]==clock and r["staff"]==staff for r in details):
                        record(note,clock,"unverified",reason=str(exc))
        # Group the complete registration envelopes, including other staves
        # and more distant chord tones. Different groups have disjoint pixel
        # rows, so no verified identity can reuse another group's head ink.
        # Gaps are recovered per staff; use each request's unchanged Y range.
        # A shared union range only partitions groups conservatively.
        radius=max((math.floor(tolerance_staff_steps*r["gap"]/2)
                    for r in requests),default=0)
        for indices in glyph_search_components(requests,dys=range(-radius,radius+1)):
            group=[requests[i] for i in indices]
            # Supply the per-staff range to the joint search as well: using
            # the union radius for matching could relax a smaller staff.
            for request in group:
                r=math.floor(tolerance_staff_steps*request["gap"]/2)
                request["dys"]=range(-r,r+1)
            joint=None
            if not any(r["unison"] for r in group):
                joint=match_glyphs_joint(raster,group,xpos,dys=range(-radius,radius+1))
            for i,request in enumerate(group):
                note=request["note"]
                staff=note["staff"]
                if request["unison"]:
                    record(note,clock,"ambiguous",reason="Unison source events can share one visible head; raster identity is inseparable")
                    continue
                evidence={}
                if joint is not None:
                    assigned=joint[i]
                    score=assigned["score"]
                    evidence["joint_assignment"]=dict(heads=len(group),
                        x=assigned["x"],y=assigned["y"],
                        exclusive_ink=len(assigned["support"]),
                        visible_reference_pixels=assigned['visible_reference_pixels'],
                        reference_pixels=assigned['reference_pixels'],
                        isolated_match=round(assigned["isolated_score"],3))
                else:
                    score=_match_glyph(raster,request["glyph"],request["gap"],
                        xpos,request["origin_y"],centered=True,
                        dxs=request["dxs"],dys=request["dys"],background_rows=request["background_rows"],
                        occlusion_columns=request['occlusion_columns'])
                status="verified"
                if score<.79:
                    # Weak contour evidence is not a claim of wrong pitch.
                    # A failed joint assignment must not hide an independently
                    # failing head behind the other members' ambiguity.
                    status="unverified"
                    evidence["reason"]="Insufficient isolated contour evidence; ledger, stem or other ink may interfere"
                    failures.append(f"{clock} {staff} {note['spelling']}: "
                        f"required {request['name']} not independently identified at written "
                        f"staff position (image score={score:.3f})")
                elif joint is None:
                    status="ambiguous"
                    evidence["reason"]="No bounded source-family assignment with sufficient distinct notehead ink"
                else:
                    verified+=1
                record(note,clock,status,glyph=request["name"],match=round(score,3),
                       target_y=round(request["origin_y"],2),**evidence)
    total=sum(len(notes) for hands in by_clock.values() for notes in hands.values())
    if len(details)!=total:
        failures.append(f"Independent raster pitch accounting {len(details)}/{total}")
    return {
        "passed":not failures, "written_active_noteheads":total,
        "image_pitch_verified":verified,"unique_onset_frames":len(by_clock),
        "tolerance_staff_steps":tolerance_staff_steps,
        "failures":failures,"measured":details,
        "complete":verified==total,
        "coverage":dict(expected=total,**{status:sum(r["status"]==status for r in details)
                        for status in ("verified","ambiguous","unsupported","unverified","mismatch")}),
        "scope":"Source-directed notehead silhouette search at written pitch "
                "relative to actual screenshot staff rails; no native geometry",
        "not_verified":["extra symbols elsewhere in the image",
                        "one-to-one assignment of inseparable dense silhouettes",
                        "stems, flags, augmentation dots and accidentals",
                        "individual beam/tie/slur masks in complex overlaps"],
    }



@lru_cache(maxsize=128)
def _render_rest_svg(svg: str, width: int, height: int):
    """Cache identical authentic font masks across thousands of full-score rests."""
    from io import BytesIO
    import cairosvg
    import numpy as np

    png=cairosvg.svg2png(bytestring=svg.encode(),
                         output_width=width,output_height=height)
    alpha=np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3]
    return alpha >= 80


def _rest_template_mask(glyph: dict, gap: float):
    """Rasterize the original Verovio SVG at the *measured image* staff scale."""
    bounds=glyph["bounds"]
    width=max(1,round(float(bounds[2])*gap/250))
    height=max(1,round(float(bounds[3])*gap/250))
    return _render_rest_svg(glyph["svg"],width,height)


def _compare_isolated_masks(observed, reference) -> float:
    """Compare two binary rest glyphs up to two pixels of raster registration.

    Unlike the old raw-image classifier, *no nearby stem, note or different
    rest is visible* in the controlled difference mask. The vertical lane is
    read from pixels, not taken from the renderer's rest-y diagnostic.
    """
    import numpy as np

    ys,xs=np.nonzero(observed)
    ry,rx=np.nonzero(reference)
    if len(xs)<5 or len(rx)<5:
        return 0.0
    # Trim SVG's standard transparent 12-unit margin; neither template
    # nor rendered image is resized to force a match.
    data=observed[ys.min():ys.max()+1,xs.min():xs.max()+1]
    shape=reference[ry.min():ry.max()+1,rx.min():rx.max()+1]
    h=max(data.shape[0],shape.shape[0])+8
    w=max(data.shape[1],shape.shape[1])+8
    best=0.0
    for dy in range(-2,3):
        for dx in range(-2,3):
            left=4+dx
            top=4+dy
            canvas=np.zeros((h,w),dtype=bool)
            canvas[top:top+shape.shape[0],left:left+shape.shape[1]]=shape
            test=np.zeros((h,w),dtype=bool)
            test[4:4+data.shape[0],4:4+data.shape[1]]=data
            intersect=int(np.count_nonzero(canvas & test))
            dice=2*intersect/(int(canvas.sum())+int(test.sum()))
            if dice>best:
                best=dice
    return best


def _rest_delta_parts(delta, gap: float) -> list[dict]:
    """Separate horizontally detached marks; bridge only small raster gaps.

    A playhead can occlude a narrow column through a rest. Joining that cut
    does not authorize joining a detached dot to the body. Inseparable ink
    stays in one part and cannot establish independent dot ownership.
    """
    import numpy as np

    columns = np.flatnonzero(delta.any(axis=0))
    groups = []
    for x in columns:
        if not groups or x-groups[-1][-1]-1 > max(1, math.floor(.12*gap)):
            groups.append([])
        groups[-1].append(int(x))
    parts = []
    for group in groups:
        left, right = group[0], group[-1]
        rows = np.flatnonzero(delta[:, left:right+1].any(axis=1))
        top, bottom = int(rows[0]), int(rows[-1])
        mask = delta[top:bottom+1, left:right+1]
        parts.append(dict(mask=mask, box=[left, top, right, bottom]))
    return sorted(parts, key=lambda part: int(part["mask"].sum()), reverse=True)


def _rectangular_rest_orientation(box: list[int], staff) -> dict:
    """Distinguish hanging/sitting ink modulo a measured staff space.

    Whole-space voice displacements preserve the edge phase even outside
    the five printed rails. Quarter-space or poorly resolved rectangles do
    not supply an orientation. Pixel edges lie half a pixel outside centres.
    """
    gap = staff.gap
    top, bottom = box[1]-.5, box[3]+.5

    def line_distance(edge):
        phase = (edge-staff.lines[0])/gap
        return abs(phase-round(phase))

    hanging, sitting = line_distance(top), line_distance(bottom)
    height = (bottom-top)/gap
    observed = None
    if .35 <= height <= .65:
        if hanging <= .13 and sitting >= .30:
            observed = "whole"
        elif sitting <= .13 and hanging >= .30:
            observed = "half"
    return dict(observed_rest=observed, staff_lines=list(staff.lines), staff_gap=gap,
                hanging_edge_error_spaces=round(hanging, 4),
                sitting_edge_error_spaces=round(sitting, 4),
                height_spaces=round(height, 4))


@lru_cache(maxsize=32)
def _rest_dot_template_mask(gap: float):
    """Read SMuFL augmentation-dot ink from the external Leipzig font."""
    from xml.etree import ElementTree as ET
    import verovio

    resources = Path(verovio.__file__).resolve().parent / "data"
    metric = ET.parse(resources/"Leipzig.xml").getroot().find("g[@c='E1E7']")
    if metric is None:
        raise ValueError("External font lacks an augmentation-dot metric")
    x, y, w, h = (float(metric.get(k)) for k in ("x", "y", "w", "h"))
    bounds = [x-12, -y-h-12, w+24, h+24]
    svg = ET.Element("svg", xmlns="http://www.w3.org/2000/svg",
                     viewBox=" ".join(map(str, bounds)), fill="white")
    svg.append(ET.parse(resources/"Leipzig/E1E7.xml").getroot())
    return _rest_template_mask(dict(svg=ET.tostring(svg, encoding="unicode"),
                                    bounds=bounds), gap)


def _rest_dot_evidence(parts: list[dict], body_box: list[int],
                       count: int, gap: float) -> dict:
    """Require distinct, detached, rightward dot contours in removed ink.

    No unchanged neighbor can supply a dot, and no changed part is ignored.
    Touching/occluded dots and more than two dots remain nonverified.
    """
    evidence = dict(status="unverified", expected_count=count,
                    observed_count=0, dots=[])
    if count > 2:
        return dict(evidence, status="unsupported", reason="More than two rest dots needs separate bounded assignment")
    if not parts and not count:
        return dict(evidence, status="verified", reason="No detached changed ink or written dots")
    reference = _rest_dot_template_mask(gap)
    previous = None
    for part in sorted(parts, key=lambda p: p["box"][0]):
        box = part["box"]
        x, y = (box[0]+box[2])/2, (box[1]+box[3])/2
        match = _compare_isolated_masks(part["mask"], reference)
        separated = (.1*gap <= box[0]-body_box[2] <= 2.2*gap and
                     body_box[1]-.75*gap <= y <= body_box[3]+.75*gap)
        if previous is not None:
            separated = separated and .4*gap <= x-previous[0] <= .9*gap and abs(y-previous[1]) <= .15*gap
        if match < .8 or not separated:
            return dict(evidence, reason="Detached changed ink cannot establish separate rest-dot contours")
        evidence["dots"].append(dict(box=box, shape_match=round(match, 4)))
        evidence["observed_count"] += 1
        previous = x, y
    if evidence["observed_count"] != count:
        return dict(evidence, status="mismatch" if evidence["observed_count"] > count else "unverified",
                    reason="Observed isolated rest-dot count differs from written count")
    return dict(evidence, status="verified", reason="Every written rest dot has distinct suppressed external-font ink")


def _rest_placement_registration(body: dict, glyph: dict, gap: float) -> dict:
    """Register external ink without resizing it or choosing a staff lane.

    Retain every near-best raster registration. All of their independently
    inferred font origins must support the same staff-grid phase.
    """
    import numpy as np

    raw = _rest_template_mask(glyph, gap)
    ys, xs = np.nonzero(raw)
    template = raw[ys.min():ys.max()+1, xs.min():xs.max()+1]
    observed = body["mask"]
    h, w = max(observed.shape[0], template.shape[0])+8, max(observed.shape[1], template.shape[1])+8
    ink = np.zeros((h, w), dtype=bool)
    ink[4:4+observed.shape[0], 4:4+observed.shape[1]] = observed
    denominator = int(ink.sum())+int(template.sum())
    candidates = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            expected = np.zeros((h, w), dtype=bool)
            expected[4+dy:4+dy+template.shape[0], 4+dx:4+dx+template.shape[1]] = template
            score = 2*int((ink & expected).sum())/denominator
            candidates.append(dict(score=score, x=body["box"][0]+dx, y=body["box"][1]+dy))
    best = max(c["score"] for c in candidates)
    registrations = [c for c in candidates if c["score"] >= best-.02]
    for c in registrations:
        c["baseline_y"] = c["y"]-int(ys.min())-float(glyph["bounds"][1])*gap/250
    return dict(match=best, template=template, registrations=registrations)


def _rest_clearance(silhouette, other_ink, gap: float) -> tuple[float, bool]:
    """Conservative pixel-edge clearance, bounded to one staff space.

    Eight-neighbor dilation measures Chebyshev distance, a lower bound on
    Euclidean clearance. Adjacent pixel squares touch and have zero clearance.
    A capped result states a lower bound, never infinite clearance.
    """
    import numpy as np

    grown = silhouette.copy()
    limit = math.ceil(gap)+1
    for distance in range(limit+1):
        if np.any(grown & other_ink):
            return float(max(0, distance-1)), False
        padded = np.pad(grown, 1)
        grown = np.logical_or.reduce([
            padded[dy:dy+grown.shape[0], dx:dx+grown.shape[1]]
            for dy in range(3) for dx in range(3)])
    return float(limit-1), True


def _rest_placement_evidence(body: dict, glyph: dict, delta, suppressed_ink,
                             staves: dict, staff_name: str, *, note_type: str) -> dict:
    """Prove a readable grid-relative layout, never an intended voice lane."""
    import numpy as np

    staff = staves[staff_name]
    gap, center = staff.gap, staff.lines[2]
    ys, xs = np.nonzero(delta)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    required_clearance = .12
    # Two and a half spaces beyond the printed rails, clipped at the midpoint
    # to an adjacent staff. This is an explicit readability bound, not a
    # source-derived declaration of the intended rest voice or lane.
    top, bottom = max(0., staff.lines[0]-2.5*gap), min(delta.shape[0]-1., staff.lines[-1]+2.5*gap)
    for name, other in staves.items():
        if name == staff_name:
            continue
        midpoint = (other.lines[2]+center)/2
        if other.lines[2] < center:
            top = max(top, midpoint+required_clearance*gap)
        else:
            bottom = min(bottom, midpoint-required_clearance*gap)
    evidence = dict(status="unverified", bbox=bbox, body_bbox=body["box"],
                    staff_lines=list(staff.lines), staff_gap=gap,
                    corridor_y=[top, bottom], required_clearance_spaces=required_clearance,
                    grid_phase_tolerance_spaces=.13)
    registered = _rest_placement_registration(body, glyph, gap)
    evidence["registration_match"] = round(registered["match"], 4)
    if registered["match"] < .79:
        return dict(evidence, reason="Rest contour cannot independently establish a bounded font-origin registration")
    registrations = registered["registrations"]
    best = max(registrations, key=lambda c: c["score"])
    baseline = best["baseline_y"]
    offsets = [(c["baseline_y"]-center)/gap for c in registrations]
    # Rectangular rests must preserve hanging/sitting phase. Other native
    # rest glyphs can occupy either a line or space in a readable voice lane.
    grid_step = 1. if note_type in {"whole", "half"} else .5
    errors = [abs(offset-round(offset/grid_step)*grid_step) for offset in offsets]
    evidence.update(baseline_y=baseline, relative_offset_spaces=round((baseline-center)/gap, 4),
                    baseline_range_y=[min(c["baseline_y"] for c in registrations),
                                      max(c["baseline_y"] for c in registrations)],
                    grid_phase_error_spaces=round(max(errors), 4))

    # Reconstruct the full external body, including ink hidden beneath another
    # symbol. Visible subtraction alone could miss same-colored overlapping
    # ink. Dots additionally contribute their actual isolated removed pixels.
    template = registered["template"]
    left = min(bbox[0], min(c["x"] for c in registrations))
    right = max(bbox[2], max(c["x"]+template.shape[1]-1 for c in registrations))
    upper = min(bbox[1], min(c["y"] for c in registrations))
    lower = max(bbox[3], max(c["y"]+template.shape[0]-1 for c in registrations))
    evidence["silhouette_bbox"] = [left, upper, right, lower]
    if left < 0 or upper < 0 or right >= delta.shape[1] or lower >= delta.shape[0]:
        return dict(evidence, reason="Complete external rest outline is clipped by the framebuffer")
    pad = math.ceil(gap)+1
    x0, y0 = max(0, left-pad), max(0, upper-pad)
    x1, y1 = min(delta.shape[1], right+pad+1), min(delta.shape[0], lower+pad+1)
    silhouette = delta[y0:y1, x0:x1].copy()
    for c in registrations:
        y, x = c["y"]-y0, c["x"]-x0
        silhouette[y:y+template.shape[0], x:x+template.shape[1]] |= template
    clearance, capped = _rest_clearance(silhouette, suppressed_ink[y0:y1, x0:x1], gap)
    evidence.update(min_clearance_pixels=clearance, min_clearance_spaces=round(clearance/gap, 4),
                    clearance_capped=capped, clearance_search_spaces=1.)
    if clearance/gap < required_clearance:
        return dict(evidence, status="mismatch", reason="Other bright framebuffer ink touches, overlaps or crowds the rest/dot silhouette")
    if upper-.5 < top or lower+.5 > bottom:
        return dict(evidence, status="mismatch", reason="Rest/dot silhouette lies outside its readable staff corridor")
    if max(errors) > .13:
        return dict(evidence, status="mismatch" if min(errors) > .2 else "ambiguous",
                    reason="Independent font-origin registration does not establish the rest type's staff-grid phase")
    return dict(evidence, status="verified", reason="External-font baseline follows the staff grid inside a readable corridor with independent bright-ink clearance")


def verify_all_rest_pixels(generated_xml: str, folder: Path,
                           *, hand: str = "both") -> dict:
    """Check rest contours using a reversible, full-frame image intervention.

    No-op and restored frames must equal the source framebuffer. Suppression
    may only remove ink in a bounded rest region. Rectangular rest identity
    needs an unambiguous hanging/sitting edge relative to detected staff rails.
    Detached dots require their own external-font contours in the same delta.
    Missing/contaminated captures are failed evidence, not musical defects.
    Per-event placement additionally requires a font-derived staff-grid origin,
    readable corridor and local clearance in the suppressed bright framebuffer.
    ``complete`` covers glyphs; ``placement_complete`` separately gates layout.
    """
    import numpy as np

    if hand not in ("both", "left", "right"):
        raise ValueError("Invalid practice hand mode")
    score = read_written_score(generated_xml)
    written = [s for s in score.symbols if s["kind"] == "rest"
               and s["visible"] and (hand == "both" or s["staff"] == hand)]
    diagnostics = json.loads((folder/"native-overlay-report.json").read_text())
    glyphs = reference_glyphs()
    controls = defaultdict(list)
    for control in diagnostics.get("rest_difference_controls", []):
        key = (round(float(control["clock"]), 8), control["staff"], control["voice"])
        controls[key].append(control)
    frames = {round(float(frame["clock"]), 8): frame
              for frame in diagnostics.get("rest_difference_frames", [])}
    written_by = defaultdict(list)
    for event in written:
        written_by[round(float(event["beat"]),8),event["staff"],event["voice"]].append(event)
    failures, measured = [], []
    identity_deltas = defaultdict(list)
    coverage = dict(expected=len(written), verified=0, ambiguous=0,
                    unsupported=0, unverified=0, mismatch=0)

    def raster(filename):
        path = folder/filename
        if not path.is_file():
            raise ValueError(f"missing actual screenshot: {filename}")
        with Image.open(path) as raw:
            return np.asarray(raw.convert("RGB"), dtype=np.int16)

    for key in controls:
        if (hand == "both" or key[1] == hand) and key not in written_by:
            failures.append(f"Unexpected rendered rest control: {key}")
    for key, events in written_by.items():
        beat,staff,voice = key
        selections = controls.get(key, [])
        frame_error = None
        try:
            if diagnostics.get("rest_difference_protocol") != 2:
                raise ValueError("unvalidated subtraction protocol; full-frame repeat/restore required")
            original = raster(f"native-{beat:.5f}.png")
            metadata = frames.get(beat, {})
            repeat = raster(metadata.get("repeat_file", "missing-repeat.png"))
            restored = raster(metadata.get("restored_file", "missing-restored.png"))
            if not (original.shape == repeat.shape == restored.shape):
                raise ValueError("no-op/restored raster dimensions changed")
            if not np.array_equal(original, repeat):
                raise ValueError("unchanged frame drifted; subtraction is uncontrolled")
            if not np.array_equal(original, restored):
                raise ValueError("restored frame drifted; intervention changed other state")
            rails = detect_staff_lines(Image.fromarray(original.astype("uint8")))
            gap = rails[staff].gap
        except (ValueError, AssertionError, OSError) as exc:
            frame_error = str(exc)
        used = set()
        for event in events:
            identity = event.get("id") or f"measure-{event['measure']}-voice-{voice}-rest-{len(measured)}"
            row = {"source_id":identity, "measure":event["measure"], "beat":beat,
                   "staff":staff, "voice":voice, "required_rest":event["note_type"],
                   "status":"unverified", "placement_evidence":dict(status="unverified",
                       reason="Unique rest identity and controlled contour evidence required before placement")}
            reason = frame_error
            # Prefer an exact source ID; do not pair duplicate voice/onset
            # rests in arbitrary order and claim an identity match.
            choices = [c for c in selections if c.get("id") == event.get("id")]
            if not choices and len(events) == len(selections) == 1:
                choices = selections
            if reason is None and len(choices) != 1:
                reason = "missing or ambiguous source-to-intervention identity"
            if reason is None:
                control = choices[0]
                if control.get("id") in used:
                    reason = "same intervention reused for multiple written rests"
                used.add(control.get("id"))
            if reason is not None:
                row["reason"] = reason
                coverage["unverified"] += 1
                failures.append(f"{key} {identity}: {reason}")
                measured.append(row)
                continue
            try:
                suppressed = raster(control["file"])
                if suppressed.shape != original.shape:
                    raise ValueError("suppressed raster must cover the entire unchanged viewport")
                delta = np.max(np.abs(original-suppressed),axis=2) >= 10
                ys,xs = np.nonzero(delta)
                row.update(delta_file=control["file"],changed_pixels=len(xs))
                if len(xs) < 12:
                    raise ValueError("missing/occluded rest: insufficient visible changed pixels")
                original_ink=bright(Image.fromarray(original.astype("uint8")))
                suppressed_ink=bright(Image.fromarray(suppressed.astype("uint8")))
                visible_removed=delta & original_ink & ~suppressed_ink
                row["visible_original_ink_removed"]=int(np.count_nonzero(visible_removed))
                if row["visible_original_ink_removed"]<12:
                    raise ValueError("control did not remove visible original rest ink")
                # Removing one pale rest cannot ADD independent pale ink.
                added = suppressed_ink & ~original_ink
                if np.count_nonzero(added & delta):
                    raise ValueError("suppression added unrelated ink; contaminated control")
                xpos = round(original.shape[1]*.42)
                if xs.min() < xpos-80 or xs.max() >= xpos+80:
                    raise ValueError("intervention changed pixels outside the rest onset region")
                if xs.max()-xs.min() > gap*4 or ys.max()-ys.min() > gap*9:
                    raise ValueError("intervention changed more than a single bounded rest/dot contour")
                # Preserve full-frame pixel addresses, without contour trimming
                # or registration: different voices must not reuse one glyph.
                identity_deltas[beat].append((row, np.flatnonzero(delta)))
                parts = _rest_delta_parts(delta, gap)
                body, marks = parts[0], parts[1:]
                # Font expectation is read independently of fixture assets.
                scores = {name.removeprefix("rest_"):round(_compare_isolated_masks(
                    body["mask"], _rest_template_mask(glyph,gap)),4)
                    for name,glyph in glyphs.items() if name.startswith("rest_")}
                expected = event["note_type"]
                if expected not in scores:
                    row.update(status="unsupported",reason=f"external font lacks rest type {expected}")
                else:
                    family = ("whole","half") if expected in ("whole","half") else (expected,)
                    match = max(scores[k] for k in family)
                    rival = max((v for k,v in scores.items() if k not in family),default=0)
                    row.update(shape_match=match,next_family_score=rival,
                               type_ambiguity=len(family)>1,
                               observed_box=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())])
                    if match >= .65 and match-rival >= .03:
                        row["status"] = "verified"
                        row["observed_rest"] = expected
                        if len(family)>1:
                            orientation = _rectangular_rest_orientation(body["box"], rails[staff])
                            row["orientation_evidence"] = orientation
                            observed = orientation["observed_rest"]
                            row["type_ambiguity"] = observed is None
                            row["observed_rest"] = observed
                            if observed is None:
                                row.update(status="ambiguous", reason="Rectangular rest edges do not establish hanging/sitting identity on the measured staff grid")
                            elif observed != expected:
                                row.update(status="mismatch", reason=f"Measured staff-relative contour identifies {observed} instead of written {expected}")
                                failures.append(f"{key} {identity}: {row['reason']}")
                        dots = _rest_dot_evidence(marks, body["box"], event["dots"], gap)
                        row["dot_evidence"] = dots
                        if dots["status"] != "verified" and row["status"] != "mismatch":
                            row.update(status=dots["status"], reason=dots["reason"])
                            failures.append(f"{key} {identity}: {row['reason']}")
                        if row["status"] == "verified":
                            row["placement_evidence"] = _rest_placement_evidence(
                                body, glyphs["rest_"+expected], delta, suppressed_ink, rails, staff,
                                note_type=expected)
                    else:
                        ranked=sorted(scores.items(),key=lambda kv:kv[1],reverse=True)
                        winner,winning_score=ranked[0]
                        winner_family=("whole","half") if winner in ("whole","half") else (winner,)
                        competitor=max((v for k,v in scores.items() if k not in winner_family),default=0)
                        if winner not in family and winning_score>=.65 and winning_score-competitor>=.03:
                            row.update(status="mismatch",observed_rest=winner,
                                       reason=f"isolated contour identifies {winner} instead of written {expected}")
                        else:
                            # Partial occlusion cannot establish a wrong glyph.
                            row.update(status="unverified",reason="occluded or inseparable rest contour")
                        row["ranked"]=ranked[:3]
                        failures.append(f"{key} {identity}: {row['reason']} ({match:.3f}, rival {rival:.3f})")
            except (ValueError, OSError) as exc:
                row.update(status="unverified",reason=str(exc))
                failures.append(f"{key} {identity}: {exc}")
            coverage[row["status"]] += 1
            measured.append(row)
    for beat, candidates in identity_deltas.items():
        shared = set()
        for index, (_row, pixels) in enumerate(candidates):
            for other_index in range(index):
                other_pixels = candidates[other_index][1]
                if np.intersect1d(pixels, other_pixels, assume_unique=True).size:
                    shared.update((index, other_index))
        for index in sorted(shared):
            row = candidates[index][0]
            if row["status"] not in ("verified", "ambiguous"):
                continue
            coverage[row["status"]] -= 1
            row.update(status="ambiguous", reason=
                       "Same-frame rest interventions share changed pixels; source identities are inseparable")
            row["placement_evidence"].update(status="ambiguous", reason=row["reason"])
            coverage["ambiguous"] += 1
            failures.append(f"{beat} {row['source_id']}: {row['reason']}")
    placement_coverage = dict(expected=len(written), **{status:sum(
        r["placement_evidence"]["status"] == status for r in measured)
        for status in ("verified", "ambiguous", "unsupported", "unverified", "mismatch")})
    return {"passed":not failures, "complete":coverage["verified"] == len(written),
            "written_active_rests":len(written),
            "image_rest_glyphs_verified":coverage["verified"],
            "intrinsically_indistinguishable_half_whole":sum(
                r["status"] == "ambiguous" and r.get("type_ambiguity", False) for r in measured),
            "coverage":coverage, "failures":failures, "measured":measured,
            "placement_coverage":placement_coverage,
            "placement_complete":placement_coverage["verified"] == len(written),
            "scope":"visible isolated contour against external Verovio font; full-frame repeat and restore invariance",
            "limitation":"Glyph and placement coverage are separate; placement proves only a bounded readable staff-grid lane and local bright-ink clearance, not the intended voice lane or global extra-symbol absence; touching/occluded dots and more than two dots remain nonverified"}
