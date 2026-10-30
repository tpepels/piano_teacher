# Step 4 — exercise algorithms and adaptive remediation

Working branch: `main`. Short focused tests; no worktrees or broad corpus runs.

## Gates

- [ ] 4.1 Extract transparent difficulty features and a replaceable estimator.
      Keep the heuristic default honest; no claimed pretrained RubricNet model.
- [ ] 4.2 Extend Coda-style part splitting into progressive source-valid
      stages; add guarded chordification as a separate rhythm strategy.
- [ ] 4.3 Improve Fukuda source-safe simplification, applying musical groups
      and preserving complete source on the final stage.
- [ ] 4.4 Turn consecutive assessed errors into a bounded actual remediation
      route using existing exercise/guided paths. Keep partial results from
      awarding mastery and retain student navigation/control.
- [ ] 4.5 Add exact-source, mixed-voice, recovery, progress and Godot
      regressions; run a short CI gate and report unsupported research areas.

## Invariants

- Every exercise maps to imported note identities and valid source bars.
- Remediation only follows actual assessed MIDI takes; never preview/Listen.
- The original stage must still be graded independently for mastery.
- No stage-key migration, destructive progress reset, or background jobs.
- Policy baselines remain selectable; "repeat-only" must not remediate.
- Unavailable trained research models must not be misrepresented as implemented.
- No multi-minute corpus audit or worktrees.
