"""Efficient pixel comparison for the independent whole-piece image oracle."""
import math
import numpy as np

from .symbol_pixel_proof import _outline


def photographed_playhead_columns(image):
    """Only a narrow, long colored rule may hide head contour pixels."""
    rgb=np.asarray(image.convert('RGB')).astype(np.int16)
    colored=(rgb[:,:,1]-rgb[:,:,0]>30)&(rgb[:,:,2]-rgb[:,:,0]>15)
    columns=np.flatnonzero(colored.sum(axis=0)>image.height*.35)
    if not 0<len(columns)<=4 or columns[-1]-columns[0]>=4:
        return ()
    # The rule does not necessarily span the whole framebuffer. Only its
    # actually colored pixels may hide contour; never censor that X above
    # or below the photographed stroke.
    return {int(x):frozenset(int(y) for y in np.flatnonzero(colored[:,x])) for x in columns}


def _comparison(blocks, template, xs, ys, background_rows=(), occlusion_columns=()):
    intersections=blocks & template
    expected=np.full((len(ys),1),int(template.sum()))
    observed=np.count_nonzero(blocks,axis=(-2,-1))
    if background_rows or occlusion_columns:
        expected=np.broadcast_to(expected,observed.shape).copy()
        # Independently identified horizontal ledger ink is allowed behind
        # a hollow head. It supplies NO contour support and never replaces
        # missing head ink. Compare the independently visible contour around
        # that occluder; at least 75% of the full head must remain measurable.
        for iy,y in enumerate(ys):
            for ix,x in enumerate(xs):
                local=sorted({row-y for row,left,right in background_rows
                              if 0<=row-y<template.shape[0] and left<=x and right>=x+template.shape[1]})
                hidden=np.zeros(template.shape,dtype=bool)
                hidden[local,:]=True
                if np.count_nonzero(template & hidden)>.25*int(template.sum()):
                    hidden[:]=False
                with_columns=hidden.copy()
                for column,rows in (occlusion_columns.items() if isinstance(occlusion_columns,dict) else ()):
                    if 0<=column-x<template.shape[1]:
                        with_columns[:,column-x]=[y+dy in rows for dy in range(template.shape[0])]
                if np.count_nonzero(template & with_columns)<=.25*int(template.sum()):
                    hidden=with_columns
                hidden_expected=np.count_nonzero(template & hidden)
                if hidden.any() and hidden_expected<=.25*int(template.sum()):
                    intersections[iy,ix][hidden]=False
                    expected[iy,ix]-=hidden_expected
                    observed[iy,ix]-=np.count_nonzero(blocks[iy,ix] & hidden)
    return intersections,expected,observed


def match_glyph(pixels, glyph, gap, origin_x, origin_y, *, centered, dxs, dys,
                background_rows=(), occlusion_columns=()):
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
    matches,expected,observed=_comparison(blocks,template,xs,ys,background_rows,occlusion_columns)
    intersection=np.count_nonzero(matches,axis=(-2,-1))
    return float(np.max(2*intersection/(expected+observed+1e-9)))


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
    intersections,expected,observed=_comparison(blocks,template,xs,ys,request.get("background_rows",()),request.get('occlusion_columns',()))
    denominators=expected+observed+1e-9
    visible_expected=np.broadcast_to(expected,observed.shape)
    scores=2*np.count_nonzero(intersections,axis=(-2,-1))/denominators
    candidates=[]
    for iy,ix in np.argwhere(scores>=minimum):
        rivals=[]
        for name,alternative in request.get("alternatives",()):
            rivals.append((match_glyph(pixels,alternative,gap,
                xs[ix]+b[2]*gap/500,ys[iy]-b[1]*gap/250,
                centered=True,dxs=range(-1,2),dys=range(-1,2),
                background_rows=request.get("background_rows",()),
                occlusion_columns=request.get('occlusion_columns',())),name))
        runner=max(rivals,default=(0.,None))
        if rivals and float(scores[iy,ix])-runner[0]<.05:
            continue
        yy,xx=np.nonzero(intersections[iy,ix])
        support=frozenset(((yy+ys[iy])*pixels.shape[1]+xx+xs[ix]).tolist())
        candidates.append(dict(x=xs[ix],y=ys[iy],score=float(scores[iy,ix]),
            denominator=float(denominators[iy,ix]),support=support,
            visible_reference_pixels=int(visible_expected[iy,ix]),
            reference_pixels=int(template.sum()),
            family_runner_up=runner[0],family_margin=float(scores[iy,ix])-runner[0]))
    return sorted(candidates,key=lambda row:-row["score"])


def match_glyphs_joint(pixels, requests, origin_x, *, dys, minimum=.79,
                      max_heads=6, max_search_nodes=20000):
    """Find a bounded all-head assignment with disjoint observed support.

    Requests contain authentic glyphs, image-measured gaps, source-derived
    Y positions and the existing horizontal search ranges. Both candidate
    Dice and final Dice must pass the unchanged threshold. Every observed
    pixel belongs to at most one head, including where genuine chord heads
    touch. Neither expected mask nor observed denominator is reduced for
    shared head ink. A request can separately identify source-required ledger rows;
    those occluders supply no head support to either isolated or joint scores.
    Thus joint scores can only be stricter than isolated scores.

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

    def assign(selected):
        # Capacitated bipartite matching: a head needs enough actual pixels
        # for the same Dice threshold, and a pixel has capacity one. Throwing
        # touching ink away from BOTH heads falsely rejects real seconds;
        # counting it for BOTH could certify a missing or duplicated head.
        owned=[set() for _ in selected]
        owners={}
        def claim(index, visited):
            visited.add(index)
            support=selected[index]["support"]
            free=support-owners.keys()
            if free:
                pixel=min(free)
            else:
                pixel=None
                for candidate in support:
                    previous=owners[candidate]
                    if previous not in visited and claim(previous,visited):
                        owned[previous].remove(candidate)
                        pixel=candidate
                        break
                if pixel is None:
                    return False
            owners[pixel]=index
            owned[index].add(pixel)
            return True
        for i,row in enumerate(selected):
            needed=math.ceil(minimum*row["denominator"]/2-1e-9)
            for _ in range(needed):
                if not claim(i,set()):
                    return None
        for i,row in enumerate(selected):
            for pixel in row["support"]-owners.keys():
                owners[pixel]=i
                owned[i].add(pixel)
        return owned

    def search(selected, union):
        nonlocal visited
        if len(selected)==len(order):
            exclusive=assign(selected)
            if exclusive is None:
                return None
            result=[None]*len(order)
            for i,row,ink in zip(order,selected,exclusive):
                result[i]=dict(x=row["x"],y=row["y"],support=ink,
                    isolated_score=row["score"],score=2*len(ink)/row["denominator"],
                    visible_reference_pixels=row['visible_reference_pixels'],
                    reference_pixels=row['reference_pixels'])
            return result
        for row in candidates[order[len(selected)]]:
            if visited>=max_search_nodes:
                return None
            visited+=1
            combined=union|row["support"]
            choices=selected+[row]
            if sum(math.ceil(minimum*c["denominator"]/2-1e-9) for c in choices)>len(combined):
                continue
            result=search(choices,combined)
            if result is not None:
                return result
        return None

    return search([],frozenset())
