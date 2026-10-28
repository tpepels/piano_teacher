"""Source plans, whole-source semantic checks and stable case job identities."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from piano_teacher.music import Phrase
from piano_teacher.notation.lesson import build_lesson_score, infer_piece_clefs
from piano_teacher.notation.model import build_score_model
from . import case_catalog
from .capture_store import ROOT


@dataclass(frozen=True)
class SourcePlan:
    source_index: int
    path: Path
    originals: tuple
    stages: tuple
    focused: tuple

    @property
    def case_count(self):
        return len(self.originals) + len(self.stages) + len(self.focused)

    @property
    def measure_count(self):
        return len({bar for case, _, _ in self.originals
                    for bar in range(case.first_bar, case.last_bar + 1)})


def plan_source(path, piece, *, source_index, max_bars, shard_index, shard_count, focused_cases):
    originals = tuple((case, None, None)
        for case in case_catalog.original_cases(path, piece, max_bars=max_bars)
        if case_catalog.case_shard(path, case, shard_count) == shard_index)
    stages = tuple((case, source_phrase, variant)
        for case, source_phrase, variant in case_catalog.curriculum_cases(path, piece)
        if case_catalog.case_shard(path, case, shard_count) == shard_index)
    focused = tuple((case, None, None) for case in focused_cases
        if (ROOT / (case.filename if "/" in case.filename
                    else "midi/" + case.filename)).resolve() == path.resolve()
        and case_catalog.case_shard(path, case, shard_count) == shard_index)
    return SourcePlan(source_index, path, originals, stages, focused)


def case_jobs(plans, phase, *, out, inputs_hash, runtime, godot, reuse_captures):
    if phase not in ('originals', 'focused', 'stages'):
        raise ValueError('Unknown audit phase: ' + phase)
    jobs = []
    for plan in plans:
        source_index, path = plan.source_index, plan.path
        for case, source_phrase, variant in getattr(plan, phase):
            directory = out / f"{source_index:02d}-{path.stem}" / case.name
            identity = dict(inputs_sha256=inputs_hash, runtime=runtime, case=asdict(case),
                source_phrase=asdict(source_phrase) if source_phrase is not None else None,
                variant=asdict(variant) if variant is not None else None, focused=phase == 'focused')
            key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            jobs.append(dict(source_index=source_index, path=path, case=case,
                source_phrase=source_phrase, variant=variant, directory=directory, godot=godot,
                focused=phase == 'focused', reuse_captures=reuse_captures, key=key))
    return jobs


def source_semantics(path, piece):
    from piano_teacher.notation.semantic_contract import verify_midi_performance, verify_musicxml_contract
    whole = Phrase(1, 1, len(piece.bar_boundaries)-1,
                   piece.bar_boundaries[0], piece.bar_boundaries[-1], piece.notes)
    score = build_lesson_score(whole, boundaries=piece.bar_boundaries,
        time_signatures=piece.time_signatures, key_signatures=piece.key_signatures,
        clef_changes=piece.clef_changes, barlines=piece.barlines,
        source_musicxml=piece.source_musicxml,
        default_clefs=None if piece.source_musicxml else infer_piece_clefs(piece.notes))
    model = build_score_model(score, boundaries=piece.bar_boundaries, hand="both")
    if path.suffix.casefold() in {".mid", ".midi"}:
        model["import_warnings"] = list(piece.import_warnings)
        semantics = verify_midi_performance(path, model, generated_xml=score.musicxml)
    else:
        semantics = verify_musicxml_contract(path.read_text(), score.musicxml, model)
    return semantics
