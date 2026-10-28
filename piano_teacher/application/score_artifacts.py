"""Selected notation, engraving and image caches, independent of session state.

The application serializes calls under its existing lock. This owner receives
source values, never an engine, learning plan, transport or renderer callback.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from ..fingering.projection import authored_projection_sources, project_model
from ..lesson_validation import require_lesson_alignment
from ..music import Phrase, Piece
from ..notation.lesson import LessonScore, build_lesson_score, infer_piece_clefs
from ..notation.model import build_score_model
from ..preprocessing_cache import PreprocessingCache
from ..rendering.legacy.engraving import EngravedScore, render_layout
from ..rendering.legacy.raster import rasterize_score
from . import score_preparation


@dataclass(frozen=True)
class ScoreSelection:
    piece: Piece
    phrase: Phrase
    hand: str
    stage_key: str
    revision: int
    fingerprint: str

    @property
    def identity(self) -> tuple:
        phrase = self.phrase
        return (id(self.piece), self.fingerprint, self.stage_key, self.hand, self.revision,
                phrase.first_bar, phrase.last_bar, phrase.start, phrase.end)


def validate_png_width(width: int) -> None:
    if not 600 <= width <= 12000:
        raise ValueError("Invalid engraving image width")


class ScoreArtifacts:
    def __init__(self, preprocessing: PreprocessingCache):
        self.preprocessing = preprocessing
        self.invalidate()

    def invalidate(self) -> None:
        """Discard selected artifacts; durable, source-keyed entries remain reusable."""
        self._notation_identity: tuple | None = None
        self._notation: LessonScore | None = None
        self._model: dict | None = None
        self._layout_identity: tuple | None = None
        self._layout: EngravedScore | None = None
        self._layout_source_bpm: float | None = None
        self._layout_key: str | None = None
        self._png: dict[tuple[int, int], bytes] = {}

    def _selected_notation(self, selected: ScoreSelection) -> LessonScore:
        if selected.identity != self._notation_identity or self._notation is None:
            piece = selected.piece
            notation = build_lesson_score(
                selected.phrase, boundaries=piece.bar_boundaries,
                time_signatures=piece.time_signatures,
                key_signatures=piece.key_signatures,
                clef_changes=piece.clef_changes,
                default_clefs=infer_piece_clefs(piece.notes),
                barlines=piece.barlines, source_musicxml=piece.source_musicxml,
                fingering_sources=authored_projection_sources(piece.fingering_plan))
            self._notation = notation
            self._notation_identity = selected.identity
            self._model = None
        return self._notation

    def source_model(self, selected: ScoreSelection) -> dict:
        """Internal source contract; HTTP callers use the isolated semantic response."""
        notation = self._selected_notation(selected)
        if self._model is None:
            self._model = build_score_model(notation,
                boundaries=selected.piece.bar_boundaries,
                hand=selected.hand, revision=selected.revision)
        return self._model

    def semantic_score(self, selected: ScoreSelection) -> dict:
        return project_model(deepcopy(self.source_model(selected)),
            selected.piece.fingering_plan,
            source_musicxml=selected.piece.source_musicxml)

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
            "engraving", "readable-midi-engraving-v3", selected.fingerprint, selected.stage_key,
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
        self._png.clear()
        return layout

    def engraved(self, selected: ScoreSelection, page: int = 0) -> str:
        score = self.engraving(selected)
        if not 0 <= page < len(score.pages):
            raise ValueError("Invalid score page")
        return score.pages[page]

    def engraved_png(self, selected: ScoreSelection, page: int = 0, *, width: int = 2000) -> bytes:
        validate_png_width(width)
        score = self.engraving(selected)
        if width > 7200 and not bool(getattr(score, "layout", {}).get("continuous_score", False)):
            raise ValueError("Invalid engraving image width")
        if not 0 <= page < len(score.pages):
            raise ValueError("Invalid score page")
        key = (page, width)
        if key not in self._png:
            # Retain one resolution per page in process memory.
            for cached in tuple(self._png):
                if cached[0] == page:
                    del self._png[cached]
            png_key = self.preprocessing.key("png", self._layout_key, page, width) if self._layout_key else None
            png = self.preprocessing.read_png(png_key) if png_key else None
            if png is None:
                png = (rasterize_score(score.pages[page]) if width == 2000
                       else rasterize_score(score.pages[page], width=width))
                if png_key:
                    self.preprocessing.write_png(png_key, png)
            else:
                print("PREPROCESS_PNG_CACHE_HIT:", page, width)
            self._png[key] = png
        return self._png[key]

    def geometry(self, selected: ScoreSelection, *, native_notes: bool = True) -> dict:
        score = self.engraving(selected)
        if not native_notes:
            return score_preparation.assemble_layout(score,
                native_notes=False, revision=selected.revision)
        notation = self._selected_notation(selected)
        model = self.semantic_score(selected)
        return score_preparation.assemble_layout(score, native_notes=True,
            native_model=model, notation_xml=notation.musicxml,
            cache=self.preprocessing, cache_key=self._layout_key or "",
            revision=selected.revision)
