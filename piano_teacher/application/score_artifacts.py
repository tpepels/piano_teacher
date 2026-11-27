"""The selected notation and native ink cache, owned by the score child."""

from __future__ import annotations

import hashlib
import os
import time
from functools import cached_property

from ..engraving.engraving import EngravedScore, render_layout
from ..fingering.projection import project_model
from ..lesson_validation import require_lesson_alignment
from ..music import source_note_id
from ..notation.display_envelope import (
    display_envelope, project_display_model, project_performance_layout,
)
from ..notation.lesson import build_lesson_score, infer_midi_clef_plan, infer_piece_clefs
from ..notation.model import build_score_model
from ..preprocessing_cache import PreprocessingCache
from ..source_timing import SCHEMA as TIMELINE_SCHEMA
from .score_preparation import assemble_layout
from .score_selection import ScoreSelection


class ScoreArtifacts:
    def __init__(self, preprocessing: PreprocessingCache, selected: ScoreSelection, timing: dict):
        self.preprocessing = preprocessing
        self.selected = selected
        self.timing = timing

    @cached_property
    def envelope(self):
        selected = self.selected
        return display_envelope(selected.piece, selected.phrase,
                                transformed=selected.transformed_rhythm)

    @cached_property
    def notation(self):
        piece = self.selected.piece
        return build_lesson_score(
            self.envelope.phrase, boundaries=piece.bar_boundaries,
            time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
            clef_changes=piece.clef_changes, default_clefs=infer_piece_clefs(piece.notes),
            inferred_clefs=infer_midi_clef_plan(piece.notes, piece.bar_boundaries),
            barlines=piece.barlines)

    @cached_property
    def notation_model(self) -> dict:
        selected = self.selected
        return build_score_model(self.notation, boundaries=selected.piece.bar_boundaries,
                                 hand=selected.hand, revision=selected.revision)

    @cached_property
    def semantic(self) -> dict:
        selected = self.selected
        model = project_display_model(
            self.notation_model, self.envelope, selected.hand, self.timing)
        if (self.timing.get("schema") != TIMELINE_SCHEMA
                or self.timing.get("source_duration_beats") != model["duration_beats"]
                or self.timing.get("sounding_duration_beats") != model["sounding_duration_beats"]):
            raise ValueError("Notation differs from its authoritative source timing")
        return project_model(model, selected.piece.fingering_plan)

    def prepare(self, operation: str) -> dict:
        if operation == "score.semantic":
            return self.semantic
        if operation == "score.native_layout":
            return self.layout
        return self.bundle()

    def bundle(self) -> dict:
        selected = self.selected
        model = self.semantic
        source_ids = [source_note_id(note, index)
                      for index, note in enumerate(selected.phrase.notes)]
        if not source_ids or len(source_ids) != len(set(source_ids)):
            raise ValueError("Score bundle has missing or duplicate source note IDs")
        graded = {identifier for identifier, note in zip(source_ids, selected.phrase.notes, strict=True)
                  if selected.hand == "both" or note.hand == selected.hand}
        if set(model["active_note_ids"]) != graded:
            raise ValueError("Score bundle notation does not match graded MIDI source IDs")
        layout = self.layout
        if layout["revision"] != selected.revision or model["revision"] != selected.revision:
            raise ValueError("Score bundle contains mixed revisions")
        return {"status": "ready", **selected.binding, "source_note_ids": source_ids,
                "layout": layout, "model": model}

    def _cached_engraving(self, key: str) -> EngravedScore | None:
        cached = self.preprocessing.read_json("engraving", key)
        if cached is None:
            return None
        selected = self.selected
        try:
            pages, geometry = cached["pages"], cached["layout"]
            if (not isinstance(pages, list) or not pages
                    or not all(isinstance(page, str) for page in pages)
                    or not isinstance(geometry, dict)):
                return None
            require_lesson_alignment(selected.phrase, geometry, selected.hand)
        except (TypeError, ValueError, KeyError, AssertionError):
            return None
        print("PREPROCESS_ENGRAVING_CACHE_HIT:", selected.phrase.first_bar,
              selected.phrase.last_bar, selected.piece.bpm)
        return EngravedScore(tuple(pages), geometry)

    def _engrave(self, key: str, *, compact: bool) -> EngravedScore:
        cached = self._cached_engraving(key)
        if cached is not None:
            return cached
        selected = self.selected
        envelope = self.envelope
        complete = render_layout(
            self.notation, "both", total_beats=envelope.phrase.end-envelope.phrase.start,
            bpm=selected.piece.bpm, continuous=compact)
        require_lesson_alignment(envelope.phrase, complete.layout, "both")
        layout = project_performance_layout(complete.layout, envelope)
        require_lesson_alignment(selected.phrase, layout, selected.hand)
        self.preprocessing.write_json("engraving", key, {"pages": list(complete.pages), "layout": layout})
        self.preprocessing.prune()
        return EngravedScore(complete.pages, layout)

    @cached_property
    def layout(self) -> dict:
        began = time.perf_counter()
        selected = self.selected
        phrase, piece = selected.phrase, selected.piece
        compact = phrase.last_bar-phrase.first_bar+1 <= 12 and phrase.end-phrase.start <= 48
        key = self.preprocessing.key(
            "engraving", "complete-display-atlas-v2",
            hashlib.sha256(self.notation.musicxml.encode("utf-8")).hexdigest(),
            selected.fingerprint, selected.stage_key,
            phrase.first_bar, phrase.last_bar, phrase.start, phrase.end,
            selected.hand, piece.bpm, compact,
            tuple((n.source_id, n.start, n.end, n.pitch, n.hand) for n in phrase.notes))
        score = self._engrave(key, compact=compact)
        engraved = time.perf_counter()
        layout = assemble_layout(score, notation_model=self.notation_model,
            notation_xml=self.notation.musicxml, cache=self.preprocessing,
            cache_key=key, revision=selected.revision)
        if os.environ.get("PIANO_TEACHER_TIMING_DIAGNOSTICS") == "1":
            print("SCORE_GEOMETRY_STAGE: engraving", round((engraved-began)*1000, 1),
                  "ms asset extraction", round((time.perf_counter()-engraved)*1000, 1),
                  "ms", flush=True)
        return layout
