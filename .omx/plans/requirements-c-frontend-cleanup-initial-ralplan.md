# RALPLAN-DR Short Mode — Initial Consensus Draft

## Scope
- Branch already created: `chore/requirements-c-frontend-cleanup`
- Context snapshot: `.omx/context/requirements-c-frontend-cleanup-20260416T030814Z.md`
- Requirement batch: `docs/requirements_todo.md` C1-C4 (`docs/requirements_todo.md:47-50`)
- Primary touchpoints observed:
  - `web_frontend/lib/api.ts`
  - `web_frontend/components/job-workspace.tsx`
  - `web_frontend/components/home-page-client.tsx`
  - `web_frontend/components/export-frame-preview.tsx`
  - `web_frontend/lib/source-video-guard.ts`
  - `web_frontend/lib/job-draft-storage.ts`
  - `web_frontend/lib/remotion/overlay-controls.ts`
  - `web_frontend/lib/remotion/export-bitrate.ts`
  - `web_frontend/lib/remotion/typography.ts`

## Principles
1. **Smallest safe touch set** — only edit files needed for C1-C4 so existing unrelated dirty worktree changes stay isolated.
2. **One canonical helper per behavior** — thin aliases/wrappers should either disappear or become explicit option paths, not parallel APIs.
3. **Behavior-preserving cleanup first** — prefer structural consolidation over semantic rewrites unless C4 requires a deliberate rule decision.
4. **Locality-aware extraction** — promote duplicated helpers only when at least two active frontend callers share the exact behavior contract.
5. **Verification before closure** — every cleanup item must end with compile/build proof plus focused UI/manual regression points.

## Decision Drivers (Top 3)
1. **Regression risk in active frontend flows**: upload, invite/coupon redemption, job workspace, export preview.
2. **Blast radius control**: current worktree already contains unrelated edits, so refactor scope must stay narrow and mechanical.
3. **Long-term API/tooling clarity**: remove duplicate entrypoints only when the surviving abstraction is clearly named and reusable.

## Viable Options

### Option A — Minimal-touch consolidation in existing files (Recommended)
**Approach:** Keep most logic in current modules, replace duplicate entrypoints with one canonical path plus a tiny shared util layer only where duplication is already proven.

**Pros**
- Lowest merge/conflict risk in a dirty tree.
- Best fit for C-batch goal: cleanup without architecture churn.
- Easier to prove behavior parity for `api.ts`, `job-workspace.tsx`, and export preview.
- Keeps import churn small, especially for `job-workspace.tsx` and preview/remotion helpers.

**Cons**
- Leaves some utility placement imperfect if broader frontend cleanup is planned later.
- Shared helper extraction must stay disciplined to avoid a half-finished “utils” bucket.

### Option B — Broader frontend utility/API reorganization
**Approach:** Introduce new shared helper modules for request/auth, time formatting, numeric math, and aspect-ratio formatting; update callers broadly in one batch.

**Pros**
- Stronger long-term consolidation story.
- Could remove more duplication than C1-C4 explicitly require.
- May improve discoverability if new module boundaries are well-designed.

**Cons**
- Higher touch count and conflict risk in a dirty worktree.
- Harder to keep behavior-preserving because multiple modules move at once.
- Exceeds the stated cleanup batch and invites incidental redesign.

**Why Option A beats Option B here:** the task is a bounded frontend cleanup batch, not a general utility architecture pass. The repo already has unrelated modifications, so minimizing file churn is more important than achieving maximal centralization in one shot.

## Recommended Execution Plan

### Step 1 — Lock the exact cleanup surface and dependency edges
**Files:** `docs/requirements_todo.md`, `web_frontend/lib/api.ts`, `web_frontend/components/job-workspace.tsx`, `web_frontend/components/home-page-client.tsx`, `web_frontend/components/export-frame-preview.tsx`, small utility callers in `web_frontend/lib/remotion/*` and `web_frontend/lib/source-video-guard.ts`

- Confirm C1-C4 scope remains limited to the already identified files and direct callsites.
- Record any extra touched file only if required to remove a duplicate helper cleanly.
- Avoid opportunistic cleanup outside the C items.

**Acceptance criteria**
- Planned edit set is explicitly bounded before implementation starts.
- Any new file/module is justified by at least 2 concrete callers.

### Step 2 — C1: collapse duplicate API entrypoints without changing behavior
**Evidence:** `web_frontend/lib/api.ts:291-299, 431-453, 518-523`; imports in `web_frontend/components/job-workspace.tsx:32`, `web_frontend/components/home-page-client.tsx:26`

