# B Batch (B1-B6) Non-Interactive RALPLAN Draft

## Requirements Summary
- Produce a plan-only, consensus-ready execution blueprint for `docs/requirements_todo.md` batch B (`B1`-`B6`) with no implementation in this round.
- Respect the user-provided dependency guidance: prioritize **B1/B4/B5 low-risk convergence**, then **B2/B3 contract reshaping**, then **B6 architecture review/ADR**.
- Refine batching for reversibility: split **B4** into helper-dedupe vs OSS-factory work, and split **B3** into sentence-boundary specification vs `Cutter`/ffmpeg cleanup.
- Treat current dirty working tree as a hard constraint: the output must be decomposed into minimal, reviewable commit batches for later execution.
- Clarify branch state: repository inspection shows current branch is `work/2026-04-16-d-batch-ralplan`, which differs from the user-mentioned `work/2026-04-16-b-batch-ralplan`.

## Grounding
- Backlog source for B1-B6: `docs/requirements_todo.md:26-31`.
- B1 grounding:
  - Web ASR path hard-locks `dashscope_filetrans`: `video_auto_cut/asr/transcribe.py:22-30`.
  - Runtime config rejects other backends: `web_api/config.py:137-141`.
- B2 grounding:
  - `auto_edit` loads SRT/JSON into segment dicts, calls PI delete/polish stages, then rebuilds subtitles/EDL/debug payloads: `video_auto_cut/editing/auto_edit.py:25-69`, `123-165`.
  - PI runner still converts between timed-text protocol, line dict payloads, chapter lines, subtitles, and EDL while carrying `<<REMOVE>>`: `video_auto_cut/pi_agent_runner.py:120-160`, `305-370`, `398-424`, `532-570`.
  - Shared line DTO is also built/read in `web_api/utils/srt_utils.py:58-142`, `168-200`, mirrored by `video_auto_cut/asr/transcribe_stage.py:17-82`, and partially validated at API confirm time in `web_api/schemas.py:15-39`.
- B3 grounding:
  - Sentence splitting state machine sits in `DashScopeFiletransClient._split_by_words`: `video_auto_cut/asr/dashscope_filetrans.py:225-341`.
  - `cut.py` helpers `filter_kept_subtitles` / `build_merged_segments` remain reusable and are consumed by `cut_srt`: `video_auto_cut/rendering/cut.py:31-73`, `85-135`; `video_auto_cut/rendering/cut_srt.py:120-147`.
  - Pipeline topic segmentation currently depends on `build_cut_srt_from_optimized_srt`, not on `Cutter.run`: `video_auto_cut/orchestration/pipeline_service.py:243-257`.
  - `video_auto_cut/rendering/__init__.py:1-3` still exports `Cutter`, so any B3b cleanup must include export/import audit.
- B4 grounding:
  - Duplicated temporal/row helpers exist in `web_api/repository.py:58-85` and `web_api/task_queue.py:19-33`, `79-89`.
  - DB compatibility shims `_extract_column_names` / `_executescript` are in `web_api/db.py:36-55`, `244-253`.
  - Similar succeeded-job listing loops are in `web_api/repository.py:1041-1094`.
  - OSS uploader construction is duplicated in `web_api/services/test.py:199-248`, `web_api/services/oss_presign.py:10-23`, `video_auto_cut/asr/transcribe.py:72-88`.
- B5 grounding:
  - Shared JSON extraction/repair path already exists in `video_auto_cut/editing/llm_client.py:238-353`.
  - `topic_segment` still wraps local `_strip_code_fence` / `_json_loads` before falling back to `request_json`: `video_auto_cut/editing/topic_segment.py:206-259`, `331-351`.
- B6 grounding:
  - Durable queue schema is real and persistent: `web_api/task_queue.py:44-76`.
  - Lease/reclaim/heartbeat/claim logic already exists: `web_api/task_queue.py:116-193`, `261-340`.
  - Dispatcher and route only support `TASK_TYPE_TEST`: `web_api/services/tasks.py:20-22`, `65-72`; `web_api/api/routes.py:257-266`.

## RALPLAN-DR
### Principles
1. **Main-path first**: optimize around the current web/API production path, not orphaned historical modules.
2. **Contract before cleanup**: when multiple representations exist, define a canonical contract before deleting adapters.
3. **Low-risk convergence early**: extract safe shared helpers before touching workflow semantics.
4. **Architecture review over premature simplification**: B6 must preserve observed reliability properties unless a reviewed alternative proves better.
5. **Commit-sized reversibility**: each batch should be small enough to revert independently on a dirty baseline.

