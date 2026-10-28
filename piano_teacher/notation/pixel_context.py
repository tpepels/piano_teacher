"""Source clefs and measured staff/ledger context for independent PNG probes.

Context limits a search or identifies allowed occluding ink; it never supplies
notehead support or substitutes for physical ledger evidence.
"""
import math

from .pixel_proof import expected_y


def clef_at(reference, bar: int, hand: str):
    matches=[(at,sign,line,octave) for at,h,sign,line,octave in reference.clefs
             if h==hand and at<=bar]
    if not matches:
        raise ValueError(f"No explicit clef for {hand} in source window")
    _i,sign,line,octave=max(matches,key=lambda e:e[0])
    return sign,line,octave


def ledger_context_rows(pixels, rail, written, notes):
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
        y=expected_y(rail,note["spelling"],clef_at(written,note["index"],note["staff"]))
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


def rectangular_rest_orientation(box: list[int], staff) -> dict:
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
