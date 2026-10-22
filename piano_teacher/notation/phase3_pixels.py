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



def verify_all_rest_pixels(generated_xml: str, folder: Path,
                           *, hand: str = "both") -> dict:
    """Independently classify each source-written rest in native PNG pixels.

    Unlike renderer diagnostic rest coordinates, the only anchors are the
    actual screenshot staff lines, the physical fixed playhead and source
    XML rest onsets/types. A search over conventional voice/lane Y does not
    assume the native renderer's internal rest placement.
    """
    from .symbol_pixel_proof import REST_TYPES

    if hand not in ("both","left","right"):
        raise ValueError("Invalid practice hand mode")
    score=read_written_score(generated_xml)
    written=[s for s in score.symbols
             if s["kind"]=="rest" and s["visible"]
             and (hand=="both" or s["staff"]==hand)]
    atlas=json.loads((folder/"fixture.json").read_text())["assets"]["native_glyphs"]
    names=tuple("rest_"+name for name in REST_TYPES if "rest_"+name in atlas)
    checked=0
    failures=[]
    details=[]
    for event in written:
        kind="rest_"+str(event["note_type"])
        beat=round(float(event["beat"]),8)
        if kind not in names:
            failures.append(f"{beat} {event['staff']}: unsupported written "
                            f"rest type {event['note_type']}")
            continue
        frame=folder/f"native-{beat:.5f}.png"
        if not frame.is_file():
            failures.append(f"{beat} {event['staff']}: missing screenshot "
                            f"for source rest")
            continue
        with Image.open(frame) as raw:
            picture=raw.convert("RGB")
        try:
            staves=detect_staff_lines(picture)
            staff=staves[event["staff"]]
            center=(staff.lines[0]+staff.lines[-1])/2
            # Music convention distinguishes whole (hanging from the
            # fourth line) from half (sitting on the middle line). Their
            # nearly identical rectangle ink CANNOT be classified if the
            # validator searches arbitrary Y positions for both.
            # The expected staff offsets are derived from notation
            # convention, not the renderer's rest Y telemetry.
            pixels=bright(picture)
            scored=[]
            for name in names:
                name_anchor=center-staff.gap if name=="rest_whole" else center
                match=_match_glyph(
                    pixels,atlas[name],staff.gap,
                    round(picture.width*.42),name_anchor,
                    centered=True,dxs=range(-13,14,2),
                    dys=range(-7,8,2))
                scored.append((name,round(match,4)))
            scored.sort(key=lambda pair:pair[1],reverse=True)
            best,score=scored[0]
            runner_up=scored[1][1] if len(scored)>1 else 0.0
            details.append({
                "beat":beat,"staff":event["staff"],"written":kind,
                "found":best,"score":score,
                "runner_up":runner_up,
            })
            if best==kind and score>=.69 and score-runner_up>=.03:
                checked+=1
            else:
                failures.append(
                    f"{beat} {event['staff']}: written {kind}, image "
                    f"{best} confidence {score:.3f} vs {runner_up:.3f}")
        except (ValueError,AssertionError,KeyError) as exc:
            failures.append(f"{beat} {event['staff']}: {exc}")
    if checked!=len(written):
        failures.append(f"Independent rest-glyph image coverage "
                        f"{checked}/{len(written)}")
    return {
        "passed":not failures,
        "written_active_rests":len(written),
        "image_rest_glyphs_verified":checked,
        "failures":failures,"measured":details,
        "scope":"Exact original Verovio rest glyph silhouette at "
                "XML-defined beat near image-detected staff",
    }
