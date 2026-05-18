# Repository Guidelines

## Project Structure & Module Organization
- `web_frontend/`: Next.js 16 app (UI, auth, browser rendering). Main folders: `app/`, `components/`, `lib/`, `public/`.
- `web_api/`: FastAPI backend and worker entrypoints. Main folders: `api/`, `services/`, `utils/`, `worker/`.
- `video_auto_cut/`: shared Python pipeline modules (ASR, editing, rendering orchestration).
- `scripts/`: operational scripts (for example `start_web_mvp.sh`, `coupon_admin.py`).
- `test_data/`: local sample media for manual regression.
- `workdir/`: runtime artifacts and job files; do not commit generated outputs.

## Current Product Flow
- Entry/UI: `web_frontend/app/page.tsx` and `web_frontend/components/home-page-client.tsx` create or resume a job, then `web_frontend/components/job-workspace.tsx` switches between upload, processing, editor, and export views.
- API boundary: `web_api/api/routes.py` owns user/guest job routes, upload confirmation, `POST /jobs/{job_id}/test/run`, `GET/PUT /jobs/{job_id}/test`, and render config/complete endpoints.
- Test pipeline: `web_api/services/test.py` runs `ASR -> auto_edit(delete/polish) -> chapter sidecar -> TEST_READY`, persists draft lines/chapters, then warms the editor subtitle style cache in the background.
- Direct prompt runtime: `video_auto_cut/direct_prompt_runner.py` and `video_auto_cut/editing/direct_prompts.py` build and parse delete/polish/chapter prompt calls. Runtime prompt text comes from `skills/direct-prompts/*.md`.
- Export pipeline: `confirm_test()` in `web_api/services/test.py` writes final Test artifacts and calls `web_api/services/render_web.py`, which builds `subtitle-render.v1.json` for `web_frontend/lib/remotion/stitch-video-web.tsx`.
- Export UI and Remotion controls live mainly in `web_frontend/components/job-workspace/export-step.tsx`, `web_frontend/components/job-workspace/use-export-step-controller.ts`, and `web_frontend/lib/remotion/`.

## Vibe Coding Iteration Loop
- Start by reading `git status --short --branch`, this file, `README.md`, and the relevant slice of `docs/requirements_todo.md`; assume unrelated dirty files are user work unless proven otherwise.
- Add or move a concise requirement entry in `docs/requirements_todo.md` when a new product request or follow-up appears, then keep the code change scoped to that entry.
- Trace one narrow path before editing: frontend view/controller, API route/service, shared pipeline module, prompt file, or Remotion rendering module. Prefer existing helpers over new abstractions.
- For frontend/UI work, use `web_frontend/app/dev-export-preview/page.tsx` as the fast lab for overlay density, wrapping, resolution presets, and export screenshots before running heavier browser flows.
- For backend/pipeline work, keep persisted job artifacts in `workdir/` and avoid committing generated media, sqlite replicas, browser profiles, `.next/`, or test outputs.
- After a coherent verified unit, commit only the relevant files. If the worktree already contains unrelated changes, do not stage them just to satisfy the commit rule; report the constraint clearly.

## Prompt & LLM Guardrails
- `skills/direct-prompts/delete.md`, `polish.md`, `delete-with-reference.md`, `polish-with-reference.md`, `chapter.md`, and `highlight.md` are the active prompt source of truth. Do not reintroduce hidden runtime prompt rules, dynamic constraints, `.pi` provider wiring, or repo-local skill folders outside `skills/direct-prompts/`.
- `video_auto_cut/editing/direct_prompts.py` uses `script` only to select the explicit `*-with-reference.md` prompt and include the script as input payload. It still must not append hidden script rules, chapter limits, title limits, theme notes, or other dynamic instructions.
- Test editing behavior goes through `video_auto_cut/direct_prompt_runner.py`, `video_auto_cut/orchestration/test_cli.py`, and `web_api/services/test.py`; do not add PI compatibility wrappers or alternate prompt runners.
- Before claiming prompt source cleanup or prompt-only behavior, run or inspect the contract tests around `test_direct_prompt_source_of_truth`, `test_direct_prompt_runner_contract`, and `test_repo_skill_layout`.

