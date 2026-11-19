# Archived Practice Flow comparison — 17 November 2026

**Historical snapshot only.** This table predates the mandatory
measure-first sliding curriculum and the 19 November 2026 admission,
verdict and presentation refactors. It must not be used as a description
of the current product. The living requirements are in
[practice-flow.md](../../practice-flow.md) and implementation progress
is tracked in [ownership remediation](../ownership-and-practice-progression-remediation.md).

## Current application versus this flow (2026-11-17)

| Moment | This flow | Application today |
|---|---|---|
| Open | Phrase 1 starts with Listen | No playback; first exercise starts |
| Division | Musical phrases of 2-4 bars | One bar per exercise (Beethoven Op. 13 II: 136 exercises) |
| Steps per hand | Listen -> Free -> Tempo on the real notes | 3-4 stages: Coda/Fukuda transformations first, then x2/x4 slowdowns, then the original |
| Coda/Fukuda | Announced aid only | Always the first stage, not clearly announced |
| Free step | Fixed step before Tempo | Only after 2 failed attempts or via a button; showed no notes until 7289fa80 |
| Start tempo | 50% of target | Fixed 40 BPM, about 12 steps to target |
| Done | 2 clean in a row at target | 3 clean at target, for every stage |
| Errors | 2 failed -> -10%, floor 50%, then Free | -10% after 5 errors in a window; guided mode after 2 failures |
| Between attempts | Directly, one bar count-in | Feedback pause, then the leading rest, then count-in |
| Leading rest/pickup | Skipped | Sat out in full |
| Linking | 1+2, 2+3, ... per hand and together | 1+2, 3+4, 1-4 (doubling), both hands only |
| Final test | Whole piece, 50% -> target, 2 clean | Whole piece at the end (present) |
| Resume | Same phrase, from Free | Same stage and tempo |
| Free display | Target waits on the playhead | Fixed in 7289fa80; previously an empty staff |
| Feedback colours | Green/red, plus a ghost note for a wrong key | Five status colours (hit, missed, late, early release, early onset) |
| Timing errors | Only clearly off counts | Timing deviations can fail an attempt |
| Count-in | Clicks and large numbers | Spoken count-in voice |
| Keyboard | Only as a hint after a wrong note in Free | Shown in guided mode and on hints |
| Quick-note spacing | At least ~3.3 staff spaces per 16th | 52 px per quick attack (about 2.4 spaces) |
