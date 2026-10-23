"""Corpus gates reject forged, incomplete and malformed independent evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import aggregate_phase3_corpus as aggregation
from scripts.aggregate_phase3_corpus import HANDS, aggregate
from piano_teacher.notation.semantic_contract import source_inventory as semantic_inventory
from piano_teacher.notation.visual_coverage import source_inventory as visual_inventory

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "tests/score-0.musicxml",
    "tests/score-1.musicxml",
)
STATUSES = ("verified", "ambiguous", "unsupported", "unverified", "mismatch")


@pytest.fixture(autouse=True)
def pinned_test_corpus(tmp_path, monkeypatch):
    """Tiny authored originals make omission tests independent of native output."""
    root = tmp_path / "originals"
    for index, name in enumerate(SOURCES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'''<score-partwise version="4.0">
<part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
<part id="P1"><measure number="1" id="m1">
<attributes><divisions>1</divisions><time><beats>1</beats><beat-type>4</beat-type></time>
<clef><sign>G</sign><line>2</line></clef></attributes>
<note id="note1"><pitch><step>{'C' if index == 0 else 'D'}</step><octave>4</octave></pitch>
<duration>1</duration><voice>1</voice><type>quarter</type><staff>1</staff></note>
<backup><duration>1</duration></backup>
<note id="rest1"><rest/><duration>1</duration><voice>2</voice><type>quarter</type><staff>2</staff></note>
</measure></part></score-partwise>''')
    monkeypatch.setattr(aggregation, "ROOT", root)
    monkeypatch.setattr(aggregation, "PINNED_SOURCES", SOURCES)


def _path(folder, index=0, hand="both", kind="visual"):
    prefix = "phase3-semantic-report" if kind == "semantic" else "phase3-report"
    return folder / f"{prefix}-{index}-{hand}" / "summary.json"


def _save(folder, data, index=0, hand="both", kind="visual"):
    path = _path(folder, index, hand, kind)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _report(folder, index=0, hand="both", *, kind="visual"):
    name = SOURCES[index]
    original = aggregation.ROOT / name
    inventory = (semantic_inventory(original) if kind == "semantic" else
                 visual_inventory(original.read_text(), hand))
    elements = [{**row, "status": "verified"} for row in inventory]
    coverage = {"expected": len(elements), **{key: len(elements) if key == "verified" else 0 for key in STATUSES}}
    data = {
        "schema_version": 1, "verification_kind": kind,
        "source_index": index, "source": name,
        "source_sha256": sha256(original.read_bytes()).hexdigest(),
        "hand": hand, "passed": True, "complete": True,
        "coverage": coverage, "elements": elements,
    }
    if kind == "visual":
        data.update({
            "scores_total": 2, "scores_attempted": [name],
            "scores_passed": 1, "scores_failed": [],
            "scores": [{
                "piece": name, "hand": hand, "passed": True,
                "measures_expected": 1, "measures_witnessed": 1,
                "notes_image_proximity_witnessed": 1,
                "rests_image_proximity_witnessed": 1, "native_frames_checked": 1,
                "missing_measures": [], "duplicated_measures": [], "unexpected_measures": [],
                "visual_elements": deepcopy(elements), "visual_coverage": deepcopy(coverage),
                "windows": [{"first_bar": 1, "last_bar": 1,
                    "visual_elements": deepcopy(elements),
                    "whole_window_coverage": {
                        "elements": deepcopy(elements),
                        "measure_count": 1, "sampled_measures": 1, "screenshot_count": 1,
                        "source_noteheads": 1, "unique_rendered_noteheads": 1,
                        "source_rests": 1, "unique_rendered_rests": 1,
                        "missing_notes": [], "missing_rests": [], "missing_measure_starts": [],
                        "unexpected_notes": [], "unexpected_rests": [],
                        "independent_image_pitch": {
                            "passed": True, "written_active_noteheads": 0 if hand == "left" else 1,
                            "image_pitch_verified": 0 if hand == "left" else 1, "failures": [],
                        },
                        "independent_image_rests": {
                            "passed": True, "written_active_rests": 0 if hand == "right" else 1,
                            "image_rest_glyphs_verified": 0 if hand == "right" else 1, "failures": [],
                            "intrinsically_indistinguishable_half_whole": 0,
                        },
                    },
                }],
            }],
        })
    _save(folder, data, index, hand, kind)
    return data


def _complete(folder, *, kind="visual"):
    for index in (0, 1):
        for hand in HANDS:
            _report(folder, index, hand, kind=kind)


def _aggregate(folder, kind="visual"):
    return aggregate(folder, scores=2, kind=kind)


def _edit(folder, edit, *, kind="visual"):
    path = _path(folder, kind=kind)
    data = json.loads(path.read_text())
    edit(data)
    _save(folder, data, kind=kind)


def _witness(data):
    return data["scores"][0]["windows"][0]["whole_window_coverage"]


@pytest.mark.parametrize("kind", ["semantic", "visual"])
def test_every_score_and_hand_requires_its_own_boundary_evidence(tmp_path, kind):
    _complete(tmp_path, kind=kind)
    result = _aggregate(tmp_path, kind)
    assert result["passed"], result["errors"]
    assert result["complete"]
    assert result["jobs_with_results"] == 6
    assert result["coverage"]["verified"] == result["coverage"]["expected"] > 0


def test_complete_gate_requires_semantic_and_visual_reports_separately(tmp_path):
    _complete(tmp_path)
    result = _aggregate(tmp_path, "complete")
    assert not result["passed"]
    assert result["required_jobs"] == 12
    assert any("semantic" in error for error in result["errors"])
    _complete(tmp_path, kind="semantic")
    assert _aggregate(tmp_path, "complete")["passed"]


def test_well_formed_incomplete_evidence_has_separate_integrity_and_coverage_results(tmp_path):
    _complete(tmp_path, kind="semantic")
    data = json.loads(_path(tmp_path, kind="semantic").read_text())
    data["elements"][-1]["status"] = "unsupported"
    data["coverage"]["verified"] -= 1
    data["coverage"]["unsupported"] += 1
    data["complete"] = False
    _save(tmp_path, data, kind="semantic")
    result = _aggregate(tmp_path, "semantic")
    assert result["integrity_complete"] is True
    assert result["integrity_errors"] == []
    assert result["coverage_errors"]
    assert result["complete"] is False
    assert result["passed"] is False


def test_missing_inventory_is_an_integrity_failure_not_just_incomplete_coverage(tmp_path):
    _complete(tmp_path, kind="semantic")
    data = json.loads(_path(tmp_path, kind="semantic").read_text())
    data["elements"].pop()
    data["coverage"]["expected"] -= 1
    data["coverage"]["verified"] -= 1
    _save(tmp_path, data, kind="semantic")
    result = _aggregate(tmp_path, "semantic")
    assert result["integrity_complete"] is False
    assert any("inventory missing" in error for error in result["integrity_errors"])


def test_missing_single_hand_job_fails_closed(tmp_path):
    _complete(tmp_path)
    _path(tmp_path, 1, "left").unlink()
    result = _aggregate(tmp_path)
    assert not result["passed"]
    assert any("1/left" in error for error in result["errors"])


def _required_projection(index, hand, kind):
    source = aggregation.ROOT / SOURCES[index]
    return (semantic_inventory(source) if kind == "semantic" else
            visual_inventory(source.read_text(), hand))


def _assert_restored_inventory(result, index, hand, kind):
    required = _required_projection(index, hand, kind)
    job = next(job for job in result["jobs"] if
               (job["source_index"], job["hand"], job["verification_kind"]) == (index, hand, kind))
    assert job["coverage"] == {
        "expected": len(required),
        **{status: len(required) if status == "unverified" else 0 for status in STATUSES},
    }
    rows = [row for row in result["unverified_elements"] if
            (row["source_index"], row["hand"], row["verification_kind"]) == (index, hand, kind)]
    assert len(rows) == len(required)
    assert all(row["status"] == "unverified" and row["score_source"] == SOURCES[index] for row in rows)
    assert [{key: row[key] for key in ("id", "construct", "source")} for row in rows] == [
        {key: row[key] for key in ("id", "construct", "source")} for row in required]
    if kind == "semantic":
        assert [row["boundary"] for row in rows] == [row["boundary"] for row in required]


@pytest.mark.parametrize("kind", ["semantic", "visual", "complete"])
def test_absent_root_restores_exact_source_inventory_for_every_pinned_job(tmp_path, kind):
    result = _aggregate(tmp_path / "absent-reports", kind)
    assert result["status"] == "blocked"
    assert result["jobs_with_results"] == 0
    assert result["coverage"]["expected"] > 0
    assert result["coverage"]["unverified"] == result["coverage"]["expected"]
    assert len(result["unverified_elements"]) == result["coverage"]["expected"]
    for boundary in (("semantic", "visual") if kind == "complete" else (kind,)):
        for index in range(2):
            for hand in HANDS:
                _assert_restored_inventory(result, index, hand, boundary)
    assert sum(job["coverage"]["expected"] for job in result["jobs"]) == result["coverage"]["expected"]


@pytest.mark.parametrize("kind", ["semantic", "visual"])
@pytest.mark.parametrize("damage", ["missing", "invalid_json", "invalid_utf8", "nonobject", "unreadable", "invalid_schema"])
def test_unavailable_report_preserves_inventory_and_healthy_jobs(tmp_path, kind, damage):
    _complete(tmp_path, kind=kind)
    before = _aggregate(tmp_path, kind)
    target = _path(tmp_path, kind=kind)
    if damage == "missing":
        target.unlink()
    elif damage == "invalid_json":
        target.write_text("{")
    elif damage == "invalid_utf8":
        target.write_bytes(b"\xff")
    elif damage == "nonobject":
        target.write_text("[]")
    elif damage == "unreadable":
        target.unlink()
        target.mkdir()
    else:
        data = json.loads(target.read_text())
        data["schema_version"] = 999
        _save(tmp_path, data, kind=kind)
    result = _aggregate(tmp_path, kind)
    assert not result["complete"]
    _assert_restored_inventory(result, 0, "both", kind)
    assert result["coverage"]["expected"] == before["coverage"]["expected"]
    missing = len(_required_projection(0, "both", kind))
    assert result["coverage"]["verified"] == before["coverage"]["verified"] - missing
    assert result["coverage"]["unverified"] == missing
    assert result["jobs"][1:] == before["jobs"][1:]


def test_swapping_pinned_sources_consistently_across_all_hands_is_rejected(tmp_path):
    _complete(tmp_path)
    for hand in HANDS:
        first = json.loads(_path(tmp_path, 0, hand).read_text())
        second = json.loads(_path(tmp_path, 1, hand).read_text())
        first["source_index"], second["source_index"] = 1, 0
        _save(tmp_path, first, 1, hand)
        _save(tmp_path, second, 0, hand)
    result = _aggregate(tmp_path)
    assert not result["passed"]
    assert any("pinned source" in error for error in result["errors"])


@pytest.mark.parametrize("key,value", [
    ("source_index", 1), ("hand", "right"), ("verification_kind", "semantic"),
    ("source_sha256", "0" * 64), ("schema_version", 0), ("source_index", False),
    ("passed", "true"), ("complete", 1),
])
def test_wrong_identity_digest_or_truthy_flags_cannot_pass(tmp_path, key, value):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: data.update({key: value}))
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("mutate", [
    lambda data: data.update({"elements": [], "coverage": {"expected": 0, **dict.fromkeys(STATUSES, 0)}}),
    lambda data: data.pop("elements"),
    lambda data: data.pop("coverage"),
    lambda data: data["coverage"].update({"verified": 999}),
    lambda data: data["coverage"].update({"expected": 4}),
    lambda data: data["coverage"].update({"ambiguous": -1}),
    lambda data: data["coverage"].update({"unsupported": False}),
    lambda data: data["elements"].append(deepcopy(data["elements"][0])),
    lambda data: data["elements"][0].update({"source": {}}),
    lambda data: data["elements"][0].update({"construct": ""}),
])
def test_empty_or_forged_ledger_is_rejected(tmp_path, mutate):
    _complete(tmp_path)
    _edit(tmp_path, mutate)
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("status", ["ambiguous", "unsupported", "unverified", "mismatch", "invented"])
def test_every_nonverified_element_is_reported_and_never_counted_verified(tmp_path, status):
    _complete(tmp_path, kind="semantic")
    before = _aggregate(tmp_path, "semantic")["coverage"]["verified"]
    def mutate(data):
        data["elements"][0].update({"status": status, "construct": "beam", "reason": "unproven shape"})
        data["complete"] = False
        if status in STATUSES:
            data["coverage"]["verified"] -= 1
            data["coverage"][status] = 1
    _edit(tmp_path, mutate, kind="semantic")
    result = _aggregate(tmp_path, "semantic")
    assert not result["passed"]
    assert not result["complete"]
    assert result["coverage"]["verified"] == before - 1
    rows = result["unverified_elements"]
    assert any(row["construct"] == "beam" and row["source"] for row in rows)
    assert any("beam" in error for error in result["errors"])


def test_all_unverified_constructs_survive_aggregation(tmp_path):
    _complete(tmp_path, kind="semantic")
    def mutate(data):
        for row, status in zip(data["elements"], ("ambiguous", "unsupported", "mismatch")):
            row["status"] = status
        data["coverage"].update(verified=len(data["elements"])-3, ambiguous=1, unsupported=1, mismatch=1)
        data["complete"] = False
    _edit(tmp_path, mutate, kind="semantic")
    result = _aggregate(tmp_path, "semantic")
    assert len(result["unverified_elements"]) == 3
    assert {row["status"] for row in result["unverified_elements"]} == {"ambiguous", "unsupported", "mismatch"}


@pytest.mark.parametrize("malformed", [None, [], "text", 1, {"scores_attempted": None},
    {"elements": [None], "coverage": []}])
def test_malformed_report_yields_diagnostic_instead_of_crashing(tmp_path, malformed):
    _complete(tmp_path)
    _save(tmp_path, malformed)
    result = _aggregate(tmp_path)
    assert not result["passed"]
    assert any("0/both" in error for error in result["errors"])


@pytest.mark.parametrize("key,value", [("scores", [None]), ("scores", {}),
    ("scores_attempted", None), ("scores_attempted", [{}]), ("scores_failed", None)])
def test_malformed_visual_structure_yields_diagnostic(tmp_path, key, value):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: data.update({key: value}))
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("key,value", [("windows", [None]), ("windows", None),
    ("measures_expected", 0), ("measures_expected", -1), ("measures_expected", True),
    ("measures_expected", "1"), ("measures_witnessed", 2), ("native_frames_checked", 2)])
def test_malformed_score_or_window_counters_are_diagnostic(tmp_path, key, value):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: data["scores"][0].update({key: value}))
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("mutate", [
    lambda score: score["windows"].append(deepcopy(score["windows"][0])),
    lambda score: score.update(measures_expected=2, measures_witnessed=2),
    lambda score: score["windows"][0].update(first_bar=0),
    lambda score: score["windows"][0].update(last_bar=2),
    lambda score: score["windows"][0].pop("first_bar"),
    lambda score: score["windows"][0].update(last_bar=False),
])
def test_reported_totals_cannot_hide_missing_duplicate_or_invalid_windows(tmp_path, mutate):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: mutate(data["scores"][0]))
    result = _aggregate(tmp_path)
    assert not result["passed"]
    assert any("window" in error.lower() or "measure" in error.lower() for error in result["errors"])


@pytest.mark.parametrize("key,value", [
    ("measure_count", 0), ("sampled_measures", 0), ("screenshot_count", 0),
    ("source_noteheads", -1), ("unique_rendered_noteheads", 2),
    ("unique_rendered_rests", None), ("unexpected_notes", ["extra"]),
    ("missing_rests", ["rest1"]), ("missing_measure_starts", None),
    ("independent_image_pitch", {}), ("independent_image_rests", None),
])
def test_missing_evidence_and_malformed_window_counts_cannot_pass(tmp_path, key, value):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: _witness(data).update({key: value}))
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("proof,expected,verified", [
    ("independent_image_pitch", "written_active_noteheads", "image_pitch_verified"),
    ("independent_image_rests", "written_active_rests", "image_rest_glyphs_verified"),
])
@pytest.mark.parametrize("bad", [None, -1, True, "1", 2])
def test_pixel_counter_equality_does_not_accept_bad_or_inconsistent_counts(tmp_path, proof, expected, verified, bad):
    _complete(tmp_path)
    def mutate(data):
        _witness(data)[proof].update({expected: bad, verified: bad})
    _edit(tmp_path, mutate)
    assert not _aggregate(tmp_path)["passed"]


def test_contour_ambiguity_cannot_be_presented_as_verified_rest_identity(tmp_path):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: _witness(data)["independent_image_rests"].update(
        intrinsically_indistinguishable_half_whole=1))
    result = _aggregate(tmp_path)
    assert not result["passed"]
    assert any("ambig" in error.lower() for error in result["errors"])


def test_pitch_and_rest_success_cannot_claim_all_notation_without_ledger(tmp_path):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: data.update(elements=[]))
    result = _aggregate(tmp_path)
    assert not result["complete"]
    assert "pitch/rest" in result["coverage_claim"]


def test_visual_and_canonical_ledgers_must_agree(tmp_path):
    _complete(tmp_path)
    _edit(tmp_path, lambda data: data["scores"][0]["visual_elements"].pop())
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("mutate", [
    lambda data: data["scores"][0]["windows"][0].pop("visual_elements"),
    lambda data: data["scores"][0]["windows"][0]["visual_elements"].pop(),
    lambda data: _witness(data).update(elements=[]),
    lambda data: data["scores"][0]["windows"][0]["visual_elements"][0]["source"].update(measure_index=2),
])
def test_window_ledgers_must_account_for_canonical_visual_evidence(tmp_path, mutate):
    _complete(tmp_path)
    _edit(tmp_path, mutate)
    assert not _aggregate(tmp_path)["passed"]


@pytest.mark.parametrize("hand,proof,expected,verified", [
    ("right", "independent_image_pitch", "written_active_noteheads", "image_pitch_verified"),
    ("left", "independent_image_rests", "written_active_rests", "image_rest_glyphs_verified"),
])
def test_zero_pixel_counts_cannot_hide_active_hand_elements(tmp_path, hand, proof, expected, verified):
    _complete(tmp_path)
    path = _path(tmp_path, hand=hand)
    data = json.loads(path.read_text())
    _witness(data)[proof].update({expected: 0, verified: 0})
    _save(tmp_path, data, hand=hand)
    assert not _aggregate(tmp_path)["passed"]


def test_wrong_source_hash_cannot_earn_verified_element_credit(tmp_path):
    _complete(tmp_path, kind="semantic")
    before = _aggregate(tmp_path, "semantic")["coverage"]["verified"]
    data = json.loads(_path(tmp_path, kind="semantic").read_text())
    count = len(data["elements"])
    data["source_sha256"] = "0" * 64
    _save(tmp_path, data, kind="semantic")
    result = _aggregate(tmp_path, "semantic")
    assert result["coverage"]["verified"] == before - count
    assert result["coverage"]["unverified"] == count


@pytest.mark.parametrize("kind", ["semantic", "visual"])
def test_omitting_original_constructs_cannot_shrink_the_denominator(tmp_path, kind):
    _complete(tmp_path, kind=kind)
    def mutate(data):
        data["elements"] = [row for row in data["elements"]
                            if row["construct"] not in ("beams", "note_rhythm")]
        data["coverage"].update(expected=len(data["elements"]), verified=len(data["elements"]))
        if kind == "visual":
            data["scores"][0].update(visual_elements=deepcopy(data["elements"]),
                                     visual_coverage=deepcopy(data["coverage"]))
    _edit(tmp_path, mutate, kind=kind)
    result = _aggregate(tmp_path, kind)
    assert not result["passed"]
    assert any("source inventory" in error for error in result["errors"])
    assert any(row["construct"] in ("beams", "note_rhythm") for row in result["unverified_elements"])


@pytest.mark.parametrize("kind", ["semantic", "visual"])
def test_required_source_binding_cannot_be_reassigned_while_retaining_id(tmp_path, kind):
    _complete(tmp_path, kind=kind)
    def mutate(data):
        data["elements"][0]["source"]["id"] = "different-original"
        if kind == "visual":
            data["scores"][0]["visual_elements"] = deepcopy(data["elements"])
    _edit(tmp_path, mutate, kind=kind)
    result = _aggregate(tmp_path, kind)
    assert not result["passed"]
    assert any("source inventory" in error for error in result["errors"])


@pytest.mark.parametrize("kind", ["semantic", "visual"])
def test_midi_written_transcription_cannot_be_called_verified(tmp_path, monkeypatch, kind):
    # A literal minimal SMF: one quarter-note C4, independently paired release.
    source = "single.midi"
    path = aggregation.ROOT / "midi" / source
    path.parent.mkdir(parents=True)
    path.write_bytes(bytes.fromhex(
        "4d54686400000006000000010060"
        "4d54726b0000000c00903c4060803c0000ff2f00"))
    monkeypatch.setattr(aggregation, "PINNED_SOURCES", (source,))
    for hand in HANDS:
        required = (semantic_inventory(path) if kind == "semantic" else
                    visual_inventory(None, hand, source_name=source))
        elements = [{**row, "status": "verified"} for row in required]
        data = {"schema_version": 1, "verification_kind": kind,
                "source_index": 0, "source": source, "source_sha256": sha256(path.read_bytes()).hexdigest(),
                "hand": hand, "passed": True, "complete": True, "elements": elements,
                "coverage": {"expected": len(elements), **{s: len(elements) if s == "verified" else 0 for s in STATUSES}}}
        _save(tmp_path, data, hand=hand, kind=kind)
    result = aggregate(tmp_path, scores=1, kind=kind)
    assert not result["passed"]
    assert any("MIDI" in error and "unsupported" in error for error in result["errors"])
    assert any(row["construct"] == "midi_written_transcription" for row in result["unverified_elements"])


def test_cli_writes_a_blocked_report_for_missing_corpus(tmp_path):
    out = tmp_path / "diagnostics" / "report.json"
    run = subprocess.run([
        sys.executable, str(ROOT / "scripts/aggregate_phase3_corpus.py"),
        "--root", str(tmp_path), "--out", str(out), "--kind", "semantic",
    ], capture_output=True, text=True, cwd=ROOT)
    assert run.returncode == 1, run.stderr
    result = json.loads(out.read_text())
    assert result["required_jobs"] == 51
    assert result["status"] == "blocked"
    assert len(result["jobs"]) == 51
    assert all(job["coverage"]["expected"] > 0 for job in result["jobs"])
    assert result["coverage"]["expected"] == result["coverage"]["unverified"] > 0
    assert len(result["unverified_elements"]) == result["coverage"]["expected"]
