"""Independent rendered timing acceptance policy (no engine scheduler imports)."""
import math
from collections import deque
from frame_pacing import FramePacing
from midi_visual_probe import MidiProbeReview

# Test budgets, deliberately stricter than journey timeouts. Raw capture
# overhead is reported and never silently subtracted from a real stall.
CONTROL_MS = 350
WINDOW_MS = 750
MOTION_ERROR_BEATS = .025
TRANSITION_SLACK_BEATS = 1.5
TRANSITION_SLACK_MS = 1200


def _musical_ms(meta):
    wall=meta.get("backend_sample_ms")
    if wall is None:
        return None
    musical=wall
    for start,length in (meta.get("timeline") or {}).get("holds_ms",[]):
        if wall>start:
            musical-=min(wall-start,float("inf") if length is None else length)
    return musical


def _segment(meta):
    timeline = meta.get("timeline") or {}
    world = meta["world"]-meta.get("run_offset",0)
    segments = timeline.get("segments",[])
    if not segments or not meta.get("following"):
        return None
    if timeline.get("end_world") is not None and world >= timeline["end_world"]-.001:
        return None
    musical=_musical_ms(meta)
    for segment in reversed(segments):
        if segment["beats"]<=1e-8 and segment["kind"]!="hold":
            continue
        if musical is not None:
            if musical >= segment["start_ms"]:
                return segment
        elif world >= segment["world_start"]-.0001:
            return segment
    return None


def _span_seconds(length,a,b,used):
    if used<=0 or length<=0:
        return 0.
    if abs(a-b)<1e-8:
        return used*60/a
    if used>=length:
        return length*60/math.sqrt(a*b)
    return (120*length/(math.pi*math.sqrt(a*b)) *
            math.atan(math.sqrt(b/a)*math.tan(math.pi*used/(2*length))))


