"""One green shard never substitutes for exact complete-corpus acceptance."""
import hashlib
import json
from pathlib import Path
from dataclasses import dataclass
import pytest
from scripts.audits.aggregate_shards import check, case_identity, encode_manifest

REV = "a" * 40


@dataclass(frozen=True)
class Case:
    name: str
    first: int


def audit(root, count=4):
    out = root / "artifacts"
    out.mkdir(parents=True)
    for i in range(count):
        folder = out / f"native-complete-shard-{i}-{REV}"
        folder.mkdir()
        ids = [f"g:{i + 20:064x}"] + ([f"s:{i + 90:064x}"] if i < 2 else [])
        data = encode_manifest(ids)
        (folder / "case-manifest.txt").write_bytes(data)
        (folder / "revision.txt").write_text(REV + "\n")
        row = dict(state="passed", passed=True, shard_index=i, shard_count=count,
                   denominators_complete=True, failures=[], active_cases=[],
                   inputs_sha256="b"*64, sources_discovered=2,
                   runtime={"godot":"4.7.2"}, capture_config={"mode":"canonical"},
                   manifest_sha256=hashlib.sha256(data).hexdigest(), manifest_entries=len(ids),
                   source_semantics_expected=int(i<2), source_semantics_checked=int(i<2),
                   cases_expected=1, cases_attempted=1, cases_checked=1, cases_pending=0,
                   sources_expected=1, sources_checked=1, measures_expected=4, measures_checked=4)
        (folder / "summary.json").write_text(json.dumps(row))
    return out


def modify(root, i, **changes):
    f = root / f"native-complete-shard-{i}-{REV}" / "summary.json"
    row = json.loads(f.read_text())
    row.update(changes)
    f.write_text(json.dumps(row))


def test_all_shards_and_semantics_disjoint_and_complete(tmp_path):
    r = check(audit(tmp_path), REV, shard_count=4)
    assert r["passed"], r["failures"]
    assert (r["cases_checked"],r["unique_case_ids"],r["sources_discovered"]) == (4,6,2)


def test_source_case_id_stable_across_worker_orders_and_scopes():
    a = case_identity("midi/s.mid","originals",Case("take",1))
    assert a == case_identity("midi/s.mid","originals",Case("take",1))
    assert a != case_identity("midi/s.mid","focused",Case("take",1))
    assert a != case_identity("midi/o.mid","originals",Case("take",1))
    with pytest.raises(ValueError):
        encode_manifest([a,a])
    with pytest.raises(ValueError):
        case_identity("/tmp/private.mid","originals",Case("take",1))


def test_missing_stale_and_foreign_revision_fail(tmp_path):
    root = audit(tmp_path)
    (root / f"native-complete-shard-2-{REV}" / "summary.json").unlink()
    assert not check(root,REV,shard_count=4)["passed"]
    root = audit(tmp_path/"new")
    (root / f"native-complete-shard-0-{REV}" / "revision.txt").write_text("f"*40)
    assert any("wrong original revision" in e for e in check(root,REV,shard_count=4)["failures"])
    (root / f"native-complete-shard-9-{REV}").mkdir()
    assert any("Stale or unexpected" in e for e in check(root,REV,shard_count=4)["failures"])


@pytest.mark.parametrize("mutation",[
    {"state":"running","passed":False},
    {"denominators_complete":False},
    {"cases_checked":0,"cases_pending":1},
    {"inputs_sha256":"f"*64},
    {"sources_discovered":5},
    {"source_semantics_checked":0},
    {"runtime":{"godot":"other"}},
    {"failures":["real source mismatch"]},
])
def test_corrupt_or_incomplete_shard_can_never_certify(tmp_path, mutation):
    root = audit(tmp_path)
    modify(root, 0, **mutation)
    assert not check(root,REV,shard_count=4)["passed"]


def test_repeated_case_in_two_green_shards_is_refused(tmp_path):
    root = audit(tmp_path)
    source = root / f"native-complete-shard-0-{REV}" / "case-manifest.txt"
    target = root / f"native-complete-shard-1-{REV}" / "case-manifest.txt"
    case = next(s for s in source.read_text().splitlines() if s.startswith("g:"))
    other = target.read_text().splitlines()
    data = encode_manifest([*other,case])
    target.write_bytes(data)
    modify(root,1,manifest_sha256=hashlib.sha256(data).hexdigest(),
           manifest_entries=3,cases_expected=2,cases_attempted=2,cases_checked=2)
    failures = check(root,REV,shard_count=4)["failures"]
    assert any("Duplicate graphical" in e for e in failures)


def test_edited_case_manifest_not_accepted(tmp_path):
    root = audit(tmp_path)
    (root / f"native-complete-shard-1-{REV}" / "case-manifest.txt").write_text("g:"+"f"*64+"\n")
    assert any("manifest digest" in e for e in check(root,REV,shard_count=4)["failures"])
