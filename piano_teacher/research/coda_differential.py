
"""Independent written-score and sounding-note comparison for Coda research.

Do not infer a written tie continuation from a MIDI attack or equate score
events with sounding events. Only actual rendered notation can certify a
written comparison; the research TimingPlan separately defines MIDI grading.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, order=True)
class WrittenNote:
    voice: str
    onset: float
    end: float
    pitch: int | None
    tie: str = ""

    @property
    def rest(self) -> bool:
        return self.pitch is None


@dataclass(frozen=True, order=True)
class SoundingNote:
    voice: str
    onset: float
    end: float
    pitch: int


def written_from_music21(stream) -> tuple[WrittenNote, ...]:
    """Flatten real music21 notation, retaining rests, chords, and tie roles.

    Voice labels are normalized by sorted voice identity *within this isolated
    source voice*. A different voice never merges its same-pitch tied notes.
    """
    from music21 import chord, stream as music_stream
    raw = []
    for event in stream.recurse().notesAndRests:
        onset = round(float(event.getOffsetInHierarchy(stream)), 6)
        end = round(onset + float(event.quarterLength), 6)
        cursor = event.activeSite
        owner = "implicit"
        while cursor is not None:
            if isinstance(cursor, music_stream.Voice):
                owner = "voice:" + str(cursor.id)
                break
            if cursor is stream:
                break
            cursor = getattr(cursor, "activeSite", None)
        if event.isRest:
            raw.append((owner, onset, end, None, ""))
        elif isinstance(event, chord.Chord):
            for member in event.notes:
                tie = getattr(getattr(member, "tie", None), "type", "") or ""
                raw.append((owner, onset, end, int(member.pitch.midi), tie))
        else:
            tie = getattr(getattr(event, "tie", None), "type", "") or ""
            raw.append((owner, onset, end, int(event.pitch.midi), tie))
    labels = {name: f"v{i}" for i, name in enumerate(sorted({v[0] for v in raw}))}
    return tuple(sorted(WrittenNote(labels[voice], start, end, pitch, tie)
                        for voice, start, end, pitch, tie in raw))


def sounding_from_written(
    written: Iterable[WrittenNote],
) -> tuple[tuple[SoundingNote, ...], tuple[str, ...]]:
    """Collapse *explicit* contiguous tie chains, preserving reattacks and voices.

    Broken ties are reported as errors rather than silently treating their
    continuations as new graded MIDI attacks.
    """
    attacks = []
    pending = {}
    errors = []
    for atom in sorted(written, key=lambda n: (n.onset, n.voice, n.pitch or -1, n.end)):
        if atom.pitch is None:
            continue
        key = atom.voice, atom.pitch
        role = atom.tie
        if role in ("stop", "continue"):
            previous = pending.get(key)
            if previous is None:
                errors.append(f"orphan-tie:{atom.voice}:{atom.pitch}:{atom.onset}")
                continue
            if abs(previous.end - atom.onset) > 1e-6:
                errors.append(f"disconnected-tie:{atom.voice}:{atom.pitch}:{atom.onset}")
                pending.pop(key)
                continue
            if role == "continue":
                pending[key] = SoundingNote(atom.voice, previous.onset, atom.end, atom.pitch)
            else:
                attacks.append(SoundingNote(atom.voice, previous.onset, atom.end, atom.pitch))
                pending.pop(key)
        elif role == "start":
            if key in pending:
                errors.append(f"double-tie-start:{atom.voice}:{atom.pitch}:{atom.onset}")
            else:
                pending[key] = SoundingNote(atom.voice, atom.onset, atom.end, atom.pitch)
        elif not role:
            attacks.append(SoundingNote(atom.voice, atom.onset, atom.end, atom.pitch))
        else:
            errors.append(f"unknown-tie:{role}:{atom.voice}:{atom.pitch}")
    errors.extend(f"unterminated-tie:{voice}:{pitch}" for voice, pitch in sorted(pending))
    return tuple(sorted(attacks)), tuple(errors)


def sounding_from_plan(plan, indices: set[int]) -> tuple[SoundingNote, ...]:
    """Canonical sounded/grading notes, filtered to this single source voice."""
    return tuple(sorted(
        SoundingNote("v0", round(event.exercise_start, 6),
                     round(event.exercise_end, 6), note.pitch)
        for i, (event, note) in enumerate(zip(plan.events, plan.original.notes))
        if i in indices))


def report_comparison(
    reference: tuple[WrittenNote, ...],
    expected_sounding: tuple[SoundingNote, ...],
    native_written: tuple[WrittenNote, ...] | None,
    *, unavailable_reason: str = "",
) -> dict:
    """Keep independent, explicit statuses for notation and played timeline."""
    reference_sounding, reference_errors = sounding_from_written(reference)
    sounding_equal = not reference_errors and reference_sounding == expected_sounding
    if native_written is None:
        written_report = {"status": "unavailable", "reason": unavailable_reason[:350]}
        alignment = "unavailable"
    else:
        native_sounding, native_errors = sounding_from_written(native_written)
        written_report = {
            "status": "exact" if reference == native_written else "different",
            "reference_event_count": len(reference),
            "native_event_count": len(native_written),
        }
        if reference != native_written:
            written_report.update(
                reference_first=[vars(x) for x in reference[:8]],
                native_first=[vars(x) for x in native_written[:8]])
        alignment = ("invalid-native-ties" if native_errors else
                     "exact" if native_sounding == expected_sounding else "different")
        if native_errors:
            written_report["native_tie_errors"] = list(native_errors[:8])
    sound_report = {
        "status": ("invalid-reference-ties" if reference_errors else
                   "exact" if sounding_equal else "different"),
        "reference_note_count": len(reference_sounding),
        "plan_note_count": len(expected_sounding),
        "native_written_to_plan": alignment,
    }
    if reference_errors:
        sound_report["reference_tie_errors"] = list(reference_errors[:8])
    if not sounding_equal:
        sound_report.update(
            reference_first=[vars(x) for x in reference_sounding[:8]],
            plan_first=[vars(x) for x in expected_sounding[:8]])
    return {"written": written_report, "sounding": sound_report}
