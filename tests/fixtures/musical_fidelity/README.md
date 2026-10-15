# Musical fidelity corpus

There are 26 supported real files (16 MIDI, 10 MusicXML) and four deliberately
unsupported files. `manifest.json` records independently authored source facts:
quarter-beat attack/release times, MIDI pitches, hands, measure boundaries,
explicit meter/key/spelling and a few register/continuation expectations. Fraction
strings retain exact intended PPQ/tuplet values. Expected events are never read
back from the importer or engraving to construct their own assertions.

The small sources cover 4/4, 3/4, 6/8, changing meters, explicit pickup, chords,
repeated attacks, separate-track and cross-hand unisons, overlapping tied voices,
chord ties, initial/internal/trailing rests, unknown and explicit MIDI keys,
MusicXML key changes and flats, crossed named hands, grand-staff voices, unusual
hand registers, triplets, quintuplets and PPQ 997. The 48-bar MusicXML contains
240 attacks and must produce more than one actual Verovio page.

`generate.py` recreates the source bytes deterministically using only explicit
source instructions and `mido`; it does not import the application or write the
manifest. Both the generated sources and the manifest are checked in. Regenerate
only when deliberately editing source material, then review the manifest
independently.

The tests import every supported file and pass every generated hand/variant
through the production lesson compiler and Verovio. They check unique stable
source IDs, unchanged precise source events, exactly one mapped attack per
required event, ties attached to that attack, actual SVG IDs/coordinates, real
evaluation and feedback on those same IDs, metadata and readable clefs. Distinct
feedback statuses are also assigned to simultaneous unisons so a pitch/onset
heuristic cannot silently swap their staff or voice. Representative actual SVGs
are rasterized to PNG and checked for visible score ink. The unsupported files
must report orphan ties, microtones, unterminated MIDI notes and ambiguous MIDI
overlaps explicitly.

From the Phase 2A checkout on Arch Linux with its normal project environment:

```sh
PYTHONPATH="$PWD" .venv/bin/python -m pytest -q tests/test_musical_fidelity_corpus.py
PYTHONPATH="$PWD" .venv/bin/python scripts/check_musical_fidelity_corpus.py --output /tmp/piano-phase2a-corpus
PYTHONPATH="$PWD" .venv/bin/python tests/fixtures/musical_fidelity/generate.py
git diff -- tests/fixtures/musical_fidelity
```

The artifact command retains a `report.json` and real PNGs, including every page
of the long score. `--fixture xml_parallel_tied_voices.musicxml` selects one
source. These are software engraving checks; they require the project's real
Verovio/raster dependencies and do not make a physical MIDI or audio claim.

Before the implementation, the new tests produced **40 failures and 17 passes**
in 0.61 seconds. Nine source-fact cases exposed existing import loss/corruption;
26 complete pipelines lacked canonical identity, all four unsupported sources
were silently accepted, and path-independent source identity was absent. The
earlier actual SVG/PNG baseline is in `/tmp/piano-phase2a-corpus-audit` for this
session, including the lost pickup/trailing measures, swapped tied voices,
flattened key/spelling and forced bass clef. Its old pitch/onset alignment check
passed all 13 probes despite those defects.
