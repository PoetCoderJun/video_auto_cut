# PI Runner + Three Skills Implementation PRD

**Date:** 2026-04-14  
**Scope:** `video_auto_cut` current repo only  
**Goal:** Replace the current chunk-first / repair-first PI auto-edit path with one clean PI runner and only three editing skills: `delete`, `polish`, `chapter`.

---

## 1. Problem Statement

The current Test editing path is not cleanly decoupled:

- `video_auto_cut/editing/auto_edit.py` is a god-object-like orchestrator.
- Main path is chunk-first (`pi_agent_chunking.py`, `pi_agent_merge.py`, boundary reconciliation).
- `pi_agent_remove.py`, `pi_agent_polish.py`, `pi_agent_boundary.py` each own explicit JSON prompt + fallback repair logic.
- `web_api/services/test.py` and `web_api/services/step2.py` still own part of the editing/chapter semantics.
- `video_auto_cut/orchestration/full_pipeline.py` is stale and not a trustworthy direct-run seam.

The desired end state is:

- one clean PI runner
- only three editing skills: `delete`, `polish`, `chapter`
- one shared system prompt for global task framing
- no default chunk-first orchestration
- no explicit JSON repair/fixup prompt chain
- backend becomes wrapper only

---

## 2. Product / Architecture Goals

### Must have
- One canonical Test execution seam.
- Three frozen task contracts: `delete`, `polish`, `chapter`.
- Shared system prompt for the overall editing mission.
- Preserved structured artifacts needed for:
  - Test preview
  - `test.json`
  - chapter correctness
  - export downstream use
- Shared chapter invariants outside `web_api`.

### Must not
- No new compatibility layer / facade stack.
- No plugin-style framework.
- No default chunk-first orchestration.
- No explicit JSON repair/fixup prompt branching as production architecture.
- No dual chapter path.

---

## 3. End-State Design

## 3.1 Canonical seam

Create one canonical direct-run seam in `video_auto_cut`, e.g.:

```python
run_test_pi(request: TestPiRequest, hooks: TestPiHooks | None = None) -> TestPiArtifacts
```

This seam is the only real Test producer.

All of these must call it:
- backend Test flow
- CLI/direct-run flow
- any skill wrappers

## 3.2 Task contracts

Only three task types exist:

```python
Literal["delete", "polish", "chapter"]
```

### `delete`
Purpose:
- remove redundant / invalid / repeated content

Input:
- source transcript lines
- optional user constraints

Output:
- per-line keep/remove decision
- updated line text only when task contract allows it
- lineage to source lines

### `polish`
Purpose:
- improve expression while preserving semantic intent and line mapping

Input:
- kept lines from delete stage
- optional user style constraints

Output:
- polished line text
- preserved line IDs / lineage

### `chapter`
Purpose:
- produce chapter segmentation and titles over validated Test lines

Input:
- final Test lines
- optional chapter constraints

Output:
- chapters with titles and block coverage
- validated chapter structure

## 3.3 Shared system prompt

One shared system prompt defines:
- the full editing mission
- the relationship between delete / polish / chapter
- safety rules
- style rules
- output discipline

Task-specific instructions should be thin overlays only.

## 3.4 Structured artifacts

Even without chunk-first design, the runner must preserve artifact lineage.

Required artifacts:
- `optimized.srt`
- `test.json`
- preview-ready line structure
- chapter-ready line/block structure
- debug metadata sufficient for verification

## 3.5 Chapter invariant ownership

Move these out of `web_api/services/step2.py` into shared domain / canonical runner support:
- `canonicalize_test_chapters(...)`
- `ensure_full_block_coverage(...)`

Backend should consume validated chapter output, not define correctness.

## 3.6 TopicSegmenter decision

There must be only one production chapter path.

Choose one of these during implementation:
1. `chapter` task wraps the existing `TopicSegmenter` internally through the canonical seam.
2. `chapter` task replaces/absorbs `TopicSegmenter`.

Do **not** keep both as active production paths.

## 3.7 Validation strategy

“No repair prompts” does **not** mean “no structure enforcement.”

Allowed strategy:
- constrained output format or structured output
- schema validation
- deterministic parser
- fail-fast on invalid output
- optional bounded retry using same contract

Not allowed:
- special repair prompts
- prompt-branch fixup pipeline
- hidden parser fallback tree as architecture

## 3.8 Overflow policy

