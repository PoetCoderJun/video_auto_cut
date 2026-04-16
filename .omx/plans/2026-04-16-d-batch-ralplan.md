# D Batch Consensus Plan — Repository Hygiene and Docs/Config Cleanup

Branch: `work/2026-04-16-d-batch-ralplan`
Date: 2026-04-16
Scope source: `docs/requirements_todo.md` D1-D4
Mode: plan-only, approval-ready draft

## RALPLAN-DR

### Principles
1. **Canonical-owner-first**: decide retain / replace / delete before cleanup when a path is still referenced by skills, tests, docs, or tooling.
2. **Runtime-truth docs/config**: docs and examples must reflect the current supported API/runtime/build contexts, not legacy MVP wording.
3. **Bounded hygiene**: remove only residue whose replacement or owner is explicit; avoid unrelated dirty-workspace churn.
4. **Reviewability over breadth**: keep changes path-scoped, evidence-backed, and independently verifiable.

### Decision Drivers
1. Reduce repo noise without breaking live entrypoints, skill docs, tests, or dev workflows.
2. Restore trustworthy source-of-truth docs/config for the current `/test`-centric flow and current build/runtime setup.
3. Keep the batch reviewable on a dirty branch without reverting unrelated modifications.

### Viable Options

#### Option A — Aggressive cleanup/delete now
- **Pros:** fastest repo-noise reduction; smallest end-state.
- **Cons:** highest regression risk for live refs (`run_asr_transcribe.py`, debug scripts, docs); weakest fit for dirty workspace.

#### Option B — Reference-led canonicalization, then cleanup **(chosen)**
- **Pros:** lets execution update refs/tests/docs in the same pass as deletion or migration; supports explicit owner decisions; safest for dirty branch review.
- **Cons:** requires upfront audit and a few explicit retention decisions; may preserve a small number of interfaces if still canonical.

#### Option C — Docs/config only now, defer residue cleanup
- **Pros:** lowest immediate deletion risk.
- **Cons:** leaves D1/D2 unresolved; duplicates audit work later; weak fit for the D-batch goal as written.

## Proposed Plan

### Step 0 — Start bookkeeping in the source of truth
**Goal:** align planning/execution with repository tracking rules before edits begin.

**Actions**
- When execution starts, move D1-D4 from `Backlog` to `In Progress` in `docs/requirements_todo.md`.
- Keep each item separate so D1-D4 can land or defer independently.
- Reserve `Done` movement for after verification evidence is captured.

**Acceptance criteria**
- `docs/requirements_todo.md` reflects active D-batch work without rewriting unrelated history.
- Later execution can update each D item independently.

### Step 1 — Establish guardrails and path-scoped audit
**Goal:** freeze the cleanup boundary before touching D1-D4 targets.

**Actions**
- Inventory current references to D1/D2/D3 candidates across scripts, skills, tests, docs, and Docker/build inputs.
- Record dirty-workspace guardrails for execution: no `git checkout --`, no reset, no broad formatting or opportunistic cleanup outside approved files.
- Separate build-context review into:
  - root `Dockerfile` context policy (`requirements.txt`, `web_api/`, `video_auto_cut/`), and
  - `web_frontend/Dockerfile` frontend-local context behavior.
- Capture the current runtime-env surfaces consumed by `web_api/config.py`, repo scripts, and `.pi/extensions/project-llm-provider.ts`.

**Key dependency/order constraint:** must complete before any retain/delete decision, because several target paths are still live or already modified.

**Acceptance criteria**
- Each D1-D4 candidate has known inbound references or explicit confirmation of no live refs.
- Dirty-branch review rules are explicit for later execution.
- Root-vs-frontend Docker context boundary is documented.
- Required/current env surfaces are enumerated before `.env.example` is edited.

### Step 2 — Make canonical retention decisions for live code/script artifacts
**Goal:** decide owner and fate before cleanup.

**Decision set**
- `skills/asr-transcribe/scripts/run_asr_transcribe.py`: retain as canonical wrapper, replace with direct module invocation and then delete, or relocate while updating skill docs/tests.
- `scripts/run_browser_format_matrix.py` and `scripts/generate_browser_format_samples.sh`: retain under frontend-owned dev tooling, relocate under `web_frontend` ownership, or remove together with the dev page if obsolete.

**Out of Step 2 by default**
- `docs/current_prompts_inventory.txt` stays with D3 unless Step 1 finds a real code/test dependency.

**Key dependency/order constraint:** D1/D2 execution depends on these decisions; no deletion before dependent refs are updated.

**Acceptance criteria**
- Each live code/script candidate has an explicit retain / replace / delete decision.
- Any retained artifact has a named owner/location and reason.
- Any removal path identifies the docs/tests/skill refs that must be updated in the same change.

