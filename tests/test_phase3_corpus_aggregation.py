"""Phase 3 full-corpus result cannot pass without every independent witness."""
import json

from scripts.aggregate_phase3_corpus import HANDS, aggregate


def _report(tmp_path, index, hand, *, score=None, pixel_passed=True):
    where=tmp_path/f"phase3-report-{index}-{hand}"
    where.mkdir(exist_ok=True)
    note_count=2 if hand=="both" else 1
    data={
        "passed":True,"scores_total":2,"hand":hand,
        "scores_attempted":[score or f"source-{index}.musicxml"],
        "scores_passed":1,"scores_failed":[],
        "scores":[{
            "passed":True,
            "measures_expected":1,
            "measures_witnessed":1,
            "independent_original_musicxml":{"passed":True},
            "independent_generated_symbol_inventory":{"passed":True},
            "windows":[{"first_bar":1,"last_bar":1,
                "whole_window_coverage":{
                    "missing_notes":[],"missing_rests":[],
                    "missing_measure_starts":[],
                    "independent_image_pitch":{
                        "passed":pixel_passed,
                        "written_active_noteheads":note_count,
                        "image_pitch_verified":note_count,
                    },
                }
            }],
        }],
    }
    (where/"summary.json").write_text(json.dumps(data))
    return data


def _complete(tmp_path):
    for index in (0,1):
        for hand in HANDS:
            _report(tmp_path,index,hand)


def test_exact_all_scores_and_hands_must_be_present(tmp_path):
    _complete(tmp_path)
    report=aggregate(tmp_path,scores=2)
    assert report["passed"],report["errors"]
    assert report["jobs_with_results"]==6


def test_missing_single_hand_job_fails_closed(tmp_path):
    _complete(tmp_path)
    (tmp_path/"phase3-report-1-left"/"summary.json").unlink()
    report=aggregate(tmp_path,scores=2)
    assert not report["passed"]
    assert any("1/left" in e for e in report["errors"])


def test_wrong_hand_or_inconsistent_score_name_is_detected(tmp_path):
    _complete(tmp_path)
    _report(tmp_path,0,"left",score="not-original.musicxml")
    report=aggregate(tmp_path,scores=2)
    assert not report["passed"]
    assert any("changed among modes" in e for e in report["errors"])


def test_partial_pixel_verification_or_failed_original_is_detected(tmp_path):
    _complete(tmp_path)
    _report(tmp_path,0,"both",pixel_passed=False)
    data=json.loads((tmp_path/"phase3-report-1-right"/"summary.json").read_text())
    data["scores"][0]["independent_original_musicxml"]["passed"]=False
    (tmp_path/"phase3-report-1-right"/"summary.json").write_text(json.dumps(data))
    result=aggregate(tmp_path,scores=2)
    assert not result["passed"]
    assert any("original MusicXML" in error for error in result["errors"])
    assert any("independent raster pitch" in error for error in result["errors"])


def test_unverified_count_is_detected_even_with_passed_flag(tmp_path):
    _complete(tmp_path)
    path=tmp_path/"phase3-report-0-both"/"summary.json"
    data=json.loads(path.read_text())
    data["scores"][0]["windows"][0]["whole_window_coverage"][
        "independent_image_pitch"]["image_pitch_verified"]=0
    path.write_text(json.dumps(data))
    assert not aggregate(tmp_path,scores=2)["passed"]
