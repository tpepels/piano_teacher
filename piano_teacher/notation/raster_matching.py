"""Efficient pixel comparison for the independent whole-piece image oracle."""
import numpy as np

from .symbol_pixel_proof import _outline


def match_glyph(pixels, glyph, gap, origin_x, origin_y, *, centered, dxs, dys):
    """Same bounded Dice search as the scalar oracle, evaluated in NumPy.

    This only changes execution cost. Bounds, rasterization, registration
    candidates, and scores are identical to the scalar pixel comparator.
    """
    bounds=glyph["bounds"]
    width=max(1,round(bounds[2]*gap/250))
    height=max(1,round(bounds[3]*gap/250))
    template=_outline(glyph["svg"],width,height)
    left=origin_x-(bounds[2]*gap/250/2 if centered else -bounds[0]*gap/250)
    top=origin_y+bounds[1]*gap/250
    xs=sorted({round(left+dx) for dx in dxs
               if 0<=round(left+dx)<pixels.shape[1]-width})
    ys=sorted({round(top+dy) for dy in dys
               if 0<=round(top+dy)<pixels.shape[0]-height})
    if not xs or not ys:
        return 0.0
    region=pixels[ys[0]:ys[-1]+height,xs[0]:xs[-1]+width]
    windows=np.lib.stride_tricks.sliding_window_view(region,(height,width))
    blocks=windows[np.array(ys)[:,None]-ys[0],np.array(xs)[None,:]-xs[0]]
    intersection=np.count_nonzero(blocks & template,axis=(-2,-1))
    observed=np.count_nonzero(blocks,axis=(-2,-1))
    return float(np.max(2*intersection/(int(template.sum())+observed+1e-9)))
