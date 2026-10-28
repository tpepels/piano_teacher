Extended retained Peace Piece profiling (2026-10-27)

The 600s interruption is consistent with accumulated work over thousands of tightly spaced frames. The optimization reduces valid-correlation FFT cost; these measurements do not establish that either complete case finishes within 600s.

Workload verified from the retained fixtures, manifest, native report and PNG names:

| Case | Actual bars | Measures | Beats | Source model notes | PNGs | Original + added captures |
|---|---:|---:|---:|---:|---:|---:|
| original-0061-0064-left | 47–64 | 18 | 72 | 532 | 6097 | 458 + 5639 |
| original-0069-0072-right | 47–72 | 26 | 104 | 758 | 8832 | 686 + 8146 |

Both nominal four-bar names expand back to bar 47. scripts/check_native_verovio_overlay.py:577 recursively follows incoming ties to their real attacks. The renderer-selected global density is 7520.92456054517 px/beat in both retained reports. The density witness is horizontal ink clearance between beat 43.99375 (128th note) and beat 44.0, a separation of 0.00625 beats. This metadata explains capture scheduling; it is not used as pixel ownership evidence.

tests/godot/native_verovio_overlay.gd:16 chooses interval = min(0.15, 96/density) = 0.012764388105103 beats. Source clocks are retained in addition to that uniform grid. Median adjacent PNG spacing is 0.01276 beats; maxima are 0.01277 after five-decimal naming. Duration and spacing are beats, not seconds.

Methods: four sequential calls of the actual verify_extra_symbol_pixels on the complete retained folders, each interrupted by a 60s signal raising a private BaseException outside the checker's expected-error handlers. Outer process cap 80s, address-space cap 3 GiB, one FFT job at a time. No checker behavior changed. cProfile, completed per-frame JSONL records and partial final-frame/stage information were saved on interruption. Python wrappers record stages and hashes but do not skip work or create verifier results on timeout.

The saved baseline module and saved optimized module share the same imported dependency functions. Their dependency fingerprints were checked. Equal completed prefixes are compared separately from differing 60s progress.

| Case / phase | Completed frames at 60s | Next interrupted frame | Beat | Wall / CPU seconds |
|---|---:|---|---:|---:|
| original-0061-0064-left / before | 675 | native-8.05433.png | 8.05433 | 60.030 / 59.058 |
| original-0061-0064-left / after | 790 | native-9.42012.png | 9.42012 | 60.032 / 59.712 |
| original-0069-0072-right / before | 840 | native-9.96875.png | 9.96875 | 60.038 / 58.912 |
| original-0069-0072-right / after | 951 | native-11.27095.png | 11.27095 | 60.044 / 59.748 |

All four stopped in the first pass. The last interrupted frame is zero-based; it is not counted as completed. None reached the residual/boundary pass.

| Identical completed prefix | Stage wall before → after | Stage CPU before → after | Scan wall before → after | Scores wall before → after |
|---|---:|---:|---:|---:|
| original-0061-0064-left, 675 frames | 59.264 → 50.479 | 58.303 → 50.299 | 23.867 → 18.560 | 18.166 → 13.487 |
| original-0069-0072-right, 840 frames | 58.324 → 53.410 | 57.211 → 53.256 | 20.233 → 16.895 | 14.251 → 11.075 |

Stage totals sum _photo, _motion, _areas, _scan and _bind wrapper wall/CPU timers over the exact shared frames. They exclude outer-loop bookkeeping, JSON logging and setup, so they are not end-to-end prefix elapsed times. _scores is nested inside _scan and is not added again. Candidate hashes, post-binding object/owner/error hashes, scan areas, shifts/bands, expected errors and stage call counts agree for every shared frame. Timing changes in untouched _photo show cache/system variance, so the entire aggregate improvement should not be attributed to the FFT change.

Baseline first-pass observations:

| Case | Photo / scan / motion / bind wall seconds | Successful scans | Full requests | Motion-fallback full / recovery full | Mean requested → padded viewport fraction | Maximum frame stage bundle |
|---|---|---:|---:|---|---:|---:|
| original-0061-0064-left | 28.23 / 23.87 / 6.41 / 0.33 | 438 | 27 | 24 / 2 | 0.282 → 0.325 | 0.481s |
| original-0069-0072-right | 29.95 / 20.23 / 7.33 / 0.42 | 475 | 22 | 18 / 3 | 0.218 → 0.258 | 0.774s |

The extra full request in each row is the opening endcap. Padding created no additional full-viewport searches in these shared prefixes. Full requests consumed 8.43s of 23.87s scan time on the left (35%) and 5.05s of 20.23s on the right (25%): significant amplification, but not a full scan on every frame. _areas itself consumed only 0.42s / 0.39s.

