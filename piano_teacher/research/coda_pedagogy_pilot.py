"""Pre-registered, blinded pilot analysis of Coda-versus-heuristic lessons.

This module NEVER decides pedagogy from synthetic MIDI, stage complexity,
course length or unit-test success. It processes independent real-player
pre/post tests on the SAME original-piece performance and SAME fixed BPM,
after equal practice exposure. Assignments are reproducible and blinded
(A/B); the study coordinator holds the A/B-to-strategy mapping separately.

No personal names, MIDI note streams, contact data or medical information.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import hmac
from itertools import combinations, product
from math import comb, isfinite
import random


PROTOCOL = "coda-pedagogy-fixed-performance-pilot-v1"


def assigned_arm(subject: str, piece: str, *, secret: str) -> str:
    """Stable cryptographic 1:1 assignment without human-readable identity."""
    if not all(isinstance(v,str) and v.strip()
               for v in (subject,piece,secret)):
        raise ValueError("Assignment needs anonymous subject, piece and private seed")
    digest=hmac.new(secret.encode(),f"{PROTOCOL}|{piece}|{subject}".encode(),
                    "sha256").digest()
    return "A" if digest[0]&1==0 else "B"


@dataclass(frozen=True)
class PilotObservation:
    anonymous_subject: str
    piece_fingerprint: str
    blinded_arm: str
    original_score_attacks: int
    test_bpm: int
    pre_correct: int
    pre_extra: int
    post_correct: int
    post_extra: int
    practice_minutes: float
    assessment_version: str
    instrument: str = "physical-midi"
    completed_original_score: bool = True

    def __post_init__(self) -> None:
        if not self.anonymous_subject or not self.piece_fingerprint:
            raise ValueError("Use pseudonymous subject and stable piece fingerprint")
        if self.blinded_arm not in ("A","B"):
            raise ValueError("Keep the study assignments blinded A/B")
        if self.instrument!="physical-midi" or not self.completed_original_score:
            raise ValueError("Only real physical-MIDI whole-original-score tests count")
        if not self.assessment_version:
            raise ValueError("Assessment software revision required")
        if type(self.test_bpm) is not int or self.test_bpm<=0:
            raise ValueError("Fixed MIDI test tempo must be positive integer")
        if (type(self.original_score_attacks) is not int or
                self.original_score_attacks<=0):
            raise ValueError("Original score must contain tested note attacks")
        for count in (self.pre_correct,self.post_correct,
                      self.pre_extra,self.post_extra):
            if type(count) is not int or not 0<=count:
                raise ValueError("Invalid note-level test count")
        if max(self.pre_correct,self.post_correct)>self.original_score_attacks:
            raise ValueError("Correct attack count exceeds original-score attacks")
        if not isfinite(self.practice_minutes) or self.practice_minutes<0:
            raise ValueError("Invalid training exposure")

    def accuracy(self, moment: str) -> float:
        """Consistent original-performance metric, penalizing extra notes."""
        correct=getattr(self,f"{moment}_correct")
        extras=getattr(self,f"{moment}_extra")
        return max(0.0, (correct-extras)/self.original_score_attacks)

    @property
    def gain(self) -> float:
        return self.accuracy("post")-self.accuracy("pre")


def _difference(rows: tuple[PilotObservation,...]) -> float:
    grouped=defaultdict(list)
    for r in rows:
        grouped[r.piece_fingerprint].append(r)
    weighted=[]
    for values in grouped.values():
        a=[x.gain for x in values if x.blinded_arm=="A"]
        b=[x.gain for x in values if x.blinded_arm=="B"]
        if not a or not b:
            raise ValueError("Each tested piece needs both randomized arms")
        effect=sum(a)/len(a)-sum(b)/len(b)
        weighted.append((effect,len(values)))
    return sum(effect*n for effect,n in weighted)/sum(n for _,n in weighted)


def _permutation_p(rows: tuple[PilotObservation,...], *, seed: int) -> tuple[float,int]:
    groups=defaultdict(list)
    for r in rows:
        groups[r.piece_fingerprint].append(r)
    configs=[]
    for values in groups.values():
        n_a=sum(x.blinded_arm=="A" for x in values)
        configs.append((values,n_a,comb(len(values),n_a)))
    total=1
    for _,_,count in configs:
        total*=count
    obs=abs(_difference(rows))
    if total<=16000:
        perms=(list(combinations(range(len(v)),na)) for v,na,_ in configs)
        allocations=product(*perms)
        limit=total
    else:
        rng=random.Random(seed)
        allocations=(
            tuple(tuple(sorted(rng.sample(range(len(v)),na)))
                  for v,na,_ in configs)
            for _ in range(10000))
        limit=10000
    extreme=0
    for assignment in allocations:
        reallocated=[]
        for (values,_,_),indices in zip(configs,assignment):
            chosen=set(indices)
            for j,v in enumerate(values):
                from dataclasses import replace
                reallocated.append(replace(v,blinded_arm="A" if j in chosen else "B"))
        if abs(_difference(tuple(reallocated)))>=obs-1e-12:
            extreme+=1
    return (extreme/limit if total<=16000 else (extreme+1)/(limit+1),
            limit)


def analyze_pilot(
    observations: tuple[PilotObservation,...], *,
    secret: str, seed: int = 2015,
) -> dict:
    """Analyze blinded paired-piece strata; does NOT assert causal success.

    A valid evaluation uses the pre-registered fixed-BPM original-score
    tests before and after equal-duration Coda or heuristic practice.
    This report remains descriptive until genuine study data are provided.
    """
    if not observations:
        raise ValueError("No real learner observations")
    if not isinstance(secret,str) or not secret:
        raise ValueError("Verify concealed randomization seed")
    seen=set()
    by_piece=defaultdict(list)
    for r in observations:
        # Avoid falsely treating repeated observations from the same
        # individual across pieces as independent randomization units.
        if r.anonymous_subject in seen:
            raise ValueError("Pilot needs one original piece per participant")
        seen.add(r.anonymous_subject)
        if assigned_arm(r.anonymous_subject,r.piece_fingerprint,secret=secret)!=r.blinded_arm:
            raise ValueError("Observed group does not match randomized allocation")
        by_piece[r.piece_fingerprint].append(r)
    piece_rows=[]
    for piece,rows in sorted(by_piece.items()):
        if len({r.original_score_attacks for r in rows})!=1:
            raise ValueError("Unequal source score attack count across arms")
        if len({r.test_bpm for r in rows})!=1:
            raise ValueError("Test BPM differs across randomized arms")
        if len({r.assessment_version for r in rows})!=1:
            raise ValueError("Assessment version differs across arms")
        if {r.blinded_arm for r in rows}!={"A","B"}:
            raise ValueError("Both arms required for every piece")
        doses=[r.practice_minutes for r in rows]
        if any(abs(x-15.0)>0.25 for x in doses):
            raise ValueError("Practice exposure must be 15 minutes ± 15 seconds")
        if max(doses)-min(doses)>0.25:
            raise ValueError("Practice exposure is unequal across arms")
        piece_rows.append({"piece":piece,
            "players":len(rows),"target_bpm":rows[0].test_bpm,
            "test_note_attacks":rows[0].original_score_attacks,
            "mean_gain_A":sum(r.gain for r in rows if r.blinded_arm=="A")/
                          sum(r.blinded_arm=="A" for r in rows),
            "mean_gain_B":sum(r.gain for r in rows if r.blinded_arm=="B")/
                          sum(r.blinded_arm=="B" for r in rows)})
    effect=_difference(observations)
    p,draws=_permutation_p(observations,seed=seed)
    return {
        "protocol":PROTOCOL,
        "blinded":True,
        "observations":len(observations),
        "pieces":piece_rows,
        "primary_outcome":"change in fixed-BPM whole-original-score attack accuracy, extras penalized",
        "arm_A_minus_B_gain":round(effect,8),
        "within_piece_label_permutation_p":round(p,8),
        "permutation_draws":draws,
        "study_conclusion":"descriptive blinded pilot; independent human efficacy claim requires real recruitment, intervention fidelity, retention and preregistered analysis",
        "source":"real physical-MIDI pre/post tests only; cannot be inferred from software fixtures",
    }
