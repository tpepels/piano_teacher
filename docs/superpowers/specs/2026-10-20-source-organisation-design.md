# Source organisation for native notation development

Status: implemented on integration branch `integrate-native-source-20261020`
(PR #15), pending final CI validation and merge to `main`.

The package boundaries and native-first loading described in this design have
been implemented. The original implementation in PR #13 was reconciled with
subsequent source-Verovio fragment, native feedback, collision-spacing and
art-direction changes already on `main`. The legacy PNG renderer remains a lazy
fallback or an explicit `PIANO_TEACHER_RENDERER=legacy` compatibility mode.
Full source MusicXML is retained during import and preprocessing; preserving
every expression when compiling simplified exercises remains separate work.

The findings and migration plan below record the *pre-refactor* codebase and
historical decisions, rather than describing current source file ownership.

## Intent and constraints

Reorganise the existing source into cohesive packages, split mixed responsibilities,
and reduce coupling while native notation development continues. The legacy
Verovio page renderer remains available until the native engine is complete.
This is a behaviour-preserving refactor: preserve source-note identities, score
schemas, HTTP routes, launch commands, cache identities, timing, grading, and
renderer fallback decisions. Add no runtime dependencies.

The native renderer still uses Verovio font outlines and extracted engraving
fragments. Removing the page renderer must not accidentally remove those assets.
Replacing that asset dependency is a separate future project.

## Findings

- `score.py` mixes MIDI/MusicXML import, Verovio setup, page engraving, and
  repeated-header policies. Its private toolkit helpers are used by native assets.
- `xml_import.py` imports `_barline_data` from `score_model.py`, pulling semantic
  score construction into source import for a shared XML parsing operation.
- `server.py` is 2,162 lines. `PracticeEngine` owns application state as well as
  lesson compilation, page/cache preparation, rasterisation, and native asset
  response assembly. `geometry()` reconstructs notation for fragment extraction.
- `score_native_notation.gd` is 1,089 lines and combines score indexing,
  completeness validation, layout calculations, and painting. It inherits its
  transport integration from the diagnostic timeline preview.
- Python tests import existing module paths and patch symbols on `server`.
  Godot tests and scripts also refer to resource paths directly. These are
  migration constraints, not reasons to retain misplaced implementations.

## Approach

Recommend explicit packages by responsibility, with small compatibility facades
during migration. A directory-only move would preserve the coupling. Replacing
both rendering pipelines with a new plugin framework would expand scope and risk
unfinished native work. Use concrete collaborators and existing data contracts.

## Python boundaries

```text
piano_teacher/
  music.py                    existing public musical data types
  importing/
    pieces.py                 import_piece and optional music21 adapter
    musicxml.py               source XML import
  notation/
    musicxml.py               shared divisions and barline parsing
    lesson.py                 lesson MusicXML compilation
    model.py                  semantic score construction and schema
    assets/
      runtime.py              Verovio toolkit/font resource setup
      glyphs.py               preparation and native glyph catalogues
      notes.py, chords.py, ties.py
      beams.py, tuplets.py, slurs.py
      svg.py                  common fragment isolation/transform helpers
  rendering/
    legacy/
      engraving.py            full-page Verovio rendering
      geometry.py             page SVG geometry and beat lookup
      spacing.py              legacy MusicXML spacing policy
      raster.py               SVG-to-PNG adapter
  application/
    score_preparation.py      notation/model/layout/assets orchestration
  transport/
    http.py                   Handler and HTTP server launch
  server.py                   PracticeEngine, main entry and compatibility exports
```

`importing` and the semantic model depend on music types and shared MusicXML
parsing, never on page rendering or glyph assets. Expose `parse_barline` publicly
in `notation.musicxml`; do not make importers consume private builder functions.
The shared module has standard-library dependencies only.

Native assets depend on the Verovio runtime and shared SVG utilities, never on
the legacy engraving entry point. Fragment extractors accept rendered pages as
data: their current need for page extraction remains explicit. Move genuinely
shared SVG helpers out of an individual tuplet extractor instead of making slur
extraction depend on tuplet extraction.

Score preparation accepts the selected phrase, piece metadata, hand, revision,
BPM and existing cache adapter. It builds one lesson notation object per
preparation operation and shares its semantic model across fragment extractors.
It owns response assembly and preserves current extraction error handling.
`PracticeEngine` retains locks, revision decisions, pending-rewind semantics and
cache invalidation triggers; collaborators must not inspect the entire engine.
Do not introduce a second cache or change persisted cache namespaces.

Keep old public imports as explicit, thin facades where callers need them.
Migrate internal imports to the owning packages. Avoid wildcard re-exports,
`sys.modules` aliases, and two copies of implementation. Update tests to patch
the collaborator used by the caller; retain tests for documented compatibility
imports. The Qt entry point and `python -m piano_teacher` keep their behaviour.

## Godot boundaries

Group score code under `godot/notation/{shared,native,legacy,diagnostics}/`.
Move files with their `.gd.uid` companions and update every preload, extends,
test fixture and script reference. Keep third-party addons untouched.

`shared` owns the semantic timeline and common score view transport state.
Extract that transport base from `score_timeline_preview.gd`; native and diagnostic
views inherit it independently, preserving method signatures and clock ownership.
Keep legacy strip motion helpers under `legacy` when they use page coordinates;
only helpers actually used by both engines belong in `shared`.

Split the native compositor into a view that issues drawing calls, a score index
that owns event/chord/beam/tie/slur lookup and completeness checks, and focused
layout helpers for barlines and note/chord/beam placement. Existing notation
geometry and exact spacing remain separate collaborators. Keep texture and asset
loading outside the semantic index. Pass explicit model/geometry values rather
than the whole view. Preserve visible-event culling and all paint ordering.

Do not reorganise all of `main.gd` or the lesson state machine in this change.
Update their imports and integration points only. Broader UI decomposition can
follow once notation boundaries are stable.

## Migration and validation

1. Establish Python/Godot test baselines and record pre-existing failures.
2. Extract shared MusicXML parsing and importer/package boundaries; verify source
   fidelity and renderer-free semantic model imports.
3. Separate native asset runtime/helpers from legacy rendering; run real glyph,
   fragment, geometry, raster and resource tests.
4. Extract score preparation and HTTP adapter; verify HTTP error handling,
   revision/BPM caches, pending retries, and native extraction fallback payloads.
5. Move Godot resources, extract the shared view and native collaborators; run
   parser checks and native spacing, barline, beaming, tuplet and fallback tests.
6. Run the full Python suite and `scripts/check_godot.sh`; inspect the final diff
   for stale paths, duplicate implementations and reversed dependencies. Update
   `docs/architecture-score-model.md` with the final module ownership map.

Add focused regression coverage for renderer-free imports and new collaborators
where existing tests do not exercise these boundaries. Preserve the musical
fidelity corpus and real native fixtures as behaviour checks. Compilation alone
does not establish visual equivalence; compare native fixture output at existing
supported viewport sizes and check legacy fallback still loads.

## Completion criteria

Both engines continue to work through existing APIs. Native modules no longer
import legacy orchestration to create toolkits or obtain fonts. Source import
does not depend on the semantic builder. HTTP routing and asset assembly no
longer live inside the practice state machine. Native score indexing and layout
can be understood and exercised separately from drawing. Every moved resource
has updated references, and the final test report distinguishes passing checks,
existing failures and any unverified desktop behaviour.
