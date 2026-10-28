Compact photographic cache: implementation and bounded evidence

Owned changes: piano_teacher/notation/extra_symbol_pixels.py and tests/test_photo_cache.py.

The verifier instantiates one private _PhotoCache per invocation. Five boolean masks are packed losslessly with numpy.packbits, combined with exact JSON scalar/staff metadata, and compressed with zlib level 1. The cache retains no decoded arrays or PNG byte buffers. Reconstruction allocates fresh boolean arrays, column arrays, dictionaries and frozen RasterStaff objects.

Limits: 96 MiB of charged resident entries, at most 10,000 entries. Charge includes compressed bytes, SHA-256, path key, tuple objects and conservative 512-byte per-entry bookkeeping. Fixed empty-container overhead and transient packing/decoding allocations are additional. PNG buffering is limited to 16 MiB + 1 byte; larger PNGs use the unchanged ordinary photo analysis. Oversized entries, evictions, disabled caching and misses decode normally. No frame, region, candidate or threshold is removed.

The cache key includes the exact frame path. Capture hashes and decodes the same bounded PNG byte snapshot. Retrieval consumes the entry and hashes newly read current PNG bytes. Matching SHA-256 restores the lossless photo; changed bytes are freshly decoded. Error results are never retained. Corrupt-PNG path-based PIL error evidence is preserved. No cache survives the verifier call. The original two-pass ownership/coverage logic and two-decoded-frame policy remain intact.

TDD: the initial reuse regression failed before implementation; the later complete-verifier integration test also observed two decodes instead of one. After implementation, the focused run passed 52 tests in 12.27s. Test paths:

- tests/test_photo_cache.py (13 cases, including a <=15s isolated resource test with 3 GiB address-space cap)
- tests/test_extra_symbol_valid_fft.py
- tests/test_extra_symbol_shard_regressions.py
- tests/test_joint_registration_resources.py
- Seven non-rendering unit/retained-frame cases in tests/test_extra_symbol_pixels.py

Controls: exact real-photo masks and metadata/dtypes; no mutable sharing; entry and byte eviction; oversized PNG and payload bypass; non-byte-aligned masks; damaged PNG; erased real onset heads; wrong-clock coverage rejection; same-size/same-mtime changed PNG; complete report equality with caching disabled; between-pass erasure invalidation; no cross-call reuse. Full audit, capture/rendering, full CI and commits were not run.

Profiles: same complete verifier calls on retained beginning, middle, dense-source-onset, dense-photographed-ink and terminal three-frame windows for each Peace Piece case. Existing window symlinks and captures were read only. Each window was warmed, then cache disabled/enabled alternated over three measured repetitions. Tables show sums of per-window medians, not a complete retained-case runtime. All warmup and measured reports are exactly equal, including errors and coverage. Each process had a 120s outer timeout, 110s alarm and 3 GiB address-space limit; FFT jobs were sequential.

| Case | Complete sampled verifier wall, disabled → enabled | CPU, disabled → enabled | Second-pass photo wall, disabled → enabled | Second decodes, disabled → enabled |
|---|---:|---:|---:|---:|
| original-0061-0064-left | 5.389 → 4.736s | 5.370 → 4.719s | 0.657343 → 0.008685s | 13 → 0 |
| original-0069-0072-right | 5.418 → 4.779s | 5.401 → 4.764s | 0.622855 → 0.008288s | 12 → 0 |

| Case / window | Complete verifier wall, disabled → enabled | First-pass capture wall, disabled → enabled | Second-pass photo wall, disabled → enabled |
|---|---:|---:|---:|
| original-0061-0064-left / begin | 0.756 → 0.594s | 0.151509 → 0.151943s | 0.149542 → 0.001868s |
| original-0061-0064-left / middle | 1.464 → 1.313s | 0.153412 → 0.156189s | 0.153612 → 0.002135s |
| original-0061-0064-left / dense-onset | 0.721 → 0.676s | 0.074135 → 0.075406s | 0.051370 → 0.000777s |
| original-0061-0064-left / dense-ink | 1.645 → 1.502s | 0.153105 → 0.158165s | 0.152192 → 0.002079s |
| original-0061-0064-left / terminal | 0.802 → 0.651s | 0.151985 → 0.154522s | 0.150626 → 0.001826s |
| original-0069-0072-right / begin | 0.782 → 0.628s | 0.152474 → 0.152604s | 0.152883 → 0.002005s |
| original-0069-0072-right / middle | 1.418 → 1.243s | 0.159054 → 0.155422s | 0.156639 → 0.002019s |
| original-0069-0072-right / dense-onset | 0.145 → 0.145s | 0.033117 → 0.033078s | 0.000000 → 0.000000s |
| original-0069-0072-right / dense-ink | 2.144 → 1.982s | 0.155716 → 0.156008s | 0.158591 → 0.002108s |
| original-0069-0072-right / terminal | 0.929 → 0.781s | 0.154353 → 0.157397s | 0.154742 → 0.002157s |

Validated second-pass reuse is about 0.67 ms/frame left and 0.69 ms/frame right, versus 50.6 / 51.9 ms/frame for ordinary photographic analysis. First-pass packing/hash cost in the left samples totals about 12 ms over 13 cacheable frames (~0.93 ms/frame); right samples are within timing variance. Complete sampled verifier wall time improves 12.1% / 11.8%. No second pass is attempted for first-pass error snapshots, exactly as before.

First-pass decode count is unchanged in every window. Dense-onset photographic failures remain errors: one measured frame left and zero right. The separate dense-ink windows measure all three frames. No coverage is inferred from these short windows.

Peak observed process RSS: approximately 310 MiB left and 333 MiB right. Representative cache peaks are only tens of KiB. Full-case cache residency/hit rate was not measured; byte/entry eviction may reduce the benefit on larger or incompressible inputs. The 96 MiB budget prevents retaining an uncompressed full case. We do not claim either 600s worker timeout is resolved. The optional bounded full-first-pass rerun was omitted: the existing profile already establishes first-pass costs, while these complete samples directly measure both packing overhead and second-pass savings.

Bookkeeping note: the left profile used the same compression/hash/reconstruction code with 256 bytes of per-entry bookkeeping padding; this was increased conservatively to 512 bytes before the right profile and final 52-test run. It changes only charged-byte accounting. All sampled windows fit either budget with identical hit sets and complete reports.

Artifacts: *.benchmark.json has every repeated timing and per-window median; *.report.json has the exact representative reports; *.pstats and *.profile.txt retain cProfile data; profile_cache.py reproduces the paired measurements. extra_symbol_pixels.before.py saves the refreshed original implementation; extra_symbol_pixels.after.py and test_photo_cache.py snapshot the final owned changes.
