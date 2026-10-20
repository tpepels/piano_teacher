"""Match plain optional grace records without adding required score events.

Beats are quarter beats relative to the supplied phrase. Position is notation
metadata; it never moves an attack off the authoritative linear time axis.
"""
from __future__ import annotations


def relative_optional_notes(optional_notes: tuple[dict, ...] = (),
                            from_beat: float = 0.0) -> tuple[dict, ...]:
    """Copy/rebase metadata when a caller slices a phrase at from_beat.

    Grace records before the seek point belong to the previous passage and
    cannot suppress mistakes in the new attempt. The source dicts stay intact.
    """
    return tuple(dict(note, beat=note["beat"] - from_beat)
                 for note in optional_notes if note["beat"] >= from_beat - 1e-7)


def match_optional_note(optional_notes: tuple[dict, ...], *, pitch: int,
                        onset: float, hand: str, seconds_per_beat: float,
                        search_window: float, used: set[str],
                        from_beat: float = 0.0) -> dict | None:
    """Consume one nearest eligible grace identity, after required matching.

    Onset is in seconds from the take's from_beat. Hand comes from the source
    staff, never from the MIDI pitch (hands may cross).
    """
    candidates = [
        (abs(onset - (note["beat"] - from_beat) * seconds_per_beat), index, note)
        for index, note in enumerate(optional_notes)
        if note.get("kind") == "grace" and note["id"] not in used
        and note["midi_pitch"] == pitch
        and (hand == "both" or note["staff"] == hand)
        and note["beat"] >= from_beat - 1e-7
        and abs(onset - (note["beat"] - from_beat) * seconds_per_beat) <= search_window
    ]
    if not candidates:
        return None
    _, _, note = min(candidates, key=lambda item: item[:2])
    used.add(note["id"])
    return note