### Decision Drivers
1. **Blast radius on active flows** — B1/B2/B3 touch current transcription/edit/render path and need stronger grounding.
2. **Refactor leverage** — B4/B5 reduce duplication that otherwise complicates B2/B3 changes.
3. **Operational reliability** — B6 impacts queue durability, worker recovery, and route/task coupling.

### Options
#### Option A — Recommended: staged convergence then contract reshape then queue ADR
- Sequence: **B1 → B4a → B4b → B5** → **B2 + B3a** → **B3b** → **B6**.
- Pros: aligns with dependency graph; front-loads low-risk wins; keeps architecture review informed by cleaned contracts; improves commit reversibility on a dirty worktree.
- Cons: delays visible simplification of edit/cut flow until shared-helper work lands and adds one extra planning checkpoint between B3a and B3b.

#### Option B — contract-first: B2/B3 before helper dedupe
- Pros: reaches core media pipeline simplification earlier.
- Cons: higher diff churn; duplicates likely get moved twice; harder to isolate regressions while worktree is dirty.

#### Option C — queue-first: B6 before B1-B5
- Pros: surfaces long-term backend architecture early.
- Cons: weak evidence that queue is the current bottleneck; risks redesigning around pre-cleanup assumptions; violates user guidance.

### Recommended Decision
Choose **Option A**. It best matches the observed dependency chain and contains risk by separating safe consolidation from semantic pipeline changes and from the open-ended queue review.

## Acceptance Criteria
1. The plan defines an explicit execution order covering **all B1-B6 items** and explains why the order is dependency-safe.
2. Each batch is scoped to a **minimal shippable commit** with bounded touchpoints, rollback surface, and verification expectations.
3. B2/B3 steps define a **target canonical contract** for subtitle/edit/cut data before removal of adapters or protocol tokens.
4. B6 is framed as an **ADR-backed architecture review** with comparison criteria, not as a predetermined simplification task.
5. Verification includes required repo checks for impacted areas (`python -m unittest discover web_api/tests -p "test_*.py"`, `cd web_frontend && npx tsc --noEmit`, `npm --prefix web_frontend run build`) plus focused backend/manual checks where frontend is untouched.
6. The plan is executable later without reopening repo-discovery questions, aside from explicitly listed open questions.

## Implementation Steps
### Batch 0 — Pre-flight cleanup gate (planning handoff prerequisite)
- Snapshot current dirty worktree, confirm branch naming mismatch, and isolate future execution onto the intended work branch before code changes.
- Deliverables:
  1. Worktree inventory note for changed files.
  2. Confirmed execution branch strategy (`work/2026-04-16-d-batch-ralplan` vs requested `...b-batch...`).
- Acceptance notes: no code changes; execution can begin later without accidental overwrite.

### Batch 1 — B1 main-path ASR residue audit and removal plan
- Goal: remove or quarantine historical Qwen-local ASR modules only after proving they are off the active web/API path.
- Scope:
  - Verify references to `video_auto_cut/asr/qwen3_asr.py` and `scripts/qwen3_asr_transcribe.py`.
  - Delete or archive dead entrypoints; keep `filetrans_like.py` if still serving DashScope normalization.
  - Add/update tests only if stale imports exist.
- Commit boundary: one commit limited to ASR path cleanup and reference removal.

### Batch 2 — B4a safe dedupe: repository/task-queue helper convergence
- Goal: extract duplicated repo/task-queue helpers without changing queue or DB semantics.
- Intended shared home: a new `web_api/utils/persistence_helpers.py` owned by backend persistence code, so `repository.py` and `task_queue.py` can share helpers without pushing storage glue into `video_auto_cut`.
- Scope:
  - Consolidate ISO/row helpers for `repository.py` + `task_queue.py`.
  - Collapse similar succeeded-job listing traversal into one internal helper.
  - Leave `db.py` shims in place unless a compatibility wrapper can be proven behaviorally identical.
- Commit boundary: infra-only refactor, no queue model changes and no OSS factory movement yet.

