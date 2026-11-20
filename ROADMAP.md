# Piano Teacher — roadmap

**Updated 2026-11-20 · MIDI input only**

[Practice flow](docs/practice-flow.md) is the learner-visible contract.
[Architecture](docs/architecture.md), [development](docs/development.md) and
[reference](docs/reference.md) contain current technical documentation.
Superseded designs, detailed audit checkpoints and earlier phase logs remain in Git.

## Product

One Godot 4.7 desktop application, embedded CPython, native Verovio notation,
one immutable score stream and a single MIDI/transport timeline. MIDI
(`.mid`/`.midi`) is the only user import. Generated MusicXML serves engraving.

Each authored measure is learned alone, then with up to three preceding
measures: **1; 2, 1–2; 3, 2–3, 1–3; 4, 3–4, 2–4, 1–4; 5, 4–5, 3–5, 2–5**.
Each window advances Right → Left → Together and Listen → Free → Tempo.
The separate final examination uses the whole original piece.

## Owner decisions

| Date | Decision |
| --- | --- |
| 2026-11-08 | One complete authored count-in bar at any practice tempo. |
| 2026-11-16 | Authentic Verovio notation at display scale; visual acceptance is at the piano. |
| 2026-11-18 | Each window has its own Listen; opening does not play the whole piece. |
| 2026-11-18 | Small existing core suite; no infrastructure, pixel or parity tests. New regression tests require owner confirmation at the piano. |
| 2026-11-19 | Each new measure grows backwards to at most four bars; independent window progress and a separate final test. |
| 2026-11-20 | Accept onset drift up to the larger of 150 ms and one local sixteenth. |
| 2026-11-20 | After the second floor-failure return to Free for the same window/hand, announce one real Coda/Fukuda aid, then return to original Free without mastery. |
| 2026-11-20 | Saved first-window and final-exam sessions reopen in complete-window Free, then Tempo at 50% of original target. |
| 2026-11-20 | Exactly one count-in bar between automatic repeats takes priority over showing both dim neighbours. Messages overlay the handoff without adding delay. |
| 2026-11-20 | Rebuild CI around player behaviour; remove architecture/implementation-shape checks and report coverage without percentage gates. |
| 2026-11-20 | Consolidate docs recursively into four Markdown files and make README learner-facing. |
| 2026-11-20 | Hold-duration grading is opt-in from Settings (off by default); key releases remain measured in both modes. |

## Implementation and verification record

The last source baseline at the start of this continuation was `92780348`.
The prior decomposition commits are `fdf21b4b`, `1028dd32`, `9c493ec1`,
`acb26db9`, `66a3c803` and `25aab6e0`; `9654d2a3` fixed Listen preload
identity and isolated standalone stdlib staging. At that source, the existing
core/native checks, embedded repertoire/control journeys and strict relocated
package build/boot passed. Physical acceptance remained open.

