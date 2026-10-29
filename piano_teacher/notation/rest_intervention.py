"""Independent rest proof through reversible full-frame suppression controls.

One call owns source-rest selection, repeat/restore checks, changed-pixel
identity claims, and separate contour/placement report accounting."""
from __future__ import annotations

import json
from PIL import Image
from collections import defaultdict
from pathlib import Path
from .pixel_context import rectangular_rest_orientation
from .pixel_ink import bright
from .pixel_proof import detect_staff_lines
from .proof import read_written_score
from .reference_font import reference_glyphs
from .rest_contours import compare_isolated_masks, partition_rest_body_dots, rest_delta_parts, rest_dot_evidence, rest_template_mask
from .rest_placement_pixels import rest_placement_evidence


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
                parts = rest_delta_parts(delta, gap)
                body, marks = parts[0], parts[1:]
                expected = event["note_type"]
                if "rest_"+expected in glyphs:
                    body, marks = partition_rest_body_dots(body, marks,
                        glyphs["rest_"+expected], gap, event["dots"])
                    # Absolute RGB deltas can also contain dark ink ADDED by
                    # a corrupt control. Genuine removed dots must not supply
                    # the visibility witness for an absent rest body.
                    x0,y0,x1,y1 = body["box"]
                    removed_body = body["mask"] & visible_removed[y0:y1+1,x0:x1+1]
                    removed_match = compare_isolated_masks(removed_body,
                        rest_template_mask(glyphs["rest_"+expected],gap))
                    row["visible_removed_body_match"] = round(removed_match,4)
                # Font expectation is read independently of fixture assets.
                scores = {name.removeprefix("rest_"):round(compare_isolated_masks(
                    body["mask"], rest_template_mask(glyph,gap)),4)
                    for name,glyph in glyphs.items() if name.startswith("rest_")}
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
                            orientation = rectangular_rest_orientation(body["box"], rails[staff])
                            row["orientation_evidence"] = orientation
                            observed = orientation["observed_rest"]
                            row["type_ambiguity"] = observed is None
                            row["observed_rest"] = observed
                            if observed is None:
                                row.update(status="ambiguous", reason="Rectangular rest edges do not establish hanging/sitting identity on the measured staff grid")
                            elif observed != expected:
                                row.update(status="mismatch", reason=f"Measured staff-relative contour identifies {observed} instead of written {expected}")
                                failures.append(f"{key} {identity}: {row['reason']}")
                        dots = rest_dot_evidence(marks, body["box"], event["dots"], gap,
                                                  visible_removed=visible_removed)
                        row["dot_evidence"] = dots
                        if dots["status"] != "verified" and row["status"] != "mismatch":
                            row.update(status=dots["status"], reason=dots["reason"])
                            failures.append(f"{key} {identity}: {row['reason']}")
                        if row["status"] == "verified":
                            if removed_match < .65:
                                raise ValueError("Rest body lacks an independently matching removed visible pale contour")
                            row["placement_evidence"] = rest_placement_evidence(
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
            "limitation":"Glyph and placement coverage are separate; placement proves only a bounded readable staff-grid lane and local bright-ink clearance, not the intended voice lane or global extra-symbol absence; touching/occluded dots and more than three dots remain nonverified"}
