"""A trial uses the ordinary learning plan and never inherits source mastery."""
from pathlib import Path
import pytest

from piano_teacher.application.coda_trial import prepare_coda_trial
from piano_teacher.learning import LearningPlan
from piano_teacher.music import load_midi

SOURCE=Path(__file__).parent/"fixtures/musical_fidelity/midi_three_four.mid"


def test_trial_is_source_isolated_and_respects_later_measure():
    source=LearningPlan(load_midi(SOURCE))
    identity=source.identity
    trial,plan=prepare_coda_trial(
        source,source_fingerprint="source-sha",
        first_bar=2,last_bar=2,family="tempo-shaping")
    assert trial.source_plan is source
    assert trial.source_fingerprint=="source-sha"
    assert trial.fingerprint!="source-sha"
    assert trial.passage.first_bar==2
    assert trial.passage.source_start==3
    assert plan.piece.bar_boundaries==(0,3,6)
    assert {n.source_id for n in plan.piece.notes}==trial.passage.original_source_ids
    assert plan.piece.source_musicxml==""
    assert source.identity==identity
    # The source has two 3/4 measures; the selected second bar happens
    # to double to the same *length* and meter grid. Attack identity
    # and absolute origin, not unequal barlines, prove source isolation.
    assert source.piece is not plan.piece
    assert source.piece.notes != plan.piece.notes
    assert trial.passage.source_start == 3
    assert plan.exercise_strategy.name=="legacy"


def test_repeat_selection_has_deterministic_trial_fingerprint():
    source=LearningPlan(load_midi(SOURCE))
    first,plan=prepare_coda_trial(source,source_fingerprint="same",
        first_bar=2,last_bar=2,family="tempo-shaping")
    other,again=prepare_coda_trial(source,source_fingerprint="same",
        first_bar=2,last_bar=2,family="tempo-shaping")
    assert first.fingerprint==other.fingerprint
    assert plan.identity==again.identity


def test_invalid_midi_and_invalid_family_rejected_before_engine_mutation():
    source=LearningPlan(load_midi(SOURCE))
    with pytest.raises(ValueError,match="Choose"):
        prepare_coda_trial(source,source_fingerprint="x",
            first_bar=2,last_bar=2,family="invalid")
    with pytest.raises(ValueError,match="eight"):
        prepare_coda_trial(source,source_fingerprint="x",
            first_bar=1,last_bar=9,family="tempo-shaping")