Default path is not chunk-first.

But oversized input needs an explicit policy:
- default: fail-fast with a clear limit/error
- optional non-default fallback: explicitly documented and isolated

Do not treat “larger model” as infinite-context architecture.

---

## 4. Implementation Workstreams

### Workstream A — Freeze contracts
**Goal:** define stable request/response schemas before refactor.

Deliverables:
- `TestPiRequest`
- `TestPiArtifacts`
- task-specific contract docs for `delete` / `polish` / `chapter`

Candidate paths:
- `video_auto_cut/editing/pi_runner_types.py`
- `docs/plans/2026-04-14-pi-runner-three-skills.md` (this doc)

Acceptance:
- task contracts reviewed and fixed before moving logic

---

### Workstream B — Build canonical runner seam
**Goal:** create the only real Test PI execution path.

Deliverables:
- `run_test_pi(...)`
- `TestPiHooks` for side-effect-only progress/preview hooks

Candidate paths:
- `video_auto_cut/editing/pi_runner.py`
- `video_auto_cut/editing/__init__.py`

Acceptance:
- direct-run path can invoke delete / polish / chapter through one seam
- hooks remain optional and side-effect-only

---

### Workstream C — Replace chunk-first main path
**Goal:** demote chunking/merge/boundary logic from default production ownership.

Deliverables:
- `auto_edit.py` no longer acts as canonical owner
- chunk modules are removed from default main path

Candidate paths:
- `video_auto_cut/editing/auto_edit.py`
- `video_auto_cut/editing/pi_agent_chunking.py`
- `video_auto_cut/editing/pi_agent_merge.py`
- `video_auto_cut/editing/pi_agent_boundary.py`

Acceptance:
- default production path does not route through chunk-first orchestration

---

### Workstream D — Unify prompt strategy
**Goal:** move framing into one shared system prompt.

Deliverables:
- one shared prompt template
- thin task overlays only

Candidate paths:
- `video_auto_cut/editing/pi_runner_prompt.py`
- existing PI prompt builders refactored or removed

Acceptance:
- no more separate repair/fixup prompt flow
- task-specific overlays are thin and validator-backed

---

### Workstream E — Validation and parsing
**Goal:** replace repair-prompt-centric architecture with explicit validation.

Deliverables:
- one structure-guarantee strategy
- shared parser/validator layer
- fail-fast policy

Candidate paths:
- `video_auto_cut/editing/pi_runner_validation.py`
- task-specific validators if necessary

Acceptance:
- invalid output fails clearly
- no prompt-repair branching needed

---

### Workstream F — Chapter ownership cleanup
**Goal:** unify chapter path and move invariants out of backend.

Deliverables:
- shared chapter invariant module
- `chapter` task wired to one production path only

Candidate paths:
- `video_auto_cut/editing/chapter_domain.py`
- `video_auto_cut/editing/topic_segment.py` or replacement
- `web_api/services/step2.py`

Acceptance:
- backend no longer defines chapter correctness
- no dual chapter path remains

---

### Workstream G — Rewire wrappers
**Goal:** make backend / CLI wrappers only.

Deliverables:
- `full_pipeline.py` becomes thin wrapper or is replaced
- `pipeline_service.py` calls canonical seam
- `web_api/services/test.py` only wraps and persists

Candidate paths:
- `video_auto_cut/orchestration/full_pipeline.py`
- `video_auto_cut/orchestration/pipeline_service.py`
- `web_api/services/test.py`
- `web_api/services/step2.py`

Acceptance:
- one real path only
- no wrapper owns editing semantics

---

## 5. Task Breakdown

## Phase 0 — Contract freeze
1. Define `TestPiRequest` schema.
2. Define `TestPiArtifacts` schema.
3. Define canonical request/response schema for:
   - `delete`
   - `polish`
   - `chapter`
4. Decide and document overflow policy.
5. Decide and document structure-guarantee strategy.
6. Decide and document `TopicSegmenter` integration strategy.

## Phase 1 — Canonical seam
7. Add `video_auto_cut/editing/pi_runner.py` with `run_test_pi(...)`.
8. Add hooks contract for progress/preview.
9. Add shared prompt module.
10. Add validator/parser module.

## Phase 2 — Migrate editing tasks
11. Route `delete` through canonical seam.
12. Route `polish` through canonical seam.
13. Route `chapter` through canonical seam.
14. Preserve line/block lineage in returned artifacts.
15. Produce `optimized.srt` and `test.json` from canonical artifacts.

