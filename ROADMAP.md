# Piano Teacher — single development roadmap

**Authoritative plan • 2026-11-03 • MIDI input only**

This is the sole active phase plan. Other `docs/` files are technical
specifications, dated research evidence, verification protocols or archived
historical records. They do not define competing implementation phases.
The replaced October roadmap is archived at
[ROADMAP-2026-10-historical](docs/archive/development/ROADMAP-2026-10-historical.md).
[Documentation index](docs/README.md) explains which sources are authoritative.

## Product contract

One Godot 4.7 desktop application, one embedded CPython practice engine and
a typed in-memory GDExtension command queue. No network service, HTTP
adapter, Qt UI or compatibility facade. MIDI (.mid/.midi) is the **sole user
input**. Internally generated MusicXML is an engraving interchange, not
another input backend. The canonical MIDI source IDs, authored durations,
selected `ExerciseStage` and stage-specific tempo policy must agree across
native notation, Listen, visual transport, physical MIDI grading, feedback
and saved progress. The unchanged original MIDI is the final performance.

New installations select adaptive **Coda + Fukuda**. Existing explicit
preferences are respected. Lessons are meaningfully transformed from
source material, not editorial renamings of the same notes. No artificial
mastery from visual previews; three clean full-target performances required.

## Phase status and acceptance gates

| Phase | Scope | Status as of this document | Exit evidence |
|---|---|---|---|
| **0 — Foundation** | MIDI import, library, native startup, one process | Implemented; typed-bridge rebuild unverified | Cold Godot startup + open real MIDI |
| **1 — Practice engine** | Count-in, transport, recovery, retry, tempo ladder, progress | Implemented in software; physical behavior open | Real full session with no clock/stage divergence |
| **2 — Notation fidelity** | Source IDs, hands, ties, rests, tuplets, native ink and geometry | Broad test/evidence coverage; real-score visual gaps remain possible | Independent framebuffer/original-note parity on required corpus |
| **3 — Original Coda, MIDI-domain** | Four algorithms; pinned author-differential reproduction and source-safe desktop lesson path | **Algorithm scope completed 2026-11-02**; post-refactor retest pending | Existing 1,273-request differential and whole-piece/17-piece corpus, then current refactor regression |
| **4 — Fukuda + composed strategies** | MIDI-domain reductions, source-local feedback, recorded-MIDI alignment, generic whole-piece/adaptive composition | **Code integrated**; live combined-path acceptance and paper figure parity not established | Focused + corpus tests, source-effect comparison, physical original-to-remediation loop |
| **5 — One architecture, no compatibility layers** | Canonical engraving, native-only score assets, typed IPC, pluggable generator ownership; delete obsolete Qt/HTTP/facades | **Implementation consolidated**; native extension/packaging acceptance still open | Current focused/corpus gates, native extension smoke, source import graph and assembled-package audit |
| **6 — Real instrument + UX performance** | Beethoven opening, READY ink, scrolling vs BPM, Listen, error/retry, rests, reconnect, latency, longer pieces | **Open** | Signed real Godot + USB/Bluetooth MIDI evidence across full checklist |
| **7 — Teaching study + release** | Independent pedagogical effectiveness, clean-machine distribution, long-session reliability | **Not complete** | Prespecified learner comparison, reproducible package and unattended long-session acceptance |

Phase 3 deliberately covers the original *MIDI-domain* algorithms. Neither
importing MusicXML nor reproducing Fukuda's acoustic front-end is silently
added to the product scope. Original Fukuda paper thresholds and figure
reproduction remain research claims until independently checked.

## Immediate order of work

**P5 — Verify consolidation.** The obsolete Qt, HTTP and engraving facade
paths have been removed; source lessons now require explicit generator
registration and every feedback-capable generator consumes graded source-ID
evidence via `with_feedback`. The ID-only `with_mistakes` and implicit
legacy generator fallback have been deleted, along with stale LearningPlan
planning forwarders. A source import-graph audit runs in fast CI and the
standalone packager checks its assembled distribution for the canonical
modules, native assets and absence of the editor server. Latest fast
contracts passed at `1390f79`; native GDExtension startup and actual assembled
package verification require the corresponding acceptance logs.

