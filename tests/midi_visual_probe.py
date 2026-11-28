"""MIDI-to-painted-notehead probes shared by image and lightweight captures."""
import numpy as np

RECEIPT_LIMIT_MS = 150
FEEDBACK_LIMIT_MS = 250


def identity(head):
    return tuple(head.get(k) for k in ("take","layer","slot","event","status"))


def pixel_witness(image, head, label):
    """Only inspect the actual painted notehead, not the full playhead glow."""
    w,h=image.size
    x,y=head["x"]*w,head["y"]*h
    rx,ry=max(2.,head["rx"]*w),max(2.,head["ry"]*h)
    crop=np.asarray(image.crop((max(0,int(x-rx)),max(0,int(y-ry)),
                                  min(w,int(x+rx+1)),min(h,int(y+ry+1)))),dtype=np.int16)
    if not crop.size:
        return False
    r,g,b=np.moveaxis(crop,-1,0)
    # Authentic status tint is blended over white noteheads; a pale mint
    # head need not have the saturation of the original solid tint.
    mask=((r>=125)&(r-g>=12)&(r-b>=10)) if label=="wrong" else ((g>=140)&(g-r>=10)&(b-r>=3))
    return int(mask.sum())>=3


class MidiProbeReview:
    def __init__(self):
        self.pending=[]
        self.completed=[]

    def observe(self, meta, image=None):
        reasons=[]
        metrics={}
        now=meta["time_ms"]
        for event in meta.get("events",[]):
            if event["kind"]!="midi":
                continue
            if not event.get("targets") or not all(event["targets"]):
                reasons.append("missing_midi_target_identity")
                self.completed.append({"kind":"midi","label":event["label"],"failed":True})
                continue
            probe=dict(event)
            probe["baseline"]={identity(h) for h in event.get("baseline_feedback",[])}
            self.pending.append(probe)
        keep=[]
        for probe in self.pending:
            elapsed=max(0.,now-probe["at_ms"])
            label=probe["label"]
            if meta.get("midi_count",0)>probe["midi_count"] and "receipt_ms" not in probe:
                probe["receipt_ms"]=elapsed
            statuses=("missed",) if label=="wrong" else ("hit","sounding","early_release")
            matching=[h for h in meta.get("painted_feedback",[])
                      if h["take"]==probe["take"] and h["source"] in probe["targets"]
                      and h["status"] in statuses and identity(h) not in probe["baseline"]]
            painted=any(image is None or pixel_witness(image,h,label) for h in matching)
            if "receipt_ms" in probe and painted:
                result={"kind":"midi","label":label,"receipt_ms":probe["receipt_ms"],"visible_ms":elapsed,
                        "witness":"core_draw" if image is None else "core_draw_and_pixels"}
                self.completed.append(result)
                if probe["receipt_ms"]>RECEIPT_LIMIT_MS or elapsed>FEEDBACK_LIMIT_MS:
                    reasons.append("midi_feedback_latency")
                    metrics["midi_probe"]=result
            elif elapsed>FEEDBACK_LIMIT_MS:
                result={"kind":"midi","label":label,"receipt_ms":probe.get("receipt_ms"),"elapsed_ms":elapsed,
                        "matching_heads":len(matching),"painted":painted,"failed":True}
                self.completed.append(result)
                reasons.append("midi_feedback_missing_or_late")
                metrics["midi_probe"]=result
            else:
                keep.append(probe)
        self.pending=keep
        return reasons,metrics

    def finish(self, required=False):
        failures=[]
        if self.pending:
            failures.append({"reasons":["unfinished_midi_probes"],"labels":[p["label"] for p in self.pending]})
        if required and not {"wrong","correct"}<={p["label"] for p in self.completed if not p.get("failed")}:
            failures.append({"reasons":["missing_midi_probe_coverage"]})
        return failures
