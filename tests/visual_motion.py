"""Physical scroll and admission witnesses for the rendered-frame verifier."""
import math
import numpy as np


def scroll_velocity(before, after, metrics):
    # Check actual rendered world displacement independently of the
    # motion compensation and the timeline's (possibly faulty) rest rate.
    if "time_ms" not in before or "time_ms" not in after:
        return None
    dt = max(0.0, after["time_ms"]-before["time_ms"],
             after.get("sample_ms",0)-before.get("sample_ms",0))/1000.0
    delta = float(after["world"])-float(before["world"])
    if not math.isfinite(delta) or not math.isfinite(dt):
        return "invalid_scroll_motion"
    # Authored sounding tempo changes are legitimate. Never take the
    # effective rate of a Free/rest segment as the permissible speed.
    rates = []
    for state in (before,after):
        rates.extend([float(state.get("bpm") or 0)])
        if state.get("mode") == "learn" or state.get("phase") == "count_in":
            rates.extend([80.0,float(state.get("target_bpm") or 0)])
        timeline = state.get("timeline") or {}
        for segment in timeline.get("segments",[]):
            if segment.get("kind") == "take":
                for span in segment.get("spans",[]):
                    rates.extend(float(rate) for rate in span[1:3])
    ceiling = max([1.0,*rates])
    # 20% allowance for bounded tempo easing and a small sampling margin.
    limit = ceiling*1.20*dt/60.0 + .025
    metrics.update(world_delta_beats=delta,scroll_limit_beats=limit,
                   scroll_bpm=delta*60/dt if dt > 0 else None,
                   scroll_reference_bpm=ceiling)
    if delta < -.02:
        return "backward_score_motion"
    if delta > limit:
        return "excessive_scroll_velocity"
    return None


def _records(meta):
    return {(layer["id"],strip["id"]):(layer,strip)
            for layer in meta.get("layers",[])
            for strip in layer.get("strips",[])}


def strip_witnesses(before, after, shape, crop_x, width):
    """Allow only additions on newly admitted future ink; protect old ink."""
    allowed = np.zeros(shape,dtype=bool)
    old,new = _records(before),_records(after)
    layers = {layer["id"]:layer for layer in after.get("layers",[])}
    for key,(_,strip) in new.items():
        if key in old or not (strip["visible"] and strip["authorized"]
                              and strip["admitted_inside"] and strip["future"]):
            continue
        lo = max(0,math.floor(strip["left"]*width)-crop_x-2)
        hi = min(shape[1],math.ceil(strip["right"]*width)-crop_x+2)
        if hi > lo:
            allowed[:,lo:hi] = True
    retired = []
    for key,(layer,strip) in old.items():
        if not strip["visible"] or (key in new and new[key][1]["visible"]):
            continue
        # New capture records every layer, even when the entire layer
        # disappeared. Old captures cannot provide this witness.
        if not (after.get("strip_witness_version") == 1 or
                any("strips" in item for item in after.get("layers",[]))):
            continue
        successor = layers.get(layer["id"])
        delta = (successor["world"]-layer["world"] if successor is not None
                 else after["world"]-before["world"])
        right = strip["right"]-delta*layer["density"]
        left = strip["left"]-delta*layer["density"]
        if right > strip["gutter"]+2/width and left < (crop_x+shape[1])/width:
            retired.append(str(key))
    return allowed,retired
