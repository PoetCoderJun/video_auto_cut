# Open Source Strategy

This repo is closest to an open-core SaaS shape: the editing pipeline, web app,
API contracts, prompt files, and browser export path can be open; the hosted
PoetCut service can remain a commercial deployment that depends on private
provider accounts, operational data, and production configuration.

## Recommended License

Use `AGPL-3.0-or-later` for the public source tree.

Why this fits the product:

- It is an OSI-approved open-source license with an SPDX identifier.
- Its network-use obligations are a better match for a web/SaaS product than a
  permissive license if the goal is to prevent closed hosted forks from taking
  improvements private.
- It still allows a separate commercial hosted service and future dual-license
  arrangements, as long as ownership and contributor terms are managed carefully.

This is not legal advice. Before a public launch, confirm the final license,
copyright holder, dependency compatibility, and contributor terms with counsel.

## Open in the Public Repo

- Core Python pipeline in `video_auto_cut/`.
- FastAPI API and worker code in `web_api/`.
- Next.js frontend in `web_frontend/`.
- Direct prompt source files in `skills/direct-prompts/`.
- Local scripts that are safe for self-hosting and development.
- Tests, docs, and reproducible sample text artifacts.

## Keep Out of the Public Repo

- Real `.env` files, provider tokens, database URLs, auth secrets, and SSH keys.
- Turso/libsql replicas, sqlite files, `workdir*/`, generated renders, uploads,
  and browser profiles.
- Production Railway variables, analytics properties that should not be reused,
  monitoring credentials, customer data, and internal operational runbooks.
- Payment-provider merchant credentials or unfinished commercial payment flows.
- Personal contact assets such as QR codes, unless they are intentionally part
  of the public brand surface.

## Online-Only Commercial Surface

The public repo may require users to bring their own:

- Turso/libsql database or local sqlite-compatible setup,
- object storage for ASR handoff,
- DashScope-compatible ASR credentials,
- OpenAI-compatible LLM endpoint and key,
- Better Auth secret and site URLs,
- analytics/search-console IDs if they want those features.

The official hosted service can additionally keep private:

- production scaling and cleanup policies,
- customer support and abuse-prevention rules,
- billing/payment implementation,
- invite/coupon operations,
- production observability,
- model/provider routing choices if they are business-sensitive.

## Pre-Release Checklist

- Replace or remove personal assets from `web_frontend/public/` if they should
  not be part of the public repo.
- Ensure `git ls-files` does not include local state directories, sqlite files,
  build caches, generated media, or credentials.
- Run a secret scan against tracked files and recent history.
- Verify Docker images include `skills/direct-prompts/`; the runtime prompt
  loader depends on those files.
- Run backend unit tests and frontend type/build checks with placeholder local
  credentials.
- Publish clear self-hosting docs that say which online providers are required.