## Feature Area Pointers
- Auth, guest sessions, coupons, and credits: `web_api/services/auth.py`, `web_api/services/account.py`, `web_api/api/routes.py`, `web_frontend/lib/auth.ts`, `web_frontend/lib/session.ts`.
- Upload and browser media handling: `web_frontend/lib/upload-pipeline.ts`, `web_frontend/lib/upload-source-preflight.ts`, `web_frontend/lib/video-transcode.ts`, `web_api/services/jobs.py`.
- Test editor state and revision conflicts: `web_frontend/components/job-workspace/use-test-document-polling.ts`, `use-editor-step-controller.ts`, `workspace-state.ts`, plus `build_document_revision()` in `video_auto_cut/editing/chapter_domain.py`.
- Chapter identity/ranges: treat `chapter_key` / `start_line_id` as canonical and `block_range` as derived display/contract data. Keep coverage checks in `video_auto_cut/editing/chapter_domain.py`.
- Render contract/highlights: `video_auto_cut/rendering/subtitle_render_contract.py`, `web_api/services/render_web.py`, `web_frontend/lib/remotion/subtitle-render-v1.ts`, `caption-highlights.ts`, and `overlay-presentation.ts`.
- Local one-shot direct prompt run: `./scripts/run_direct_prompt_test.sh test_data/media/1.wav`.

## Build, Test, and Development Commands
- Install deps:
  - `python -m pip install -r requirements.txt`
  - `cd web_frontend && npm install`
- One-command local run (recommended): `./scripts/start_web_mvp.sh`
  - Starts FastAPI (`127.0.0.1:8000`), worker loop, and Next.js (`127.0.0.1:3000`).
- Frontend only:
  - `npm --prefix web_frontend run dev`
  - `npm --prefix web_frontend run build`
- Backend only:
  - API: `uvicorn web_api.app:app --host 127.0.0.1 --port 8000`
  - Worker: `python -m web_api`

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, snake_case; add type hints for public service/repository functions.
- TypeScript/React: 2-space indentation, camelCase for variables/functions, PascalCase for components/types.
- Keep API error messages user-facing and non-technical.
- Prefer small, focused modules in `web_api/services` and `web_frontend/components`.

## Testing Guidelines
- Current automated tests exist mainly in `web_api/tests/` (unittest style).
- Run: `python -m unittest discover web_api/tests -p "test_*.py"`.
- Useful targeted checks:
  - Direct prompt source/runner: `python -m unittest web_api.tests.test_direct_prompt_source_of_truth web_api.tests.test_direct_prompt_runner_contract web_api.tests.test_repo_skill_layout -v`
  - Direct prompt runner end-to-end contracts: `python -m unittest web_api.tests.test_direct_prompt_runner web_api.tests.test_direct_prompt_runner_end_to_end -v`
  - Backend Test/render handoff: `python -m unittest web_api.tests.test_test_run web_api.tests.test_render_web web_api.tests.test_render_completion -v`
  - Frontend workspace/render units: `cd web_frontend && npm run test:unit`
- For web changes, always run:
  - `cd web_frontend && npx tsc --noEmit`
  - `npm --prefix web_frontend run build`
- No strict coverage gate yet; include manual verification steps (upload, Test/Step2, render/export).
- Shared local web E2E smoke account for browser upload/export verification:
  - Email: `e2e-web-smoke@example.com`
  - Password: `E2E-Web-Smoke-20260420!`
  - Status: activated with credits; prefer reusing this account instead of creating throwaway users during local tests.
