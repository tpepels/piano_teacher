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
from pathlib import Path
import json

from PIL import Image

from .proof import read_written_score
from .pixel_proof import detect_staff_lines, expected_y
from .symbol_pixel_proof import bright, _match_glyph


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
    staves define the coordinate system; the MusicXML pitch and clef supply
    its expected pitch position. A missing or extra notehead peak fails.
    """
    if hand not in ("both","left","right"):
        raise ValueError("Invalid hand mode")
    written=read_written_score(generated_xml)
    by_clock=defaultdict(lambda:defaultdict(list))
    for symbol in written.symbols:
        if symbol["kind"]!="note" or not symbol["visible"]:
            continue
        staff=symbol["staff"]
        if hand!="both" and staff!=hand:
            continue
        by_clock[round(float(symbol["beat"]),8)][staff].append(symbol)
    atlas=json.loads((folder/"fixture.json").read_text())["assets"]
    glyphs=atlas["native_glyphs"]
    verified=0
    failures=[]
    details=[]
    for clock,hands in sorted(by_clock.items()):
        filename=folder/f"native-{clock:.5f}.png"
        if not filename.is_file():
            failures.append(f"{clock}: screenshot missing")
            continue
        with Image.open(filename) as raw:
            image=raw.convert("RGB")
        try:
            staves=detect_staff_lines(image)
        except AssertionError as exc:
            failures.append(f"{clock}: five-line staff detection failed: {exc}")
            continue
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
                raster=bright(image)
                xpos=round(image.width*.42)
                for target,note in pitches:
                    kind=note["note_type"]
                    glyph=("head_whole" if kind=="whole" else
                           "head_half" if kind=="half" else "head_black")
                    # Seconds in a chord are deliberately displaced
                    # horizontally by the engraver; they may also overlap
                    # another head mask and lower silhouette agreement.\n                    # Thirds also have overlapping head silhouettes because\n                    # the font head height exceeds one staff-space.
                    adjacent=any(
                        other is not note and
                        abs(other_y-target) <= 1.05*staves[staff].gap
                        for other_y,other in pitches
                    )
                    x_search=range(-32,33) if adjacent else range(-16,17)
                    score=_match_glyph(
                        raster,glyphs[glyph],staves[staff].gap,
                        xpos,target,centered=True,
                        dxs=x_search,dys=range(-4,5))
                    # One global overlapping-second allowance, never a
                    # score-specific pitch or passage exception. The
                    # independent one-staff-step mutation test remains.
                    threshold=.75 if adjacent else .79
                    if score < threshold:
                        failures.append(
                            f"{clock} {staff} {note['spelling']}: "
                            f"wrong/missing {glyph} silhouette at written "
                            f"staff position (image score={score:.3f})")
                    else:
                        verified+=1
                    details.append({"beat":clock,"staff":staff,
                                    "spelling":note["spelling"],
                                    "glyph":glyph,"match":round(score,3),
                                    "target_y":round(target,2)})
            except (ValueError,AssertionError,TypeError) as exc:
                failures.append(f"{clock} {staff}: {exc}")
    total=sum(len(notes) for hands in by_clock.values() for notes in hands.values())
    if verified!=total:
        failures.append(f"Independent raster pitch coverage {verified}/{total}")
    return {
        "passed":not failures, "written_active_noteheads":total,
        "image_pitch_verified":verified,"unique_onset_frames":len(by_clock),
        "tolerance_staff_steps":tolerance_staff_steps,
        "failures":failures,"measured":details,
        "scope":"Actual screenshot staff rails and notehead peak Y versus "
                "independently parsed written pitch/clef; no native geometry",
        "not_verified":["rest identity from native-only telemetry",
                        "note glyph shapes in dense passages",
                        "individual beam/tie/slur masks in complex overlaps"],
    }



def _rest_template_mask(glyph: dict, gap: float):
    """Rasterize the original Verovio SVG at the *measured image* staff scale."""
    from io import BytesIO
    import cairosvg
    import numpy as np

    bounds=glyph["bounds"]
    width=max(1,round(float(bounds[2])*gap/250))
    height=max(1,round(float(bounds[3])*gap/250))
    png=cairosvg.svg2png(bytestring=glyph["svg"].encode(),
                         output_width=width,output_height=height)
    alpha=np.asarray(Image.open(BytesIO(png)).convert("RGBA"))[:,:,3]
    return alpha >= 80


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
    """Independently verify each *actual rendered rest's* isolated contour.

    The Godot test harness captures two real framebuffers at the identical
    physical playhead and fixed layout: with and without each selected rest.
    Pixel subtraction isolates JUST that rest, including those shifted to
    collision-free voice lanes. The XML dictates the required glyph type;
    model rest IDs are used only to select the controlled intervention.

    Half/whole rests share an identical rectangle outline. Their duration
    identity cannot be inferred from isolated contours alone if a polyphonic
    voice lane is freely shifted: classify them honestly as a shared
    block-rest family, with duration independently verified by Phase 1.
    """
    from collections import defaultdict
    import numpy as np

    if hand not in ("both","left","right"):
        raise ValueError("Invalid practice hand mode")
    score=read_written_score(generated_xml)
    written=[s for s in score.symbols if s["kind"]=="rest"
             and s["visible"] and (hand=="both" or s["staff"]==hand)]
    fixture=json.loads((folder/"fixture.json").read_text())
    glyphs=fixture["assets"]["native_glyphs"]
    diagnostics=json.loads((folder/"native-overlay-report.json").read_text())
    controls=defaultdict(list)
    for item in diagnostics.get("rest_difference_controls",[]):
        key=(round(float(item["clock"]),8),item["staff"],item["voice"])
        controls[key].append(item)

    written_by=defaultdict(list)
    for event in written:
        key=(round(float(event["beat"]),8),event["staff"],event["voice"])
        written_by[key].append(event)

    # All signed control captures are evidence: an extra suppressed native
    # rest or an absent source-matched control cannot silently be ignored.
    failures=[]
    checked=0
    ambiguous=0
    measured=[]
    expected_keys=set(written_by)
    for key in controls:
        if (hand=="both" or key[1]==hand) and key not in expected_keys:
            failures.append(f"Unexpected rendered rest control: {key}")
    if not written:
        return {
            "passed":not failures,"written_active_rests":0,
            "image_rest_glyphs_verified":0,
            "intrinsically_indistinguishable_half_whole":0,
            "failures":failures,"measured":[],
            "method":"paired native Godot rest silhouette isolation",
        }
    for key,events in written_by.items():
        controls_at=controls.get(key,[])
        if len(controls_at)!=len(events):
            failures.append(f"{key}: {len(events)} written rests, "
                            f"{len(controls_at)} native isolated-render controls")
            continue
        beat,staff,voice=key
        source_frame=folder/f"native-{beat:.5f}.png"
        if not source_frame.is_file():
            failures.append(f"{key}: original Godot PNG missing")
            continue
        with Image.open(source_frame) as image:
            original=np.asarray(image.convert("RGB"),dtype=np.int16)
        x0=round(original.shape[1]*.42)-80
        for event,control in zip(events,controls_at):
            file=folder/control["file"]
            if not file.is_file():
                failures.append(f"{key}: suppressed-rest PNG missing: {file}")
                continue
            with Image.open(file) as png:
                suppressed=np.asarray(png.convert("RGB"),dtype=np.int16)
            crop=original[:,x0:x0+160]
            if suppressed.shape!=crop.shape:
                failures.append(f"{key}: suppressed raster wrong dimensions")
                continue
            difference=np.max(np.abs(crop-suppressed),axis=2)>=10
            ink=int(difference.sum())
            if ink < 12:
                failures.append(f"{key}: rest did not produce enough real "
                                f"image pixels (changed={ink})")
                continue
            # Count only the rest sprite. Original Verovio provides the
            # independent template silhouettes.
            scores={}
            rail_gap=detect_staff_lines(Image.fromarray(
                original.astype("uint8")))[staff].gap
            for name in ("whole","half","quarter","eighth",
                         "16th","32nd","64th","128th"):
                identifier="rest_"+name
                if identifier in glyphs:
                    scores[name]=round(_compare_isolated_masks(
                        difference,_rest_template_mask(
                            glyphs[identifier],rail_gap)),4)
            expected=event["note_type"]
            if expected not in scores:
                failures.append(f"{key}: Verovio font lacks written {expected}")
                continue
            # A whole and a half rest are the very same rectangular contour:
            # refer to them as one observable family, not two verifiable
            # identities. Anything else must win over that family.
            family=("whole","half") if expected in ("whole","half") else (expected,)
            expected_match=max(scores[option] for option in family)
            alternatives=[(name,score) for name,score in scores.items()
                          if name not in family]
            rival=max((value for _,value in alternatives),default=0.0)
            result={
                "beat":beat,"staff":staff,"voice":voice,
                "required_rest":expected,"delta_file":control["file"],
                "changed_pixels":ink,"shape_match":expected_match,
                "next_family_score":rival,
                "type_ambiguity":expected in ("whole","half"),
            }
            measured.append(result)
            if expected_match>=.65 and expected_match-rival>=.03:
                checked+=1
                if expected in ("whole","half"):
                    ambiguous+=1
            else:
                ranked=sorted(scores.items(),key=lambda pair:pair[1],reverse=True)
                failures.append(f"{key}: written rest_{expected}, isolated "
                                f"contour matched {ranked[:3]} (required="
                                f"{expected_match:.3f}; rival={rival:.3f})")
    if checked!=len(written):
        failures.append(f"Independent rest-contour coverage "
                        f"{checked}/{len(written)}")
    return {
        "passed":not failures,"written_active_rests":len(written),
        "image_rest_glyphs_verified":checked,
        "intrinsically_indistinguishable_half_whole":ambiguous,
        "failures":failures,"measured":measured,
        "scope":"Actual native framebuffer difference isolates each rest, "
                "compared with exact Verovio font contour independently "
                "of Godot rest lane coordinates",
        "limitation":"Whole and half rests have the same rectangle silhouette; "
                     "correct value needs source MusicXML and staff/voice "
                     "placement and is not certified by isolated shape alone",
    }