The remote baseline at [`c11517f9`](https://github.com/tpepels/piano_teacher/commit/c11517f9976f23d228629c4701c4f11615c5ef0a)
passed [core CI run 44781461686](https://github.com/tpepels/piano_teacher/actions/runs/44781461686).
Native-production was skipped by the opt-in workflow policy. All six architecture
fixes A1–A6 are already on main, but their combined embedded/package and
physical acceptance was not established by that CI. Historical local records
below refer to their explicitly stated revisions.

| Current step | Implementation and evidence |
| --- | --- |
| Practice controls | `79e05ad8`: stable Pause/Resume and Listen again controls, wrong-note-only Free keyboard hints, two-second messages. Existing UI/Godot checks passed. |
| Complete practice flow and feedback | `6ef9dd30`: complete-window Free; explicit saved first/final warm-up; original MIDI target including half-speed below 12 BPM; persistent second-return aid and original return; authored bounds distinct from intact release tails; first-attack-aligned audio/grading; exact one-bar repeat admission with physical source/header clearance. |
| Authentic score and one feedback owner | `6ef9dd30`, refined in `ee6ccbf3`: both staves and dim source neighbours share existing renderer/queue. Active IDs alone are graded. Genuine carry-in ties and held tails retain source IDs. Recorder alone pairs presses/releases; live projection uses the final grader's assignment and frozen musical elapsed time. Source-to-head validation, full provisional replacement, explicit final locking, pending withdrawals and beat-gated tied heads prevent stale/future ink. Listen lighting, Free ink and actual-pitch ghosts share the retained source strips. |
| Previous core/native verification | At the pre-rebuild source, CI gates passed: **335 Python passed, one optional system SF2/libfluidsynth check skipped**; existing Godot scenarios report zero failures and `GODOT_STARTUP_SYNTAX_OK`. No tests added; existing assertions/doubles changed only for obsolete interfaces and owner-approved practice rules. Logs: `debug-sessions/practice-completion/python-final.log` and `godot-resume-final.log` in the same directory. Final carry-in model/server/import subset: 13 passed. Python source was unchanged by the final Godot-only Resume correction. |
| Additional source diagnostics | Actual engine: full four-bar Free, saved first/final Free, original tempo despite old manual target, announced aid → original Free without mastery, persisted return count, clean/failed exact repeat deadlines, leading-rest PCM alignment and complete held tails. Actual native assets: Moonlight selected/display identities, context/carry-in ties, no foreign graded attacks, future-tie gating, provisional retraction, Listen release and actual-pitch ghost facts. |
| Large-score work | Strict feedback lookup is linear and live observations bounded while canonical assignment is retained. Actual 18,058-note Hanon live-grader call measured about 9–26 ms; this is software cost, not physical MIDI/audio latency. |
| Full embedded and relocated package | **Passed on source `bc957d37`**: all seven full-workflow cases, including fixture creation, native bridge, production controls, Moonlight, Peace Piece, Chopin and strict relocated package build/boot. Checkout/package architecture audits report `PHASE5_ARCHITECTURE_AUDIT_OK`; runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Log: `debug-sessions/practice-completion/embedded-production-accepted.log`. |
| Documentation | `75ae738e` consolidates the historical tree into four current Markdown documents and introduces the learner README and dedicated wordmark. Final review reconciles Retry/Resume ownership and per-hand completion. All 104 local links/anchors across these guides, README and ROADMAP pass; all 14 prior research citations remain. Recursive Markdown count is exactly four. |

### CI suite rebuilt 2026-11-20

The owner approved a ground-up rebuild prioritizing player behaviour and
refactoring freedom. The unchanged baseline at `16a064e2` had 35 Python
modules/336 collected cases (335 passed, one optional audio skip) and 26
native scenario invocations. Baseline log:
`debug-sessions/practice-completion/test-rebuild-baseline.log`.

Commit `5477aa74` replaces the suite with ten Python modules/85 cases and four executed Godot
groups. It covers the actual default course, complete Free windows, growing
windows/hands, tempo/failure/aid/final progression, saved migrations, MIDI
recovery, real audio, fingering and source/take-specific feedback. Architecture,
source-text, private-shape, parity and widget/layout checks are removed.
Package validation retains required runtime assets and actual import closure
without historical module-name restrictions. See the [coverage map](docs/development.md#ci-coverage).

The rebuild exposed a real manual final-entry defect: selecting the final and
requesting Learn could start timed Learn at target tempo without guided targets.
Commit `0e060629` keeps explicit final Learn in whole-piece Free before normal
half-speed Tempo. Automatic final progression already entered Practice at 50%.
The regression failed before the fix in `debug-sessions/practice-completion/final-learn-red.log`.

Current local CI passes: **84 Python passed, one absent optional system-SF2
skip; production Godot parsing and all four native behaviour groups pass**.
Python coverage is **58.9% lines, 38.3% branches**, informational without a gate.
CI uploads XML/JSON coverage reports. Evidence: `debug-sessions/practice-completion/ci-rebuild-final.log`.
The **full embedded workflow passes all seven cases on `5477aa74`**: isolated
fixture, embedded registration/real score, default Practice Flow controls,
Moonlight Sonata with Retry/Listen/navigation, Peace Piece, Chopin and strict
relocated standalone package build/boot with a cleared environment and clean
HOME. Checkout and packaged source both report `PACKAGE_CONTENTS_OK`; the
runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Evidence:
`debug-sessions/practice-completion/embedded-ci-rebuild.log`.
This is local software verification; no new remote GitHub result or physical
acceptance is claimed. The correction record below is historical evidence.

### Coverage extension 2026-11-20

The owner requested additional CI coverage while retaining the compact,
behaviour-focused policy. The extension exercises real-take statistics,
stable paging and bounded-detail missingness, explicit redacted/atomic export,
scoped reset/deletion, desktop admission/expiry/failure/retry/Resume/Listen and
exact repeats, configured piano keys, library-health recovery, all built-in
warm-ups, native chord/tie/tuplet/meter fidelity and stale preload rejection.

The new mastery-report scenario exposed a real defect: the completed default
course uses two target successes, but the state snapshot and captured history
advertised the old generic three-pass rule. Commit `873f1b43` exposes the actual
required count to snapshots, transition messages, evidence and validation.
Statistics prefer that captured rule while retaining the legacy recorded-settings fallback. The
grading/progression rule itself is unchanged. Both failures were reproduced
before the fix in `debug-sessions/practice-completion/coverage-mastery-red.log`
and `coverage-mastery-snapshot-red.log` in the same directory. All 30 focused
history/course/resume/alternate cases pass in `coverage-mastery-green.log`.
Review found the same obsolete count in the pending-repeat message; the
desktop scenario reproduced the actual “Clean pass 1/3” in
`coverage-pass-notice-red.log`. It now reports the actual 1/2 criterion. All 37
combined rule/history/desktop/course/resume/alternate checks pass in
`coverage-rule-green.log`. The independent review found no critical or
important regressions; whole-source notation parity was narrowed to the actual
opening chord and held ending.

Commit `70f7b459` completes the remaining control/source scenarios and coverage
guide. The expanded Python suite has twelve feature modules and 108 cases (23 added):
**107 tests pass, one optional system-SF2 check skips**.
Informational coverage rises from **58.9% to 69.5% lines** and **38.3% to
49.4% branches**, with the same source scope and no exclusions or percentage
gate. The common CI command also passes Godot parsing and all four native
behaviour groups, with zero failure counters. Evidence:
`debug-sessions/practice-completion/coverage-extension-ci-final.log`.
The **full production/package workflow passes all seven cases on `70f7b459`**:
embedded registration/real score, the default Practice Flow scene/control
journey, Moonlight Retry/Listen/navigation, Peace Piece, Chopin and the actual
strict relocated standalone build/clean-HOME/cleared-environment boot, plus
fixture creation. Both content audits report `PACKAGE_CONTENTS_OK`; the full
runner exits zero with `PASS LOCAL EMBEDDED PRODUCTION CONTROL`. Evidence:
`debug-sessions/practice-completion/coverage-extension-embedded.log`.
No push or new remote CI result is claimed. Physical and clean-machine
acceptance remain unverified.

## Hold grading and architectural verification — 2026-11-20

**Grade how long I hold notes**, off by default, persists in desktop Settings.
The single preference controls fixed and tempo-mapped live/final scoring,
feedback event ink, clean progression and captured assessment-rule identity.
Key releases are measured in both modes. Changing the setting stops the active
attempt after the preference saves. Existing player-focused tests have been
updated; no new test modules or architecture-shape tests are introduced.

The six architecture defects originally reported at `82bf06bb` already have
implementation commits: A1 sustained-note admission (`96c895e7`); A2 bound
resize (`0d959470`); A3 lifecycle writes (`e7b10962`); A4 read-only
snapshots (`1507b427`); A5 dependency cycles (`f8daff77`); and A6
request encapsulation and obsolete native ports (`c11517f9`).
Commit `ad1055ac` repaired the acceptance readers exposed by removal of
the renderer's private `stream_passes` property. Both remote core and
native-production CI then passed
([run 44796955201](https://github.com/tpepels/piano_teacher/actions/runs/44796955201)),
including embedded real-score journeys and relocated package boot.
The follow-up commits `0028157d` and `44398729` remove remaining
private-helper imports in the source-planning, notation, engraving, MIDI
import and research modules; the bounded authentic SVG rasterizer is shared
without a reverse tuplet-to-beam import. Native-production passed at `44398729`
but its core CI hit real audio-readiness timeouts under concurrent fixture
rendering (101 passed, 4 skipped; three timeouts and two worker teardown errors).
Fallback PCM is now synthesized with a bounded fundamental-phase recurrence,
preserving the original overtone weights, attack/release shape and output
format while avoiding redundant per-sample transcendental calls. Its cache
revision changes to invalidate old synthetic WAVs. A fresh complete CI
result is required before accepting this correction. Physical and clean-machine
acceptance remain separate.

## Phase status and remaining acceptance

### Architecture re-audit 2026-11-20

Remediation execution: A1 now validates authored and sounding bounds from the
existing semantic source contract. Targeted Python and all native checks pass;
the direct gateway diagnostic accepts a full held ending and rejects different
prepared coverage (`96c895e7`). A2 now preserves bound crops and committed
horizontal spacing on resize; targeted Python/native checks and the existing
controller journey with a resize diagnostic pass. A3–A6 and obsolete-port
cleanup remain open. Physical resize acceptance remains unverified.
A3 lifecycle transfers now pass all 107 Python behaviour checks (one optional
system-SF2 skip); remaining work is A4–A6 and obsolete internal ports.
A4 now removes transition execution and guided-deadline scheduling from reads.
Full local CI passes (107 Python, one optional skip; native/parser pass).
The remaining implementation is A5/A6 and obsolete internal ports.
A5 now removes the deferred runtime cycles and private source-index coupling;
all 107 Python checks pass, and the one-off runtime import scan is acyclic.
Remaining implementation: A6/private requests and obsolete native ports.
A6 and obsolete native ports are implemented; all six source-audit items now
have code changes. Full local core CI passes, with 69.6% Python line and 49.4%
branch coverage. Integrated review and full embedded/package verification are
pending; physical acceptance remains unverified.

Implementation audited at `640a77f5`. The prior Phase 5 completion assessment
was too broad and is reopened. The [active audit](docs/architecture.md#remaining-work--source-audit-2026-11-20)
records six concrete remaining items, priorities and intended owners:

1. A1: authored-versus-sounding endpoint disagreement can refuse desktop
   admission for a cross-bar held note. Actual existing MIDI/public-command
   diagnostic publishes 4 versus 6 beats; the inspected Godot guard rejects it.
2. A2: viewport resizing can rewrite a retained node's source crop outside its
   admitted immutable stream binding. Source mutation path confirmed; physical
   appearance has not been observed in this audit.
3. A3: remaining Engine/PlaybackSession writes bypass transport, attempt and
   guided lifecycle owners; finish those transfers through semantic operations.
4. A4: snapshot reads still call the mutating transition loop alongside the
   existing worker; remove the compatibility advancement path.
5. A5: deferred statistics, tuplet and course/generator cycles and the private
   alternate-curriculum source-index dependency remain.
6. A6: admission/preloader callers still inspect private request IDs. Also
   remove unused internal mutation facades after checking supported API usage.

No production code or tests were changed for this audit. No new test run,
remote CI result, graphical reproduction or hardware acceptance is claimed.
The existing source/method review and recorded public-command diagnostic are
the evidence. The earlier software gates remain historical scenario evidence.

### Production rerun and correction record

At `75ae738e`, the full embedded workflow passed native registration and the
strict relocated standalone build/clean-HOME boot, but failed four real-scene
checks: stale preparation overlay, missing Retry leading rest, and incomplete
Peace Piece/Chopin context chord atlases. These were actual implementation
failures; their acceptance checks were retained.

The asset correction compiles every authentic atlas from the same complete
notation model before bounded display projection. Source/active IDs and one
renderer are preserved; incomplete cached atlases are invalidated. Retained
command-buffer generations now republish readiness after admission-time crops,
so readiness cannot precede its matching status notification. The five existing
asset-session scenarios pass, the exact Peace/Chopin native assets compile,
and the actual production Play/Pause/Resume journey passes.

At that pre-rebuild source, the Python suite passed **335 tests, one optional audio dependency
skip**. Final native checks and the complete production/package rerun pass.
The first failed run is retained in
`debug-sessions/practice-completion/embedded-production.log`; acceptance below
uses the subsequent complete rerun rather than focused diagnostics alone.

Asset/readiness source commit: `546bdaca`. Retry now creates its complete
leading rest in the same admitted source batch and owner when no full
predecessor rest survives. Stable before/source/after slot identities preserve
FIFO order, archive replay and rollback; a provisional prefix remains hidden
until authorization. The unchanged actual Moonlight journey passes Retry,
count-in state and cue delivery with Dummy audio, Listen, navigation, tempo
changes and saved reopening
(`debug-sessions/practice-completion/retry-fixed-reproduction.log`).

Retry source commit: `242d71ae`. Final review also corrected second Pause
during a Resume reading lead, accepted early first attacks and signed ghost
coordinates. MidiIngress alone applies the temporal gate; Recorder preserves
the accepted timestamp. Backend-selected `release_advisory` keeps accepted flow
notes green while retaining complete measured release dimensions. Native
ghosts use the existing physical strip/header bounds. Existing Python remains
335 passed/one optional skip; the complete final Godot script passes with all
failure counters zero and `GODOT_STARTUP_SYNTAX_OK`. No new tests were added.

Feedback/clock source commit: `ee6ccbf3`. Its complete production run passed
the fixture, native registration, Moonlight journey and strict relocated package
build/boot, but Peace Piece and Chopin exposed a Resume withdrawal of an
unexpired paused source strip. Resume now protects the first retained paused
strip while allowing later unseen measures to withdraw; preview and actual
withdrawal use the same queue policy. Its new admitted copy explicitly retains
the paused transport predecessor without changing existing geometry or keys.
Both unchanged repertoire journeys now pass in
`debug-sessions/practice-completion/resume-fixed-reproduction.log`; the complete
native script also passes with zero scenario failures in
`debug-sessions/practice-completion/godot-resume-final.log`.

Resume source commit: `bc957d37`. The final full production workflow exits zero
and passes every case on that committed source, including the unchanged Peace
Piece/Chopin Resume checks and actual relocated standalone package build/boot
under a clean HOME and cleared environment. Log:
`debug-sessions/practice-completion/embedded-production-accepted.log`.
The same run passes the architecture audit for checkout and packaged source.
That run predates the CI rebuild and manual final-Learn correction recorded
above; it remains historical evidence for that source.

| Phase | State |
| --- | --- |
| Phase 5 — ownership decomposition | A1–A6 implemented in `96c895e7` through `c11517f9`; `ad1055ac` corrected obsolete acceptance diagnostics. Combined core/native/package workflow passed at `ad1055ac`. A follow-up helper-ownership cleanup requires a new full CI result. Physical acceptance remains open. |
| Phase 6 — software and physical verification | Full embedded/native and relocated standalone software workflow passed on `ad1055ac` ([run 44796955201](https://github.com/tpepels/piano_teacher/actions/runs/44796955201)). Helper-ownership follow-up needs a fresh full CI run. Physical MIDI/audio, rendering and clean-machine acceptance remain open. |

Unverified acceptance: Kawai CA49 USB and Bluetooth MIDI, physical press/release
latency, speakers and audible count-in, real-performance grading, on-screen
scrolling/spacing/colour/ghost acceptance, reconnect and drift under real load,
and a clean-machine desktop package. Headless results do not certify these.

The owner should exercise Moonlight Sonata, Peace Piece, Chopin, moving windows,
Listen/Free/Tempo, count-in, Pause/Resume/Retry, automatic continuation, the aid
return and saved final examination using [the physical protocol](docs/development.md#verification-and-acceptance).

## Commands

```bash
./run.sh
bash scripts/test.sh
bash scripts/verify-embedded-production-local.sh
bash scripts/package-inprocess.sh
```
