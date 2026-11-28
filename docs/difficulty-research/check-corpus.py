"""Validate D0 corpus integrity without importing production code."""
import hashlib
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
data = json.loads((HERE / "corpus-v1.json").read_text())
groups = {}
ids = set()
for source in data["repertoire"]:
    group = source["composition"]
    assert groups.setdefault(group, source["split"]) == source["split"], group
    raw = (ROOT / source["path"]).read_bytes()
    digest = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
    assert digest == source["git_blob"], source["path"]
    assert raw[:4] == b"MThd" and struct.unpack(">H", raw[12:14])[0] == source["ppq"]
    for window in source["windows"]:
        assert window["id"] not in ids
        ids.add(window["id"])
        assert 0 <= window["start_tick"] < window["end_tick"] <= source["last_attack_tick"] + 1
        assert window["annotation_status"] == "unannotated"
        assert window["hands"] == ["L", "R"]
families = {}
for case in data["synthetic"]:
    assert families.setdefault(case["family"], case["split"]) == case["split"]
    assert case["id"] not in ids
    ids.add(case["id"])
    assert case["bpm"] > 0 and case["hand"] in ("L", "R")
    assert case["expert_severity"] is None
    notes = {n["id"]: n for n in case["events"]}
    assert len(notes) == len(case["events"])
    assert all(n["onset"] >= 0 and n["duration"] > 0 and 21 <= n["pitch"] <= 108
               and (n["finger"] is None or 1 <= n["finger"] <= 5) for n in notes.values())
    for feature in case["expected_features"]:
        assert feature["observed"] in ("present", "absent", "unknown")
        assert feature["notes"] and set(feature["notes"]) <= notes.keys()
    for substitution in case.get("substitutions", []):
        note = notes[substitution["note"]]
        assert note["onset"] < substitution["beat"] < note["onset"] + note["duration"]
    for tie in case.get("ties", []):
        note = notes[tie["note"]]
        assert note["onset"] < tie["boundary"] < note["onset"] + note["duration"]
print(f"Corpus integrity OK: {len(groups)} compositions, {len(families)} synthetic families, {len(ids)} unique windows/cases")
