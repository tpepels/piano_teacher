# Production piano fingering implementation plan

> **For agentic workers:** Use superpowers:executing-plans for implementation and dispatch independent backend/native view work in parallel.

**Goal:** Real local Lumikey predictions, stored once per original piece and displayed consistently throughout its lesson path, with permanent corrections.

**Architecture:** A provider-neutral plan and atomic store operate on original `Piece.notes` and canonical source IDs. The Lumikey adapter invokes the supported published JavaScript inference against bundled ONNX weights on CPU. The backend projects the stored plan into native notation events; the existing score view draws and edits those assignments.

**Tech stack:** Python, Node.js, @lumikey/piano-fingering-model 0.3.0, onnxruntime-node 1.30.0, Godot native notation.

**Spec:** User attachment `/home/tom/.codex/attachments/7df5266a-71f2-4180-8b44-815ba786fdcf/Pasted text.txt`.

## Constraints

- Work directly on main; preserve archive branches and preservation bundle.
- Whole original piece, both hands, stable source IDs; never infer lesson variants.
- Manual > authored XML > automatic; fixed constraints remain fixed.
- No heuristic fallback or fabricated predictions; unknowns include reasons.
- Local offline runtime; pinned dependencies, weights, licensing metadata and hashes.
- Focused tests and fast CI only; no full corpus audit.

## Review focus

- Dense overlapping voices: distinct keys cannot occupy one finger; impossible constraints are reported.
- Equal-pitch notes: retain separate identities, allow a physical shared key where appropriate.
- Corrupt cache or missing runtime: recover safely and report unavailable automatic assignments.
- Ties and XML fingering substitutions: never invent a new attack or silently flatten ambiguous annotations.
- Manual edits during playback/load: persist atomically and invalidate score caches safely.

## Tasks

- [x] Provider/core: tests first for actual ONNX inference, constraints, identity, persistence and failure handling. Add `piano_teacher/fingering/{types,lumikey,service,projection}.py`, Node bridge and locked runtime dependencies. Add Piece plan field and authored XML extraction.
- [x] Backend: integrate `FingeringService(directory).prepare(piece,fingerprint)` at original import, attach via `replace(piece,fingering_plan=plan)`. Add `correct(piece,fingerprint,source_id,finger)` and `/fingering` API, project via `project_model(model,plan)` and refresh score revisions. Test restarts, variants and grading invariance.
- [x] Native score: draw event `fingering={finger,hand,source_id,origin}` in the existing continuous view. Add a small right-click correction popup, route POST `/fingering`, and framebuffer regressions for collision avoidance, ties and scrolling.
- [x] Validate whole real Hanon, Chopin and Bill Evans pieces with the installed provider; verify all lesson projections, fixed constraints and cache reuse. Document measured results and setup.
- [x] Run focused tests and fast CI; independent review, address findings, commit/push main, inspect status/worktrees and prune newly abandoned entries.

## Interfaces

`Piece.fingering_plan: FingeringPlan | None` (default None). `FingeringPlan.summary() -> dict` includes status, provider/model version, counts and error. `FingeringPlan.assignments` maps canonical source IDs to assignments. `project_model(model:dict,plan:FingeringPlan|None)->dict` returns projected model, assigning only attack events. `FingeringService.prepare(piece:Piece,fingerprint:str)->FingeringPlan`; `correct(piece,fingerprint,source_id,finger:int|None)->FingeringPlan` saves/rebuilds the complete piece. None removes a manual override. Provider errors become honest unknown assignments rather than invented fingers. Backend state exposes `fingering=plan.summary()`.
