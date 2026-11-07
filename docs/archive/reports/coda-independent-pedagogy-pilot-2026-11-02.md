# Independent Coda pedagogical evaluation protocol

**Protocol ID:** `coda-pedagogy-fixed-performance-pilot-v1`

**Status:** Historical v1 analysis infrastructure only; **no real participants enrolled
and no pedagogical effect established**. The v1 intervention description used a
removed comparator and is not ready for prospective enrollment. This protocol is recorded as
a design document, not a retrospectively successful experiment.

## Question and comparison

Does a MIDI pianist's ability to play an **unchanged original score** improve
more after a fixed amount of practice with Coda-derived exercises than after
the existing heuristic lessons?

The intervention is the **actual application teaching order**, NOT
the historical Tang Coda backend (which does not specify a curriculum).
Historical v1 specified Coda as `coda-midi` and its comparator as `legacy`.
`legacy` is no longer registered and must not be restored. The available
original-progression comparator is `source-progression`. A new prospective
protocol must freeze that actual registered generator/version and the selected
Coda generator/version, rather than silently interpreting old v1 records as a
different intervention. The existing v1 analysis remains a historical instrument.
The specific software revision and strategy snapshot must be fixed at
the start of data collection; neither branch is updated mid-study.

## Trial procedure

1. Obtain explicit informed consent. Assign each participant a random
   pseudonym **outside the application** and one MIDI piece appropriate
   to their level. Keep any identity mapping separately from study data.
2. Randomize with `scripts/evaluate_coda_pedagogy.py assign` using a
   private randomization secret. The coordinator privately maps blinded
   `A` and `B` to the prospectively fixed registered strategies before enrollment; the person
   analyzing results must not see that mapping.
3. Each participant performs the **complete original score** on a real
   physical MIDI keyboard at a **fixed identical BPM** for their piece.
   Capture expected original attack count, correct note attacks and extra
   note attacks using one unchanged scoring engine revision. This is the
   **pretest**. The piece/tempo/hand arrangement must be identical in the
   posttest and between both arms.
4. Give exactly **15 minutes** (± 15 seconds) with the allocated lesson
   generator. No teacher intervention that differs between arms. Use the
   normal practice controls, including retry, without exposing the other
   strategy during training. Log any departures separately.
5. Repeat the **same unchanged original-score performance test** at the
   same fixed BPM, before revealing the assigned arm to the analyst.
   This is the **posttest**. No transformed exercise, slow passage, easier
   tempo or stage-specific mastery score can substitute.
6. An independent analyst runs the predefined program over
   pseudonymized observations. Keep the A/B mapping blinded until the
   analysis is finalized. A new prospective protocol must include a 24-hour unsupported original-target
   retention test at the common test BPM, with a seven-day test when feasible.
   Those delayed outcomes need explicit fields and a prespecified analysis; the
   v1 immediate pre/post program does not analyze them. See the current
   [retry evaluation protocol](../../mistake-response-policies.md#evaluation-protocol).

**Unit of randomization:** one participant learning one piece. A
participant may contribute only one piece to avoid falsely treating
repeated observations as independent. Each evaluated piece needs both arms.
Separate subjects must play at the same fixed test BPM, with equal
assessment revision, original note count and comparable exposure.

## Predefined outcome

For each pre/post whole-piece attempt:

`accuracy = max(0, (correct_attacks - extra_attacks) / original_score_attacks)`

Primary individual improvement is `post_accuracy - pre_accuracy`.
For each piece, compute the mean improvement for blinded A and B and
subtract B from A. The overall effect is the sample-size-weighted average
of piece-level differences. Use a **within-piece, fixed-arm-count
permutation test**; enumerate exactly when at most 16,000 allocations,
otherwise use 10,000 deterministic pseudo-random allocations. This
addresses the randomization design but not missing compliance,
participant-selection bias, prior familiarity, or differences in the
music played. The result is descriptive until independently reproduced.

The analysis does not treat elapsed practice steps, application mastery
indicators, total stage counts, generated notes or unit-test success as
proof of improved learning. External preregistration, a prospective power analysis and
human study are necessary before confirming a meaningful improvement.

## Data and privacy

Input is a JSON file with exact `protocol` and a list of
`observations`. Each observation must contain:

```json
{
  "anonymous_subject": "opaque-code",
  "piece_fingerprint": "source-midi-fingerprint",
  "blinded_arm": "A",
  "original_score_attacks": 100,
  "test_bpm": 80,
  "pre_correct": 60,
  "pre_extra": 0,
  "post_correct": 70,
  "post_extra": 0,
  "practice_minutes": 15.0,
  "assessment_version": "fixed-score-grader-version",
  "instrument": "physical-midi",
  "completed_original_score": true
}
```

These numbers are **schema examples, not observed study data**.

No names, emails, recordings, full MIDI note streams or medical traits
are required by the analysis. Do not commit participant files, the
randomization secret, or the secret arm-to-strategy mapping.

The analysis rejects a changed/unknown assignment, duplicate participant,
missing arm within a piece, altered BPM/score/assessment revision,
unrecorded/unequal training exposure, and synthetic/nonphysical results.

## How to run

```bash
cd ~/Projects/piano_teacher
# Choose a private random secret, do not put it in the repository.
read -rs CODA_STUDY_RANDOMIZATION_SECRET
export CODA_STUDY_RANDOMIZATION_SECRET
python scripts/evaluate_coda_pedagogy.py assign \
  --anonymous-subject 'opaque-01' --piece-fingerprint 'piece-sha'
python scripts/evaluate_coda_pedagogy.py analyze \
  --input /private/study-observations.json \
  --output /private/analysis-blinded.json
```

The study observations JSON wraps the array with
`{"protocol":"coda-pedagogy-fixed-performance-pilot-v1","observations":[...]}`.

**Research status:** this is an independently auditable evaluation
instrument, not proof of better pedagogy. An actual study requires
participant recruitment, consent, controlled intervention delivery,
blinded analysis, retention follow-up and transparent adverse/missing
data reporting. No human-outcome results currently exist.

## Separately verified software safety

`piano_teacher/research/coda_live_note_audit.py` verifies the generated
application stages independently of the author code: all emitted source
note IDs, pitch, track, hand and channel identity, signed source indices,
transformed rhythm flags, tempo slowdown, canonical grading expected
seconds, and complete unchanged terminal performance.

The bounded CI runs it against all **16** independent MIDI cases:
**134 stages audited, zero rejected cases** in
[run 41459002790](https://github.com/tpepels/piano_teacher/actions/runs/41459002790).
The detailed per-stage JSON is retained as a GitHub Actions artifact.
That is **production MIDI event-contract coverage**, not original
MusicXML note-for-note parity, nor a human learning result.

The original Coda MusicXML source differential is already pinned under
[the research parity report](research-coda-supported-parity-2026-11-01.md).
The author returns `None` and sometimes malformed/disconnected ties
for cases that cannot safely be made into a MIDI lesson. It is not
appropriate to label those unsafe outputs as production targets.
