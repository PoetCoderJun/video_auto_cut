# Repository Guidelines

## Project Structure & Module Organization
- `web_frontend/`: Next.js 16 app (UI, auth, browser rendering). Main folders: `app/`, `components/`, `lib/`, `public/`.
- `web_api/`: FastAPI backend and worker entrypoints. Main folders: `api/`, `services/`, `utils/`, `worker/`.
- `video_auto_cut/`: shared Python pipeline modules (ASR, editing, rendering orchestration).
- `scripts/`: operational scripts (for example `start_web_mvp.sh`, `coupon_admin.py`).
- `test_data/`: local sample media for manual regression.
- `workdir/`: runtime artifacts and job files; do not commit generated outputs.

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
- For web changes, always run:
  - `cd web_frontend && npx tsc --noEmit`
  - `npm --prefix web_frontend run build`
- No strict coverage gate yet; include manual verification steps (upload, Test/Step2, render/export).
- Shared local web E2E smoke account for browser upload/export verification:
  - Email: `e2e-web-smoke@example.com`
  - Password: `E2E-Web-Smoke-20260420!`
  - Status: activated with credits; prefer reusing this account instead of creating throwaway users during local tests.
- Reliable local browser upload/export debugging path:
  - Prefer **headed Chrome real-machine mode** for browser export verification. Headless Chrome often trips the local render capability guard and can report “当前浏览器图形能力不足”.
  - Source fixture for the large real-world regression case is `test_data/raw/AI1.MOV` (the user may say `A1.MOV`, but the repo fixture is `AI1.MOV`).
  - Start the stack from repo root with `.env` loaded. The most reliable manual path is:
    - API: `set -a && source .env && set +a && TURSO_LOCAL_REPLICA_PATH='/Users/huzujun/Desktop/video_auto_cut/workdir/web_api_turso_replica.db' /usr/local/anaconda3/envs/python39/qwen312/bin/python -m uvicorn web_api.app:app --host 127.0.0.1 --port 8000 --log-level info --access-log`
    - Frontend dev: `set -a && source .env && set +a && BETTER_AUTH_SECRET='video-auto-cut-prod-secret-20260420-strong-abcdef123456789' TURSO_LOCAL_REPLICA_PATH='/Users/huzujun/Desktop/video_auto_cut/workdir/web_api_turso_replica.db' NEXT_PUBLIC_API_BASE='http://127.0.0.1:8000/api/v1' NEXT_PUBLIC_SITE_URL='http://127.0.0.1:3000' BETTER_AUTH_URL='http://127.0.0.1:3000' WEB_API_BASE='http://127.0.0.1:8000/api/v1' npm --prefix web_frontend run dev -- --hostname 127.0.0.1 --port 3000`
  - If `web_frontend` dependencies were cleaned, run `npm --prefix web_frontend install` before starting Next.js.
  - Use an **absolute** `TURSO_LOCAL_REPLICA_PATH` when launching frontend auth flows; relative replica paths can break Better Auth/Turso file-sync behavior depending on the current working directory.
  - For login smoke checks, verify `POST http://127.0.0.1:3000/api/auth/sign-in/email` succeeds before starting long browser automation runs.
  - If using CDP/Chrome automation, first kill stale Chrome instances with old `--remote-debugging-port` values and use a fresh port/profile per run; stale sessions can cause the automation to attach to the wrong page or hang waiting for outdated UI text.
  - The legacy `scripts/e2e_browser_upload_export.mjs` flow may lag behind current UI copy/state names; if it stalls, inspect the live page over CDP and drive the current buttons/states directly instead of trusting old text waits.
  - For subtitle/export visual debugging, useful checkpoints are:
    - upload accepted: page shows `请保持页面开启，我们会自动继续处理。`
    - edit running: `正在筛除冗余字幕` / `正在润色字幕` / `正在生成章节`
    - export ready: `保存并进入导出` or `导出设置`
    - export done: `下载上次导出`
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
