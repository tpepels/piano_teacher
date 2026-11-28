"""Original Coda's automatically enumerated chordification widths.

This reproduces only the parameter *set* in Annie Tang's pinned backend
music/exercise.py:249. It does not grant parity for any generated exercise.
A zero width is preserved as an author-invalid parameter for diagnostics,
rather than silently normalized to a valid operation.
"""
from __future__ import annotations


def original_chord_levels(quantization: int, numerator: int,
                          denominator: int) -> tuple[int, ...]:
    if any(type(value) is not int or value <= 0
           for value in (quantization, numerator, denominator)):
        raise ValueError("Positive integer quantization and meter required")
    q, n, d = quantization, numerator, denominator
    return tuple(sorted({
        q, q * 2, q // 2,
        d, d * 2, d // 2,
        n * d,
    }))
