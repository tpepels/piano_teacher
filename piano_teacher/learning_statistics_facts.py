"""Pure numerical summaries and comparable performed-evidence contexts."""
import math

def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Residual:
    def __init__(self):
        self.samples = []
        self.count = 0
        self.total = self.absolute = self.mean = self.m2 = 0.0
        self.minimum = self.maximum = None

    def add(self, value):
        if not number(value):
            return
        self.count += 1
        self.samples.append(value)
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.total += value
        self.absolute += abs(value)
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def result(self):
        samples = sorted(self.samples)
        def quantile(p):
            if not samples:
                return None
            index = (len(samples)-1)*p
            lo, hi = math.floor(index), math.ceil(index)
            return samples[lo] + (samples[hi]-samples[lo])*(index-lo)
        return {"sample_count": self.count,
                "quantiles_seconds": {key: quantile(p) for key, p in (("p05", .05), ("p25", .25), ("p50", .5), ("p75", .75), ("p95", .95))},
                "mean_seconds": self.mean if self.count else None,
                "mean_absolute_seconds": self.absolute / self.count if self.count else None,
                "population_std_seconds": math.sqrt(max(0.0, self.m2 / self.count)) if self.count else None,
                "minimum_seconds": self.minimum, "maximum_seconds": self.maximum}


def performed_context(context, terminal):
    result = dict(context)
    if isinstance(terminal.get("assistance_used"), bool):
        result["assistance"] = terminal["assistance_used"]
    assessed_end, planned_end = terminal.get("assessed_end_beat"), context.get("end_beat")
    if number(assessed_end) and number(planned_end) and assessed_end < planned_end:
        result["end_beat"] = assessed_end
        if result.get("scope") == "full":
            result["scope"] = "partial"
    return result


def compatibility(before, after):
    """Recheck context rather than trusting an outcome's comparability flags."""
    if before is None or after is None:
        return "unknown"
    left = performed_context(before["context"], before["terminal"])
    right = performed_context(after["context"], after["terminal"])
    dimensions = []
    for fields in (("fingerprint", "stage_key", "hand"), ("performed_bpm",),
                   ("scope", "from_beat", "end_beat"), ("rule_id",)):
        dimensions.append(None if any(left.get(k) is None or right.get(k) is None for k in fields)
                          else all(left[k] == right[k] for k in fields))
    for field in ("tempo_map_hash", "calibration_ms", "midi_available"):
        if field in left or field in right:
            dimensions.append(None if left.get(field) is None or right.get(field) is None
                              else left[field] == right[field])
    support = []
    for attempt in (before, after):
        value = attempt["terminal"].get("assistance_used", attempt["context"].get("assistance"))
        support.append(value if isinstance(value, bool) else None)
    dimensions.append(None if any(value is None for value in support) else support[0] == support[1])
    if False in dimensions:
        return "incompatible"
    return "compatible" if all(value is True for value in dimensions) else "unknown"


