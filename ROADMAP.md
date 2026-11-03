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
| **0 — Foundation** | MIDI import, library, native startup, one process | **Software acceptance complete**: cold production UI, saved real MIDI, native notation and Play/Pause/Resume passed in CI at `aecbb09` | [Production scene and embedded runtime evidence](https://github.com/tpepels/piano_teacher/actions/runs/41663899894) |
| **1 — Practice engine** | Count-in, transport, recovery, retry, tempo ladder, progress | Implemented in software; physical behavior open | Real full session with no clock/stage divergence |
| **2 — Notation fidelity** | Source IDs, hands, ties, rests, tuplets, native ink and geometry | Broad test/evidence coverage; real-score visual gaps remain possible | Independent framebuffer/original-note parity on required corpus |
| **3 — Original Coda, MIDI-domain** | Four algorithms; pinned author-differential reproduction and source-safe desktop lesson path | **Algorithm scope complete; post-consolidation Coda tests green** | Existing 1,273-request differential and whole-piece/17-piece corpus, then current refactor regression |
| **4 — Fukuda + composed strategies** | MIDI-domain reductions, source-local feedback, recorded-MIDI alignment, generic whole-piece/adaptive composition | **Code integrated**; live combined-path acceptance and paper figure parity not established | Focused + corpus tests, source-effect comparison, physical original-to-remediation loop |
| **5 — One architecture, no compatibility layers** | Canonical engraving, native-only score assets, typed IPC, pluggable generator ownership; delete obsolete Qt/HTTP/facades | **COMPLETE — 2026-11-03** | All required fast/focused/corpus, native load, Godot parser, source graph and staged-package checks passed; see evidence below |
| **6 — Real instrument + UX performance** | Beethoven opening, READY ink, scrolling vs BPM, Listen, error/retry, rests, reconnect, latency, longer pieces | **Open** | Signed real Godot + USB/Bluetooth MIDI evidence across full checklist |
| **7 — Teaching study + release** | Independent pedagogical effectiveness, clean-machine distribution, long-session reliability | **Not complete** | Prespecified learner comparison, reproducible package and unattended long-session acceptance |

Phase 3 deliberately covers the original *MIDI-domain* algorithms. Neither
importing MusicXML nor reproducing Fukuda's acoustic front-end is silently
added to the product scope. Original Fukuda paper thresholds and figure
reproduction remain research claims until independently checked.

## Completed Phase 5 — verified implementation

**P5 — Architecture consolidation.** Implemented and accepted on 2026-11-03.
The product uses one MIDI-only, native Godot/embedded-CPython runtime, one typed
in-memory operation queue, and explicitly registered independent whole-piece
lesson generators. Unregistered generators fail rather than selecting a
heuristic fallback. `LegacyStrategy`, `HeuristicLessonGenerator`,
`with_mistakes`, unversioned lesson reconstruction, stale LearningPlan
forwarders and obsolete Qt/HTTP/page-image paths are removed. Graded
source-ID evidence enters every adaptive generator through `with_feedback`.
Saved strategy/version stage identities isolate BPM and mastery; unversioned
records remain in storage but cannot award credit.

**Recorded acceptance evidence:**

| Gate | Reproducible result |
|---|---|
| Fast architecture, import graph and Python state contracts | [403 passed, 6 skipped at `f9ae15b`](https://github.com/tpepels/piano_teacher/actions/runs/41637045068) |
| Fukuda source MIDI contracts | [43 passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328757) |
| Composed Coda+Fukuda and course persistence | [98 passed, then 17-piece real MIDI corpus passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328743) |
| Independent Coda research and full MIDI repertoire | [235 passed / 1 skipped, 51 passed; stage audit passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328719) |
| Godot GDScript parser | [Green at `e47ec35`](https://github.com/tpepels/piano_teacher/actions/runs/41631177422); commit comparison through `f9ae15b` contains no `godot/` changes |
| Compiled native CPython/Godot bridge | [Build passed at `b1aa9ae`](https://github.com/tpepels/piano_teacher/actions/runs/41636328908) |
| Embedded Godot typed `library.catalog` and assembled standalone runtime | [Both passed at `f9ae15b`](https://github.com/tpepels/piano_teacher/actions/runs/41637102956), including `PIANO_NATIVE_CLASS_OK`, `PIANO_NATIVE_LIBRARY_OK` and `PHASE5_ARCHITECTURE_AUDIT_OK` |

The native smoke uses the matching built artifact and confirms one registered
`PianoNative` class with a working embedded Python typed operation. The staged
package audit checks the actual copied runtime, relative import graph,
required binaries and removal of editor-only runtime code. As intended, it
does not certify a clean-machine launch of the final compressed release; that
is Phase 7. Hardware latency, visual note alignment, physical grading and
pedagogical effectiveness belong to Phases 6 and 7, not Phase 5.

## Immediate order of work

**P6 — Prove real user behavior.** The
[embedded real-MIDI workflow](https://github.com/tpepels/piano_teacher/actions/runs/41660803843)
passed at `213cc255`: library catalog, opening an actual two-hand MIDI,
Verovio note anchors, source-semantic score, score-ready acknowledgement,
Play/Pause/Resume and the staged package asset audit. Native CI is now pinned
to the exact build revision and reruns on changes to the score pipeline.
This establishes embedded software integration, not Godot framebuffer
correctness or physical MIDI keyboard behavior.

**P6 — Production UI gate.** The real-scene
[acceptance run](https://github.com/tpepels/piano_teacher/actions/runs/41663899894)
passed at `aecbb09`. `main.tscn` starts the embedded Python worker, reopens
the saved MIDI, compiles retained notation, dismisses the loading overlay
and starts, pauses and resumes the same transport. Commit `4feb8ac`
adds stronger checks for actual viewport-visible noteheads, stationary
pause positions and scroll displacement at the displayed BPM. The
stronger frame-level checks passed in the later
[real-score native runtime gate](https://github.com/tpepels/piano_teacher/actions/runs/41678370190)
at `d92d9e6`. Neither check substitutes for an independent pixel proof or
physical MIDI test.

**P6 — Real-source written rest.** The
[bounded real-MIDI regression](https://github.com/tpepels/piano_teacher/actions/runs/41665774242)
passed at `cc7efe9`, including the composed-generator contracts and the
17-piece MIDI corpus. Its newly generated three-measure, two-hand source
contains a full silent measure, and the unchanged original performance
continues along the same visual and grading beat axis across the silence.
This establishes software clock continuity, not the target-device frame
cadence or MIDI input response.

**P6 — Actual repertoire and session.** A bounded native integration
journey uses the repository's genuine `Moonlight_Sonata_I.midi` and drives
the production scene through ready notation, Play/Pause/Resume, a full
backward/retry preparation measure, Listen/return, selection of step 2,
manual -5 BPM and closing/reopening the saved lesson. Both score revisions
and visible native noteheads are checked at every publication boundary.
The native workflow
[passed at `d92d9e6`](https://github.com/tpepels/piano_teacher/actions/runs/41678370190),
including decoded Listen WAV playback and the staged runtime audit. Sound-card
output and physical MIDI grading still require real hardware.

**P6 — Real-score viewport coverage.** Two further production-scene
cases now select the real `Peace_Piece_-_Bill_Evans_(Piano_Solo).midi` and
`Chopin_-_Nocturne_Op_9_No_2_(E_Flat_Major).midi` through the persisted
library. The full file SHA-256 must match the loaded backend fingerprint.
Each case verifies retained visible noteheads at READY, at least two beats
of lookahead, a stationary Pause and source-clock-aligned motion on Resume.
Both
[passed at `d92d9e6`](https://github.com/tpepels/piano_teacher/actions/runs/41678370190),
including SHA-256 source identity, actual retained notehead presence, Pause and
BPM-consistent Resume. Independent framebuffer pixel verification remains
separate from these headless compositing checks.

**P6 — Graded software-input callback.** The
[bounded Coda + Fukuda test and 17-score corpus](https://github.com/tpepels/piano_teacher/actions/runs/41676220356)
passed at `23ca2ca`. This additional real MIDI fixture delivers original
note-on/off messages through `PracticeEngine._receive`, including a whole
silent bar; one clean whole-piece performance and a second take with a
deliberate wrong RH pitch produce correctly source-bound performance reviews
without modifying the source MIDI. The
[backend-calibrated click and display-clock regression](https://github.com/tpepels/piano_teacher/actions/runs/41676891067)
passed at `c2a7ab7`, including state-response delay injection. Neither is
a measurement of physical USB/Bluetooth input latency.

**P6 — Independent real-score pixel proof.** The targeted
`phase6-real-score-framebuffer.yml` gate runs on matching Godot 4.7.2,
generates source-registered production PNGs for Peace Piece measures 1–2,
Chopin Nocturne measures 5–6 and Moonlight Sonata measures 1–2, verifies
real written rest/notehead ink, and demands that deliberate framebuffer
damage is rejected by the same pixel oracle. Missing/mismatched source
symbols or output frames fail the build; captured evidence is uploaded with
the exact source SHA. This is a bounded sample, **not** full-score coverage.
Its first current-revision run must pass before this gate can be accepted.
The fixture assembler now uses the single canonical native layout path,
with no obsolete `native_notes` switch.

**P6 — Score preparation.** Score loading now supersedes obsolete
layout/model requests without waiting for old deadlines, bounds semantic
retries, and surfaces actionable failure if retained notation never completes.
The Godot `score_asset_lifecycle` regression runs as part of the bounded
syntax/behavior CI gate.
The original five native score-session contracts now enforce the same
bounded retry, revision supersession, failure and publication semantics. Loading phase, Browse and delayed Retry now come
directly from this session into the practice UI. Retry can also supersede a
still-pending layout request. Physical screen/instrument evidence remains open.

On the real Beethoven Pathétique II MIDI,
record READY ink, Step 1 provenance, effective tempo, Play/Listen/Retry,
post-rest handoff and stage changes. Run the
[physical keyboard acceptance checklist](docs/verification/coda-fukuda-physical-midi-checklist.md)
with both USB and Bluetooth where available. Fix source-specific failures
in the single clock/score pipeline, not by adding alternative paths.

**Release package hygiene.** Standalone staging now explicitly excludes
Godot test fixtures, smoke scripts, editor-only .uid files and MCP plugins.
The package audit rejects these sources if a future change includes them;
clean-machine installed execution remains a Phase 7 gate.

**P7 — Validate pedagogy and ship.** Preregister a human within-piece or
counterbalanced study comparing meaningful learning outcomes across Coda,
Fukuda, combined and original-note practice. Keep generated sequences and
evidence reproducible; separately test clean-machine installation and offline
functioning.

## Outstanding critiques and resolution directions

| Critique | Required resolution or research |
|---|---|
| Later production commits require fresh acceptance evidence | Re-run the affected fast/focused, corpus and native gates against the changed revision; do not claim hardware or release validation from source checks |
| Sparse opening and dense note spacing may still be visually wrong | Native framebuffer captures before/after Play at fixed BPM; measure first attack x-position and pixels/beat against timing |
| Score preparation and large-piece transitions may stall | Score projection is now reused per selected revision across geometry + semantic commands; profile cold/warm import, engraving, atlas and command queues per stage; require bounded P95 |
| Stage choice might be repetitive or musically ineffective | Expose actual removed/retimed/source-preserved notes; inspect stages on a varied corpus, then run P7 study |
| Audio, visual scroll and MIDI grading could drift under load | Record common source-ID/beat traces, audio position and note-on timestamps; compare under pause/retry/rest/tempo changes |
| Calibration pulse drift under delayed score/device snapshots | Calibration beat now uses the same backend monotonic epoch as MIDI events; a Godot regression injects stale snapshots and verifies the visible downbeat/click. This is a software correction only; hardware audio/USB/Bluetooth offsets still require measurement |
| Physical latency/handshake and reconnect remain unproven | Measure timestamp and calibration error with USB and Bluetooth on target device; fault-inject disconnect and recovery |
| Full packaging, migration and runtime fault handling not accepted | Isolated clean-home install, simulated corrupted cache/old course, crash/reopen, offline start and asset-bundle checks |
| Application roots may still contain avoidable coordination | Audit `server.py`/`main.gd` for engine-owning transitions and forwarding accessors; move complete responsibilities to narrowly typed owners and delete old paths, not aliases |
| Removed strategies can survive in historical test fixtures or saved preferences | Prevent runtime registration, reject obsolete selection, migrate unknown saved choice to the default hybrid; retain historical fixtures only as test data |
| Original Fukuda numeric/figure parity is not independently established | Paper-to-code threshold/figure audit; explicitly report MIDI-domain substitutions instead of claiming audio-domain replication |

## Current blockers

| Blocker | Unblock |
|---|---|
| **Real Beethoven and physical instrument behavior unobserved** | Reopen Beethoven in combined strategy; capture diagnostic log, framebuffer and keyboard assessment trace |
| **Research comparison and release evidence missing** | P7 pilot and clean-machine packaging gate, after P6 |

## Commands and completion rules

```bash
git pull --ff-only
# Re-run on any new production change:
bash scripts/ci-smoke.sh
bash scripts/check-godot-syntax.sh
bash scripts/verify-hybrid-workflow.sh --focused
bash scripts/verify-hybrid-workflow.sh --corpus
# Rebuild the native binary when C++/bridge/runtime inputs change:
bash scripts/build-inprocess.sh
bash scripts/verify-native-bridge.sh
# Staged standalone audit is performed by the native runtime smoke CI.
```

Do not run or wait for long CI during interactive development. A focused
test suite proves only its named contracts; software source inspection
cannot certify audio/visual correctness or a physical MIDI device.
**A phase closes only after every stated gate has evidence.** Archive
outdated planning notes; update **this file** when statuses change.
