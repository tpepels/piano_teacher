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
import numpy as np

from PIL import Image

from .proof import read_written_score
from .pixel_proof import detect_staff_lines, expected_y, observed_notehead_ys
from .symbol_pixel_proof import bright, _match_note_template


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
    templates=atlas["native_note_templates"]
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
                pitches=sorted((
                    expected_y(staves[staff],note["spelling"],
                        _clef_at(written,note["index"],staff)),
                    note) for note in notes
                ,key=lambda pair:pair[0])
                # Hollow half/whole heads do not create the filled image-
                # width peaks used for quarter/eighth/chord notes. Verify
                # their full native image mask against Verovio reference.
                filled=[item for item in pitches
                        if item[1]["note_type"] not in {"half","whole"}]
                hollow=[item for item in pitches
                        if item[1]["note_type"] in {"half","whole"}]
                if filled:
                    measured=observed_notehead_ys(image,staff,staves[staff])
                    if len(measured)!=len(filled):
                        failures.append(f"{clock} {staff}: image filled-head count "
                                        f"{len(measured)} vs {len(filled)} "
                                        f"independently written filled heads")
                    else:
                        for (target,note),observed in zip(filled,measured):
                            steps=abs(observed-target)/(staves[staff].gap/2)
                            if steps>tolerance_staff_steps:
                                failures.append(
                                    f"{clock} {staff} {note['spelling']}: image y="
                                    f"{observed:.2f}, expected={target:.2f}; "
                                    f"{steps:.2f} staff steps")
                            else:
                                verified+=1
                            details.append({"beat":clock,"staff":staff,
                                            "spelling":note["spelling"],
                                            "observed_y":round(observed,2),
                                            "expected_y":round(target,2),
                                            "error_steps":round(steps,3),
                                            "head_type":"filled"})
                if hollow:
                    raster=bright(image)
                    xpos=round(image.width*.42)
                    for target,note in hollow:
                        kind=note["note_type"]
                        options=(("whole",) if kind=="whole"
                                 else ("half_up","half_down"))
                        score=max(_match_note_template(raster,templates[name],
                                  staves[staff].gap,xpos,target)
                                  for name in options)
                        if score < .66:
                            failures.append(f"{clock} {staff} {note['spelling']}: "
                                            f"missing hollow {kind} head at "
                                            f"written position (mask={score:.3f})")
                        else:
                            verified+=1
                        details.append({"beat":clock,"staff":staff,
                                        "spelling":note["spelling"],
                                        "score":round(score,3),
                                        "head_type":kind})
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
