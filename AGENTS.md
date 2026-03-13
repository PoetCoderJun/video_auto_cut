# Repository Guidelines

## Project Structure & Module Organization
- `video_auto_cut/`: shared Python pipeline modules for ASR, auto-edit, topic segmentation, rendering, and human-loop orchestration.
- `skills/video-auto-cut-human-loop/`: Skill entrypoint and workflow reference for Codex, Claude Code, or PyAgent.
- `scripts/`: local helper scripts, especially `run_human_loop_pipeline.py`.
- `tests/`: wrapper-level regression tests for the Skills edition.
- `test_data/`: local sample media for manual verification.
- `workdir/`: runtime artifacts; do not commit generated outputs.

## Build, Test, and Development Commands
- Install deps: `python -m pip install -r requirements.txt`
- Show wrapper help: `python scripts/run_human_loop_pipeline.py --help`
- Run tests: `python -m unittest discover -s tests -p "test_*.py" -v`
- Typical human-loop flow:
  - `python scripts/run_human_loop_pipeline.py run --input-video /abs/in.mp4 --output-video /abs/out.mp4`
  - edit `draft_step1.json`, then `approve-step1`
  - rerun `run`, edit `draft_topics.json`, then `approve-step2`
  - `python scripts/run_human_loop_pipeline.py render --input-video /abs/in.mp4`

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, snake_case, type hints for public helpers.
- Keep workflow logic in reusable Python modules, not prompt text.
- Prefer artifact files with explicit names such as `draft_step1.json` and `final_topics.json`.

## Testing Guidelines
- Add focused `unittest` coverage under `tests/` for wrapper state transitions and resume behavior.
- When touching pipeline orchestration, verify:
  - `run` stops at Step1 review
  - `approve-step1` allows resume into Step2
  - `run` stops at Step2 review
  - `render` only works after both confirmations
- Include manual verification notes for real media runs when behavior changes.

## Commit & Pull Request Guidelines
- Prefer Conventional Commits such as `feat(skill): ...`, `fix(pipeline): ...`, `docs(skill): ...`.
- Keep commits focused; avoid mixing workflow refactors with unrelated prompt or asset changes.
- PRs should explain:
  - what changed in the local pipeline or skill
  - which paths are affected
  - what tests or manual runs verified the change

## Security & Configuration Tips
- Never commit `.env`, credentials, model weights, or generated artifacts.
- Common runtime envs are `ASR_DASHSCOPE_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, and optional OSS settings.
- `ffmpeg` must be available in `PATH` for audio extraction and final cutting.
