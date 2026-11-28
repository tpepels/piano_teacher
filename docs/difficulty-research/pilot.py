"""D0 evidence workflow; no production imports or difficulty predictions."""
import argparse
import csv
import hashlib
import itertools
import json
import math
from collections import Counter, defaultdict, deque
from pathlib import Path
import random

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CATEGORIES = ("displacement", "span", "chord_shape", "chord_transition", "speed",
              "repetition", "crossing", "substitution", "independence", "rhythm")
PRESENCE = {"present", "absent", "unknown", "not_applicable"}
SEVERITY = {"0", "1", "2", "3", "unknown"}
META = ("packet_id", "unit_id", "rater_id", "rater_background", "judgment_mode")
RATING_FIELDS = (*META, "severity", *CATEGORIES, "confidence", "evidence", "alternate_fingering")
REVIEW_FIELDS = ("window", "blob", "note_id", "track", "channel", "onset", "offset",
                 "pitch", "target", "hand", "finger", "fingering_provenance",
                 "attack_tick", "release_tick", "measure", "voice", "edition", "reviewer")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_source(source):
    """Literal note/tempo data. No guessed hand, fingering, or ties."""
    import mido

    path = ROOT / source["path"]
    raw = path.read_bytes()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    if blob != source["git_blob"]:
        raise ValueError(f"Changed source: {path}")
    midi = mido.MidiFile(path)
    if midi.ticks_per_beat != source["ppq"] or midi.type == 2:
        raise ValueError(f"Unsupported source timing: {path}")
    notes, tempo, meter = [], {0: 500000}, {0: [4, 4]}
    for track, events in enumerate(midi.tracks):
        tick, open_notes = 0, defaultdict(deque)
        for idx, event in enumerate(events):
            tick += event.time
            if event.type == "set_tempo":
                tempo[tick] = event.tempo
            elif event.type == "time_signature":
                meter[tick] = [event.numerator, event.denominator]
            elif event.type == "note_on" and event.velocity:
                open_notes[(event.channel, event.note)].append((idx, tick))
            elif event.type in ("note_off", "note_on"):
                key = (event.channel, event.note)
                if not open_notes[key]:
                    raise ValueError(f"Unmatched release in {path}, track {track}, tick {tick}")
                start_idx, start = open_notes[key].popleft()
                if tick <= start:
                    raise ValueError(f"Nonpositive note length in {path}")
                notes.append(dict(note_id=f"{track}:{start_idx}", track=track,
                                  channel=event.channel, onset=start, offset=tick, pitch=event.note))
        if any(open_notes.values()):
            raise ValueError(f"Unmatched attack in {path}, track {track}")
    return notes, sorted(tempo.items()), sorted(meter.items())


def inventory(corpus, plan):
    rows, maps = [], {}
    for source in corpus["repertoire"]:
        windows = [w for w in source["windows"] if w["id"] in plan["source_windows"]]
        if not windows:
            continue
        notes, tempo, meter = read_source(source)
        for window in windows:
            wid = window["id"]
            maps[wid] = dict(source=source["path"], blob=source["git_blob"],
                             ppq=source["ppq"], tempo_us=tempo, meter=meter,
                             start=window["start_tick"], end=window["end_tick"])
            # At least four quarter notes AND two seconds at source tempo.
            # The fastest encoded tempo gives a conservative tick bound;
            # slower trial conditions therefore have enough context too.
            ticks_2s = math.ceil(2_000_000 * source["ppq"] / min(v for _, v in tempo))
            lower = max(0, window["start_tick"] - max(window["context_before_ticks"], ticks_2s))
            upper = window["end_tick"] + max(window["context_after_ticks"], ticks_2s)
            maps[wid]["context_ticks"] = [lower, upper]
            for note in sorted(notes, key=lambda n: (n["onset"], n["note_id"])):
                if note["offset"] <= lower or note["onset"] >= upper:
                    continue
                target = window["start_tick"] <= note["onset"] < window["end_tick"]
                rows.append(dict(window=wid, blob=source["git_blob"], **note, target=int(target),
                                 hand="", finger="", fingering_provenance="", attack_tick=note["onset"],
                                 release_tick=note["offset"], measure="", voice="", edition="", reviewer=""))
    if set(maps) != set(plan["source_windows"]):
        raise ValueError("Pilot plan references absent source window")
    return rows, maps


