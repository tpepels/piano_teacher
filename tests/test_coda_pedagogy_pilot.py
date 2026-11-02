"""Independent real-player pilot logic; synthetic tests prove only analysis."""
from dataclasses import replace
import pytest

from piano_teacher.research.coda_pedagogy_pilot import (
    PROTOCOL, PilotObservation, analyze_pilot, assigned_arm,
)

SECRET="a-fixed-test-secret-not-to-use-with-humans"


def samples():
    result=[]
    for piece,bpm,notes in (("piece-one",80,100),("piece-two",70,40)):
        chosen={"A":[],"B":[]}
        for i in range(200):
            subject=f"anonymous-{piece}-{i}"
            arm=assigned_arm(subject,piece,secret=SECRET)
            if len(chosen[arm])<4:
                chosen[arm].append(subject)
            if all(len(v)==4 for v in chosen.values()):
                break
        assert all(len(v)==4 for v in chosen.values())
        for arm,people in chosen.items():
            for i,subject in enumerate(people):
                pre=(25+i) if notes==100 else 10+i
                post=pre+(10 if arm=="A" else 5)
                result.append(PilotObservation(
                    subject,piece,arm,notes,bpm,pre,0,post,0,15.0,
                    "grading-v1"))
    return tuple(result)


def test_assignment_is_blinded_stable_and_piece_stratified():
    assert assigned_arm("a","piece",secret=SECRET)==assigned_arm(
        "a","piece",secret=SECRET)
    assert {assigned_arm(f"player-{i}","one",secret=SECRET)
            for i in range(100)}=={"A","B"}
    with pytest.raises(ValueError,match="anonymous"):
        assigned_arm("","p",secret=SECRET)


def test_paired_piece_stratified_analysis_has_provenance_not_false_claim():
    rows=samples()
    result=analyze_pilot(rows,secret=SECRET)
    assert result["protocol"]==PROTOCOL
    assert result["observations"]==16
    assert len(result["pieces"])==2
    assert result["blinded"] is True
    assert result["arm_A_minus_B_gain"]>0
    assert 0<=result["within_piece_label_permutation_p"]<=1
    assert result["permutation_draws"]==70*70
    assert "independent human efficacy claim requires" in result["study_conclusion"]
    assert "physical-MIDI" in result["source"]


def test_tampered_assignment_and_wrong_secret_are_rejected():
    rows=list(samples())
    rows[0]=replace(rows[0],blinded_arm=("B" if rows[0].blinded_arm=="A" else "A"))
    with pytest.raises(ValueError,match="randomized allocation"):
        analyze_pilot(tuple(rows),secret=SECRET)
    with pytest.raises(ValueError,match="randomized allocation"):
        analyze_pilot(samples(),secret="different-secret-from-real")


def test_nonphysical_and_nonstandard_original_score_do_not_enter_study():
    r=samples()[0]
    with pytest.raises(ValueError,match="physical-MIDI"):
        replace(r,instrument="synthetic")
    with pytest.raises(ValueError,match="physical-MIDI"):
        replace(r,completed_original_score=False)
    with pytest.raises(ValueError,match="exceeds"):
        replace(r,post_correct=101)
    with pytest.raises(ValueError,match="Invalid note"):
        replace(r,pre_correct=-1)


def test_assessment_and_exposure_must_match_within_piece():
    rows=list(samples())
    rows[0]=replace(rows[0],test_bpm=90)
    with pytest.raises(ValueError,match="BPM differs"):
        analyze_pilot(tuple(rows),secret=SECRET)
    rows=list(samples())
    rows[0]=replace(rows[0],practice_minutes=12.0)
    with pytest.raises(ValueError,match="exposure"):
        analyze_pilot(tuple(rows),secret=SECRET)
    rows=list(samples())
    rows[0]=replace(rows[0],assessment_version="grading-v2")
    with pytest.raises(ValueError,match="version differs"):
        analyze_pilot(tuple(rows),secret=SECRET)
    with pytest.raises(ValueError,match="Duplicate subject-piece"):
        analyze_pilot(samples()+(samples()[0],),secret=SECRET)


def test_one_armed_piece_or_no_data_is_not_called_comparison():
    with pytest.raises(ValueError,match="No real"):
        analyze_pilot((),secret=SECRET)
    rows=tuple(r for r in samples() if r.blinded_arm=="A")
    with pytest.raises(ValueError,match="Both arms"):
        analyze_pilot(rows,secret=SECRET)