def _span(meta):
    segment = _segment(meta)
    if not segment or segment["kind"] == "hold" or meta.get("paused"):
        return None
    timeline=meta.get("timeline") or {}
    local = meta["world"]-meta.get("run_offset",0)-segment["world_start"]
    musical=_musical_ms(meta)
    elapsed=None if musical is None else (musical-segment["start_ms"])/1000
    remaining=segment["beats"]
    for index,(beats,a,b) in enumerate(segment["spans"]):
        used=min(beats,remaining)
        duration=_span_seconds(beats,a,b,used)
        if used>0 and ((elapsed is not None and 0<=elapsed<duration) or
                      (elapsed is None and 0<=local<used)):
            if abs(a-b) > .001:
                return None
            # A publication can cut or replace a span at the same start
            # instant. Never join samples from different timing contracts.
            key = (timeline.get("run"),meta.get("run_offset",0),
                   tuple(tuple(h) for h in timeline.get("holds_ms",[])),
                   segment["start_ms"],segment["world_start"],segment["beats"],
                   tuple(tuple(s) for s in segment["spans"]),index)
            return key,float(a),segment["kind"]
        remaining-=used
        local-=used
        if elapsed is not None:
            elapsed-=duration
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
    if not current or current["kind"] not in ("rest","count_in"):
        return None
    segments = meta["timeline"]["segments"]
    index = segments.index(current)
    if current["kind"] == "count_in":
        # The ending half of the current authorized count-in runs at the
        # selected take BPM. Do not treat an old count-in or an easing span
        # as constant just because the current state has another BPM.
        playback=meta.get("playback") or {}
        take=(playback.get("current") or {}).get("segment_id",playback.get("segment_id"))
        next_take=segments[index+1] if index+1<len(segments) else {}
        span=_span(meta)
        if (take and next_take.get("take_id")==take and span
                and span[0][-1]==len(current["spans"])-1 and meta.get("bpm",0)>0):
            return float(meta["bpm"])
        return None
    if not index:
        return None
    # Cut-at-Resume leaves a zero-length placeholder; it is not a
    # tempo owner. Find the preceding real segment or Free hold.
    previous = next((s for s in reversed(segments[:index])
                     if s["kind"]=="hold" or s["beats"]>1e-8),None)
    following = next((s for s in segments[index+1:]
                      if s["kind"]=="hold" or s["beats"]>1e-8),None)
    if previous is None:
        return None
    if previous["kind"] == "hold" and following and following["kind"] == "hold":
        # Inter-target Free movement policy: 1.5-second target travel,
        # but no artificial acceleration beyond 80 BPM.
        base = max(1.,float(meta.get("bpm") or 0))
        return max(base,min(80.,current["beats"]*40.))
    if previous["kind"] in ("take","count_in","hold","rest") and following and following["kind"]=="count_in":
        # A rest leading to a timed count-in continues the real outgoing
        # rate, including a Free hold cut at the mode boundary.
        return _rate_at(previous,previous["beats"])
    if previous["kind"] in ("take","count_in") and not following:
        return _rate_at(previous,previous["beats"])
    return None


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
        self.pacing = FramePacing()
        self.motion = deque()
        self.pending = []
        self.completed = []
        self.active = False
        self.motion_windows = 0
        self.tempo_windows = 0
        self.policy_windows = 0
        self.midi = MidiProbeReview()

    def observe(self, old, new, old_image, image):
        if new.get("timing_version") != 2:
            return [],{}
        self.active = True
        reasons,metrics = self.pacing.observe(old,new)
        events = new.get("events",[])
        injected = any(e["kind"] == "injected_hitch" for e in events)
        if injected:
            self.motion.clear()
            # The deliberate recovery stall interrupts the Resume only.
            # Unrelated pending MIDI and controls retain their deadlines.
            interrupted = [p for p in self.pending if p["label"] == "resume"]
            for probe in interrupted:
                self.completed.append({"kind":probe["kind"],"label":probe["label"],
                                       "interrupted_by_injected_hitch":True})
            self.pending = [p for p in self.pending if p["label"] != "resume"]
        if not injected:
            a,b = _span(old),_span(new)
            if a is None or b is None or a != b:
                self.motion.clear()
            elif a[2] in ("take","rest","count_in"):
                sample_dt = new["sample_ms"]-old["sample_ms"]
                if sample_dt > 0:
                    delta = new.get("motion_world",new["world"])-old.get("motion_world",old["world"])
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
        midi_reasons,midi_metrics = self.midi.observe(new,image)
        reasons.extend(midi_reasons)
        metrics.update(midi_metrics)
        for event in events:
            if event["kind"] != "transition":
                continue
            if injected and event["label"] == "resume":
                self.completed.append({"kind":"transition","label":"resume",
                                       "interrupted_by_injected_hitch":True})
                continue
            self.pending.append(dict(event))
        keep = []
        for event in self.pending:
            elapsed = max(0.,new["time_ms"]-event["at_ms"])
            label = event["label"]
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
        pacing,failures = self.pacing.finish()
        failures.extend(self.midi.finish("wrong_free" in required_steps))
        completed = self.completed + self.midi.completed
        if self.pending:
            failures.append({"reasons":["unfinished_timing_probes"],"probes":[p["label"] for p in self.pending]})
        summary = dict(pacing,active=self.active,motion_windows=self.motion_windows,
                       tempo_windows=self.tempo_windows,policy_windows=self.policy_windows,
                       probes=completed)
        if self.active:
            labels={(p["kind"],p["label"]) for p in completed if not p.get("interrupted_by_injected_hitch") and not p.get("failed")}
            required=set(required_steps)
            if "wrong_free" in required:
                expected={("midi","wrong"),("midi","correct"),("transition","resume")}
                if not expected<=labels or self.pacing.injected != 1:
                    failures.append({"reasons":["missing_timing_probe_coverage"],"missing":sorted(expected-labels),"injected_hitches":self.pacing.injected})
            if "retry_wait" in required and ("transition","retry") not in labels:
                failures.append({"reasons":["missing_retry_timing_coverage"]})
            if self.tempo_windows < 1 and ("wrong_free" in required or "retry_wait" in required):
                failures.append({"reasons":["missing_sustained_tempo_coverage"]})
            if self.policy_windows < 1 and ("wrong_free" in required or "retry_wait" in required):
                failures.append({"reasons":["missing_independent_velocity_policy_coverage"]})
        return summary,failures
