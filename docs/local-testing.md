# Local testing

From the checkout:

```bash
git pull --ff-only
bash scripts/verify.sh
```

The default runs the full Python/Godot regression, native repertoire and relocated-package audit, full 30 FPS pixel capture and lightweight 60 FPS pacing capture. No tests are silently skipped after a failed independent suite. The final status is nonzero if any suite or report archive fails. The output identifies one ZIP to upload. No real learner HOME is used by the native journeys. The runner does not pull or modify the checkout.

Optional `--quick` runs regression and Godot behavior checks only; `--visual` runs both rendered suites only. Neither is equivalent to full acceptance. `PIANO_TEST_RESULTS` selects the report directory. `PIANO_PATHETIQUE_II_MIDI` supplies the optional original external MIDI source. Existing Python, Godot, soundfont and Xvfb requirements still apply.

The full native verifier includes the package audit, so no separate package-build step is required. Raw captures are retained only when `PIANO_KEEP_VISUAL_CAPTURE=1` is explicitly requested.
