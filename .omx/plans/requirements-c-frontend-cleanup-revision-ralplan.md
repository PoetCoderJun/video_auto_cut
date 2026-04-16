# RALPLAN Final Revision Draft — C1-C4 Frontend Cleanup Batch

## 1) Principles
1. **Smallest safe touch set** — target execution branch is `chore/requirements-c-frontend-cleanup`; execution must pass a branch preflight before edits because the worktree is already dirty.
2. **C1 merges transport only** — unify fetch / assertOk / JSON parsing, but do not merge auth-source semantics.
3. **Contract-first cleanup** — only consolidate helpers when the runtime contract is explicitly identical.
4. **Close the scoped cleanup fully** — where C3 is retained in scope, pick one explicit contract and finish that cleanup in this batch rather than deferring design to execution.
5. **Explicit display rules beat heuristics** — C4 uses a fixed standard-label table first, then exact normalized fallback.

## 2) Decision Drivers
1. **Regression-sensitive surfaces**: auth/invite redemption, coupon redemption, job workspace, export preview.
2. **Dirty-tree blast-radius control**: execution needs a precise write set and clear read-only anchors.
3. **Semantic clarity**: C1/C3/C4 must encode exact precedence/contracts, not leave choices to the implementer.

## 3) Options

### Option A — Minimal-touch, explicit-contract cleanup (**Recommended**)
- C1: one private request core in `api.ts`; `options.authToken > authTokenProvider`; `requireAuth` errors only when neither yields a token.
- C2: local `job-workspace.tsx` simplification only.
- C3: finish two concrete cleanups only:
  - overlay-domain defaults/limits dedupe between `job-draft-storage.ts` and `overlay-controls.ts`
  - unify `mm:ss` formatter between `job-workspace.tsx` and `source-video-guard.ts`
- C4: explicit standard display table first, exact fallback second.
- **Pros**: lowest churn, fully specified, matches Architect/Critic guidance.
- **Cons**: leaves unrelated duplication outside this batch.

### Option B — Broader shared-utils extraction
- Pull request/clamp/duration/aspect-ratio logic into new shared frontend utilities and migrate all visible callers.
- **Pros**: stronger centralization.
- **Cons**: larger write set, higher conflict risk, more room for false equivalence.

### Option C — Keep current code largely intact and only document intended rules
- Limit batch to tiny edits plus comments/notes.
- **Pros**: lowest code churn.
- **Cons**: fails the goal of actually closing C3/C4 cleanup decisions in this batch.

**Recommendation:** Option A.

## 4) Final execution steps

### Preflight 0 — Confirm target execution branch
- Target execution branch: `chore/requirements-c-frontend-cleanup`
- Run `git branch --show-current` before any edits.
- If the current branch is not `chore/requirements-c-frontend-cleanup`, run `git switch chore/requirements-c-frontend-cleanup`.
- Only after confirming the target branch, continue to Step 1-6.

### Step 1 — Freeze write set vs read-only anchors
**Expected write set**
- `web_frontend/lib/api.ts`
- `web_frontend/components/home-page-client.tsx`
- `web_frontend/components/auth-page-client.tsx`
- `web_frontend/components/coupon-redeem-entry.tsx`
- `web_frontend/components/job-workspace.tsx`
- `web_frontend/lib/source-video-guard.ts`
- `web_frontend/lib/job-draft-storage.ts`
- `web_frontend/lib/remotion/overlay-controls.ts`
- `web_frontend/components/export-frame-preview.tsx`
- `docs/requirements_todo.md`

**Read-only validation anchors by default**
- `web_frontend/lib/remotion/export-bitrate.ts`
- `web_frontend/lib/remotion/typography.ts`
- `web_frontend/lib/remotion/dev-export-preview-presets.ts`
- `web_frontend/lib/job-draft-storage.test.mjs`
- `web_frontend/lib/remotion/export-bitrate.test.mjs`
- `web_frontend/lib/remotion/typography.test.mjs`

**Rule**
- The three remotion files above are **not expected write targets**; they are evidence / validation anchors unless a direct implementation need is documented during execution.

### Step 2 — C1: merge transport with fixed precedence
**Plan**
- Remove `uploadAudioDirectToOss` alias and move callers to `uploadAudio`.
- Replace `requestWithExplicitToken` with one private request core in `api.ts`.
- Request token precedence is fixed as:
  - **`options.authToken` first**
  - then `authTokenProvider` / resolved token path
- `requireAuth` throws only when **both** sources yield no token.
- Preserve both call styles for `activateInviteCode`:
  - `activateInviteCode(code)`
  - `activateInviteCode(code, token)`