### Batch 3 — B4b OSS uploader factory convergence
- Goal: centralize OSS uploader construction/config assembly for web/API + ASR callers while preserving prefixes and TTL behavior.
- Intended shared home: `video_auto_cut/asr/oss_uploader.py`, because both `web_api` and transcription code already depend on that package and this avoids introducing a new `web_api -> video_auto_cut -> web_api` utility loop.
- Scope:
  - Unify uploader initialization used by `web_api/services/test.py`, `web_api/services/oss_presign.py`, and `video_auto_cut/asr/transcribe.py`.
  - Keep call-site-specific prefix/object-key behavior explicit at the edge.
- Commit boundary: upload-config refactor only.

### Batch 4 — B5 LLM JSON helper unification
- Goal: make `llm_client` the single JSON-cleaning/repair authority and reduce `topic_segment` wrappers to validation/domain concerns.
- Scope:
  - Replace local fence/JSON parsing duplication with imports from `llm_client` or a dedicated editing JSON helper module.
  - Keep `topic_segment` validation/fallback semantics stable.
  - Verify `render_web` main path still exercises topic segmentation correctly.
- Commit boundary: editing-layer helper consolidation only.

### Batch 5 — B2 contract reshape for edit pipeline
- Goal: define a canonical **line-oriented edit contract** (`line_id/start/end/original_text/optimized_text/ai_suggest_remove/user_final_remove`) across delete/polish/chapter/build steps, with adapters only at ingress/egress.
- Intended source-of-truth owner: a neutral shared module under `video_auto_cut/editing/` (for example `line_contract.py` / `test_line_contract.py`), with `web_api/utils/srt_utils.py`, `video_auto_cut/asr/transcribe_stage.py`, `pi_agent_runner.py`, and API schema adapters delegating to it rather than each re-declaring the DTO.
- Canonical invariants:
  - `user_final_remove` is the sole authoritative downstream keep/remove field for chaptering, cut-SRT generation, final SRT export, and UI confirmation.
  - `ai_suggest_remove` is provenance from model/normalizer stages only; after delete-stage normalization it should be treated as advisory history, not final truth.
  - `optimized_text` may change in polish/user-confirm flows; `original_text` remains immutable after ingress normalization.
  - `<<REMOVE>>` survives only inside SRT/text export adapters and import parsers, not as an internal cross-module contract token.
- Scope:
  - Introduce the canonical line schema and normalization helpers in the designated shared owner module, then have PI runner/helpers import from there.
  - Refactor `auto_edit` to convert SRT/JSON input once into segments, then once into canonical lines, then derive SRT/EDL/debug from those lines.
  - Align related adapters/validators in `web_api/utils/srt_utils.py`, `video_auto_cut/asr/transcribe_stage.py`, `web_api/schemas.py`, and related tests so the same contract is enforced end-to-end.
  - Demote `<<REMOVE>>` from active cross-module protocol toward an edge-format artifact only if compatibility requires it.
- Commit boundary: semantic pipeline refactor with dedicated regression verification.

### Batch 6 — B3a sentence-boundary specification aligned to the canonical edit contract
- Goal: codify `dashscope_filetrans` sentence-boundary rules and their relationship to the post-B2 line contract before touching ffmpeg/cutter cleanup.
- Scope:
  - Review `_split_by_words` heuristics and freeze intended punctuation/pause/segment-cap behavior in focused tests or fixtures.
  - Confirm where sentence-split outputs enter the B2 canonical line model and document adapter expectations.
- Commit boundary: ASR boundary spec + targeted refactor only; no `Cutter` removal yet.

### Batch 7 — B3b cut helper / `Cutter` cleanup
- Goal: simplify cut orchestration only after Batch 5 and Batch 6 stabilize canonical line/segment boundaries.
- Scope:
  - Run a repo-wide `Cutter` import/export audit, including `video_auto_cut/rendering/__init__.py`, before deciding whether the class is legacy CLI-only, extracted, or removed.
  - Separate reusable `cut.py` helper functions from the possibly-dead `Cutter` execution shell.
  - Preserve `cut_srt` and `pipeline_service` behavior as the active path.
- Commit boundary: rendering cleanup only, with no change to topic-segmentation contract.