### Step 3A — Execute D1 repository residue cleanup
**Goal:** clean residual scripts/deps/generated artifacts without breaking live skill/test entrypoints.

**Scope**
- Residual scripts/deps/generated artifacts in `scripts/`, `requirements.txt`, `skills/*`, and tracked `__pycache__` / `.pyc` trees.
- Thin wrappers or stale package markers such as `skills/*/__init__.py` only after verifying they are not required by loaders/tests.
- `moviepy` removal only if the usage audit shows no remaining runtime/test dependency.
- `skills/asr-transcribe/scripts/run_asr_transcribe.py` only according to Step 2’s decision and with dependent docs/tests updated atomically.

**Acceptance criteria**
- No deleted D1 artifact still has live refs in skills/tests/docs.
- `moviepy` removal is justified by actual dependency usage review, not assumption.
- Tracked `__pycache__` and `.pyc` residue is removed from source control and covered by ignore policy where appropriate.

### Step 3B — Execute D2 debug-format tooling cleanup as a frontend-owned sub-lane
**Goal:** resolve debug-only format-matrix tooling with a smaller blast radius than D1.

**Scope**
- `scripts/run_browser_format_matrix.py`
- `scripts/generate_browser_format_samples.sh`
- related assets/ownership/docs under `web_frontend/app/dev-format-matrix/` and `web_frontend/public/generated-format-samples/`

**Actions**
- If retained, move these scripts closer to the frontend dev page and document their ownership.
- If removed, remove the paired dev page/assets/docs together rather than leaving half-supported tooling.

**Acceptance criteria**
- Debug tooling has exactly one owner/location, or is fully removed with its dependent page/docs/assets.
- D2 changes remain reviewable independently from D1 residue cleanup.

### Step 4 — Rewrite D3 docs after ownership settles
**Goal:** re-establish a small trustworthy docs set.

**Actions**
- Rewrite `docs/web_api_interface.md` against the current route surface and explicitly state scope: supported public contract vs full implementation inventory.
- The rewrite must explicitly include or exclude the following route groups rather than hand-wave “route families”:
  - `/jobs`
  - `/me`
  - `/auth/coupon/redeem`
  - `/public/coupons/verify`
  - `/public/invites/claim`
  - `/client/upload-issues`
  - `/jobs/{job_id}`
  - `/jobs/{job_id}/oss-upload-url`
  - `/jobs/{job_id}/audio-oss-ready`
  - `/jobs/{job_id}/audio`
  - `/jobs/{job_id}/test/run`
  - `/jobs/{job_id}/test`
  - `/jobs/{job_id}/test/confirm`
  - `/jobs/{job_id}/render/config`
  - `/jobs/{job_id}/render/complete`
- Remove stale `Step2` and `Clerk JWT` wording unless retained as explicit historical notes.
- Rewrite `docs/README.md` as the docs index for maintained source-of-truth documents.
- Decide whether `docs/current_prompts_inventory.txt` is refreshed, archived with a pointer, or removed with a replacement reference; record an owner if it is retained.

**Key dependency/order constraint:** do this after D1/D2 ownership decisions so docs only describe the final canonical surfaces.

**Acceptance criteria**
- `docs/web_api_interface.md` declares scope and matches the chosen current route surface.
- `docs/README.md` points only to maintained docs.
- `docs/current_prompts_inventory.txt` is either refreshed with owner/date, archived with pointer, or removed with replacement reference.

### Step 5 — Tighten D4 config examples and build-context ignore rules
**Goal:** reduce config noise while also filling current runtime/build gaps.

