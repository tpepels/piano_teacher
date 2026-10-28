"""Selected-source artifacts own compilation, identity and bounded caches."""
from dataclasses import FrozenInstanceError, replace

import pytest

from piano_teacher.application import score_artifacts
from piano_teacher.music import Note, Phrase, Piece
from piano_teacher.preprocessing_cache import PreprocessingCache
from piano_teacher.rendering.legacy.engraving import EngravedScore


@pytest.fixture
def artifacts_api():
    return score_artifacts


@pytest.fixture
def selected(artifacts_api):
    notes = (Note(0, 1, 60, 0, 0, "right", "source-r"),
             Note(4, 5, 48, 1, 0, "left", "source-l"))
    phrase = Phrase(1, 1, 2, 0, 8, notes)
    piece = Piece("Selected source", 100, notes, (phrase,),
                  bar_boundaries=(0, 4, 8), time_signatures=((0, 4, 4),))
    return artifacts_api.ScoreSelection(piece=piece, phrase=phrase, hand="both",
        stage_key="stage-both", revision=7, fingerprint="source-bytes")


@pytest.fixture
def rendering(artifacts_api, monkeypatch):
    rendered = []

    def render(notation, first, last, hand, *, total_beats, bpm, continuous):
        rendered.append((notation, first, last, hand, bpm, continuous))
        glyphs = [{**binding, "id": identifier, "beat": binding["display_beat"],
                   "x": .25, "y": .5, "page": 0}
                  for identifier, binding in notation.note_bindings.items()]
        layout = {"pages": 1, "beats": total_beats, "notes": glyphs,
                  "mapping_schema": "source-note-v1",
                  "attack_map": {g["source_id"]: g["id"] for g in glyphs if g["is_attack"]},
                  "continuation_map": {}, "continuous_score": continuous}
        return EngravedScore(("<svg>selected source</svg>",), layout)

    monkeypatch.setattr(artifacts_api, "render_layout", render)
    return rendered


def test_one_selected_compilation_feeds_semantics_engraving_and_native_assets(
        artifacts_api, selected, rendering, tmp_path, monkeypatch):
    from piano_teacher.application import score_preparation
    compile_lesson = artifacts_api.build_lesson_score
    compiled = []

    def compile_once(*args, **kwargs):
        notation = compile_lesson(*args, **kwargs)
        compiled.append(notation)
        return notation

    def assemble(score, **kwargs):
        return {"revision": kwargs["revision"], "xml": kwargs["notation_xml"],
                "notes": kwargs["native_model"]["notes"], "pages": score.pages}

    monkeypatch.setattr(artifacts_api, "build_lesson_score", compile_once)
    monkeypatch.setattr(score_preparation, "assemble_layout", assemble)
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    semantic = owner.semantic_score(selected)
    engraving = owner.engraving(selected)
    geometry = owner.geometry(selected)
    assert {note["id"] for note in semantic["notes"]} == {"source-r", "source-l"}
    assert geometry["notes"] == semantic["notes"] and geometry["revision"] == 7
    assert len(compiled) == 1 and rendering[0][0] is compiled[0]
    assert geometry["xml"] == compiled[0].musicxml
    assert geometry["pages"] == engraving.pages
    assert owner.cached_layout(selected) is engraving
    assert rendering[0][1:] == (1, 2, "both", 100, True)
    with pytest.raises(FrozenInstanceError):
        selected.hand = "left"


def test_semantic_reads_are_isolated_and_never_engrave(
        artifacts_api, selected, rendering, tmp_path):
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    first = owner.semantic_score(selected)
    first["notes"].clear()
    first["practice_timeline"]["gap"]["duration_beats"] = 99
    second = owner.semantic_score(selected)
    assert {note["id"] for note in second["notes"]} == {"source-r", "source-l"}
    assert second["practice_timeline"]["gap"]["duration_beats"] == 4
    assert rendering == [] and owner.cached_layout(selected) is None


