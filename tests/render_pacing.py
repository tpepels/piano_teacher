"""Low-overhead real frame pacing review, without texture readback."""
import argparse
import json
import math
from pathlib import Path
from frame_pacing import FramePacing
from midi_visual_probe import MidiProbeReview


def review(records, manifest, required_steps=()):
    failures, steps = [], set()
    previous = None
    midi = MidiProbeReview()
    pacing = FramePacing()
    count = 0
    armed = False
    fps = manifest.get("fps")
    if fps not in (30,60,120) or not manifest.get("pacing_only"):
        raise ValueError("Not a valid lightweight pacing capture")
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
            reasons,metrics = pacing.observe(previous,frame)
            if reasons:
                failures.append(dict(metrics,reasons=reasons,frame=index,step=frame["step"],
                                     phase=frame.get("phase"),revision=frame.get("revision")))
        if armed:
            sample=dict(frame.get("midi_sample",{}))
            sample.update(time_ms=frame["time_ms"],events=frame.get("events",[]))
            reasons,metrics=midi.observe(sample)
            if reasons:
                failures.append({"reasons":reasons,"frame":index,"step":frame["step"],"metrics":metrics})
        previous=frame
    if count != manifest["frames"] or not manifest["success"]:
        raise ValueError("Incomplete pacing capture")
    summary,pacing_failures=pacing.finish(minimum_samples=60)
    failures.extend(pacing_failures)
    summary.update(frames=count,steps=sorted(steps))
    missing=set(required_steps)-steps
    if missing:
        failures.append({"reasons":["missing_journey_steps"],"steps":sorted(missing)})
    if "hitch_recover" in required_steps and pacing.injected!=1:
        failures.append({"reasons":["missing_injected_hitch_witness"],"count":pacing.injected})
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