- Remove `uploadAudioDirectToOss` as an empty alias and migrate callsites to `uploadAudio`.
- Fold explicit-token request flow into the main request path (likely via request options / auth header injection) so `requestWithExplicitToken` disappears while `activateInviteCode` still supports explicit token and default auth path.
- Preserve public behavior for coupon redemption and audio upload retries.

**Acceptance criteria**
- `uploadAudioDirectToOss` no longer exists.
- `requestWithExplicitToken` no longer exists.
- `activateInviteCode` still works for both explicit-token and normal authenticated flows.
- `home-page-client.tsx` and `job-workspace.tsx` compile against the surviving API exports.

### Step 3 — C2: simplify `job-workspace.tsx` local helper structure without changing UX
**Evidence:** `web_frontend/components/job-workspace.tsx:290-317, 519, 1185, 1232`

- Replace `getActiveStep` switch with a status→step map + fallback.
- Inline or replace thin wrappers like `withTimeout` only where the callsite stays readable; preserve timeout messaging semantics.
- Evaluate whether local `formatDuration` and render-duration helper should become shared only if exact contracts match C3 destinations.

**Acceptance criteria**
- Step resolution no longer depends on a switch statement.
- Timeout handling stays explicit at async callsites and preserves current timeout/error messages.
- No job workspace user-facing copy or state transitions change unintentionally.

### Step 4 — C3/C4: unify proven duplicate helpers and settle one aspect-ratio display rule
**Evidence:**
- Duration duplication: `web_frontend/components/job-workspace.tsx:334-354`, `web_frontend/lib/source-video-guard.ts:5-10`
- Clamp duplication: `web_frontend/lib/remotion/overlay-controls.ts:40-45`, `web_frontend/lib/remotion/export-bitrate.ts:38-40`, `web_frontend/lib/remotion/typography.ts:202-205`, `web_frontend/components/export-frame-preview.tsx:49-53`
- Aspect ratio logic: `web_frontend/components/export-frame-preview.tsx:64-79`

- Extract or reuse a small shared numeric/time utility only for identical behaviors; do not force mismatched callers into one abstraction.
- Remove math-only thin wrappers from `typography.ts` if they add no domain meaning; keep semantically meaningful helpers.
- Choose and document one export-preview aspect-ratio rule. Recommendation: keep **exact reduced integer ratio** (current gcd-based behavior) unless product wants named approximations, because it is deterministic, already implemented, and avoids ambiguous lookup tables.

**Acceptance criteria**
- Shared `clamp`/duration helpers have one canonical frontend implementation for matching contracts.
- `typography.ts` no longer carries math wrappers that are just renamed `Math.*` calls without domain meaning.
- `export-frame-preview.tsx` uses a single documented aspect-ratio rule; no competing formatting path remains.

### Step 5 — Close the batch with bounded verification and requirement tracking
**Files:** `docs/requirements_todo.md`, touched frontend files

- Run required frontend validation.
- Perform manual UI verification in the specific flows touched by C1-C4.
- Move C1-C4 from `In Progress` to `Done` only after validation evidence is available.

**Acceptance criteria**
- `cd web_frontend && npx tsc --noEmit` passes.
- `npm --prefix web_frontend run build` passes.
- `docs/requirements_todo.md` reflects completed status plus date/result notes.

## Verification Plan

### Required automated checks
1. `cd web_frontend && npx tsc --noEmit`
2. `npm --prefix web_frontend run build`

### Targeted manual frontend checks
1. **Upload flow:** from both `home-page-client` and `job-workspace`, confirm audio upload still reaches the same success/error states after alias removal.
2. **Coupon/invite flow:** verify `activateInviteCode` still succeeds with normal signed-in flow and with explicit token caller path used by auth/coupon entry points.
3. **Job workspace timing/status UI:** confirm active step indicator, timeout-backed operations, and displayed durations remain unchanged in visible UX.
4. **Export preview:** inspect ratio label after the chosen rule using representative sizes (e.g. 1920×1080, 1080×1920, 2560×1440, odd-size inputs if available).
5. **Overlay preview sanity:** ensure helper consolidation does not alter slider/preview clamping behavior for subtitle/progress/chapter controls.

## Risks & Mitigations
- **Risk: hidden semantic differences between duplicate helpers.**
  - **Mitigation:** compare contracts before merging; if invalid/NaN behavior differs materially, keep separate helpers or normalize callers explicitly.
