# Mistake-response policies (MIDI practice)

## Source of truth
Each musical mistake is graded against the already-authoritative MIDI score, source
measure grid, active hand, and transport clock. Responses receive immutable
evidence and return a **decision**. PracticeEngine alone mutates tempo, plans,
persistence, score revision, the one MIDI recorder and the visual rewind. No
policy owns a timer, starts a second backend, infers missing notation, or
awards mastery. Partial retries never earn full-passage mastery.

Registered policies live in
`piano_teacher/application/mistake_responses.py`. Call
`resolve_mistake_policy(id)`, `rolling_response(policy, facts...)` or
`whole_response(policy, evidence...)`. An invalid ID raises an error,
rather than silently switching strategies. The selected ID is a validated,
persisted `mistake_response_strategy` preference and appears in Settings
under **When a note is wrong**. Changes apply to new decisions without
restarting the score. None of these settings changes the exercise generator.

| Policy | Rolling threshold | Failed complete take |
| --- | --- | --- |
| Adaptive recovery (default) | Two-measure rewind, -10% tempo, guided on second repeated problem | Ordinary rewind at existing tempo |
| Repeat at current tempo | Two-measure rewind, same BPM, no forced guidance | Ordinary rewind |
| Slower, accurate repetition | Two-measure rewind, -20% tempo, no forced guidance | -10% BPM and retry |
| Isolate difficult measures | Last offending chunk's final measure, -10% tempo, guidance on third repeat | -10% BPM and retry from latest graded bad measure |
| Guided repair | Two-measure rewind, -10% tempo, guided immediately | Rewind; guided intervention on mid-phrase threshold |
| Finish the phrase | No mid-phrase interruption; allow complete assessment | Rewind after the full assessment if failed |

The five-error rolling threshold, on-time/early/late MIDI assessment,
meter-aware boundaries, source identity, min-BPM bound, score loading gates,
and third clean-pass mastery are unchanged. Focused partial retries preserve
the original whole-passage verification step. Warm-ups retain their own
rules. Policy names and thresholds are configuration, not proven estimates
of causal teaching effectiveness.

## Research basis and limitations

* **Slow deliberate practice and tempo changes**: Allingham and Wöllner,
  *Psychology of Music* (2022), survey of 256 adult instrumentalists.
  Slow practice is widespread; their findings are *self-reports*, not
  evidence that a fixed -10% or -20% reduction is optimal.
  https://doi.org/10.1177/03057356211073481
* **Error-tolerant versus error-avoiding contexts**: Kruse-Weber and
  Parncutt's interdisciplinary framework distinguishes exploratory
  performance from accuracy-focused procedural practice. This motivates
  an uninterrupted "finish then review" option alongside immediate repair.
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4110716/
* **Short, directed trouble-spot practice**: Hanberry (2004) studied
  score analysis, hand shifts, difficult chords, accidentals and
  metronome-supported slower practice in undergraduate piano learners.
  The study *did not find significant group differences attributable to
  the taught practice strategies*. Its practical categories informed our
  one-measure option, not a claim of proven superiority.
  https://repository.lsu.edu/gradschool_dissertations/1187/
* **Explicit practice instructions**: Pike and Salas-Ruiz (2025) reported
  improved playing accuracy in a case study involving directed worksheets
  with intermediate group-piano students. It supports exposing concrete
  response descriptions, not claiming a trained personalized model.
  https://doi.org/10.1177/02557614251393168
* **Feedback is not proof of durable learning**: Zhang and Liu (2026)
  reviewed technology-mediated feedback in instrumental practice. This
  implementation verifies event timing and score fidelity; long-term
  retention and comparative teaching effectiveness remain untested.
  https://pubmed.ncbi.nlm.nih.gov/42947794/

## Acceptance and extension contract
A new response must have a stable ID and explanation, valid tempo/focus
bounds, a pure no-side-effects policy, full- and rolling-evidence behavior,
source-bound tests, a Settings option, and a safe fallback for inadequate
evidence. The engine must not grow a policy-name-specific chain.

The public extension is `register_mistake_policy(MistakePolicy(...))` called
once before loading settings. A registration can declare `rolling_handler`
and `whole_handler` pure functions; they receive frozen `RollingEvidence`
and `WholeEvidence` objects and return `RollingResponse` /
`WholeResponse` decisions. The public evaluator checks identity, authentic
metrical boundaries, tempo bounds and source duration even for third-party
strategies. An invalid decision raises rather than corrupting a transport or
silently changing the score. The six supplied strategies use the same default
evaluator with independent parameters; custom algorithms can replace either
evaluator without touching `PracticeEngine`.
Policy changes during active playing must preserve the current recorder,
transport ID, existing score revision and source-derived evidence.