Close P5 **only** when the current native build/typed `library.catalog` smoke,
fast/focused Coda+Fukuda suite, 17-piece corpus, Godot parser, and assembled
release import audit all pass. Keep hardware latency, actual Beethoven
framebuffer behavior and pedagogical studies under P6/P7.

**P6 — Prove real user behavior.** On the real Beethoven Pathétique II MIDI,
record READY ink, Step 1 provenance, effective tempo, Play/Listen/Retry,
post-rest handoff and stage changes. Run the
[physical keyboard acceptance checklist](docs/verification/coda-fukuda-physical-midi-checklist.md)
with both USB and Bluetooth where available. Fix source-specific failures
in the single clock/score pipeline, not by adding alternative paths.

**P7 — Validate pedagogy and ship.** Preregister a human within-piece or
counterbalanced study comparing meaningful learning outcomes across Coda,
Fukuda, combined and original-note practice. Keep generated sequences and
evidence reproducible; separately test clean-machine installation and offline
functioning.

## Outstanding critiques and resolution directions

| Critique | Required resolution or research |
|---|---|
| Verification may lag behind the latest commit | Require hash-specific fast, focused, corpus, native and assembled-bundle evidence before closing P5 |
| Sparse opening and dense note spacing may still be visually wrong | Native framebuffer captures before/after Play at fixed BPM; measure first attack x-position and pixels/beat against timing |
| Score preparation and large-piece transitions may stall | Profile cold/warm import, engraving, atlas and command queues per stage; require bounded P95 and no duplicate compilation |
| Stage choice might be repetitive or musically ineffective | Expose actual removed/retimed/source-preserved notes; inspect stages on a varied corpus, then run P7 study |
| Audio, visual scroll and MIDI grading could drift under load | Record common source-ID/beat traces, audio position and note-on timestamps; compare under pause/retry/rest/tempo changes |
| Physical latency/handshake and reconnect remain unproven | Measure timestamp and calibration error with USB and Bluetooth on target device; fault-inject disconnect and recovery |
| Full packaging, migration and runtime fault handling not accepted | Isolated clean-home install, simulated corrupted cache/old course, crash/reopen, offline start and asset-bundle checks |
| Application roots may still contain avoidable coordination | Audit `server.py`/`main.gd` for engine-owning transitions and forwarding accessors; move complete responsibilities to narrowly typed owners and delete old paths, not aliases |
| Removed strategies can survive in historical test fixtures or saved preferences | Prevent runtime registration, reject obsolete selection, migrate unknown saved choice to the default hybrid; retain historical fixtures only as test data |
| Original Fukuda numeric/figure parity is not independently established | Paper-to-code threshold/figure audit; explicitly report MIDI-domain substitutions instead of claiming audio-domain replication |

## Current blockers

| Blocker | Unblock |
|---|---|
| **Native extension and assembled package require current acceptance** | Fast Python and import-graph audit are green; verify the latest [native build](https://github.com/tpepels/piano_teacher/actions/workflows/inprocess-native-build.yml), embedded typed-op smoke and complete staged-package audit. Do not substitute source inspection for those gates |
| **Native C++/Godot typed-op protocol changed** | Rebuild `scripts/build-inprocess.sh`; run `scripts/verify-native-bridge.sh` and Godot syntax/smoke |
| **Real Beethoven and physical instrument behavior unobserved** | Reopen Beethoven in combined strategy; capture diagnostic log, framebuffer and keyboard assessment trace |
| **Research comparison and release evidence missing** | P7 pilot and clean-machine packaging gate, after P6 |

## Commands and completion rules

```bash
git pull --ff-only
bash scripts/build-inprocess.sh
bash scripts/verify-native-bridge.sh
bash scripts/ci-smoke.sh
bash scripts/check-godot-syntax.sh
bash scripts/verify-hybrid-workflow.sh --focused
# Run separately when the focused gates are green:
bash scripts/verify-hybrid-workflow.sh --corpus
```

Do not run or wait for long CI during interactive development. A focused
test suite proves only its named contracts; software source inspection
cannot certify audio/visual correctness or a physical MIDI device.
**A phase closes only after every stated gate has evidence.** Archive
outdated planning notes; update **this file** when statuses change.
