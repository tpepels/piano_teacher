"""Fast offline RubricNet integration tests; no heavy model worker in CI."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from piano_teacher.exercise_strategies import (
    RubricNetTrainedStrategy, ExerciseContext, resolve_strategy, available_strategies,
)
from piano_teacher.learning import LearningPlan
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.research.rubricnet_assets import BASIC_FEATURES, UPSTREAM_COMMIT
from piano_teacher.research.rubricnet_extractor import (
    RubricNetExtractor, RubricNetUnavailable, VENDOR_ROOT,
)
from piano_teacher.server import PracticeEngine


VENDORED_BLOBS = {
    "bayesian_model.py": "4105807690ba05412793d1a75e074c73c9faeaeb",
    "clefs_signatures.py": "47f06140b4220dd9b1a9d27ed361a0248ac9d4c0",
    "common_utils.py": "a8629ea94ec9b3a127a658f67e47cc250a6953bd",
    "difficulty_calculators.py": "67b8a92e502d06cb9ea0a6fbe285b5265704e36d",
    "keys_features.py": "ee61c4e9204766d8faa264d7820309c059ea7731",
    "performance_chain.py": "96fd0310e59c961a9bc518935f3787d2569a6dee",
    "raw_data_extractors.py": "2e676bd55f7bdeea5e3837c6749686962e69a7cc",
    "rhythm_chart.py": "7069436e2c2aa66e192a826c03f7d48e29ffca28",
    "rhythm_chart_new.py": "8cb7b83add1ac12621f0f99fa7c41b1845f9c91a",
    "piano_fingering_argnn/GGCN.py": "ab3a065d5e58ad15d4d1140133a83f0326b08425",
    "piano_fingering_argnn/common.py": "f83bbf96417dd40805aaab779804d0437570e1aa",
    "piano_fingering_argnn/compute_embeddings.py": "b44e36d117eb44f872e22ba9792394650d1b70b0",
    "piano_fingering_argnn/seq2seq_model.py": "6186ccf7e9c3f2890eb17d6d2e8b5903d27436a9",
    "piano_fingering_argnn/utils.py": "7acbcbe02a423b66fa3db0a137bea4d614954b40",
}


def score():
    notes = tuple(
        Note(i * .5, i * .5 + .4, 60+i, 0, 0, "right", f"s-{i}", "v1")
        for i in range(8))
    phrase = Phrase(1, 1, 1, 0, 4, notes)
    return Piece("Model score", 80, notes, (phrase,),
                 bar_boundaries=(0, 4), source_musicxml="<score-partwise/>")


def test_vendored_extractor_matches_all_original_git_blobs():
    folder = VENDOR_ROOT / "extractor" / "DifficultyFeatures" / "code"
    for path, reference_sha in VENDORED_BLOBS.items():
        content = (folder / path).read_bytes()
        digest = hashlib.sha1(b"blob " + str(len(content)).encode() +
                              b"\0" + content).hexdigest()
        assert digest == reference_sha, path


def test_trained_strategy_keeps_independent_profile_and_original_source(monkeypatch):
    import piano_teacher.exercise_strategies as strategies
    monkeypatch.setattr(
        strategies, "_trained_rubricnet_from_xml",
        lambda xml: RubricNetTrainedStrategy(SimpleNamespace(median_class=4)))
    piece = score()
    plan = LearningPlan(piece, exercise_strategy="rubricnet-trained")
    assert plan.profile == "rubricnet-trained"
    assert plan.variants[-1].notes == piece.notes
    assert plan.exercise_strategy.name == "rubricnet-trained"
    assert any(entry["id"] == "rubricnet-trained"
               for entry in available_strategies())
    assert LearningPlan(piece).exercise_strategy.name == "legacy"
    assert plan.identity != LearningPlan(piece).identity


@pytest.mark.parametrize("difficulty,expected", [
    (1, "baseline"), (4, "coda"), (7, "combined"),
])
def test_trained_class_uses_explicit_not_learned_exercise_policy(difficulty, expected):
    phrase = score().phrases[0]
    context = ExerciseContext(phrase, "right")
    obj = RubricNetTrainedStrategy(SimpleNamespace(median_class=difficulty))
    source = tuple(range(len(phrase.notes)))
    def baseline():
        from piano_teacher.exercise_generator import ExerciseVariant
        return (ExerciseVariant("original", phrase, source),)
    variants = obj.generate(context, baseline)
    assert variants[-1].level == "original"
    assert variants[-1].notes == phrase.notes
    if expected == "baseline":
        assert len(variants) == 1
    else:
        assert variants[0].level.startswith(expected)


def test_missing_worker_fails_without_heuristic_fallback(monkeypatch, tmp_path):
    import piano_teacher.research.rubricnet_extractor as extractor
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing python")
    monkeypatch.setattr(extractor.subprocess, "run", missing)
    with pytest.raises(RubricNetUnavailable, match="could not run"):
        RubricNetExtractor(python_executable="/nonexistent/python").extract(
            "<score-partwise/>")
    with pytest.raises(RubricNetUnavailable, match="original MusicXML"):
        RubricNetExtractor().extract("")


def test_invalid_worker_response_is_never_relabelled_as_trained(monkeypatch):
    import piano_teacher.research.rubricnet_extractor as extractor
    payload = {"commit": UPSTREAM_COMMIT,
               "features": {name: 1 for name in BASIC_FEATURES[:-1]}}
    monkeypatch.setattr(extractor.subprocess, "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout="RUBRICNET_FEATURES=" + json.dumps(payload),
            stderr=""))
    with pytest.raises(RubricNetUnavailable, match="Invalid worker feature"):
        RubricNetExtractor().extract("<score-partwise/>")


def test_failed_trained_selection_cannot_change_persisted_settings_or_progress(
        monkeypatch, tmp_path):
    import piano_teacher.exercise_strategies as strategies
    engine = PracticeEngine(tmp_path, enable_midi=False)
    try:
        engine.plan = LearningPlan(score())
        engine.fingerprint = "unchanged-score"
        before = engine.plan.identity
        def unavailable(_):
            raise RubricNetUnavailable("missing research environment")
        monkeypatch.setattr(strategies, "_trained_rubricnet_from_xml", unavailable)
        with pytest.raises(RubricNetUnavailable):
            engine.set_preferences(exercise_strategy="rubricnet-trained")
        assert engine.library.settings["exercise_strategy"] == "coda-part"
        assert engine.plan.identity == before
        assert engine.plan.mastered == {}
        assert engine.library.settings["exercise_strategy"] != "rubricnet-trained"
    finally:
        engine.db.close()
