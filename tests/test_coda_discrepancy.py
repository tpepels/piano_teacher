"""Classification uses both source and reference evidence, never parity inference."""
import pytest

from piano_teacher.research.coda_differential import WrittenNote, SoundingNote
from piano_teacher.research.coda_discrepancy import explain_discrepancy, CAUSES


def _classify(case, *, ref_written, ours_written, ref_sound, ours_sound,
              source_sound=(), operation="slow-x2", errors=()):
    return explain_discrepancy(
        source_case=case, voice_index=0, operation=operation,
        reference_written=tuple(ref_written), native_written=tuple(ours_written),
        reference_sounding=tuple(ref_sound), adapter_sounding=tuple(ours_sound),
        source_sounding=tuple(source_sound), reference_tie_errors=tuple(errors))


def test_rest_coverage_is_written_only():
    played=(SoundingNote("v0",0,2,60),)
    ref=(WrittenNote("v0",0,2,60),)
    native=ref+(WrittenNote("v0",2,4,None),)
    diagnosis=_classify("source-parallel-ties",ref_written=ref,
        ours_written=native,ref_sound=played,ours_sound=played,source_sound=played)
    assert diagnosis.category=="rest-coverage-only"
    assert diagnosis.evidence["adapter_unchanged_from_source"]
    assert diagnosis.evidence["first_written_difference"]["reference"] is None
    assert diagnosis.evidence["native_rest_count"]==1


@pytest.mark.parametrize(("fixture","operation","category"),[
    ("source-authored-beams","dotted-3-to-1","beamed-source-protected"),
    ("long-multipage-first-two-bars","dotted-1-to-3","cross-measure-group-protected"),
    ("authored-triplet","chord-2-beat","tuplet-source-protected"),
    ("rest-bearing-triplet","dotted-3-to-1","rest-bearing-tuplet-protected"),
    ("changing-meter","chord-2-beat","changing-meter-cross-bar-chord"),
    ("changing-meter","dotted-3-to-1","changing-meter-dotted-quantization"),
])
def test_changed_sounding_timelines_remain_distinct(fixture,operation,category):
    ref=(SoundingNote("v0",0,2,60),)
    ours=(SoundingNote("v0",0,1,60),)
    diagnosis=_classify(fixture,operation=operation,
        ref_written=(WrittenNote("v0",0,2,60),),
        ours_written=(WrittenNote("v0",0,1,60),),
        ref_sound=ref,ours_sound=ours,source_sound=ours)
    assert diagnosis.category==category
    assert diagnosis.evidence["adapter_unchanged_from_source"]
    assert diagnosis.evidence["first_sounding_difference"]["reference"]["end"]==2


def test_missing_reference_pitch_is_preserved_as_evidence():
    original=(SoundingNote("v0",0,1,60),SoundingNote("v0",1,2,62))
    ref=(SoundingNote("v0",0,1,60),)
    result=_classify("rest-bearing-triplet",operation="dotted-3-to-1",
        ref_written=(WrittenNote("v0",0,1,60),),
        ours_written=(WrittenNote("v0",0,1,60),WrittenNote("v0",1,2,62)),
        ref_sound=ref,ours_sound=original,source_sound=original)
    assert result.evidence["missing_reference_pitches"]=={62:1}
    assert result.category=="rest-bearing-tuplet-protected"


def test_invalid_reference_tie_is_never_waived_as_sound_match():
    result=_classify("authored-triplet",operation="dotted-3-to-1",
        ref_written=(WrittenNote("v0",.666667,1,76,"start"),
                     WrittenNote("v0",2.5,2.666667,76,"stop")),
        ours_written=(WrittenNote("v0",.666667,1,76),),
        ref_sound=(),ours_sound=(SoundingNote("v0",.666667,1,76),),
        errors=("disconnected-tie:v0:76:2.5",))
    assert result.category=="upstream-disconnected-tie"
    assert result.evidence["reference_tie_errors"]==["disconnected-tie:v0:76:2.5"]


def test_notation_segmentation_and_unknown_cases():
    sound=(SoundingNote("v0",0,2,60),)
    ref=(WrittenNote("v0",0,1,60,"start"),WrittenNote("v0",1,2,60,"stop"))
    native=(WrittenNote("v0",0,2,60),)
    for fixture,expect in (("changing-meter","written-segmentation-meter"),
                           ("rest-bearing-triplet","written-segmentation-tuplet"),
                           ("unknown-fixture","unclassified")):
        result=_classify(fixture,ref_written=ref,ours_written=native,
            ref_sound=sound,ours_sound=sound,operation="slow-x2")
        assert result.category==expect
    with pytest.raises(ValueError,match="Exact parity"):
        _classify("unknown-fixture",ref_written=ref,ours_written=ref,
            ref_sound=sound,ours_sound=sound)


def test_every_category_has_an_explanation():
    assert all(message and "TODO" not in message for message in CAUSES.values())
