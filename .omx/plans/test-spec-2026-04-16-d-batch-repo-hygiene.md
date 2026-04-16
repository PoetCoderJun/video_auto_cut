# Test Spec — D Batch Repository Hygiene / Docs / Config Cleanup

Date: 2026-04-16
Branch: `work/2026-04-16-d-batch-ralplan`
Status: planning-ready

## Verification objectives
Confirm that D1-D4 cleanup removes residue without breaking live references, and that rewritten docs/config match current runtime/build behavior.

## Evidence set

### 1. Reference integrity
- `rg -n "extract_audio|invite_admin|run_browser_format_matrix|generate_browser_format_samples|run_asr_transcribe|moviepy" README.md docs scripts web_frontend web_api video_auto_cut skills`
- Expectation: any removed artifact has zero dangling refs; retained artifacts have updated canonical refs only.

### 2. Generated-artifact hygiene
- `find . -type d -name '__pycache__' | sort`
- `git status --short`
- Expectation: tracked cache artifacts removed from source control; ignore policy prevents immediate re-noise.

### 3. API doc accuracy
- Cross-check rewritten `docs/web_api_interface.md` against `web_api/api/routes.py`.
- Required route decision list:
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
- Expectation: every route group is either documented or explicitly out of scope.

### 4. Stale-language removal
- `rg -n "Step2|Clerk JWT" docs/web_api_interface.md docs/README.md docs/current_prompts_inventory.txt README.md`
- Expectation: stale wording removed or explicitly marked historical.

### 5. Config example accuracy
- Cross-check `.env.example` against:
  - `web_api/config.py`
  - `.pi/extensions/project-llm-provider.ts`
  - `scripts/start_web_mvp.sh`
  - `README.md`
- Expectation: required/current supported envs are present; advanced knobs are clearly labeled optional.

### 6. Docker ignore policy accuracy
- Review `.dockerignore` against:
  - root `Dockerfile`
  - `web_frontend/Dockerfile`
- Expectation: ignore rules are intentional and do not rely on outdated blanket exclusions.

### 7. D2 asset ownership cross-check
- Verify whether existing `web_frontend/public/generated-format-samples/portrait_*` assets remain canonical, move with the dev page, or are removed together with D2 tooling.
- Expectation: no orphaned generated-format assets remain after the D2 decision.

### 8. Focused automated regression
- `python -m unittest web_api.tests.test_repo_skill_layout`
- Add/update narrow tests only if needed for chosen D1/D2 outcomes.

## Acceptance checklist
- [ ] D1 artifacts resolved with no dangling refs
- [ ] D2 tooling has one canonical owner or is fully removed
- [ ] D3 docs explicitly match chosen API scope
- [ ] D4 config/ignore rules reflect current runtime/build truth
- [ ] `docs/requirements_todo.md` moved items through `In Progress` → `Done/Deferred` with evidence
