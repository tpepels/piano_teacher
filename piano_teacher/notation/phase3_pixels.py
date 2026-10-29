"""Independent notehead positions and equal-time translation in retained PNGs.

Written expectations come from MusicXML; photographed rails, silhouettes and
translation supply evidence. The public rest detector remains available here
and has a separate full-frame intervention owner."""
from __future__ import annotations

import math
from PIL import Image
from collections import defaultdict
from pathlib import Path
from .pixel_context import clef_at, ledger_context_rows
from .pixel_ink import bright
from .pixel_motion import horizontal_dice
from .pixel_proof import detect_staff_lines, expected_y
from .proof import read_written_score
from .raster_matching import match_glyph as _match_glyph, glyph_search_components, match_glyphs_joint, photographed_playhead_columns
from .reference_font import reference_glyphs
from .rest_intervention import verify_all_rest_pixels


__all__ = ("verify_all_notehead_pixels", "verify_all_rest_pixels",
           "verify_scroll_pixels", "verify_translation_sequence")


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
        alternatives = horizontal_dice(a, b, limit)
        best = max((dice, -abs(shift), shift) for dice, shift in alternatives)
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
                ledger_rows=ledger_context_rows(raster,staves[staff],written,notes)
                pitches=sorted([
                    (expected_y(staves[staff],note["spelling"],
                        clef_at(written,note["index"],staff)),note)
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
                    unisons=[n for y,n in pitches if n is not note and abs(y-target)<.001]
                    displaced_group = displaced_group or any(n['voice']!=note['voice'] for n in unisons)
                    x_search=range(-32,33) if displaced_group else range(-16,17)
                    def family(n):
                        return n['note_type'] if n['note_type'] in ('whole','half') else 'black'
                    # Equal compatible heads may genuinely be shared. A
                    # hollow/filled pair, or equal heads explicitly stemmed
                    # the same way, requires distinct actual contour owners.
                    shareable=any(family(n)==family(note) and not (
                        note.get('stem') in ('up','down') and n.get('stem')==note['stem'])
                        for n in unisons)
                    requests.append(dict(note=note,glyph=glyphs[glyph],name=glyph,
                        gap=staves[staff].gap,origin_y=target,dxs=x_search,
                        alternatives=tuple((name,glyphs[name]) for name in ("head_black","head_half","head_whole") if name!=glyph),
                        background_rows=ledger_rows if glyph!="head_black" else (),
                        occlusion_columns=occlusion_columns,
                        unison=shareable))
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
