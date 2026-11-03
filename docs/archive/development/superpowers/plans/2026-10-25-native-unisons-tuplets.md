# Correct native unisons and retained Moonlight tuplets

Continue directly on main from 833e1d9. Scope is engraving algorithms and
independent pixel recognition; audit recovery infrastructure stays unchanged.

Design: preserve Verovio's existing authentic chord/note artwork and move an
entire colliding voice column, including its stems, beams and tie attachments.
Opposing compatible heads may share; hollow/filled heads must remain readable.
Register displaced contours from source-bounded search and actual PNG pixels,
retaining all score/family/visibility thresholds and exclusive ownership for
incompatible heads. Diagnose the Moonlight bracket separately against its
retained XML/SVG/PNG, correcting generic tuplet placement or pixel recognition
where the evidence identifies the defect.

- [x] Inspect main/worktrees; reproduce both existing actual unison failures.
- [x] Add mixed-head, shared-head and overlapping-chord positive and corrupted
  negative regressions, then fix column placement and pixel ownership.
- [x] Reproduce and fix Moonlight bracket with real-frame positive and erasure/
  detached/wrong-reference negatives; preserve existing tuplet behavior.
- [x] Verify focused chord/voice/tie/beam/tuplet scopes and fast CI only.
- [x] Review, commit and push main; inspect status/worktrees and preserve the
  intentional historical archive branches and external preservation bundle.

Parallel ownership: main owns unison directions/column offsets/chord and beam
attachments in view.gd plus feature_pixels.py. Fermat owns only tuplet painting
in view.gd, tuplet asset helpers, connector bracket proof and dedicated tests.
No full corpus run, infrastructure redesign or temporary worktree is needed.
