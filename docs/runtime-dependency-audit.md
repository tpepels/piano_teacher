# Runtime dependency and architectural simplification audit

**Baseline:** [ae95edd739003ed5908546b2e3f19ecaa583f347](https://github.com/tpepels/piano_teacher/tree/ae95edd739003ed5908546b2e3f19ecaa583f347)  
**Audit date:** 2026-11-28  
**Status:** static source inspection and review of existing recorded benchmarks; no remediation or new runtime measurements performed by this audit.

## 1. Purpose and constraints

Identify external runtimes, redundant transformations, obsolete interfaces, unnecessary runtime assets and duplicated responsibilities. A dependency must have an explicit owner, a current product requirement and a demonstrated reason to remain. Do not remove a dependency just because another language/library could perform a similar task.

The canonical product remains the offline Godot desktop application with an embedded Python musical engine, one authoritative musical timeline, one native score presentation and a supervised notation process. Retain source-note identity, the forward-only visual transport, admission and cancellation guarantees, authored music, fingering corrections, saved progress and the learner-visible behaviour in [practice-flow.md](practice-flow.md). Historical storage readers are not automatically dead code. Keep development and diagnostic tools out of the release, without removing useful development coverage.

This audit complements [architecture.md](architecture.md), [asset-worker.md](asset-worker.md), [development.md](development.md) and [reference.md](reference.md). ROADMAP.md is still the authoritative implementation/phase record. An audit recommendation is not a completed phase or authorization to alter teaching behaviour.

### Evidence and decision method

- **Confirmed:** directly observed source/configuration and call path.
- **Candidate:** plausible simplification, requiring complete caller/feature or dependency closure before deletion.
- **Measured:** numerical observation recorded in asset-worker.md; workload and limitations apply. No new benchmark results are claimed here.
- **Keep:** currently justified dependency or boundary; review only with a viable equivalent and measured benefit.

For each candidate, record the production entry point and transitive call path, feature and owner, direct and transitive packages/assets, cold/warm runtime cost, package size, replacement options, compatibility obligations and verification evidence. Search dynamic imports, string-based command dispatch, generated resources, subprocess entry points, native registrations and test/release scripts. Distinguish production, optional runtime, build, test, research and historical-data paths. A grep hit or absence alone cannot establish dead code.

## 2. Current runtime inventory

| Dependency or runtime | Current owner / reason | Classification | Audit disposition |
| --- | --- | --- | --- |
| Godot 4.7 / GDScript | Desktop, presentation, GPU, input, audio playback | Required | Keep; no second UI or renderer |
| Native C++ GDExtension / godot-cpp / libpython | Embedded engine, command/timing and asset lanes | Required; toolchain build-only | Keep; audit work on each lane |
| CPython | Musical domain and local worker processes | Required | Keep one compatible bundled Python distribution |
| mido / python-rtmidi | MIDI import, device access | Required | Keep distinct parsing and device responsibilities |
| music21 | MusicXML parsing, repeat handling, MIDI conversion | Required for current XML import | A1: evaluate direct canonical import; remove only after functional replacement |
| Verovio and its music fonts | Authentic engraving, glyphs and score geometry | Required | Keep; not a duplicate renderer of the interactive scene |
| CairoSVG / Cairo, Pillow | Rasterizing and manipulating genuine engraving fragments | Required by current asset pipeline | A4: investigate redundant transformations and alternatives |
| Lumikey model weights 0.3.0 | Original left- and right-hand ONNX weights | Bundled fingering data | A2: exact weights verified before inference |
| Python ONNX Runtime 1.30.0 | CPU inference in an isolated Python process | Required for automatic fingering | A2: replaces the Node binding |
| FluidSynth / SF2 SoundFont | Optional sampled Listen audio via ctypes | Optional runtime | A5: choose one supported audio synthesis path |
| Python basic synthesizer | Listen when no SoundFont exists | Current fallback runtime | A5: retire only after replacement works offline everywhere supported |
| SQLite / standard-library persistence | Local learner progress, evidence and caches | Required | Keep; preserve old data and migration semantics |
| NumPy | Fingering input tensors via Python ONNX Runtime, plus research and curriculum | Runtime dependency | A6: identify other production imports and required extras |
| pytest, coverage, PyYAML, Ruff, gdtoolkit, ShellCheck, actionlint, SCons, compiler | Tests, quality, native build | Development/build | Exclude from release unless independently needed at runtime |
| Godot MCP toolkit, editor cache, smoke journeys | Development/editor/verification | Development/test | A8: exclude from package; current project has no active MCP autoload/plugin entry |
| Linux device/graphics/audio drivers and shared libraries | Native platform integration | Host/runtime | Document actual minimum system requirements; audit ELF/library closure |

Evidence: [pyproject.toml](../pyproject.toml), [package-inprocess.sh](../scripts/package-inprocess.sh), [CI](../.github/workflows/ci.yml), [sample_piano.py](../piano_teacher/sample_piano.py). This source-level inventory leaves exhaustive dependency and binary accounting to A8.

## 3. Findings

### A1 — Lossy MusicXML → MIDI → reconstructed MusicXML

**Priority:** high (musical fidelity and dependency complexity). **Status:** confirmed pipeline; replacement feasibility unverified.

Evidence:
- [importing/pieces.py](../piano_teacher/importing/pieces.py), load_musicxml: parses the captured bytes via music21, removes grace notes, converts using streamToMidiFile, calls load_midi and recovers authored fingering by rounded onset/pitch.
- Malformed repeats are stripped and the score converted again. Written fingers are matched without a staff/voice discriminator in the key; duplicate simultaneous pitches and expanded repeat occurrences need investigation.
- [learning.py](../piano_teacher/learning.py), LearningPlan requires source_format == "midi"; [preprocessing_cache.py](../piano_teacher/preprocessing_cache.py) restores that format. Thus the imported MusicXML travels as a MIDI-shaped source.
- [application/score_artifacts.py](../piano_teacher/application/score_artifacts.py), notation, calls build_lesson_score, infers clefs and produces new MusicXML for Verovio; [notation/lesson.py](../piano_teacher/notation/lesson.py) and [notation/model.py](../piano_teacher/notation/model.py) reconstruct the display.

**Consequence:** MIDI has no general representation for original voices, spelling, written ties/slurs, grace-note notation, tuplet groupings, articulations and other score markings. The pipeline provably drops grace notes; the precise loss and impact for other features must be established fixture by fixture. Reconstructed score data should not be mistaken for preserved authored notation. This may explain fidelity problems but is not proof of any specific observed bug.

**Target:** import MIDI and MusicXML into one canonical source representation directly, with authored notation and performed attacks/releases linked through stable source identities. Model written time, repeats and performed time explicitly where they differ. Separate origin format from the normalized musical model. Preserve real authored context when deriving excerpts/remediation and send generated notation only where required. Reuse Music21 if it remains the best verified parser; eliminating it is a contingent benefit, not a prerequisite. Do not write a second engraving engine.

**Verification/removal gate:** compare MIDI equivalence and MusicXML fidelity on real single/multi-staff scores, compressed MXL, pickups, meter/key/clef changes, ties across bars, tuplets, grace notes, same-pitch voices, transposition, repeats/voltas and malformed input. Check attack identity, fingering associations, expected/graded durations, held endings, score layout and navigation. Define explicit handling for unsupported notation; no silent lossy fallback. Migrate or invalidate versioned import caches without losing learner progress or overrides. Prove import closure, performance and packaged offline behaviour before removing Music21.

### A2 — Migrate fingering inference to Python

**Status:** implemented. [ROADMAP](../ROADMAP.md#python-onnx-fingering-a2-2026-11-28)
records the software acceptance and performance comparison.

The [provider](../piano_teacher/fingering/lumikey.py) runs whole-piece inference
in a bounded, cancellable Python subprocess. It uses the original
[tokenization and sequential model history](../piano_teacher/fingering/inference.py)
with the ported [chord and overlap constraints](../piano_teacher/fingering/overlap.py).
The same model files, SHA-256 hashes and license provenance are recorded in
[third-party notices](../piano_teacher/fingering/THIRD_PARTY_NOTICES.md).
Exact JavaScript comparison covered repertoire, authored and manual overrides,
same-pitch voices, shared thumbs, sustained notes, overlapping constraints and
unplayable chords. The new provider identity regenerates prediction caches
while reading corrections from the same override file.

### A3 — Source preparation still blocks the command lane

**Priority:** high (responsiveness). **Status:** confirmed; current timing lane is already independent in the documented native architecture.

Evidence: [application/source_preparation_session.py](../piano_teacher/application/source_preparation_session.py), prepare, reads/imports a source, creates a ThreadPoolExecutor for fingering, constructs LearningPlan, restores progress under the state lock and waits at predicted.result(). Corrections also wait for inference. [application/source_workflows.py](../piano_teacher/application/source_workflows.py) and [server.py](../piano_teacher/server.py) own source-bound preparation/installation. [native/src/piano_native.cpp](../native/src/piano_native.cpp), worker_loop, executes commands serially; [asset-worker.md](asset-worker.md) documents the independent timing driver.

**Consequence:** expensive loading/correction can delay later commands, even though MIDI and timing can continue. It is inaccurate to claim that the current migration necessarily stalls all engine ticks.

**Target:** move expensive import/curriculum and inference work out of synchronous command dispatch, with bounded source preparation, explicit latest-request ownership, stale-result rejection and atomic source installation. Maintain one selected source and one authoritative lesson/progress owner. Existing source_mutation and settlement guarantees must not be bypassed. Decide whether a dedicated worker or existing isolated inference worker is suitable based on workload; do not queue this behind unrelated engraving by default.

**Verification gate:** record command latency during cold imports and corrections, Stop/Pause, source replacement, failed import, repeated navigation, shutdown, stale inference and reopening with saved progress. Confirm no old result installs into the new piece or overwrites durable edits, no half-installed source, and no new musical timing regression. Avoid speculative prefetch or extra orchestration layers without evidence.

### A4 — Rendering transformations and frame tails

**Priority:** medium-high (performance). **Status:** confirmed multi-stage pipeline; redundant work is a candidate, not yet established.

Evidence: [engraving/engraving.py](../piano_teacher/engraving/engraving.py) produces Verovio SVG and layout; [source_svg.py](../piano_teacher/source_svg.py) parses SVG geometry; [notation/assets/vector_art.py](../piano_teacher/notation/assets/vector_art.py) uses Cairo recording/image surfaces, Pillow and PNG/base64 for certain fragments. [application/score_artifacts.py](../piano_teacher/application/score_artifacts.py) stores engraving pages/layout and assembles model and assets. [godot/score_preparation_job.gd](../godot/score_preparation_job.gd) and [godot/score_asset_session.gd](../godot/score_asset_session.gd) decode, prepare, fit, upload and install. The retained renderer is the sole interactive notation surface.

**Target:** inventory every geometry/image transform and whether it depends on source, stage, viewport, density, status or annotation. Measure repeated SVG parsing, rasterization, PNG/base64 encoding/decoding, atlas copies, texture uploads, retained drawing, viewport refits and cache hits. Eliminate confirmed duplicate work, maintain one correct representation per boundary and reuse immutable assets where appropriate. Preserve genuine Verovio ink, stable glyph origins, beams, ties, tuplets, slurs, barlines, context, feedback masks and native visual readiness.

Keep Verovio. Godot's SVG rasterizer is not automatically equivalent to Cairo for every SVG fragment. Do not replace libraries or the IPC format until the measured bottleneck and visual equivalence justify the change.

**Verification gate:** record CPU stages, frame p50/p95/p99/max, missed frame deadlines, texture counts, peak/combined memory and warm/cold sizes on the same pieces/display/host. Include repeated lesson changes, resize, DPI, scale changes, pause/resume and score feedback. Physical visual checks supplement software tests.

### A5 — Two piano synthesis paths and optional host dependency

**Priority:** medium (consistency and maintenance). **Status:** confirmed dual implementation.

Evidence: [demo.py](../piano_teacher/demo.py), DemoAudioCache.render, chooses its Python PCM synthesizer when no local SoundFont is present. [sample_piano.py](../piano_teacher/sample_piano.py) locates the user's SF2 bank and loads host libfluidsynth via ctypes. [application/listen_session.py](../piano_teacher/application/listen_session.py) has one audio render thread, one replaceable pending request and chunk cancellation. An indivisible SoundFont load and Python waveform generation remain potential latency sources. This is not the older unbounded multi-thread implementation.

**Target:** choose one supported high-quality offline synthesis implementation and appropriately licensed instrument assets, with explicit native library packaging/host requirements. Evaluate the cost of bundled SoundFont size and library dependencies against sound quality. Keep one authoritative musical tempo/note timeline and generation identity. Consider a dedicated isolated audio worker only if useful for cancellation or GIL/command-lane latency. Do not introduce real-time playback drift or a second scheduler merely to simplify the audio path.

**Verification gate:** identical notes/timing through tempo maps, held releases, Listen count-in/synchronization, Pause/Resume, Listen again, cancellation and shutdown. Measure render startup, WAV size, decode and main-thread cost. Verify sound quality and latency on a physical piano/audio device and a clean offline installation. Remove the basic synthesizer only when a reliable replacement is distributed; missing audio must be explicit, not silent.

### A6 — Research code mixed with production curriculum

**Priority:** medium (maintainability and dependencies). **Status:** confirmed production reachability of several research modules; dead-code candidates require a full trace.

Evidence: [lesson_generators.py](../piano_teacher/lesson_generators.py) uses CodaAid and FukudaAid for Free remediation. [application/coda_midi_curriculum.py](../piano_teacher/application/coda_midi_curriculum.py) imports coda_midi_grid, coda_midi_sparse, coda_reference_exercises and coda_author_catalog from research; Fukuda uses [fukuda_midi.py](../piano_teacher/fukuda_midi.py). There are nine Coda-related research modules plus __init__.py at the baseline.

**Target:** classify each algorithm, helper and dataset by actual production reachability and supported remediation requirement. Move the production reduction logic into the domain owning it, preserving attribution/fidelity limits. Keep genuinely experimental reference work outside runtime packaging and remove proven unused paths. Do not rename or move files merely to meet a file-count metric. Consolidate duplicated logic only where semantics are equivalent.

**Verification gate:** exact remediation eligibility, simplified note/rhythm mapping, original-note identity, manual correction projection, return to the original passage and all existing Practice Flow behaviour. Audit NumPy and other transitive imports on the actual production path. Do not drop Coda/Fukuda features without explicit product approval.

### A7 — Alternative score-generation operations

**Priority:** medium-low (interface and state-space reduction). **Status:** confirmed multiple operations; redundancy is a candidate.

Evidence: [application/score_ipc.py](../piano_teacher/application/score_ipc.py) OPERATIONS includes score.bundle, score.semantic, score.native_layout. [application/score_artifacts.py](../piano_teacher/application/score_artifacts.py) dispatches each. [godot/score_asset_session.gd](../godot/score_asset_session.gd) requests score.bundle, containing both model and layout. [inprocess.py](../piano_teacher/inprocess.py) and native asset classification expose the operations.

**Target:** trace all callers, including smoke scripts, diagnostics, dynamic commands and native tests. If the latter two are test-only or obsolete, migrate tests to the actual production bundle contract and remove unused operations end-to-end (router, mailbox classification, protocol, worker, docs). A test's use of a dead production interface alone does not justify retaining it. Preserve any independently required operation only with a documented consumer and rationale.

**Verification gate:** one authoritative source-bound bundle, exact graded IDs, rejection of stale/partial/duplicate/wrong-revision results, renderer readiness, cancellation and worker crash recovery. No fallback to parent-side engraving or second publication path.

### A8 — Broad release copying and incomplete runtime manifest

**Priority:** medium-low, revisit after A1–A7. **Status:** confirmed exclusion-based packaging.

Evidence: [scripts/package-inprocess.sh](../scripts/package-inprocess.sh) stages Godot, the application, the exact fingering files and a Python library subtree. It removes the MCP toolkit, four named smoke fixtures, caches and selected development files. [scripts/verify-package-contents.py](../scripts/verify-package-contents.py) audits imports, models, license notices and selected exclusions. The tracked godot/tests/test_transient_pitch_spelling.gd remains a packaging candidate. The package import smoke includes Python ONNX Runtime. MusicXML import and sampled-piano availability need their own packaged verification.

**Target:** use a reviewed allowlist/runtime manifest or an equivalent deterministic export process; include transitive Python/native/shared-library dependencies, required assets, exact model/font provenance and licenses. Separate application and developer artifacts, preserve standalone launch, explicitly validate actual imported Godot assets and dynamic loads. Generate a dependency/version/size report from the assembled artifact and check for development-only packages, binaries, source trees and caches. Keep migrations and real runtime worker entry points.

**Verification gate:** extend the relocated package run to Listen audio, score worker restart, saved progress and device discovery. Inspect package contents and native linkage, compare archive and unpacked sizes, and test real supported host drivers separately.

## 4. Related checks, not new rewrite mandates

- **Worker identity and full-source transfer:** [application/score_selection.py](../piano_teacher/application/score_selection.py) serializes original notes, selected phrase and fingering document; [application/score_read_services.py](../piano_teacher/application/score_read_services.py) caches encoded source and validates source-bound requests. Review selection changes and same-revision annotation corrections for stale admission and needless retransmission. Keep the existing bounded IPC and independent subprocess; do not introduce shared memory or compression without measured benefit.
- **Persistence and state duplication:** review remaining legacy-named variant fields and historical schema readers only against real persistence compatibility. Do not remove durable settlement/receipt guards or change progress schema casually. [architecture.md](architecture.md#remaining-complexity-and-why-it-stays) documents why several apparently redundant structures remain.
- **Source reachability:** extend/use [scripts/audit-a0-reachability.py](../scripts/audit-a0-reachability.py) with explicit entry-point ownership and dynamic references; its static results are candidates, not deletion authorization. Verify production root versus harness roots and actual runtime import closure.
- **Documentation:** the README's former description of everything running in one desktop process is obsolete after the score-worker migration. Keep runtime/feature claims, dependency list and distribution instructions synchronized.

## 5. Baseline and benchmark method

The existing [score-worker report](asset-worker.md#post-migration-audit-measurements) records these paired observations (threaded baseline 7459582a vs audited subprocess, same host/CPU affinity, synthetic MIDI driver boundary, software OpenGL):

| Measurement | Threaded baseline | Audited subprocess |
| --- | ---: | ---: |
| Cold whole-piece bundle | 57.16 s | 13.84 s |
| MIDI callback p95 / max | 15.96 / 33.72 ms | 0.30 / 0.47 ms |
| Engine tick p95 / max | 26.13 / 88.24 ms | 0.27 / 0.29 ms |
| Combined sampled RSS | 149.1 MiB | 181.1 MiB |
| Opening-window frame p95 / max | 16.29 / 174.33 ms | 16.91 / 158.49 ms |
| Lesson selection to retained notation | 502.14 ms | 510.26 ms |

A warm exchange used 576 KB input and 3.66 MB output; the report estimates about 5.43 ms outside the worker in the measured exchange. The report's follow-up also shows large opening frame spikes and overlapping lesson-transition durations. Keep these as context, not new measurements or proof of physical acceptance. RSS sums double-count shared pages. The report's earlier opening run measured import 23 ms, course/progress 120 ms and parallel fingering 424 ms. Do not treat that single run as a universal bottleneck ranking.

Before each change, use the same checkout/workload on the same hardware, CPU affinity, renderer, runtime versions, source corpus, warm/cold cache setup and input stream. Record repeated samples and distributions (not a single best run), process CPU/RSS/PSS where available, package size, source-load/command latency, MIDI arrival-to-admission and tick timing, child generation/IPC, frame tails, texture preparation/upload and audio latency as relevant. Include typical short windows, large whole pieces and difficult notation. Capture current instrumentation limitations, physical-device/display latency separately, and any sample variance. Set acceptance thresholds from the measured baseline and product requirements before optimizing. Avoid claiming reductions in dependency count imply performance gains.

## 6. Proposed remediation order and closure criteria

| Order | Work | Dependency / decision |
| --- | --- | --- |
| 0 | Inventory and benchmark | Complete dependency/caller/asset closure and record baseline; no speculative deletion |
| 1 | A1 MusicXML fidelity design and direct import | Agree written/performed representation and compatibility first; do not remove features |
| 2 | A2 Python fingering inference | Implemented with exact model and prediction parity |
| 3 | A3 asynchronous source preparation | Build on stable source/fingering contracts; protect current cancellation and durable settlement |
| 4 | A4 render pipeline simplification | Profile first; target actual frame/CPU/memory costs, not number of libraries |
| 5 | A5 audio consolidation | Select soundfont/license/host policy and validate consistent Listen behaviour |
| 6 | A6 production research closure | Preserve remediation functionality and fidelity limitations |
| 7 | A7 remove proven unused score operations | Can be an early low-risk cleanup once caller audit is complete |
| 8 | A8 release manifest and dependency enforcement | Establish inventory early, finalize after runtime changes; enforce only justified runtime assets |

This is an audit priority list, not a requirement to implement phases in strict serial order. Each approved implementation phase must cover its complete agreed scope, remove superseded implementations, maintain coherent documentation, update ROADMAP.md and record unresolved acceptance explicitly. Do not combine unrelated rewrites or add layers merely to satisfy the audit.

For each phase:
1. Record the before/after call and dependency graph, affected features, data compatibility and chosen design.
2. Verify behavior using the existing real production and synthetic-MIDI journeys; follow repository test policy and owner-approved regression coverage. For replacements, use a temporary comparison oracle as needed and remove it from the production package. Do not preserve obsolete behavior solely for a test.
3. Run relevant existing software checks, quality gate, full configured CI and clean standalone-package verification. Resolve regressions rather than weaken assertions.
4. Record measurements, actual removed dependencies/code/assets, remaining justified dependencies and limitations. Keep physical piano/audio/display acceptance separate; never report it from headless runs.
5. Require explicit approval for reduced functionality or deferred agreed scope.

### Audit exit criteria

All shipped dependencies and executables have a documented current purpose and owner; the production artifact has no unneeded language runtimes or development/research artifacts; all supported behavior and user data survive; no new fallback renderer, timing authority or competing implementation exists. Any remaining dependency is deliberately retained with evidence. All claimed performance improvements are measured and all remaining blockers are listed. This document alone does not satisfy those gates.
