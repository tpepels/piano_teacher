"""Independent rendered timing acceptance policy (no engine scheduler imports)."""
import math
from collections import deque
import numpy as np

# Test budgets, deliberately stricter than journey timeouts. Raw capture
# overhead is reported and never silently subtracted from a real stall.
CONTROL_MS = 350
MIDI_RECEIPT_MS = 150
MIDI_FEEDBACK_MS = 250
HITCH_MS = 100
WINDOW_MS = 750
MOTION_ERROR_BEATS = .025
TRANSITION_SLACK_BEATS = 1.5
TRANSITION_SLACK_MS = 1200


def _segment(meta):
    timeline = meta.get("timeline") or {}
    world = meta["world"]-meta.get("run_offset",0)
    segments = timeline.get("segments",[])
    if not segments or not meta.get("following"):
        return None
    if timeline.get("end_world") is not None and world >= timeline["end_world"]-.001:
        return None
    for segment in reversed(segments):
        if world >= segment["world_start"]-.0001:
            return segment
    return None


def _span(meta):
    segment = _segment(meta)
    if not segment or segment["kind"] == "hold" or meta.get("paused"):
        return None
    local = meta["world"]-meta.get("run_offset",0)-segment["world_start"]
    # Only stable constant spans can be judged by the constant rate test;
    # easing boundaries and authored tempo changes have their own gross cap.
    for index,(beats,a,b) in enumerate(segment["spans"]):
        if local < beats or index == len(segment["spans"])-1:
            if abs(a-b) > .001:
                return None
            key = ((meta.get("timeline") or {}).get("run"),segment["start_ms"],index)
            return key,float(a),segment["kind"]
        local -= beats
    return None


def _rate_at(segment, beat):
    for length,a,b in segment["spans"]:
        if beat <= length or length == 0:
            fraction = min(1.,max(0.,beat/length)) if length else 1.
            return a+(b-a)*(1-math.cos(math.pi*fraction))/2
        beat -= length
    return segment["spans"][-1][2]


def _policy_rate(meta):
    """Independent bound on artificial speed, not the published rest rate."""
    current = _segment(meta)
    if not current or current["kind"] != "rest":
        return None
    segments = meta["timeline"]["segments"]
    index = segments.index(current)
    if not index:
        return None
    previous = segments[index-1]
    following = segments[index+1] if index+1 < len(segments) else None
    if previous["kind"] == "hold" and following and following["kind"] == "hold":
        # Inter-target Free movement policy: 1.5-second target travel,
        # but no artificial acceleration beyond 80 BPM.
        base = max(1.,float(meta.get("bpm") or 0))
        return max(base,min(80.,current["beats"]*40.))
    if previous["kind"] in ("take","count_in") and (not following or following["kind"]!="hold"):
        # A silent tail continues at the outgoing sounding tempo.
        return _rate_at(previous,previous["beats"])
    return None


def _pixels(image, meta, label):
    # Score-only crop centred on the reading axis. Red wrong-note ink and
    # mint notehead ink are distinct from the fixed green staff background.
    rgb = np.asarray(image,dtype=np.int16)
    h,w = rgb.shape[:2]
    x,y,sw,sh = meta["score"]
    center = meta["playhead"]
    left = max(0,round(max(x,center-.07)*w))
    right = min(w,round(min(x+sw,center+.07)*w))
    crop = rgb[max(0,round(y*h)):min(h,round((y+sh)*h)),left:right]
    r,g,b = np.moveaxis(crop,-1,0)
    if label == "wrong":
        return int(((r>=110)&(r-g>=25)&(r-b>=20)).sum())
    return int(((g>=145)&(g-r>=18)&(b-r>=8)).sum())


def _feedback(meta):
    return {(layer["id"],strip["id"],tuple(entry))
            for layer in meta.get("layers",[]) for strip in layer.get("strips",[])
            if strip["visible"] and strip["left"]<1 and strip["right"]>strip["gutter"]
            for entry in strip.get("pitch_feedback",[])}


def _clearance(event):
    # Only ink already exposed at the button press is unavoidable. Ignore
    # queued but unexposed future notes and their trailing rests.
    world = event["world"]
    ends = [float(strip["world_end"]) for layer in event.get("layers",[])
            for strip in layer.get("strips",[])
            if strip.get("ever_visible") and strip.get("world_end") is not None]
    return max([0.,*(end-world for end in ends)])


def _take(meta, event):
    playback = meta.get("playback") or {}
    current = playback.get("current") or {}
    if not current or not playback.get("presentation_confirmed"):
        return None
    if event["label"] == "retry" and meta["transport"] <= event["transport"]:
        return None
    if event["label"] == "resume" and meta.get("paused"):
        return None
    identity = current.get("segment_id",playback.get("segment_id"))
    segments = (meta.get("timeline") or {}).get("segments",[])
    for index,segment in enumerate(segments):
        if segment.get("kind") == "take" and segment.get("take_id") == identity and index:
            count = segments[index-1]
            if count["kind"] == "count_in":
                return segment,count
    return None


