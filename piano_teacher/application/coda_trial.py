"""Isolated, source-traceable MIDI Coda trial for the existing teaching engine.

The trial is a normal LearningPlan over a Coda-transformed MIDI passage.
It deliberately uses the production score/Listen/assessment owners instead
of introducing a second playback clock. Its fingerprint is separate from
original-piece mastery, and the source plan remains available to restore.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from ..learning import LearningPlan
from ..research.coda_midi_passage import MidiPassage, project_midi_passage


FAMILIES = frozenset(("tempo-shaping", "dotted-rhythms", "chordification"))


@dataclass(frozen=True)
class CodaTrial:
    source_plan: LearningPlan
    source_fingerprint: str
    passage: MidiPassage
    family: str
    fingerprint: str


def prepare_coda_trial(
    original_plan: LearningPlan, *, source_fingerprint: str,
    first_bar: int, last_bar: int, family: str,
) -> tuple[CodaTrial, LearningPlan]:
    """Prepare the entire new plan before mutating a running session."""
    piece = original_plan.piece
    if (piece.source_format != "midi" or piece.source_musicxml or
            piece.midi_ticks_per_beat <= 0):
        raise ValueError("Coda trial needs an imported MIDI file")
    if family not in FAMILIES:
        raise ValueError("Choose slowdown, dotted rhythm or chord blocks")
    if last_bar-first_bar+1 > 8:
        raise ValueError("Coda trial supports up to eight measures")
    passage,stage=project_midi_passage(
        piece,first_bar,last_bar,family=family,bpm=original_plan.bpm)
    if family != "tempo-shaping" and not any(
        abs(event.exercise_start-(event.source_start-passage.source_start))>1e-7
        or abs(event.exercise_end-(event.source_end-passage.source_start))>1e-7
        for event in stage.timing.events):
        # Coda grouping can return a valid no-op for sparse or unsuitable
        # passages. Keep the existing source lesson active in that case.
        raise ValueError("No eligible note groups in this passage; try slowdown")
    trial_plan=LearningPlan(
        stage.piece,exercise_strategy="legacy",
        timing_strategy="original-timing",tempo_strategy="constant-tempo")
    # The trial cannot save progress to the source-piece fingerprint.
    fingerprint=sha256((
        "coda-midi-trial-v1|"+source_fingerprint+"|"+
        stage.selection.fingerprint+"|"+str(first_bar)+"|"+
        str(last_bar)+"|"+family).encode()).hexdigest()
    trial=CodaTrial(original_plan,source_fingerprint,passage,family,fingerprint)
    return trial,trial_plan