- Explicitly review these callers:
  - `web_frontend/components/home-page-client.tsx`
  - `web_frontend/components/auth-page-client.tsx`
  - `web_frontend/components/coupon-redeem-entry.tsx`

**Acceptance criteria**
- `requestWithExplicitToken` is removed.
- Shared transport exists in one private core.
- Precedence is implemented as `options.authToken > authTokenProvider`.
- `requireAuth` only errors when both token sources are absent.
- No auth-source semantic drift beyond transport dedupe.

### Step 3 — C2: local `job-workspace.tsx` simplification
**Plan**
- Convert `getActiveStep` from switch to constant mapping + explicit fallback.
- Simplify `withTimeout` only if readability improves and timeout/error copy remains unchanged.
- Keep unrelated local helpers local.

**Acceptance criteria**
- Active-step resolution is table-driven.
- Timeout behavior and user-facing messaging are preserved.

### Step 4 — C3: complete the scoped helper cleanup in this batch
**Chosen route (fixed)**
- **Yes: this batch will unify the `formatDuration` duplication between `job-workspace.tsx` and `source-video-guard.ts`.**
- Shared contract is fixed as:
  - if value is **non-finite or <= 0** ⇒ `00:00`
  - else format as **`mm:ss`**
- This formatter may be shared only between these batch-owned callers.
- Also dedupe overlay-domain defaults/limits/clamp behavior between:
  - `web_frontend/lib/job-draft-storage.ts`
  - `web_frontend/lib/remotion/overlay-controls.ts`
- Do **not** broaden C3 into repo-wide clamp extraction.
- `export-bitrate.ts` and `typography.ts` remain read-only unless execution finds a direct blocker and documents it.

**Acceptance criteria**
- `job-workspace.tsx` and `source-video-guard.ts` use one consistent `mm:ss` formatter contract.
- Overlay defaults/limits duplication is reduced only within the overlay domain.
- No repo-wide clamp util is introduced.

### Step 5 — C4: fixed aspect-ratio decision rule + sample matrix
**Decision rule**
1. If the exact `(width,height)` belongs to a known product-facing standard preset family, display the mapped friendly label.
2. Otherwise, display the **exact normalized ratio** via gcd reduction.
3. No tolerance matching in this batch.

**Standard display table for this batch**
- 16:9 family → label `16:9`
- 9:16 family → label `9:16`
- 1:1 family → label `1:1`
- 4:3 family → label `4:3`
- 21:9 family → label `21:9`

**Required sample output matrix**
- `1920x1080 -> 16:9`
- `544x960 -> 9:16`
- `1080x1080 -> 1:1`
- `3440x1440 -> 21:9`
- `720x1268 -> 180:317`

**Acceptance criteria**
- `export-frame-preview.tsx` contains one canonical formatting path.
- The five sample outputs above are satisfied exactly.
- Non-standard sizes use exact normalized fallback.

### Step 6 — Verify, then update requirements
**Plan**
- Run mandatory compile/build checks.
- Run targeted tests when touched scope warrants them.
- Record manual verification across explicit-token auth, workspace, and ratio-label scenarios.
- Only after evidence is collected, move C items in `docs/requirements_todo.md` as appropriate.

## 5) Final verification plan

### Mandatory
1. `cd web_frontend && npx tsc --noEmit`
2. `npm --prefix web_frontend run build`

### Targeted tests
3. `node web_frontend/lib/job-draft-storage.test.mjs`
4. `node web_frontend/lib/remotion/export-bitrate.test.mjs`
5. `node web_frontend/lib/remotion/typography.test.mjs`

### Manual checks
1. **C1 auth paths**
   - `home-page-client.tsx`: `activateInviteCode(code)`
   - `auth-page-client.tsx`: `activateInviteCode(code, token)`
   - `coupon-redeem-entry.tsx`: `activateInviteCode(code, token)`
2. **C2 workspace behavior**
   - active-step rendering unchanged
   - timeout-backed flows keep same UX/error copy
3. **C3 formatter + overlay domain**
   - `job-workspace.tsx` and `source-video-guard.ts` both emit `00:00` for non-finite / `<=0`
   - overlay defaults and limits still round-trip correctly
4. **C4 ratio labels**
   - `1920x1080 -> 16:9`
   - `544x960 -> 9:16`
   - `1080x1080 -> 1:1`
   - `3440x1440 -> 21:9`
   - `720x1268 -> 180:317`

## 6) Risks & mitigations
- **Risk: C1 breaks explicit-token flows while deduping transport.**  
  **Mitigation:** hard-code precedence as `options.authToken > authTokenProvider`; verify all three `activateInviteCode` call paths.
