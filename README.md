# PoetCut Core

PoetCut Core is a source-available, non-commercial algorithm core for subtitle-driven talking-head video editing.

It keeps the reusable editing logic:

- ASR adapter interfaces and DashScope file-transcription integration.
- Direct-prompt delete, polish, chapter, and highlight contracts.
- SRT/Test text parsing and canonical subtitle editing state.
- Subtitle render contract helpers used by downstream renderers.
- Local CLI paths for running the core pipeline on sample SRT or your own media.

It intentionally does not include the production web product:

- No Next.js frontend, FastAPI hosted API, Better Auth, account system, coupons, credits, public invite flow, analytics, Railway/Docker deployment, online payment, production object-storage presign routes, or private operations scripts.
- No production database replicas, `.env`, customer data, browser profiles, generated exports, or large source media.
- No right to offer this code as a commercial hosted service without a separate commercial license.

## License

This repository is distributed under the `PoetCut Core Non-Commercial Source License 1.0`.

You may read, modify, and self-host it for personal, educational, research, evaluation, and internal non-commercial use. Commercial use, paid hosting, resale, incorporation into a commercial product, or offering PoetCut as a service requires a separate commercial license.

This is source-available software with a non-commercial restriction. It is not OSI-approved open source.

## Repository Layout

- `video_auto_cut/`: Python algorithm core.
- `skills/direct-prompts/`: canonical prompt source files used at runtime.
- `scripts/run_direct_prompt_test.sh`: local CLI helper for the core direct-prompt pipeline.
- `test_data/`: small text fixtures only; large media and generated videos are excluded.
- `tests/`: core contract tests for prompt loading, parsers, and render contracts.

## Install

Python 3.10+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy the example environment file if you want to call real LLM or ASR providers:

```bash
cp .env.example .env
```

Fill in your own provider credentials. Do not reuse any production PoetCut credentials or analytics properties.

## Run The Core Pipeline

For a text-only smoke path, use a local SRT. This avoids ASR/object-storage setup:

```bash
./scripts/run_direct_prompt_test.sh test_data/srt/1.srt
```

For media input, configure the ASR and object-storage variables in `.env`, then pass a local media path:

```bash
./scripts/run_direct_prompt_test.sh /path/to/input.mp4 --lang zh
```

The CLI writes outputs under `workdir/direct_prompt_runs/`, which is ignored by Git.

## Environment

Required for direct-prompt editing:

- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`

Required only for media-to-SRT ASR:

- `DASHSCOPE_ASR_API_KEY`
- `OSS_ENDPOINT`
- `OSS_BUCKET`
- `OSS_ACCESS_KEY_ID`
- `OSS_ACCESS_KEY_SECRET`

No hosted account, billing, coupon, analytics, or production deployment variables are part of this core edition.

## Test

```bash
python -m unittest discover tests -p "test_*.py" -v
```

The default test suite does not call external LLM or ASR providers.

## Commercial Boundary

The public core is the algorithm and contract layer. Production service code remains private by design:

- hosted web UI and API;
- auth/account/session management;
- credit, coupon, payment, invite, and abuse-prevention logic;
- production deployment, monitoring, provider routing, and cleanup jobs;
- object-storage presign endpoints for browser uploads;
- customer data, operational runbooks, private credentials, and analytics.

See `docs/OPEN_CORE_BOUNDARY.md` for the detailed split.
