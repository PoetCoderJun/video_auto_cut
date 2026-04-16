task statement: Implement C2 plus the duration-format part of C3 in lane 2/3 for branch chore/requirements-c-frontend-cleanup.
desired outcome: Replace getActiveStep switch with typed constant mapping + fallback, unify duration formatting contract across job-workspace.tsx and source-video-guard.ts, keep timeout/error copy unchanged, and only touch owned files.
known facts/evidence:
- getActiveStep currently uses a switch in web_frontend/components/job-workspace.tsx.
- job-workspace.tsx and source-video-guard.ts each define formatDuration with slightly different invalid-input handling.
- withTimeout exists in job-workspace.tsx and timeout/error copy must remain unchanged.
constraints:
- Ownership/write scope only: web_frontend/components/job-workspace.tsx and web_frontend/lib/source-video-guard.ts.
- Minimal touch only.
- Read-only outside ownership.
unknowns/open questions:
- Whether simplifying withTimeout would be clearly better without semantic change.
likely codebase touchpoints:
- web_frontend/components/job-workspace.tsx
- web_frontend/lib/source-video-guard.ts