### Batch 8 — B6 queue architecture review + ADR (no default simplification)
- Goal: review whether the current durable lease-based queue should be extended, narrowed, or split, based on actual reliability requirements.
- Scope:
  - Document current invariants: persistence, lease recovery, heartbeat, claim fairness, task-type routing, and the coupled job-state transitions triggered by enqueue/execute/fail flows.
  - Treat the current success path as an explicit ADR invariant: `/jobs/{job_id}/test/run` + `queue_job_task` + worker `execute_task` + `run_test` currently drive `UPLOAD_READY -> TEST_RUNNING -> TEST_READY`, with failure/credit backedges preserved.
  - Compare at least two viable futures (retain durable queue with clearer abstraction vs split dispatch/runtime responsibilities; invalidate “replace with in-memory/simple table” if unsupported).
  - Produce ADR and optional follow-on implementation backlog, not mandatory code changes.
- Commit boundary: ADR/docs/requirements update only unless a later approved implementation plan is requested.

## Risks & Mitigations
- **Risk: dead-code removal breaks non-web scripts.**
  - Mitigation: exhaustive reference search before B1 deletion; if ambiguity remains, quarantine behind legacy path instead of immediate delete.
- **Risk: B4 helper extraction accidentally changes Turso/sqlite compatibility.**
  - Mitigation: avoid altering `db.py` semantics in the first dedupe pass; add regression checks around both local-only and Turso-capable codepaths where possible.
- **Risk: B2 canonical model refactor changes delete/polish/chapter semantics.**
  - Mitigation: freeze representative fixtures from current `.optimized.srt`, `.test.txt`, `.edl.json`, and chapter output before refactor; document which fields are allowed to change per stage and reject drift in keep/remove authority.
- **Risk: B3 oversimplifies sentence splitting and hurts subtitle readability.**
  - Mitigation: define sentence-boundary fixtures covering punctuation, pauses, and segment caps before code changes.
- **Risk: B6 redesign chases elegance over reliability.**
  - Mitigation: require ADR comparison against current lease/heartbeat behavior, operational failure modes, and route/worker/job-state coupling invariants.

## Verification Steps
- Global regression baseline before and after each implementation batch:
  - `python -m unittest discover web_api/tests -p "test_*.py"`
  - `cd web_frontend && npx tsc --noEmit`
  - `npm --prefix web_frontend run build`
- Batch-focused checks:
  - **B1**: repo-wide reference search for removed ASR modules; smoke transcription path using DashScope config only.
  - **B4a**: repository/task-queue unit coverage for helper outputs.
  - **B4b**: OSS presign/test upload smoke checks.
  - **B5**: malformed JSON/fenced JSON cases through topic segmentation path.
  - **B2**: freeze baseline artifacts from one short and one long representative input under `workdir/batch-b-baselines/{case}/` (`optimized.srt`, `optimized.raw.srt`, `test.txt`, `edl.json`, topics/cut-srt when applicable), then diff post-refactor outputs against those captures with an explicit review of allowed changes (`optimized_text` only where expected, no unintended `user_final_remove` drift).
  - **B3a**: sentence-boundary fixtures for punctuation, pauses, and max-segment limits, ideally promoted into automated tests after the initial `workdir` capture.
  - **B3b**: `dev-export-preview`/cut subtitle flow sanity if overlay text timing changes; ensure `pipeline_service` topic segmentation still consumes generated cut SRT; verify no live imports depend on removed `Cutter` exports.
  - **B6**: ADR review against explicit failure scenarios (worker crash, stale lease, duplicate claim, future task-type expansion) plus state-machine checks for route entry gating and job status mutations across the full `UPLOAD_READY -> TEST_RUNNING -> TEST_READY` success path and failure backedges.

## ADR
- **Decision:** Execute B batch in three phases: (1) low-risk convergence `B1/B4a/B4b/B5`, (2) semantic contract reshaping `B2/B3a/B3b`, (3) standalone `B6` queue architecture review/ADR.
- **Drivers:** current main-path evidence, dependency ordering, reversible commit sizing, queue reliability preservation.
- **Alternatives considered:**
  1. Contract-first `B2/B3` before dedupe — rejected for higher churn and regression ambiguity.
  2. Queue-first `B6` redesign — rejected because current queue already carries reliability semantics and is not yet grounded as the first bottleneck.
  3. One-shot B1-B6 mega-refactor — rejected due to dirty worktree and poor rollback isolation.
