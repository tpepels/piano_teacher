"""Pick complete rhythmic groups and contiguous slur sections in lessons.

Hard groups (beams and short slurs) are never sampled at individual onset
times. Long slurs are practised in contiguous windows, with the original
stage restoring the complete passage. Pitches within a chord can be reduced.
"""
from __future__ import annotations

from collections import defaultdict
from .music import Phrase


def group_variants(phrase: Phrase, hand: str, groups, max_attacks: int):
    """Return nested (level, original phrase indices) preserving hard groups."""
    indexed = [(i, n) for i, n in enumerate(phrase.notes)
               if hand == "both" or n.hand == hand]
    if not indexed:
        return ()
    attacks = defaultdict(list)
    for i, note in indexed:
        attacks[(note.hand, note.track, note.voice, round(note.start, 6))].append(i)
    ordered = sorted(attacks, key=lambda k: (k[3], k[0], k[1], k[2]))
    by_index = {index: key for key, indices in attacks.items() for index in indices}
    positions = {key: i for i, key in enumerate(ordered)}
    # Link the entire span of a group. When another voice overlaps the slur
    # it must not produce disconnected isolated attacks in a first lesson.
    parent = list(range(len(ordered)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a, b):
        parent[find(b)] = find(a)

    # For both-hand drills a simultaneous onset is a single learner action.
    # Do not practise half of that time slice in a group-aligned subset.
    if hand == "both":
        for i in range(1, len(ordered)):
            if ordered[i][3] == ordered[i - 1][3]:
                union(i - 1, i)

    for kind, onsets in groups:
        if kind != "beam" and (kind != "slur" or len(onsets) > max_attacks):
            continue
        locations = [positions[by_index[next(iter(onset))]]
                     for onset in onsets if next(iter(onset)) in by_index]
        if len(locations) != len(onsets):
            continue
        for i in range(min(locations), max(locations)):
            union(i, i + 1)

    blocks = defaultdict(list)
    for i in range(len(ordered)):
        blocks[find(i)].append(i)
    ordered_blocks = sorted(blocks.values(), key=lambda block: block[0])
    def attack_count(chosen):
        return len({ordered[i][3] for i in chosen})

    def prefix(limit):
        chosen = set()
        for block in ordered_blocks:
            proposed = chosen | set(block)
            if chosen and attack_count(proposed) > limit:
                break
            chosen = proposed
            if attack_count(chosen) >= limit:
                break
        return chosen

    first = prefix(max(2, max_attacks // 2))
    second = prefix(max_attacks)
    def indices(chosen, level):
        result = []
        for pos in sorted(chosen):
            tone_indices = sorted(attacks[ordered[pos]], key=lambda i:
                                  (phrase.notes[i].pitch, i))
            if level == "skeleton":
                result.append(tone_indices[-1 if ordered[pos][0] == "right" else 0])
            elif level == "outline":
                result.append(tone_indices[0])
                if len(tone_indices) > 1:
                    result.append(tone_indices[-1])
            else:
                result.extend(tone_indices)
        return tuple(sorted(set(result), key=lambda i:
                            (phrase.notes[i].start, phrase.notes[i].pitch, i)))

    # An outline must include the pitch chosen by the skeleton at every
    # retained onset, so the existing progress stages stay nested.
    last = set(range(len(ordered)))
    candidates = [("skeleton", indices(first, "skeleton")),
                  ("outline", indices(second, "outline"))]
    # A long slur cannot be made into a single <=8-attack exercise.
    # Do NOT sample every nth note: cover its remaining complete rhythmic
    # blocks in consecutive sections before the final original performance.
    # Keep these sections separate from skeleton/outline rather than
    # pretending they are increasingly complete subsets of one phrase.
    if any(kind == "slur" and len(onsets) > max_attacks
           for kind, onsets in groups):
        covered = set(second)
        remaining = [block for block in ordered_blocks if not set(block) <= covered]
        section_number = 2
        while remaining:
            selected_positions = set()
            while remaining:
                block = set(remaining[0])
                proposed = selected_positions | block
                if selected_positions and attack_count(proposed) > max_attacks:
                    break
                selected_positions = proposed
                remaining.pop(0)
            candidates.append((f"section-{section_number}",
                               indices(selected_positions, "outline")))
            section_number += 1
    candidates.append(("original", indices(last, "original")))
    results = []
    for level, selected in candidates:
        if selected and (not results or selected != results[-1][1]):
            results.append((level, selected))
    if len(results) == 1:
        return (("original", results[0][1]),)
    if results[-1][0] != "original":
        results[-1] = ("original", results[-1][1])
    return tuple(results)
