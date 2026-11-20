# Fingering, learning evidence and research

[Practice flow](practice-flow.md) is the product behaviour contract;
[architecture](architecture.md) defines current owners; [development](development.md)
covers setup and acceptance. This reference preserves data/provenance contracts
and the limits of research claims. Product phases belong to [ROADMAP](../ROADMAP.md).

## Fingering

Automatic fingering receives both hands of the complete original MIDI `Piece`
at source BPM. Practice tempo, selected hand, simplified variant and repeated
passage only project the result by stable `source_id`. They never change the
graded note set or event times. Numbers are shown only for known assignments;
right-hand numbers are above the staff and left-hand numbers below. A tied
continuation gets no new number.

Right-click a note or choose its number to set 1–5. “Use original / automatic”
removes the manual correction. Shared keys retain separate original-voice
choices. An edit applies to every exercise containing that original note.
Source correction is serialized and validated against the captured source
generation, fingerprint and original-notes identity before durable work and
again before installation; a late result cannot replace a newly opened piece.

[FingeringProvider](../piano_teacher/fingering/) accepts the original piece and
fixed constraints. Its plan records canonical source IDs, hands, known/unknown
fingers, original annotations, overrides, provider/model/config versions, input
digest and diagnostics. Plans are written atomically under an interprocess
lock. Compatible sources reuse plans; source/config/model changes are isolated.
Removing an override may reuse the saved uncorrected prediction.

Plans and corrections live under `$XDG_DATA_HOME/piano-teacher/fingering/`
(normally `~/.local/share/piano-teacher/fingering/`). Keep `overrides.json` when
clearing derived caches: it contains manual corrections. A corrupt override
file is reported, not silently reset; corrupt derived plans can be rebuilt.