There were 237 photographic-rule failures in the left shared prefix and 365 on the right. They are identical before/after, are reported unverified by the checker, and reset tracking. The few recovery full scans and motion failures are included above. This subtask did not investigate or modify those independent photographic checks.

No measured frame-stage bundle across the capped prefixes and representative windows exceeded 0.80s. The five largest baseline prefix frames account for only 3.9% / 4.1% of the stage totals. Measured source _bind cost is <1% of capped wall time. The first-pass profile supports accumulated repeated work, rather than a small number of large stalls.

Representative exact workloads: each is a real three-frame temporary symlink folder passed to the complete verifier, before and after. Both passes finish. Begin, middle and terminal are positional selections; dense-onset selects the largest simultaneous source-note count (11 at beat 39.96875); dense-ink selects the largest photographable ink count among 13 stratified positions plus that onset. This is a sampled density maximum, not an exhaustive PNG ranking. Each window forces its own opening/closing endcaps, and has intentionally incomplete whole-score clock coverage. No original PNG or case file was written.

| Case | Window / frames (beats) | Wall before → after | CPU before → after | Exact report equality |
|---|---|---:|---:|---|
| original-0061-0064-left | begin: 0.00000, 0.01276, 0.02553 | 0.881 → 0.812 | 0.878 → 0.810 | yes |
| original-0061-0064-left | middle: 36.00834, 36.02110, 36.03387 | 1.638 → 1.580 | 1.627 → 1.575 | yes |
| original-0061-0064-left | dense-onset: 39.96530, 39.96875, 39.97806 | 0.824 → 0.807 | 0.818 → 0.804 | yes |
| original-0061-0064-left | terminal: 71.97838, 71.99115, 72.00000 | 0.890 → 0.854 | 0.883 → 0.852 | yes |
| original-0061-0064-left | dense-ink: 36.00000, 36.00834, 36.02110 | 1.804 → 1.808 | 1.795 → 1.802 | yes |
| original-0069-0072-right | begin: 0.00000, 0.01276, 0.02553 | 0.862 → 0.856 | 0.859 → 0.853 | yes |
| original-0069-0072-right | middle: 52.07870, 52.09147, 52.09375 | 1.506 → 1.499 | 1.501 → 1.493 | yes |
| original-0069-0072-right | dense-onset: 39.96530, 39.96875, 39.97806 | 0.162 → 0.156 | 0.159 → 0.156 | yes |
| original-0069-0072-right | terminal: 103.97871, 103.99147, 104.00000 | 1.018 → 0.975 | 1.010 → 0.972 | yes |
| original-0069-0072-right | dense-ink: 78.01594, 78.02870, 78.04147 | 2.320 → 2.299 | 2.308 → 2.286 | yes |

These single-run window timings are descriptive, not a library-weighted speedup. Full-viewport FFT sizes often do not shrink, explaining the small gains in late/dense windows.

The left dense-onset window has one photographable frame; the right dense-onset window has zero. Their exact reports preserve those unverified errors. The separate dense-ink windows (near beat 36.00834 left and 78.02870 right) each measure all three frames.

In successful three-frame windows, the residual pass alone spends about 0.15–0.17s decoding the three frames again (~50–55ms per successful frame). Head-boundary evidence takes at most 0.009s per window and rectangular-rest component checks at most 0.030s. Sample source _bind totals peak at 0.065s. These are small relative to repeated decode/scan costs in the measured windows. A complete-case residual pass, source-anchor-tree queries under fully verified coverage, and every later source binding were not measured; those costs cannot be ruled out globally.

Strong conclusions: tie context and density produce far more work than the nominal case names suggest; _photo and repeated _scan dominate measured wall/CPU; motion adds a regular cost; full-scan fallback amplifies scan cost but is not universal; _bind and boundary/component checks do not dominate the measured samples; valid-FFT optimization retains exact outputs and improves shared-prefix scan time.

Weak conclusions: simple prefix-rate projections for first pass only are approximately 542 → 463s left and 631 → 558s right, excluding the later residual pass. Those are extrapolations, not completed-case runtimes: content changes, photographic errors, cache state, cProfile overhead and worker contention can alter the rate. The worker budget also includes earlier stages. These figures explain why sub-second three-frame samples are compatible with a 600s worker timeout; they do not prove an exact timeout cause at a particular frame or that 600s is now sufficient.

Artifacts: workload.json; full-analysis.json; representative.json; *.full60.summary.json / *.frames.jsonl / *.pstats / *.profile.txt; per-window *.report.json; saved baseline/optimized modules and reproducer scripts. Full diagnostic processes peak around 397–405 MiB RSS; the sequential representative process peaks around 836 MiB. All had a 3 GiB address-space cap and process runtime below 120s.

No additional production or test edits were made for this follow-up. No full audit, render, CI, worktree, commit or push. Existing cases remained read-only.