class TimingReview:
    def __init__(self):
        self.gaps = []
        self.capture_costs = []
        self.motion = deque()
        self.pending = []
        self.completed = []
        self.failures = []
        self.active = False
        self.motion_windows = 0
        self.injected = 0
        self.tempo_windows = 0
        self.policy_windows = 0
        self.fps = 30

    def observe(self, old, new, old_image, image):
        if new.get("timing_version") != 1:
            return [],{}
        self.active = True
        reasons,metrics = [],{}
        dt = new["time_ms"]-old["time_ms"]
        events = new.get("events",[])
        injected = any(e["kind"] == "injected_hitch" for e in events)
        fps = new.get("fps",30)
        self.fps = fps
        if injected:
            self.injected += 1
            self.motion.clear()
            # Deliberate OS.delay_msec is only exempt from pacing and the
            # interrupted command's latency. The visual continuity and
            # journey recovery assertions remain active.
            # Do not silently discard unrelated pending probes. Only the
            # Resume intentionally interrupted by the harness is exempt.
            for probe in self.pending:
                self.completed.append({"kind":probe["kind"],"label":probe["label"],
                                       "interrupted_by_injected_hitch":True})
            self.pending.clear()
        else:
            self.gaps.append(dt)
            self.capture_costs.append(new.get("capture_cost_ms",0.))
            if dt > min(HITCH_MS,max(50.,3*1000/fps)):
                reasons.append("render_frame_hitch")
                metrics.update(frame_gap_ms=dt,capture_cost_ms=new.get("capture_cost_ms",0.),
                               frame_budget_ms=1000/fps)
        if not injected:
            a,b = _span(old),_span(new)
            if a is None or b is None or a != b:
                self.motion.clear()
            elif a[2] in ("take","rest","count_in"):
                sample_dt = new["sample_ms"]-old["sample_ms"]
                if sample_dt > 0:
                    delta = new["world"]-old["world"]
                    self.motion.append((sample_dt,delta,a[1],a[2]))
                    while len(self.motion)>1 and sum(x[0] for x in self.motion)-self.motion[0][0]>=WINDOW_MS:
                        self.motion.popleft()
                    duration = sum(x[0] for x in self.motion)
                    if duration >= WINDOW_MS:
                        expected = sum(x[0]*x[2]/60000 for x in self.motion)
                        actual = sum(x[1] for x in self.motion)
                        self.motion_windows += 1
                        if a[2]=="take":
                            self.tempo_windows += 1
                        # 5% plus small absolute rounding margin over a
                        # sustained window, rather than 20% every frame.
                        if abs(actual-expected) > max(MOTION_ERROR_BEATS,.05*expected):
                            reasons.append("sustained_scroll_rate_error")
                            metrics.update(window_ms=duration,expected_beats=expected,actual_beats=actual)
                        policy = _policy_rate(new)
                        if policy is not None:
                            self.policy_windows += 1
                            actual_bpm = actual*60000/duration
                            if abs(actual_bpm-policy)>max(2.,.05*policy):
                                reasons.append("unauthorized_rest_or_free_speed")
                                metrics.update(policy_bpm=policy,measured_bpm=actual_bpm)
            else:
                self.motion.clear()
        for event in events:
            if injected or event["kind"] == "injected_hitch":
                continue
            probe = dict(event)
            probe["baseline"] = _pixels(old_image,old,event["label"]) if event["kind"]=="midi" else 0
            probe["feedback_before"] = _feedback(old) if event["kind"]=="midi" else set()
            self.pending.append(probe)
        keep = []
        for event in self.pending:
            elapsed = max(0.,new["time_ms"]-event["at_ms"])
            label = event["label"]
            if event["kind"] == "midi":
                if "receipt_ms" not in event and new.get("midi_count",0)>event["midi_count"]:
                    event["receipt_ms"] = elapsed
                feedback = _feedback(new)-event["feedback_before"]
                # For the injected wrong note require the actual pitch;
                # for a clean attack require a newly colored hit/sounding
                # head, never a miss or an unrelated old ghost.
                matched = any(
                    (entry[0]==str(event["pitch"]) and entry[1].isdigit()) if label=="wrong"
                    else entry[1] in ("hit","sounding","early_release")
                    for _,_,entry in feedback)
                painted = _pixels(image,new,label)>event["baseline"]+3
                if "receipt_ms" in event and matched and painted:
                    self.completed.append({"kind":"midi","label":label,"receipt_ms":event["receipt_ms"],"visible_ms":elapsed})
                    if event["receipt_ms"]>MIDI_RECEIPT_MS or elapsed>MIDI_FEEDBACK_MS:
                        reasons.append("midi_feedback_latency")
                    continue
                if elapsed>MIDI_FEEDBACK_MS:
                    reasons.append("midi_feedback_missing_or_late")
                    metrics["midi_probe"] = {"label":label,"receipt_ms":event.get("receipt_ms"),"elapsed_ms":elapsed,"painted":painted}
                    self.completed.append({"kind":"midi","label":label,"failed":True})
                    continue
            else:
                pause = label.startswith("pause_")
                if "response_ms" not in event:
                    changed = (bool(new.get("paused")) == pause) if label!="retry" else new["transport"]>event["transport"]
                    # The actual button's rendered text must have changed
                    # for Pause/Resume, not merely a backend state poll.
                    button_changed = new.get("button_text") != event.get("button_text")
                    if changed and (label=="retry" or button_changed):
                        event["response_ms"] = elapsed
                        if elapsed>CONTROL_MS:
                            reasons.append("control_response_latency")
                if label.endswith("_control"):
                    if "response_ms" in event:
                        self.completed.append({"kind":"control","label":label,"response_ms":event["response_ms"]})
                        continue
                    if elapsed>CONTROL_MS:
                        reasons.append("control_response_missing_or_late")
                        self.completed.append({"kind":"control","label":label,"failed":True})
                        continue
                else:
                    placed = _take(new,event)
                    if placed and "response_ms" in event:
                        take,count = placed
                        bar = float(count["beats"])
                        bpm = max(1.,event["bpm"])
                        clearance = _clearance(event)
                        start = take["world_start"]+new.get("run_offset",0.)
                        distance = start-event["world"]
                        # One complete count-in, physical clearance, header
                        # allowance and publication lead. No whole extra
                        # passage is allowed merely because it was queued.
                        maximum = clearance+bar+TRANSITION_SLACK_BEATS+CONTROL_MS*bpm/60000
                        duration_limit = maximum*60000/bpm+TRANSITION_SLACK_MS
                        if distance>maximum and not event.get("distance_reported"):
                            reasons.append("unnecessary_transition_travel")
                            metrics.update(transition_distance=distance,transition_limit=maximum,clearance=clearance)
                            event["distance_reported"] = True
                        if new.get("phase")=="playing":
                            self.completed.append({"kind":"transition","label":label,"response_ms":event["response_ms"],"onset_ms":elapsed,"limit_ms":duration_limit,"distance":distance,"limit_beats":maximum})
                            if elapsed>duration_limit:
                                reasons.append("unnecessary_transition_delay")
                            continue
                    if elapsed>CONTROL_MS and "response_ms" not in event:
                        reasons.append("control_response_missing_or_late")
                        self.completed.append({"kind":"transition","label":label,"failed":True})
                        continue
            keep.append(event)
        self.pending = keep
        return list(dict.fromkeys(reasons)),metrics

    def finish(self,required_steps=()):
        failures=[]
        if self.pending:
            failures.append({"reasons":["unfinished_timing_probes"],"probes":[p["label"] for p in self.pending]})
        summary={"active":self.active,"motion_windows":self.motion_windows,"tempo_windows":self.tempo_windows,
                 "injected_hitches":self.injected,"policy_windows":self.policy_windows,"probes":self.completed}
        if self.gaps:
            gaps=np.asarray(self.gaps)
            summary.update(frame_samples=len(gaps),p95_frame_ms=float(np.percentile(gaps,95)),
                           p99_frame_ms=float(np.percentile(gaps,99)),max_frame_ms=float(gaps.max()),
                           p95_capture_ms=float(np.percentile(self.capture_costs,95)))
            # At 30 FPS the baseline budget is 33ms; high-refresh captures
            # must be explicitly requested and satisfy their own budget.
            # The summary uses observed configured FPS, never inferred FPS.
            limit = 1.75*1000/self.fps
            p99_limit = 2.5*1000/self.fps
            summary.update(p95_limit_ms=limit,p99_limit_ms=p99_limit,fps=self.fps)
            if summary["p95_frame_ms"]>limit or summary["p99_frame_ms"]>p99_limit:
                failures.append({"reasons":["recurring_frame_pacing_failure"],"p95_ms":summary["p95_frame_ms"],"limit_ms":limit,"p99_ms":summary["p99_frame_ms"],"p99_limit_ms":p99_limit})
        if self.active:
            labels={(p["kind"],p["label"]) for p in self.completed if not p.get("interrupted_by_injected_hitch")}
            required=set(required_steps)
            if "wrong_free" in required:
                expected={("midi","wrong"),("midi","correct"),("transition","resume")}
                if not expected<=labels or self.injected != 1:
                    failures.append({"reasons":["missing_timing_probe_coverage"],"missing":sorted(expected-labels),"injected_hitches":self.injected})
            if "retry_wait" in required and ("transition","retry") not in labels:
                failures.append({"reasons":["missing_retry_timing_coverage"]})
            if self.tempo_windows < 1 and ("wrong_free" in required or "retry_wait" in required):
                failures.append({"reasons":["missing_sustained_tempo_coverage"]})
        return summary,failures