def checked_review(expected, actual):
    immutable = REVIEW_FIELDS[:9]
    def key(row):
        return row["window"], row["note_id"]
    actual_by_key = {key(row): row for row in actual}
    if len(actual_by_key) != len(actual) or set(actual_by_key) != {key(row) for row in expected}:
        raise ValueError("Source review has missing, duplicate or foreign notes")
    result = []
    for original in expected:
        row = actual_by_key[key(original)]
        if any(str(original[k]) != row[k] for k in immutable):
            raise ValueError(f"Changed source facts: {key(row)}")
        if row["hand"] not in ("L", "R", "unknown"):
            raise ValueError(f"Unreviewed hand: {key(row)}")
        if row["hand"] == "unknown" and row["target"] == "1":
            raise ValueError(f"Unresolved target hand: {key(row)}")
        if row["finger"] not in ("1", "2", "3", "4", "5", "unknown"):
            raise ValueError(f"Unreviewed finger: {key(row)}")
        if row["fingering_provenance"] not in ("edition", "teacher", "override", "inferred", "unknown"):
            raise ValueError(f"Unreviewed fingering provenance: {key(row)}")
        if row["finger"] == "unknown" and row["fingering_provenance"] != "unknown":
            raise ValueError(f"Unknown finger must have unknown provenance: {key(row)}")
        if row["finger"] != "unknown" and row["fingering_provenance"] == "unknown":
            raise ValueError(f"Known finger needs provenance: {key(row)}")
        if not all(row[k].strip() for k in ("edition", "reviewer", "measure", "voice")):
            raise ValueError(f"Missing edition/hand review evidence: {key(row)}")
        start, end = int(row["attack_tick"]), int(row["release_tick"])
        if not 0 <= start < end:
            raise ValueError(f"Invalid reviewed note timing: {key(row)}")
        result.append(dict(row, attack_tick=start, release_tick=end))
    return result


def make_packet(corpus, plan, reviewed, maps, output):
    """Create neutral unit IDs and rating sheets; no expected labels exposed."""
    output.mkdir(parents=True, exist_ok=False)
    conditions = []
    for wid, meta in maps.items():
        notes = [n for n in reviewed if n["window"] == wid]
        if len({n["edition"] for n in notes}) != 1:
            raise ValueError(f"Inconsistent edition for {wid}")
        for hand, factor in itertools.product(plan["hands"], plan["tempo_factors"]):
            selected = [n for n in notes if n["hand"] == hand]
            attacks = sorted({n["attack_tick"] for n in selected if n["target"] == "1"})
            if not attacks:
                raise ValueError(f"No reviewed attacks for {wid}/{hand}")
            conditions.append(dict(key=f"{wid}/{hand}/{factor}", hand=hand, factor=factor,
                                   source=meta, edition=notes[0]["edition"], notes=selected,
                                   unknown_context=[n for n in notes if n["hand"] == "unknown"],
                                   attacks=attacks))
    for case in corpus["synthetic"]:
        if case["id"] not in plan["synthetic"]:
            continue
        notes = [dict(note_id=n["id"], attack_tick=round(n["onset"]*480),
                      release_tick=round((n["onset"]+n["duration"])*480), pitch=n["pitch"],
                      finger=n["finger"] if n["finger"] is not None else "unknown",
                      voice=n["voice"], fingering_provenance="constructed", target="1")
                 for n in case["events"]]
        conditions.append(dict(key=case["id"], hand=case["hand"], factor=1,
                               source=dict(ppq=480, tempo_us=[[0, round(60000000/case["bpm"])]],
                                           meter=case["meter"]),
                               edition="Original constructed control", notes=notes,
                               attacks=sorted({n["attack_tick"] for n in notes})))
    rng = random.Random(plan["seed"])
    rng.shuffle(conditions)
    units, cases, keymap = [], [], {}
    for i, condition in enumerate(conditions, 1):
        cid = f"P{i:03d}"
        keymap[cid] = condition["key"]
        cases.append(dict(case_id=cid, **{k: v for k, v in condition.items() if k not in ("key", "attacks")}))
        for j, tick in enumerate(condition["attacks"], 1):
            units.append(dict(unit_id=f"{cid}-{j:04d}", case_id=cid, attack_tick=tick,
                              note_ids=[n["note_id"] for n in condition["notes"]
                                        if n["attack_tick"] == tick]))
    # Packet content excludes corpus split labels, expected synthetic features,
    # contrast hints and model predictions. Coordinator key stays separate.
    packet = dict(version=1, plan_version=plan["version"],
                  plan_digest=digest(plan), cases=cases, units=units)
    packet_id = digest(packet)
    packet["packet_id"] = packet_id
    save(output / "packet.json", packet)
    save(output / "coordinator-key.json", dict(packet_id=packet_id, mapping=keymap))
    rows = [dict(packet_id=packet_id, unit_id=u["unit_id"]) for u in units]
    for rater in range(1, plan["raters"]+1):
        write_csv(output / f"ratings-{rater}.csv", RATING_FIELDS, rows)
    return packet


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def ordinal_alpha(rows):
    """Krippendorff ordinal alpha, coincidence weighting for missing ratings."""
    counts = Counter()
    pairs = Counter()
    for ratings in rows:
        n = len(ratings)
        if n < 2:
            continue
        counts.update(ratings)
        for a, b in itertools.permutations(ratings, 2):
            pairs[a, b] += 1/(n-1)
    total = sum(counts.values())
    if total < 2 or len(counts) < 2:
        return None
    def distance(a, b):
        low, high = sorted((a, b))
        if low == high:
            return 0.0
        return (sum(counts[x] for x in range(low, high+1)) -
                (counts[low]+counts[high])/2)**2
    observed = sum(n*distance(a, b) for (a, b), n in pairs.items())/total
    expected = sum(counts[a]*(counts[b]-(a == b))*distance(a, b)
                   for a in counts for b in counts)/(total*(total-1))
    return None if expected == 0 else 1-observed/expected


