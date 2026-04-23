# Test Spec — 2026-04-23 guest first free edit

## Backend
- Guest session claim creates a reusable guest token for a first-time device fingerprint + IP tuple.
- Re-claim on the same eligible device before consumption rotates/returns a valid guest token instead of creating extra free uses.
- Consumed guest sessions cannot claim another free use.
- Guest actor can create/load/upload/run/confirm/render/complete a job without bearer auth when a valid guest token is supplied.
- Guest completion consumes the free use idempotently for the same job.
- Authenticated account coupon flows remain unchanged.

## Frontend
- API client attaches bearer auth when available, otherwise falls back to the stored guest token.
- Guest session claim is requested before unauthenticated upload flows and stored locally.
- Guest-authenticated create/upload requests send `X-Guest-Token` instead of failing on missing bearer auth.

## Regression verification
- `python -m unittest web_api.tests.test_guest_sessions web_api.tests.test_routes_guest_access -v`
- `python -m unittest web_api.tests.test_routes_job_cleanup_regression web_api.tests.test_api_security_guards -v`
- `cd web_frontend && node --experimental-strip-types --test lib/api.test.mjs`
- `cd web_frontend && npx tsc --noEmit`
- `cd web_frontend && npm run build`
