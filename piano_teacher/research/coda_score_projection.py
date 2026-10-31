"""Research-only source MusicXML → one Coda notation/Listen/grade timeline.

The original Piece and TimingPlan remain immutable. This adapter creates a
separate, explicitly revision-keyed ScoreSelection whose printed note events,
Listen notes and graded events share the same transformed clock.

This is a strict supported subset. We reject unsupported structural markup
instead of silently dropping directions, ties, tuplets, articulations or
mid-measure changes. Production practice strategy selection is untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from math import isclose
from xml.etree import ElementTree as ET

from ..application.listen_session import ListenSelection
from ..application.score_artifacts import ScoreSelection
from ..exercise_contracts import ConstantTempo, TempoMap, TimingPlan, assess_timed
from ..exercise_generator import ExerciseVariant
from ..music import Piece, Phrase
from ..practice import PlayedNote
from ..notation.lesson import build_lesson_score, infer_piece_clefs
from .coda_annotation_guard import (
    source_annotation_obligations, verify_annotation_projection,
)


_ALLOWED_MEASURE = frozenset({
    "attributes", "note", "backup", "forward", "direction",
})
_ALLOWED_NOTE = frozenset({
    "pitch", "rest", "duration", "voice", "type", "dot", "staff", "chord",
    "accidental", "stem", "notations", "beam",
})
_ALLOWED_ATTRIBUTES = frozenset({
    "divisions", "key", "time", "clef", "staves",
})


def _tag(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _safe_xml(source: str, *, slowdown: bool) -> ET.Element:
    if not source:
        raise ValueError("A Coda score projection requires original MusicXML")
    root = ET.fromstring(source)
    if _tag(root) != "score-partwise":
        raise ValueError("Only original score-partwise MusicXML is supported")
    if not root.findall("{*}part"):
        raise ValueError("No source MusicXML parts")
    for part in root.findall("{*}part"):
        for measure in part.findall("{*}measure"):
            seen_note = False
            for item in measure:
                tag = _tag(item)
                if tag not in _ALLOWED_MEASURE:
                    raise ValueError(f"Coda notation projection cannot preserve {tag}")
                if slowdown and tag == "direction":
                    raise ValueError("Coda slowdown cannot yet preserve source directions")
                if tag == "attributes":
                    if seen_note:
                        raise ValueError("Coda projection rejects mid-measure attribute changes")
                    for mark in item:
                        if _tag(mark) not in _ALLOWED_ATTRIBUTES:
                            raise ValueError("Unsupported original staff attribute")
                elif tag == "note":
                    seen_note = True
                    if item.find("{*}tie") is not None:
                        raise ValueError("Coda source ties need a separate continuation proof")
                    if item.find("{*}grace") is not None or (
                            set(map(_tag,item)) - _ALLOWED_NOTE):
                        raise ValueError("Coda projection cannot remap expressive/tuplet/tied notes")
                    if item.find("{*}chord") is not None and slowdown:
                        # The original note groups are still source-owned,
                        # but sync of a chord's original XML cursor is not
                        # proven for rebarred notation in this first subset.
                        raise ValueError("Slowdown of source chord XML is not yet supported")
                elif tag in ("backup","forward") and not seen_note:
                    raise ValueError("Source voice cursor precedes all note events")
    return root


def _scaled_original(source: str, factor: int) -> str:
    """Scale source note/rest and cursor lengths for authored-rest projection.

    It is a separate helper XML, never a mutation of the user's original.
    Rebarred notation is synthesized by the canonical lesson builder.
    """
    root = _safe_xml(source, slowdown=True)
    for part in root.findall("{*}part"):
        for measure in part.findall("{*}measure"):
            for node in measure:
                tag = _tag(node)
                if tag in ("note","forward","backup"):
                    for duration in node.findall("{*}duration"):
                        value=int(duration.text)
                        if value <= 0:
                            raise ValueError("Nonpositive original MusicXML duration")
                        duration.text=str(value*factor)
    return ET.tostring(root,encoding="unicode")


def _original_metadata(piece:Piece, old:Phrase, plan:TimingPlan, factor:int):
    if old.start != 0 or old.first_bar != 1:
        raise ValueError("Coda projection currently requires a source excerpt starting at bar 1")
    if not piece.bar_boundaries or piece.bar_boundaries[0]!=0 or (
            abs(piece.bar_boundaries[-1]-old.end)>1e-7):
        raise ValueError("Coda projection needs complete original measure boundaries")
    original_grid=tuple(piece.bar_boundaries)
    if factor==1:
        if abs(plan.duration_beats-(old.end-old.start))>1e-7:
            raise ValueError("Changing source grid requires an explicit slowdown factor")
        return original_grid, piece.time_signatures, piece.key_signatures, piece.clef_changes
    if factor not in (2,4):
        raise ValueError("Only published Coda written slowdown x2/x4 is supported")
    if len({round(right-left,7) for left,right in zip(
            original_grid, original_grid[1:])})!=1:
        raise ValueError("Source slowdown cannot yet rebar mixed meter lengths")
    if len({(n,d) for _,n,d in piece.time_signatures})>1:
        raise ValueError("Source slowdown cannot yet rebar changing meters")
    bar=original_grid[1]-original_grid[0]
    total=plan.duration_beats
    count=round(total/bar)
    if count <= 0 or not isclose(count*bar,total,abs_tol=1e-7):
        raise ValueError("Slowdown does not occupy complete source-meter bars")
    new_grid=tuple(round(i*bar,8) for i in range(count+1))
    shift=lambda beat: round(beat*factor,8)
    keys=tuple(replace(v,beat=shift(v.beat)) for v in piece.key_signatures)
    clefs=tuple(replace(v,beat=shift(v.beat)) for v in piece.clef_changes)
    meters=tuple((shift(t),n,d) for t,n,d in piece.time_signatures)
    return new_grid,meters,keys,clefs


@dataclass(frozen=True)
class CodaProjectedStage:
    """One immutable research selection for all four downstream consumers."""

    original_piece: Piece
    timing: TimingPlan
    piece: Piece
    variant: ExerciseVariant
    selection: ScoreSelection
    tempo_map: TempoMap
    reference_family: str
    original_source_sha256: str

    def listen_selection(self) -> ListenSelection:
        return ListenSelection(
            self.variant,self.tempo_map.bpm_at(0),self.selection.stage_key,
            self.selection.revision,self.piece.bar_boundaries,
            self.piece.time_signatures,self.tempo_map)

    def grade(self, played: list[PlayedNote], *, hand: str = "both"):
        """Grades the exercise without crediting original-piece mastery."""
        return assess_timed(self.timing,hand,self.tempo_map.bpm_at(0),played,
                            tempo_map=self.tempo_map)


def project_coda_score(piece:Piece, timing:TimingPlan, *,
                       reference_family:str, bpm:float, revision:int = 1
                       ) -> CodaProjectedStage:
    """Produce immutable notation/audio/scoring inputs from one TimingPlan.

    Authored rests and source key/clef context survive in a private source
    XML projection; unsupported annotations fail before any score is shown.
    Source identity and original-score mastery remain separately owned.
    """
    if reference_family not in ("dotted-rhythms","chordification","tempo-shaping"):
        raise ValueError("Not an original Coda timing-transformation family")
    if len(timing.original.notes)==0:
        raise ValueError("Coda projection requires pitched source notes")
    original=timing.original.phrase
    if not piece.source_musicxml:
        raise ValueError("Coda projection requires original source MusicXML")
    _safe_xml(piece.source_musicxml,slowdown=reference_family=="tempo-shaping")
    if original.start!=0 or original.first_bar!=1 or (
            original.end!=piece.bar_boundaries[-1]):
        raise ValueError("Coda projection currently requires the whole original selected score")
    if set(note.source_id for note in original.notes)!={
            note.source_id for note in piece.notes}:
        raise ValueError("Coda source score/phrase note identities disagree")
    if len(set(note.source_id for note in original.notes)) != len(original.notes):
        raise ValueError("Duplicate original source-note identities")
    if reference_family=="tempo-shaping":
        fraction=timing.duration_beats/(original.end-original.start)
        factor=round(fraction)
        if abs(fraction-factor)>1e-8 or factor not in (2,4):
            raise ValueError("Written slowdown needs exact Coda x2/x4 beat expansion")
        if any(abs(e.exercise_start-e.source_start*factor)>1e-7 or
               abs(e.exercise_end-e.source_end*factor)>1e-7
               for e in timing.events):
            raise ValueError("Slowdown must scale the complete original source timeline")
    else:
        factor=1
    obligations = source_annotation_obligations(piece,timing,factor=factor)
    grid,meters,keys,clefs=_original_metadata(piece,original,timing,factor)
    new_phrase=timing.exercise_phrase
    new_phrase=replace(new_phrase,first_bar=1,last_bar=len(grid)-1)
    # One canonical transformed rhythm supplies the grader, the written
    # score and Listen. Original Piece is never replaced or re-imported.
    if any(note.start<0 or note.end>new_phrase.end+1e-7
           for note in new_phrase.notes):
        raise ValueError("Transformed note exceeds the written score")
    source_xml=(_scaled_original(piece.source_musicxml,factor)
                if factor>1 else piece.source_musicxml)
    bars=tuple(piece.barlines)
    if factor>1 and bars:
        raise ValueError("Slowdown cannot yet preserve source repeat/barline semantics")
    projected_piece=replace(
        piece,notes=new_phrase.notes,phrases=(new_phrase,),
        bar_boundaries=grid,time_signatures=meters,key_signatures=keys,
        clef_changes=clefs,barlines=bars,source_musicxml=source_xml,
        fingering_plan=None)
    if obligations.notes or obligations.dynamics:
        preview = build_lesson_score(
            new_phrase,boundaries=projected_piece.bar_boundaries,
            time_signatures=projected_piece.time_signatures,
            key_signatures=projected_piece.key_signatures,
            clef_changes=projected_piece.clef_changes,
            default_clefs=infer_piece_clefs(projected_piece.notes),
            barlines=projected_piece.barlines,
            source_musicxml=projected_piece.source_musicxml,
            retimed_source=True)
        verify_annotation_projection(obligations,preview.musicxml,
                                     preview.note_bindings)
    variant=ExerciseVariant(
        timing.name,new_phrase,timing.original.source_indices)
    digest=sha256((piece.source_musicxml+timing.name+
                   repr(tuple((e.source_index,e.exercise_start,e.exercise_end)
                              for e in timing.events))).encode()).hexdigest()
    selection=ScoreSelection(
        projected_piece,new_phrase,"both","research-"+timing.name,
        revision,digest,transformed_rhythm=True)
    tempo=ConstantTempo().generate(timing,bpm)
    return CodaProjectedStage(piece,timing,projected_piece,variant,selection,
                              tempo,reference_family,
                              sha256(piece.source_musicxml.encode()).hexdigest())
