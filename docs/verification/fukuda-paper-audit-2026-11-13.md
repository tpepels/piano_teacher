# Fukuda paper-to-code audit — 2026-11-13

Primary reference: Fukuda, Ikemiya, Itoyama and Yoshii, [SMC 2015 paper](https://sap.ist.i.kyoto-u.ac.jp/lab/bib/intl/FUK-SMC15.pdf), sections 3.2–3.4 and Figures 4–8. Downloaded PDF SHA-256: `6aecdbd3f955b01534364c55e12c1d5d452d679e7fcd2f499060dc9e1bc0ff68`. Page 4, including Figures 4–6, was rendered and visually inspected.

| Requirement | Current MIDI implementation | Qualification |
| --- | --- | --- |
| Chord simplification, §3.4.1 / Fig. 4 | `rule_chord_outer` preserves extremes and removes interior attacks in eligible chords | The paper permits priority-based interior removal; it does not specify this maximal reduction as the sole output. |
| Fast passages, §3.4.2 / Fig. 5 | `rule_fast_thinning`: 0.21 seconds, alternating interior notes; endpoints, overlaps and local peaks protected | The paper's threshold is not numerical. The value and melody guard are implementation choices. Fig. 5 changes written note values; this product retains original MIDI release durations. |
| Returning leap, §3.4.3 / Fig. 6a | `rule_octave_leaps`: adjacent jumps greater than 12 semitones, returning within 12 | Explicit MIDI inequalities operationalize the illustrated rule. |
| One-way leap, §3.4.3 / Fig. 6b | Chord/fast reduction within two beats of either endpoint | Two beats is an engineering locality choice. |
| Chroma alignment, §3.2 | Recorded-MIDI chroma/cosine DTW | MIDI substitutes for acoustic transcription; live grading retains the existing clock. |

The acoustic CQT/NMF and octave-artifact suppression remain outside MIDI-only input. A wrong MIDI octave remains an error. Figures 7–8 are illustrated experimental outputs, not a supplied executable reference dataset. Exact figure-event and numerical equivalence remain unproved; software corpus acceptance certifies source-safe MIDI behavior only. Human learning and delayed retention require the separate consented comparison protocol in [mistake-response-policies.md](../mistake-response-policies.md#evaluation-protocol).