def test_same_revision_fragments_and_replaced_source_do_not_share_artifacts(
        artifacts_api, selected, rendering, tmp_path):
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    whole = owner.semantic_score(selected)
    owner.engraving(selected)
    phrase = Phrase(2, 2, 2, 4, 8, (selected.piece.notes[1],))
    fragment = replace(selected, phrase=phrase)
    assert owner.cached_layout(fragment) is None
    fragment_model = owner.semantic_score(fragment)
    assert fragment_model["first_bar"] == 2 and fragment_model["duration_beats"] == 4
    assert [note["id"] for note in fragment_model["notes"]] == ["source-l"]
    assert len(whole["notes"]) == 2
    owner.engraving(fragment)
    changed_note = replace(phrase.notes[0], pitch=50, source_id="replacement")
    changed_phrase = replace(phrase, notes=(changed_note,))
    changed = replace(fragment, piece=replace(selected.piece, notes=(changed_note,)),
                      phrase=changed_phrase, fingerprint="different-source")
    assert owner.cached_layout(changed) is None
    assert [note["id"] for note in owner.semantic_score(changed)["notes"]] == ["replacement"]
    owner.engraving(changed)
    assert len(rendering) == 3


@pytest.mark.parametrize("changes", [
    {"revision": 8}, {"hand": "left"}, {"stage_key": "another-stage"},
    {"fingerprint": "different-source-bytes"},
])
def test_selection_identity_keeps_source_hand_stage_and_revision_distinct(
        artifacts_api, selected, rendering, tmp_path, changes):
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    owner.engraving(selected)
    changed = replace(selected, **changes)
    assert owner.cached_layout(changed) is None
    assert owner.semantic_score(changed)["revision"] == changed.revision
    assert owner.cached_layout(changed) is None  # Semantic reads cannot relabel old ink.
    fresh = owner.engraving(changed)
    assert owner.cached_layout(changed) is fresh


def test_persisted_engraving_and_png_reuse_survive_owner_replacement(
        artifacts_api, selected, rendering, tmp_path, monkeypatch):
    raster_calls = []

    def raster(svg, *, width=2000):
        raster_calls.append((svg, width))
        return b"\x89PNG\r\n\x1a\n"+str(width).encode()

    monkeypatch.setattr(artifacts_api, "rasterize_score", raster)
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    first = owner.engraving(selected)
    png = owner.engraved_png(selected)
    assert owner.engraved_png(selected) == png
    assert owner.engraved_png(selected, width=3000) != png
    assert owner.engraved_png(selected) == png
    again = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    assert again.engraving(selected) == first
    assert again.engraved_png(selected) == png
    assert len(rendering) == 1 and len(raster_calls) == 2


def test_corrupt_cached_source_binding_is_rejected_and_rebuilt(
        artifacts_api, selected, rendering, tmp_path):
    cache = PreprocessingCache(tmp_path)
    owner = artifacts_api.ScoreArtifacts(cache)
    first = owner.engraving(selected)
    broken = {**first.layout, "attack_map": {}}
    cache.write_json("engraving", owner.engraving_cache_key,
                     {"pages": list(first.pages), "layout": broken})
    again = artifacts_api.ScoreArtifacts(cache)
    restored = again.engraving(selected)
    assert restored.layout["attack_map"] == first.layout["attack_map"]
    assert len(rendering) == 2


def test_invalidation_clears_memory_and_reuses_durable_source_ink(
        artifacts_api, selected, rendering, tmp_path):
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    original_model = owner.source_model(selected)
    original = owner.engraving(selected)
    key = owner.engraving_cache_key
    assert not owner.source_bpm_changed(100)
    assert owner.source_bpm_changed(101)
    owner.invalidate()
    assert owner.cached_layout(selected) is None and owner.engraving_cache_key is None
    assert not owner.source_bpm_changed(101)
    advanced = replace(selected, revision=8)
    assert owner.source_model(advanced) is not original_model
    assert owner.semantic_score(advanced)["revision"] == 8
    assert owner.engraving(advanced) == original
    assert owner.engraving_cache_key == key and len(rendering) == 1


def test_image_bounds_and_reference_layout_keep_the_existing_contract(
        artifacts_api, selected, rendering, tmp_path, monkeypatch):
    from piano_teacher.application import score_preparation
    owner = artifacts_api.ScoreArtifacts(PreprocessingCache(tmp_path))
    monkeypatch.setattr(score_preparation, "assemble_layout",
        lambda score, **kwargs: {"revision": kwargs["revision"], "native": kwargs["native_notes"]})
    assert owner.geometry(selected, native_notes=False) == {"revision": 7, "native": False}
    assert owner.engraved(selected) == "<svg>selected source</svg>"
    with pytest.raises(ValueError, match="Invalid score page"):
        owner.engraved(selected, 1)
    with pytest.raises(ValueError, match="width"):
        owner.engraved_png(selected, width=599)
    with pytest.raises(ValueError, match="width"):
        owner.engraved_png(selected, width=12001)
    with pytest.raises(ValueError, match="Invalid score page"):
        owner.engraved_png(selected, 1)