The [Lumikey adapter](../piano_teacher/fingering/lumikey.py) uses the published
`@lumikey/piano-fingering-model` **0.3.0**, its unmodified pretrained ONNX models
and **ONNX Runtime 1.30.0 CPU**, with one execution thread. Exact package/model
hashes, licensing and provenance remain in the
[third-party notices](../piano_teacher/fingering/lumikey_runtime/THIRD_PARTY_NOTICES.md).
The publisher declares the package including model files MIT, without a separate
model license/copyright text. Training source/data are not copied into this
project. [One-time setup](development.md#build-and-run) is the networked install
step; opening, inference and correction run locally afterward.

The adapter masks physically/fixed-constraint-incompatible real model logits:
distinct held keys need distinct fingers, simultaneous chords respect pitch
order, and future fixed overlapping fingers reserve their intervals. Equal-pitch
written voices may share a physical key while retaining separate identities.
The highest remaining model score wins; no heuristic fallback fabricates a
finger. Unsatisfiable dense/held constraints, out-of-range notes or inference
failure remain unknown with a reason. Manual/authored known fingers remain
available if the runtime is missing.

This is constrained sequential inference, not exhaustive whole-piece search or
a model of the learner's hand reach. It preserves imported hands/durations and
does not guarantee editorial fingering. Conflicting primary fingers require
correction; substitutions/alternates remain text and may be flagged for review.
Missing expression, pedal technique and physical hand use cannot be recovered
from MIDI and must not be presented as measured facts.

Bundled Japanese count-in clips have their own exact public-domain provenance
in the [count-in asset notice](../godot/assets/countin/README.md). Keep these
notices alongside the assets; do not replace them with a research summary.

## Local learning evidence

One evidence ledger shares the [ProgressRepository](../piano_teacher/progress_repository.py)
SQLite connection. [LearningCapture](../piano_teacher/application/learning_capture.py)
captures the authoritative grader's actual assignment; it never rematches notes
from status colours later. There is no second recording/history service.

| Entity | Identity and meaning |
| --- | --- |
| Learner | Random local ID; no account, name or inferred physical identity. |
| Practice session | One engine run with UTC bounds, run ID, terminal reason and separately accumulated active/guided/pause/count-in/preparation/feedback intervals. Saved navigation `sessions` are distinct. |
| Attempt | Stable UUID, exact source/generator/stage/hand/variant, source-note IDs, interval, target/performed BPM, frozen tempo map, transport/revision, calibration and full/partial/guided/preview/Perform classification. |
| Note observation | Expected source pitch/onset/release, actual matched press identity/times, signed onset/hold/release residuals, local seconds/beat, applied tolerances, independent dimensions and explicit missing/unreleased/truncated/ambiguous flags. |
| Assessment | Unique attempt linkage, grader/schema/rule versions, actual assessed interval/completeness, counts, clean/passed and eligibility/reason. |
| Retry decision and outcome | Selected policy/version/resolved parameters and scope/BPM before/after; subsequent exposure linkage, observed/aborted/canceled/censored outcome, supported focus versus unsupported original-target verification. |
| Rule snapshot / event | Frozen formulas, versions and settings plus source/map provenance; pause, assistance, navigation, interruption and progression facts with stable IDs. |

An attempt ID survives pause/resume and failed commit retry; a new repetition
gets a new ID. Transport IDs and score revisions are provenance, not globally
unique attempts. Source/revision changes cannot relabel sealed evidence.
UTC groups calendar history; run-relative monotonic intervals measure duration.
Monotonic epochs cannot be compared across process restarts. Preserve the BPM
actually performed, not the next retry's BPM.

Chords have several pitch obligations but one onset opportunity. Extras have
press IDs without fabricated expected-note identities. Source hand does not
prove which physical hand played. Uncaptured velocity/pedal accuracy stays
unavailable. Aborted takes never invent omissions in an unobserved suffix;
unreleased keys are distinct from measured short holds.

### Grading, mastery and settlement

Keep `Assessment.clean`, `Assessment.passed` and actual mastery awards separate.
Current Practice Flow uses the [two-clean-at-target rule](practice-flow.md).
Its accepted flow verdict checks pitch, onset and extras; retained key-release
observations do not fail the flow. This differs from strict `Assessment.clean`.
Other registered strategies can retain their configured accepted-full-target
criterion. The historical `accepted-full-target-v1` rule meant no wrong,
omitted or extra notes and timing/hold warnings on fewer than half the distinct
onset groups; three consecutive eligible full-target takes awarded mastery.
Historical snapshots keep their original rule and cannot be retroactively
rewritten into current flow credit. Neither criterion proves durable learning.

Guided, partial, assisted, Perform and preview outcomes retain their real scope;
they never masquerade as unsupported complete-target mastery. A successful
slower/shorter retry is not evidence of equivalent original-target ability.

Capture and progress settle in the existing savepoint. Identical repeated
settlement is a no-op; the same identity with a conflicting sealed payload is
an error. Save failure preserves the take and blocks unrecorded mastery.
Crash recovery closes open attempts as interrupted with known checkpoint prefix
and unknown end/suffix; exactly-once settlement does not mean zero data loss
under arbitrary process death. Invalid rejected commands do not create applied
events or terminate an otherwise valid take.

Each intervention has one proximal outcome: its first subsequent linked
exposure, even if aborted. An episode may separately link its first unsupported
original-target verification. Later interventions do not erase prior outcomes
or receive independent causal credit for the complete sequence. Source/hand/
stage/policy/rule changes, override or session end censor unresolved episodes.

### Retention, export and deletion

Default note-detail retention is **365 days / 256 MiB logical detail payload**.
Validated preferences range from 7–3,650 days and 16–4,096 MiB. These limits do
not promise SQLite/WAL file sizes. Safe transitions prune oldest complete-session
detail transactionally, recording coverage while retaining compact counts,
provenance and outcomes. Open/pending evidence is not silently pruned. A full
budget suspends recording safely if eligible pruning cannot accommodate a write.

Queries/exports disclose retained-since bounds, missingness, pruned detail and
censored outcomes. Legacy bounded history is migrated once with deterministic
identities and `legacy_bounded` provenance. Unknown dates, rules, matches and
onset groups stay unknown; pruned note sequences are never reconstructed from
summary counts.

Settings provides explicit local versioned JSON export and confirmed deletion.
Default export omits source paths, piece/device names and raw MIDI bytes;
optional detailed exports include retained observations with units/provenance.
There is no automatic upload, account or participant enrollment. A random local
ID is pseudonymous, not a guarantee that a detailed musical trace is anonymous.

- **Reset lesson** preserves learning evidence and records the reset.
- **Delete piece history** removes linked evidence and saved learning progress/
  generator feedback for that learner and source.
- **Delete learner history** removes evidence/proficiency/tempo/guidance feedback;
  next use creates a new learner ID.

Source MIDI and device/audio/window preferences remain. Already exported copies
are outside application deletion control. Deletion remains available at the
recording limit and removes linked rows without orphan evidence.

### Bounded read-only statistics

`learning.statistics` uses query version **1**, report schema **2**, canonical
ledger schema **1**. Filters cover exact source fingerprint, session, stage,
hand, scope, policy, inclusive UTC dates and performed BPM. Default page size
is 250, maximum 1,000. Cursors freeze the insertion high-water mark and bind
learner/filters/limits; deleted anchors expire them. Unknown context cannot
match a known-value filter.

Retained-detail snapshots use a 2 MiB default / 4 MiB maximum budget, at most
10,000 observations and 4,000 related rows per event/decision/outcome table.
Error locations are capped at 1,000 per dimension, local timing/policy cohorts
at 250, and recorded phases at 20,000 intervals / 64 names. Truncation remains
explicit; counts limited by a related-row cap are lower bounds. Quantiles use
only retained bounded samples. Combined grading-status rate and independent
pitch accuracy retain separate denominators. The
read-only asset worker captures a bounded `mode=ro`, `query_only` WAL snapshot,
releases it before formatting and checks for deletion/learner changes afterward.
It does not acquire the music lock or change progress.

Reports separate pitch accuracy, clean/accepted rates, timing/hold residuals,
performed-tempo trajectories, active practice intervals and intervention burden.
Every denominator names eligible scope and retained coverage. Missing phase
intervals cannot become complete practice time; unfinished mastery is censored.
Comparable policy cohorts retain all grading/source/calibration facts except
the policy fields deliberately compared. Descriptive group differences are
not causal effects or inferred expertise. Settings → Learning history → Practice
statistics provides bounded paging, refresh and explicit loading/error/empty
states; stale learner/current-piece replies are rejected.

## Research and evaluation

Coda/Fukuda generators and fixed retry policies are selectable source-safe
algorithms, not validated claims of better teaching. They retain stable IDs,
versions, authentic source bindings and explicit transformations. Practice Flow
uses them only as an [announced simplified aid](practice-flow.md#simplified-exercises-coda--fukuda),
then returns to original-note Free. It does not silently substitute an entire
research curriculum for normal moving windows.
The durable `flow_returns` table belongs to the exact stage/window and hand;
aid completion restores original full-window Free and awards no original mastery.

The six fixed response baselines remain `adaptive`, `steady-repeat`,
`slow-practice`, `micro-loop`, `guided-repair` and `finish-then-review`.
The misleadingly broad `adaptive` ID retains its fixed configured behaviour.
The separately registered `evidence-adaptive` selector (version
`evidence-adaptive-v1`) uses comparable
source-bound outcomes to repeat, isolate, slow and reintegrate. Its source
requires repeated concentration (at least three pitch errors, at least 60% in
one shared bar across two failures) before isolation, and limits new automatic
interventions to twelve before ordinary repetition continues. These constants
are engineering choices, not experimentally optimal pedagogy. Registered
handlers receive frozen facts and return validated decisions; invalid source,
tempo or boundaries fail explicitly without policy-name branches in the engine.

### Evidence and its limits

These sources motivated questions and comparison designs; none validates this
application's exact thresholds or ranks its policies:

| Source | Relevant evidence and limit |
| --- | --- |
| [Ericsson, Krampe & Tesch-Römer (1993)](https://doi.org/10.1037/0033-295X.100.3.363) | Purposeful practice framework/history; not a randomized test of these beginner piano retries. |
| [Duke, Simmons & Cash (2009)](https://doi.org/10.1177/0022429408328851) | Accuracy related to next-day rankings in 17 advanced pianists; small observational study of one passage, not a causal interruption rule. |
| [Allingham & Wöllner (2022)](https://doi.org/10.1177/03057356211073481) | Slow practice survey, 256 instrumentalists; self-report supplies no optimal percentage. |
| [Hanberry (2004)](https://repository.lsu.edu/gradschool_dissertations/1187/) | Eight-week strategy instruction in 39 music majors found no significant between-group accuracy effect; bundled strategies do not isolate mechanisms. |
| [Winstein, Pohl & Lewthwaite (1994)](https://pubmed.ncbi.nlm.nih.gov/7886280/) | Some frequent physical guidance impaired nonmusical retention; this does not prescribe piano prompt fading. |
| [Fujii, Lulic & Chen (2016)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4893479/) | Full concurrent auditory feedback helped an arm-coordination task; counters a universal reduced-feedback rule. |
| [Caramiaux et al. (2018)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5832267/) | Tempo-set/order affected immediate smoothness in 48 nonmusicians; no delayed retention and no universal random-tempo prescription. |
| [Cash (2009)](https://doi.org/10.1177/0022429409343470) | Rest placement affected a short piano-sequence task; no universal repertoire break duration follows. |
| [Wiseheart, D’Souza & Chae (2017)](https://doi.org/10.1371/journal.pone.0182986) | No reliable spacing advantage in tested novice piano tasks/lags; verbal-memory spacing cannot simply be imported. |
| [Moringen et al. (2024)](https://arxiv.org/abs/2406.04812) | Small teacher-choice modeling manuscript; predicting choices does not establish learning benefits. |
| [McKay et al. (2022)](https://doi.org/10.1016/j.psychsport.2022.102165) | Reduced-feedback synthesis found substantial uncertainty and no significant overall advantage. |
| [Zhang & Liu (2026)](https://pubmed.ncbi.nlm.nih.gov/42947794/) | Heterogeneous instrumental-feedback evidence with limited delayed retention/transfer. |

No strong direct comparison here establishes that interrupting at a bar boundary
beats completing the same phrase at equal dose. Acoustic delayed-feedback
experiments do not answer when a visual assessment message should appear.
Fukuda's MIDI-domain adaptation is not proof of exact reproduction of its
original acoustic-system figures. Original-author ground truth, independent
learners and paper parity remain separate evidence requirements.

### Evaluation boundary

Offline replay freezes original MIDI/hash, source/stage/hand, versions, rule/map
settings, calibration, note-on/off traces, clock schedule and initial database.
It can compare deterministic engineering decisions, source coverage, performed
BPM, interruption counts, rollback and resource use. It cannot predict what a
person would play after a different intervention. Simulated successes never
establish learning efficacy.

A human comparison needs consent, prespecified matched unfamiliar passages,
counterbalanced conditions, experience/difficulty/device/calibration records
and equal practice dose. The proposed retry feasibility crossover compares a
candidate, default and finish-then-review; a Coda/Fukuda/combined/original course
comparison is a distinct study. Neither has been completed merely by preparing
scripts or operator materials.

The primary proposed retention endpoint is unsupported full-original-target
pitch error at a common prespecified tempo after 24 hours, with blind checks,
uncertainty and missing follow-ups reported. Track timing/hold separately,
eligible clean-pass rates, censored time-to-mastery, transfer, interruptions,
assistance, voluntary stops and actual learner-reported frustration. MIDI alone
does not diagnose fatigue, attention, emotion or physical hand use.

Online action learning needs eligible action sets, known nonzero selection
probabilities, policy/RNG versions and observed/censored outcomes. Deterministic
logs cannot evaluate unchosen actions. [Li et al.'s replay method](https://arxiv.org/abs/1003.5956)
and [Dudík et al.'s off-policy evaluation](https://proceedings.mlr.press/r10/dudik12a.html)
depend on appropriate support; they do not create missing counterfactuals.
No universal sample minimum or pedagogical superiority is claimed.
