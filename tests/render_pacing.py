"""Low-overhead real frame pacing review, without texture readback."""
import argparse
import json
import math
from pathlib import Path
import numpy as np
from midi_visual_probe import MidiProbeReview


def review(records, manifest, required_steps=()):
    failures, gaps, costs, steps = [], [], [], set()
    previous = None
    midi = MidiProbeReview()
    count = injected = 0
    armed = False
    fps = manifest.get("fps")
    if fps not in (30,60,120) or not manifest.get("pacing_only"):
        raise ValueError("Not a valid lightweight pacing capture")
    limit = min(100.,max(50.,3000/fps))
    for index,frame in enumerate(records):
        if frame["frame"] != index or frame["fps"] != fps:
            raise ValueError("Missing or mismatched pacing sample")
        count += 1
        if previous and frame["engine_frame"] != previous["engine_frame"]+1:
            raise ValueError("Missing real rendered frame")
        if not math.isfinite(frame["time_ms"]) or (previous and frame["time_ms"]<=previous["time_ms"]):
            raise ValueError("Invalid frame timestamp")
        if frame["screen"] != "practice":
            armed = False
        armed |= frame["ready"] and frame["screen"]=="practice"
        if armed:
            steps.add(frame["step"])
        if previous and armed and previous["screen"]=="practice":
            if any(e["kind"]=="injected_hitch" for e in frame.get("events",[])):
                injected += 1
            else:
                dt = frame["time_ms"]-previous["time_ms"]
                gaps.append(dt)
                costs.append(frame["capture_cost_ms"])
                if dt>limit:
                    failures.append({"reasons":["render_frame_hitch"],"frame":index,"step":frame["step"],
                                     "gap_ms":dt,"limit_ms":limit,"capture_cost_ms":costs[-1]})
        if armed:
            sample=dict(frame.get("midi_sample",{}))
            sample.update(time_ms=frame["time_ms"],events=frame.get("events",[]))
            reasons,metrics=midi.observe(sample)
            if reasons:
                failures.append({"reasons":reasons,"frame":index,"step":frame["step"],"metrics":metrics})
        previous=frame
    if count != manifest["frames"] or not manifest["success"]:
        raise ValueError("Incomplete pacing capture")
    summary={"fps":fps,"frames":count,"frame_samples":len(gaps),"injected_hitches":injected,"steps":sorted(steps)}
    if len(gaps)<60:
        failures.append({"reasons":["insufficient_pacing_coverage"]})
    else:
        p95,p99=float(np.percentile(gaps,95)),float(np.percentile(gaps,99))
        summary.update(p95_frame_ms=p95,p99_frame_ms=p99,max_frame_ms=max(gaps),
                       p95_capture_ms=float(np.percentile(costs,95)),
                       p95_limit_ms=1750/fps,p99_limit_ms=2500/fps)
        if p95>1750/fps or p99>2500/fps:
            failures.append({"reasons":["recurring_frame_pacing_failure"]})
    missing=set(required_steps)-steps
    if missing:
        failures.append({"reasons":["missing_journey_steps"],"steps":sorted(missing)})
    if "hitch_recover" in required_steps and injected!=1:
        failures.append({"reasons":["missing_injected_hitch_witness"],"count":injected})
    summary["midi_probes"]=midi.completed
    failures.extend(midi.finish("wrong_free" in required_steps))
    return {"timing":summary,"failures":failures}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--require-step",action="append",default=[])
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    try:
        manifest=json.loads((args.capture/"complete.json").read_text())
        with (args.capture/"frames.jsonl").open() as handle:
            result=review((json.loads(line) for line in handle),manifest,args.require_step)
    except (OSError,ValueError,KeyError,TypeError) as error:
        result={"failures":[{"reasons":["invalid_pacing_capture"],"detail":str(error)}]}
    (args.output/"report.json").write_text(json.dumps(result,indent=2))
    print("RENDER_PACING",json.dumps(result["timing"] if "timing" in result else result))
    return int(bool(result["failures"]))


if __name__=="__main__":
    raise SystemExit(main())
