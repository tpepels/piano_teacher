# Coda Gate 2 — root causes of the 26 pinned differential discrepancies

**Date:** 2026-11-01. **Scope:** research only, not production Coda.
**Issue:** [#42](https://github.com/tpepels/piano_teacher/issues/42).

## Reproduction

- Author: [`annieetang/coda_backend@a4eb85df`](https://github.com/annieetang/coda_backend/tree/a4eb85dfc2bd418818ca9ff775c0a11ccccb3530), executed unmodified except for the unused database service initializer.
- Current reference gate: [GitHub Action 41338162668](https://github.com/tpepels/piano_teacher/actions/runs/41338162668), successful; artifact `13095553270`.
- Author and native **serialized MusicXML** are independently normalized to voice-owned written noteheads, rests, ties, pitches, and quarter-beat intervals. Explicit contiguous tie chains then yield **sounding** notes. The native grading `TimingPlan` is independently checked against native written sounding notes.
- Re-run the bounded `.github/workflows/coda-upstream-parity.yml` workflow manually. It writes `real-source-voices.json`, including **complete** original/native written streams, sounding streams, original source-attack timelines, fixture SHA-256, first differences and source conditions for each discrepancy.
- `piano_teacher/research/coda_discrepancy.py` provides the fixture-scoped causal diagnoses; `tests/test_coda_discrepancy.py` checks that exact-pitched/rest, tie-gap, source-guard and unknown scenarios are not conflated.
- Pinned fixture enumeration: `scripts/probe_coda_upstream_scores.py:CASES`. The six selected scores contain two matched source voices each: **12/12** exact MMR source voices.

## Result

Of 60 selected exercise outputs: 30 exact in writing and sounding; 10 sounding-exact but written-different; 15 sounding-different; one original Coda output with a disconnected written tie; four original backend `None` returns. **All 26 non-exact/non-None cases are classified, zero unclassified.** Classifications are about these fixtures and exact parameters only; they do not prove broader correctness or pedagogical equivalence.

| Root cause or observed difference | Cases | Evidence |
|---|---:|---|
| Different rest coverage, same pitched written fragments and sounding notes | 5 | Four parallel-tie x2/x4 slowdowns plus changing-meter LH chord |
| Different written tuplets/tie subdivisions, same sounded notes | 1 | Rest-bearing triplet RH slowdown x2 |
| Different written meter-based subdivisions, same sounded notes | 4 | Changing-meter RH/LH slowdowns x2/x4 |
| Guarded beamed passage versus author transformation | 3 | Authored beams RH dotted both directions and 2-beat chord |
| Guarded cross-measure grouping versus author dotted retiming | 2 | Long multipage first-two-bars LH both dotted patterns |
| Guarded authored tuplet versus author retiming/chordification | 2 | Authored triplet RH dotted 1:3 and chord |
| Guarded rest-bearing tuplet versus author transformation | 3 | Rest-bearing triplet RH dotted both directions and chord |
| Author truncates dotted duration to whole ticks at 3 ticks/quarter | 4 | Changing-meter RH/LH dotted both directions |
| Author forms chord across source 3/4-to-2/4 bar boundary | 1 | Changing-meter RH chord |
| Author exports disconnected tie continuation | 1 | Authored triplet RH dotted 3:1 |
| **Total** | **26** | Full per-case counterexamples in workflow artifact |

## Per-case register

Each row below identifies **every** non-exact case from the retained 60-case report. Voice indices refer to the reference score's selected part/voice ordering.

| Fixture | Voice | Operations | Category | Count |
|---|---|---|---|---:|
| `source-parallel-ties` | 0, 1 | `slow-x2`, `slow-x4` | Rest coverage only | 4 |
| `source-authored-beams` | 0 | `dotted-3-to-1`, `dotted-1-to-3`, `chord-2-beat` | Beam guard | 3 |
| `long-multipage-first-two-bars` | 1 | Both dotted patterns | Cross-measure guard | 2 |
| `authored-triplet` | 0 | `dotted-3-to-1` | Disconnected upstream tie | 1 |
| `authored-triplet` | 0 | `dotted-1-to-3`, `chord-2-beat` | Tuplet guard | 2 |
| `rest-bearing-triplet` | 0 | `slow-x2` | Written subdivision only | 1 |
| `rest-bearing-triplet` | 0 | Both dotted patterns, `chord-2-beat` | Rest/tuplet guard | 3 |
| `changing-meter` | 0, 1 | `slow-x2`, `slow-x4` | Written meter subdivision only | 4 |
| `changing-meter` | 1 | `chord-2-beat` | Rest coverage only | 1 |
| `changing-meter` | 0, 1 | Both dotted patterns | Quantization truncation | 4 |
| `changing-meter` | 0 | `chord-2-beat` | Cross-meter chord | 1 |
| **Total** | | | | **26** |

## Minimal counterexamples and code causes

1. **Rest coverage (5).** In the first parallel-tie voice at slowdown x2, both generators produce the same tied C4 (MIDI 60), sounding from beat 0 to 12. The native complete selected excerpt additionally writes a rest from beat 12 to 16; the reference output ends at beat 12. No new pitch attack or grading difference. The changing-meter LH chord has the same situation with a final rest.
2. **Equivalent sounding, different written segments (5).** The rest-bearing triplet x2 and mixed-meter x2/x4 exercises retain identical sounding notes, but differ in tie splitting and/or inserted rests. In changing-meter RH x2, the reference ties the final G5 over 8–9 and 9–10, while native renders one G5 from 8–10. The source meter context differs: the original author uses the first meter and the native source-aware projection uses 3/4 followed by 2/4. No grading discrepancy.
3. **Beam guard (3).** For source C4–D4 eighths (0–0.5 and 0.5–1), the author's dotted 3:1 output shifts to 0–0.75 and 0.75–1. The adapter retains the eighths because the authored beam group is protected until its connected notation can be safely transformed. Original Coda also groups four eighth notes into blocked 2-beat chords, while adapter keeps the original beamed run.
4. **Cross-measure guard (2).** Multipage LH has consecutive **independent** C3 notes (MIDI 48) at 0–4 and 4–8. Original dotted 3:1 produces 0–6 and 6–8; adapter refuses a grouping straddling the barline at 4. These are not ties, so the difference is not explained by MIDI sustain normalization.
5. **Authored triplet guard (2).** Original Coda's chordification collapses the initial triplet C5–D5–E5 attacks at beats 0, 1/3, 2/3 into a blocked chord at 0–1; the adapter preserves original tuplets. Its short-long dotted run differs for the same notation-safety policy.
6. **Rest-bearing triplet guard (3).** Dotted original-Coda outputs also **lose MIDI pitch 76** in this fixture, whereas the adapter retains that source pitch. Source has a written rest inside the 3:2 group. The author's chordification moves notes across that rest while the adapter preserves the written-rest context. These are real sounding differences; they must not be counted as equivalent output.
7. **Changing-meter dotted grid (4).** The first source meter is 3/4, yielding author/reference quantization **3 ticks per quarter** for this sample. In its dotted routine, the author converts duration multipliers with `int()`, so 3 × 1.5 = 4.5 ticks becomes **4**, or 4/3 beats, rather than the intended 1.5 beats. The guarded adapter refuses the non-integral grid transformation. This explains both dotted patterns for RH and LH.
8. **Cross-meter chord (1).** In changing-meter RH, Coda places MIDI 76 and 77 together at beat 2 for a duration of two beats (through beat 4), crossing the meter/barline change at beat 3. The adapter leaves the original notes at 2–3 and 3–4 because chordification groups must stay within one authored measure.
9. **Disconnected upstream tie (1).** Original authored-triplet RH dotted 3:1 exports an E5/MIDI 76 written tie start at 0.666667–1 and a stop at 2.5–2.666667; that is an invalid continuation with a 1.5-beat gap. The original score is not a safe MIDI target for this output. Native retains the source note at 0.666667–1 without fabricating another attack.

## Conclusions and boundaries

These 26 discrepancies are now *reproducibly accounted for within the six checked fixtures*. The author may emit musically unsafe outputs; matching its note arrays is not always a valid production requirement. Every diagnosis cites exact serialized written and sounding traces in the retained JSON report, with the same source revision and original backend.

The case classifier deliberately uses known fixture names for categorical **scope**, then includes actual source/native/reference event differences and source-versus-adapter timing. An unfamiliar fixture is reported `unclassified` instead of receiving a guessed explanation. Classification is not a proof that every possible score sharing a fixture feature behaves identically.

**No changes** to exercise-generation strategies, source import, notation rendering, MIDI grading or teaching. Gate 2 remains research-only. Next: define the supported parity subset and separately validate full notation preservation and native Godot/physical MIDI on accepted exercises.
