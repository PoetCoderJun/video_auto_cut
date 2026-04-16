# Context Snapshot: requirements D repo hygiene

- task statement: Create a dedicated work branch, then plan execution for the D batch in `docs/requirements_todo.md` (repository hygiene and docs/config cleanup).
- desired outcome: Produce an approval-ready implementation plan that covers D1-D4 with concrete scope, sequencing, verification, and affected files; create the required planning artifacts before any implementation.

## known facts / evidence
- User explicitly requested `$ralplan`, so this turn should follow consensus planning rather than jump into implementation.
- A fresh branch was created for this lane: `work/2026-04-16-d-batch-ralplan`.
- `docs/requirements_todo.md` defines D batch as:
  - D1 clean residual scripts/deps/generated artifacts (`scripts/extract_audio.py`, `scripts/invite_admin.py`, `moviepy`, `skills/*/__init__.py`, `__pycache__/`, thin wrappers)
  - D2 migrate/delete debug-page-only scripts (`run_browser_format_matrix.py`, `generate_browser_format_samples.sh`)
  - D3 rewrite docs source of truth (`docs/web_api_interface.md`, `docs/README.md`, `docs/current_prompts_inventory.txt`)
  - D4 trim `.env.example` noise and `.dockerignore` legacy rules
- Current repo evidence relevant to D batch:
  - `scripts/` still contains `extract_audio.py`, `invite_admin.py`, `run_browser_format_matrix.py`, `generate_browser_format_samples.sh`, and checked-in `scripts/__pycache__/...pyc`.
  - `skills/asr-transcribe/scripts/` still contains `__init__.py` and `run_asr_transcribe.py`; multiple `__pycache__` directories exist across repo.
  - `requirements.txt` still lists `moviepy`.
  - `docs/README.md` is a minimal stale index and does not mention current D-batch-relevant docs.
  - `docs/web_api_interface.md` still documents the old MVP/Step2 contract and outdated auth wording.
  - `docs/current_prompts_inventory.txt` exists and likely needs either refresh or deletion decision.
  - `.env.example` contains many optional/verbose knobs, especially ASR and CORS sections.
  - `.dockerignore` currently ignores broad patterns including `*.md`, `scripts`, `test_data`, and `web_frontend`, suggesting legacy/overbroad exclusions.

## constraints
- Follow repo instructions from root `AGENTS.md`.
- Maintain `docs/requirements_todo.md` as the source of truth; update item movement/status in the same turn when appropriate.
- Ralplan-first gate is active; planning artifacts are required under `.omx/plans/` before implementation.
- Avoid destructive cleanup without explicit verification of current usage.
- Existing workspace is dirty with many unrelated modifications; do not revert or disturb them.

## unknowns / open questions
- For D1/D2, which residual scripts are still referenced by README, tests, CI, or developer workflows?
- For D3, should `docs/current_prompts_inventory.txt` be regenerated, archived, or removed entirely?
- For D4, which `.env.example` entries are genuinely required for recommended local run vs advanced/optional tuning?
- For `.dockerignore`, is the target Docker build local-only or meant for deployment/CI contexts too?

## likely codebase touchpoints
- `docs/requirements_todo.md`
- `scripts/`
- `requirements.txt`
- `skills/`
- `docs/README.md`
- `docs/web_api_interface.md`
- `docs/current_prompts_inventory.txt`
- `.env.example`
- `.dockerignore`