**Actions**
- Reduce `.env.example` to recommended local-run essentials first, then a short advanced/optional section for tuning knobs that are still supported.
- Add any currently required or operationally important envs that are missing from `.env.example`, especially the active LLM provider surface (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` / `DASHSCOPE_API_KEY` fallback) if those remain part of the supported path.
- Rewrite `.dockerignore` as intentional root build-context policy rather than a blanket legacy exclusion list.
- Explicitly state the current A6 boundary in docs/config language:
  - either root image does **not** support in-container Test editing yet because `.pi/` and `skills/` are absent, or
  - D-batch only documents that A6 remains a blocking follow-up before claiming such support.

**Key dependency/order constraint:** do this after Step 4 so config/docs language aligns with the final chosen docs surface and build-context story.

**Acceptance criteria**
- `.env.example` clearly distinguishes required local-run variables from optional advanced tuning.
- `.env.example` no longer omits current supported runtime envs that users are expected to set.
- `.dockerignore` no longer excludes broad paths (`*.md`, `scripts`, `web_frontend`, `test_data`, etc.) without current build-context rationale.
- Resulting ignore policy is explainable against the current root Dockerfile and separate frontend Dockerfile behavior.
- The A6/container-support boundary is explicitly documented rather than implied.

### Step 6 — Verification evidence and final bookkeeping
**Goal:** leave D-batch ready for safe execution and review.

**Actions**
- Capture verification evidence and any explicit deferrals.
- Move each D item from `In Progress` to `Done` or leave it pending/deferred based on actual outcome.
- Record final decisions for ambiguous artifacts, especially prompt inventory ownership and wrapper retention/removal.

**Acceptance criteria**
- `docs/requirements_todo.md` reflects D-batch progress without rewriting unrelated history.
- Verification outputs are sufficient to review cleanup safely on a dirty branch.
- Remaining follow-ups are explicit and bounded.

## Verification Plan

### Repo sweeps
- `rg` for removed paths and names: `extract_audio.py`, `invite_admin.py`, `run_browser_format_matrix.py`, `generate_browser_format_samples.sh`, `run_asr_transcribe.py`, `moviepy`
- `rg` for stale doc language: `Step2`, `Clerk JWT`
- `rg` for prompt-inventory ownership pointers or replacement references, depending on the chosen D3 outcome
- `find . -type d -name '__pycache__'` and tracked-file review for `.pyc`

### Code/doc cross-checks
- Cross-check `docs/web_api_interface.md` against `web_api/api/routes.py`
- Cross-check `.env.example` entries against actual env consumers in `web_api/config.py`, `.pi/extensions/project-llm-provider.ts`, `scripts/start_web_mvp.sh`, and relevant README sections
- Review `.dockerignore` against:
  - root `Dockerfile` build context and copies
  - `web_frontend/Dockerfile` local context assumptions
- If D2 is retained, verify dev-format tooling docs/path references align with `web_frontend/app/dev-format-matrix/` and generated sample asset paths

### Targeted test expectations for later execution
- `python -m unittest web_api.tests.test_repo_skill_layout`
- Any doc/layout tests added or updated to protect the chosen `run_asr_transcribe.py` and prompt-inventory outcomes
- Additional exact test file list should be captured by updating `test-spec-2026-04-16-d-batch-repo-hygiene.md` if execution decisions add or remove narrow regression coverage

## Risks
- **Live wrapper discoverability loss:** removing `run_asr_transcribe.py` without a replacement command/doc path could break skill usability and tests.
- **Prompt inventory drift:** refreshing `docs/current_prompts_inventory.txt` without defining ownership may recreate the same staleness.
- **Over-tight `.dockerignore`:** a broad rewrite can either leak files into context or over-optimize for the current `COPY` statements while ignoring build-context reality.
- **A6 boundary confusion:** D4 can accidentally imply Docker/Test-edit support that the current root image does not provide.
- **Dirty-branch collisions:** D-batch touches files already modified in the workspace, so execution must stay path-scoped and avoid cleanup of unrelated diffs.

## File Touchpoints
- `docs/requirements_todo.md`
- `docs/README.md`
- `docs/web_api_interface.md`
- `docs/current_prompts_inventory.txt`
- `.env.example`
- `.dockerignore`
- `requirements.txt`
- `scripts/`
- `skills/asr-transcribe/SKILL.md`
- `skills/asr-transcribe/scripts/`
- `web_frontend/app/dev-format-matrix/`
- `web_frontend/public/generated-format-samples/`
- `web_api/tests/test_repo_skill_layout.py`
- any ignore file updates required to keep generated artifacts out of source control

## ADR

### Decision
Use a **reference-led canonicalization then cleanup** plan for D1-D4, with explicit retain/replace/delete decisions before removing live residue.

### Drivers
- Cleanup must not break live skill/test/doc entrypoints.
- Docs/config must converge on current runtime truth rather than legacy MVP wording.
- The branch is already dirty, so the work must be tightly scoped and reviewable.

### Alternatives considered
- **Aggressive cleanup/delete now:** faster, but too risky given live refs and already-modified targets.
- **Docs/config only now:** safer short-term, but leaves the residue batch unresolved and duplicates audit effort later.

### Why chosen
This option best fits the repo’s current state: it can remove real residue while still protecting discoverability, tests, and docs by updating dependents in the same bounded lane.

### Consequences
- Execution will spend more time up front on auditing and decision capture.
- A few artifacts may be retained temporarily if they are still canonical.
- D1 and D2 can still land together, but as separate sub-lanes for a smaller blast radius.
- D4 must document the current container/Test-editing boundary instead of hand-waving it.

### Follow-ups
- Keep `prd-2026-04-16-d-batch-repo-hygiene.md` and `test-spec-2026-04-16-d-batch-repo-hygiene.md` in sync if execution decisions narrow or expand scope.
- In execution handoff, explicitly record the final outcome for `docs/current_prompts_inventory.txt`.
