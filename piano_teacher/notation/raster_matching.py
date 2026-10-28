"""Efficient pixel comparison for the independent whole-piece image oracle."""
import math
from collections import defaultdict, deque
import numpy as np

from .pixel_ink import rasterize_outline


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
    template=rasterize_outline(glyph["svg"],width,height)
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
    template=rasterize_outline(glyph["svg"],width,height)
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
                      max_heads=6, max_search_nodes=20000,
                      max_assignment_work=500000, diagnostics=None):
    """Find authentic heads with disjoint actual pixel ownership.

    Candidate/final Dice, family margin and visible-contour requirements are
    unchanged. Check the capacity of EVERY head subset, not just total ink.
    Allocate through pixel-membership classes using integer max flow, never
    recursive per-pixel augmentation. Placement, candidate search and capacity
    work all have explicit bounds; exhaustion returns None, never partial proof.
    """
    visited=work=0
    exhausted=False
    if diagnostics is not None:
        diagnostics.update(exhausted=False,work_used=0,search_nodes=0)

    def charge(amount=1):
        nonlocal work,exhausted
        work+=amount
        if work>max_assignment_work:
            exhausted=True
        return not exhausted

    def finish(result):
        if diagnostics is not None:
            diagnostics.update(exhausted=exhausted,work_used=work,
                               search_nodes=visited)
        return result

    if not requests or len(requests)>max_heads:
        return None
    dys=tuple(dys)
    placements=sum(len(r['dxs'])*len(r.get('dys',dys)) for r in requests)
    if placements>8192:
        exhausted=True
        return finish(None)
    if not charge(placements):
        return finish(None)
    candidates=[_joint_candidates(pixels,r,origin_x,dys,minimum) for r in requests]
    if any(not rows for rows in candidates):
        return finish(None)
    # Compact actual pixel IDs: bitset size depends on observed candidates,
    # not framebuffer dimensions. Expected/occluded pixels supply no capacity.
    coordinates={}
    masks={}
    for rows in candidates:
        for row in rows:
            support=row['support']
            if support not in masks:
                if not charge(len(support)):
                    return finish(None)
                mask=0
                for pixel in support:
                    if pixel not in coordinates:
                        coordinates[pixel]=len(coordinates)
                    mask |= 1<<coordinates[pixel]
                masks[support]=mask
    order=sorted(range(len(requests)),key=lambda i:len(candidates[i]))

    def assign(selected):
        # Pixels eligible for the same subset of heads form ONE capacity
        # bucket. There are at most 2**heads-1 such buckets, regardless of ink.
        membership={}
        for i,row in enumerate(selected):
            if not charge(len(row['support'])):
                return None
            for pixel in row['support']:
                membership[pixel]=membership.get(pixel,0) | (1<<i)
        buckets=defaultdict(list)
        for pixel,mask in membership.items():
            buckets[mask].append(pixel)
        groups=list(buckets.items())
        first_head=1+len(groups)
        sink=first_head+len(selected)
        graph=[[] for _ in range(sink+1)]

        def edge(a,b,capacity):
            forward=[b,capacity,len(graph[b])]
            reverse=[a,0,len(graph[a])]
            graph[a].append(forward)
            graph[b].append(reverse)
            return forward

        allocations=[]
        for index,(mask,ink) in enumerate(groups):
            edge(0,index+1,len(ink))
            allocations.append([(i,edge(index+1,first_head+i,len(ink)))
                for i in range(len(selected)) if mask & (1<<i)])
        required=[math.ceil(minimum*row['denominator']/2-1e-9) for row in selected]
        for i,needed in enumerate(required):
            edge(first_head+i,sink,needed)
        remaining=sum(required)
        while remaining:
            parents={0:None}
            pending=deque([0])
            while pending and sink not in parents:
                node=pending.popleft()
                for index,link in enumerate(graph[node]):
                    if not charge():
                        return None
                    target,capacity,_=link
                    if capacity and target not in parents:
                        parents[target]=(node,index)
                        pending.append(target)
            if sink not in parents:
                return None
            amount=remaining
            node=sink
            while node:
                previous,index=parents[node]
                amount=min(amount,graph[previous][index][1])
                node=previous
            node=sink
            while node:
                previous,index=parents[node]
                link=graph[previous][index]
                link[1]-=amount
                graph[node][link[2]][1]+=amount
                node=previous
            remaining-=amount
        owned=[set() for _ in selected]
        for (_,ink),links in zip(groups,allocations):
            at=0
            for i,link in links:
                count=len(ink)-link[1]
                owned[i].update(ink[at:at+count])
                at+=count
            owned[links[0][0]].update(ink[at:])
        return owned

    def search(selected, subsets):
        nonlocal visited,exhausted
        if len(selected)==len(order):
            exclusive=assign(selected)
            if exclusive is None:
                return None
            result=[None]*len(order)
            for i,row,ink in zip(order,selected,exclusive):
                result[i]=dict(x=row['x'],y=row['y'],support=ink,
                    isolated_score=row['score'],score=2*len(ink)/row['denominator'],
                    visible_reference_pixels=row['visible_reference_pixels'],
                    reference_pixels=row['reference_pixels'])
            return result
        for row in candidates[order[len(selected)]]:
            if visited>=max_search_nodes:
                exhausted=True
                return None
            visited+=1
            mask=masks[row['support']]
            needed=math.ceil(minimum*row['denominator']/2-1e-9)
            added=[]
            # Previous subsets already passed. Only subsets containing the
            # new head need checking. An unrelated head's surplus cannot pay
            # a touching pair's deficit (the stalled corpus counterexample).
            for previous,capacity in [(0,0),*subsets]:
                if not charge():
                    return None
                combined=previous|mask
                demand=capacity+needed
                if combined.bit_count()<demand:
                    break
                added.append((combined,demand))
            else:
                result=search(selected+[row],subsets+added)
                if result is not None:
                    return result
                if exhausted:
                    return None
        return None

    return finish(search([],[]))
