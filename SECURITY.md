# Security Policy

## Reporting Vulnerabilities

Please do not open public issues for credentials, auth bypasses, customer data
exposure, upload/render isolation problems, or provider-token leaks.

Send a private report to the project maintainer with:

- affected commit or deployed version,
- reproduction steps,
- expected impact,
- any relevant logs with secrets redacted.

## Supported Surface

Security-sensitive areas include:

- auth/JWT and Better Auth integration,
- guest sessions, coupons, credits, and account state,
- upload and object-storage presigning,
- ASR/LLM provider credentials,
- local and hosted Turso/libsql replicas,
- browser-side export and source-video cache handling.

## Handling Secrets

Never commit `.env`, real provider keys, database replicas, customer media,
render outputs, browser profiles, or local agent state. Use `.env.example` for
configuration names and placeholders only.
