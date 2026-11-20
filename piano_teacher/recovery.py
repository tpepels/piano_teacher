"""Shared rolling-recovery decision facts.

The canonical graded rolling assessment lives in timed_assessment.py.
Do not reintroduce the retired parallel evaluator or fixed-meter fallback.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryDecision:
    end_beat: float
    restart_beat: float
    errors: int
    wrong: int
    missed: int
