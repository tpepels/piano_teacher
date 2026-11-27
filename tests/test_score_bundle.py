"""A4: active and future scores share one exact notation/source contract."""
from types import SimpleNamespace

import pytest

from piano_teacher.application.score_artifacts import ScoreArtifacts
from piano_teacher.application.score_selection import ScoreSelection


def _bundle_source(*, hand="right", notes=None, layout_revision=4,
                   model_revision=4, active_ids=("right-1",)):
    source = ScoreSelection(
        piece=object(),
        phrase=SimpleNamespace(notes=notes or (
            SimpleNamespace(source_id="right-1", hand="right"),
            SimpleNamespace(source_id="left-1", hand="left"),
        )),
        hand=hand, stage_key="stage:source", revision=4,
        fingerprint="source-sha")
    assets = ScoreArtifacts(None, source, {})
    assets.layout = {
        "revision": layout_revision, "anchors": {"right-1": {}}}
    assets.semantic = {
        "revision": model_revision, "active_note_ids": list(active_ids)}
    return assets


def test_bundle_binds_both_halves_to_one_source_and_original_note_ids():
    assets = _bundle_source()
    bundle = assets.bundle()
    assert bundle["status"] == "ready"
    assert (bundle["fingerprint"], bundle["revision"], bundle["stage_key"],
            bundle["hand"]) == ("source-sha", 4, "stage:source", "right")
    assert bundle["source_note_ids"] == ["right-1", "left-1"]
    assert bundle["layout"]["revision"] == bundle["model"]["revision"] == 4


@pytest.mark.parametrize("changed", [
    {"layout_revision": 5},
    {"model_revision": 5},
    {"active_ids": ("left-1",)},
    {"active_ids": ("right-1", "unrelated-note")},
    {"notes": (
        SimpleNamespace(source_id="right-1", hand="right"),
        SimpleNamespace(source_id="right-1", hand="left"),
    )},
])
def test_bundle_rejects_mixed_revisions_and_incorrect_authored_attack_ids(changed):
    assets = _bundle_source(**changed)
    with pytest.raises(ValueError, match="Score bundle"):
        assets.bundle()


def test_current_practice_source_exposes_single_ready_bundle(practice_session):
    session = practice_session(bars=1)
    state = session.snapshot()
    bundle = session.ask("score.bundle")
    assert bundle["status"] == "ready"
    assert bundle["revision"] == state["revision"]
    assert bundle["fingerprint"] == state["piece_fingerprint"]
    assert bundle["hand"] == state["hand"]
    assert bundle["layout"]["revision"] == bundle["model"]["revision"]
    assert bundle["model"]["active_note_ids"]
    assert set(bundle["model"]["active_note_ids"]).issubset(
        bundle["source_note_ids"])
    assert bundle["layout"].get("anchors") is not None
    assert session.ask("score.semantic") == bundle["model"]


def test_bundle_does_not_mutate_the_next_read_after_client_edits(practice_session):
    session = practice_session(bars=1)
    initial = session.ask("score.bundle")
    original_ids = list(initial["model"]["active_note_ids"])
    initial["model"]["active_note_ids"].clear()
    initial["layout"]["anchors"].clear()
    reread = session.ask("score.bundle")
    assert reread["model"]["active_note_ids"] == original_ids
    assert reread["layout"]["anchors"]


def test_active_bundle_source_changes_with_selected_practice_window(practice_session):
    session = practice_session(bars=3)
    first = session.ask("score.bundle")
    session.select(2, 2)
    second = session.ask("score.bundle")
    assert second["revision"] != first["revision"]
    assert second["stage_key"] != first["stage_key"]
    assert second["fingerprint"] == first["fingerprint"]
    assert second["source_note_ids"] != first["source_note_ids"]