## Phase 3 — Backend/domain cleanup
16. Move chapter invariants out of `web_api/services/step2.py`.
17. Update `web_api/services/test.py` to consume canonical artifacts only.
18. Remove editing semantic ownership from backend path.
19. Fix `editing/__init__.py` eager import pollution.
20. Replace or thin-wrap `full_pipeline.py`.

## Phase 4 — Demote old path
21. Remove chunk-first path from default production route.
22. Mark old chunk/repair modules as non-owner or delete them if safe.
23. Remove duplicated parse-fallback logic from main path.
24. Ensure no dual path remains for chapter generation.

## Phase 5 — Verification and docs
25. Add direct-run smoke tests for the 3 tasks.
26. Add invariant tests for chapter coverage.
27. Add parity tests for backend wrapper vs direct-run seam.
28. Update README / docs if entrypoints or terminology change.

---

## 6. Acceptance Criteria

### Architecture
- Exactly one canonical Test PI seam exists.
- Only three editing task contracts exist: `delete`, `polish`, `chapter`.
- Backend / CLI / skill wrappers all call the same seam.
- Default production path is not chunk-first.
- Main path does not rely on explicit repair/fixup prompts.

### Correctness
- `test.json` still contains enough lineage for preview and chapter correctness.
- `optimized.srt` remains producible from canonical artifacts.
- chapter invariants are enforced outside `web_api`.
- `TopicSegmenter` and `chapter` do not coexist as dual production paths.

### Operability
- Direct-run CLI works for all 3 tasks.
- Overflow policy is explicit.
- Invalid structured output fails predictably.
- Hooks do not leak backend semantics into the seam.

---

## 7. Verification Plan

### Direct-run smoke
```bash
python -m video_auto_cut.<canonical_module> --input test_data/<fixture> --task delete
python -m video_auto_cut.<canonical_module> --input test_data/<fixture> --task polish
python -m video_auto_cut.<canonical_module> --input test_data/<fixture> --task chapter
```

### Backend parity
- backend Test path and direct-run seam produce equivalent:
  - `optimized.srt`
  - `test.json`
  - validated chapter coverage semantics

### Existing test suite baseline
```bash
python -m unittest discover web_api/tests -p "test_*.py"
cd web_frontend && npx tsc --noEmit
npm --prefix web_frontend run build
```

### New tests to add
- `web_api/tests/test_pi_runner_contracts.py`
- `web_api/tests/test_pi_runner_direct_run.py`
- `web_api/tests/test_chapter_invariants_shared.py`
- `web_api/tests/test_backend_test_wraps_canonical_runner.py`

---

## 8. Risks and Guardrails

### Risk 1: God-runner
Guardrail:
- keep validators / invariants / artifact builders separate from orchestration

### Risk 2: Loss of lineage
Guardrail:
- `TestArtifacts` schema must explicitly preserve line/block lineage

### Risk 3: No-repair becomes no-safety
Guardrail:
- choose validator strategy first, not later

### Risk 4: Fake direct-run seam
Guardrail:
- there can be only one production path; wrappers only wrap

### Risk 5: Hidden dual chapter path
Guardrail:
- make `TopicSegmenter` relationship explicit before migration

### Risk 6: Implicit infinite-context assumption
Guardrail:
- document overflow policy and test it

---

## 9. ADR

**Decision**  
Adopt a thin-contract refactor around one canonical Test PI seam, with only three editing tasks: `delete`, `polish`, `chapter`.

**Drivers**  
- one real execution path
- runner/skill/backend decoupling
- preserved artifact lineage and chapter correctness
- no default chunk-first / repair-prompt-first design

**Alternatives considered**
- patch the current chain incrementally
- build a larger god-runner around one huge prompt
- keep dual chapter and backend invariant ownership

**Why chosen**
- smaller patch is not clean enough
- god-runner is too risky
- dual ownership keeps the system muddy
- this approach is the minimum clean rewrite with testable boundaries

**Consequences**
- medium refactor
- old chunk/repair modules lose production ownership
- backend becomes thinner
- chapter correctness moves to shared domain

**Follow-ups**
- finalize task contracts
- finalize validation strategy
- finalize `TopicSegmenter` unification choice
- implement and verify direct-run seam
