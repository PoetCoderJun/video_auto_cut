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
  - Use **headed Chrome real-machine mode**. Headless Chrome can falsely report `当前浏览器图形能力不足`.
  - Use `test_data/raw/AI1.MOV` for the real large-case regression check.
  - Standard local startup:
    - `./scripts/start_web_mvp.sh debug`
    - if Kimi is overloaded (`429 rate_limit_error` / `currently overloaded`), restart with `PI_PROVIDER=vac-llm ./scripts/start_web_mvp.sh debug`
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
