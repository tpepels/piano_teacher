"""Pinned editorial cases and source/curriculum case enumeration."""
from __future__ import annotations
from bisect import bisect_right
import hashlib
import json
from pathlib import Path

from .capture_store import ROOT
from .case_types import AuditCase

AUTUMN_FILE = "Bill_Evans_on_Autunm_Leaves_From_the_Album_Portrait_in_Jazz.midi"
# Preserve the regression threshold that would have caught the 438px/beat
# user screenshot. More complex pieces use independently specified budgets.
MAX_AUTUMN_DENSITY = 400.0


# Explicit, pinned real MIDI corpus. Case changes require an intentional
# review: CI must never silently drop a hard score or select easy passages.
CASES = (
    AuditCase("autumn-7-8-both", AUTUMN_FILE, 7, 8,
              max_density=MAX_AUTUMN_DENSITY, max_tiny_rests=2,
              features=("aligned_swing",)),
    AuditCase("autumn-1-2-right", AUTUMN_FILE, 1, 2, "right"),
    AuditCase("ala-1-2-left", "Ala_–_Joep_Beving.midi", 1, 2, "left"),
    AuditCase("chopin-1-2-right",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 1, 2, "right"),
    AuditCase("chopin-5-6-both",
              "Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi", 5, 6,
              min_lookahead_beats=1.75, features=("triplet_turn",)),
    AuditCase("danny-boy-1-2-both", "Danny_Boy(Bill_Evans_Ver_).midi", 1, 2),
    AuditCase("merry-go-round-1-2-both", "Merry-Go-Round-of-Life.midi", 1, 2),
    AuditCase("peace-piece-1-2-both", "Peace_Piece_-_Bill_Evans_(Piano_Solo).midi", 1, 2),
    AuditCase("waltz-1-2-both", "Waltz_for_Debby.midi", 1, 2),
    AuditCase("fidelity-chord-ties",
              "tests/fixtures/musical_fidelity/xml_chord_ties.musicxml",
              1, 2, features=("chords","ties")),
    AuditCase("fidelity-quintuplets",
              "tests/fixtures/musical_fidelity/xml_quintuplets.musicxml",
              1, 1, "right", features=("tuplets",)),
    AuditCase("fidelity-grandstaff",
              "tests/fixtures/musical_fidelity/xml_grandstaff_voices.musicxml",
              1, 1, features=("grandstaff",)),
    AuditCase("fidelity-key-change",
              "tests/fixtures/musical_fidelity/xml_keys_spelling.musicxml",
              1, 2, "right", features=("key_change",)),
    AuditCase("fidelity-sparse-rests",
              "tests/fixtures/musical_fidelity/midi_sparse_rests.mid",
              1, 2, "right", features=("rests",)),
    AuditCase("fidelity-midi-triplets",
              "tests/fixtures/musical_fidelity/midi_triplets.mid",
              1, 1, "right", features=("tuplets",)),
)



def selected_cases(only: str | None = None) -> tuple[AuditCase, ...]:
    matches = tuple(c for c in CASES if not only or only.lower() in c.name.lower()
                    or only.lower() in c.filename.lower())
    if not matches:
        raise ValueError(f"No native overlay cases match {only!r}")
    return matches


def library_sources(directory: Path = ROOT / "midi", *, only: str = "") -> tuple[Path, ...]:
    """Discover the complete source library, including future bundled files."""
    sources = tuple(sorted((p for p in directory.iterdir()
                            if p.is_file() and p.suffix.casefold() in {".mid", ".midi"}),
                           key=lambda p: p.name.casefold()))
    if not sources:
        raise ValueError(f"No MIDI files in {directory}")
    selected = tuple(p for p in sources if only.casefold() in p.name.casefold())
    if not selected:
        raise ValueError(f"No MIDI files match {only!r}")
    return selected


def context_first_bar(piece, first_bar: int) -> int:
    """Keep incoming ties by including their real attacks, without inventing one."""
    while first_bar > 1:
        start = piece.bar_boundaries[first_bar - 1]
        incoming = [note.start for note in piece.notes
                    if note.start < start - 1e-7 and note.end > start + 1e-7]
        if not incoming:
            break
        earlier = max(1, bisect_right(piece.bar_boundaries, min(incoming) + 1e-7))
        if earlier >= first_bar:
            break
        first_bar = earlier
    return first_bar


def original_cases(path: Path, piece, *, max_bars: int = 4):
    if max_bars < 1:
        raise ValueError("Window size must be positive")
    count = len(piece.bar_boundaries) - 1
    for first in range(1, count + 1, max_bars):
        last = min(first + max_bars - 1, count)
        context = context_first_bar(piece, first)
        for hand in ("right", "left", "both"):
            yield AuditCase(f"original-{first:04d}-{last:04d}-{hand}",
                            str(path), context, last, hand)


def curriculum_cases(path: Path, piece):
    """Enumerate the actual production curriculum, including dense focus stages."""
    from piano_teacher.learning import LearningPlan
    plan = LearningPlan(piece)
    for index, exercise in enumerate(plan.exercises):
        plan.select(index)
        for hand in plan.hands:
            plan.set_hand(hand)
            for variant in plan.variants:
                case = AuditCase(f"{exercise.kind}-{index:04d}-{hand}-{variant.level}",
                                 str(path), variant.phrase.first_bar,
                                 variant.phrase.last_bar, hand)
                yield case, exercise.phrase, variant


def case_shard(path: Path, case: AuditCase, shard_count: int) -> int:
    """Stable, disjoint case partition; each case belongs to exactly one shard."""
    if shard_count < 1:
        raise ValueError("shard_count must be positive")
    identity = path.name + "\0" + case.name
    return int.from_bytes(hashlib.sha256(identity.encode()).digest()[:8], "big") % shard_count



def discover_sources(*, only, include_fixtures):
    discovered = list(library_sources(only=only))
    if include_fixtures and not only:
        manifest_dir = ROOT / 'tests/fixtures/musical_fidelity'
        manifest = json.loads((manifest_dir / 'manifest.json').read_text())
        discovered.extend(manifest_dir / entry['file'] for entry in manifest['supported'])
    return discovered