- Reliable local browser upload/export debugging path:
  - Use **headed Chrome real-machine mode**. Headless Chrome can falsely report `当前浏览器图形能力不足`.
  - Use `test_data/raw/AI1.MOV` for the real large-case regression check.
  - Standard local startup:
    - `./scripts/start_web_mvp.sh debug`
    - if the configured LLM is overloaded (`429 rate_limit_error` / `currently overloaded`), switch `LLM_BASE_URL` / `LLM_MODEL` to a backup OpenAI-compatible provider and restart `./scripts/start_web_mvp.sh debug`
  - Stable build-mode startup for preview/export debugging when you need to avoid Next dev HMR / page target rebuilds:
    - `WEB_DB_LOCAL_ONLY=1 BETTER_AUTH_LOCAL_ONLY=1 ./scripts/start_web_mvp.sh build`
    - Use this especially when browser E2E reaches export but dev mode keeps rebuilding or CDP targets get invalidated during preview/export.
    - `start_web_mvp.sh` now resolves the auth/business local replica path to an absolute path before starting standalone Next, so build mode can reuse the local Better Auth sqlite replica correctly.
  - If frontend deps were cleaned, run `npm --prefix web_frontend install` first.
  - Before a long browser run, first confirm smoke login works:
    - `POST http://127.0.0.1:3000/api/auth/sign-in/email` should return `200`
  - If auth breaks with `invalid local state: db file exists but metadata file does not`, restart with `start_web_mvp.sh debug`; the frontend auth replica now self-heals on open.
  - Current page-state checkpoints:
    - upload accepted: `请保持页面开启，我们会自动继续处理。`
    - processing: `正在筛除冗余字幕` / `正在润色字幕` / `正在生成章节`
    - editor ready: `保存并进入导出`
    - export ready: `导出设置`
    - export done: `下载上次导出`
  - Fresh browser sessions may lose the local source cache. If export page shows `尚未读取到当前项目的本地源视频缓存`, reselect the original source file once before clicking `导出视频`.
  - For CDP/automation runs, always use a fresh debug port/profile and kill stale Chrome `--remote-debugging-port` processes first.
- For overlay / export UI work, use `web_frontend/app/dev-export-preview/page.tsx` as the reusable mock lab:
  - The mock lab uses a plain white background instead of a real source video so overlay density and wrapping are easier to inspect.
  - Switch scenario presets to inspect long chapter titles, compact single-line titles, and landscape progress labels.
  - Use the editable text inputs to test extreme title lengths, manual line breaks, and same-length copy with different wrap strategies before changing layout logic.
  - Switch resolution presets or use the built-in compare grid to cover low-res landscape, 2K/4K landscape, low-res portrait, and high-res portrait before asking for screenshots or export clips.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style when possible (`feat:`, `fix:`, `docs:`, `chore:`), optionally scoped (e.g., `feat(web): ...`).
- Keep commits atomic; avoid mixing refactor + behavior change + generated artifacts.
- After each completed iteration (a coherent, verified unit of work), create a commit immediately before starting the next iteration or handing off.
- If `git push` to `git@github.com:PoetCoderJun/video_auto_cut.git` fails because SSH port 22 is blocked, push via GitHub SSH over port 443 instead:
  - `GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o Hostname=ssh.github.com -p 443' git push origin main`
- PRs should include:
  - What changed and why.
  - Affected paths (e.g., `web_api/api/routes.py`).
  - Verification evidence (commands run, key logs, UI screenshots for frontend changes).

## Security & Configuration Tips
- Required envs for online mode: `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`.
- Local/offline fallback: set `WEB_DB_LOCAL_ONLY=1`.
- Never commit `.env`, credentials, model weights, or `workdir/` runtime files.

## Requirement Tracking
- Maintain `docs/requirements_todo.md` as the single source of truth for requirement tracking.
- When a new user requirement, change request, or follow-up task appears, update `docs/requirements_todo.md` in the same turn when appropriate.
- Move items across `Backlog`, `In Progress`, and `Done` instead of rewriting history from scratch.
- Keep entries concise and action-oriented, and include dates or affected paths when they help clarify status.
