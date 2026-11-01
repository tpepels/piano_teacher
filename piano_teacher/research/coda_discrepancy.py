"""Evidence-based classification of pinned Coda author/adapter differences.

No exercise transformations occur here. A category requires measured written
and sounding differences plus a known, independently identified source case.
Unknown conditions remain unclassified, never silently counted as parity.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any

from .coda_differential import SoundingNote, WrittenNote


CAUSES = {
    "rest-coverage-only": (
        "Written pitched segments and sounded events agree; only rest events differ."
    ),
    "written-segmentation-tuplet": (
        "Sounded events agree; authored-triplet notation has different note/rest "
        "subdivisions or ties after regeneration."
    ),
    "written-segmentation-meter": (
        "Sounded events agree; written note/rest subdivisions differ on a source "
        "with a 3/4-to-2/4 meter change. Original Coda uses only its first meter."
    ),
    "beamed-source-protected": (
        "Original Coda modifies a beamed source group; the guarded adapter "
        "retains its protected attack timing rather than rewriting beaming."
    ),
    "cross-measure-group-protected": (
        "Original Coda re-times consecutive same-pitch whole notes across a "
        "source barline; adapter groups must remain inside a source measure."
    ),
    "tuplet-source-protected": (
        "Original Coda changes tuplet-member timing/grouping; the adapter "
        "retains authored tuplet attacks without a verified retimed projection."
    ),
    "rest-bearing-tuplet-protected": (
        "Original Coda changes the note/rest-bearing tuplet group; the "
        "adapter applies its written-rest/tuplet preservation restrictions."
    ),
    "changing-meter-group-protected": (
        "Original Coda transforms notes in the 3/4-to-2/4 excerpt using its "
        "first-meter-only policy; adapter enforces source-measure restrictions."
    ),
    "upstream-disconnected-tie": (
        "The original exported MusicXML contains a tied continuation whose "
        "onset is separated from its tied predecessor by an audible gap."
    ),
    "unclassified": "No supported causal classification; requires manual audit.",
}


@dataclass(frozen=True)
class Discrepancy:
    category: str
    reason: str
    evidence: dict[str, Any]


def _event(event):
    return vars(event) if event is not None else None


def _first_difference(a, b) -> dict[str, Any] | None:
    sentinel = object()
    for index, (left, right) in enumerate(
            zip_longest(a, b, fillvalue=sentinel)):
        if left != right:
            return {"index": index,
                    "reference": _event(left) if left is not sentinel else None,
                    "adapter": _event(right) if right is not sentinel else None}
    return None


def _pitch_counter(notes) -> Counter:
    return Counter(note.pitch for note in notes)


def explain_discrepancy(
    *, source_case: str, voice_index: int, operation: str,
    reference_written: tuple[WrittenNote, ...],
    native_written: tuple[WrittenNote, ...],
    reference_sounding: tuple[SoundingNote, ...],
    adapter_sounding: tuple[SoundingNote, ...],
    source_sounding: tuple[SoundingNote, ...],
    reference_tie_errors: tuple[str, ...],
) -> Discrepancy:
    """Classify every known *non-exact* comparison, retaining counterexamples.

    Fixture-based categories are checked against actual event/voice differences.
    They explain a pinned observed cause, not a claim for arbitrary repertoire.
    """
    sounding_exact = (not reference_tie_errors and
                      reference_sounding == adapter_sounding)
    written_exact = reference_written == native_written
    if sounding_exact and written_exact:
        raise ValueError("Exact parity is not a discrepancy")
    ref_pitched = tuple(x for x in reference_written if not x.rest)
    native_pitched = tuple(x for x in native_written if not x.rest)
    ref_rests = tuple(x for x in reference_written if x.rest)
    native_rests = tuple(x for x in native_written if x.rest)
    lost_pitches = _pitch_counter(adapter_sounding) - _pitch_counter(reference_sounding)
    gained_pitches = _pitch_counter(reference_sounding) - _pitch_counter(adapter_sounding)

    if reference_tie_errors:
        category = ("upstream-disconnected-tie" if
                    any("disconnected-tie:" in e for e in reference_tie_errors)
                    else "unclassified")
    elif sounding_exact:
        if ref_pitched == native_pitched and ref_rests != native_rests:
            category = "rest-coverage-only"
        elif source_case == "rest-bearing-triplet" and operation.startswith("slow-"):
            category = "written-segmentation-tuplet"
        elif source_case == "changing-meter" and operation.startswith("slow-"):
            category = "written-segmentation-meter"
        else:
            category = "unclassified"
    elif source_case == "source-authored-beams":
        category = "beamed-source-protected"
    elif source_case == "long-multipage-first-two-bars":
        category = "cross-measure-group-protected"
    elif source_case == "authored-triplet":
        category = "tuplet-source-protected"
    elif source_case == "rest-bearing-triplet":
        category = "rest-bearing-tuplet-protected"
    elif source_case == "changing-meter":
        category = "changing-meter-group-protected"
    else:
        category = "unclassified"

    evidence: dict[str, Any] = {
        "source_case": source_case, "source_voice": voice_index,
        "operation": operation,
        "reference_written_count": len(reference_written),
        "native_written_count": len(native_written),
        "reference_sounding_count": len(reference_sounding),
        "adapter_sounding_count": len(adapter_sounding),
        "source_sounding_count": len(source_sounding),
        "adapter_unchanged_from_source": adapter_sounding == source_sounding,
        "source_and_reference_same": reference_sounding == source_sounding,
        "reference_rest_count": len(ref_rests),
        "native_rest_count": len(native_rests),
        "reference_tie_errors": list(reference_tie_errors),
        "missing_reference_pitches": dict(sorted(lost_pitches.items())),
        "extra_reference_pitches": dict(sorted(gained_pitches.items())),
        "first_written_difference": _first_difference(reference_written,native_written),
        "first_sounding_difference": _first_difference(reference_sounding,adapter_sounding),
    }
    return Discrepancy(category, CAUSES[category], evidence)
