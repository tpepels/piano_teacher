"""One frame timing policy for both rendered observation modes."""
import numpy as np


class FramePacing:
    def __init__(self):
        self.gaps = []
        self.costs = []
        self.injected = 0
        self.fps = None

    def observe(self, old, new):
        fps = new.get("fps", 30)
        if fps not in (30, 60, 120) or (self.fps is not None and self.fps != fps):
            raise ValueError("Invalid or changed frame pacing target")
        self.fps = fps
        if any(event["kind"] == "injected_hitch" for event in new.get("events", [])):
            self.injected += 1
            return [], {}
        dt = new["time_ms"] - old["time_ms"]
        cost = new.get("capture_cost_ms", 0.)
        self.gaps.append(dt)
        self.costs.append(cost)
        limit = min(100., max(50., 3000/fps))
        if dt > limit:
            return ["render_frame_hitch"], {
                "frame_gap_ms": dt, "limit_ms": limit, "capture_cost_ms": cost,
                "previous_ms": old["time_ms"], "at_ms": new["time_ms"],
                "frame_budget_ms": 1000/fps,
                "draw_ms": new.get("draw_ms"),
                "between_draws_ms": new.get("between_draws_ms"),
            }
        return [], {}

    def finish(self, minimum_samples=0):
        summary = {"fps": self.fps, "frame_samples": len(self.gaps),
                   "injected_hitches": self.injected}
        failures = []
        if len(self.gaps) < minimum_samples:
            failures.append({"reasons": ["insufficient_pacing_coverage"]})
        if self.gaps:
            p95, p99 = (float(np.percentile(self.gaps, q)) for q in (95, 99))
            p95_limit, p99_limit = 1750/self.fps, 2500/self.fps
            summary.update(p95_frame_ms=p95, p99_frame_ms=p99, max_frame_ms=max(self.gaps),
                           p95_capture_ms=float(np.percentile(self.costs, 95)),
                           p95_limit_ms=p95_limit, p99_limit_ms=p99_limit)
            if p95 > p95_limit or p99 > p99_limit:
                failures.append({"reasons": ["recurring_frame_pacing_failure"],
                                 "p95_ms": p95, "limit_ms": p95_limit,
                                 "p99_ms": p99, "p99_limit_ms": p99_limit})
        return summary, failures
