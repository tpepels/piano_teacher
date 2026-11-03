# Native Notation Consolidation Implementation Plan

**Goal:** Make the existing Verovio/native comparison the single comprehensive notation command, with native Godot as the only production display renderer.

**Architecture:** Retain the independent MIDI and MusicXML readers, actual Godot capture harness, Verovio outlines and pixel mutation tests. Enumerate source measures and actual curriculum stages before running them. Bind semantic and visual checks to the same generated score; keep unresolved symbols explicit and make incomplete required checks fail.

**Constraints:** Work on `main`; commit verified changes. Preserve local MCP/editor configuration. Allow valid spacing, scaling and voice-lane choices. Never omit silent measures, source attacks, difficult scores or unresolved symbols to obtain a pass.

## Tasks

- [ ] Consolidate corpus discovery, window/curriculum enumeration and semantic/visual validation in the existing overlay command. Add regressions for omitted MIDI files, silent windows, carries at boundaries, variant source selection and incomplete visual evidence.
- [x] Remove production legacy renderer selection and fallback; migrate focused tests to the production native view.
- [x] Improve independent rest classification using staff-relative placement; keep image erasure, displacement, duplicate-identity and uncontrolled-frame mutations.
- [x] Replace overlapping notation workflow orchestration with one canonical requirement; retain independent algorithmic regression checks.
- [ ] Finish source-bound connector/ledger integration and evidence for unexpected symbols; preserve explicit unknowns and fix actual engraving defects.
- [ ] Run focused checks, the Python suite, Godot validation and the canonical corpus test. Investigate genuine engraving defects and retain diagnostic frames for unresolved cases.
- [ ] Review the complete change, commit completed fixes and record actual verification and remaining unsupported notation.

## Review focus

Incoming sustained notes at capture boundaries; silent measures/hands; unchanged source identities through simplification; layout-independent glyph attachment and pitch; incomplete detectors never counted as verified.
