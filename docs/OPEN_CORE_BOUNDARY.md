# Open Core Boundary

PoetCut Core is the non-commercial source-available algorithm edition. It is designed to be useful for studying, modifying, and running the subtitle-editing core without publishing the production SaaS product.

## Included

- Python ASR adapter interfaces and DashScope file-transcription integration.
- Direct-prompt runtime and prompt source files.
- Delete, polish, chapter, and highlight output parsers.
- SRT/Test text helpers and canonical editing data structures.
- Subtitle render contract helpers.
- Small text fixtures and non-networked contract tests.

## Excluded

- Hosted Next.js frontend and FastAPI product API.
- Better Auth, JWKS, account identity, guest sessions, coupons, credits, public invites, and payment logic.
- Railway/Docker production deployment logic.
- Browser upload presign routes and production object-storage API surface.
- Analytics IDs, SEO production domains, WeChat/contact assets, brand marketing pages, and commercial beta copy.
- Customer data, database replicas, runtime `workdir/` contents, generated videos, browser profiles, and private operations scripts.

## Why This Split

The business logic of subtitle-driven editing can be public and auditable. The production logic that makes the hosted service deployable, billable, scalable, and directly cloneable stays private.

The result is intentionally not a one-command production clone. It is a clean algorithm core that can run locally, with external providers supplied by the user, under a non-commercial license.