def agreement(packet, sheets, plan):
    packet_id = packet.get("packet_id")
    if packet_id != digest({k: v for k, v in packet.items() if k != "packet_id"}) or packet.get("plan_digest") != digest(plan):
        raise ValueError("Packet or frozen plan identity mismatch")
    units = {unit["unit_id"] for unit in packet["units"]}
    if not units or len(units) != len(packet["units"]):
        raise ValueError("Invalid packet units")
    raters = set()
    matrix = defaultdict(list)
    for sheet in sheets:
        if len(sheet) != len(units) or {row["unit_id"] for row in sheet} != units:
            raise ValueError("Missing, duplicate, or foreign units in rater sheet")
        ids = {row["rater_id"].strip() for row in sheet}
        if len(ids) != 1 or "" in ids or ids & raters:
            raise ValueError("Each sheet must have one distinct rater ID")
        raters |= ids
        for row in sheet:
            if row.get("packet_id") != packet_id:
                raise ValueError("Rating belongs to a different packet")
            if not row["rater_background"].strip() or row["judgment_mode"] not in ("score", "played"):
                raise ValueError("Rater background and judgment mode required")
            if row["severity"] not in SEVERITY or any(row[c] not in PRESENCE for c in CATEGORIES):
                raise ValueError("Use explicit unknown; blanks are not ratings")
            if row["confidence"] not in ("low", "medium", "high") or not row["evidence"].strip():
                raise ValueError("Confidence and reason required")
            matrix[row["unit_id"]].append(row)
    if len(raters) != plan["raters"]:
        raise ValueError("Exactly three independent rater sheets required")
    severity = [[int(row["severity"]) for row in matrix[u] if row["severity"] != "unknown"]
                for u in sorted(units)]
    coverage = sum(len(row) for row in severity)/(len(units)*len(raters))
    complete_coverage = sum(len(row) == len(raters) for row in severity)/len(units)
    alpha = ordinal_alpha(severity)
    metrics = dict(raters=len(raters), units=len(units), severity_coverage=coverage,
                   complete_severity_coverage=complete_coverage, ordinal_alpha=alpha,
                   categories={})
    c = plan["criteria"]
    failures = []
    if coverage < c["severity_coverage"] or complete_coverage < c["severity_coverage"]:
        failures.append("insufficient severity coverage")
    if alpha is None or alpha < c["ordinal_alpha"]:
        failures.append("insufficient ordinal agreement")
    for category in CATEGORIES:
        positive_units = negative_units = pp = pn = valid = applicable = 0
        for unit in units:
            raw = [row[category] for row in matrix[unit]]
            applicable += sum(v != "not_applicable" for v in raw)
            values = [v for v in raw if v in ("present", "absent")]
            valid += len(values)
            positive_units += values.count("present") >= 2
            negative_units += values.count("absent") >= 2
            for a, b in itertools.combinations(values, 2):
                pp += a == b == "present"
                pn += a != b
        pa = 2*pp/(2*pp+pn) if 2*pp+pn else None
        cov = valid/applicable if applicable else 0.0
        enough = positive_units >= c["min_positive_units"] and negative_units >= c["min_negative_units"]
        passed = enough and cov >= c["category_coverage"] and pa is not None and pa >= c["positive_agreement"]
        metrics["categories"][category] = dict(positive_units=positive_units,
            negative_units=negative_units, coverage=cov, positive_agreement=pa,
            status="pass" if passed else ("fail" if enough else "insufficient_sample"))
        if enough and not passed:
            failures.append(f"unreliable category: {category}")
    if not any(v["status"] == "pass" for v in metrics["categories"].values()):
        failures.append("no adequately sampled reliable category")
    return dict(metrics=metrics, failures=failures, pilot_status="pass" if not failures else "open",
                d0_status="requires independent provenance review and threshold sign-off")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("inventory")
    p.add_argument("output", type=Path)
    p = sub.add_parser("prepare")
    p.add_argument("review", type=Path)
    p.add_argument("output", type=Path)
    p = sub.add_parser("assess")
    p.add_argument("packet", type=Path)
    p.add_argument("ratings", type=Path, nargs=3)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, plan = load(HERE/"corpus-v1.json"), load(HERE/"pilot-plan.json")
    if args.command == "assess":
        report = agreement(load(args.packet), [read_csv(p) for p in args.ratings], plan)
        save(args.output, report)
        print(json.dumps(report, indent=2))
        return int(report["pilot_status"] != "pass")
    rows, maps = inventory(corpus, plan)
    if args.command == "inventory":
        args.output.mkdir(parents=True, exist_ok=False)
        write_csv(args.output/"source-review.csv", REVIEW_FIELDS, rows)
        save(args.output/"source-context.json", maps)
        print(f"Review {len(rows)} source-note rows; no hands/fingers inferred.")
    else:
        packet = make_packet(corpus, plan, checked_review(rows, read_csv(args.review)), maps, args.output)
        print(f"Prepared {len(packet['cases'])} conditions, {len(packet['units'])} attack units.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
