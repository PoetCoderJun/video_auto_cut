# Render Font Scaling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebuild export-video typography sizing so subtitles, chapter cards, and progress labels stay readable across portrait and landscape resolutions.

**Architecture:** Extract the sizing and wrapping rules from the Remotion composition into a pure TypeScript typography helper, then consume that helper from the composition. Drive the refactor with focused unit tests that lock expected behavior for portrait, landscape, and ultrawide cases before touching the rendering component.

**Tech Stack:** Next.js 16, React 19, Remotion 4, TypeScript 5, Node 22 built-in test runner

---

### Task 1: Lock responsive typography behavior with failing tests

**Files:**
- Create: `web_frontend/lib/remotion/typography.test.ts`
- Test target: `web_frontend/lib/remotion/typography.ts`

**Step 1: Write the failing test**

Create tests that assert:
- portrait `1080x1920` keeps subtitle/chapter/progress fonts above explicit readability floors
- landscape `1920x1080` stays within upper bounds instead of overscaling
- narrow portrait `720x1280` still reserves enough label width and line wrapping capacity

**Step 2: Run test to verify it fails**

Run: `node --test --experimental-strip-types web_frontend/lib/remotion/typography.test.ts`
Expected: FAIL because `web_frontend/lib/remotion/typography.ts` or its exported helpers do not exist yet.

### Task 2: Implement pure typography sizing helpers

**Files:**
- Create: `web_frontend/lib/remotion/typography.ts`
- Modify: `web_frontend/lib/remotion/stitch-video-web.tsx`
- Test: `web_frontend/lib/remotion/typography.test.ts`

**Step 1: Write minimal implementation**

Implement pure helpers that:
- derive independent subtitle/chapter/progress font sizes from width, height, and orientation
- use clamped ranges instead of a single global linear short-edge scale
- compute subtitle wrapping width from the actual subtitle box width rather than only the frame short edge

**Step 2: Run test to verify it passes**

Run: `node --test --experimental-strip-types web_frontend/lib/remotion/typography.test.ts`
Expected: PASS

### Task 3: Wire the composition to the new helper and verify integration

**Files:**
- Modify: `web_frontend/lib/remotion/stitch-video-web.tsx`

**Step 1: Refactor composition**

Replace the inline typography math with the helper outputs while preserving current theme and layout structure.

**Step 2: Verify typecheck/build**

Run:
- `cd web_frontend && npx tsc --noEmit`
- `npm --prefix web_frontend run build`

Expected: PASS

