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


def glyph_search_components(requests, *, dys):
    """Partition searches whose vertical pixel rectangles can overlap.

    Include the full original registration range, even for nonadjacent
    pitches and different staves. Separate components cannot reuse ink.
    """
    dys=tuple(dys)
    intervals=[]
    for i,request in enumerate(requests):
        b=request["glyph"]["bounds"]
        gap=request["gap"]
        height=max(1,round(b[3]*gap/250))
        ys=[round(request["origin_y"]+b[1]*gap/250+dy)
            for dy in request.get("dys",dys)]
        if ys:
            intervals.append((min(ys),max(ys)+height,i))
    groups=[]
    bottom=-1
    for top,end,i in sorted(intervals):
        if not groups or top>=bottom:
            groups.append([])
        groups[-1].append(i)
        bottom=max(bottom,end)
    return groups


def _joint_candidates(pixels, request, origin_x, dys, minimum):
    """Keep threshold-passing original Dice candidates and their actual ink."""
    glyph=request["glyph"]
    gap=request["gap"]
    b=glyph["bounds"]
    width=max(1,round(b[2]*gap/250))
    height=max(1,round(b[3]*gap/250))
    template=_outline(glyph["svg"],width,height)
    left=origin_x-b[2]*gap/250/2
    top=request["origin_y"]+b[1]*gap/250
    xs=sorted({round(left+dx) for dx in request["dxs"]
               if 0<=round(left+dx)<pixels.shape[1]-width})
    ys=sorted({round(top+dy) for dy in request.get("dys",dys)
               if 0<=round(top+dy)<pixels.shape[0]-height})
    if not xs or not ys:
        return []
    region=pixels[ys[0]:ys[-1]+height,xs[0]:xs[-1]+width]
    windows=np.lib.stride_tricks.sliding_window_view(region,(height,width))
    blocks=windows[np.array(ys)[:,None]-ys[0],np.array(xs)[None,:]-xs[0]]
    intersections=blocks & template
    denominators=int(template.sum())+np.count_nonzero(blocks,axis=(-2,-1))+1e-9
    scores=2*np.count_nonzero(intersections,axis=(-2,-1))/denominators
    candidates=[]
    for iy,ix in np.argwhere(scores>=minimum):
        yy,xx=np.nonzero(intersections[iy,ix])
        support=frozenset(((yy+ys[iy])*pixels.shape[1]+xx+xs[ix]).tolist())
        candidates.append(dict(x=xs[ix],y=ys[iy],score=float(scores[iy,ix]),
            denominator=float(denominators[iy,ix]),support=support))
    return sorted(candidates,key=lambda row:-row["score"])


def match_glyphs_joint(pixels, requests, origin_x, *, dys, minimum=.79,
                      max_heads=6, max_search_nodes=20000):
    """Find a bounded all-head assignment with disjoint observed support.

    Requests contain authentic glyphs, image-measured gaps, source-derived
    Y positions and the existing horizontal search ranges. Both candidate
    Dice and final Dice must pass the unchanged threshold. Every pixel
    supporting multiple chosen masks is discarded from *all* identities;
    neither the complete expected mask nor the observed-ink denominator is
    reduced. Thus joint scores can only be stricter than isolated scores.

    Return None when any head lacks evidence or the search bound is hit.
    The returned support sets are actual image pixel indices, pairwise
    disjoint, and can be independently checked by callers/tests. This
    deliberately does not attempt to separate inseparable contours.
    """
    if not requests or len(requests)>max_heads:
        return None
    dys=tuple(dys)
    candidates=[_joint_candidates(pixels,r,origin_x,dys,minimum) for r in requests]
    if any(not rows for rows in candidates):
        return None
    order=sorted(range(len(requests)),key=lambda i:len(candidates[i]))
    visited=0

    def search(selected, exclusive, union):
        nonlocal visited
        if len(selected)==len(order):
            result=[None]*len(order)
            for i,row,ink in zip(order,selected,exclusive):
                result[i]=dict(x=row["x"],y=row["y"],support=ink,
                    isolated_score=row["score"],score=2*len(ink)/row["denominator"])
            return result
        for row in candidates[order[len(selected)]]:
            if visited>=max_search_nodes:
                return None
            visited+=1
            ink=row["support"]-union
            if 2*len(ink)/row["denominator"]<minimum:
                continue
            remaining=[old-row["support"] for old in exclusive]
            if any(2*len(old)/chosen["denominator"]<minimum
                   for old,chosen in zip(remaining,selected)):
                continue
            result=search(selected+[row],remaining+[ink],union|row["support"])
            if result is not None:
                return result
        return None

    return search([],[],frozenset())
