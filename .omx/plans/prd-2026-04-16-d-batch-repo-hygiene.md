# PRD — D Batch Repository Hygiene / Docs / Config Cleanup

Date: 2026-04-16
Branch: `work/2026-04-16-d-batch-ralplan`
Source requirement: `docs/requirements_todo.md` D1-D4
Status: planning-ready

## Problem
The repo still contains residual scripts, tracked generated artifacts, stale docs, noisy example config, and overbroad Docker ignore rules. These issues reduce trust in the repo’s source of truth and make future cleanup riskier because some “residue” is still live.

## Goal
Complete D1-D4 with a bounded, reviewable cleanup that:
- removes true residue,
- preserves or clearly replaces live entrypoints,
- rewrites docs to match the current `/test`-centric flow,
- clarifies config/build boundaries.

## Non-goals
- No broader architecture refactor outside D1-D4.
- No A6 implementation to add `.pi/` / `skills/` into the deployment image in this batch.
- No opportunistic cleanup of unrelated dirty files.

## Users / beneficiaries
- Repo maintainers
- Future coding agents working from repo docs/config
- Developers running local API/frontend/Test flows

## Scope
### D1
- Residual scripts/deps/generated artifacts in `scripts/`, `requirements.txt`, `skills/*`, tracked `__pycache__` / `.pyc`
- `skills/asr-transcribe/scripts/run_asr_transcribe.py` only after explicit retain/replace/delete decision

### D2
- `scripts/run_browser_format_matrix.py`
- `scripts/generate_browser_format_samples.sh`
- `web_frontend/app/dev-format-matrix/` and related generated sample assets if ownership changes

### D3
- `docs/web_api_interface.md`
- `docs/README.md`
- `docs/current_prompts_inventory.txt`

### D4
- `.env.example`
- `.dockerignore`
- associated docs language for container/Test-editing support boundary

## Success metrics
- No dangling references to removed D1/D2 files.
- `docs/web_api_interface.md` no longer documents Step2-era flow as current truth.
- `.env.example` clearly separates required vs optional knobs and covers active supported runtime envs.
- `.dockerignore` is explainable from current Docker build contexts.

## Functional requirements
1. The batch must begin by moving D1-D4 into `In Progress` in `docs/requirements_todo.md`.
2. Live code/script artifacts must receive explicit retain/replace/delete decisions before deletion.
3. D1 and D2 may ship together, but must be executed as separate sub-lanes.
4. D3 must explicitly include or exclude each current route family in the rewritten API doc.
5. D4 must state the current root-image limitation around in-container Test editing and A6 follow-up status.

## Risks / mitigations
- Live wrapper removal breaks skill discoverability → update docs/tests atomically or retain wrapper.
- Prompt inventory becomes stale again → assign owner/date or remove with replacement reference.
- `.dockerignore` rewrite drifts from Docker reality → validate against both Dockerfiles.

## Delivery slices
1. Audit + decisions
2. D1 cleanup
3. D2 cleanup
4. D3 docs rewrite
5. D4 config/ignore rewrite
6. Verification + todo bookkeeping