- **Why chosen:** maximizes learning and safety: early batches remove duplication and dead-path noise, which lowers ambiguity before touching core media contracts; queue review stays evidence-driven.
- **Consequences:** visible simplification lands later; some temporary adapters may persist between batches; B6 may conclude with no immediate code simplification.
- **Follow-ups:** after each batch, update `docs/requirements_todo.md` status, capture fixture baselines for B2/B3, and only then decide whether to launch `ralph` or `team` execution.

## Available-Agent-Types Roster
- `architect` — contract and system-boundary review.
- `critic` — challenge plan quality/risk coverage (via consensus review lane).
- `planner` — re-plan/re-scope if execution feedback changes assumptions.
- `explore` / `explorer` — cheap repo-fact gathering and reference audits.
- `researcher` — external SDK/API/package evaluation if DashScope/OSS/Turso behavior must be rechecked.
- `executor` / `worker` — bounded implementation batches with disjoint file ownership.
- `build-fixer` / `debugger` — fix broken tests/build/toolchain regressions per batch.
- `test-engineer` / `verifier` — fixture strategy, regression checks, acceptance validation.
- `code-reviewer` / `security-reviewer` — final review for backend queue and upload surfaces.
- `writer` — ADR / migration notes / requirements tracking updates.

## Follow-up Staffing Guidance
### Path A — `ralph` (sequential, lower coordination overhead)
- Best for: executing batches one by one on a dirty baseline with explicit human checkpoints.
- Suggested lanes:
  1. `explorer` (low) for pre-flight ref search, `Cutter` audit, and fixture inventory.
  2. `executor` (high) for B1, B4a, B4b, B5, then B2, then B3a/B3b.
  3. `architect` (high) checkpoint before starting B2, before B3b removal decisions, and before finalizing B6 ADR.
  4. `verifier` (high) after every batch.
- Reasoning levels:
  - B1/B4a/B4b/B5: medium-high.
  - B2/B3a/B3b: high.
  - B6 ADR: high.

### Path B — `team` (parallel, after worktree is isolated)
- Best for: parallelizing safe lanes once branch/worktree hygiene is restored.
- Suggested staffing:
  - Worker 1: B1 + ASR reference audit.
  - Worker 2: B4a persistence-helper dedupe in `web_api` only.
  - Worker 3: B4b/B5 shared OSS + JSON-helper work with strict file ownership split if run together.
  - Architect lane: lock canonical B2 invariants and B4 helper-home decisions after outputs of Workers 1-3 land.
  - Worker 4: B2 implementation on `auto_edit.py`, `pi_agent_runner.py`, `web_api/utils/srt_utils.py`, `video_auto_cut/asr/transcribe_stage.py`, `web_api/schemas.py`, and related tests.
  - Worker 5: B3a/B3b implementation on `dashscope_filetrans.py`, `rendering/cut.py`, `rendering/cut_srt.py`, `rendering/__init__.py`, plus import-audit updates.
  - Writer/architect/verifier lane: B6 ADR and final verification.
- Reasoning levels:
  - Workers 1-3: medium.
  - Worker 4/5: high.
  - Architect/verifier/B6 ADR: high.

## Launch Hints
- `ralph` path (after approval and branch hygiene):
  - `$ralph "Execute Batch 1 (B1 ASR residue audit/removal) from .omx/plans/b-batch-ralplan.md with required verification"`
  - Then advance batch-by-batch, not all at once.
- `team` path:
  - `$team "Execute Phase 1 of .omx/plans/b-batch-ralplan.md: Worker A=B1, Worker B=B4, Worker C=B5; do not touch B2/B3/B6 yet"`
  - Launch Phase 2 only after Phase 1 verification is green.
- For either path, first reconcile the branch-name mismatch and snapshot the dirty worktree to avoid overwriting unrelated edits.

## Team Verification Path
1. **Pre-execution gate:** verify clean isolation (stash/worktree/branch), fixture capture, and explicit ownership by batch.
2. **Phase 1 verification:** B1/B4/B5 each pass unit/build checks plus focused smoke checks; no semantic media-output drift beyond intended helper cleanup.
3. **Phase 2 verification:** B2 and B3 run with frozen artifact comparisons (`optimized.srt`, `test.txt`, `edl.json`, topics/cut SRT) on representative inputs.
4. **Phase 3 verification:** B6 ADR reviewed by architect + verifier against durability/failure-mode checklist.
5. **Release recommendation:** merge only after all prior phases pass and `docs/requirements_todo.md` is updated to reflect actual batch completion.
