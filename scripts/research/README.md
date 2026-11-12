# Research scripts

Explicit local commands, not CI jobs and not part of lesson startup.

- `export_coda_midi_godot_model.py`: exports a real later-measure MIDI-Coda
  score model for Godot smoke tests (a Python-to-Godot semantic boundary
  probe; it does not launch the app or use MIDI hardware).

## Removed: RubricNet and the other exercise strategies

Owner decision 2026-11-11: the app offers one exercise strategy, adaptive
Coda + Fukuda (`coda-fukuda-midi`). The RubricNet reproduction (vendored
upstream extractor, bundled folds, export/parity/CIPI tools and the
`rubricnet-trained` strategy) was removed together with the `fukuda`,
`coda-part`, `feature-gated`, `fukuda+coda-part`, `coda-midi` and
`fukuda-midi` strategies and the separate rhythm and tempo strategy axes.
The history is in git (removal commit on 2026-11-12) and in
`docs/archive/reports/research-reproduction-gate-1.md`.
