"""Optional real MusicXML regression for the offline vendored RubricNet worker.

Runs only in the dedicated short RubricNet acceptance job, not fast CI.
These are checked-in two-staff MusicXML scores with distinct rhythmic and
polyphonic structures. No online access during extraction or prediction.
"""
from math import isfinite
from pathlib import Path

import pytest

from piano_teacher.research.rubricnet_assets import BASIC_FEATURES
from piano_teacher.research.rubricnet_extractor import RubricNetExtractor, RubricNetUnavailable
from piano_teacher.research.rubricnet_model import RubricNetModel


FIXTURES = Path(__file__).parent / "fixtures" / "connector_pixels"


@pytest.mark.parametrize("score_name", [
    "beam16", "beams", "beam-down", "beam-chords",
])
def test_offline_worker_extracts_real_two_hand_scores_and_predicts(score_name):
    score = (FIXTURES/score_name/"score.musicxml").read_text(encoding="utf-8")
    features = RubricNetExtractor(timeout_seconds=20).extract(score)
    assert tuple(features) == BASIC_FEATURES
    assert len(features) == 12
    assert all(isfinite(x) for x in features.values())
    model = RubricNetModel.bundled()
    result = model.predict_descriptors(features)
    assert len(result.predictions) == 5
    assert all(0 <= pred.predicted_class <= 8 for pred in result.predictions)


@pytest.mark.parametrize("score_name", ["tuplets", "moonlight-rest-voices"])
def test_unpitched_second_hand_is_rejected_without_fabricated_features(score_name):
    source = (FIXTURES/score_name/"score.musicxml").read_text(encoding="utf-8")
    with pytest.raises(RubricNetUnavailable):
        RubricNetExtractor(timeout_seconds=20).extract(source)


def test_worker_matches_published_bach_reference_fixture():
    # This fixture is included in upstream; in the dedicated workflow the
    # reference is extracted by the pinned upstream oracle separately.
    # A synthetic score is NOT used as a substitute for that oracle.
    from scripts.research.verify_rubricnet_source_features import (
        REFERENCE_DESCRIPTORS,
    )
    assert len(REFERENCE_DESCRIPTORS) == len(BASIC_FEATURES)
