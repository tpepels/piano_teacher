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
from .raster_matching import glyph_search_components, match_glyphs_joint
from .reference_font import reference_glyphs


def _clef_at(reference, bar: int, hand: str):
    matches=[(at,sign,line,octave) for at,h,sign,line,octave in reference.clefs
             if h==hand and at<=bar]
    if not matches:
        raise ValueError(f"No explicit clef for {hand} in source window")
    _i,sign,line,octave=max(matches,key=lambda e:e[0])
    return sign,line,octave


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
        xpos=round(image.width*.42)
        requests=[]
        for staff,notes in hands.items():
            try:
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
            if len(group)>1 and not any(r["unison"] for r in group):
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
                        isolated_match=round(assigned["isolated_score"],3))
                else:
                    score=_match_glyph(raster,request["glyph"],request["gap"],
                        xpos,request["origin_y"],centered=True,
                        dxs=request["dxs"],dys=request["dys"])
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
                elif len(group)>1 and joint is None:
                    status="ambiguous"
                    evidence["reason"]="No bounded joint assignment with sufficient disjoint notehead ink"
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


def verify_all_rest_pixels(generated_xml: str, folder: Path,
                           *, hand: str = "both") -> dict:
    """Check rest contours using a reversible, full-frame image intervention.

    No-op and restored frames must equal the source framebuffer. Suppression
    may only remove ink in a bounded rest region. Source duration remains
    ambiguous for the indistinguishable half/whole rectangular family.
    Missing/contaminated captures are failed evidence, not musical defects.
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
                   "status":"unverified"}
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
                # Font expectation is read independently of fixture assets.
                scores = {name.removeprefix("rest_"):round(_compare_isolated_masks(
                    delta, _rest_template_mask(glyph,gap)),4)
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
                        row["status"] = "ambiguous" if len(family)>1 else "verified"
                        if row["status"] == "ambiguous":
                            row["reason"] = "half/whole contour family; value and displaced voice lane not distinguishable"
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
            coverage["ambiguous"] += 1
            failures.append(f"{beat} {row['source_id']}: {row['reason']}")
    return {"passed":not failures, "complete":coverage["verified"] == len(written),
            "written_active_rests":len(written),
            "image_rest_glyphs_verified":coverage["verified"],
            "intrinsically_indistinguishable_half_whole":sum(
                r["status"] == "ambiguous" and r.get("type_ambiguity", False) for r in measured),
            "coverage":coverage, "failures":failures, "measured":measured,
            "scope":"visible isolated contour against external Verovio font; full-frame repeat and restore invariance",
            "limitation":"contour proof does not establish rest placement, dots, half/whole identity or absence of overlaps"}
