"""Selected notation and source engraving, independent of session state.

The application serializes calls under its existing lock. This owner receives
source values, never an engine, learning plan, transport or renderer callback.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import os
import time
from dataclasses import dataclass

from ..fingering.projection import authored_projection_sources, project_model
from ..lesson_validation import require_lesson_alignment
from ..music import Phrase, Piece
from ..notation.lesson import (LessonScore, build_lesson_score,
                               infer_piece_clefs, infer_midi_clef_plan)
from ..notation.model import build_score_model
from ..preprocessing_cache import PreprocessingCache
from ..engraving.engraving import EngravedScore, render_layout
from . import score_preparation


@dataclass(frozen=True)
class ScoreSelection:
    piece: Piece
    phrase: Phrase
    hand: str
    stage_key: str
    revision: int
    fingerprint: str
    transformed_rhythm: bool = False
    display_name: str = ""

    @property
    def identity(self) -> tuple:
        phrase = self.phrase
        return (id(self.piece), self.fingerprint, self.stage_key, self.hand,
                self.transformed_rhythm, self.revision,
                phrase.first_bar, phrase.last_bar, phrase.start, phrase.end)


class ScoreArtifacts:
    def __init__(self, preprocessing: PreprocessingCache):
        self.preprocessing = preprocessing
        self.invalidate()

    def invalidate(self) -> None:
        """Discard selected artifacts; durable, source-keyed entries remain reusable."""
        self._notation_identity: tuple | None = None
        self._notation: LessonScore | None = None
        self._model: dict | None = None
        self._projected_model: dict | None = None
        self._prepared_layout_identity: tuple | None = None
        self._prepared_layout: dict | None = None
        self._layout_identity: tuple | None = None
        self._layout: EngravedScore | None = None
        self._layout_source_bpm: float | None = None
        self._layout_key: str | None = None

    def _selected_notation(self, selected: ScoreSelection) -> LessonScore:
        if selected.identity != self._notation_identity or self._notation is None:
            piece = selected.piece
            notation = build_lesson_score(
                selected.phrase, boundaries=piece.bar_boundaries,
                time_signatures=piece.time_signatures,
                key_signatures=piece.key_signatures,
                clef_changes=piece.clef_changes,
                default_clefs=infer_piece_clefs(piece.notes),
                inferred_clefs=(infer_midi_clef_plan(piece.notes, piece.bar_boundaries)
                                if not piece.source_musicxml else None),
                barlines=piece.barlines,
                # Source slurs/rests use the original event clock. Retimed
                # drills must engrave their actual durations instead.
                source_musicxml=piece.source_musicxml,
                retimed_source=selected.transformed_rhythm,
                fingering_sources=authored_projection_sources(piece.fingering_plan))
            self._notation = notation
            self._notation_identity = selected.identity
            self._model = None
            self._projected_model = None
        return self._notation

    def notation_musicxml(self, selected: ScoreSelection) -> str:
        """The exact selected lesson XML, shared with model and engraving."""
        return self._selected_notation(selected).musicxml

    def source_model(self, selected: ScoreSelection) -> dict:
        """Internal source contract; the command queue publishes a semantic snapshot."""
        notation = self._selected_notation(selected)
        if self._model is None:
            self._model = build_score_model(notation,
                boundaries=selected.piece.bar_boundaries,
                hand=selected.hand, revision=selected.revision)
        return self._model

    def semantic_score(self, selected: ScoreSelection) -> dict:
        # Native geometry needs this exact projection, then score.semantic
        # requests it again. Build the source/fingering mapping once for a
        # selected stage and revision; return isolated snapshots to consumers.
        source = self.source_model(selected)
        if self._projected_model is None:
            self._projected_model = project_model(deepcopy(source),
                selected.piece.fingering_plan,
                source_musicxml=selected.piece.source_musicxml)
        return deepcopy(self._projected_model)

    def cached_layout(self, selected: ScoreSelection) -> EngravedScore | None:
        """Feedback may read only ink belonging to this exact source selection."""
        return self._layout if self._layout_identity == selected.identity else None

    def source_bpm_changed(self, source_bpm: float) -> bool:
        return self._layout is not None and self._layout_source_bpm != source_bpm

    @property
    def engraving_cache_key(self) -> str | None:
        return self._layout_key

    def engraving(self, selected: ScoreSelection) -> EngravedScore:
        if self.cached_layout(selected) is not None:
            return self._layout
        piece, phrase = selected.piece, selected.phrase
        notation = self._selected_notation(selected)
        # Short exercises remain continuous; larger works retain bounded pages.
        compact = phrase.last_bar-phrase.first_bar+1 <= 12 and phrase.end-phrase.start <= 48
        fingering_sources = authored_projection_sources(piece.fingering_plan)
        fingering_key = ((("fingering_sources", tuple(sorted(fingering_sources))),)
                         if fingering_sources else ())
        key = self.preprocessing.key(
            "engraving", "readable-midi-engraving-v4",
            hashlib.sha256(notation.musicxml.encode("utf-8")).hexdigest(),
            selected.fingerprint, selected.stage_key,
            phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
            selected.hand, piece.bpm, compact,
            tuple((n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes),
            *fingering_key)
        cached = self.preprocessing.read_json("engraving", key)
        layout = None
        if cached is not None:
            try:
                pages, geometry = cached["pages"], cached["layout"]
                if (not isinstance(pages, list) or not pages
                        or not all(isinstance(page, str) for page in pages)
                        or not isinstance(geometry, dict)):
                    raise ValueError("Invalid preprocessed score")
                candidate = EngravedScore(tuple(pages), geometry)
                require_lesson_alignment(phrase, candidate.layout, selected.hand)
                layout = candidate
                print("PREPROCESS_ENGRAVING_CACHE_HIT:", phrase.first_bar, phrase.last_bar, piece.bpm)
            except (TypeError, ValueError, KeyError, AssertionError):
                layout = None
        if layout is None:
            layout = render_layout(notation, phrase.first_bar, phrase.last_bar, selected.hand,
                total_beats=phrase.end-phrase.start, bpm=piece.bpm, continuous=compact)
            require_lesson_alignment(phrase, layout.layout, selected.hand)
            self.preprocessing.write_json("engraving", key,
                {"pages": list(layout.pages), "layout": layout.layout})
            self.preprocessing.prune()
        self._layout = layout
        self._layout_identity = selected.identity
        self._layout_source_bpm = piece.bpm
        self._layout_key = key
        return layout

    def geometry(self, selected: ScoreSelection) -> dict:
        # A transient renderer retry or second layout request for the same
        # source revision must not re-extract every Verovio beam/tie/tuplet
        # fragment. Preserve an owned immutable snapshot; callers cannot
        # mutate the layout subsequently served to another request.
        if selected.identity == self._prepared_layout_identity and self._prepared_layout is not None:
            return deepcopy(self._prepared_layout)
        diagnostics = os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1"
        began = time.perf_counter()
        score = self.engraving(selected)
        if diagnostics:
            print("SCORE_GEOMETRY_STAGE: engraving",
                  round((time.perf_counter()-began)*1000, 1), "ms", flush=True)
        checkpoint = time.perf_counter()
        notation = self._selected_notation(selected)
        model = self.semantic_score(selected)
        if diagnostics:
            print("SCORE_GEOMETRY_STAGE: semantic",
                  round((time.perf_counter()-checkpoint)*1000, 1), "ms", flush=True)
        checkpoint = time.perf_counter()
        prepared = score_preparation.assemble_layout(score,
            native_model=model, notation_xml=notation.musicxml,
            cache=self.preprocessing, cache_key=self._layout_key or "",
            revision=selected.revision)
        if diagnostics:
            print("SCORE_GEOMETRY_STAGE: native-assets",
                  round((time.perf_counter()-checkpoint)*1000, 1), "ms",
                  "total", round((time.perf_counter()-began)*1000, 1), "ms", flush=True)
        self._prepared_layout_identity = selected.identity
        self._prepared_layout = prepared
        return deepcopy(prepared)
