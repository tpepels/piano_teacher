"""Separate photographic translation procedures with their original policies.

horizontal_dice/frame_shift use positive displacement for leftward score
motion. register_translation returns the pixel displacement itself (negative
for leftward motion). Search ranges, margins, and signs remain distinct.
"""
import numpy as np

from .pixel_ink import bright


def horizontal_dice(a, b, limit):
    """Exact 2-D intersections at every allowed horizontal displacement.

    Repeated stems can rank a genuine translation below arbitrary column-
    projection shortlists. Row-preserving FFT correlation measures all shifts
    in bounded memory; rounding recovers integer binary-pixel intersections.
    """
    import numpy as np

    width = a.shape[1]
    size = 1 << (2*width-2).bit_length()
    fa = np.fft.rfft(a.astype(np.float64), n=size, axis=1)
    fb = np.fft.rfft(b.astype(np.float64), n=size, axis=1)
    intersections = np.rint(np.fft.irfft((fa*fb.conj()).sum(axis=0), n=size))
    first = np.r_[0, a.sum(axis=0).cumsum()]
    second = np.r_[0, b.sum(axis=0).cumsum()]
    result = []
    for shift in range(-limit, limit+1):
        low, high = max(0, shift), min(width, width+shift)
        other_low, other_high = max(0, -shift), min(width, width-shift)
        denominator = int(first[high]-first[low]+second[other_high]-second[other_low])
        result.append((2*max(0, int(intersections[shift % size]))/denominator
                       if denominator else 0., shift))
    return result


def frame_shift(first, second):
    """Measure actual score translation without consulting native geometry.

    Retain the motion oracle's .80 full-contour agreement and minimum ink.
    Every permitted translation uses actual two-dimensional contour evidence;
    repeated stems cannot exclude the true shift through a column shortlist.
    The wider search permits retained frames several beats apart. Competing
    translations with the same evidence do not establish a source clock.
    """
    if first.size != second.size:
        return None
    a, b = bright(first), bright(second)
    if min(int(a.sum()), int(b.sum())) < 24:
        return None
    measured = horizontal_dice(a, b, round(first.width*.75))
    score, shift = max(measured, key=lambda p: (p[0], -abs(p[1])))
    if score < .80 or any(s >= score-.02 and abs(x-shift) > 2 for s, x in measured):
        return None
    return dict(shift=shift, contour_agreement=score)


def register_translation(a, b, gap):
    """Measure horizontal score translation; require a unique 2D ink match."""
    if a.shape != b.shape:
        raise ValueError('Framebuffer dimensions differ')
    w = a.shape[1]
    left, right = round(w*.20), round(w*.96)
    a, b = a[:, left:right], b[:, left:right]
    col_a, col_b = a.sum(axis=0).astype(float), b.sum(axis=0).astype(float)
    n = a.shape[1]
    correlation = np.correlate(col_b, col_a, 'full')
    shifts = np.arange(1-n, n)
    correlation[np.abs(shifts) > n*.60] = -1
    candidates = []
    # Nearby subpixel phases are one registration, not independent rivals.
    for index in np.argsort(correlation)[::-1]:
        shift = int(shifts[index])
        if any(abs(shift-s) <= max(2, gap*.15) for _, s in candidates):
            continue
        lo, hi = max(0, -shift), min(n, n-shift)
        aa, bb = a[:, lo:hi], b[:, lo+shift:hi+shift]
        denominator = int(aa.sum()+bb.sum())
        dice = float(2*np.count_nonzero(aa & bb)/denominator) if denominator >= 80 else 0.
        candidates.append((dice, shift))
        if len(candidates) == 12:
            break
    candidates.sort(reverse=True)
    best, shift = candidates[0]
    margin = best-candidates[1][0]
    if best < .80 or margin < .04:
        raise ValueError(f'Ambiguous image translation (agreement={best:.3f}, margin={margin:.3f})')
    return shift, dict(pixels=shift, agreement=round(best, 4), margin=round(margin, 4))