- **Risk: explicit-token auth path regresses while standard auth still works.**
  - **Mitigation:** preserve `activateInviteCode` dual-path behavior and manually exercise explicit-token callers after refactor.
- **Risk: broad helper extraction touches unrelated remotion/render files.**
  - **Mitigation:** prefer importing into already-listed files only; defer wider dedupe to a later batch.
- **Risk: dirty worktree causes accidental edits outside scope.**
  - **Mitigation:** keep file list bounded, review diffs per file, and avoid formatting sweeps/reorders.
- **Risk: aspect-ratio rule changes user-visible labels unexpectedly.**
  - **Mitigation:** choose one documented rule up front and verify with common landscape/portrait presets before closing C4.

## ADR

### Decision
Use a **minimal-touch, behavior-preserving cleanup plan** for C1-C4: collapse duplicate API/helper entrypoints, extract only proven shared helpers, and keep export preview on one explicit aspect-ratio display rule.

### Drivers
- Dirty worktree requires narrowest safe edit set.
- Cleanup batch scope is bounded to C1-C4, not a general frontend redesign.
- Affected flows are user-facing and regression-sensitive.

### Alternatives considered
1. **Minimal-touch consolidation in place**.
2. **Broader shared utility/API reorganization** with new modules and wider caller migration.

### Why chosen
Option 1 delivers the requested cleanup with lower merge risk, lower behavioral risk, and a clearer chance of finishing C1-C4 without absorbing unrelated frontend cleanup debt.

### Consequences
- Some non-critical duplication may remain outside the explicitly touched paths.
- The surviving helper/API shapes should become clearer and easier to maintain.
- Future cleanup passes may still choose deeper utility reorganization if more callers accumulate.

### Follow-ups
- If more duplicate math/time helpers appear after this batch, consider a dedicated shared frontend utility pass.
- If product wants human-friendly aspect names rather than exact ratios, create a separate requirement rather than expanding C4 mid-batch.

## Available Agent Types Roster
- `architect`: architecture/tradeoff review, high reasoning
- `critic`: plan challenge/review, high reasoning
- `planner`: sequencing/risk review, medium reasoning
- `explore` / `explorer`: fast codebase lookup, low reasoning
- `executor` / `worker`: implementation, high reasoning
- `code-reviewer`: final multi-concern code review, high reasoning
- `verifier`: completion/test evidence check, high reasoning
- `test-engineer`: validation strategy and regression focus, medium reasoning
- `build-fixer`: compile/build failure cleanup, high reasoning

## Staffing / Verification Guidance

### If follow-up execution goes through `ralph`
- **Suggested lanes**
  1. `executor` (high): implement C1-C4 in bounded file set.
  2. `verifier` (high): check diff scope, ensure C1-C4 only, validate acceptance criteria.
  3. `code-reviewer` (high, optional before handoff): inspect cleanup quality and confirm no incidental redesign.
- **Verification path**
  - Ralph implementation lane finishes.
  - Verifier confirms required commands + manual check list coverage.
  - Ralph closes only after `docs/requirements_todo.md` status update is included.

### If follow-up execution goes through `team`
- **Suggested staffing**
  - Worker 1 (`executor`, high): C1 API client cleanup in `web_frontend/lib/api.ts` + direct caller updates.
  - Worker 2 (`executor`, high): C2/C3 `job-workspace.tsx` + shared duration/helper consolidation.
  - Worker 3 (`executor`, medium/high): C3/C4 remotion/export-preview helper cleanup + aspect-ratio rule unification.
  - Shared `verifier` (high): validate touch scope, compile/build output, and manual-check evidence.
- **Why these lanes exist**
  - C1 is isolated around API/auth/upload surface.
  - C2/C3 share `job-workspace.tsx` and local-helper simplification.
  - C3/C4 share preview/remotion helper usage and user-visible ratio formatting.
- **Launch hints**
  - `omx team run .omx/plans/requirements-c-frontend-cleanup-initial-ralplan.md`
  - or `$team .omx/plans/requirements-c-frontend-cleanup-initial-ralplan.md`
- **Team verification path**
  - Each worker proves its file set stayed within assigned ownership.
  - Team verifier runs `tsc` + `build`, checks manual flows list, and confirms `docs/requirements_todo.md` update.
  - After team handoff, Ralph-style final reviewer or `code-reviewer` confirms cross-lane cohesion before merge.