- **Risk: write set expands into remotion helpers unnecessarily.**  
  **Mitigation:** keep `export-bitrate.ts`, `typography.ts`, and `dev-export-preview-presets.ts` read-only by default.
- **Risk: C3 reopens broad utility design.**  
  **Mitigation:** fix scope now: unify only overlay-domain duplicates plus the `job-workspace`/`source-video-guard` formatter.
- **Risk: C4 produces inconsistent labels.**  
  **Mitigation:** use explicit preset-family table plus exact fallback; validate against the required five-case matrix.
- **Risk: dirty tree causes accidental spillover.**  
  **Mitigation:** verifier checks touched files against the expected write set before signoff.

## 7) ADR

### Decision
Execute C1-C4 as a **minimal-touch, fully specified cleanup batch** on target branch `chore/requirements-c-frontend-cleanup` after branch preflight: merge API transport only, simplify `job-workspace.tsx` locally, complete the scoped duration/overlay cleanup, and use explicit standard ratio labels with exact fallback.

### Drivers
- High regression sensitivity on user-facing flows.
- Need for strict write-scope control in a dirty tree.
- Need to remove execution-time ambiguity from C1/C3/C4.

### Alternatives considered
1. **Option A (chosen):** minimal-touch, explicit-contract cleanup.
2. **Option B:** broader shared-utils extraction.
3. **Option C:** defer most cleanup decisions and only make tiny edits.

### Why chosen
Option A is the smallest plan that still fully closes the open design questions called out by Architect and Critic.

### Consequences
- The batch stays executable with a narrow write set.
- Some unrelated duplication remains intentionally deferred.
- C3 is actually closed in this round instead of being left to implementer judgment.

### Follow-ups
- If future cleanup wants broader shared frontend utils, open a separate batch.
- If product later wants more named ratio labels, add a new requirement rather than widening C4.

## 8) Agent roster + ralph/team staffing + verification path

### Available agent roster
- `architect`
- `critic`
- `planner`
- `explore` / `explorer`
- `executor` / `worker`
- `code-reviewer`
- `verifier`
- `test-engineer`
- `build-fixer`

### Ralph staffing
- **Executor (high)**: implement Steps 2-5 within the expected write set only.
- **Verifier (high)**: check touched-file scope, run validation, confirm manual matrix.
- **Code-reviewer (high, optional)**: verify C1 precedence/auth semantics and C4 rule fidelity.

**Ralph verification path**
1. Executor completes bounded diff.
2. Verifier confirms no unplanned writes outside expected write set.
3. Verifier runs mandatory checks + targeted tests.
4. Verifier confirms manual auth/workspace/ratio matrix.
5. Then update `docs/requirements_todo.md`.

### Team staffing
- **Worker 1 — C1 API/auth lane (`executor`, high)**
  - Write ownership: `web_frontend/lib/api.ts`, `web_frontend/components/home-page-client.tsx`, `web_frontend/components/auth-page-client.tsx`, `web_frontend/components/coupon-redeem-entry.tsx`
- **Worker 2 — C2/C3 workspace lane (`executor`, high)**
  - Write ownership: `web_frontend/components/job-workspace.tsx`, `web_frontend/lib/source-video-guard.ts`
- **Worker 3 — C3/C4 preview lane (`executor`, high)**
  - Write ownership: `web_frontend/lib/job-draft-storage.ts`, `web_frontend/lib/remotion/overlay-controls.ts`, `web_frontend/components/export-frame-preview.tsx`
- **Shared verifier (`verifier`, high)**
  - Validation ownership only; no feature edits.

### Suggested reasoning by lane
- C1 auth/API lane: **high**
- C2/C3 workspace lane: **high**
- C3/C4 preview lane: **high**
- Verification lane: **high**

### Launch hints
- `omx team run .omx/plans/requirements-c-frontend-cleanup-revision-ralplan.md`
- `$team .omx/plans/requirements-c-frontend-cleanup-revision-ralplan.md`
- `$ralph .omx/plans/requirements-c-frontend-cleanup-revision-ralplan.md`

### Team verification path
1. Workers stay inside assigned write ownership.
2. Verifier checks write set vs read-only anchors.
3. Run `tsc` + `build`.
4. Run `job-draft-storage.test.mjs`, `export-bitrate.test.mjs`, `typography.test.mjs`.
5. Confirm three auth flows, workspace UX, and the five-case ratio matrix.
6. Final reviewer confirms plan fidelity before merge/handoff.
